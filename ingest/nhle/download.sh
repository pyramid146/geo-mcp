#!/usr/bin/env bash
# Fetch the Historic England National Heritage List for England (NHLE).
#
# Historic England serves the NHLE as 11 sub-layers on an ArcGIS
# FeatureServer. ogr2ogr's ArcGIS driver paginates the FeatureServer
# responses for us, so we just call it once per layer and land a
# GeoPackage per layer in /data/ingest/nhle/.
#
# Idempotent: an existing .gpkg is skipped. Delete the file (or the
# whole /data/ingest/nhle dir) to force a re-fetch.
set -euo pipefail

readonly FS="https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer"
readonly DEST_DIR="/data/ingest/nhle"
mkdir -p "$DEST_DIR"

# Layer name → FeatureServer layer id. Only the point/polygon layers we
# actually want in the tool layer.
declare -A LAYERS=(
    [listed_buildings_points]=0
    [listed_buildings_polygons]=3
    [scheduled_monuments]=6
    [parks_and_gardens]=7
    [battlefields]=8
    [protected_wreck_sites]=9
    [world_heritage_sites]=10
)

for name in "${!LAYERS[@]}"; do
    layer_id="${LAYERS[$name]}"
    out="${DEST_DIR}/${name}.gpkg"
    if [[ -f "$out" ]]; then
        echo "[download] ${name}: already present, skipping."
        continue
    fi
    echo "[download] ${name} (layer ${layer_id}) → ${out}"
    ogr2ogr \
        -f GPKG \
        "$out" \
        "${FS}/${layer_id}/query?where=1=1&outFields=*&returnGeometry=true&f=geojson" \
        -nln "$name" \
        -t_srs EPSG:27700
done

echo "[download] Layers on disk:"
for name in "${!LAYERS[@]}"; do
    out="${DEST_DIR}/${name}.gpkg"
    if [[ -f "$out" ]]; then
        count=$(ogrinfo -so "$out" "$name" 2>/dev/null | grep -oE 'Feature Count: [0-9]+' | head -1)
        size=$(du -h "$out" | awk '{print $1}')
        printf "  %-30s %-20s %s\n" "$name" "$count" "$size"
    fi
done
