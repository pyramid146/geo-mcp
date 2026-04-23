# English Indices of Deprivation 2019

One row per LSOA (2011 boundaries) with IMD rank + decile for every
Lower-layer Super Output Area in England.

## Source

- **Portal**: https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019
- **File**: File 1 (Index of Multiple Deprivation) XLSX, converted to CSV
- **Licence**: Open Government Licence v3.0
- **Update cadence**: MHCLG publish every ~5 years; IoD 2019 is the
  current release. IoD 2025 expected in 2026/27.

## Attribution

> Contains English Indices of Deprivation 2019 data © Crown copyright
> 2019, licensed under the Open Government Licence v3.0.

## Schema

```
staging.imd_2019
  lsoa11_code  text PRIMARY KEY  -- e.g. E01000001
  lsoa11_name  text
  lad19_code   text
  lad19_name   text
  imd_rank     integer           -- 1 = most deprived of 32,844
  imd_decile   integer           -- 1 = most deprived 10%, 10 = least deprived 10%
```
