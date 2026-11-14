"""Integration tests against Postgres loaded from db/init (docker compose or the CI service).

They run only when TEST_DATABASE_URL points at the read-only role, for example
postgresql+psycopg://agent_reader:agent_reader@localhost:5432/bank
"""

import os

import pytest
from conftest import ScriptedLLM

from text_to_sql.agent import TextToSQLAgent
from text_to_sql.db import make_engine, run_query
from text_to_sql.schema import load_catalog

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture()
def pg():
    eng = make_engine(URL)
    yield eng
    eng.dispose()


def test_reads_work(pg):
    result = run_query(pg, "SELECT COUNT(*) FROM transactions WHERE merchant LIKE '%Air%'", max_rows=10)
    assert result.rows[0][0] > 0


@pytest.mark.parametrize(
    "statement",
    ["CREATE TABLE scratch (id int)", "DELETE FROM transactions", "UPDATE accounts SET balance = 0"],
)
def test_database_refuses_writes_even_without_the_guard(pg, statement):
    with pytest.raises(Exception) as err, pg.connect() as conn:
        conn.exec_driver_sql(statement)
    message = str(err.value).lower()
    assert "read-only" in message or "permission denied" in message


def test_column_comments_reach_the_catalog(pg):
    catalog = {t.name: t for t in load_catalog(pg)}
    amount = next(c for c in catalog["transactions"].columns if c.name == "amount")
    assert amount.comment and "money in" in amount.comment


def test_agent_end_to_end(pg):
    sql = """```sql
    SELECT b.branch_name, COUNT(*) AS customers
    FROM customers c JOIN branches b ON b.branch_id = c.branch_id
    GROUP BY b.branch_name ORDER BY customers DESC, b.branch_name
    ```"""
    agent = TextToSQLAgent(ScriptedLLM(replies=[sql, "Answer."]), pg)
    state = agent.ask("Which branch has the most customers?")
    assert state["attempts"] == 1
    assert state["columns"] == ["branch_name", "customers"]
    assert sum(r[1] for r in state["rows"]) == 30
