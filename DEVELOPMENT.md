# Development / ops

Everything you'd need to run your own `geo-mcp` instance or contribute
to the project. The hosted service exists so users don't have to —
self-hosting is reasonable if you want air-gapped use, different
licence terms, or are hacking on the code.

## Prerequisites

- Docker + docker-compose
- Python 3.12
- `gdal-bin` (`ogr2ogr`, `gdal_translate`)
- `postgresql-client-16`
- ~60 GB of free disk after full ingest

## Quickstart

```bash
git clone https://github.com/pyramid146/geo-mcp.git && cd geo-mcp
cp .env.example .env     # fill in passwords; never commit .env
docker compose up -d postgis
./scripts/migrate.sh

# Load the datasets you need — each has download.sh + load.sh in ingest/<name>/.
# Nothing hard-depends between datasets except reverse_geocode (needs ONSPD +
# Boundary-Line) and flood tools (need ONSPD for postcode resolution).
./ingest/onspd/download.sh && ./ingest/onspd/load.sh
./ingest/boundary_line/download.sh && ./ingest/boundary_line/load.sh
# …etc

python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q               # ~50 s, integrates against real PostGIS
python -m geo_mcp       # serves on MCP_HTTP_HOST:MCP_HTTP_PORT (default 127.0.0.1:8000)
```

Useful HTTP endpoints while running:

- `GET /health` — liveness + readiness probe (no auth). Reports Postgres
  connectivity, tool count, and `meta` row counts.
- `GET /` — landing page.
- `GET /signup` + `POST /signup` — self-service API-key minting.

## Environment

| Env var | Default | Purpose |
|---|---|---|
| `POSTGRES_DB` | required | Postgres database name |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `5432` | Postgres address |
| `DB_USER` / `MCP_READONLY_PASSWORD` | `mcp_readonly` / required | App role (readonly on geospatial data, read/write on `meta`) |
| `MCP_HTTP_HOST` / `MCP_HTTP_PORT` | `127.0.0.1` / `8000` | Bind address |
| `GEO_MCP_PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Base URL used in signup emails |
| `GEO_MCP_FROM_EMAIL` | `onboarding@resend.dev` | `From:` address on signup emails |
| `RESEND_API_KEY` | unset | Resend API key — if unset, verification URLs are logged instead of emailed |

Ingest and migration scripts additionally need `MCP_ADMIN_PASSWORD` and
`MCP_INGEST_PASSWORD` — see `.env.example`.

## Architecture principles

- **Tool responses are structured dicts.** Never raw PostGIS geometries.
  If the agent has to post-process the response, the tool is designed wrong.
- **Errors come back as `{"error": ..., "message": ...}`**, never raised
  to the client. The MCP layer sees a successful response carrying an
  error object it can reason about.
- **Docstrings are product copy.** They're what the LLM reads to decide
  whether to call the tool. Treat them with the same care as landing-page
  copy.
- **Auth is in-process.** `AuthMiddleware` is authoritative for API-key
  validation. Transport layers (Cloudflare, reverse proxy) are TLS /
  DDoS only — never shift auth to the edge.
- **Every response carries its attribution.** OGLv3 data must be
  credited; the tools do it automatically.

## Ingest pattern

Each dataset lives under `ingest/<name>/` with:

- `download.sh` — idempotent fetch of the source into `/data/ingest/<name>/`
- `load.sh` — `ogr2ogr` / `COPY` → PostGIS `staging.<name>`
- `verify.sql` — row counts, bbox check, spatial index verify
- `README.md` — source URL, licence, attribution text

`/data/ingest/` is bulk, git-ignored. The scripts are in-repo. Monthly
cron refresh is the intended pattern for production.

## Tests

```bash
pytest -q                     # full suite
pytest -q tests/test_flood.py # single file
pytest -q -k signup           # by name
```

Tests hit the real PostGIS rather than mocking, on the principle that
mocks drift from the real schema faster than the cost of running
Postgres in Docker. The test fixtures write rows to `meta.*` tables
using `@example.test` emails (RFC 2606 reserved) — clean these up
periodically with:

```sql
BEGIN;
DELETE FROM meta.usage_log       WHERE customer_id IN (SELECT id FROM meta.customers WHERE email LIKE '%@example.test');
DELETE FROM meta.api_keys        WHERE customer_id IN (SELECT id FROM meta.customers WHERE email LIKE '%@example.test');
DELETE FROM meta.pending_signups WHERE email LIKE '%@example.test';
DELETE FROM meta.customers       WHERE email LIKE '%@example.test';
COMMIT;
```

A proper fix is a separate `geo_test` database; not yet wired.

## Ops — production bits

### systemd units

Service units live under `scripts/systemd/` (backups) and
`scripts/cloudflared/` (tunnel) with install docs in each directory's
README. Templates use `CHANGEME` placeholders for user + paths; fill
them in before `sudo cp … /etc/systemd/system/`.

### Nightly backup + restore drill

`scripts/systemd/geo-mcp-backup.{service,timer}` runs a nightly
`pg_dump` of the `meta` schema to `/data/backups/meta-YYYYMMDD-HHMMSS.sql.gz`,
keeps the latest 30, prunes the rest. If an rclone remote named `r2` (or
whatever `GEO_MCP_OFFSITE_REMOTE` points at) is configured, the backup
script also rclone-syncs the local backups dir to an S3-compatible
offsite (Cloudflare R2, Backblaze B2). Verified cheap: the `meta` dump
is <100 KB gzipped, so offsite cost is negligible.

`scripts/restore-drill.sh` restores the latest dump into a scratch
database, asserts row counts, drops the scratch. Run ad-hoc after any
schema migration; ideally also on a monthly cadence.

### Cloudflare Tunnel

`scripts/cloudflared/` has a sample tunnel config and systemd unit
for exposing the local server at a stable HTTPS hostname via
Cloudflare's outbound-tunnel product. Step-by-step install in
`scripts/cloudflared/README.md`.

Unrelated to the application itself — the MCP server knows nothing
about where its HTTP traffic is coming from.
