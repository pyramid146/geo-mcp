# OS Open Zoomstack — buildings

Every building polygon in Great Britain, at property scale.

## Source

- **Product page**: https://www.ordnancesurvey.co.uk/products/os-open-zoomstack
- **API endpoint**: `https://api.os.uk/downloads/v1/products/OpenZoomstack/downloads`
- **Format loaded**: GeoPackage (GB, ~4.3 GB zipped). Only the
  `local_buildings` layer is loaded — ~15.1 M polygons, EPSG:27700.
  Other Zoomstack layers (roads, rail, woodland, etc.) remain in
  the extracted `.gpkg` for future tools without re-downloading.
- **Licence**: Open Government Licence v3.0
- **Refresh cadence**: ~biannual

Coverage is GB only; Northern Ireland uses Ordnance Survey of NI,
not the Ordnance Survey (GB), and isn't in this dataset.

## Attribution

> Contains OS data © Crown copyright and database right [year]. OS
> Open Zoomstack is licensed under the Open Government Licence v3.0.

## Schema

```
staging.os_zoomstack_buildings
  uuid       text                        -- stable OS building identifier
  geom_osgb  geometry(MULTIPOLYGON, 27700)
  area_sqm   double precision            -- generated from geom_osgb
```

GIST index on `geom_osgb`, btree on `uuid`.
