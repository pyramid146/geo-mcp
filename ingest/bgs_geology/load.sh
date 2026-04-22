#!/usr/bin/env bash
# Load the four BGS Geology 625k themes into staging tables.
# Bedrock + superficial are the two that power the geology_uk tool;
# dykes + faults are loaded as reference layers for future use.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly BASE="/data/ingest/bgs_geology/extracted/BGS_Geology_625k_Shapefile"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

load_shp() {
    local shp_path="$1" table_name="$2"; shift 2
    local select_cols="$1"
    if [[ ! -f "$shp_path" ]]; then
        echo "[load] ERROR: missing shapefile: $shp_path" >&2
        exit 1
    fi
    echo "[load] $shp_path → staging.${table_name}"
    psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
        "DROP TABLE IF EXISTS staging.${table_name} CASCADE;"
    ogr2ogr \
        -f PostgreSQL \
        "PG:${PG_CONN}" \
        "$shp_path" \
        -nln "staging.${table_name}" \
        -nlt PROMOTE_TO_MULTI \
        -select "$select_cols" \
        -lco GEOMETRY_NAME=geom \
        -lco SCHEMA=staging \
        -lco LAUNDER=YES \
        -lco SPATIAL_INDEX=GIST \
        -lco PRECISION=NO \
        -t_srs EPSG:27700 \
        -a_srs EPSG:27700 \
        --config PG_USE_COPY YES
}

load_shp "${BASE}/Bedrock/625k_V5_BEDROCK_Geology_Polygons.shp" \
         bgs_bedrock \
         "LEX,LEX_D,RCS,RCS_D,GP_EQ_D,FM_EQ_D,MAX_TIME_D,MIN_TIME_D,MAX_TIME_Y,MIN_TIME_Y,BGSTYPE"

load_shp "${BASE}/Superficial/UK_625k_SUPERFICIAL_Geology_Polygons.shp" \
         bgs_superficial \
         "LEX,LEX_D,RCS_D,SUPGP_EQ_D,MAX_AGE,MIN_AGE,MAX_AGE_NO,MIN_AGE_NO"

load_shp "${BASE}/Bedrock/625k_V5_DYKES_Geology_Polygons.shp" \
         bgs_dykes \
         "LEX,LEX_D,RCS_D"

load_shp "${BASE}/Bedrock/625k_V5_FAULT_Geology_Lines.shp" \
         bgs_faults \
         "CATEGORY,FEATURE,FEATURE_D,FLTNAME_C,FLTNAME_D"

echo "[load] ANALYZE"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
ANALYZE staging.bgs_bedrock;
ANALYZE staging.bgs_superficial;
ANALYZE staging.bgs_dykes;
ANALYZE staging.bgs_faults;
SQL

echo "[load] Done."
