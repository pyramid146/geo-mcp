#!/usr/bin/env bash
# Load the GIAS all-data CSV into staging.gias_schools.
#
# GIAS ships ~200 columns; we project only the subset that drives
# property/location tools: identity (URN, name, postcode), type
# (phase, establishment type, gender), status (open/closed), capacity
# (age range, pupil count), quality signal (Ofsted rating +
# inspection date), and location (OSGB easting/northing).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly CSV_PATH="/data/ingest/gias_schools/edubasealldata.csv"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"

psql() { command psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

if [[ ! -f "$CSV_PATH" ]]; then
    echo "[load] ERROR: CSV missing — run download.sh first" >&2
    exit 1
fi

echo "[load] (re)creating tables"
psql <<'SQL'
DROP TABLE IF EXISTS staging.gias_schools CASCADE;

-- Unlogged raw loader — GIAS schema drifts slightly from refresh to
-- refresh (columns sometimes renamed/added), so load everything as
-- text, then project the columns we actually use.
CREATE UNLOGGED TABLE staging._gias_raw (
    data jsonb
);
SQL

echo "[load] streaming CSV → jsonb rows"
# Use python to convert the CSV into one-row-per-line JSON; handles
# GIAS's Latin-1 / Windows-1252 accents, embedded commas, and quoted
# multi-line values cleanly.
python3 - "$CSV_PATH" <<'PY' | psql -c "\\copy staging._gias_raw (data) FROM stdin WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b')"
import csv, json, sys

# CSV is Windows-1252 per DfE's historical encoding choice.
path = sys.argv[1]
with open(path, encoding="cp1252", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        sys.stdout.write(json.dumps(row).replace("\t", " ") + "\n")
PY

echo "[load] projecting typed columns"
psql <<'SQL'
CREATE TABLE staging.gias_schools (
    urn                bigint PRIMARY KEY,
    name               text NOT NULL,
    status             text,                  -- Open / Closed / Proposed to open / etc.
    type_of_est        text,                  -- e.g. Community school, Academy
    type_group         text,                  -- LA maintained / Academies / Independent / Free School / ...
    phase              text,                  -- Primary / Secondary / All-through / Nursery / ...
    gender             text,                  -- Mixed / Boys / Girls
    age_low            integer,
    age_high           integer,
    capacity           integer,
    pupils             integer,
    ofsted_rating      text,                  -- Outstanding / Good / ... / null
    ofsted_last_insp   date,
    postcode           text,
    town               text,
    la_name            text,
    easting            double precision,
    northing           double precision
);

INSERT INTO staging.gias_schools (
    urn, name, status, type_of_est, type_group, phase, gender,
    age_low, age_high, capacity, pupils, ofsted_rating, ofsted_last_insp,
    postcode, town, la_name, easting, northing
)
SELECT
    NULLIF(data->>'URN', '')::bigint,
    data->>'EstablishmentName',
    NULLIF(data->>'EstablishmentStatus (name)', ''),
    NULLIF(data->>'TypeOfEstablishment (name)', ''),
    NULLIF(data->>'EstablishmentTypeGroup (name)', ''),
    NULLIF(data->>'PhaseOfEducation (name)', ''),
    NULLIF(data->>'Gender (name)', ''),
    NULLIF(data->>'StatutoryLowAge', '')::integer,
    NULLIF(data->>'StatutoryHighAge', '')::integer,
    NULLIF(data->>'SchoolCapacity', '')::integer,
    NULLIF(data->>'NumberOfPupils', '')::integer,
    NULLIF(data->>'OfstedRating (name)', ''),
    CASE
      WHEN data->>'OfstedLastInsp' ~ '^\d{2}-\d{2}-\d{4}$'
        THEN to_date(data->>'OfstedLastInsp', 'DD-MM-YYYY')
      ELSE NULL
    END,
    NULLIF(data->>'Postcode', ''),
    NULLIF(data->>'Town', ''),
    NULLIF(data->>'LA (name)', ''),
    NULLIF(data->>'Easting', '')::double precision,
    NULLIF(data->>'Northing', '')::double precision
  FROM staging._gias_raw
 WHERE NULLIF(data->>'URN', '') IS NOT NULL
   AND NULLIF(data->>'EstablishmentName', '') IS NOT NULL;

DROP TABLE staging._gias_raw;

-- Only build geom where coords are present; some schools (centralised
-- admin entries, closed schools w/ lost coords) have null easting/northing.
ALTER TABLE staging.gias_schools
    ADD COLUMN geom_osgb geometry(POINT, 27700)
    GENERATED ALWAYS AS (
        CASE WHEN easting IS NOT NULL AND northing IS NOT NULL
          THEN ST_SetSRID(ST_MakePoint(easting, northing), 27700)
          ELSE NULL END
    ) STORED;

CREATE INDEX gias_schools_geom_idx ON staging.gias_schools USING GIST (geom_osgb);
CREATE INDEX gias_schools_phase_idx ON staging.gias_schools (phase);
CREATE INDEX gias_schools_status_idx ON staging.gias_schools (status);

ANALYZE staging.gias_schools;
SQL

echo "[load] Done."
