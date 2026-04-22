# OS Terrain 50

## What it is

OS Open's 50m-resolution Digital Terrain Model of Great Britain. Elevation
values are metres above the OSGB36 datum. 2,858 tiles covering GB at
roughly 10km × 10km each, ~1M cells per tile.

## Source

- **Product page:** https://www.ordnancesurvey.co.uk/products/os-terrain-50
- **Downloads API:** `https://api.os.uk/downloads/v1/products/Terrain50/downloads`
- **Direct zip:** `https://api.os.uk/downloads/v1/products/Terrain50/downloads?area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect`
- **Size:** ~160 MB zipped (outer zip is nested — per-tile inner zips)
- **Licence:** Open Government Licence v3.0

## Usage

```bash
./download.sh      # fetch, unpack nested zip, build VRT, convert to COG
```

`download.sh` is idempotent at every step — it re-uses the zip (md5 check),
the extracted tiles, the VRT, and the final COG whenever they already exist.

## Output

`/data/cogs/terrain50.tif` — a single Cloud-Optimised GeoTIFF of the
full GB coverage, EPSG:27700, DEFLATE-compressed with predictor 3 and
512-pixel internal tiles. 238 MB on disk, 13 200 × 24 600 pixels.

The tool layer reads this COG directly with rasterio; random point access
only reads the relevant internal tile, not the whole file.

## Licence & attribution

Mandatory in any API response that draws on this data:

```
Contains OS data © Crown copyright and database right 2026. Licensed under the Open Government Licence v3.0.
```

## Known gap

One tile (`NR33`, ~Colonsay / Oronsay area in the Inner Hebrides) ships
with an `Int32` band while the other 2,857 tiles are `Float32`.
`gdalbuildvrt` refuses to merge heterogeneous band types and skips the
offending tile, leaving a ~10 × 10 km hole in the coverage. A point-of-
interest query there will return a `NoData` sentinel — the tool surfaces
that as `{"error": "no_elevation_at_point"}`.

If the gap becomes commercially material, preprocess the outlier tile
with `gdal_translate -ot Float32` before rebuilding the VRT.
