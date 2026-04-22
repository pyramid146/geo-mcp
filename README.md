# geo-mcp

A **UK-specialist geospatial MCP server** for LLM agents. One HTTP endpoint, 20 tools, returning *decisions* (flood zone, listed-building match, recent comparable sales) rather than raw polygons an agent can't use.

Built for the property-risk vertical — conveyancing, insurance, proptech — but useful anywhere a UK location question needs a structured answer.

---

## What it does

```
┌───────────────────────────┐   ┌─────────────────────────────────┐
│  LLM agent                │   │  geo-mcp                        │
│  (Claude Desktop, Code,   │──►│  fastmcp over streamable HTTP   │
│   CustomGPT, etc.)        │   │  API-key auth + usage logging   │
└───────────────────────────┘   └────────────┬────────────────────┘
                                             │
                           ┌─────────────────┼────────────────┐
                           ▼                 ▼                ▼
                     PostGIS 16+3.4    OS Terrain 50     Upstream APIs
                     (ONSPD, NHLE,     COG (elevation)   (BGS GeoIndex,
                      HMLR PPD, EPC,                      EA RoFSW WMS)
                      EA flood, BGS,
                      OpenNames, …)
```

## Tools

### Flood
| Tool | Input | Returns |
|---|---|---|
| `flood_risk_uk` | lat, lon | EA Flood Map for Planning zone (1/2/3), source, coverage note |
| `flood_risk_probability_uk` | postcode | RoFRS likelihood band × property type (defended-state probabilistic risk) |
| `surface_water_risk_uk` | lat, lon | RoFSW band (High/Medium/Low/Very Low) via EA WMS |
| `historic_floods_uk` | lat, lon | EA Recorded Flood Outlines since 1946 — count, most recent, by source |
| `nppf_planning_context_uk` | lat, lon, vulnerability | NPPF Table 3 compatibility, sequential/exception-test flags |
| `flood_re_eligibility_uk` | country, property_type, build_year, … | rules-based Flood Re eligibility + the rule that drove it |
| `flood_risk_summary_uk` | area (district / LAD / named place) | per-area zone breakdown + RoFRS |
| `flood_assessment_uk` | postcode or lat/lon | composite verdict + plain-English narrative across all of the above |

### Property
| Tool | Input | Returns |
|---|---|---|
| `recent_sales_uk` | postcode, years | HMLR Price Paid Data — stats + up to 50 recent sales |
| `energy_performance_uk` | postcode or UPRN | EPC certificate(s); includes `flood_re_year_signal` derived from age band |
| `is_listed_building_uk` | lat, lon, tolerance_m | exact-point check against Historic England's NHLE |
| `heritage_nearby_uk` | lat, lon, radius_m | listed buildings, monuments, parks, battlefields, wrecks, WHS within radius |

### Ground / geotech
| Tool | Input | Returns |
|---|---|---|
| `geology_uk` | lat, lon | BGS 625k bedrock + superficial formation, age, rock type |
| `boreholes_nearby_uk` | lat, lon, radius_m | BGS GeoIndex boreholes with scan URLs |

### Geocoding / geometry
| Tool | Input | Returns |
|---|---|---|
| `geocode_uk` | query | best-hit lat/lon + confidence + alternatives (postcode / place / road) |
| `reverse_geocode_uk` | lat, lon | nearest postcode + full admin hierarchy + geology block |
| `transform_coords` | x, y, from_epsg, to_epsg | transformed coords with units + datum |
| `distance_between` | lat1,lon1, lat2,lon2 | great-circle + OSGB projected + initial azimuth |
| `elevation` | lat/lon points | OS Terrain 50 sample per point |
| `elevation_summary_uk` | area | mean / min / max / p10 / p50 / p90 elevation across postcodes |

Every response includes the licence attribution for the data it used. Coverage and caveats (e.g. "England only", "dataset at 1:625k scale") are embedded in the response, not tucked in the docs.

---

## Data & licences

All datasets used in the default build are **Open Government Licence v3.0** (OGLv3) — commercial reuse is fine with attribution. The tool responses include attribution strings you can surface in your UI.

| Source | Dataset | Licence |
|---|---|---|
| ONS | ONSPD (postcodes) | OGLv3 |
| Ordnance Survey | Boundary-Line, OpenNames, Terrain 50 | OGLv3 |
| Environment Agency | Flood Zones, RoFRS, RoFSW (WMS), Recorded Flood Outlines | OGLv3 |
| Historic England | National Heritage List | OGLv3 |
| British Geological Survey | Geology 625k, GeoIndex boreholes | OGLv3 |
| HM Land Registry | Price Paid Data | OGLv3 |
| MHCLG | EPC Register | OGLv3 |

