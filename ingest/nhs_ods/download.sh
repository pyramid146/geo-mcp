#!/usr/bin/env bash
# Fetch NHS ODS GP-practices CSV via the NHS public search-and-export
# API. The files.digital.nhs.uk mirror 403s requests from most clients;
# odsdatasearchandexport.nhs.uk serves the same data publicly.
set -euo pipefail
readonly DEST_DIR="/data/ingest/nhs_ods"
mkdir -p "$DEST_DIR"

for report in epraccur ebranchs; do
    url="https://www.odsdatasearchandexport.nhs.uk/api/getReport?report=${report}"
    out="${DEST_DIR}/${report}.csv"
    echo "[download] ${report}"
    curl --fail --location --silent --show-error \
         -A "Mozilla/5.0" \
         -o "${out}.part" "$url"
    mv "${out}.part" "$out"
    wc -l "$out"
done
