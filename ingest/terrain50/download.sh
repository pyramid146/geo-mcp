#!/usr/bin/env bash
# Fetch OS Terrain 50 (ASCII Grid DTM) from the OS Data Hub, then build a
# Cloud-Optimised GeoTIFF covering GB at 50m resolution.
#
# OS Terrain 50 ships as a nested zip: the outer zip contains one 10km-tile
# zip per national-grid square, each of which contains the .asc grid. We
# unzip the outer zip, then loop-unzip the inner zips to flatten everything
# into a single folder of .asc files ready for gdalbuildvrt / gdal_translate.
set -euo pipefail

readonly PRODUCT="Terrain50"
readonly FORMAT="ASCII+Grid+and+GML+%28Grid%29"
readonly AREA="GB"
readonly LIST_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads"
readonly DOWNLOAD_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/terrain50"
readonly ZIP_PATH="${DEST_DIR}/terr50_gagg_gb.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"
readonly TILES_DIR="${DEST_DIR}/tiles"
readonly VRT_PATH="${DEST_DIR}/terrain50.vrt"
readonly COG_PATH="/data/cogs/terrain50.tif"

mkdir -p "$DEST_DIR" "$TILES_DIR" "$(dirname "$COG_PATH")"

manifest=$(curl -sSL --max-time 30 "$LIST_URL")
expected_md5=$(echo "$manifest" | python3 -c "
import json, sys
items = json.load(sys.stdin)
m = next(d for d in items if d.get('format','').startswith('ASCII Grid') and d.get('area')=='$AREA')
print(m['md5'])
")
echo "[download] OS API reports md5=${expected_md5}"

if [[ -f "$ZIP_PATH" ]]; then
    local_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$local_md5" == "$expected_md5" ]]; then
        echo "[download] Zip already present and md5 matches. Skipping download."
    else
        echo "[download] Local md5 != API md5 — re-fetching."
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

# Outer extract (per-tile zips)
if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name '*.zip' -print -quit 2>/dev/null)" ]]; then
    echo "[download] Extracting outer zip"
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

# Inner extract (flatten .asc into tiles/)
existing_asc=$(find "$TILES_DIR" -maxdepth 1 -name '*.asc' 2>/dev/null | wc -l)
if [[ "$existing_asc" -lt 100 ]]; then
    echo "[download] Flattening inner zips into ${TILES_DIR}"
    rm -rf "$TILES_DIR"
    mkdir -p "$TILES_DIR"
    while IFS= read -r z; do
        unzip -q -o "$z" -d "${TILES_DIR}/.tmp"
    done < <(find "$EXTRACT_DIR" -name '*.zip')
    find "${TILES_DIR}/.tmp" -name '*.asc' -exec mv -t "$TILES_DIR" {} +
    rm -rf "${TILES_DIR}/.tmp"
fi

asc_count=$(find "$TILES_DIR" -maxdepth 1 -name '*.asc' | wc -l)
echo "[download] .asc tiles: ${asc_count}"

if [[ ! -f "$VRT_PATH" ]]; then
    echo "[download] Building VRT index"
    find "$TILES_DIR" -maxdepth 1 -name '*.asc' > "${DEST_DIR}/tile_list.txt"
    # -vrtnodata makes the VRT report -9999 for gap cells (anywhere no
    # .asc tile covers). Without this the gap fills with 0, which is
    # indistinguishable from a genuine sea-level reading and makes the
    # elevation tool return "0 m" for Dublin etc. instead of
    # out_of_coverage.
    gdalbuildvrt \
        -a_srs EPSG:27700 \
        -vrtnodata -9999 \
        -input_file_list "${DEST_DIR}/tile_list.txt" \
        "$VRT_PATH"
fi

if [[ ! -f "$COG_PATH" ]]; then
    echo "[download] Converting VRT → Cloud-Optimised GeoTIFF at ${COG_PATH}"
    gdal_translate \
        -of COG \
        -co COMPRESS=DEFLATE \
        -co PREDICTOR=3 \
        -co BLOCKSIZE=512 \
        -co BIGTIFF=YES \
        -co RESAMPLING=BILINEAR \
        -a_srs EPSG:27700 \
        -a_nodata -9999 \
        "$VRT_PATH" "$COG_PATH"
fi

echo "[download] Done."
echo "  COG: ${COG_PATH}"
ls -lh "$COG_PATH"
