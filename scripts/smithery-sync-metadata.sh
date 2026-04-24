#!/usr/bin/env bash
# Push the Smithery listing metadata (display name, description,
# icon, homepage) via the registry API — the CLI's ``publish``
# command doesn't expose these fields, and the UI's publish-deprecated
# /setup flow can't reach an API-key auth server.
#
# Prerequisites: ``smithery auth login`` has been run.
# Usage:         ./scripts/smithery-sync-metadata.sh
#
# The description here MUST be kept in sync with
# .github/LISTING_COPY.md's "Short description (≤ 280 chars)".
# The homepage and icon URL point at geomcp.dev — update if the
# public hostname moves.
set -euo pipefail

SMITHERY_NAMESPACE="${SMITHERY_NAMESPACE:-cairo-pyramids}"
SMITHERY_SERVER="${SMITHERY_SERVER:-geo-mcp}"
REGISTRY="https://registry.smithery.ai"

TOKEN=$(smithery auth whoami --full 2>&1 | awk -F= '/SMITHERY_API_KEY/ {print $2}')
if [[ -z "$TOKEN" ]]; then
    echo "Could not extract token from 'smithery auth whoami --full'." >&2
    echo "Run 'smithery auth login' first." >&2
    exit 1
fi

read -r -d '' DESCRIPTION <<'EOF' || true
UK-specialist MCP server that lets an LLM agent answer location-grounded questions it otherwise cant — floods, property, heritage, environmental designations, geology, crime, schools, healthcare, elevation, geocoding. Built on current UK open-data sources rather than the model training corpus.

33 tools covering:

• Flood: EA Flood Map (planning zones 1/2/3), RoFRS risk band, surface water (WMS), historic events, NPPF sequential/exception test trigger, Flood Re eligibility, composite verdict
• Property: UPRN resolver + OS Zoomstack building footprint, HMLR INSPIRE title polygon (24M+ freehold titles), EPC certificate, HMLR price-paid history, one-call property due-diligence report
• Heritage + environment: Historic England listed buildings, scheduled monuments, registered parks/gardens; Natural England SSSI/SAC/SPA/Ramsar/NNR/LNR/AONB/Ancient Woodland; OS Open Greenspace
• Community: Police.uk street-level crime with trend, DfE GIAS schools + Ofsted ratings, NHS ODS GP practices, IMD 2019 deprivation decile
• Ground: BGS Geology 625k bedrock/superficial, GeoIndex borehole logs, Coal Authority planning-risk verdict
• Geometry: OS OpenNames + ONSPD geocoding, OS Terrain 50 elevation, OS Open Rivers/Roads proximity, distance + CRS projection

Hosted at geomcp.dev. Free tier via email signup (no card). OGLv3 data with per-response attribution. MIT-licensed code.
EOF

PAYLOAD=$(jq -nc \
    --arg displayName "geo-mcp" \
    --arg description "$DESCRIPTION" \
    --arg iconUrl "https://geomcp.dev/favicon.svg" \
    --arg homepage "https://geomcp.dev" \
    '{displayName: $displayName,
      description: $description,
      iconUrl: $iconUrl,
      homepage: $homepage}')

echo "PATCH $REGISTRY/servers/$SMITHERY_NAMESPACE/$SMITHERY_SERVER"
echo "$PAYLOAD" | jq .

STATUS=$(curl -sS -o /tmp/smithery-metadata.json -w "%{http_code}" \
    -X PATCH "$REGISTRY/servers/$SMITHERY_NAMESPACE/$SMITHERY_SERVER" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

echo "HTTP $STATUS"
cat /tmp/smithery-metadata.json
echo
