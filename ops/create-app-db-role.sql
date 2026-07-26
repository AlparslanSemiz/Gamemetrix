\set ON_ERROR_STOP on

-- Required psql variables:
--   admin_user, app_user, app_password, database_name
-- Invoke this file without putting passwords on the command line; pass them
-- through the environment and psql variables in a protected deployment shell.

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'app_user',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'app_user',
    :'app_password'
)
\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'database_name', :'app_user')
\gexec

SELECT format('ALTER SCHEMA public OWNER TO %I', :'app_user')
\gexec

SELECT format('ALTER TABLE %I.%I OWNER TO %I', schemaname, tablename, :'app_user')
FROM pg_tables
WHERE schemaname = 'public'
\gexec

SELECT format('ALTER SEQUENCE %I.%I OWNER TO %I', sequence_schema, sequence_name, :'app_user')
FROM information_schema.sequences
WHERE sequence_schema = 'public'
\gexec

SELECT format(
    'ALTER FUNCTION %I.%I(%s) OWNER TO %I',
    namespace.nspname,
    procedure.proname,
    pg_get_function_identity_arguments(procedure.oid),
    :'app_user'
)
FROM pg_proc AS procedure
JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
WHERE namespace.nspname = 'public'
\gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', :'database_name', :'app_user')
\gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'app_user')
\gexec
SELECT format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO %I', :'app_user')
\gexec
SELECT format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_user')
\gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO %I', :'app_user')
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT ALL ON TABLES TO %I',
    :'app_user',
    :'app_user'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT ALL ON SEQUENCES TO %I',
    :'app_user',
    :'app_user'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO %I',
    :'app_user',
    :'app_user'
)
\gexec

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname = :'app_user';
