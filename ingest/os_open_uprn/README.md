# OS Open UPRN

One row per Unique Property Reference Number across Great Britain — a
coordinate anchor for every addressable location that the Ordnance
Survey has ever assigned a UPRN to (~40M rows).

No addresses, no postcodes — OS Open UPRN is deliberately geometry-only.
It's the bridge between "UPRN in someone's database" and "point on a map"
that used to require a paid AddressBase subscription.

## Source

- **Product page:** https://www.ordnancesurvey.co.uk/products/os-open-uprn
- **API endpoint:** `https://api.os.uk/downloads/v1/products/OpenUPRN/downloads`
- **Format loaded:** CSV (GB, quarterly refresh, ~600 MB zipped, ~1.5 GB uncompressed)
- **Licence:** Open Government Licence v3.0

The API auto-serves the latest release; re-running `download.sh` picks
up new quarters without edits.

## Attribution

Any tool surfacing OS Open UPRN data must include:

> Contains OS data © Crown copyright and database right [year]. OS Open
> UPRN is licensed under the Open Government Licence v3.0.

## Schema

```
staging.os_open_uprn
  uprn       bigint PRIMARY KEY
  easting    double precision           -- OSGB36 / EPSG:27700
  northing   double precision
  lat        double precision           -- WGS84 / EPSG:4326
  lon        double precision
  geom_osgb  geometry(POINT, 27700)     -- generated, indexed with GIST
```
