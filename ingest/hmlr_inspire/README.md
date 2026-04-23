# HMLR INSPIRE Index Polygons

Freehold title polygons for every registered property in England and
Wales, published by HM Land Registry under INSPIRE. ~24 M polygons.

## Source & manual download step

This one requires a free HMLR account — bulk downloads cannot be
scripted without accepting the terms on each session.

1. Register at <https://use-land-property-data.service.gov.uk>
2. Accept the INSPIRE data terms
3. From <https://use-land-property-data.service.gov.uk/datasets/inspire>
   download the per-local-authority GML zip files (~400 zips, ~10 MB
   each, ~4 GB total)
4. Drop the zips into `/data/ingest/hmlr_inspire/raw/`
5. Run `./ingest/hmlr_inspire/load.sh` to unzip + ogr2ogr-load
   everything into `staging.hmlr_inspire_polygons`

## Licence

- **Licence**: HMLR INSPIRE Index Polygon Licence — a public licence
  compatible with OGLv3 for commercial reuse with attribution.
- **Refresh cadence**: HMLR publishes monthly updates; re-downloading
  quarterly is typically enough.

## Attribution

> Contains HM Land Registry INSPIRE Index Polygon data © Crown
> copyright and database right [year]. Licensed under the INSPIRE
> Index Polygons Licence (v2.0).

## Schema

```
staging.hmlr_inspire_polygons
  inspire_id   bigint PRIMARY KEY   -- HMLR-stable INSPIRE ID
  gml_id       text                  -- raw GML identifier
  la_code      text                  -- LA the zip came from (from filename)
  update_date  date                  -- when the polygon was last edited
  geom_osgb    geometry(MULTIPOLYGON, 27700)
```

GIST on `geom_osgb`, B-tree on `inspire_id`.

## Why not a ready-to-run download.sh?

The INSPIRE download page issues a session-specific CSRF token on every
click — there's no stable URL an unauthenticated fetcher can pull. If
the HMLR workflow ever opens up (some are hinting at it moving to a
bulk-download API), this script will fold cleanly into the rest of
the ingest pattern.
