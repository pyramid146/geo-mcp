# EA Flood Map for Planning — Flood Zones

## What it is

The Environment Agency's authoritative map of river and sea flood probability
in England. Two zones are explicitly stored:

- **Flood Zone 3** — ≥1% (1 in 100) annual probability of river flooding, or
  ≥0.5% (1 in 200) annual probability of sea flooding.
- **Flood Zone 2** — 0.1%–1% (1 in 1,000 to 1 in 100) annual probability from
  rivers, or 0.1%–0.5% (1 in 1,000 to 1 in 200) from the sea, plus accepted
  past flood outlines.
- **Flood Zone 1** — implicit. Any point not in Zone 2 or 3 is Zone 1
  (<0.1% annual probability).

This is the dataset Local Planning Authorities use to determine whether a
planning application needs a Flood Risk Assessment.

## Source

- **Metadata page:** https://www.data.gov.uk/dataset/104434b0-5263-4c90-9b1e-e43b1d57c750/flood-map-for-planning-flood-zones1
- **Defra landing page:** https://environment.data.gov.uk/dataset/04532375-a198-476e-985e-0579a0a11b47
- **CKAN API (resolved by `download.sh`):** `https://ckan.publishing.service.gov.uk/api/3/action/package_show?id=flood-map-for-planning-flood-zones1`
- **Zipped GeoPackage size:** ~962 MB (extracts to ~5.7 GB)
- **Feature count:** ~3.5 M polygons (2.9 M FZ2 + 0.6 M FZ3)
- **CRS:** EPSG:27700 (OSGB36 / British National Grid)
- **Update cadence:** roughly quarterly; the CKAN API always yields the
  latest release, so `download.sh` needs no edits across refreshes.

This replaces the retired separate "Flood Zone 2" and "Flood Zone 3"
datasets (superseded April 2025).

## Licence & attribution

Open Government Licence v3.0. Mandatory attribution for any API response
whose answer was sourced from this data:

```
Contains Environment Agency data © Environment Agency copyright and/or database right 2025. Licensed under the Open Government Licence v3.0.
```

## Usage

```bash
./download.sh                # fetch + unzip; idempotent on file presence
./load.sh                    # ogr2ogr gpkg → staging.ea_flood_zones (slow)
psql -h 127.0.0.1 -U mcp_readonly -d geo -f verify.sql
```

## Schema

`staging.ea_flood_zones`

| column         | notes                                                   |
|----------------|---------------------------------------------------------|
| `ogc_fid`      | synthetic PK from ogr2ogr                               |
| `origin`       | source of the polygon (e.g. "National modelled")        |
| `flood_zone`   | `FZ2` or `FZ3`                                          |
| `flood_source` | `Rivers` / `Sea` / `Rivers and Sea`                     |
| `geom`         | `MULTIPOLYGON`, SRID 27700, GIST-indexed                |

## Tool design notes

For `flood_risk_uk(lat, lon)`:

1. Reproject the input (WGS84 → OSGB 27700) so the GIST index on `geom` is
   usable.
2. Check FZ3 coverage first (`WHERE flood_zone = 'FZ3' AND ST_Covers(geom, pt) LIMIT 1`).
3. If no FZ3 hit, check FZ2.
4. Otherwise return `zone: 1`.

`LIMIT 1` short-circuits the scan as soon as any one polygon covers the
point — typical response <100 ms.

Surface-water risk and defended-area flags are NOT in this dataset; they
come from separate EA datasets (RoFRS, Areas Benefiting from Defences)
and are deferred to a `flood_risk_uk` v2 in a later phase.
