#!/usr/bin/env bash
# Load Natural England's statutory designated sites (plus Ancient
# Woodland) into a unified staging.ne_designated_sites table.
#
# Each source GeoJSON has slightly different attribute field names
# (NAME / SAC_NAME / SPA_NAME, REF_CODE / CODE / SAC_CODE / SPA_CODE),
# so we load each into a per-source tmp table, then union-project
# into a canonical shape: (designation_type, name, code, geom_osgb).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DATA_DIR="/data/ingest/ne_designated_sites"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

psql() { command psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

load_geojson() {
    local in_path="$1"
    local tmp_table="$2"
    if [[ ! -f "$in_path" ]]; then
        echo "[load] SKIP $in_path (missing)"; return
    fi
    echo "[load] $in_path → staging.${tmp_table}"
    psql -c "DROP TABLE IF EXISTS staging.${tmp_table} CASCADE;"
    ogr2ogr \
        -f PostgreSQL \
        "PG:${PG_CONN}" \
        "$in_path" \
        -nln "staging.${tmp_table}" \
        -nlt PROMOTE_TO_MULTI \
        -lco GEOMETRY_NAME=geom_osgb \
        -lco SCHEMA=staging \
        -lco LAUNDER=YES \
        -lco SPATIAL_INDEX=NONE \
        -lco PRECISION=NO \
        -s_srs EPSG:4326 \
        -t_srs EPSG:27700 \
        --config PG_USE_COPY YES
}

load_geojson "$DATA_DIR/sssi.geojson"             ne_tmp_sssi
load_geojson "$DATA_DIR/aonb.geojson"             ne_tmp_aonb
load_geojson "$DATA_DIR/sac.geojson"              ne_tmp_sac
load_geojson "$DATA_DIR/spa.geojson"              ne_tmp_spa
load_geojson "$DATA_DIR/ramsar.geojson"           ne_tmp_ramsar
load_geojson "$DATA_DIR/nnr.geojson"              ne_tmp_nnr
load_geojson "$DATA_DIR/lnr.geojson"              ne_tmp_lnr
load_geojson "$DATA_DIR/ancient_woodland.geojson" ne_tmp_aw

echo "[load] building canonical staging.ne_designated_sites"
psql <<'SQL'
DROP TABLE IF EXISTS staging.ne_designated_sites CASCADE;
CREATE TABLE staging.ne_designated_sites (
    id               bigserial PRIMARY KEY,
    designation_type text NOT NULL,     -- SSSI | AONB | SAC | SPA | Ramsar | NNR | LNR | AncientWoodland
    name             text,
    code             text,
    geom_osgb        geometry(MULTIPOLYGON, 27700) NOT NULL
);

INSERT INTO staging.ne_designated_sites (designation_type, name, code, geom_osgb)
SELECT 'SSSI',             name, ref_code, geom_osgb FROM staging.ne_tmp_sssi
UNION ALL
SELECT 'AONB',             name, code,     geom_osgb FROM staging.ne_tmp_aonb
UNION ALL
SELECT 'SAC',              sac_name, sac_code, geom_osgb FROM staging.ne_tmp_sac
UNION ALL
SELECT 'SPA',              spa_name, spa_code, geom_osgb FROM staging.ne_tmp_spa
UNION ALL
SELECT 'Ramsar',           name, code,     geom_osgb FROM staging.ne_tmp_ramsar
UNION ALL
SELECT 'NNR',              name, ref_code, geom_osgb FROM staging.ne_tmp_nnr
UNION ALL
SELECT 'LNR',              name, ref_code, geom_osgb FROM staging.ne_tmp_lnr
UNION ALL
SELECT 'AncientWoodland',  name, themname, geom_osgb FROM staging.ne_tmp_aw;

DROP TABLE staging.ne_tmp_sssi, staging.ne_tmp_aonb, staging.ne_tmp_sac,
           staging.ne_tmp_spa, staging.ne_tmp_ramsar, staging.ne_tmp_nnr,
           staging.ne_tmp_lnr, staging.ne_tmp_aw;

CREATE INDEX ne_designated_sites_geom_idx
    ON staging.ne_designated_sites USING GIST (geom_osgb);
CREATE INDEX ne_designated_sites_type_idx
    ON staging.ne_designated_sites (designation_type);

ANALYZE staging.ne_designated_sites;
SQL

echo "[load] Done."
