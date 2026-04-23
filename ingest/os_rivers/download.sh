#!/usr/bin/env bash
# Fetch OS Open Rivers (GeoPackage, GB) — every watercourse in GB as
# LineString geometry with name, watercourse type, form attributes.
set -euo pipefail

readonly PRODUCT="OpenRivers"
readonly FORMAT="GeoPackage"
readonly AREA="GB"
readonly URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/os_rivers"
readonly ZIP_PATH="${DEST_DIR}/oprvrs_gpkg.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] ${URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

gpkg_name=$(unzip -l "$ZIP_PATH" | awk '/\.gpkg$/ {print $NF; exit}')
if [[ ! -f "${EXTRACT_DIR}/$(basename "$gpkg_name")" ]]; then
    mkdir -p "$EXTRACT_DIR"
    unzip -o -j "$ZIP_PATH" "$gpkg_name" -d "$EXTRACT_DIR"
fi
chmod 644 "${EXTRACT_DIR}/"*.gpkg 2>/dev/null || true
echo "[download] GPKG at $(find "$EXTRACT_DIR" -name '*.gpkg')"
ogrinfo "$(find "$EXTRACT_DIR" -name '*.gpkg')" 2>&1 | awk '/^[0-9]+:/ {print "  " $0}'
