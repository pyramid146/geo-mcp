#!/usr/bin/env bash
# Page Natural England's ArcGIS FeatureServer layers for seven statutory
# designations + Ancient Woodland into per-dataset GeoJSON files on disk.
# Safe to re-run: each file is written fresh.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEST_DIR="/data/ingest/ne_designated_sites"
mkdir -p "$DEST_DIR"

readonly HOST="https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services"
readonly FETCH="${SCRIPT_DIR}/fetch_to_geojson.py"

# (service_path, out_filename, space-separated fields)
declare -A DATASETS=(
    [SSSI_England]="sssi.geojson NAME REF_CODE"
    [Areas_of_Outstanding_Natural_Beauty_England]="aonb.geojson NAME CODE"
    [Special_Areas_of_Conservation_England]="sac.geojson SAC_NAME SAC_CODE"
    [Special_Protection_Areas_England]="spa.geojson SPA_NAME SPA_CODE"
    [Ramsar_England]="ramsar.geojson NAME CODE"
    [National_Nature_Reserves_England]="nnr.geojson NAME REF_CODE"
    [Local_Nature_Reserves_England]="lnr.geojson NAME REF_CODE"
    [Ancient_Woodland_England]="ancient_woodland.geojson NAME THEMNAME"
)

for svc in "${!DATASETS[@]}"; do
    parts=(${DATASETS[$svc]})
    out="${parts[0]}"
    fields=("${parts[@]:1}")
    echo "[download] ${svc} → ${out}"
    python3 "$FETCH" \
        "${HOST}/${svc}/FeatureServer/0" \
        "${DEST_DIR}/${out}" \
        "${fields[@]}"
done

echo "[download] Done."
ls -lh "$DEST_DIR"/*.geojson
