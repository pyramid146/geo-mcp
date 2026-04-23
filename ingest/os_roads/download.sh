#!/usr/bin/env bash
# Fetch OS Open Roads (Shapefile, GB) — every road in GB with
# classification (motorway / A / B / minor), name, and form.
# Shapefile is 606 MB zipped; GeoPackage is 1 GB. Either works;
# Shapefile is smaller + more portable.
set -euo pipefail

readonly URL="https://api.os.uk/downloads/v1/products/OpenRoads/downloads?area=GB&format=ESRI%C2%AE+Shapefile&redirect"
readonly DEST_DIR="/data/ingest/os_roads"
readonly ZIP_PATH="${DEST_DIR}/oproad_essh.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"
if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] fetching"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name 'RoadLink.shp' -print -quit 2>/dev/null)" ]]; then
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi
rl=$(find "$EXTRACT_DIR" -name 'RoadLink.shp' | head -1)
echo "[download] RoadLink: $rl"
