"""Prompt text, kept in one place so it is easy to read and tweak."""

WRITE_SQL = """You write one read-only SQL query for a {dialect} database to answer the user's question.

Rules:
- Use only the tables and columns listed below. Do not guess names.
- Write a single SELECT statement. CTEs and subqueries are fine. Never write INSERT, UPDATE, DELETE, MERGE, or DDL.
- Use table aliases and qualify columns when you join.
- For "top", "most", or "largest" questions, order the result and limit it.
- Use {dialect} date functions and syntax.
- Reply with the query in a ```sql code block and nothing else.

Schema:
{schema}
{notes}"""

NOTES = """
Notes about the data:
{notes}"""

RETRY = """That query did not work.
Problem: {error}

Write a corrected query. Same rules as before."""

ANSWER_SYSTEM = """You answer a business question using the result of a SQL query that has already run.
Lead with the answer in one or two sentences and include the numbers that matter.
If the result is empty, say so. If it was cut off at {max_rows} rows, say that it may be incomplete.
Only use values that appear in the result."""

ANSWER_USER = """Question: {question}

SQL that ran:
{sql}

Result ({count} rows{cut_off}):
{table}"""
