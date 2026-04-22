# geo-mcp

A **UK-specialist geospatial MCP server** for LLM agents. One HTTP endpoint, 20 tools, returning *decisions* (flood zone, listed-building match, recent comparable sales) rather than raw polygons an agent can't use.

Built for the property-risk vertical — conveyancing, insurance, proptech — but useful anywhere a UK location question needs a structured answer.

---

## Get started

1. Visit **`https://<hosted-instance>/signup`** and enter your email.
2. Click the confirmation link — your API key is displayed once.
3. Paste it into your MCP client config. Example for Claude Code at `~/.claude/mcp_servers.json`:
   ```json
   {
     "geo-mcp": {
       "type": "http",
       "url": "https://<hosted-instance>/mcp",
       "headers": { "Authorization": "Bearer gmcp_live_..." }
     }
   }
   ```

Free tier. Rate-limited but no credit card required.

---

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

All datasets used in the default build are **Open Government Licence v3.0** — commercial reuse is fine with attribution.

| Source | Dataset |
|---|---|
| ONS | ONSPD (postcodes) |
| Ordnance Survey | Boundary-Line, OpenNames, Terrain 50 |
| Environment Agency | Flood Zones, RoFRS, RoFSW (WMS), Recorded Flood Outlines |
| Historic England | National Heritage List |
| British Geological Survey | Geology 625k, GeoIndex boreholes |
| HM Land Registry | Price Paid Data |
| MHCLG | EPC Register |

The server itself is MIT-licensed — see [LICENSE](./LICENSE).

---

## Design notes

- **Decisions, not data.** "Flood Zone 3, rivers" beats a 500-row polygon dump. If the caller has to post-process the response, the tool is designed wrong.
- **Docstrings are product copy.** They're what the LLM reads to decide whether to call the tool.
- **Errors come back as `{"error": ..., "message": ...}`**, never raised to the client.
- **Auth is in-process.** `AuthMiddleware` is authoritative for API-key validation. Transport layers (Cloudflare, reverse proxy) are TLS/DDoS only.
- **Every response carries its attribution.** OGLv3 data must be credited; the tools do it automatically.

---

## Development

Running locally is supported but non-trivial — the tools need ~60 GB of pre-ingested UK open data to work. The hosted instance exists precisely so you don't have to do this.

**Prerequisites:** Docker + docker-compose, Python 3.12, `gdal-bin`, `postgresql-client-16`, ~60 GB free disk.

```bash
git clone <repo> && cd geo-mcp
cp .env.example .env     # fill in passwords
docker compose up -d postgis
./scripts/migrate.sh

# Load the datasets you need — each has download.sh + load.sh in ingest/<name>/
./ingest/onspd/download.sh && ./ingest/onspd/load.sh
# …etc

python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q               # ~50 s, integrates against real PostGIS
python -m geo_mcp       # serves on 127.0.0.1:8000
```

Hit `GET /health` for liveness + readiness (no auth). `GET /` for the landing page, `GET /signup` to mint yourself a key without going through the admin CLI.

### Environment

| Env var | Default | Purpose |
|---|---|---|
| `POSTGRES_DB` | required | Postgres database name |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `5432` | Postgres address |
| `DB_USER` / `MCP_READONLY_PASSWORD` | `mcp_readonly` / required | App role (readonly on geospatial data, read/write on `meta`) |
| `MCP_HTTP_HOST` / `MCP_HTTP_PORT` | `127.0.0.1` / `8000` | Bind address |
| `GEO_MCP_PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Base URL used in signup emails |
| `GEO_MCP_FROM_EMAIL` | `onboarding@resend.dev` | `From:` address on signup emails |
| `RESEND_API_KEY` | unset | Resend API key — if unset, verification URLs are logged instead of emailed |

Ingest and migration scripts additionally need `MCP_ADMIN_PASSWORD` + `MCP_INGEST_PASSWORD` — see `.env.example`.

### Backups + restore drill

`scripts/systemd/geo-mcp-backup.{service,timer}` run a nightly `pg_dump` of the `meta` schema to `/data/backups`. `scripts/restore-drill.sh` restores the latest dump into a scratch DB and asserts row counts.

---

## Licence

MIT for the code. See [LICENSE](./LICENSE). Every tool response carries the specific attribution string for the data it used — treat those as non-optional.
