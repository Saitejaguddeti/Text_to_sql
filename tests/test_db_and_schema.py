import pytest

from text_to_sql.db import explain, run_query, short_error
from text_to_sql.schema import load_catalog, pick_tables, render


def test_sqlite_connection_refuses_writes(engine):
    # even if something got past the guard, the file is opened read-only
    with pytest.raises(Exception) as err, engine.connect() as conn:
        conn.exec_driver_sql("DELETE FROM transactions")
    assert "readonly" in str(err.value).lower()


def test_run_query_caps_rows_and_flags_truncation(engine):
    result = run_query(engine, "SELECT transaction_id FROM transactions ORDER BY transaction_id", max_rows=5)
    assert result.columns == ["transaction_id"]
    assert [r[0] for r in result.rows] == [1, 2, 3, 4, 5]
    assert result.truncated


def test_explain_catches_unknown_columns(engine):
    with pytest.raises(Exception) as err:
        explain(engine, "SELECT trade_date FROM transactions")
    assert "no such column" in short_error(err.value)


def test_catalog_has_tables_keys_and_foreign_keys(engine):
    catalog = {t.name: t for t in load_catalog(engine)}
    assert set(catalog) == {"accounts", "branches", "customers", "transactions"}
    assert catalog["transactions"].primary_key == ["transaction_id"]
    assert ("account_id", "accounts", "account_id") in catalog["transactions"].foreign_keys


def test_small_schemas_are_sent_whole(engine):
    catalog = load_catalog(engine)
    assert pick_tables("anything at all", catalog, limit=6) == catalog


def test_ranking_picks_matching_tables_and_their_join_targets(engine):
    catalog = load_catalog(engine)
    chosen = [t.name for t in pick_tables("total card spend by merchant in July", catalog, limit=1)]
    assert chosen[0] == "transactions"
    assert "accounts" in chosen  # transactions.account_id -> accounts, needed for joins


def test_render_shows_keys(engine):
    text = render(load_catalog(engine))
    assert "TABLE transactions" in text
    assert "account_id INTEGER REFERENCES accounts.account_id NOT NULL" in text
    assert "transaction_id INTEGER PRIMARY KEY" in text
