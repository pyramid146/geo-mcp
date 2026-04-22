# EA Historic Floods — Recorded Flood Outlines

## What it is

The Environment Agency's per-event record of actual floods in England
since **1946**. Each polygon is one recorded flood outline with the
event name, start / end dates, source (main river / sea / drainage /
sewer / …) and cause (channel capacity exceeded, defence overtopped,
etc.).

We deliberately use this product rather than the related *Historic
Flood Map* (which is the binary composite of all recorded outlines
with no event metadata) because the per-event detail is what makes
this genuinely useful for property-risk reporting.

## Source

- **CKAN slug:** `recorded-flood-outlines1`
- **Landing page:** https://environment.data.gov.uk/dataset/…
- **GeoPackage zip:** ~80 MB
- **Feature count:** ~31,750 polygon records
- **CRS:** EPSG:27700 (OSGB36 / British National Grid)
- **Licence:** Open Government Licence v3.0
- **Update cadence:** roughly quarterly

## Licence & attribution

```
© Environment Agency copyright and/or database right 2026. Licensed under the Open Government Licence v3.0.
```

## Usage

```bash
./download.sh                # fetch + unzip via CKAN-resolved URL
./load.sh                    # ogr2ogr gpkg → staging.ea_historic_floods
psql -h 127.0.0.1 -U mcp_readonly -d geo -f verify.sql
```

## Schema

`staging.ea_historic_floods` (subset of the source columns we actually
need for the tool layer):

| column | notes |
|---|---|
| `ogc_fid` | synthetic PK |
| `name` | event name, e.g. "Tewkesbury July 2007" |
| `start_date`, `end_date` | event window (nullable for poorly-documented events) |
| `flood_src` | `main river`, `sea`, `ordinary watercourse`, `sewer`, `drainage`, `unknown`, … |
| `flood_caus` | free-text cause, e.g. "channel capacity exceeded (no raised defences)" |
| `fluvial_f`, `coastal_f`, `tidal_f` | source-type flags (yes/no) |
| `geom` | `MULTIPOLYGON`, SRID 27700, GIST-indexed |

Indexes on `start_date` and `flood_src` support chronological and
source-filtered queries.

## Tool design notes

For `historic_floods_uk(lat, lon)`:

1. Reproject lat/lon → EPSG:27700 once.
2. `ST_Covers(flood.geom, pt)` against the spatial index.
3. Return `{count, earliest, most_recent, sources, events[]}` with
   up to N (say 10) most-recent events listed explicitly. Caps keep
   response size predictable when a point happens to sit inside many
   overlapping flood outlines (Severn / Thames valleys).

Complements the other flood tools:
- `flood_risk_uk` — planning grade, ignores defences
- `flood_risk_probability_uk` — insurance grade, accounts for defences
- `historic_floods_uk` — *has it actually happened here*