The server itself is MIT-licensed — see [LICENSE](./LICENSE).

---

## Usage

### Hosted (easiest)

A hosted instance is available for evaluation. Email **cairo.pyramids@protonmail.com** for an API key.

Add to `~/.claude/mcp_servers.json` (Claude Code) or equivalent:

```json
{
  "geo-mcp": {
    "type": "http",
    "url": "https://geo-mcp.<host>/mcp",
    "headers": { "Authorization": "Bearer gmcp_live_..." }
  }
}
```

### Self-host

Bring-your-own data. See [Self-hosting](#self-hosting) below — non-trivial (multi-GB datasets, some with OAuth hoops).

---

## Self-hosting

**Prerequisites**
- Docker + docker-compose
- ~60 GB free disk (PostGIS + ingested data)
- Python 3.12
- `gdal-bin` (`ogr2ogr`, `gdal_translate`) for the ingest scripts
- `postgresql-client-16` for admin CLI convenience

**1. Clone + env**
```bash
git clone https://github.com/<you>/geo-mcp.git
cd geo-mcp
cp .env.example .env
# Fill in passwords in .env (never commit)
```

**2. PostGIS**
```bash
docker compose up -d postgis
./scripts/migrate.sh           # applies migrations/*.sql as mcp_admin
```

**3. Load data**

Each dataset has an idempotent `download.sh` + `load.sh` pair in `ingest/<name>/`. Load only the ones your tools need — there's no hard dependency between datasets.

```bash
./ingest/onspd/download.sh && ./ingest/onspd/load.sh
./ingest/boundary_line/download.sh && ./ingest/boundary_line/load.sh
# …and so on per-dataset
```

EPC requires a GOV.UK One Login OAuth flow — the bulk CSVs get dropped into `data-hand-off/` and `ingest/epc/` takes over from there. See `ingest/epc/README.md`.

**4. Install & run**
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m geo_mcp.admin mint-key --email you@example.com --label dev
# Save the key that's printed — the server only stores its hash.
python -m geo_mcp
```

Hits `http://127.0.0.1:8000/mcp`. Liveness probe at `GET /health` bypasses auth.

**5. Optional: nightly backup drill**

`scripts/systemd/geo-mcp-backup.{service,timer}` back up the `meta` schema (customers, keys, usage log) to `/data/backups` daily. `scripts/restore-drill.sh` restores the latest into a scratch DB and asserts row counts. Adjust paths / user for your host.

---

## Config

| Env var | Default | Purpose |
|---|---|---|
| `POSTGRES_DB` | required | Postgres database name |
| `DB_HOST` | `127.0.0.1` | Postgres host |
| `DB_PORT` | `5432` | Postgres port |
| `DB_USER` | `mcp_readonly` | Role tools query as — use the readonly role. |
| `MCP_READONLY_PASSWORD` | required | Readonly-role password |
| `MCP_HTTP_HOST` | `127.0.0.1` | Bind host. Set to `0.0.0.0` to accept Tailscale / Cloudflare Tunnel. |
| `MCP_HTTP_PORT` | `8000` | Bind port |

Ingest and migration scripts additionally need `MCP_ADMIN_PASSWORD` and `MCP_INGEST_PASSWORD` — see `.env.example`.

---

## Development

```bash
pip install -e '.[dev]'
pytest -q           # full suite, ~50 s, needs local PostGIS
ruff check .
```

Most tests integrate against the running PostGIS container rather than mocking — mocks drift from the real schema, and the cost of running Postgres in Docker is trivial.

### Architecture principles

- **Tools return decisions, not data.** "Flood Zone 3, rivers" beats a 500-row polygon dump. An agent that has to post-process the response means the tool was designed wrong.
- **Docstrings are product copy.** They're what the LLM reads to decide whether to call the tool. Invest accordingly.
- **Errors come back as `{"error": ..., "message": ...}`**, never raised to the client.
- **Auth is in-process.** `AuthMiddleware` is authoritative for API-key validation. Any transport layer (Cloudflare, reverse proxy) is TLS/DDoS only — never shift auth to the edge.
- **Every response carries its attribution.** OGLv3 data must be credited; the tools do it automatically so your UI can surface it.

---

## Licence

MIT for the code. See [LICENSE](./LICENSE).

Data licences vary by dataset — every tool response carries the specific attribution string for the data it used. Treat those as non-optional.
