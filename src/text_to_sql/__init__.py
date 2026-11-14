"""Text-to-SQL agent: plain-English questions in, read-only SQL and an answer out."""

from .agent import TextToSQLAgent
from .sql_guard import GuardResult, check_sql

__all__ = ["TextToSQLAgent", "GuardResult", "check_sql"]
__version__ = "0.1.0"
