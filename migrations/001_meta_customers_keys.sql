-- Phase 5a: customers, API keys, and tool-call usage log.
-- Idempotent — safe to re-run. Lives in the `meta` schema so data/staging
-- stay purely geospatial and these service-metadata tables are separated.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS meta.customers (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email               text        UNIQUE NOT NULL,
    stripe_customer_id  text        UNIQUE,
    tier                text        NOT NULL DEFAULT 'free'
                                     CHECK (tier IN ('free','hobby','pro','team')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    notes               text
);

CREATE TABLE IF NOT EXISTS meta.api_keys (
    id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id  uuid         NOT NULL REFERENCES meta.customers(id) ON DELETE CASCADE,
    -- sha256 hex of the full plaintext key. What we index + look up on.
    key_hash     text         UNIQUE NOT NULL,
    -- First 12 chars of the plaintext key (namespace + a few chars),
    -- safe to display in UIs, search logs by, etc.
    key_prefix   text         NOT NULL,
    label        text,                                 -- user-provided name
    created_at   timestamptz  NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);
CREATE INDEX IF NOT EXISTS api_keys_customer_idx ON meta.api_keys (customer_id);
CREATE INDEX IF NOT EXISTS api_keys_prefix_idx   ON meta.api_keys (key_prefix);

-- Append-only usage log. Every authenticated tool invocation writes one row.
-- `bigserial` id because this table is expected to grow into tens of millions.
CREATE TABLE IF NOT EXISTS meta.usage_log (
    id            bigserial    PRIMARY KEY,
    api_key_id    uuid         NOT NULL REFERENCES meta.api_keys(id),
    customer_id   uuid         NOT NULL REFERENCES meta.customers(id),
    tool_name     text         NOT NULL,
    called_at     timestamptz  NOT NULL DEFAULT now(),
    duration_ms   integer      NOT NULL,
    status        text         NOT NULL CHECK (status IN ('ok','error')),
    error_code    text
);
CREATE INDEX IF NOT EXISTS usage_log_called_at_idx        ON meta.usage_log (called_at);
CREATE INDEX IF NOT EXISTS usage_log_api_key_called_idx   ON meta.usage_log (api_key_id, called_at);
CREATE INDEX IF NOT EXISTS usage_log_customer_called_idx  ON meta.usage_log (customer_id, called_at);

-- mcp_ingest owns the tables (consistent with the staging-schema pattern and
-- the default-privileges grant to mcp_readonly). The app (which connects as
-- mcp_readonly) needs INSERT + UPDATE here, which is NOT covered by the
-- schema-level grants; wire it up explicitly.
GRANT INSERT, SELECT, UPDATE ON meta.customers TO mcp_readonly;
GRANT INSERT, SELECT, UPDATE ON meta.api_keys  TO mcp_readonly;
GRANT INSERT, SELECT         ON meta.usage_log TO mcp_readonly;
GRANT USAGE, SELECT ON SEQUENCE meta.usage_log_id_seq TO mcp_readonly;
