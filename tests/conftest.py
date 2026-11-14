from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from text_to_sql.db import make_engine

ROOT = Path(__file__).resolve().parents[1]


class ScriptedLLM(BaseChatModel):
    """Chat model stand-in: returns canned replies in order and keeps every prompt it was sent."""

    replies: list[str]
    calls: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(messages)
        if len(self.calls) > len(self.replies):
            raise AssertionError(f"unexpected model call #{len(self.calls)}")
        reply = AIMessage(self.replies[len(self.calls) - 1])
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("db") / "demo.db"
    conn = sqlite3.connect(path)
    for name in ("01_schema.sql", "02_seed.sql"):
        conn.executescript((ROOT / "db" / "init" / name).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def engine(demo_db):
    eng = make_engine(f"sqlite:///{demo_db}")
    yield eng
    eng.dispose()
