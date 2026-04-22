#!/usr/bin/env bash
# Load OS Boundary-Line admin-level shapefiles into PostGIS staging and
# build staging.admin_names — the (code → name) lookup table that
# reverse_geocode_uk joins onto to return friendly names alongside the
# GSS codes that come from ONSPD.
#
# Four shapefiles are loaded (polygons kept for future point-in-polygon
# tools); one supplementary — scotland_and_wales_region — is skipped
# because it carries electoral-region boundaries, not LA names.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DATA_ROOT="/data/ingest/boundary_line/extracted/Data"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

load_shp() {
    local shp_path="$1"
    local table_name="$2"

    if [[ ! -f "$shp_path" ]]; then
        echo "[load] ERROR: shapefile not found: $shp_path" >&2
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
        -select NAME,CODE,AREA_CODE,DESCRIPTIO,TYPE_CODE \
        -lco GEOMETRY_NAME=geom \
        -lco SCHEMA=staging \
        -lco LAUNDER=YES \
        -lco SPATIAL_INDEX=GIST \
        -lco PRECISION=NO \
        -t_srs EPSG:27700 \
        -a_srs EPSG:27700 \
        --config PG_USE_COPY YES
}

load_shp "${DATA_ROOT}/Supplementary_Country/country_region.shp"               bl_country
load_shp "${DATA_ROOT}/GB/english_region_region.shp"                            bl_english_region
load_shp "${DATA_ROOT}/GB/district_borough_unitary_region.shp"                  bl_lad
load_shp "${DATA_ROOT}/GB/district_borough_unitary_ward_region.shp"             bl_ward

echo "[load] Building staging.admin_names lookup"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
DROP TABLE IF EXISTS staging.admin_names CASCADE;

CREATE TABLE staging.admin_names (
    code  text PRIMARY KEY,
    name  text NOT NULL,
    level text NOT NULL  -- 'country' | 'region' | 'lad' | 'ward'
);

-- Name cleanup: strip OS's legal-style suffixes that add noise without
-- information. Region names lose " English Region"; LAD names lose
-- " London Boro", " District", and the borough designator " (B)".
INSERT INTO staging.admin_names (code, name, level)
SELECT DISTINCT ON (code) code, name, level
  FROM (
    SELECT code, name,                                                      'country' AS level FROM staging.bl_country
    UNION ALL
    SELECT code, regexp_replace(name, ' English Region$', ''),              'region'  AS level FROM staging.bl_english_region
    UNION ALL
    SELECT code,
           regexp_replace(
               regexp_replace(name, ' \(B\)$', ''),
               ' (London Boro|District)$', ''
           ),                                                                'lad'     AS level FROM staging.bl_lad
    UNION ALL
    SELECT code, name,                                                      'ward'    AS level FROM staging.bl_ward
  ) u
 ORDER BY code;

CREATE INDEX admin_names_level_idx ON staging.admin_names (level);

ANALYZE staging.admin_names;
SQL

echo "[load] Done."
