from conftest import ScriptedLLM

from text_to_sql.cli import main

SQL = """```sql
SELECT c.segment, COUNT(*) AS customers
FROM customers c
GROUP BY c.segment
ORDER BY customers DESC
```"""


def test_cli_prints_sql_rows_and_answer(demo_db, monkeypatch, capsys):
    llm = ScriptedLLM(replies=[SQL, "Most customers are in the retail segment."])
    monkeypatch.setattr("langchain.chat_models.init_chat_model", lambda model, **kwargs: llm)
    monkeypatch.setenv("LLM_MODEL", "scripted:test")
    monkeypatch.delenv("SCHEMA_NOTES_FILE", raising=False)

    code = main(["--db", f"sqlite:///{demo_db}", "How", "many", "customers", "per", "segment?"])

    out = capsys.readouterr().out
    assert code == 0
    assert "SQL:" in out and "GROUP BY" in out
    assert "segment" in out and "retail" in out
    assert out.rstrip().endswith("Most customers are in the retail segment.")
    assert llm.calls[0][1].content == "How many customers per segment?"


def test_cli_needs_a_model(monkeypatch, capsys):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    try:
        main(["anything"])
    except SystemExit as e:
        assert e.code == 2
    assert "LLM_MODEL" in capsys.readouterr().err


def test_cli_reports_a_missing_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_MODEL", "scripted:test")
    monkeypatch.delenv("SCHEMA_NOTES_FILE", raising=False)

    code = main(["--db", f"sqlite:///{tmp_path / 'missing.db'}", "anything"])

    err = capsys.readouterr().err
    assert code == 2
    assert "Could not connect to the database" in err
    assert "build_demo_db.py" in err
