# geo-mcp

A **UK geospatial MCP server** for LLM agents. 22 tools covering flood risk, property records, heritage, geology, elevation, and geocoding — built on UK open-data sources, returning decisions an LLM can act on rather than raw polygons.

Without this, an agent answering a UK location question falls back to whatever happens to be in its training data — often stale, often hallucinated. With it, the agent gets current, authoritative, attributable data.

---

## What you can ask

Once connected, an agent can answer questions it otherwise can't:

**Flood and water**
- "What's the flood risk at 12 Mill Lane, Tewkesbury GL20 5BY?"
- "Has the area around CB3 9AX ever flooded, and how recently?"
- "Is this postcode in Flood Zone 2 or 3 for planning purposes?"
- "How does surface water risk differ from river risk at this point?"

**Property**
- "Give me a full property report for UPRN 10033544614" *(returns flood, EPC, sales, heritage, elevation in one call)*
- "What have flats sold for in SW1A 1AA in the last 5 years?"
- "What's the EPC rating and construction age of this property?"
- "Would this property be eligible for Flood Re?"

**Heritage and planning**
- "Is 10 Downing Street a listed building?"
- "List scheduled monuments within 500 m of this coordinate"
- "Can a new dwelling be built at this location under NPPF?"
- "What heritage designations affect the area around the Tower of London?"

**Ground and elevation**
- "What's the bedrock at 51.5014, -0.1419?"
- "Are there any BGS borehole records within 1 km of this point?"
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
2. Click the confirmation link — your API key is displayed once.
3. Paste it into your MCP client config. Example for Claude Code at `~/.claude/mcp_servers.json`:
   ```json
   {
     "geo-mcp": {
       "type": "http",
       "url": "https://geomcp.dev/mcp",
       "headers": { "Authorization": "Bearer gmcp_live_..." }
     }
   }
   ```

Free tier, rate-limited, no card required.

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
| `property_lookup_uk` | UPRN | OS Open UPRN coords (WGS84 + OSGB) + full admin + geology for the point |
| `property_report_uk` | UPRN | one-call composite: lookup + EPC + comparable sales + flood + listed + heritage + elevation, with headline + narrative |
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
| Ordnance Survey | Boundary-Line, OpenNames, Terrain 50, Open UPRN |
| Environment Agency | Flood Zones, RoFRS, RoFSW (WMS), Recorded Flood Outlines |
| Historic England | National Heritage List |
| British Geological Survey | Geology 625k, GeoIndex boreholes |
| HM Land Registry | Price Paid Data |
| MHCLG | EPC Register |

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
