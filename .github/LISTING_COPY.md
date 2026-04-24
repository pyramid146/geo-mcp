# Directory-listing submission copy for geo-mcp

Reusable text for the various MCP directory submission forms
(Smithery, PulseMCP, Glama, mcpservers.org, awesome-mcp). Keep this
roughly in sync with the README's opening paragraphs if you update it.

---

## One-liner (≤ 120 chars)

UK geospatial MCP server — 33 tools for flood, property, heritage, crime, geology, schools, elevation and more.

## Short description (≤ 280 chars)

Hosted UK geospatial MCP server. 33 tools covering flood risk, property records (UPRN, EPC, price-paid), heritage designations, Natural England SSSI / AONB, crime (police.uk), coal mining, schools (GIAS), NHS GPs, elevation, and geocoding. OGLv3 data, free tier.

## Medium description (≤ 800 chars)

A UK geospatial MCP server built on open-data sources. Lets an LLM agent answer location questions it otherwise can't — grounded in current, attributable UK open data rather than its training corpus.

33 tools cover:

- **Flood**: EA Flood Map (planning zones), RoFRS, surface water (WMS), historic events, NPPF planning, Flood Re eligibility, composite verdict
- **Property**: UPRN resolver + building footprint (OS Zoomstack), HMLR title polygon, EPC, price-paid, one-call composite report
- **Heritage + environment**: Historic England listed buildings / monuments, Natural England SSSI / SAC / SPA / Ramsar / NNR / LNR / AONB / Ancient Woodland, OS Open Greenspace
- **Community**: Police.uk street-level crime, DfE GIAS schools + Ofsted, NHS ODS GP practices, IMD 2019 deprivation
- **Ground**: BGS Geology 625k, GeoIndex boreholes, Coal Authority planning risk
- **Geometry**: geocoding (OS OpenNames + ONSPD), elevation (OS Terrain 50), rivers + roads (OS Open), distance + projection

Hosted at https://geomcp.dev. Free tier, no card.

## Tags / categories

geospatial, uk, flood, property, heritage, maps, geography, geocoding, environment, real-estate, planning, insurance, proptech, conveyancing, gis

## Connection details (for directories that embed the config)

```json
{
  "mcpServers": {
    "geo-mcp": {
      "type": "http",
      "url": "https://geomcp.dev/mcp",
      "headers": { "Authorization": "Bearer YOUR_KEY_HERE" }
    }
  }
}
```

- Transport: streamable HTTP
- Auth: Bearer token
- Sign up (free): https://geomcp.dev/signup
- Status: https://geomcp.dev/status
- Privacy: https://geomcp.dev/privacy
- Source: https://github.com/pyramid146/geo-mcp
- Licence (code): MIT
- Licence (data): OGLv3 (per-response attribution strings)

## Screenshot / hero image suggestions

- The landing page at geomcp.dev renders with the branded grid-tile mark
  and six domain cards — a full-width screenshot of that is the obvious
  choice. Light mode for directories with light UIs, dark mode for dark.
