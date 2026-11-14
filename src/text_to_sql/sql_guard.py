"""Read-only guard for model-written SQL.

The SQL is parsed with sqlglot, not pattern-matched, and has to be a single SELECT-style query
(CTEs, joins, subqueries, and UNION are fine). Anything that writes data, changes schema or
permissions, locks rows, changes session state, or calls a known side-effect function is
rejected before the database ever sees it. Accepted queries get a row cap added.

This is one of three layers; the read-only connection and the read-only database role are the
other two (see db.py and db/init/04_readonly_role.sql).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

# sqlglot logs a warning for every statement it can only parse as a generic command
logging.getLogger("sqlglot").setLevel(logging.ERROR)

_FORBIDDEN_NODES: dict[type[exp.Expression], str] = {
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Delete: "DELETE",
    exp.Merge: "MERGE",
    exp.Create: "CREATE",
    exp.Drop: "DROP",
    exp.Alter: "ALTER",
    exp.TruncateTable: "TRUNCATE",
    exp.Into: "SELECT ... INTO (it creates a table)",
    exp.Lock: "FOR UPDATE / FOR SHARE (it locks rows)",
    exp.Grant: "GRANT",
    exp.Revoke: "REVOKE",
    exp.Copy: "COPY",
    exp.Set: "SET",
    exp.Use: "USE",
    exp.Transaction: "BEGIN",
    exp.Commit: "COMMIT",
    exp.Rollback: "ROLLBACK",
    exp.Pragma: "PRAGMA",
    exp.LoadData: "LOAD DATA",
    exp.Analyze: "ANALYZE",
    exp.Comment: "COMMENT",
    exp.Cache: "CACHE",
    exp.Uncache: "UNCACHE",
    exp.Kill: "KILL",
    exp.Execute: "EXECUTE",
    exp.Command: "a raw command",
}

# Functions that sleep, signal other sessions, touch files, or change sequences/settings.
_FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_notify",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_switch_wal",
    "lo_import",
    "lo_export",
    "lo_unlink",
    "dblink",
    "dblink_exec",
    "set_config",
    "nextval",
    "setval",
    "load_extension",
    "readfile",
    "writefile",
    "edit",
}

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    sql: str = ""
    reason: str = ""


def extract_sql(text: str) -> str:
    """Pull the SQL out of a model reply: the first ```sql block if there is one, else the whole reply."""
    m = _FENCE.search(text)
    sql = m.group(1) if m else text
    return sql.strip().rstrip(";").strip()


def check_sql(sql: str, dialect: str, max_rows: int = 200) -> GuardResult:
    text = extract_sql(sql)
    if not text:
        return GuardResult(False, reason="No SQL was produced.")

    try:
        statements = [s for s in sqlglot.parse(text, read=dialect) if s is not None]
    except (ParseError, TokenError) as e:
        return GuardResult(False, reason=f"The SQL could not be parsed: {str(e).splitlines()[0][:200]}")

    if len(statements) != 1:
        return GuardResult(False, reason=f"Expected exactly one statement, got {len(statements)}.")
    tree = statements[0]

    if not isinstance(tree, exp.Query):
        label = _FORBIDDEN_NODES.get(type(tree), tree.key.upper())
        return GuardResult(False, reason=f"Only SELECT queries are allowed; this is {label}.")

    for node in tree.walk():
        for node_type, label in _FORBIDDEN_NODES.items():
            if isinstance(node, node_type):
                return GuardResult(False, reason=f"The query contains {label}, which is not allowed.")
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if name in _FORBIDDEN_FUNCTIONS or name.startswith("system$"):
                return GuardResult(False, reason=f"The function {name}() is not allowed.")

    capped = _cap_rows(tree, max_rows)
    return GuardResult(True, sql=capped.sql(dialect=dialect, pretty=True))


def _function_name(node: exp.Func) -> str:
    name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
    return (name or "").lower()


def _cap_rows(tree: exp.Query, max_rows: int) -> exp.Query:
    """Add LIMIT max_rows, or lower a bigger limit. Odd limits (FETCH FIRST, LIMIT ALL) get wrapped."""
    limit = tree.args.get("limit")
    if limit is None:
        return tree.limit(max_rows)
    value = limit.expression if isinstance(limit, exp.Limit) else None
    if isinstance(value, exp.Literal) and value.is_int and int(value.this) <= max_rows:
        return tree
    return exp.select("*").from_(tree.subquery("capped")).limit(max_rows)
