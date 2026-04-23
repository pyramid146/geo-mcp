# GIAS — Get Information About Schools (DfE)

Authoritative England-wide register of ~52k educational establishments:
LA-maintained schools, academies, free schools, independent schools,
special schools, pupil referral units, nurseries, FE colleges.

## Source

- **Portal**: https://www.get-information-schools.service.gov.uk
- **Daily CSV**: `https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{YYYYMMDD}.csv`
  (regenerated daily; `download.sh` falls back to the latest available
  within the last 10 days).
- **Format loaded**: CSV (Windows-1252, ~64 MB, ~52k rows).
- **Licence**: Open Government Licence v3.0.

GIAS requires a `User-Agent` header on the API calls; ingest sends a
minimal Mozilla UA.

## Attribution

> Contains information from the Department for Education's Get
> Information About Schools (GIAS) register, licensed under the Open
> Government Licence v3.0. Ofsted inspection outcomes © Ofsted.

## Schema

```
staging.gias_schools
  urn              bigint PK
  name             text
  status           text    -- Open / Closed / Proposed ...
  type_of_est      text    -- e.g. Community school, Academy - converter
  type_group       text    -- LA maintained / Academies / Independent / Free / ...
  phase            text    -- Primary / Secondary / All-through / Nursery / ...
  gender           text    -- Mixed / Boys / Girls
  age_low/high     int
  capacity         int
  pupils           int
  ofsted_rating    text    -- Outstanding / Good / Requires improvement / Inadequate / null
  ofsted_last_insp date
  postcode         text
  town             text
  la_name          text
  easting/northing double
  geom_osgb        geometry(POINT, 27700)  -- generated from easting/northing
```

GIST on `geom_osgb`, btree on `phase` and `status`.
