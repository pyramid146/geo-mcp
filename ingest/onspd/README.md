# ONSPD — ONS Postcode Directory

## What it is

A list of every current and terminated UK postcode linked to administrative,
health, and other geographic areas (local authority, ward, LSOA/MSOA, country,
region, etc.), with centroid coordinates in both WGS84 (`lat`, `long`) and
OSGB (`oseast1m`, `osnrth1m`).

Gridlink-sourced, published by the Office for National Statistics.

## Current release

- **Version:** February 2026
- **Source page:** https://geoportal.statistics.gov.uk/datasets/3080229224424c9cb53c0b48f5a64d27/about
- **Direct zip:** https://www.arcgis.com/sharing/rest/content/items/3080229224424c9cb53c0b48f5a64d27/data
- **Size:** ~246 MB zipped
- **Release cadence:** quarterly (February / May / August / November)

To adopt the next release, open the Open Geography Portal, find the new ONSPD
item page, copy its item-id (the hex string in the URL), and update
`ONSPD_ITEM_ID` + `ONSPD_VERSION` at the top of `download.sh`.

## Licence & attribution

Open Government Licence v3.0. The following attribution **must** be surfaced
in any API response whose data was sourced (directly or transitively) from
ONSPD:

```
Source: Office for National Statistics licensed under the Open Government Licence v.3.0
Contains OS data © Crown copyright and database right 2026
Contains Royal Mail data © Royal Mail copyright and database right 2026
Contains GeoPlace data © Local Government Information House Limited copyright and database right 2026
```

## Usage

```bash
./download.sh               # fetch + unzip into /data/ingest/onspd/
./load.sh                   # ogr2ogr CSV → staging.onspd, build indexes
psql -h 127.0.0.1 -U mcp_readonly -d geo -f verify.sql
```

`download.sh` is idempotent — rerunning skips the fetch when the local zip
size matches remote. `load.sh` drops and recreates `staging.onspd` each run.

## Schema notes

- Source is CSV with headers; `ogr2ogr` auto-creates columns with
  `AUTODETECT_TYPE=YES`, so numeric columns (lat, long, oseast1m, osnrth1m)
  land as `DOUBLE PRECISION` / `INTEGER` rather than text.
- Geometry column `geom` is `GEOMETRY(POINT, 4326)` built from the `lat` /
  `long` columns. A GIST index is created inline by ogr2ogr.
- B-tree indexes on `pcds` (canonical spaced form, e.g. `SW1A 1AA`) and
  `pcd` (7-char form).
- Rows whose coordinates are ONSPD's "unknown" sentinel (long=0,
  lat=99.999999) have `geom` nulled out post-load — their row-level
  metadata is still queryable, spatial queries ignore them.
- Tables in `staging` are owned by `mcp_ingest`; default privileges
  auto-grant `SELECT` to `mcp_readonly`.

## Key columns (subset)

ONSPD column names are not entirely stable across releases — admin-boundary
columns carry year suffixes (e.g. `lad25cd`, `ctry25cd`) that roll forward
each release. The columns below are the ones that matter for the MVP tools.
Tools should reference columns via constants defined per release, not
hard-code the suffix.

| column     | meaning |
|------------|---------|
| `pcds`     | canonical postcode, single-space form (e.g. `SW1A 1AA`) |
| `pcd7`     | 7-char no-space form |
| `pcd8`     | 8-char fixed-width form |
| `lat`, `long` | WGS84 centroid |
| `east1m`, `north1m` | OSGB eastings / northings, metres |
| `lad25cd`  | Local Authority District (2025 boundaries) |
| `wd25cd`   | electoral ward (2025) |
| `lsoa21cd`, `msoa21cd` | Lower/Middle Super Output Area (2021 census) |
| `ctry25cd` | country code (E92000001 = England etc.) |
| `rgn25cd`  | region code (E12000007 = London etc.) |
| `dointr`   | date postcode introduced (YYYYMM) |
| `doterm`   | date postcode terminated; NULL = live |
| `geom`     | POINT, SRID 4326 |
