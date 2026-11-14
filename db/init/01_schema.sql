-- Sample retail-banking schema used by the demo database and the tests.
-- Plain SQL that runs on both Postgres and SQLite.

CREATE TABLE branches (
    branch_id    INTEGER PRIMARY KEY,
    branch_name  VARCHAR(80) NOT NULL,
    city         VARCHAR(60) NOT NULL,
    state        CHAR(2)     NOT NULL
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    first_name   VARCHAR(40)  NOT NULL,
    last_name    VARCHAR(40)  NOT NULL,
    email        VARCHAR(120),
    city         VARCHAR(60),
    state        CHAR(2),
    segment      VARCHAR(20)  NOT NULL,
    branch_id    INTEGER REFERENCES branches (branch_id),
    joined_on    DATE         NOT NULL
);

CREATE TABLE accounts (
    account_id    INTEGER PRIMARY KEY,
    customer_id   INTEGER        NOT NULL REFERENCES customers (customer_id),
    account_type  VARCHAR(20)    NOT NULL,
    status        VARCHAR(10)    NOT NULL,
    opened_on     DATE           NOT NULL,
    closed_on     DATE,
    balance       NUMERIC(12, 2) NOT NULL
);

CREATE TABLE transactions (
    transaction_id  INTEGER PRIMARY KEY,
    account_id      INTEGER        NOT NULL REFERENCES accounts (account_id),
    posted_on       DATE           NOT NULL,
    amount          NUMERIC(12, 2) NOT NULL,
    txn_type        VARCHAR(20)    NOT NULL,
    merchant        VARCHAR(80),
    category        VARCHAR(40)
);

CREATE INDEX ix_customers_branch ON customers (branch_id);
CREATE INDEX ix_accounts_customer ON accounts (customer_id);
CREATE INDEX ix_transactions_account_date ON transactions (account_id, posted_on);
