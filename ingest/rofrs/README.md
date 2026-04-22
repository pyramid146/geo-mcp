# RoFRS — Risk of Flooding from Rivers and Sea (postcode-level)

## What it is

The Environment Agency's probabilistic flood-risk assessment for England,
**taking account of the presence and condition of flood defences** — as
opposed to `EA Flood Map for Planning` (our other flood source) which
ignores defences.

This is the dataset the EA surfaces to the public through the
*Check Your Long Term Flood Risk* service on gov.uk. It's also the
dataset UK insurers use to price flood risk — a single postcode gets a
likelihood category in one of four bands:

- **High** — ≥3.3% annual chance
- **Medium** — 1-3.3%
- **Low** — 0.1-1%
- **Very Low** — <0.1%

## What this ingest loads

The full RoFRS product is a 2 m raster grid. It's gated behind EA's
"Approval for Access" process (AfA379) and not trivially downloadable.

Instead we load the companion product **"RoFRS — Postcodes in Areas
at Risk"**: a single CSV at postcode grain that pre-joins the raster
cells to UK postcodes and counts properties in each (category ×
property type) bucket. This is what real insurance / conveyancing
workflows actually consume, so no spatial data is needed for MVP.

## Source

- **Metadata page:** https://www.data.gov.uk/dataset/…/risk-of-flooding-from-rivers-and-sea-postcodes-in-areas-at-risk2
- **Defra landing page:** https://environment.data.gov.uk/dataset/96ab4342-82c1-4095-87f1-0082e8d84ef1
- **Size:** 4.7 MB zipped / 17 MB uncompressed CSV
- **Row count:** ~269k (after dropping anonymised rows: ~230k usable)
- **Update cadence:** roughly annual
- **Licence:** Open Government Licence v3.0

## Licence & attribution

```
© Environment Agency copyright and/or database right 2025. All rights reserved.
Some features are based on digital spatial data from the Centre for Ecology & Hydrology, © NERC.
Licensed under the Open Government Licence v3.0.
```

## Usage

```bash
./download.sh                # fetch + unzip (CKAN API auto-resolves current release)
./load.sh                    # strip BOM, drop anonymised rows, COPY into staging
psql -h 127.0.0.1 -U mcp_readonly -d geo -f verify.sql
```

## Schema

`staging.rofrs_postcodes` (positional schema from the EA CSV):

| column | meaning |
|---|---|
| `pcds` | postcode (PK, spaced form like `SW1A 1AA`) |
| `cntpc` | total properties in the postcode |
| `res_cntpc` / `nrp_cntpc` / `unc_cntpc` | residential / non-residential / unclassified |
| `res_cnt_<band>` / `nrp_cnt_<band>` / `unc_cnt_<band>` / `tot_cnt_<band>` | property counts in each of the four bands: `verylow`, `low`, `medium`, `high` |
| `sortoff`, `district`, `sector`, `unit` | the EA's split of the postcode text |

## Anonymisation

The source CSV contains rows like `NE70 7P*` — the unit letter masked
with `*`. EA does this when disclosing exact counts at a full postcode
could identify individual properties. Those rows always carry zeros
in the risk columns, so `load.sh` drops them — they add no information
and would break the primary-key / join assumption.

## Tool integration

- **`flood_risk_probability_uk(postcode)`** — dedicated postcode lookup
  returning the worst populated category and per-band property counts.
  Complements the point-in-polygon `flood_risk_uk`.
- **`flood_risk_summary_uk(area)`** — area-level aggregation gains a
  `probability` block alongside the existing `by_zone` counts. The join
  is postcode-keyed on both sides so adding it is cheap.
