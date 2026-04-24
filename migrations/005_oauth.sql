-- Phase 5a.3: OAuth 2.1 authorization-code + PKCE flow.
-- Motivation: MCP hosting platforms (Smithery, and any others adopting
-- the MCP authorization spec) require remote MCP servers to expose
-- OAuth 2.1 discovery + authorization endpoints for their publish /
-- catalogue validation. Our direct-use clients keep working via
-- static API keys (``Authorization: Bearer <key>`` / ``X-API-Key``);
-- OAuth is layered ON TOP so the same API-key machinery (rate-limit,
-- usage-log, revoke) applies to tokens minted through OAuth.
--
-- Design:
--   1. Dynamic client registration (RFC 7591) — public clients only,
--      no client_secret. MCP spec treats hosting platforms as public
--      clients and relies on PKCE S256 for security.
--   2. Authorization codes are short-lived (10 min), single-use, tied
--      to a PKCE challenge + a concrete ``meta.api_keys`` row.
--   3. When the client calls /oauth/token with a valid code + verifier,
--      we mint a NEW api_keys row labelled ``oauth:<client_name>`` and
--      return its plaintext as the access_token. No parallel token
--      table: access tokens ARE API keys, which keeps the auth layer
--      single-purpose and lets users revoke platform access (e.g.
--      disconnect from Smithery) via the same revoke flow as any key.

-- Clients that have called /oauth/register. Accept-any policy: we
-- don't gate registration, so this is effectively an audit log of
-- "who has tried to authorize against us".
CREATE TABLE IF NOT EXISTS meta.oauth_clients (
    id              text         PRIMARY KEY,  -- random opaque client_id
    name            text,                      -- client_name from DCR metadata
    redirect_uris   text[]       NOT NULL,     -- allowed redirect_uris
    created_at      timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS oauth_clients_created_at_idx
    ON meta.oauth_clients (created_at);

-- Short-lived authorization codes issued by /oauth/authorize and
-- redeemed at /oauth/token. Single-use (``used_at``) so a leaked code
-- can't be replayed.
CREATE TABLE IF NOT EXISTS meta.oauth_auth_codes (
    code                    text         PRIMARY KEY,
    client_id               text         NOT NULL REFERENCES meta.oauth_clients(id) ON DELETE CASCADE,
    -- The api_key row the user authenticated with at /oauth/authorize.
    -- We mint a NEW key at /oauth/token; this column is just the "who
    -- granted access" breadcrumb for logs + audit.
    granter_api_key_id      uuid         NOT NULL REFERENCES meta.api_keys(id),
    customer_id             uuid         NOT NULL REFERENCES meta.customers(id),
    -- PKCE (RFC 7636). S256 only — no plain.
    code_challenge          text         NOT NULL,
    code_challenge_method   text         NOT NULL CHECK (code_challenge_method = 'S256'),
    redirect_uri            text         NOT NULL,
    scope                   text,
    expires_at              timestamptz  NOT NULL,
    used_at                 timestamptz
);
CREATE INDEX IF NOT EXISTS oauth_auth_codes_expires_at_idx
    ON meta.oauth_auth_codes (expires_at);

-- Same pattern as the rest of meta.* — mcp_ingest owns the tables,
-- the app (connecting as mcp_readonly — name is legacy, it's the
-- write role for meta.*) needs CRUD on both; the admin role
-- (mcp_admin) gets full privileges for the test-cleanup fixture
-- and any manual ops.
GRANT INSERT, SELECT, UPDATE, DELETE ON meta.oauth_clients    TO mcp_readonly;
GRANT INSERT, SELECT, UPDATE, DELETE ON meta.oauth_auth_codes TO mcp_readonly;
GRANT ALL PRIVILEGES                  ON meta.oauth_clients    TO mcp_admin;
GRANT ALL PRIVILEGES                  ON meta.oauth_auth_codes TO mcp_admin;
