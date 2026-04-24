#!/usr/bin/env bash
# Load HMLR INSPIRE Index Polygon GML zips into
# staging.hmlr_inspire_polygons. Expects zip files already placed in
# /data/ingest/hmlr_inspire/raw/ — see README.md for the manual
# download step.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly RAW_DIR="/data/ingest/hmlr_inspire/raw"
readonly EXTRACT_DIR="/data/ingest/hmlr_inspire/extracted"

set -a; source "${REPO_ROOT}/.env"; set +a
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=127.0.0.1 port=5432 dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

# HMLR's GML files carry an xsi:schemaLocation pointing at their
# internal ETL server (hh-etl-d01.lnx.lr.net:8080), which is
# unreachable from the public internet. Fast-fail those HTTP calls
# (default was 134 s per file × 318 files = several hours wasted).
export GDAL_HTTP_CONNECTTIMEOUT=2
export GDAL_HTTP_TIMEOUT=3

psql() { command psql -h 127.0.0.1 -p 5432 -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

if [[ ! -d "$RAW_DIR" ]] || [[ -z "$(ls -1 "$RAW_DIR"/*.zip 2>/dev/null | head -1)" ]]; then
    cat >&2 <<EOF
[load] No zips found in $RAW_DIR.
       See ingest/hmlr_inspire/README.md for the HMLR manual
       registration + download step.
EOF
    exit 1
fi

mkdir -p "$EXTRACT_DIR"

echo "[load] extracting zips"
for z in "$RAW_DIR"/*.zip; do
    la_code=$(basename "$z" .zip)
    tgt="${EXTRACT_DIR}/${la_code}"
    mkdir -p "$tgt"
    if [[ -z "$(find "$tgt" -name '*.gml' -print -quit)" ]]; then
        unzip -q -o "$z" -d "$tgt"
    fi
done

echo "[load] (re)creating staging.hmlr_inspire_polygons"
psql -c "DROP TABLE IF EXISTS staging.hmlr_inspire_polygons CASCADE;"

first=1
for gml in "$EXTRACT_DIR"/*/*.gml; do
    [[ -f "$gml" ]] || continue
    la_code=$(basename "$(dirname "$gml")")
    if [[ $first -eq 1 ]]; then
        echo "[load] $gml → create"
        ogr2ogr -f PostgreSQL "PG:${PG_CONN}" "$gml" \
            -nln staging._hmlr_raw -nlt PROMOTE_TO_MULTI \
            -lco GEOMETRY_NAME=geom_osgb -lco SCHEMA=staging \
            -lco LAUNDER=YES -lco SPATIAL_INDEX=NONE -lco PRECISION=NO \
            -a_srs EPSG:27700 -t_srs EPSG:27700 \
            --config PG_USE_COPY YES \
            -sql "SELECT INSPIREID, gml_id, '$la_code' AS la_code, VALIDFROM FROM PREDEFINED"
        first=0
    else
        ogr2ogr -f PostgreSQL "PG:${PG_CONN}" "$gml" \
            -nln staging._hmlr_raw -append \
            --config PG_USE_COPY YES \
            -sql "SELECT INSPIREID, gml_id, '$la_code' AS la_code, VALIDFROM FROM PREDEFINED"
    fi
done

psql <<'SQL'
CREATE TABLE staging.hmlr_inspire_polygons AS
SELECT DISTINCT ON (inspireid)
       inspireid::bigint AS inspire_id,
       gml_id,
       la_code,
       CASE
         WHEN validfrom ~ '^\d{4}-\d{2}-\d{2}'
           THEN to_date(substring(validfrom, 1, 10), 'YYYY-MM-DD')
         ELSE NULL
       END AS update_date,
       geom_osgb
  FROM staging._hmlr_raw
 ORDER BY inspireid, validfrom DESC NULLS LAST;

DROP TABLE staging._hmlr_raw;

ALTER TABLE staging.hmlr_inspire_polygons ADD PRIMARY KEY (inspire_id);
CREATE INDEX hmlr_inspire_geom_idx ON staging.hmlr_inspire_polygons USING GIST (geom_osgb);
ANALYZE staging.hmlr_inspire_polygons;
SQL

echo "[load] Done."
