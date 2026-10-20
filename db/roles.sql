-- Read-only application role. Run as nlsql_admin with: -v reader_password=...
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nlsql_reader') THEN
        CREATE ROLE nlsql_reader LOGIN;
    END IF;
END
$$;
ALTER ROLE nlsql_reader WITH LOGIN PASSWORD :'reader_password';

GRANT CONNECT ON DATABASE nlsql TO nlsql_reader;
GRANT USAGE ON SCHEMA public TO nlsql_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nlsql_reader;
-- tables nlsql_admin creates later (e.g. when schema.sql is re-run) get SELECT automatically
ALTER DEFAULT PRIVILEGES FOR ROLE nlsql_admin IN SCHEMA public GRANT SELECT ON TABLES TO nlsql_reader;

ALTER ROLE nlsql_reader SET default_transaction_read_only = on;
ALTER ROLE nlsql_reader SET statement_timeout = '5s';