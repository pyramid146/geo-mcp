-- Email-bomb defence: enforce at most one active verification token
-- per email. An attacker rotating IPs through POST /signup could send
-- unlimited verification emails to a victim; this index caps that at
-- "one email per victim per 24h" (until the first token expires).

-- Step 1: clean up any pre-existing duplicates so the unique index can
-- be created. Keep only the most-recent unverified row per email.
DELETE FROM meta.pending_signups a
 USING meta.pending_signups b
 WHERE a.email = b.email
   AND a.verified_at IS NULL
   AND b.verified_at IS NULL
   AND (a.created_at < b.created_at
        OR (a.created_at = b.created_at AND a.id < b.id));

-- Step 2: partial unique index on active (unverified) tokens.
-- Verified rows stay in the table (for audit) but aren't blocked from
-- having a new signup in the future — once a row is verified the
-- next signup with the same email starts fresh.
CREATE UNIQUE INDEX IF NOT EXISTS pending_signups_email_active_uq
    ON meta.pending_signups (email)
 WHERE verified_at IS NULL;

-- Step 3: the app role (mcp_readonly — despite the name, it writes to
-- meta.*) needs DELETE on this table so start_signup() can clean up
-- verified / expired rows before retrying the insert.
GRANT DELETE ON meta.pending_signups TO mcp_readonly;
