#!/usr/bin/env bash
# Fetch the latest OS Open UPRN (CSV / GB) from the OS Data Hub Downloads
# API. Idempotent — if the local zip matches the API-reported md5,
# re-runs are a no-op.
#
# OS Open UPRN is refreshed quarterly. The download API auto-serves the
# latest release, so this script never needs updating for a new release.
set -euo pipefail

readonly PRODUCT="OpenUPRN"
readonly FORMAT="CSV"
readonly AREA="GB"
readonly LIST_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads"
readonly DOWNLOAD_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/os_open_uprn"
readonly ZIP_PATH="${DEST_DIR}/osopenuprn.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

manifest=$(curl -sSL --max-time 30 "$LIST_URL")
expected_md5=$(echo "$manifest" | python3 -c "import json, sys; v = [d for d in json.load(sys.stdin) if d.get('format') == '$FORMAT' and d.get('area') == '$AREA'][0]; print(v['md5'])")
expected_size=$(echo "$manifest" | python3 -c "import json, sys; v = [d for d in json.load(sys.stdin) if d.get('format') == '$FORMAT' and d.get('area') == '$AREA'][0]; print(v['size'])")
echo "[download] OS API reports: md5=${expected_md5}, size=${expected_size}"

if [[ -f "$ZIP_PATH" ]]; then
    local_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$local_md5" == "$expected_md5" ]]; then
        echo "[download] OS Open UPRN already present and md5 matches. Skipping."
    else
        echo "[download] Local md5 (${local_md5}) != API md5. Re-fetching."
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
    actual_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$actual_md5" != "$expected_md5" ]]; then
        echo "[download] ERROR: md5 mismatch after download (got ${actual_md5}, expected ${expected_md5})" >&2
        exit 1
    fi
fi

# Find the CSV inside the zip without extracting yet — we want to know the
# inner filename so the load script can point at it directly.
inner_csv=$(unzip -l "$ZIP_PATH" | awk '/osopenuprn_[0-9]+\.csv/ {print $NF; exit}')
if [[ -z "$inner_csv" ]]; then
    echo "[download] ERROR: no osopenuprn_YYYYMM.csv inside zip" >&2
    exit 1
fi

if [[ ! -f "${EXTRACT_DIR}/${inner_csv}" ]]; then
    echo "[download] Extracting ${inner_csv} to ${EXTRACT_DIR}"
    mkdir -p "$EXTRACT_DIR"
    unzip -o -j "$ZIP_PATH" "${inner_csv}" -d "$EXTRACT_DIR"
fi
# OS's zip leaves the inner CSV mode 000 — force readable so postgres can COPY it.
chmod 644 "${EXTRACT_DIR}/${inner_csv}"

echo "[download] CSV at: ${EXTRACT_DIR}/${inner_csv}"
wc -l "${EXTRACT_DIR}/${inner_csv}" || true
