#!/usr/bin/env bash
# Push Smithery listing metadata (display name, description, icon,
# homepage) via the registry API — the CLI's ``publish`` command
# doesn't expose these fields and the UI's deprecated /setup flow
# can't reach an API-key auth server.
#
# Two listings to manage:
#   - cairo-pyramids/geo-mcp        (onshore, default)
#   - cairo-pyramids/geo-mcp-marine (marine, env: PRODUCT=marine)
#
# Prerequisites: ``smithery auth login`` has been run.
# Usage:
#   ./scripts/smithery-sync-metadata.sh                 # onshore
#   PRODUCT=marine ./scripts/smithery-sync-metadata.sh  # marine
#
# Descriptions here MUST be kept in sync with .github/LISTING_COPY.md.
set -euo pipefail

PRODUCT="${PRODUCT:-onshore}"
SMITHERY_NAMESPACE="${SMITHERY_NAMESPACE:-cairo-pyramids}"
REGISTRY="https://registry.smithery.ai"

TOKEN=$(smithery auth whoami --full 2>&1 | awk -F= '/SMITHERY_API_KEY/ {print $2}')
if [[ -z "$TOKEN" ]]; then
    echo "Could not extract token from 'smithery auth whoami --full'." >&2
    echo "Run 'smithery auth login' first." >&2
    exit 1
fi

case "$PRODUCT" in
    onshore)
        SMITHERY_SERVER="${SMITHERY_SERVER:-geo-mcp}"
        DISPLAY_NAME="geo-mcp"
        HOMEPAGE="https://geomcp.dev"
        read -r -d '' DESCRIPTION <<'EOF' || true
UK-specialist MCP server that lets an LLM agent answer location-grounded questions it otherwise can't — floods, property, heritage, environmental designations, geology, crime, schools, healthcare, elevation, geocoding. Built on current UK open-data sources rather than the model training corpus.

**33 tools covering:**

- **Flood** — EA Flood Map (planning zones 1/2/3), RoFRS risk band, surface water (WMS), historic events, NPPF sequential/exception test trigger, Flood Re eligibility, composite verdict
- **Property** — UPRN resolver + OS Zoomstack building footprint, HMLR INSPIRE title polygon (24M+ freehold titles), EPC certificate, HMLR price-paid history, one-call property due-diligence report
- **Heritage + environment** — Historic England listed buildings, scheduled monuments, registered parks/gardens; Natural England SSSI/SAC/SPA/Ramsar/NNR/LNR/AONB/Ancient Woodland; OS Open Greenspace
- **Community** — police.uk street-level crime with trend, DfE GIAS schools + Ofsted ratings, NHS ODS GP practices, IMD 2019 deprivation decile
- **Ground** — BGS Geology 625k bedrock/superficial, GeoIndex borehole logs, Coal Authority planning-risk verdict
- **Geometry** — OS OpenNames + ONSPD geocoding, OS Terrain 50 elevation, OS Open Rivers/Roads proximity, distance + CRS projection

Hosted at [geomcp.dev](https://geomcp.dev). Free tier via email signup (no card). OGLv3 data with per-response attribution. MIT-licensed code.
EOF
        ;;

    marine)
        SMITHERY_SERVER="${SMITHERY_SERVER:-geo-mcp-marine}"
        DISPLAY_NAME="geo-mcp marine"
        HOMEPAGE="https://geomcp.dev/marine"
        read -r -d '' DESCRIPTION <<'EOF' || true
UK offshore data discovery MCP server. For a given marine point or polygon, surfaces what bathymetric, geophysical, geotechnical, ecological, and licensing data exists — with direct download URLs into the open-data archive that holds it.

**6 tools covering:**

- **Bathymetry** (EMODnet WMS+WFS, CC-BY 4.0) — seabed depth at point plus the UKHO + EU surveys that contributed to the value, with SeaDataNet metadata URLs
- **UKHO ADMIRALTY archive** — ~7,000 bathymetric surveys with polygon footprints, dates, file sizes; modern multibeam at 1–2 m grid
- **Crown Estate Marine Data Exchange** — offshore-wind developer surveys (Hornsea, Dogger Bank, Triton Knoll, …) with a GIS-readiness classifier that flags shapefile / GeoTIFF / DTM bundles vs specialist seismic projects vs PDFs
- **BGS GeoIndex Offshore** — samples (boreholes, grabs, cores) with PDF logs, Folk-classified seabed sediment, 2D seismic lines with downloadable scans, hydrocarbon wells
- **NSTA Open Data** — UKCS petroleum licences, hydrocarbon fields, 2D + 3D seismic survey footprints, subsea pipelines, current CO2 storage licences (Endurance, Hewett, Acorn)

Aimed at consenting consultants, EIA writers, offshore-wind developers, cable-route engineers, and CCUS site assessors. Returns metadata + portal URLs, not raw data — the deliverable a desk-based offshore screening produces today, in seconds. Hosted at [geomcp.dev/marine](https://geomcp.dev/marine). Same free API key as the onshore product. Per-source open licences (CC-BY 4.0, OGLv3, NSTA Open User, Crown Estate Open Data) with attribution strings preserved on every response. NDR raw archive remains gated; this tool surfaces the metadata + portal URLs.
EOF
        ;;

    *)
        echo "Unknown PRODUCT=$PRODUCT (use 'onshore' or 'marine')" >&2
        exit 1
        ;;
esac

PAYLOAD=$(jq -nc \
    --arg displayName "$DISPLAY_NAME" \
    --arg description "$DESCRIPTION" \
    --arg iconUrl "https://geomcp.dev/icon.svg" \
    --arg homepage "$HOMEPAGE" \
    '{displayName: $displayName,
      description: $description,
      iconUrl: $iconUrl,
      homepage: $homepage}')

echo "PATCH ($PRODUCT) $REGISTRY/servers/$SMITHERY_NAMESPACE/$SMITHERY_SERVER"
echo "$PAYLOAD" | jq .

STATUS=$(curl -sS -o /tmp/smithery-metadata.json -w "%{http_code}" \
    -X PATCH "$REGISTRY/servers/$SMITHERY_NAMESPACE/$SMITHERY_SERVER" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

echo "HTTP $STATUS"
cat /tmp/smithery-metadata.json
echo
