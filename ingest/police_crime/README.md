# Police.uk street-level crime

Monthly rolling archive of every recorded crime in England, Wales, and
Northern Ireland (Police Service of Northern Ireland also publishes via
this route). ~5–6 M incidents per year, categorised across 14 crime
types, anonymised to street-level coordinates.

## Source

- **Landing page**: https://data.police.uk
- **Archive endpoint**: `https://data.police.uk/data/archive/{latest-month}.zip`
  (302 redirects to S3). We pull the most recent zip which contains a
  rolling 36 months of data; the ingest script extracts only the last
  `GEO_MCP_CRIME_MONTHS` months (default 24) to keep disk use bounded.
- **Format**: one CSV per force per month, named `{YYYY-MM}/{force}-street.csv`
- **Licence**: Open Government Licence v3.0

Scotland is **not** covered — Police Scotland doesn't contribute to
the data.police.uk archive. Queries against Scottish points will return
zero hits; the tool surfaces this as a coverage note.

## Attribution

Any tool surfacing this data must include:

> Contains information provided by the police forces of England, Wales
> and Northern Ireland via data.police.uk, licensed under the Open
> Government Licence v3.0. Crime locations are anonymised to a
> street-level point and may not precisely represent where an incident
> occurred.

## Schema

```
staging.police_crimes
  id            bigserial PK
  crime_id      text (may be empty for early records)
  month         date (first of month)
  reported_by   text    -- force that reported
  falls_within  text    -- force whose jurisdiction
  lon, lat      WGS84
  location      text    -- anonymised street description
  lsoa_code     text
  lsoa_name     text
  crime_type    text    -- 14 categories: burglary, violence, ASB, etc.
  last_outcome  text
  context       text
  geom_osgb     geometry(POINT, 27700)  -- generated, indexed (GIST)
```

Indexes on `month`, `crime_type`, and `geom_osgb` (GIST).
