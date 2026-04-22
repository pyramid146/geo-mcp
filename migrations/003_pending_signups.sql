-- Phase 5a.2: self-service email-verified signup.
-- Caller hits POST /signup with an email; we store a sha256 of the
-- verification token here, email the token to the address, and on
-- click we look it up, verify within the TTL, and provision a key
-- via the existing auth.mint_key flow.

CREATE TABLE IF NOT EXISTS meta.pending_signups (
    id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    email        text         NOT NULL,
    -- sha256 hex of the full plaintext verification token. The plaintext
    -- only exists in the email we send.
    token_hash   text         UNIQUE NOT NULL,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    expires_at   timestamptz  NOT NULL,
    verified_at  timestamptz,
    -- For rudimentary abuse tracking. Not authoritative (a user could
    -- change networks), but useful for rate-limiting + log forensics.
    source_ip    inet
);
CREATE INDEX IF NOT EXISTS pending_signups_email_idx      ON meta.pending_signups (email);
CREATE INDEX IF NOT EXISTS pending_signups_created_at_idx ON meta.pending_signups (created_at);

GRANT INSERT, SELECT, UPDATE ON meta.pending_signups TO mcp_readonly;
