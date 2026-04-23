#!/usr/bin/env bash
# Load OS Open Roads RoadLink shapefiles (tiled per 100 km grid square)
# into staging.os_roads. Loops over every *_RoadLink.shp and appends.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly SHP_DIR="/data/ingest/os_roads/extracted/data"

set -a; source "${REPO_ROOT}/.env"; set +a
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=127.0.0.1 port=5432 dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

psql() { command psql -h 127.0.0.1 -p 5432 -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

psql -c "DROP TABLE IF EXISTS staging.os_roads CASCADE;"

first=1
for shp in "$SHP_DIR"/*_RoadLink.shp; do
    [[ -f "$shp" ]] || continue
    if [[ $first -eq 1 ]]; then
        echo "[load] $shp → staging.os_roads (create)"
        ogr2ogr -f PostgreSQL "PG:${PG_CONN}" "$shp" \
            -nln staging.os_roads -nlt PROMOTE_TO_MULTI \
            -lco GEOMETRY_NAME=geom_osgb -lco SCHEMA=staging \
            -lco LAUNDER=YES -lco SPATIAL_INDEX=GIST -lco PRECISION=NO \
            -a_srs EPSG:27700 -t_srs EPSG:27700 \
            -dim XY \
            --config PG_USE_COPY YES
        first=0
    else
        echo "[load] $shp → append"
        ogr2ogr -f PostgreSQL "PG:${PG_CONN}" "$shp" \
            -nln staging.os_roads -nlt PROMOTE_TO_MULTI \
            -append \
            -dim XY \
            --config PG_USE_COPY YES
    fi
done

psql <<'SQL'
CREATE INDEX IF NOT EXISTS os_roads_class_idx ON staging.os_roads (class);
CREATE INDEX IF NOT EXISTS os_roads_name1_idx ON staging.os_roads (name1);
ANALYZE staging.os_roads;
SQL
echo "[load] Done."
