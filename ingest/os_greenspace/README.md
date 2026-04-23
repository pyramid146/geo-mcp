# OS Open Greenspace

165,587 public greenspace polygons across Great Britain.

## Source

- **API endpoint**: `https://api.os.uk/downloads/v1/products/OpenGreenspace/downloads`
- **Format loaded**: GeoPackage (GB, ~57 MB zipped)
- **Licence**: Open Government Licence v3.0

Only the `greenspace_site` layer is loaded; the per-site `access_point`
layer stays in the extracted GPKG for future tools.

## Attribution

> Contains OS data © Crown copyright and database right [year]. OS Open
> Greenspace is licensed under the Open Government Licence v3.0.

## Schema

```
staging.os_greenspace
  id                 text                   -- stable OS site id
  function           text                   -- one of 10 categories
  distinctive_name_1 text                   -- primary name (nullable)
  distinctive_name_2..4 text                -- name alternates
  geom_osgb          geometry(MULTIPOLYGON, 27700)
  area_sqm           double precision       -- generated
```

GIST on `geom_osgb`, B-tree on `function`.
