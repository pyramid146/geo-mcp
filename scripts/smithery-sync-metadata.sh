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

DESCRIPTION='Hosted UK geospatial MCP server. 33 tools covering flood risk, property records (UPRN, EPC, price-paid), heritage designations, Natural England SSSI / AONB, crime (police.uk), coal mining, schools (GIAS), NHS GPs, elevation, and geocoding. OGLv3 data, free tier.'

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
