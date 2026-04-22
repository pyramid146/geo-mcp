#!/bin/bash
# Runs once on a fresh data directory (empty /data/postgres).
# Creates application roles, schemas, and default privileges. Passwords come
# from env vars set in docker-compose.yml; this script itself is credential-free.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE mcp_admin    WITH LOGIN PASSWORD '${MCP_ADMIN_PASSWORD}' CREATEDB CREATEROLE;
    CREATE ROLE mcp_ingest   WITH LOGIN PASSWORD '${MCP_INGEST_PASSWORD}';
    CREATE ROLE mcp_readonly WITH LOGIN PASSWORD '${MCP_READONLY_PASSWORD}';

    CREATE SCHEMA staging AUTHORIZATION mcp_admin;
    CREATE SCHEMA prod    AUTHORIZATION mcp_admin;
    CREATE SCHEMA meta    AUTHORIZATION mcp_admin;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO mcp_ingest, mcp_readonly;

    GRANT USAGE, CREATE ON SCHEMA staging TO mcp_ingest;
    GRANT USAGE          ON SCHEMA prod    TO mcp_ingest;

    -- Readonly needs USAGE on staging too, otherwise the default-privilege
    -- SELECT grants on future staging tables are unreachable. Staying
    -- SELECT-only via default privileges — no CREATE or INSERT path.
    GRANT USAGE ON SCHEMA staging, prod, meta TO mcp_readonly;

    ALTER DEFAULT PRIVILEGES FOR ROLE mcp_ingest IN SCHEMA staging
        GRANT SELECT ON TABLES    TO mcp_readonly;
    ALTER DEFAULT PRIVILEGES FOR ROLE mcp_ingest IN SCHEMA staging
        GRANT SELECT ON SEQUENCES TO mcp_readonly;
    ALTER DEFAULT PRIVILEGES FOR ROLE mcp_admin  IN SCHEMA prod
        GRANT SELECT ON TABLES    TO mcp_readonly;
    ALTER DEFAULT PRIVILEGES FOR ROLE mcp_admin  IN SCHEMA meta
        GRANT SELECT ON TABLES    TO mcp_readonly;
EOSQL
