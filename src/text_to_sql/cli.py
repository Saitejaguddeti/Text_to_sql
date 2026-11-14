"""Command line: text-to-sql "Which branch has the most customers?"

With no question it opens a prompt and keeps asking until you enter a blank line.
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from sqlalchemy.exc import SQLAlchemyError

from .agent import TextToSQLAgent, format_table
from .config import load_settings
from .db import make_engine, short_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="text-to-sql",
        description="Answer a plain-English question from a SQL database using read-only queries.",
    )
    parser.add_argument("question", nargs="*", help="the question (leave out for an interactive prompt)")
    parser.add_argument("--db", help="SQLAlchemy URL; overrides DATABASE_URL")
    parser.add_argument("--model", help="chat model as provider:model; overrides LLM_MODEL")
    parser.add_argument("--quiet", action="store_true", help="print only the answer")
    args = parser.parse_args(argv)

    settings = load_settings()
    model = args.model or settings.llm_model
    if not model:
        parser.error("set LLM_MODEL (for example anthropic:claude-sonnet-5-5) or pass --model")

    engine = make_engine(args.db or settings.database_url, settings.statement_timeout_ms)
    try:
        with engine.connect():
            pass
    except SQLAlchemyError as e:
        hint = ""
        if engine.dialect.name == "sqlite":
            hint = "\nFor the demo database, run: python scripts/build_demo_db.py"
        print(f"Could not connect to the database: {short_error(e)}{hint}", file=sys.stderr)
        return 2

    # imported here so --help works without a model provider installed
    from langchain.chat_models import init_chat_model

    agent = TextToSQLAgent(
        init_chat_model(model),
        engine,
        max_rows=settings.max_rows,
        max_attempts=settings.max_attempts,
        notes=settings.schema_notes,
    )

    if args.question:
        return _ask(agent, " ".join(args.question), args.quiet)

    while True:
        try:
            question = input("\nquestion> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            return 0
        _ask(agent, question, args.quiet)


def _ask(agent: TextToSQLAgent, question: str, quiet: bool) -> int:
    state = agent.ask(question)
    if not quiet and state.get("sql"):
        print("\nSQL:\n" + textwrap.indent(state["sql"], "  "))
        if "rows" in state:
            more = " (cut off at the row limit)" if state.get("truncated") else ""
            print(f"\n{len(state['rows'])} rows{more}:")
            print(textwrap.indent(format_table(state["columns"], state["rows"]), "  "))
    print("\n" + state.get("answer", ""))
    return 0 if "rows" in state else 1


if __name__ == "__main__":
    sys.exit(main())
