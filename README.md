# Text-to-SQL Agent

A LangGraph agent that answers plain-English questions from a SQL database. It looks up the tables and
columns that matter for the question, has an LLM write the query, checks the query, runs it read-only,
and answers from the rows that come back.

It works with Postgres and Snowflake. A SQLite copy of the sample database is included, so you can try it
without setting up a server.

## How it works

```mermaid
flowchart LR
    Q([question]) --> S[load_schema]
    S --> W[write_sql]
    W --> C{check_sql}
    C -- ok --> R{run_sql}
    R -- ok --> A[answer]
    C -- rejected or invalid --> W
    R -- failed --> W
    C -. out of attempts .-> G[give_up]
    R -. out of attempts .-> G
```

| Step | What it does |
|---|---|
| `load_schema` | Reads tables, columns, keys, and comments through SQLAlchemy's inspector. Small schemas go to the model whole. Bigger ones are ranked by how well table and column names match the question, and the tables they join to are added. |
| `write_sql` | Sends the schema, optional business notes, and the question to the model and asks for one query. On a retry it also sends the failed query and the reason it failed. |
| `check_sql` | Parses the query with sqlglot and rejects anything that is not a single read-only SELECT (see below). Then it runs `EXPLAIN`, so a wrong table or column name is caught without running the query. |
| `run_sql` | Runs the query in a read-only transaction that is always rolled back, and fetches at most `MAX_ROWS` rows. |
| `answer` | Has the model answer the question from the rows, and say so when the result is empty or was cut off. |
| `give_up` | After `MAX_ATTEMPTS` failed tries, stops and reports the last problem instead of guessing. |

## Read-only, in three layers

The agent can only read. Each layer below would stop a write on its own; they are stacked on purpose.

1. **SQL guard** (`sql_guard.py`). The query is parsed, not matched with regexes, and must be exactly one
   SELECT-style statement. CTEs, joins, subqueries, and UNION are fine. It rejects INSERT, UPDATE, DELETE,
   MERGE, DDL, TRUNCATE, GRANT/REVOKE, COPY, `SELECT ... INTO`, `FOR UPDATE`, SET, transaction control,
   a second statement hidden after a comment, data-modifying CTEs (`WITH x AS (DELETE ...)`), and
   side-effect functions such as `pg_sleep`, `set_config`, `nextval`, and Snowflake `SYSTEM$` functions.
   It also adds a `LIMIT` when the query has none, and lowers one that is too big.
2. **Read-only connection** (`db.py`). Postgres sessions start with `default_transaction_read_only=on` and
   a statement timeout. SQLite is opened with `mode=ro`. Snowflake gets a statement timeout and relies on
   layer 3.
3. **Read-only role.** `db/init/04_readonly_role.sql` creates `agent_reader`, which can only SELECT. On
   Snowflake, connect with a role that has nothing but USAGE and SELECT grants.

The Postgres tests check layers 2 and 3 directly: they send `CREATE TABLE`, `DELETE`, and `UPDATE` straight
to the database, skipping the guard, and expect the database to refuse.

What the guard says about a few bad queries:

```
DELETE FROM transactions WHERE posted_on < '2026-05-01'
  -> Only SELECT queries are allowed; this is DELETE.
SELECT * FROM accounts; DROP TABLE accounts
  -> Expected exactly one statement, got 2.
SELECT pg_sleep(60)
  -> The function pg_sleep() is not allowed.
```

## Quick start

### SQLite demo

