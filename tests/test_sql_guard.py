import pytest

from text_to_sql.sql_guard import check_sql, extract_sql

ALLOWED = [
    "SELECT * FROM customers",
    "select c.first_name, count(*) from customers c join accounts a on a.customer_id = c.customer_id group by 1",
    "WITH spend AS (SELECT account_id, SUM(amount) AS total FROM transactions GROUP BY account_id) SELECT * FROM spend",
    "SELECT state FROM customers UNION SELECT state FROM branches",
    "SELECT account_id, amount, RANK() OVER (PARTITION BY account_id ORDER BY amount) AS r FROM transactions",
    "SELECT * FROM accounts WHERE customer_id IN (SELECT customer_id FROM customers WHERE segment = 'premier')",
    "select merchant from transactions where merchant like '%Air%'",
]

BLOCKED = [
    ("DELETE FROM accounts", "DELETE"),
    ("UPDATE accounts SET balance = 0", "UPDATE"),
    ("INSERT INTO branches VALUES (9, 'x', 'y', 'NC')", "INSERT"),
    ("DROP TABLE customers", "DROP"),
    ("TRUNCATE TABLE transactions", "TRUNCATE"),
    ("ALTER TABLE accounts ADD COLUMN note TEXT", "ALTER"),
    ("CREATE TABLE copy_of_customers AS SELECT * FROM customers", "CREATE"),
    ("MERGE INTO accounts a USING branches b ON a.account_id = b.branch_id WHEN MATCHED THEN DELETE", "MERGE"),
    ("GRANT SELECT ON customers TO PUBLIC", "GRANT"),
    ("SELECT * INTO backup FROM customers", "INTO"),
    ("SELECT * FROM accounts FOR UPDATE", "FOR UPDATE"),
    ("WITH gone AS (DELETE FROM accounts RETURNING *) SELECT * FROM gone", "DELETE"),
    ("SELECT 1; DROP TABLE customers", "exactly one statement"),
    ("SELECT 1 -- looks harmless\n; DROP TABLE customers", "exactly one statement"),
    ("SELECT pg_sleep(30)", "pg_sleep"),
    ("SELECT set_config('default_transaction_read_only', 'off', false)", "set_config"),
    ("SELECT nextval('accounts_id_seq')", "nextval"),
    ("BEGIN", "BEGIN"),
    ("SET search_path = somewhere_else", "SET"),
    ("COPY customers TO '/tmp/customers.csv'", "COPY"),
    ("VACUUM", "raw command"),
    ("", "No SQL"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_read_only_queries_pass(sql):
    result = check_sql(sql, "postgres")
    assert result.ok, result.reason


@pytest.mark.parametrize("sql,why", BLOCKED)
def test_writes_and_side_effects_are_rejected(sql, why):
    result = check_sql(sql, "postgres")
    assert not result.ok
    assert why.lower() in result.reason.lower()


def test_snowflake_system_functions_are_rejected():
    result = check_sql("SELECT SYSTEM$WAIT(10)", "snowflake")
    assert not result.ok and "system$wait" in result.reason


def test_snowflake_qualify_is_fine():
    sql = "SELECT * FROM transactions QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY posted_on DESC) = 1"
    assert check_sql(sql, "snowflake").ok


def test_unparseable_text_is_rejected():
    result = check_sql("Sorry, I can't answer that from this schema.", "postgres")
    assert not result.ok


def test_row_cap_is_added_when_missing():
    result = check_sql("SELECT * FROM transactions", "postgres", max_rows=200)
    assert result.ok and result.sql.rstrip().endswith("LIMIT 200")


def test_small_limit_is_kept():
    result = check_sql("SELECT * FROM transactions LIMIT 10", "postgres", max_rows=200)
    assert result.ok and "LIMIT 10" in result.sql and "200" not in result.sql


def test_big_limit_is_capped():
    result = check_sql("SELECT * FROM transactions LIMIT 100000", "postgres", max_rows=200)
    assert result.ok and result.sql.rstrip().endswith("LIMIT 200")


def test_union_gets_one_cap_for_the_whole_result():
    result = check_sql("SELECT state FROM customers UNION SELECT state FROM branches", "postgres", max_rows=50)
    assert result.ok and result.sql.rstrip().endswith("LIMIT 50")


def test_sql_is_pulled_out_of_a_chatty_reply():
    reply = "Here is the query:\n```sql\nSELECT COUNT(*) FROM customers;\n```\nIt counts customers."
    assert extract_sql(reply) == "SELECT COUNT(*) FROM customers"
    assert check_sql(reply, "postgres").ok
