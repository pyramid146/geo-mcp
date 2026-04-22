"""Shared area resolution for the _summary_uk tools.

Accepts a free-form ``area`` string and resolves it against ONSPD / Boundary-
Line / OpenNames into an ONSPD filter predicate. The four supported forms:

- **Postcode district** (``"BA14"``, ``"M2"``, ``"SW1A"``). Matches postcodes
  by their outward code (the part before the space in ``pcds``).
- **GSS local-authority code** (``"E06000054"``, ``"S12000005"``). Matches
  on ``lad25cd``.
- **Local-authority name** (``"Wiltshire"``, ``"Manchester"``). Looked up
  case-insensitively in ``staging.admin_names`` at ``level='lad'``.
- **Populated-place name** (``"Trowbridge"``, ``"Bath"``). Resolved via
  OpenNames to the place's postcode district, then treated as above.

Returned object has everything the caller needs to plug into a WHERE clause.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_POSTCODE_DISTRICT_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?$", re.IGNORECASE)
_GSS_CODE_RE = re.compile(r"^[ESWN]\d{8}$", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedArea:
    method: str                 # 'postcode_district' | 'lad_code' | 'lad_name' | 'place_name'
    resolved_to: str            # human-readable description of what we actually used
    filter_sql: str             # SQL fragment referencing $1 (one param)
    param: str                  # the single bind parameter value

    def to_meta(self, input_: str) -> dict[str, Any]:
        return {"input": input_, "method": self.method, "resolved_to": self.resolved_to}


async def resolve_area(area: str, conn) -> ResolvedArea | None:
    """Resolve an area string against ONSPD / admin_names / OpenNames.
    Returns None if no resolution path matches.

    Caller supplies an asyncpg connection (so we don't open a second
    connection per tool call).
    """
    q = area.strip()
    if not q:
        return None

    if _POSTCODE_DISTRICT_RE.match(q):
        district = q.upper()
        return ResolvedArea(
            method="postcode_district",
            resolved_to=f"postcode district {district}",
            filter_sql="split_part(pcds, ' ', 1) = $1",
            param=district,
        )

    if _GSS_CODE_RE.match(q):
        code = q.upper()
        return ResolvedArea(
            method="lad_code",
            resolved_to=f"LAD {code}",
            filter_sql="lad25cd = $1",
            param=code,
        )

    lad = await conn.fetchrow(
        """
        SELECT code, name FROM staging.admin_names
         WHERE level = 'lad' AND lower(name) = lower($1)
         LIMIT 1
        """,
        q,
    )
    if lad is not None:
        return ResolvedArea(
            method="lad_name",
            resolved_to=f"LAD {lad['code']} ({lad['name']})",
            filter_sql="lad25cd = $1",
            param=lad["code"],
        )

    place = await conn.fetchrow(
        """
        SELECT name1, local_type, postcode_district FROM staging.opennames
         WHERE lower(name1) = lower($1)
           AND type = 'populatedPlace'
           AND postcode_district IS NOT NULL
           AND postcode_district <> ''
         ORDER BY CASE local_type
                    WHEN 'City'   THEN 1
                    WHEN 'Town'   THEN 2
                    WHEN 'Village' THEN 3
                    WHEN 'Hamlet' THEN 4
                    ELSE 9
                  END
         LIMIT 1
        """,
        q,
    )
    if place is not None:
        pd = place["postcode_district"]
        return ResolvedArea(
            method="place_name",
            resolved_to=(
                f"postcode district {pd} (from {place['local_type']} \"{place['name1']}\")"
            ),
            filter_sql="split_part(pcds, ' ', 1) = $1",
            param=pd,
        )

    return None
