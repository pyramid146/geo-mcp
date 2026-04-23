# OS Open Rivers

193,040 watercourse link segments across GB — rivers, canals, tidal
rivers, lakes, and other named surface water features as LineStrings.
Covers 26,245 distinct named watercourses.

## Source

- **API**: `https://api.os.uk/downloads/v1/products/OpenRivers/downloads`
- **Format loaded**: GeoPackage (GB, ~52 MB zipped). Only the
  `watercourse_link` layer is loaded; `hydro_node` stays in the
  extracted GPKG for future tools.
- **Licence**: Open Government Licence v3.0

## Attribution

> Contains OS data © Crown copyright and database right [year]. OS Open
> Rivers is licensed under the Open Government Licence v3.0.

## Schema

```
staging.os_rivers
  id                      text                           -- OS link id
  watercourse_name        text  (nullable)
  watercourse_name_alt    text  (nullable)
  form                    text   -- river / tidalRiver / canal / lake / ...
  flow_direction          text
  length                  double
  geom_osgb               geometry(MULTILINESTRING, 27700)
```

GIST on `geom_osgb`, B-tree on `watercourse_name`.
