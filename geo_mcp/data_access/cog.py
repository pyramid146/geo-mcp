from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import rasterio


def _cogs_dir() -> Path:
    return Path(os.getenv("COGS_DIR", "/data/cogs"))


@lru_cache(maxsize=8)
def open_cog(name: str) -> rasterio.DatasetReader:
    """Open a named COG out of the configured COGS_DIR, once per process."""
    path = _cogs_dir() / name
    return rasterio.open(path)
