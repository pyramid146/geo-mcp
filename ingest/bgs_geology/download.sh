#!/usr/bin/env bash
# Fetch BGS Geology 625k (DiGMapGB-625) Shapefile bundle from BGS.
# One 16 MB zip containing four themes (Bedrock + Dykes + Fault lines,
# Superficial). Open Government Licence v3.0.
#
# The BGS site uses a WordPress Download Manager plugin that issues
# attachment URLs keyed by `wpdmdl`. The id below is the published
# GIS-line-and-polygon-data Shapefile bundle. If BGS re-publish a new
# version, update WPDMDL and re-run — the id changes each release.
set -euo pipefail

readonly WPDMDL=119623
readonly DOWNLOAD_URL="https://www.bgs.ac.uk/download/bgs-geology-625k-gis-line-and-polygon-data-shapefile-format/?wpdmdl=${WPDMDL}"

readonly DEST_DIR="/data/ingest/bgs_geology"
readonly ZIP_PATH="${DEST_DIR}/BGS_Geology_625k_Shapefile.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

if [[ -f "$ZIP_PATH" ]]; then
    echo "[download] Zip already present. Skipping (rm to force)."
else
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name 'UK_625k_SUPERFICIAL_Geology_Polygons.shp' -print -quit 2>/dev/null)" ]]; then
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

echo "[download] Shapefiles:"
find "$EXTRACT_DIR" -name '*.shp' -printf '  %p\n' | sort
