# OS OpenNames

## What it is

OS OpenNames is the Ordnance Survey's free gazetteer for Great Britain:
a flat list of ~3 million named features — populated places (cities,
towns, villages, hamlets), roads, watercourses, landforms, landcover
areas, and more. Each row carries a single centroid point (OSGB27700)
and contextual admin fields (postcode district, populated place, county
/ unitary, region, country).

## Source

- **Product page:** https://www.ordnancesurvey.co.uk/products/os-open-names
- **Downloads API:** `https://api.os.uk/downloads/v1/products/OpenNames/downloads`
- **Direct zip:** `https://api.os.uk/downloads/v1/products/OpenNames/downloads?area=GB&format=CSV&redirect`
- **Size:** ~103 MB zipped (CSV bundle), extracts to ~1.8 GB of per-100km-tile CSVs
- **Row count:** ~3.04 M features
- **CRS of GEOMETRY_X / GEOMETRY_Y:** EPSG:27700
- **Licence:** Open Government Licence v3.0

## Licence & attribution

```
Contains OS data © Crown copyright and database right 2026. Licensed under the Open Government Licence v3.0.
```

## Usage

```bash
./download.sh                # fetch + extract; md5-verified, idempotent
./load.sh                    # merge CSVs, COPY into staging.opennames, index
psql -h 127.0.0.1 -U mcp_readonly -d geo -f verify.sql
```

Rebuilds take ~2 min on this host.

## Schema

`staging.opennames` — 34 text/int columns mirroring the OS OpenNames
technical specification (positional, since the source CSVs have no
header). Added on top at load time:

- `geom` — `GEOMETRY(POINT, 27700)` GENERATED column derived from
  `geometry_x` / `geometry_y`.
- Indexes:
  - GIST on `geom`
  - B-tree on `lower(name1)` and `lower(name2)` — the hot path for
    forward geocoding
  - B-tree on `type`, `local_type`, `postcode_district`

## Tool design notes

For `geocode_uk(query)`:

1. If `query` matches a UK postcode pattern → hit `staging.onspd` by
   `pcds` or `pcd7` (normalized). Fast, unambiguous, and the same point
   the ONS considers canonical for that postcode.
2. Otherwise → exact case-insensitive match on `staging.opennames.name1`,
   filtering to `type = 'populatedPlace'` first, then broadening if no
   hits. Rank by `local_type` (City > Town > Village > Hamlet > …).
3. If multiple matches remain (e.g. "Newport" is four different places),
   return the best and the full alternatives list with admin context
   for disambiguation.

Fuzzy matching and multi-token address parsing are out of scope for
v1 — the tool returns `match_type: 'none'` for queries it can't resolve
directly. A later pass can add a pg_trgm-based similarity search or
hook in a dedicated address parser.
