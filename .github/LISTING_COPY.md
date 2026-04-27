# Directory-listing submission copy for geo-mcp

Reusable text for the various MCP directory submission forms
(Smithery, PulseMCP, Glama, mcpservers.org, awesome-mcp). Keep this
roughly in sync with the README's opening paragraphs if you update it.

The geo-mcp service exposes **two MCP products** sharing one auth and
one Cloudflare tunnel:

- **Onshore** (`/mcp`) — 33 tools, decision-shaped (synthesised verdicts).
  Listing copy in this file's first half.
- **Marine** (`/marine/mcp`) — 6 tools, discovery-shaped (metadata + portal
  URLs). Listing copy in the **Marine product** section near the bottom.

Each product is published as a separate Smithery listing (and similar on
PulseMCP / Glama). The same gmcp_live_… key works on both endpoints.

---

# Onshore product

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


---

# Marine product

A separate Smithery listing aimed at the offshore industry — different
audience, different value prop (discovery + download URLs, not
synthesised verdicts), distinct distribution channels (LinkedIn,
4COffshore, RenewableUK forums; not Hacker News).

## One-liner (≤ 120 chars)

UK offshore data MCP — bathymetry, surveys, seismic, wells, CO2 storage from EMODnet, UKHO, Crown Estate, BGS, NSTA.

## Short description (≤ 280 chars)

Hosted MCP server aggregating UK offshore open-data discovery — EMODnet bathymetry, UKHO ADMIRALTY survey archive, Crown Estate Marine Data Exchange, BGS GeoIndex Offshore, NSTA petroleum + CO2 storage. Returns metadata + download URLs for consenting / EIA / cable-route screening. Free tier.

## Medium description (≤ 800 chars)

UK offshore data discovery MCP server. For a given marine point or polygon, surfaces what bathymetric, geophysical, geotechnical, ecological, and licensing data exists — with direct download URLs into the open-data archive that holds it.

6 tools cover:

- **Bathymetry** (EMODnet WMS+WFS, CC-BY 4.0) — depth at point + the UKHO/EU surveys that contributed
- **UKHO ADMIRALTY archive** — ~7,000 bathymetric surveys with polygon footprints, modern multibeam at 1–2 m grid
- **Crown Estate Marine Data Exchange** — offshore-wind developer surveys (Hornsea, Dogger Bank, Triton Knoll, …) with GIS-readiness classification
- **BGS GeoIndex Offshore** — samples, sediment (Folk classification), seismic lines, hydrocarbon wells
- **NSTA Open Data** — petroleum licences, fields, 2D + 3D seismic, pipelines, CO2 storage licences (Endurance, Hewett, Acorn)

The deliverable a desk-based offshore screening produces today, in seconds. Hosted at https://geomcp.dev/marine. Free tier, no card.

## Tags / categories

geospatial, marine, offshore, uk, ukcs, north-sea, bathymetry, seismic, hydrocarbons, wells, ccus, carbon-storage, offshore-wind, hydrography, seabed, oceanography, gis, cable-route

## Connection details (for directories that embed the config)

```json
{
  "mcpServers": {
    "geo-mcp-marine": {
      "type": "http",
      "url": "https://geomcp.dev/marine/mcp",
      "headers": { "Authorization": "Bearer YOUR_KEY_HERE" }
    }
  }
}
```

- Transport: streamable HTTP
- Auth: Bearer token (same key as the onshore product)
- Sign up (free): https://geomcp.dev/signup
- Marine landing: https://geomcp.dev/marine
- Source: https://github.com/pyramid146/geo-mcp
- Licence (code): MIT
- Licence (data): per-source — EMODnet CC-BY 4.0, BGS OGLv3, NSTA Open User Licence, Crown Estate Open Data Licence, UKHO Crown copyright (catalogue free, files require free SeaBed account). Per-response `attribution` strings carry the canonical credit text.

## What's NOT included (be honest in the listing)

- UKHO commercial chart products (AVCS, raw ENCs, AIS Density)
- The locked-down NDR raw-data archive at ndr.nstauthority.co.uk (raw SEG-Y, full well logs, mud logs) — requires Microsoft Azure AD + organisation-affiliated NDR account. The marine tools surface metadata + portal URLs so users with appropriate access can pull the files; we don't proxy gated content.

## Screenshot / hero image suggestions

- The marine landing page at geomcp.dev/marine — same brand shell, prompt cards labelled Bathymetry / ADMIRALTY archive / Crown Estate developer surveys / BGS public record / NSTA petroleum + CO2 storage / one-shot offshore brief. The Dogger Bank coordinate (53.89°N, 1.88°E) is a good demo point — every tool returns substantial output there.
