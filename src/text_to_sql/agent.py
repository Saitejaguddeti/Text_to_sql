"""The LangGraph agent.

    load_schema -> write_sql -> check_sql -> run_sql -> answer

If check_sql or run_sql fails, the error is sent back to write_sql so the model can fix its query.
After max_attempts tries the graph stops at give_up instead.

Each node returns only the keys it changes; LangGraph merges them into the state.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy.engine import Engine

from . import prompts
from .db import SQLGLOT_DIALECTS, explain, run_query, short_error
from .schema import Table, load_catalog, pick_tables, render
from .sql_guard import check_sql, extract_sql


class AgentState(TypedDict, total=False):
    question: str
    tables: list[str]
    schema: str
    draft_sql: str  # what the model wrote last
    sql: str  # the query that passed the checks (normalized, with a row cap)
    error: str  # why the last attempt failed; empty when the step succeeded
    attempts: int
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool
    answer: str


class TextToSQLAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        engine: Engine,
        *,
        max_rows: int = 200,
        max_attempts: int = 3,
        notes: str = "",
        table_limit: int = 6,
    ) -> None:
        if engine.dialect.name not in SQLGLOT_DIALECTS:
            raise ValueError(f"Unsupported database: {engine.dialect.name}")
        self.llm = llm
        self.engine = engine
        self.dialect = SQLGLOT_DIALECTS[engine.dialect.name]
        self.max_rows = max_rows
        self.max_attempts = max_attempts
        self.notes = notes.strip()
        self.table_limit = table_limit
        self._catalog: list[Table] | None = None
        self.graph = self._build_graph()

    def ask(self, question: str) -> AgentState:
        return self.graph.invoke({"question": question, "attempts": 0, "error": ""})

    # ------------------------------------------------------------------ nodes
    def load_schema(self, state: AgentState) -> dict:
        if self._catalog is None:
            self._catalog = load_catalog(self.engine)
        tables = pick_tables(state["question"], self._catalog, self.table_limit)
        return {"tables": [t.name for t in tables], "schema": render(tables)}

    def write_sql(self, state: AgentState) -> dict:
        notes = prompts.NOTES.format(notes=self.notes) if self.notes else ""
        messages: list[BaseMessage] = [
            SystemMessage(prompts.WRITE_SQL.format(dialect=self.dialect, schema=state["schema"], notes=notes)),
            HumanMessage(state["question"]),
        ]
        if state.get("error"):
            # show the model its last attempt and what went wrong with it
            messages += [
                AIMessage(f"```sql\n{extract_sql(state['draft_sql'])}\n```"),
                HumanMessage(prompts.RETRY.format(error=state["error"])),
            ]
        reply = self.llm.invoke(messages)
        return {"draft_sql": reply.text, "attempts": state.get("attempts", 0) + 1, "error": ""}

    def check(self, state: AgentState) -> dict:
        verdict = check_sql(state["draft_sql"], self.dialect, self.max_rows)
        if not verdict.ok:
            return {"error": verdict.reason}
        try:
            explain(self.engine, verdict.sql)
        except Exception as e:  # unknown column, bad join, type mismatch, ...
            return {"error": f"The database rejected the query: {short_error(e)}"}
        return {"sql": verdict.sql}

    def run(self, state: AgentState) -> dict:
        try:
            result = run_query(self.engine, state["sql"], self.max_rows)
        except Exception as e:
            return {"error": f"The query failed when it ran: {short_error(e)}"}
        return {"columns": result.columns, "rows": result.rows, "truncated": result.truncated}

    def answer(self, state: AgentState) -> dict:
        rows = state.get("rows", [])
        user = prompts.ANSWER_USER.format(
            question=state["question"],
            sql=state["sql"],
            count=len(rows),
            cut_off=", cut off at the row limit" if state.get("truncated") else "",
            table=format_table(state.get("columns", []), rows, max_rows=50),
        )
        system = prompts.ANSWER_SYSTEM.format(max_rows=self.max_rows)
        reply = self.llm.invoke([SystemMessage(system), HumanMessage(user)])
        return {"answer": reply.text}

    def give_up(self, state: AgentState) -> dict:
        return {
            "answer": (
                f"I could not get a safe, working query after {state.get('attempts', 0)} attempts. "
                f"Last problem: {state.get('error')}"
            )
        }

    # ------------------------------------------------------------------ graph
    def _next_or_retry(self, next_node: str):
        def route(state: AgentState) -> str:
            if not state.get("error"):
                return next_node
            return "write_sql" if state.get("attempts", 0) < self.max_attempts else "give_up"

        return route

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("load_schema", self.load_schema)
        g.add_node("write_sql", self.write_sql)
        g.add_node("check_sql", self.check)
        g.add_node("run_sql", self.run)
        g.add_node("answer", self.answer)
        g.add_node("give_up", self.give_up)

        g.add_edge(START, "load_schema")
        g.add_edge("load_schema", "write_sql")
        g.add_edge("write_sql", "check_sql")
        g.add_conditional_edges("check_sql", self._next_or_retry("run_sql"), ["run_sql", "write_sql", "give_up"])
        g.add_conditional_edges("run_sql", self._next_or_retry("answer"), ["answer", "write_sql", "give_up"])
        g.add_edge("answer", END)
        g.add_edge("give_up", END)
        return g.compile()


def format_table(columns: list[str], rows: list[tuple[Any, ...]], max_rows: int = 20) -> str:
    """Plain-text table for the terminal and for the answer prompt."""
    if not columns:
        return "(no columns)"
    shown = [["" if v is None else str(v) for v in row] for row in rows[:max_rows]]
    widths = [max([len(c)] + [len(r[i]) for r in shown]) for i, c in enumerate(columns)]
    line = " | ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)).rstrip()
    out = [line, "-+-".join("-" * w for w in widths)]
    out += [" | ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)).rstrip() for r in shown]
    if not rows:
        out.append("(no rows)")
    elif len(rows) > max_rows:
        out.append(f"... {len(rows) - max_rows} more rows")
    return "\n".join(out)
