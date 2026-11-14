"""Settings come from environment variables; a .env file in the working directory is loaded if present."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_model: str | None
    max_rows: int
    max_attempts: int
    statement_timeout_ms: int
    schema_notes: str


def load_settings() -> Settings:
    load_dotenv()
    notes_file = os.getenv("SCHEMA_NOTES_FILE")
    notes = Path(notes_file).read_text(encoding="utf-8") if notes_file else ""
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///demo.db"),
        llm_model=os.getenv("LLM_MODEL") or None,
        max_rows=int(os.getenv("MAX_ROWS", "200")),
        max_attempts=int(os.getenv("MAX_ATTEMPTS", "3")),
        statement_timeout_ms=int(os.getenv("STATEMENT_TIMEOUT_MS", "15000")),
        schema_notes=notes,
    )
