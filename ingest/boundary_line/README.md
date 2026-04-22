# OS Boundary-Line

## What it is

Vector boundaries for every administrative and electoral area in Great
Britain — countries, English regions, local authorities, wards, parishes,
Westminster and Senedd/Scottish Parliament constituencies. Names and GSS
codes attached. OGL v3.

Released twice a year (May and October). The OS Downloads API always serves
the latest release, so `download.sh` never needs updating for new releases —
just rerun it.

## Source

- **Product page:** https://docs.os.uk/os-downloads/products/areas-and-zones-portfolio/boundary-line
- **Downloads API (authoritative):** `https://api.os.uk/downloads/v1/products/BoundaryLine/downloads`
- **Direct shapefile zip:** `https://api.os.uk/downloads/v1/products/BoundaryLine/downloads?area=GB&format=ESRI%C2%AE+Shapefile&redirect`
- **Size:** ~742 MB zipped (GB shapefile format)
- **Licence:** Open Government Licence v3.0

## Licence & attribution

Any API response whose content traces back to Boundary-Line must carry:

```
Contains OS data © Crown copyright and database right 2026.
Licensed under the Open Government Licence v3.0.
```

## Usage

```bash
./download.sh                # fetch + md5 verify + unzip
./load.sh                    # ogr2ogr shapefiles → PostGIS staging, build admin_names
psql -h 127.0.0.1 -U mcp_readonly -d geo -f verify.sql
```

`download.sh` queries the OS Downloads API for the current release's md5 and
compares against the local file. Matching md5 → no re-download.

## What gets loaded

| staging table        | source                                          | rows (approx) |
|----------------------|--------------------------------------------------|---------------|
| `bl_country`         | `Supplementary_Country/country_region.shp`       | ~3 (E/S/W)    |
| `bl_english_region`  | `GB/english_region_region.shp`                   | 9             |
| `bl_lad`             | `GB/district_borough_unitary_region.shp`         | 350           |
| `bl_ward`            | `GB/district_borough_unitary_ward_region.shp`    | ~6,600        |

All geometries are EPSG:27700 polygons with a GIST index on `geom`.

Not loaded: the supplementary Scottish-Parliament / Senedd electoral-region
file (`scotland_and_wales_region.shp`), parishes, polling districts, ceremonial
counties, historic counties, the Welsh community wards, and `high_water_polyline`.
These stay on disk for future tools that want them.

## `staging.admin_names`

A denormalised lookup table built from the shapefiles above:

| column | notes                                               |
|--------|-----------------------------------------------------|
| `code` | GSS code (primary key) — matches ONSPD `*25cd` cols |
| `name` | Friendly name. Cleaned: trailing ` English Region` stripped from regions, trailing ` (B)` borough designator stripped from LAs |
| `level`| `'country'` / `'region'` / `'lad'` / `'ward'`       |

This is what `reverse_geocode_uk` joins onto to turn ONSPD's codes into names
without running a point-in-polygon query per call.
