"""Postgres helpers for google-ads-cli."""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any


DEFAULT_DSN = "postgresql:///google_ads_cli"


def _load_env_file(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def config_dir() -> pathlib.Path:
    home = pathlib.Path(os.environ.get("GOOGLE_ADS_CLI_HOME", pathlib.Path.home() / ".google-ads-cli")).expanduser()
    return pathlib.Path(os.environ.get("GOOGLE_ADS_CLI_CONFIG_DIR", home)).expanduser()


def load_env() -> None:
    _load_env_file(config_dir() / ".env")


def dsn() -> str:
    load_env()
    return (
        os.environ.get("GOOGLE_ADS_CLI_PG_DSN")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DSN
    )


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect(*, schema: str | None = None, application_name: str = "google-ads-cli"):
    import psycopg

    conn = psycopg.connect(dsn(), application_name=application_name)
    if schema:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema)}")
            cur.execute(f"SET search_path TO {quote_ident(schema)}, public")
        conn.commit()
    return conn


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
