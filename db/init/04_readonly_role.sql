-- The agent connects as this role. It can read the tables and nothing else,
-- and every transaction it opens is read-only by default.

CREATE ROLE agent_reader LOGIN PASSWORD 'agent_reader';

GRANT CONNECT ON DATABASE bank TO agent_reader;
GRANT USAGE ON SCHEMA public TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

ALTER ROLE agent_reader SET default_transaction_read_only = on;
ALTER ROLE agent_reader SET statement_timeout = '15s';