macOS / Linux:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[anthropic]"        # or ".[openai]" / ".[bedrock]"
python scripts/build_demo_db.py      # creates demo.db
cp .env.example .env                 # set LLM_MODEL and your API key
text-to-sql "Which 5 merchants had the most card spend in Q3 2026?"
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[anthropic]"
python scripts/build_demo_db.py
Copy-Item .env.example .env          # then set LLM_MODEL and your API key in .env
text-to-sql "Which 5 merchants had the most card spend in Q3 2026?"
```

Run `text-to-sql` with no question to get an interactive prompt.

### Postgres

```bash
docker compose up -d
pip install -e ".[postgres,anthropic]"
export DATABASE_URL=postgresql+psycopg://agent_reader:agent_reader@localhost:5432/bank
# PowerShell: $env:DATABASE_URL = "postgresql+psycopg://agent_reader:agent_reader@localhost:5432/bank"
text-to-sql "Which branch has the most premier customers?"
```

If port 5432 is already taken (for example by another Postgres container), change the mapping in
`docker-compose.yml` to `"5433:5432"` and use `localhost:5433` in `DATABASE_URL`.

### Snowflake

```bash
pip install -e ".[snowflake,anthropic]"
export DATABASE_URL="snowflake://USER:PASSWORD@ACCOUNT/DATABASE/SCHEMA?warehouse=WH&role=READ_ONLY_ROLE"
```

Table and column comments are sent to the model with the schema (Postgres and Snowflake both have them),
so well-commented tables get better SQL. For databases without comments, put the same kind of notes in a
file and point `SCHEMA_NOTES_FILE` at it, like `db/schema_notes.md`.

## Example

For "Which 5 merchants had the most card spend in Q3 2026?" the model writes a query along these lines.
This is the query as the guard returns it, and the rows it gets from the demo database:

```sql
SELECT
  t.merchant,
  ROUND(-SUM(t.amount), 2) AS card_spend
FROM transactions AS t
WHERE
  t.txn_type = 'card_purchase'
  AND t.posted_on >= '2026-07-01'
  AND t.posted_on < '2026-10-01'
GROUP BY
  t.merchant
ORDER BY
  card_spend DESC
LIMIT 5
```

```
merchant        | card_spend
----------------+-----------
Best Buy        | 23654.43
Delta Air Lines | 23005.62
Marriott        | 9661.74
Costco          | 9251.7
Duke Energy     | 7118.68
```

The answer step turns those rows into a sentence or two. The exact SQL and wording depend on the model.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | required | Chat model as `provider:model`, passed to LangChain's `init_chat_model`, for example `anthropic:claude-sonnet-5-5` |
| `DATABASE_URL` | `sqlite:///demo.db` | SQLAlchemy URL |
| `SCHEMA_NOTES_FILE` | none | Text file with business notes added to the prompt |
| `MAX_ROWS` | `200` | Row cap added to every query and applied when fetching |
| `MAX_ATTEMPTS` | `3` | Tries before the agent gives up |
| `STATEMENT_TIMEOUT_MS` | `15000` | Query timeout on Postgres and Snowflake |

## Using it from Python

```python
from langchain.chat_models import init_chat_model

from text_to_sql import TextToSQLAgent
from text_to_sql.db import make_engine

agent = TextToSQLAgent(init_chat_model("anthropic:claude-sonnet-5-5"), make_engine("sqlite:///demo.db"))
state = agent.ask("How many open savings accounts are there?")
print(state["sql"])
print(state["rows"])
print(state["answer"])
```

## Tests

```bash
pip install -e ".[dev,postgres]"
pytest
```

The tests use a scripted stand-in for the model, so they need no API key. They cover the guard (allowed
and blocked SQL), the read-only SQLite connection, schema loading and table picking, the retry loop
(unsafe SQL, a bad column name, giving up), the row cap, and the CLI. The Postgres tests run when
`TEST_DATABASE_URL` is set. CI loads `db/init` into a Postgres service and runs them as `agent_reader`.

## Project layout

```
src/text_to_sql/
  agent.py       LangGraph graph and nodes
  sql_guard.py   read-only checks and row cap (sqlglot)
  schema.py      catalog from the database, table picking, schema text for the prompt
  db.py          read-only engines, query execution, EXPLAIN
  prompts.py     prompt text
  cli.py         command line
db/init/         schema, sample data, column comments, read-only role (run by Postgres on first start)
db/schema_notes.md
scripts/         sample data generator and SQLite demo builder
tests/
```

## Limitations

- Table picking is keyword matching. For a warehouse with hundreds of tables, embedding search over table
  and column descriptions would pick better.
- Each question stands alone; there is no follow-up memory yet.
- The model sees the schema and up to 50 result rows. Columns that should never leave the database should
  be hidden from the role the agent connects as.
- The sample data is made up.

## License

MIT
