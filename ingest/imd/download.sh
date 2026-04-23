#!/usr/bin/env bash
# Fetch the English Indices of Deprivation 2019 — File 1 (Index of
# Multiple Deprivation, by LSOA 2011).
# This is the headline IMD dataset MHCLG publishes every ~5 years.
set -euo pipefail

readonly DEST_DIR="/data/ingest/imd"
readonly URL="https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/833970/File_1_-_IMD2019_Index_of_Multiple_Deprivation.xlsx"
readonly XLSX_PATH="${DEST_DIR}/imd2019_file1.xlsx"
readonly CSV_PATH="${DEST_DIR}/imd2019.csv"

mkdir -p "$DEST_DIR"

if [[ ! -f "$XLSX_PATH" ]]; then
    echo "[download] fetching ${URL}"
    curl --fail --location --progress-bar -o "${XLSX_PATH}.part" "$URL"
    mv "${XLSX_PATH}.part" "$XLSX_PATH"
fi
echo "[download] XLSX at ${XLSX_PATH}"

echo "[download] converting to CSV"
python3 - "$XLSX_PATH" "$CSV_PATH" <<'PY'
import csv, sys
from openpyxl import load_workbook

src, dst = sys.argv[1], sys.argv[2]
wb = load_workbook(src, data_only=True)
# File 1 has a single data sheet named "IMD2019" (sheet 1).
sheet_names = wb.sheetnames
for candidate in ("IMD2019", "IoD2019 File 1", sheet_names[0]):
    if candidate in sheet_names:
        ws = wb[candidate]
        break

with open(dst, "w", newline="") as f:
    w = csv.writer(f)
    for row in ws.iter_rows(values_only=True):
        if row[0] is None:  # trailing blanks
            continue
        w.writerow(row)
print(f"wrote {dst}")
PY
wc -l "$CSV_PATH"
head -1 "$CSV_PATH"
