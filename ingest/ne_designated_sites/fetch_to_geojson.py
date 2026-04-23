#!/usr/bin/env python3
"""Page a Natural England ArcGIS FeatureServer layer into a single
GeoJSON file.

Usage: fetch_to_geojson.py <FeatureServer URL (layer 0)> <out.geojson> [fields...]

FeatureServers cap responses at maxRecordCount (typically 2000), so
we loop on resultOffset until the server signals there are no more.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request


def fetch_all(layer_url: str, out_path: str, fields: list[str]) -> None:
    base = layer_url.rstrip("/")
    out_fields = ",".join(fields) if fields else "*"
    # 1000 is below most ArcGIS FeatureServer maxRecordCount caps
    # (typically 1000 or 2000). Asking for 2000 risked silent truncation
    # to 1000 on SSSI's service — stop condition then misfires. 1000 is
    # a safe lowest-common-denominator across all NE layers.
    page_size = 1000
    offset = 0
    features: list[dict] = []

    while True:
        params = {
            "where": "1=1",
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }
        url = f"{base}/query?{urllib.parse.urlencode(params)}"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    data = json.loads(r.read())
                break
            except Exception as exc:
                if attempt == 2:
                    raise
                print(f"  retry after {exc!r}", file=sys.stderr)
                time.sleep(2 ** attempt)

        page = data.get("features", [])
        features.extend(page)
        print(f"  offset={offset} fetched={len(page)} total={len(features)}")
        if len(page) < page_size:
            break
        offset += page_size

    out = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w") as f:
        json.dump(out, f)
    print(f"  wrote {len(features)} features → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: fetch_to_geojson.py <layer url> <out.geojson> [fields...]", file=sys.stderr)
        sys.exit(1)
    fetch_all(sys.argv[1], sys.argv[2], sys.argv[3:])
