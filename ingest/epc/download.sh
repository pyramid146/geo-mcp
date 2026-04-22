#!/usr/bin/env bash
# Unpack EPC bulk zips dropped into <repo>/data-hand-off/ by the
# operator.
#
# Expected files (any subset — what's present gets unpacked):
#   data-hand-off/domestic-csv.zip      — England & Wales domestic EPCs
#   data-hand-off/non-domestic-csv.zip  — commercial / non-domestic EPCs
#   data-hand-off/display-csv.zip       — Display Energy Certificates
#
# Why hand-off not auto-download? The EPC service moved from
# epc.opendatacommunities.org (HTTP Basic Auth, scriptable) to
# get-energy-performance-data.communities.gov.uk (OAuth via GOV.UK One
# Login, requires a human browser consent). Treating the zip as a manual
# drop-in is less work than wiring the full OAuth flow, and matches the
# quarterly-ish refresh cadence anyway.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly HANDOFF_DIR="${REPO_ROOT}/data-hand-off"
readonly DEST_DIR="/data/ingest/epc"

mkdir -p "$DEST_DIR"

shopt -s nullglob
any=0
for kind in domestic non-domestic display; do
    zip="${HANDOFF_DIR}/${kind}-csv.zip"
    extract_dir="${DEST_DIR}/${kind}"
    if [[ ! -f "$zip" ]]; then
        echo "[download] ${kind}: no hand-off zip at ${zip}, skipping."
        continue
    fi
    any=1
    echo "[download] ${kind}: hand-off zip $(du -h "$zip" | awk '{print $1}')"

    # Match both layouts: new gov.uk service ships certificates-YYYY.csv
    # files at the archive root; the older opendatacommunities service
    # shipped per-LA folders containing a single certificates.csv.
    if [[ -d "$extract_dir" ]] && [[ -n "$(find "$extract_dir" \( -name 'certificates-*.csv' -o -name 'certificates.csv' \) -print -quit 2>/dev/null)" ]]; then
        if [[ "$zip" -nt "$extract_dir" ]]; then
            echo "[download] ${kind}: zip newer than extracted dir, re-extracting"
            rm -rf "$extract_dir"
        else
            echo "[download] ${kind}: extracted data already present, skipping."
            continue
        fi
    fi

    mkdir -p "$extract_dir"
    unzip -q -o "$zip" -d "$extract_dir"
    n=$(find "$extract_dir" \( -name 'certificates-*.csv' -o -name 'certificates.csv' \) | wc -l)
    echo "[download] ${kind}: extracted ${n} certificates CSV file(s)"
done

if [[ $any -eq 0 ]]; then
    cat >&2 <<EOM
[download] ERROR: no EPC zips found under ${HANDOFF_DIR}

To refresh: sign in at
    https://get-energy-performance-data.communities.gov.uk/
download any of domestic / non-domestic / display bulk CSVs, save as
    ${HANDOFF_DIR}/domestic-csv.zip
    ${HANDOFF_DIR}/non-domestic-csv.zip
    ${HANDOFF_DIR}/display-csv.zip
then re-run this script.
EOM
    exit 1
fi
