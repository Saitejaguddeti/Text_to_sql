from conftest import ScriptedLLM

from text_to_sql.agent import TextToSQLAgent

TOP_MERCHANTS = """```sql
SELECT t.merchant, ROUND(-SUM(t.amount), 2) AS card_spend
FROM transactions t
WHERE t.txn_type = 'card_purchase'
GROUP BY t.merchant
ORDER BY card_spend DESC
LIMIT 3
```"""


def make_agent(engine, replies, **kwargs):
    llm = ScriptedLLM(replies=replies)
    return TextToSQLAgent(
        llm, engine, notes="Card spend is the negative of amount on card_purchase rows.", **kwargs
    ), llm


def test_happy_path(engine):
    agent, llm = make_agent(engine, [TOP_MERCHANTS, "These are the top three merchants."])
    state = agent.ask("Which 3 merchants had the most card spend?")

    assert state["attempts"] == 1
    assert state["columns"] == ["merchant", "card_spend"]
    assert len(state["rows"]) == 3
    assert state["answer"] == "These are the top three merchants."
    # the schema, the dialect, and the business notes all reach the model
    system_prompt = llm.calls[0][0].content
    assert "TABLE transactions" in system_prompt and "sqlite" in system_prompt
    assert "negative of amount" in system_prompt
    # and the answer prompt carries the rows that came back
    top_merchant = state["rows"][0][0]
    assert top_merchant in llm.calls[1][-1].content


def test_unsafe_sql_is_sent_back_and_never_runs(engine):
    agent, llm = make_agent(engine, ["DELETE FROM transactions", TOP_MERCHANTS, "Answer."])
    state = agent.ask("Clean up the transactions and show the top merchants")

    assert state["attempts"] == 2
    assert len(state["rows"]) == 3
    retry_prompt = llm.calls[1][-1].content
    assert "Only SELECT queries are allowed; this is DELETE" in retry_prompt


def test_database_errors_are_fed_back(engine):
    bad = "SELECT merchant, SUM(amount) FROM transactions WHERE trade_date >= '2026-07-01' GROUP BY merchant"
    agent, llm = make_agent(engine, [bad, TOP_MERCHANTS, "Answer."])
    state = agent.ask("Top merchants since July")

    assert state["attempts"] == 2
    assert "no such column" in llm.calls[1][-1].content


def test_gives_up_after_max_attempts(engine):
    agent, llm = make_agent(engine, ["DROP TABLE accounts"] * 3, max_attempts=3)
    state = agent.ask("Drop the accounts table")

    assert state["attempts"] == 3
    assert "rows" not in state
    assert state["answer"].startswith("I could not get a safe, working query after 3 attempts")
    assert len(llm.calls) == 3  # no answer call when nothing ran


def test_row_cap_applies_to_model_sql(engine):
    agent, _ = make_agent(engine, ["SELECT * FROM transactions", "Lots of transactions."], max_rows=25)
    state = agent.ask("Show me every transaction")

    assert len(state["rows"]) == 25
    assert state["sql"].rstrip().endswith("LIMIT 25")
