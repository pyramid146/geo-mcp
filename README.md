# geo-mcp

A **UK geospatial MCP server** for LLM agents. 33 tools covering flood risk, property records, heritage, environmental designations, greenspace, schools, healthcare, deprivation, rivers, roads, geology, crime, coal mining, elevation, and geocoding — built on UK open-data sources, returning decisions an LLM can act on rather than raw polygons.

Without this, an agent answering a UK location question falls back to whatever happens to be in its training data — often stale, often hallucinated. With it, the agent gets current, authoritative, attributable data.

🌐 **Hosted at [geomcp.dev](https://geomcp.dev)** — get a free API key at <https://geomcp.dev/signup> and point your MCP client at `https://geomcp.dev/mcp`. Running your own instance is also supported; see [DEVELOPMENT.md](./DEVELOPMENT.md).

---

## What you can ask

Once connected, an agent can answer questions it otherwise can't:

**Flood and water**
- "What's the flood risk at 12 Mill Lane, Tewkesbury GL20 5BY?"
- "Has the area around CB3 9AX ever flooded, and how recently?"
- "Is this postcode in Flood Zone 2 or 3 for planning purposes?"
- "How does surface water risk differ from river risk at this point?"
- "Would this property be eligible for Flood Re?"

**Property and title**
- "Give me a full property report for UPRN 10033544614" *(returns flood, EPC, sales, heritage, elevation in one call)*
- "Draw the building-footprint polygon for this UPRN"
- "What's the registered freehold title polygon containing this point?"
- "What have flats sold for in SW1A 1AA in the last 5 years?"
- "What's the EPC rating and construction age of this property?"

**Heritage, planning and environment**
- "Is 10 Downing Street a listed building?"
- "List scheduled monuments within 500 m of this coordinate"
- "Is this property inside an SSSI, AONB or Ancient Woodland?"
- "Can a new dwelling be built at this location under NPPF?"
- "What parks and green spaces are within 500 m?"

**Local amenity and community**
- "How many crimes in 500 m over the last year, broken down by type?"
- "What are the three nearest primary schools and their Ofsted ratings?"
- "Nearest GP practice to this postcode?"
- "What's the Index of Multiple Deprivation decile for this LSOA?"

**Ground, land and transport**
- "What's the bedrock at 51.5014, -0.1419?"
- "Are there any BGS borehole records within 1 km of this point?"
- "Is this property in a Coal Authority high-risk area?"
- "How close is this to the nearest motorway, A-road, or named river?"
- "What's the elevation profile for this postcode area?"

**Geocoding and geometry**
- "Where is SW1A 1AA?"
- "What postcode is closest to 51.5014, -0.1419, and what's the full admin hierarchy?"
- "How far is it between these two UK points, as the crow flies and projected?"
- "Convert these British National Grid coordinates to WGS84"

Every response carries its data source and licence attribution, so an agent surfacing answers can credit them correctly.

---

## Get started

1. Visit **`https://geomcp.dev/signup`** and enter your email.
2. Click the confirmation link — your API key is displayed once. Save it somewhere safe.
3. Paste it into your MCP client's config (pick whichever matches your setup):

### Claude Desktop

**Try this first: the built-in Connectors UI.** Recent Claude Desktop versions have **Settings → Connectors → Add Custom Connector** that takes a URL + Bearer header and handles everything natively. If you see that option, use it — paste `https://geomcp.dev/mcp` and your key, done.

**If your version doesn't have that UI, use the `mcp-remote` bridge** — a tiny Node.js process that speaks stdio to Claude Desktop and forwards HTTP to the server.

1. Install Node.js if you haven't (https://nodejs.org — LTS). Check with `node --version`.
2. Install the bridge (one-off, takes ~10 s):
   ```
   npm install -g mcp-remote
   ```
3. Open the config file via **File → Settings → Developer → Edit Config** (or edit directly):
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

   Add (or merge into) the `mcpServers` block. Note the command differs by OS — on Windows you must use the `.cmd` shim because Claude Desktop spawns binaries without `PATHEXT` resolution:

   **Windows**:
   ```json
   {
     "mcpServers": {
       "geo-mcp": {
         "command": "mcp-remote.cmd",
         "args": [
           "https://geomcp.dev/mcp",
           "--header",
           "Authorization: Bearer gmcp_live_..."
         ]
       }
     }
   }
   ```

   **macOS**:
   ```json
   {
     "mcpServers": {
       "geo-mcp": {
         "command": "mcp-remote",
         "args": [
           "https://geomcp.dev/mcp",
           "--header",
           "Authorization: Bearer gmcp_live_..."
         ]
       }
     }
   }
   ```
4. **Fully quit Claude Desktop** (tray icon → Quit on Windows; `Cmd+Q` on macOS — not just close the window) and relaunch. geo-mcp's tools appear in the tool picker once connected.

If Claude Desktop shows "Some MCP servers could not be loaded," open the MCP log (`%APPDATA%\Claude\Logs\mcp.log` on Windows, `~/Library/Logs/Claude/mcp.log` on macOS) for the specific error.

### Claude Code (CLI)

Register the server with the built-in `claude mcp add` command:

```bash
claude mcp add --transport http --scope user geo-mcp \
  https://geomcp.dev/mcp \
  --header "Authorization: Bearer gmcp_live_..."
```

`--scope user` makes it available in every project you run `claude` from (as opposed to just the current repo). This writes the config to the right file for your platform and avoids hand-editing JSON, which has the habit of going subtly wrong on WSL (credential-store side effects etc.).

Verify:

```bash
claude mcp list           # should list geo-mcp
claude mcp get geo-mcp    # does an actual health-check ping — errors here mean the key or URL is wrong
```

**Restart your Claude CLI session** after adding. Any `claude` process already running won't see the new server until you exit and re-launch — the MCP server list is loaded at startup.

**Note on secrets**: the Bearer token ends up stored in plaintext inside Claude's config file on disk. That's the same cleartext tradeoff every tool-config-with-an-API-key has. If you want the token out of config files entirely, the usual pattern is to wrap the server as a local stdio proxy that reads the token from an environment variable and forwards to the HTTP endpoint — out of scope for this README, but a standard MCP pattern. Otherwise just make sure the config file is only readable by you (`chmod 600`) and don't commit it anywhere.

### Codex CLI (OpenAI's `codex` command-line agent)

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.geo-mcp]
type = "http"   # some Codex versions use `transport = "http"` instead
url = "https://geomcp.dev/mcp"
headers = { Authorization = "Bearer gmcp_live_..." }
```

Codex speaks streamable-HTTP MCP natively, so no `mcp-remote` bridge is needed.

**Version note**: the key name for the transport has varied between Codex releases — older versions use `transport = "http"`, newer ones `type = "http"`. If the server doesn't get discovered, swap the key and try again. Run `codex --help` or check the current Codex docs for your release.

Verify:

```bash
codex mcp list       # should list geo-mcp
```

Restart any existing `codex` session afterwards — like Claude Code, the MCP server list is loaded at startup.

### Other MCP clients

Most MCP clients that speak streamable-HTTP accept the same three fields: `type: "http"`, `url`, and a Bearer header. Check your client's docs for where its config lives.

Free tier, rate-limited, no card required.

---

## Tools

### Flood
| Tool | Input | Returns |
|---|---|---|
| `flood_risk_uk` | lat, lon | EA Flood Map for Planning zone (1/2/3), source; returns `coverage_gap` for points outside England rather than a false Zone 1 |
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
| `property_lookup_uk` | UPRN | OS Open UPRN coords (WGS84 + OSGB) + full admin + geology for the point |
| `building_footprint_uk` | UPRN | OS Open Zoomstack building polygon (GeoJSON) + area + OSGB bbox for a UPRN |
| `title_polygon_uk` | lat, lon | HMLR INSPIRE freehold-title polygon containing the point (requires manual HMLR download — see ingest/hmlr_inspire/README.md) |
| `property_report_uk` | UPRN | one-call composite: lookup + EPC + comparable sales + flood + listed + heritage + elevation, with headline + narrative |
| `recent_sales_uk` | postcode, years | HMLR Price Paid Data — stats + up to 50 recent sales |
| `energy_performance_uk` | postcode or UPRN | EPC certificate(s); includes `flood_re_year_signal` derived from age band |
| `is_listed_building_uk` | lat, lon, tolerance_m | exact-point check against Historic England's NHLE |
| `heritage_nearby_uk` | lat, lon, radius_m | listed buildings, monuments, parks, battlefields, wrecks, WHS within radius |
| `designated_sites_nearby_uk` | lat, lon, radius_m, types? | Natural England SSSI / SAC / SPA / Ramsar / NNR / LNR / AONB / Ancient Woodland within radius |
| `green_space_nearby_uk` | lat, lon, radius_m, functions? | OS Open Greenspace — parks, play spaces, allotments, cemeteries, sports facilities |
| `schools_nearby_uk` | lat, lon, radius_m, phase? | DfE GIAS schools — phase, Ofsted rating, pupil count, postcode |
| `deprivation_uk` | postcode or lat/lon | IMD 2019 decile + rank for the resolved LSOA (England) |
| `river_nearby_uk` | lat, lon, radius_m | OS Open Rivers — nearest named watercourse + nearby named rivers (form: river / tidalRiver / canal / lake) |
| `road_nearby_uk` | lat, lon, radius_m, classes? | OS Open Roads — nearest Motorway / A / B road, per-class nearest, unique nearby roads by number + name |
| `gp_practices_nearby_uk` | lat, lon, radius_m, active_only? | NHS ODS GP practices + branches within radius |

### Ground / geotech
| Tool | Input | Returns |
|---|---|---|
| `geology_uk` | lat, lon | BGS 625k bedrock + superficial formation, age, rock type |
| `boreholes_nearby_uk` | lat, lon, radius_m | BGS GeoIndex boreholes with scan URLs |
| `coal_mining_risk_uk` | lat, lon | Coal Authority planning-risk verdict — in-coalfield flag, Development High Risk, past/current surface mining, coal resource |

### Crime
| Tool | Input | Returns |
|---|---|---|
| `crime_nearby_uk` | lat, lon, radius_m, months | police.uk street-level incidents — total + breakdown by crime type + monthly trend |

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
| Ordnance Survey | Boundary-Line, OpenNames, Terrain 50, Open UPRN, Open Zoomstack, Open Greenspace |
| Environment Agency | Flood Zones, RoFRS, RoFSW (WMS), Recorded Flood Outlines |
| Historic England | National Heritage List |
| Natural England | SSSI, SAC, SPA, Ramsar, NNR, LNR, AONB, Ancient Woodland |
| British Geological Survey | Geology 625k, GeoIndex boreholes |
| Coal Authority / Mining Remediation Authority | Planning & Policy Constraints WMS (live) |
| HM Land Registry | Price Paid Data |
| MHCLG | EPC Register |
| DfE | GIAS (Get Information About Schools) |
| Police forces (via data.police.uk) | Street-level crime incidents |

The server itself is MIT-licensed — see [LICENSE](./LICENSE).

---

## Why the tools return what they do

- **Decisions, not data.** "Flood Zone 3, rivers" beats a 500-row polygon dump. If the caller has to post-process the response, the tool is designed wrong.
- **Every response carries its attribution.** OGLv3 datasets require credit; the tools do it automatically so a user-facing surface (a report, a chat reply) can display the right line.
- **Coverage caveats are inline.** "England only", "scale 1:625k, not suitable for foundation decisions" — embedded in the response, not buried in docs a user will never read.

---

## Contributing / running your own instance

See [DEVELOPMENT.md](./DEVELOPMENT.md) for ingest scripts, environment variables, test suite, and ops notes. Not recommended for casual use — the data alone takes ~60 GB after ingest.

---

## Licence

MIT for the code. See [LICENSE](./LICENSE). Data attribution lines ship with every tool response and are non-optional.
