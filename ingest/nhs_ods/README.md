# NHS ODS — GP Practices + Branches

22k GP practices and registered branches across the UK, geocoded via
ONSPD postcode join.

## Source

- **Portal**: https://digital.nhs.uk/services/organisation-data-service
- **Download endpoint**: `https://www.odsdatasearchandexport.nhs.uk/api/getReport?report={epraccur|ebranchs}`
  — the `files.digital.nhs.uk` mirror returns 403 for scripted fetches;
  this search-and-export API does not.
- **Format loaded**: CSV (no header), 27 ODS columns per spec
- **Licence**: Open Government Licence v3.0

Only GP practices (epraccur) and their branches (ebranchs) are ingested.
Hospitals, dentists, pharmacies are separate ODS files not currently
loaded.

## Attribution

> Contains information from NHS Digital's Organisation Data Service
> (ODS), licensed under the Open Government Licence v3.0.

## Schema

```
staging.nhs_gp_practices
  org_code    text    -- ODS practice code, e.g. A81001
  name        text
  addr1       text
  town        text
  postcode    text
  status_code text    -- ACTIVE / INACTIVE / DORMANT / '' for branches
  open_date   date
  close_date  date
  lat, lon    double  -- from ONSPD
  geom_wgs84  geometry(POINT, 4326)
  geom_osgb   geometry(POINT, 27700)
```
