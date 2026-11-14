"""Table and column details for the prompt.

The catalog comes from SQLAlchemy's inspector, so it works the same way on Postgres,
Snowflake, and SQLite, and it picks up table and column comments where the database has them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.engine import Engine


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    comment: str | None = None


@dataclass
class Table:
    name: str
    columns: list[Column]
    primary_key: list[str] = field(default_factory=list)
    # (column, referenced table, referenced column)
    foreign_keys: list[tuple[str, str, str]] = field(default_factory=list)
    comment: str | None = None


def load_catalog(engine: Engine, schema: str | None = None) -> list[Table]:
    insp = sa.inspect(engine)
    tables = []
    for name in sorted(insp.get_table_names(schema=schema)):
        columns = [
            Column(c["name"], str(c["type"]), c.get("nullable", True), c.get("comment"))
            for c in insp.get_columns(name, schema=schema)
        ]
        pk = insp.get_pk_constraint(name, schema=schema).get("constrained_columns") or []
        fks = [
            (col, fk["referred_table"], ref)
            for fk in insp.get_foreign_keys(name, schema=schema)
            for col, ref in zip(fk["constrained_columns"], fk["referred_columns"], strict=True)
        ]
        try:
            comment = insp.get_table_comment(name, schema=schema).get("text")
        except NotImplementedError:  # SQLite has no table comments
            comment = None
        tables.append(Table(name, columns, list(pk), fks, comment))
    return tables


_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    words = set(_WORD.findall(text.lower().replace("_", " ")))
    # rough plural folding so "customer" matches "customers" and "branches" matches "branch"
    words |= {w[:-1] for w in words if w.endswith("s") and len(w) > 3}
    words |= {w[:-2] for w in words if w.endswith("es") and len(w) > 4}
    return words


def pick_tables(question: str, catalog: list[Table], limit: int = 6) -> list[Table]:
    """Choose the tables worth showing the model for this question.

    Small schemas are sent whole. Larger ones are ranked by how many question words show up
    in table names (weighted higher), column names, and comments; then the tables those
    reference through foreign keys are added so the model can write the joins.
    """
    if len(catalog) <= limit:
        return catalog

    q = _words(question)

    def score(t: Table) -> int:
        s = 3 * len(q & _words(t.name))
        s += sum(len(q & _words(c.name)) for c in t.columns)
        s += len(q & _words(t.comment or ""))
        return s

    scores = {t.name: score(t) for t in catalog}
    ranked = sorted(catalog, key=lambda t: scores[t.name], reverse=True)
    chosen = [t for t in ranked if scores[t.name] > 0][:limit] or ranked[:limit]

    by_name = {t.name: t for t in catalog}
    picked = {t.name for t in chosen}
    for t in list(chosen):
        for _, ref_table, _ in t.foreign_keys:
            if ref_table in by_name and ref_table not in picked:
                chosen.append(by_name[ref_table])
                picked.add(ref_table)
    return chosen


def render(tables: list[Table]) -> str:
    """Compact, DDL-like text the model can read: one block per table with keys and comments."""
    blocks = []
    for t in tables:
        lines = [f"TABLE {t.name}" + (f"  -- {t.comment}" if t.comment else "")]
        fk_by_col = {col: f"{rt}.{rc}" for col, rt, rc in t.foreign_keys}
        for c in t.columns:
            parts = [f"  {c.name} {c.type}"]
            if c.name in t.primary_key:
                parts.append("PRIMARY KEY")
            if c.name in fk_by_col:
                parts.append(f"REFERENCES {fk_by_col[c.name]}")
            if not c.nullable and c.name not in t.primary_key:
                parts.append("NOT NULL")
            line = " ".join(parts)
            if c.comment:
                line += f"  -- {c.comment}"
            lines.append(line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
