"""Database access.

Connections are opened read-only wherever the database supports it, so the SQL guard is not
the only thing between the model and the data. Queries run inside a transaction that is
always rolled back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url

# SQLAlchemy backend name -> sqlglot dialect name
SQLGLOT_DIALECTS = {"postgresql": "postgres", "snowflake": "snowflake", "sqlite": "sqlite"}


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool


def make_engine(url: str, statement_timeout_ms: int = 15_000) -> Engine:
    u = make_url(url)
    backend = u.get_backend_name()

    if backend == "postgresql":
        options = f"-c default_transaction_read_only=on -c statement_timeout={statement_timeout_ms}"
        return sa.create_engine(u, connect_args={"options": options}, pool_pre_ping=True)

    if backend == "sqlite":
        # mode=ro: SQLite itself refuses to write to the file
        if u.database and u.database != ":memory:" and not u.database.startswith("file:"):
            u = u.set(database=f"file:{u.database}", query={"mode": "ro", "uri": "true"})
        return sa.create_engine(u)

    if backend == "snowflake":
        # Snowflake has no read-only session switch. Connect with a role that only has
        # USAGE and SELECT grants; the timeout keeps a runaway query from burning credits.
        timeout_s = max(1, statement_timeout_ms // 1000)
        params = {"STATEMENT_TIMEOUT_IN_SECONDS": timeout_s}
        return sa.create_engine(u, connect_args={"session_parameters": params})

    raise ValueError(f"Unsupported database {backend!r}; use postgresql, snowflake, or sqlite.")


def _execute(engine: Engine, sql: str, max_rows: int | None) -> tuple[list[str], list[tuple[Any, ...]]]:
    # The query goes to the driver's cursor with no parameters at all. Going through SQLAlchemy would
    # pass an empty parameter set, and drivers like psycopg then read the % in LIKE '%x%' as a placeholder.
    with engine.connect() as conn, conn.begin() as tx:
        cursor = conn.connection.cursor()
        try:
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description or []]
            rows = cursor.fetchall() if max_rows is None else cursor.fetchmany(max_rows + 1)
        finally:
            cursor.close()
            tx.rollback()
    return columns, [tuple(r) for r in rows]


def run_query(engine: Engine, sql: str, max_rows: int) -> QueryResult:
    columns, rows = _execute(engine, sql, max_rows)
    return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)


def explain(engine: Engine, sql: str) -> None:
    """Have the database plan the query without running it.

    This catches unknown tables and columns, bad joins, and type errors cheaply.
    Raises the driver's error if the database rejects the query.
    """
    prefix = {"sqlite": "EXPLAIN QUERY PLAN ", "snowflake": "EXPLAIN USING TEXT "}.get(engine.dialect.name, "EXPLAIN ")
    _execute(engine, prefix + sql, max_rows=None)


def short_error(exc: BaseException, limit: int = 500) -> str:
    """The useful part of a database error: the driver's message and any hint, without the SQL echo."""
    orig = getattr(exc, "orig", None) or exc
    text = str(orig).split("[SQL:")[0].strip()
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()][:4]
    return " | ".join(lines)[:limit]
