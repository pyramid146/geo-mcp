from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    http_host: str
    http_port: int

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings(
        db_host=os.getenv("DB_HOST", "127.0.0.1"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_name=_env("POSTGRES_DB"),
        db_user=os.getenv("DB_USER", "mcp_readonly"),
        db_password=_env("MCP_READONLY_PASSWORD"),
        http_host=os.getenv("MCP_HTTP_HOST", "127.0.0.1"),
        http_port=int(os.getenv("MCP_HTTP_PORT", "8000")),
    )
