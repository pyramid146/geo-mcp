# Natural England Designated Sites

Eight statutory designation types unified into one lookup table:

| Type | Count (GB, 2026-Q2) | Meaning |
|---|---|---|
| SSSI | 4,128 | Sites of Special Scientific Interest (biological / geological) |
| SAC  | 250 | Special Areas of Conservation (EU Habitats Directive) |
| SPA  | 250 | Special Protection Areas (EU Birds Directive) |
| Ramsar | 1,291 | Wetlands of international importance |
| NNR  | 224 | National Nature Reserves |
| LNR  | 1,722 | Local Nature Reserves |
| AONB | 34 | Areas of Outstanding Natural Beauty / National Landscapes |
| AncientWoodland | 53,638 | Continuously wooded since ≥ 1600 |

## Source

Natural England's ArcGIS Feature Services, paged via their public
REST endpoint. Each layer is downloaded as GeoJSON (EPSG:4326),
then ogr2ogr re-projects to EPSG:27700 and unions all sources into
a single canonical table with `(designation_type, name, code, geom_osgb)`.

- **Host**: `services.arcgis.com/JJzESW51TqeY9uat`
- **Refresh cadence**: NE updates on a rolling cycle; re-running
  `download.sh` + `load.sh` every few months is enough.
- **Licence**: Open Government Licence v3.0
- **Coverage**: England. Scotland, Wales and NI have equivalent
  designations published by NatureScot / Natural Resources Wales /
  DAERA — not in this dataset.

## Attribution

> Contains Natural England data © Natural England, licensed under
> the Open Government Licence v3.0.

## Schema

```
staging.ne_designated_sites
  id                bigserial PK
  designation_type  text NOT NULL
  name              text
  code              text
  geom_osgb         geometry(MULTIPOLYGON, 27700)
```

GIST on `geom_osgb`; B-tree on `designation_type`.
