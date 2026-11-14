"""Build demo.db, a SQLite copy of the sample database, from the SQL files in db/init.

Run from the repo root:  python scripts/build_demo_db.py [path]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 03_comments.sql and 04_readonly_role.sql are Postgres-only
SQL_FILES = ["01_schema.sql", "02_seed.sql"]


def build(path: Path) -> None:
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        for name in SQL_FILES:
            conn.executescript((ROOT / "db" / "init" / name).read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo.db"
    build(target)
    print(f"built {target}")
