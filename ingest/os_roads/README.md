# OS Open Roads

~4 M road-link segments across GB, classified by road type and named
where known.

## Source

- **API**: `https://api.os.uk/downloads/v1/products/OpenRoads/downloads`
- **Format loaded**: ESRI Shapefile (GB, ~606 MB zipped, tiled per
  100 km grid). Every `*_RoadLink.shp` tile is loaded and appended
  into a single canonical table.
- **Licence**: Open Government Licence v3.0

## Attribution

> Contains OS data © Crown copyright and database right [year]. OS Open
> Roads is licensed under the Open Government Licence v3.0.

## Schema

```
staging.os_roads
  identifier       text
  class            text    -- Motorway / A Road / B Road / Classified Unnumbered /
                           --   Unclassified / Not Classified / Unknown
  roadnumber       text    -- "M25", "A1(M)", "B6521", "" for unnumbered
  name1, name2     text    -- street names (nullable)
  formofway        text    -- Single Carriageway / Dual Carriageway / Roundabout / ...
  length           integer
  geom_osgb        geometry(MULTILINESTRING, 27700)
```

GIST on `geom_osgb`, B-tree on `class` and `name1`.
