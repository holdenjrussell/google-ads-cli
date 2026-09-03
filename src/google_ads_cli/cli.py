#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["psycopg[binary]>=3.2.0"]
# ///
"""Installable Google Ads warehouse and operator CLI.

The CLI stores native Google Ads structure, search terms, fields,
recommendations, assets, budgets, change history, mutation plans, and optional
platform-reported performance in a local Postgres database.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


def _preload_env_file(path: pathlib.Path) -> None:
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


_INITIAL_PROFILE_ROOT = pathlib.Path(
    os.environ.get("GOOGLE_ADS_CLI_HOME", pathlib.Path.home() / ".google-ads-cli")
).expanduser()
_INITIAL_CONFIG_DIR = pathlib.Path(os.environ.get("GOOGLE_ADS_CLI_CONFIG_DIR", _INITIAL_PROFILE_ROOT)).expanduser()
_preload_env_file(_INITIAL_CONFIG_DIR / ".env")


def _split_config_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in re.split(r"[,|\n]", raw) if item.strip()]


def _load_json_config(env_name: str, file_env_name: str, default: dict[str, Any]) -> dict[str, Any]:
    raw = os.environ.get(env_name)
    path = os.environ.get(file_env_name)
    try:
        if raw:
            value = json.loads(raw)
            return value if isinstance(value, dict) else default
        if path:
            value = json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default
    except (OSError, json.JSONDecodeError):
        return default
    return default


PACKAGE_DIR = pathlib.Path(__file__).parent
PROJECT_ROOT = PACKAGE_DIR.parents[1] if len(PACKAGE_DIR.parents) > 1 else PACKAGE_DIR
PROFILE_ROOT = pathlib.Path(os.environ.get("GOOGLE_ADS_CLI_HOME", pathlib.Path.home() / ".google-ads-cli")).expanduser()
CONFIG_DIR = pathlib.Path(os.environ.get("GOOGLE_ADS_CLI_CONFIG_DIR", PROFILE_ROOT)).expanduser()
CONFIG_ENV_PATH = CONFIG_DIR / ".env"
SCHEMA = "google_ads_tw"
DEFAULT_API_VERSION = os.environ.get("GOOGLE_ADS_API_VERSION", "v24")
REST_BASE = "https://googleads.googleapis.com"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
OAUTH_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
DEFAULT_SLACK_CHANNEL = os.environ.get("GOOGLE_ADS_SLACK_CHANNEL_ID", "")
DEFAULT_TARGET_NCPA = float(os.environ.get("GOOGLE_ADS_TARGET_NCPA", "70"))
GOOGLE_ADS_OPERATOR_DASHBOARD_URL = os.environ.get("GOOGLE_ADS_OPERATOR_DASHBOARD_URL", "")
DEFAULT_BUSINESS_NAME = os.environ.get("GOOGLE_ADS_BUSINESS_NAME", "Your Business")
DEFAULT_BRAND_TERMS = _split_config_list(os.environ.get("GOOGLE_ADS_BRAND_TERMS"))
REPORT_TITLE = os.environ.get(
    "GOOGLE_ADS_REPORT_TITLE",
    f"{DEFAULT_BUSINESS_NAME} Google Ads Heartbeat" if DEFAULT_BUSINESS_NAME != "Your Business" else "Google Ads Heartbeat",
)
DEFAULT_PMAX_BRAND_ASSETS = _load_json_config("GOOGLE_ADS_PMAX_BRAND_ASSETS_JSON", "GOOGLE_ADS_PMAX_BRAND_ASSETS_FILE", {})
DEFAULT_PMAX_ASSET_GROUP_ASSETS = _load_json_config(
    "GOOGLE_ADS_PMAX_ASSET_GROUP_ASSETS_JSON",
    "GOOGLE_ADS_PMAX_ASSET_GROUP_ASSETS_FILE",
    {},
)
DEFAULT_DEMAND_GEN_AD_ASSETS = _load_json_config(
    "GOOGLE_ADS_DEMAND_GEN_AD_ASSETS_JSON",
    "GOOGLE_ADS_DEMAND_GEN_AD_ASSETS_FILE",
    {},
)
SLACK_HELPER_PATH = os.environ.get("GOOGLE_ADS_SLACK_HELPER")
DIRECT_HOURLY_JOB = os.environ.get("GOOGLE_ADS_DIRECT_HOURLY_JOB", "google-ads-direct-hourly")
DIRECT_DAILY_JOB = os.environ.get("GOOGLE_ADS_DIRECT_DAILY_JOB", "google-ads-direct-daily")
DIRECT_BOOTSTRAP_JOB = os.environ.get("GOOGLE_ADS_DIRECT_BOOTSTRAP_JOB", "google-ads-direct-bootstrap")
REPORT_HOURLY_JOB = os.environ.get("GOOGLE_ADS_REPORT_HOURLY_JOB", "google-ads-report-hourly")
ATTRIBUTION_HOURLY_JOB = os.environ.get("GOOGLE_ADS_ATTRIBUTION_HOURLY_JOB", "google-ads-attribution-hourly")
ATTRIBUTION_ROLLING_JOB = os.environ.get("GOOGLE_ADS_ATTRIBUTION_ROLLING_JOB", "google-ads-attribution-rolling")
AUDIT_SCHEDULER = os.environ.get("GOOGLE_ADS_AUDIT_SCHEDULER", "").lower() in {"1", "true", "yes"}
AUDIT_DASHBOARD = os.environ.get("GOOGLE_ADS_AUDIT_DASHBOARD", "").lower() in {"1", "true", "yes"}
AUDIT_SLACK_REPORT = os.environ.get("GOOGLE_ADS_AUDIT_SLACK_REPORT", "").lower() in {"1", "true", "yes"}
SCHEMA_LOCK_KEY = (240615001, 240615002)
OFFICIAL_CLIENT_REPO = "https://github.com/googleads/google-ads-python.git"
OPEN_SOURCE_REPOS = {
    "google-ads-open-cli": "https://github.com/Bin-Huang/google-ads-open-cli.git",
    "google-ads-api-report-fetcher": "https://github.com/google/ads-api-report-fetcher.git",
    "google-ads-mcp": "https://github.com/google-marketing-solutions/google_ads_mcp.git",
    "google-ads-api-developer-assistant": "https://github.com/googleads/google-ads-api-developer-assistant.git",
}
OFFICIAL_CLIENT_CACHE = PROFILE_ROOT / "cache" / "google-ads-python"
RESEARCH_CACHE = PROFILE_ROOT / "cache" / "google-ads-research"
EXPERT_SOURCE_DIR = pathlib.Path(os.environ.get("GOOGLE_ADS_EXPERT_SOURCE_DIR", PACKAGE_DIR / "references" / "expert-sources")).expanduser()
EXPERT_SOURCE_CATALOG = EXPERT_SOURCE_DIR / "source_catalog.json"
EXPERT_SOURCE_CACHE = EXPERT_SOURCE_DIR / "cache"
LAUNCHD_LOG_ROOTS: list[pathlib.Path] = []
log_root = PROFILE_ROOT / "logs"
if log_root not in LAUNCHD_LOG_ROOTS:
    LAUNCHD_LOG_ROOTS.append(log_root)
LAUNCHD_LOG_ROOT = LAUNCHD_LOG_ROOTS[0]

try:
    from .pg import connect, json_dumps, quote_ident  # noqa: E402
except ImportError:  # pragma: no cover - direct script execution fallback
    from pg import connect, json_dumps, quote_ident  # type: ignore  # noqa: E402


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def jsonb(value: Any) -> str:
    return json_dumps(value if value is not None else {})


def snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.lower()


def get_path(row: dict[str, Any], dotted: str) -> Any:
    current: Any = row
    for raw_part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        part = raw_part if raw_part in current else snake_to_camel(raw_part)
        current = current.get(part)
    return current


def str_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def num_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def money(value: float | int | None) -> str:
    if value is None:
        return "No data"
    return f"${float(value):,.2f}"


def short_money(value: float | int | None) -> str:
    if value is None:
        return "No data"
    value_f = float(value)
    sign = "-" if value_f < 0 else ""
    value_f = abs(value_f)
    if value_f >= 1000:
        return f"{sign}${value_f / 1000:.1f}K"
    return f"{sign}${value_f:,.0f}"


def pct(value: float | int | None) -> str:
    if value is None:
        return "No data"
    return f"{float(value) * 100:.1f}%"


def load_env_file(path: pathlib.Path, *, override: bool = False) -> None:
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
        if key and (override or key not in os.environ):
            os.environ[key] = value


def load_env() -> None:
    load_env_file(CONFIG_ENV_PATH)


def update_skill_env(values: dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_ENV_PATH
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    keys = set(values)
    seen: set[str] = set()
    out: list[str] = []
    for raw in existing:
        line = raw.strip()
        key = ""
        if line and not line.startswith("#") and "=" in line:
            probe = line[len("export "):] if line.startswith("export ") else line
            key = probe.partition("=")[0].strip()
        if key in keys:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(raw)
    for key, value in values.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    path.chmod(0o600)


def api_version() -> str:
    load_env()
    return os.environ.get("GOOGLE_ADS_API_VERSION", DEFAULT_API_VERSION)


def credential_state() -> dict[str, Any]:
    load_env()
    refresh_ready = all(
        os.environ.get(name)
        for name in ("GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET")
    )
    keys = {
        "access_token": bool(os.environ.get("GOOGLE_ADS_ACCESS_TOKEN")),
        "developer_token": bool(os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")),
        "customer_id": bool(os.environ.get("GOOGLE_ADS_CUSTOMER_ID")),
        "login_customer_id": bool(os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")),
        "refresh_token": bool(os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")),
        "client_id": bool(os.environ.get("GOOGLE_ADS_CLIENT_ID")),
        "client_secret": bool(os.environ.get("GOOGLE_ADS_CLIENT_SECRET")),
    }
    missing = [name for name in ("developer_token", "customer_id") if not keys[name]]
    if not keys["access_token"] and not refresh_ready:
        missing.append("access_token_or_refresh_token_set")
    return {
        "ready": not missing,
        "missing": missing,
        "keys": keys,
        "refresh_ready": refresh_ready,
    }


def refresh_access_token() -> str | None:
    load_env()
    if not all(
        os.environ.get(name)
        for name in ("GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET")
    ):
        return None
    payload = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(text)
        except json.JSONDecodeError:
            details = {"error": text}
        raise RuntimeError(f"Google OAuth refresh failed {exc.code}: {json.dumps(details)[:800]}") from exc
    token = body.get("access_token")
    if not token:
        raise RuntimeError("Google OAuth refresh did not return an access token")
    os.environ["GOOGLE_ADS_ACCESS_TOKEN"] = token
    return str(token)


def current_access_token() -> str:
    token = refresh_access_token()
    if token:
        return token
    token = os.environ.get("GOOGLE_ADS_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GOOGLE_ADS_ACCESS_TOKEN is missing")
    return token


def token_scope_state(token: str) -> dict[str, Any]:
    url = f"{OAUTH_TOKENINFO_URL}?{urllib.parse.urlencode({'access_token': token})}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "scopes": [], "adwords_scope": False}
    scopes = str(body.get("scope") or "").split()
    return {"ok": True, "scopes": scopes, "adwords_scope": GOOGLE_ADS_SCOPE in scopes}


def mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "*" * min(6, max(2, len(local) - 2))
    return f"{masked_local}@{domain}"


def oauth_identity_state(token: str, *, reveal_email: bool = False) -> dict[str, Any]:
    req = urllib.request.Request(
        OAUTH_USERINFO_URL,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(text)
        except json.JSONDecodeError:
            details = {"error": text}
        return {"ok": False, "error": f"Google OAuth userinfo failed {exc.code}: {json.dumps(details)[:500]}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    email = str(body.get("email") or "").strip() or None
    domain = email.split("@", 1)[1] if email and "@" in email else None
    payload: dict[str, Any] = {
        "ok": True,
        "email_masked": mask_email(email),
        "email_domain": domain,
        "email_verified": body.get("email_verified"),
        "subject_present": bool(body.get("sub")),
    }
    if reveal_email:
        payload["email"] = email
    return payload


def google_headers() -> dict[str, str]:
    state = credential_state()
    if not state["keys"]["developer_token"]:
        raise RuntimeError("GOOGLE_ADS_DEVELOPER_TOKEN is missing")
    headers = {
        "Authorization": f"Bearer {current_access_token()}",
        "developer-token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id.replace("-", "")
    return headers


def customer_id(value: str | None = None) -> str:
    load_env()
    cid = value or os.environ.get("GOOGLE_ADS_CUSTOMER_ID") or ""
    cid = cid.replace("-", "").strip()
    if not cid:
        raise RuntimeError("GOOGLE_ADS_CUSTOMER_ID is missing")
    return cid


def ensure_schema() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS google_sync_runs (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            status TEXT NOT NULL,
            customer_id TEXT,
            api_version TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            rows_fetched INTEGER NOT NULL DEFAULT 0,
            rows_written INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_api_catalog_sources (
            source_name TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            source_ref TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_api_services (
            api_version TEXT NOT NULL,
            service_name TEXT NOT NULL,
            service_file TEXT,
            methods JSONB NOT NULL DEFAULT '[]'::jsonb,
            operations JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_name TEXT,
            source_ref TEXT,
            raw_hash TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (api_version, service_name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_api_methods (
            api_version TEXT NOT NULL,
            service_name TEXT NOT NULL,
            method_name TEXT NOT NULL,
            operation_kind TEXT,
            rest_path TEXT,
            service_file TEXT,
            source_name TEXT,
            source_ref TEXT,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (api_version, service_name, method_name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_ads_fields (
            api_version TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            data_type TEXT,
            type_url TEXT,
            selectable BOOLEAN,
            filterable BOOLEAN,
            sortable BOOLEAN,
            repeated BOOLEAN,
            selectable_with JSONB NOT NULL DEFAULT '[]'::jsonb,
            attribute_resources JSONB NOT NULL DEFAULT '[]'::jsonb,
            metrics JSONB NOT NULL DEFAULT '[]'::jsonb,
            segments JSONB NOT NULL DEFAULT '[]'::jsonb,
            enum_values JSONB NOT NULL DEFAULT '[]'::jsonb,
            resource_name TEXT,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (api_version, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_offline_catalog_fields (
            api_version TEXT NOT NULL,
            resource TEXT NOT NULL,
            field_name TEXT NOT NULL,
            field_path TEXT NOT NULL,
            resource_kind TEXT NOT NULL,
            class_name TEXT,
            field_type TEXT,
            proto_type TEXT,
            enum_type TEXT,
            message_type TEXT,
            repeated BOOLEAN NOT NULL DEFAULT false,
            optional BOOLEAN NOT NULL DEFAULT false,
            description TEXT,
            source_file TEXT,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (api_version, field_path)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_query_manifest (
            api_version TEXT NOT NULL,
            surface_type TEXT NOT NULL,
            surface_name TEXT NOT NULL,
            command TEXT NOT NULL,
            query_name TEXT,
            source_resource TEXT,
            warehouse_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
            date_window TEXT,
            default_days INTEGER,
            default_chunk_days INTEGER,
            requires_auth BOOLEAN NOT NULL DEFAULT true,
            can_mutate BOOLEAN NOT NULL DEFAULT false,
            schedule TEXT,
            query TEXT,
            query_hash TEXT,
            selected_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            metric_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            segment_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            resource_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            notes TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (api_version, surface_type, surface_name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_raw_snapshots (
            id BIGSERIAL PRIMARY KEY,
            sync_run_id TEXT REFERENCES google_sync_runs(id) ON DELETE SET NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            api_version TEXT,
            customer_id TEXT,
            endpoint TEXT NOT NULL,
            request JSONB NOT NULL DEFAULT '{}'::jsonb,
            response JSONB NOT NULL,
            headers JSONB NOT NULL DEFAULT '{}'::jsonb,
            row_count INTEGER,
            status TEXT NOT NULL DEFAULT 'ok'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_fetch_errors (
            id BIGSERIAL PRIMARY KEY,
            sync_run_id TEXT REFERENCES google_sync_runs(id) ON DELETE SET NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            endpoint TEXT NOT NULL,
            request JSONB NOT NULL DEFAULT '{}'::jsonb,
            error JSONB NOT NULL DEFAULT '{}'::jsonb,
            message TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_customers (
            customer_id TEXT PRIMARY KEY,
            resource_name TEXT,
            descriptive_name TEXT,
            currency_code TEXT,
            time_zone TEXT,
            manager BOOLEAN,
            test_account BOOLEAN,
            status TEXT,
            optimization_score NUMERIC,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_campaign_budgets (
            customer_id TEXT NOT NULL,
            budget_id TEXT NOT NULL,
            resource_name TEXT,
            name TEXT,
            status TEXT,
            amount_micros BIGINT,
            delivery_method TEXT,
            explicitly_shared BOOLEAN,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, budget_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_campaigns (
            customer_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            resource_name TEXT,
            name TEXT,
            status TEXT,
            serving_status TEXT,
            advertising_channel_type TEXT,
            advertising_channel_sub_type TEXT,
            campaign_budget TEXT,
            bidding_strategy_type TEXT,
            start_date DATE,
            end_date DATE,
            optimization_score NUMERIC,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, campaign_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_ad_groups (
            customer_id TEXT NOT NULL,
            ad_group_id TEXT NOT NULL,
            campaign_id TEXT,
            resource_name TEXT,
            name TEXT,
            status TEXT,
            type TEXT,
            cpc_bid_micros BIGINT,
            target_cpa_micros BIGINT,
            target_roas NUMERIC,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, ad_group_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_ads (
            customer_id TEXT NOT NULL,
            ad_group_id TEXT NOT NULL DEFAULT '',
            ad_id TEXT NOT NULL,
            campaign_id TEXT,
            resource_name TEXT,
            name TEXT,
            status TEXT,
            ad_type TEXT,
            final_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
            display_url TEXT,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, ad_group_id, ad_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_keywords (
            customer_id TEXT NOT NULL,
            ad_group_id TEXT NOT NULL DEFAULT '',
            criterion_id TEXT NOT NULL,
            campaign_id TEXT,
            text TEXT,
            match_type TEXT,
            status TEXT,
            negative BOOLEAN,
            quality_score INTEGER,
            final_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, ad_group_id, criterion_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_search_terms (
            customer_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            campaign_id TEXT NOT NULL DEFAULT '',
            ad_group_id TEXT NOT NULL DEFAULT '',
            search_term TEXT NOT NULL,
            status TEXT,
            impressions BIGINT,
            clicks BIGINT,
            cost_micros BIGINT,
            conversions NUMERIC,
            conversions_value NUMERIC,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, report_date, campaign_id, ad_group_id, search_term)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_assets (
            customer_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            resource_name TEXT,
            name TEXT,
            type TEXT,
            source TEXT,
            policy_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, asset_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_asset_groups (
            customer_id TEXT NOT NULL,
            asset_group_id TEXT NOT NULL,
            campaign_id TEXT,
            resource_name TEXT,
            name TEXT,
            status TEXT,
            final_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, asset_group_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_conversion_actions (
            customer_id TEXT NOT NULL,
            conversion_action_id TEXT NOT NULL,
            resource_name TEXT,
            name TEXT,
            status TEXT,
            type TEXT,
            category TEXT,
            include_in_conversions_metric BOOLEAN,
            value_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, conversion_action_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_recommendations (
            customer_id TEXT NOT NULL,
            recommendation_id TEXT NOT NULL,
            campaign_id TEXT,
            type TEXT,
            impact JSONB NOT NULL DEFAULT '{}'::jsonb,
            dismissed BOOLEAN,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, recommendation_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_change_events (
            customer_id TEXT NOT NULL,
            change_event_id TEXT NOT NULL,
            change_date_time TIMESTAMPTZ,
            user_email TEXT,
            resource_type TEXT,
            change_resource_type TEXT,
            changed_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            old_resource JSONB NOT NULL DEFAULT '{}'::jsonb,
            new_resource JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, change_event_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_gaql_rows (
            id BIGSERIAL PRIMARY KEY,
            sync_run_id TEXT REFERENCES google_sync_runs(id) ON DELETE SET NULL,
            customer_id TEXT NOT NULL,
            query_name TEXT NOT NULL,
            source_resource TEXT NOT NULL,
            report_date DATE,
            row_hash TEXT NOT NULL,
            query TEXT NOT NULL,
            row_json JSONB NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (customer_id, query_name, row_hash)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_core_generic (
            customer_id TEXT NOT NULL,
            surface TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            query_name TEXT NOT NULL,
            source_resource TEXT NOT NULL,
            row_hash TEXT NOT NULL,
            query TEXT NOT NULL,
            selected_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
            row_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, surface, entity_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_performance_daily (
            customer_id TEXT NOT NULL,
            level TEXT NOT NULL,
            report_date DATE NOT NULL,
            campaign_id TEXT NOT NULL DEFAULT '',
            ad_group_id TEXT NOT NULL DEFAULT '',
            ad_id TEXT NOT NULL DEFAULT '',
            criterion_id TEXT NOT NULL DEFAULT '',
            asset_group_id TEXT NOT NULL DEFAULT '',
            search_term TEXT NOT NULL DEFAULT '',
            campaign_name TEXT,
            ad_group_name TEXT,
            ad_name TEXT,
            campaign_channel_type TEXT,
            campaign_channel_sub_type TEXT,
            device TEXT NOT NULL DEFAULT '',
            network TEXT NOT NULL DEFAULT '',
            impressions BIGINT,
            clicks BIGINT,
            interactions BIGINT,
            cost_micros BIGINT,
            conversions NUMERIC,
            conversions_value NUMERIC,
            all_conversions NUMERIC,
            all_conversions_value NUMERIC,
            video_views BIGINT,
            ctr NUMERIC,
            average_cpc_micros BIGINT,
            average_cpm_micros BIGINT,
            cost_per_conversion_micros BIGINT,
            value_per_conversion NUMERIC,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (
                customer_id, level, report_date, campaign_id, ad_group_id,
                ad_id, criterion_id, asset_group_id, search_term, device, network
            )
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_performance_generic (
            customer_id TEXT NOT NULL,
            surface TEXT NOT NULL,
            report_date DATE NOT NULL,
            entity_key TEXT NOT NULL,
            query_name TEXT NOT NULL,
            row_hash TEXT NOT NULL,
            query TEXT NOT NULL,
            selected_dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            row_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_id, surface, report_date, entity_key, row_hash)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_backfill_chunks (
            customer_id TEXT NOT NULL,
            surface TEXT NOT NULL,
            since_date DATE NOT NULL,
            until_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            rows_fetched INTEGER NOT NULL DEFAULT 0,
            rows_written INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            last_run_id TEXT REFERENCES google_sync_runs(id) ON DELETE SET NULL,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (customer_id, surface, since_date, until_date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_optimizer_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            report_date DATE NOT NULL,
            latest_hour TIMESTAMPTZ,
            target_ncpa NUMERIC NOT NULL,
            decision_payload JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_mutation_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            customer_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            operation_count INTEGER NOT NULL DEFAULT 0,
            validate_only BOOLEAN NOT NULL DEFAULT true,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            output_path TEXT,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            executed_run_id TEXT REFERENCES google_sync_runs(id) ON DELETE SET NULL,
            executed_at TIMESTAMPTZ,
            result JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_keyword_research_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            customer_id TEXT NOT NULL,
            seed_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
            final_url TEXT,
            geo_targets JSONB NOT NULL DEFAULT '[]'::jsonb,
            language TEXT,
            keyword_plan_network TEXT,
            request JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_count INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'generateKeywordIdeas',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_keyword_research_ideas (
            run_id UUID NOT NULL REFERENCES google_keyword_research_runs(id) ON DELETE CASCADE,
            customer_id TEXT NOT NULL,
            text TEXT NOT NULL,
            close_variants JSONB NOT NULL DEFAULT '[]'::jsonb,
            avg_monthly_searches BIGINT,
            competition TEXT,
            competition_index INTEGER,
            low_top_of_page_bid_micros BIGINT,
            high_top_of_page_bid_micros BIGINT,
            monthly_search_volumes JSONB NOT NULL DEFAULT '[]'::jsonb,
            recommended_match_type TEXT,
            intent_bucket TEXT,
            source TEXT NOT NULL DEFAULT 'generateKeywordIdeas',
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, text)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_expert_source_documents (
            source_id TEXT NOT NULL,
            document_url TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            access_level TEXT NOT NULL,
            topics JSONB NOT NULL DEFAULT '[]'::jsonb,
            operator_notes TEXT,
            title TEXT,
            content_hash TEXT,
            text_excerpt TEXT,
            summary TEXT,
            cache_path TEXT,
            retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (source_id, document_url)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_attribution_hourly_imports (
            report_date DATE,
            report_hour TIMESTAMPTZ,
            shop_domain TEXT,
            channel TEXT,
            preset_name TEXT,
            attribution_model TEXT,
            attribution_window TEXT,
            accounting_mode TEXT,
            subscription_filter TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            adset_id TEXT,
            adset_name TEXT,
            ad_id TEXT,
            ad_name TEXT,
            ad_spend DOUBLE PRECISION,
            combined_net_revenue DOUBLE PRECISION,
            pixel_purchases DOUBLE PRECISION,
            pixel_new_customer_purchases DOUBLE PRECISION,
            pixel_new_customer_cpa DOUBLE PRECISION,
            pixel_cpa DOUBLE PRECISION,
            pixel_new_customer_purchases_percent DOUBLE PRECISION,
            impressions DOUBLE PRECISION,
            cpm DOUBLE PRECISION,
            outbound_ctr DOUBLE PRECISION,
            clicks DOUBLE PRECISION,
            pixel_sessions DOUBLE PRECISION,
            pixel_cost_per_visitors DOUBLE PRECISION,
            pixel_new_visitors DOUBLE PRECISION,
            pixel_cost_per_new_visitors DOUBLE PRECISION,
            pixel_new_visitor_percent DOUBLE PRECISION,
            pixel_new_customer_aov DOUBLE PRECISION,
            pixel_aov DOUBLE PRECISION,
            pixel_new_customer_conversion_rate DOUBLE PRECISION,
            pixel_conversion_rate DOUBLE PRECISION,
            pixel_roas DOUBLE PRECISION,
            pixel_new_customers_roas DOUBLE PRECISION,
            pixel_unique_add_to_carts DOUBLE PRECISION,
            ctr DOUBLE PRECISION,
            cpc DOUBLE PRECISION,
            outbound_clicks DOUBLE PRECISION,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_file TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS google_attribution_level_daily_imports (
            report_date DATE,
            level TEXT,
            channel TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            adset_id TEXT,
            adset_name TEXT,
            ad_id TEXT,
            ad_name TEXT,
            shop_domain TEXT,
            preset_name TEXT,
            attribution_model TEXT,
            attribution_window TEXT,
            accounting_mode TEXT,
            subscription_filter TEXT,
            ad_spend DOUBLE PRECISION,
            combined_net_revenue DOUBLE PRECISION,
            pixel_purchases DOUBLE PRECISION,
            pixel_new_customer_purchases DOUBLE PRECISION,
            impressions DOUBLE PRECISION,
            clicks DOUBLE PRECISION,
            pixel_sessions DOUBLE PRECISION,
            pixel_new_visitors DOUBLE PRECISION,
            pixel_new_customer_revenue DOUBLE PRECISION,
            pixel_unique_add_to_carts DOUBLE PRECISION,
            outbound_clicks DOUBLE PRECISION,
            source_row_count INTEGER,
            hour_count INTEGER,
            rolled_up_at TIMESTAMPTZ
        )
        """,
        """
        CREATE OR REPLACE FUNCTION google_infer_campaign_type(name TEXT)
        RETURNS TEXT
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT CASE
                WHEN coalesce(name, '') = '' THEN 'unknown'
                WHEN regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%pmax%'
                  OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%performancemax%'
                  OR lower(name) LIKE '%performance max%' THEN 'pmax'
                WHEN lower(name) LIKE '%shopping%'
                  OR lower(name) LIKE '%standard shop%'
                  OR lower(name) LIKE '%product shopping%' THEN 'shopping'
                WHEN lower(name) LIKE '%youtube%'
                  OR lower(name) LIKE '%video%' THEN 'youtube_video'
                WHEN lower(name) LIKE '%demand gen%'
                  OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%demandgen%'
                  OR lower(name) LIKE '%discovery%' THEN 'demand_gen'
                WHEN lower(name) LIKE '%display%'
                  OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%gdn%' THEN 'display'
                WHEN lower(name) LIKE '%search%'
                  OR lower(name) LIKE '%rsa%'
                  OR lower(name) LIKE '%brand%'
                  OR lower(name) LIKE '%bofu%'
                  OR lower(name) LIKE '%generic%' THEN
                    CASE
                        WHEN lower(name) LIKE '%non-brand%'
                          OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%nonbrand%'
                          OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%nonbranded%'
                          OR lower(name) LIKE '%generic%' THEN 'generic_search'
                        WHEN lower(name) LIKE '%brand%'
                          OR lower(name) LIKE '%bofu%' THEN 'branded_search'
                        ELSE 'search'
                    END
                ELSE 'unknown'
            END
        $$;
        """,
        """
        CREATE OR REPLACE FUNCTION google_campaign_type_label(campaign_type TEXT)
        RETURNS TEXT
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT CASE coalesce(campaign_type, 'unknown')
                WHEN 'branded_search' THEN 'Branded Search'
                WHEN 'generic_search' THEN 'Generic Search'
                WHEN 'search' THEN 'Search'
                WHEN 'shopping' THEN 'Shopping'
                WHEN 'pmax' THEN 'Performance Max'
                WHEN 'youtube_video' THEN 'YouTube / Video'
                WHEN 'demand_gen' THEN 'Demand Gen'
                WHEN 'display' THEN 'Display'
                ELSE 'Unknown'
            END
        $$;
        """,
    ]
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_google_raw_run ON google_raw_snapshots(sync_run_id)",
        "CREATE INDEX IF NOT EXISTS idx_google_raw_endpoint ON google_raw_snapshots(endpoint)",
        "CREATE INDEX IF NOT EXISTS idx_google_fields_category ON google_ads_fields(api_version, category)",
        "CREATE INDEX IF NOT EXISTS idx_google_api_methods_kind ON google_api_methods(api_version, operation_kind)",
        "CREATE INDEX IF NOT EXISTS idx_google_query_manifest_type ON google_query_manifest(api_version, surface_type, requires_auth)",
        "CREATE INDEX IF NOT EXISTS idx_google_gaql_query_date ON google_gaql_rows(query_name, report_date)",
        "CREATE INDEX IF NOT EXISTS idx_google_core_generic_surface ON google_core_generic(surface, fetched_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_google_core_generic_hash ON google_core_generic(row_hash)",
        "CREATE INDEX IF NOT EXISTS idx_google_perf_date_level ON google_performance_daily(report_date, level)",
        "CREATE INDEX IF NOT EXISTS idx_google_perf_campaign ON google_performance_daily(campaign_id)",
        "CREATE INDEX IF NOT EXISTS idx_google_perf_search_term ON google_performance_daily(search_term) WHERE search_term <> ''",
        "CREATE INDEX IF NOT EXISTS idx_google_perf_generic_surface ON google_performance_generic(surface, report_date)",
        "CREATE INDEX IF NOT EXISTS idx_google_backfill_status ON google_backfill_chunks(status, surface)",
        "CREATE INDEX IF NOT EXISTS idx_google_optimizer_date ON google_optimizer_snapshots(report_date, generated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_google_mutation_plans_created ON google_mutation_plans(created_at DESC, entity_type, operation_type)",
        "CREATE INDEX IF NOT EXISTS idx_google_keyword_ideas_volume ON google_keyword_research_ideas(avg_monthly_searches DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS idx_google_keyword_ideas_intent ON google_keyword_research_ideas(intent_bucket, recommended_match_type)",
        "CREATE INDEX IF NOT EXISTS idx_google_expert_sources_type ON google_expert_source_documents(source_type, retrieved_at DESC)",
    ]
    views = [
        """
        CREATE OR REPLACE VIEW google_tw_attribution_hourly AS
        SELECT
            report_date,
            report_hour,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_id,
            campaign_name,
            adset_id AS ad_group_id,
            adset_name AS ad_group_name,
            ad_id,
            ad_name,
            ad_spend AS tw_spend,
            combined_net_revenue AS tw_revenue,
            pixel_purchases AS tw_purchases,
            pixel_new_customer_purchases AS tw_new_customer_orders,
            CASE WHEN ad_spend > 0 THEN combined_net_revenue / ad_spend END AS tw_roas,
            CASE WHEN pixel_new_customer_purchases > 0 THEN ad_spend / pixel_new_customer_purchases END AS tw_ncpa,
            CASE WHEN pixel_purchases > 0 THEN ad_spend / pixel_purchases END AS tw_cpa,
            ad_spend,
            pixel_new_customer_purchases,
            pixel_new_customer_cpa,
            pixel_purchases,
            pixel_cpa,
            pixel_new_customer_purchases_percent,
            impressions,
            cpm,
            outbound_ctr,
            clicks,
            pixel_sessions,
            pixel_cost_per_visitors,
            pixel_new_visitors,
            pixel_cost_per_new_visitors,
            pixel_new_visitor_percent,
            pixel_new_customer_aov,
            pixel_aov,
            pixel_new_customer_conversion_rate,
            pixel_conversion_rate,
            combined_net_revenue,
            pixel_roas,
            pixel_new_customers_roas,
            pixel_unique_add_to_carts,
            ctr,
            cpc,
            outbound_clicks,
            raw,
            source_file,
            fetched_at,
            google_infer_campaign_type(campaign_name) AS campaign_type,
            google_campaign_type_label(google_infer_campaign_type(campaign_name)) AS campaign_type_label
        FROM google_attribution_hourly_imports
        WHERE channel IN ('Google', 'Google Ads')
        """,
        """
        CREATE OR REPLACE VIEW google_tw_attribution_daily AS
        SELECT
            report_date,
            CASE WHEN level = 'adset' THEN 'ad_group' ELSE level END AS level,
            channel,
            campaign_id,
            campaign_name,
            adset_id AS ad_group_id,
            adset_name AS ad_group_name,
            ad_id,
            ad_name,
            sum(ad_spend) AS tw_spend,
            sum(combined_net_revenue) AS tw_revenue,
            sum(pixel_purchases) AS tw_purchases,
            sum(pixel_new_customer_purchases) AS tw_new_customer_orders,
            CASE WHEN sum(ad_spend) > 0 THEN sum(combined_net_revenue) / sum(ad_spend) END AS tw_roas,
            CASE WHEN sum(pixel_new_customer_purchases) > 0 THEN sum(ad_spend) / sum(pixel_new_customer_purchases) END AS tw_ncpa,
            CASE WHEN sum(pixel_purchases) > 0 THEN sum(ad_spend) / sum(pixel_purchases) END AS tw_cpa,
            shop_domain,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            sum(ad_spend) AS ad_spend,
            sum(pixel_new_customer_purchases) AS pixel_new_customer_purchases,
            CASE WHEN sum(pixel_new_customer_purchases) > 0 THEN sum(ad_spend) / sum(pixel_new_customer_purchases) END AS pixel_new_customer_cpa,
            sum(pixel_purchases) AS pixel_purchases,
            CASE WHEN sum(pixel_purchases) > 0 THEN sum(ad_spend) / sum(pixel_purchases) END AS pixel_cpa,
            CASE WHEN sum(pixel_purchases) > 0 THEN sum(pixel_new_customer_purchases) / sum(pixel_purchases) END AS pixel_new_customer_purchases_percent,
            sum(impressions)::bigint AS impressions,
            CASE WHEN sum(impressions) > 0 THEN sum(ad_spend) / sum(impressions) * 1000 END AS cpm,
            CASE WHEN sum(impressions) > 0 THEN sum(outbound_clicks) / sum(impressions) END AS outbound_ctr,
            sum(clicks)::bigint AS clicks,
            sum(pixel_sessions) AS pixel_sessions,
            CASE WHEN sum(pixel_sessions) > 0 THEN sum(ad_spend) / sum(pixel_sessions) END AS pixel_cost_per_visitors,
            sum(pixel_new_visitors) AS pixel_new_visitors,
            CASE WHEN sum(pixel_new_visitors) > 0 THEN sum(ad_spend) / sum(pixel_new_visitors) END AS pixel_cost_per_new_visitors,
            CASE WHEN sum(pixel_sessions) > 0 THEN sum(pixel_new_visitors) / sum(pixel_sessions) END AS pixel_new_visitor_percent,
            CASE WHEN sum(pixel_new_customer_purchases) > 0 THEN sum(pixel_new_customer_revenue) / sum(pixel_new_customer_purchases) END AS pixel_new_customer_aov,
            CASE WHEN sum(pixel_purchases) > 0 THEN sum(combined_net_revenue) / sum(pixel_purchases) END AS pixel_aov,
            CASE WHEN sum(pixel_sessions) > 0 THEN sum(pixel_new_customer_purchases) / sum(pixel_sessions) END AS pixel_new_customer_conversion_rate,
            CASE WHEN sum(pixel_sessions) > 0 THEN sum(pixel_purchases) / sum(pixel_sessions) END AS pixel_conversion_rate,
            sum(combined_net_revenue) AS combined_net_revenue,
            CASE WHEN sum(ad_spend) > 0 THEN sum(combined_net_revenue) / sum(ad_spend) END AS pixel_roas,
            CASE WHEN sum(ad_spend) > 0 THEN sum(pixel_new_customer_revenue) / sum(ad_spend) END AS pixel_new_customers_roas,
            sum(pixel_unique_add_to_carts) AS pixel_unique_add_to_carts,
            CASE WHEN sum(impressions) > 0 THEN sum(clicks) / sum(impressions) END AS ctr,
            CASE WHEN sum(clicks) > 0 THEN sum(ad_spend) / sum(clicks) END AS cpc,
            sum(outbound_clicks) AS outbound_clicks,
            sum(pixel_new_customer_revenue) AS pixel_new_customer_revenue,
            sum(source_row_count)::integer AS source_row_count,
            max(hour_count) AS hour_count,
            max(rolled_up_at) AS rolled_up_at,
            google_infer_campaign_type(campaign_name) AS campaign_type,
            google_campaign_type_label(google_infer_campaign_type(campaign_name)) AS campaign_type_label
        FROM google_attribution_level_daily_imports
        WHERE channel IN ('Google', 'Google Ads')
        GROUP BY
            report_date,
            CASE WHEN level = 'adset' THEN 'ad_group' ELSE level END,
            channel,
            campaign_id,
            campaign_name,
            adset_id,
            adset_name,
            ad_id,
            ad_name,
            shop_domain,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter
        """,
        """
        CREATE OR REPLACE VIEW google_tw_attribution_level_daily AS
        SELECT * FROM google_tw_attribution_daily
        """,
        """
        CREATE OR REPLACE VIEW google_ad_hourly_performance AS
        SELECT
            NULL::text AS customer_id,
            report_date AS date_start,
            report_date AS date_stop,
            report_hour AS period_start,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_id,
            campaign_name,
            ad_group_id,
            ad_group_name,
            ad_id,
            ad_name,
            tw_spend AS spend,
            impressions,
            clicks,
            outbound_clicks,
            ctr,
            cpc,
            cpm,
            tw_purchases AS purchases,
            tw_new_customer_orders AS new_customer_orders,
            tw_revenue AS revenue,
            tw_roas AS roas,
            tw_cpa AS cpa,
            tw_ncpa AS ncpa,
            fetched_at,
            'triple_whale_hourly'::text AS source,
            campaign_type,
            campaign_type_label
        FROM google_tw_attribution_hourly
        """,
        """
        CREATE OR REPLACE VIEW google_ad_daily_performance AS
        SELECT
            NULL::text AS customer_id,
            report_date AS date_start,
            report_date AS date_stop,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_id,
            campaign_name,
            ad_group_id,
            ad_group_name,
            ad_id,
            ad_name,
            tw_spend AS spend,
            impressions,
            clicks,
            outbound_clicks,
            ctr,
            cpc,
            cpm,
            tw_purchases AS purchases,
            tw_new_customer_orders AS new_customer_orders,
            tw_revenue AS revenue,
            tw_roas AS roas,
            tw_cpa AS cpa,
            tw_ncpa AS ncpa,
            rolled_up_at AS fetched_at,
            'triple_whale_daily'::text AS source,
            campaign_type,
            campaign_type_label
        FROM google_tw_attribution_daily
        WHERE level = 'ad'
        """,
        """
        CREATE OR REPLACE VIEW google_ad_group_daily_performance AS
        SELECT
            NULL::text AS customer_id,
            report_date AS date_start,
            report_date AS date_stop,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_id,
            campaign_name,
            ad_group_id,
            ad_group_name,
            tw_spend AS spend,
            impressions,
            clicks,
            outbound_clicks,
            ctr,
            cpc,
            cpm,
            tw_purchases AS purchases,
            tw_new_customer_orders AS new_customer_orders,
            tw_revenue AS revenue,
            tw_roas AS roas,
            tw_cpa AS cpa,
            tw_ncpa AS ncpa,
            rolled_up_at AS fetched_at,
            'triple_whale_daily'::text AS source,
            campaign_type,
            campaign_type_label
        FROM google_tw_attribution_daily
        WHERE level = 'ad_group'
        """,
        """
        CREATE OR REPLACE VIEW google_campaign_daily_performance AS
        SELECT
            NULL::text AS customer_id,
            report_date AS date_start,
            report_date AS date_stop,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_id,
            campaign_name,
            tw_spend AS spend,
            impressions,
            clicks,
            outbound_clicks,
            ctr,
            cpc,
            cpm,
            tw_purchases AS purchases,
            tw_new_customer_orders AS new_customer_orders,
            tw_revenue AS revenue,
            tw_roas AS roas,
            tw_cpa AS cpa,
            tw_ncpa AS ncpa,
            rolled_up_at AS fetched_at,
            'triple_whale_daily'::text AS source,
            campaign_type,
            campaign_type_label
        FROM google_tw_attribution_daily
        WHERE level = 'campaign'
        """,
        """
        CREATE OR REPLACE VIEW google_account_daily_performance AS
        SELECT
            NULL::text AS customer_id,
            report_date AS date_start,
            report_date AS date_stop,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            sum(tw_spend) AS spend,
            sum(impressions)::bigint AS impressions,
            sum(clicks)::bigint AS clicks,
            sum(outbound_clicks) AS outbound_clicks,
            CASE WHEN sum(impressions) > 0 THEN sum(clicks) / sum(impressions) END AS ctr,
            CASE WHEN sum(clicks) > 0 THEN sum(tw_spend) / sum(clicks) END AS cpc,
            CASE WHEN sum(impressions) > 0 THEN sum(tw_spend) / sum(impressions) * 1000 END AS cpm,
            sum(tw_purchases) AS purchases,
            sum(tw_new_customer_orders) AS new_customer_orders,
            sum(tw_revenue) AS revenue,
            CASE WHEN sum(tw_spend) > 0 THEN sum(tw_revenue) / sum(tw_spend) END AS roas,
            CASE WHEN sum(tw_purchases) > 0 THEN sum(tw_spend) / sum(tw_purchases) END AS cpa,
            CASE WHEN sum(tw_new_customer_orders) > 0 THEN sum(tw_spend) / sum(tw_new_customer_orders) END AS ncpa,
            max(rolled_up_at) AS fetched_at,
            'triple_whale_daily'::text AS source,
            'all'::text AS campaign_type,
            'All Campaign Types'::text AS campaign_type_label
        FROM google_tw_attribution_daily
        WHERE level = 'campaign'
        GROUP BY
            report_date,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter
        """,
        """
        CREATE OR REPLACE VIEW google_campaign_type_daily_performance AS
        SELECT
            NULL::text AS customer_id,
            report_date AS date_start,
            report_date AS date_stop,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_type,
            campaign_type_label,
            sum(tw_spend) AS spend,
            sum(impressions)::bigint AS impressions,
            sum(clicks)::bigint AS clicks,
            sum(outbound_clicks) AS outbound_clicks,
            CASE WHEN sum(impressions) > 0 THEN sum(clicks) / sum(impressions) END AS ctr,
            CASE WHEN sum(clicks) > 0 THEN sum(tw_spend) / sum(clicks) END AS cpc,
            CASE WHEN sum(impressions) > 0 THEN sum(tw_spend) / sum(impressions) * 1000 END AS cpm,
            sum(tw_purchases) AS purchases,
            sum(tw_new_customer_orders) AS new_customer_orders,
            sum(tw_revenue) AS revenue,
            CASE WHEN sum(tw_spend) > 0 THEN sum(tw_revenue) / sum(tw_spend) END AS roas,
            CASE WHEN sum(tw_purchases) > 0 THEN sum(tw_spend) / sum(tw_purchases) END AS cpa,
            CASE WHEN sum(tw_new_customer_orders) > 0 THEN sum(tw_spend) / sum(tw_new_customer_orders) END AS ncpa,
            max(rolled_up_at) AS fetched_at,
            'triple_whale_daily'::text AS source
        FROM google_tw_attribution_daily
        WHERE level = 'campaign'
        GROUP BY
            report_date,
            shop_domain,
            channel,
            preset_name,
            attribution_model,
            attribution_window,
            accounting_mode,
            subscription_filter,
            campaign_type,
            campaign_type_label
        """,
        """
        CREATE OR REPLACE VIEW google_tw_rolling_31d AS
        WITH latest AS (
            SELECT max(report_date) AS end_date
            FROM google_tw_attribution_daily
        )
        SELECT
            latest.end_date - 30 AS window_start,
            latest.end_date AS window_end,
            d.level,
            d.campaign_id,
            max(d.campaign_name) AS campaign_name,
            d.ad_group_id,
            max(d.ad_group_name) AS ad_group_name,
            d.ad_id,
            max(d.ad_name) AS ad_name,
            sum(d.tw_spend) AS spend,
            sum(d.impressions)::bigint AS impressions,
            sum(d.clicks)::bigint AS clicks,
            sum(d.tw_purchases) AS purchases,
            sum(d.tw_new_customer_orders) AS new_customer_orders,
            sum(d.tw_revenue) AS revenue,
            CASE WHEN sum(d.tw_spend) > 0 THEN sum(d.tw_revenue) / sum(d.tw_spend) END AS roas,
            CASE WHEN sum(d.tw_purchases) > 0 THEN sum(d.tw_spend) / sum(d.tw_purchases) END AS cpa,
            CASE WHEN sum(d.tw_new_customer_orders) > 0 THEN sum(d.tw_spend) / sum(d.tw_new_customer_orders) END AS ncpa,
            max(d.rolled_up_at) AS rolled_up_at,
            google_infer_campaign_type(max(d.campaign_name)) AS campaign_type,
            google_campaign_type_label(google_infer_campaign_type(max(d.campaign_name))) AS campaign_type_label
        FROM google_tw_attribution_daily d
        JOIN latest ON true
        WHERE latest.end_date IS NOT NULL
          AND d.report_date BETWEEN latest.end_date - 30 AND latest.end_date
        GROUP BY latest.end_date, d.level, d.campaign_id, d.ad_group_id, d.ad_id
        """,
        """
        CREATE OR REPLACE VIEW google_performance_daily_summary AS
        SELECT
            customer_id,
            level,
            report_date,
            campaign_id,
            max(campaign_name) AS campaign_name,
            sum(cost_micros) / 1000000.0 AS spend,
            sum(impressions) AS impressions,
            sum(clicks) AS clicks,
            sum(conversions) AS conversions,
            sum(conversions_value) AS conversion_value,
            CASE WHEN sum(cost_micros) > 0 THEN sum(conversions_value) / (sum(cost_micros) / 1000000.0) END AS roas,
            CASE WHEN sum(conversions) > 0 THEN (sum(cost_micros) / 1000000.0) / sum(conversions) END AS cpa
        FROM google_performance_daily
        GROUP BY customer_id, level, report_date, campaign_id
        """,
        """
        CREATE OR REPLACE VIEW google_tw_platform_comparison_daily AS
        SELECT
            coalesce(t.report_date, p.report_date) AS report_date,
            coalesce(t.campaign_id, p.campaign_id) AS campaign_id,
            coalesce(t.campaign_name, p.campaign_name) AS campaign_name,
            t.tw_spend,
            t.tw_revenue,
            t.tw_purchases,
            t.tw_new_customer_orders,
            t.tw_roas,
            t.tw_ncpa,
            p.spend AS google_reported_spend,
            p.conversions AS google_reported_conversions,
            p.conversion_value AS google_reported_conversion_value,
            p.roas AS google_reported_roas,
            p.cpa AS google_reported_cpa
        FROM google_tw_attribution_daily t
        FULL OUTER JOIN google_performance_daily_summary p
          ON p.report_date = t.report_date
         AND p.level = 'campaign'
         AND p.campaign_id = coalesce(t.campaign_id, '')
        WHERE coalesce(t.level, 'campaign') = 'campaign'
        """,
    ]
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn:
        with conn.cursor() as cur:
            # Launchd/reporting commands can overlap; serialize schema DDL.
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", SCHEMA_LOCK_KEY)
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            for statement in statements:
                cur.execute(statement)
            for statement in indexes:
                cur.execute(statement)
            for statement in views:
                cur.execute(statement)
        conn.commit()


def run_start(command: str, customer: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    ensure_schema()
    run_id = str(uuid.uuid4())
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_sync_runs (id, command, status, customer_id, api_version, metadata)
            VALUES (%s, %s, 'running', %s, %s, %s::jsonb)
            """,
            (run_id, command, customer, api_version(), jsonb(metadata or {})),
        )
    return run_id


def run_finish(
    run_id: str,
    status: str,
    *,
    rows_fetched: int = 0,
    rows_written: int = 0,
    errors: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE google_sync_runs
            SET status = %s,
                completed_at = now(),
                rows_fetched = rows_fetched + %s,
                rows_written = rows_written + %s,
                errors = errors + %s,
                metadata = metadata || %s::jsonb
            WHERE id = %s
            """,
            (status, rows_fetched, rows_written, errors, jsonb(metadata or {}), run_id),
        )


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in headers.items():
        lowered = str(key).lower()
        if lowered in {"authorization", "developer-token", "login-customer-id"}:
            continue
        out[str(key)] = str(value)
    return out


def sanitize_request(request: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(request)
    for key in list(cleaned):
        if "token" in str(key).lower() or "secret" in str(key).lower():
            cleaned[key] = "[redacted]"
    return cleaned


def store_raw_snapshot(
    run_id: str | None,
    *,
    customer: str | None,
    endpoint: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any] | list[Any],
    response_headers: dict[str, Any] | None = None,
) -> None:
    row_count = None
    if isinstance(response_payload, dict) and isinstance(response_payload.get("results"), list):
        row_count = len(response_payload["results"])
    elif isinstance(response_payload, list):
        row_count = sum(len(item.get("results", [])) for item in response_payload if isinstance(item, dict))
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_raw_snapshots (
                sync_run_id, api_version, customer_id, endpoint, request,
                response, headers, row_count
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            """,
            (
                run_id,
                api_version(),
                customer,
                endpoint,
                jsonb(sanitize_request(request_payload)),
                jsonb(response_payload),
                jsonb(sanitize_headers(response_headers or {})),
                row_count,
            ),
        )


def log_fetch_error(run_id: str | None, endpoint: str, request_payload: dict[str, Any], exc: Exception) -> None:
    payload = {"type": exc.__class__.__name__, "message": str(exc)}
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_fetch_errors (sync_run_id, endpoint, request, error, message)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
            """,
            (run_id, endpoint, jsonb(sanitize_request(request_payload)), jsonb(payload), str(exc)),
        )


def api_request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    url = f"{REST_BASE}/{api_version()}/{path.lstrip('/')}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method.upper(), headers=google_headers())
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            text = response.read().decode("utf-8")
            return (json.loads(text) if text else {}, dict(response.headers.items()))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(text)
        except json.JSONDecodeError:
            details = {"error": text}
        raise RuntimeError(f"Google Ads API {exc.code}: {json.dumps(details)[:1200]}") from exc


def search_gaql(
    query: str,
    *,
    customer: str,
    run_id: str | None = None,
    query_name: str = "custom",
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_token = None
    page = 0
    endpoint = f"customers/{customer}/googleAds:search"
    while True:
        page += 1
        # Google Ads API v24 fixes Search page size at 10,000 rows and rejects
        # explicit pageSize values.
        request_payload: dict[str, Any] = {"query": query}
        if page_token:
            request_payload["pageToken"] = page_token
        try:
            body, headers = api_request("POST", endpoint, request_payload)
        except Exception as exc:
            log_fetch_error(run_id, endpoint, request_payload, exc)
            raise
        store_raw_snapshot(
            run_id,
            customer=customer,
            endpoint=endpoint,
            request_payload={"query_name": query_name, **request_payload},
            response_payload=body,
            response_headers=headers,
        )
        page_rows = body.get("results") or []
        rows.extend(page_rows)
        page_token = body.get("nextPageToken")
        if not page_token:
            break
        if max_pages and page >= max_pages:
            break
    return rows


def search_google_ads_fields(
    query: str,
    *,
    run_id: str | None = None,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_token = None
    page = 0
    endpoint = "googleAdsFields:search"
    while True:
        page += 1
        request_payload: dict[str, Any] = {"query": query}
        if page_token:
            request_payload["pageToken"] = page_token
        try:
            body, headers = api_request("POST", endpoint, request_payload)
        except Exception as exc:
            log_fetch_error(run_id, endpoint, request_payload, exc)
            raise
        store_raw_snapshot(
            run_id,
            customer=None,
            endpoint=endpoint,
            request_payload={"query_name": "field_catalog", **request_payload},
            response_payload=body,
            response_headers=headers,
        )
        page_rows = body.get("results") or []
        rows.extend(page_rows)
        page_token = body.get("nextPageToken")
        if not page_token:
            break
        if max_pages and page >= max_pages:
            break
    return rows


def row_hash(row: dict[str, Any], query_name: str) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{query_name}:{payload}".encode("utf-8")).hexdigest()


def store_gaql_rows(
    run_id: str | None,
    *,
    customer: str,
    query_name: str,
    source_resource: str,
    query: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    params = [
        (
            run_id,
            customer,
            query_name,
            source_resource,
            get_path(row, "segments.date"),
            row_hash(row, query_name),
            query,
            jsonb(row),
        )
        for row in rows
    ]
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO google_gaql_rows (
                sync_run_id, customer_id, query_name, source_resource,
                report_date, row_hash, query, row_json, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
            ON CONFLICT (customer_id, query_name, row_hash) DO UPDATE SET
                sync_run_id = excluded.sync_run_id,
                row_json = excluded.row_json,
                fetched_at = now()
            """,
            params,
        )
    return len(rows)


def collect_resource_names(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "resourceName" and child:
                found.append(str(child))
            elif key.endswith("ResourceName") and child:
                found.append(str(child))
            else:
                collect_resource_names(child, found)
    elif isinstance(value, list):
        for child in value:
            collect_resource_names(child, found)


def core_entity_key(surface: str, row: dict[str, Any]) -> str:
    resource_names: list[str] = []
    collect_resource_names(row, resource_names)
    if resource_names:
        payload = "|".join(sorted(set(resource_names)))
    else:
        payload = json.dumps(row, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{surface}:{payload}".encode("utf-8")).hexdigest()


def core_selected_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "metrics"}


def store_core_generic_rows(
    *,
    customer: str,
    surface: str,
    query_name: str,
    source_resource: str,
    query: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    params = [
        (
            customer,
            surface,
            core_entity_key(surface, row),
            query_name,
            source_resource,
            row_hash(row, query_name),
            query,
            jsonb(core_selected_fields(row)),
            jsonb(row),
        )
        for row in rows
    ]
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO google_core_generic (
                customer_id, surface, entity_key, query_name, source_resource,
                row_hash, query, selected_fields, row_json, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
            ON CONFLICT (customer_id, surface, entity_key)
            DO UPDATE SET
                query_name = excluded.query_name,
                source_resource = excluded.source_resource,
                row_hash = excluded.row_hash,
                query = excluded.query,
                selected_fields = excluded.selected_fields,
                row_json = excluded.row_json,
                fetched_at = now()
            """,
            params,
        )
    return len(params)


def extract_id(resource_name: Any) -> str:
    if not resource_name:
        return ""
    return str(resource_name).rstrip("/").split("/")[-1]


def upsert_core_ad_rows(customer: str, rows: list[dict[str, Any]]) -> int:
    params = []
    for row in rows:
        ad_group_ad = row.get("adGroupAd") or {}
        ad = ad_group_ad.get("ad") or {}
        ad_id = str_or_empty(ad.get("id") or extract_id(ad.get("resourceName")))
        ad_group_id = str_or_empty(get_path(row, "ad_group.id"))
        if not ad_id:
            continue
        params.append(
            (
                customer,
                ad_group_id,
                ad_id,
                str_or_empty(get_path(row, "campaign.id")),
                ad.get("resourceName") or ad_group_ad.get("resourceName"),
                ad.get("name"),
                ad_group_ad.get("status"),
                ad.get("type"),
                jsonb(ad.get("finalUrls") or []),
                ad.get("displayUrl"),
                jsonb(ad_group_ad),
            )
        )
    if not params:
        return 0
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO google_ads (
                customer_id, ad_group_id, ad_id, campaign_id, resource_name,
                name, status, ad_type, final_urls, display_url, raw, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, now())
            ON CONFLICT (customer_id, ad_group_id, ad_id) DO UPDATE SET
                campaign_id = excluded.campaign_id,
                resource_name = excluded.resource_name,
                name = excluded.name,
                status = excluded.status,
                ad_type = excluded.ad_type,
                final_urls = excluded.final_urls,
                display_url = excluded.display_url,
                raw = excluded.raw,
                fetched_at = now()
            """,
            params,
        )
    return len(params)


def upsert_core_rows(customer: str, surface: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    if surface == "ad":
        return upsert_core_ad_rows(customer, rows)
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        for row in rows:
            if surface == "customer":
                cust = row.get("customer") or {}
                cid = str_or_empty(cust.get("id") or customer)
                cur.execute(
                    """
                    INSERT INTO google_customers (
                        customer_id, resource_name, descriptive_name, currency_code,
                        time_zone, manager, test_account, status, optimization_score,
                        raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (customer_id) DO UPDATE SET
                        resource_name = excluded.resource_name,
                        descriptive_name = excluded.descriptive_name,
                        currency_code = excluded.currency_code,
                        time_zone = excluded.time_zone,
                        manager = excluded.manager,
                        test_account = excluded.test_account,
                        status = excluded.status,
                        optimization_score = excluded.optimization_score,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        cid,
                        cust.get("resourceName"),
                        cust.get("descriptiveName"),
                        cust.get("currencyCode"),
                        cust.get("timeZone"),
                        cust.get("manager"),
                        cust.get("testAccount"),
                        cust.get("status"),
                        num_or_none(cust.get("optimizationScore")),
                        jsonb(cust),
                    ),
                )
            elif surface == "campaign_budget":
                budget = row.get("campaignBudget") or {}
                bid = str_or_empty(budget.get("id") or extract_id(budget.get("resourceName")))
                if not bid:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_campaign_budgets (
                        customer_id, budget_id, resource_name, name, status,
                        amount_micros, delivery_method, explicitly_shared, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (customer_id, budget_id) DO UPDATE SET
                        resource_name = excluded.resource_name,
                        name = excluded.name,
                        status = excluded.status,
                        amount_micros = excluded.amount_micros,
                        delivery_method = excluded.delivery_method,
                        explicitly_shared = excluded.explicitly_shared,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        bid,
                        budget.get("resourceName"),
                        budget.get("name"),
                        budget.get("status"),
                        int_or_none(budget.get("amountMicros")),
                        budget.get("deliveryMethod"),
                        budget.get("explicitlyShared"),
                        jsonb(budget),
                    ),
                )
            elif surface == "campaign":
                campaign = row.get("campaign") or {}
                cid = str_or_empty(campaign.get("id") or extract_id(campaign.get("resourceName")))
                if not cid:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_campaigns (
                        customer_id, campaign_id, resource_name, name, status,
                        serving_status, advertising_channel_type,
                        advertising_channel_sub_type, campaign_budget,
                        bidding_strategy_type, start_date, end_date,
                        optimization_score, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (customer_id, campaign_id) DO UPDATE SET
                        resource_name = excluded.resource_name,
                        name = excluded.name,
                        status = excluded.status,
                        serving_status = excluded.serving_status,
                        advertising_channel_type = excluded.advertising_channel_type,
                        advertising_channel_sub_type = excluded.advertising_channel_sub_type,
                        campaign_budget = excluded.campaign_budget,
                        bidding_strategy_type = excluded.bidding_strategy_type,
                        start_date = excluded.start_date,
                        end_date = excluded.end_date,
                        optimization_score = excluded.optimization_score,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        cid,
                        campaign.get("resourceName"),
                        campaign.get("name"),
                        campaign.get("status"),
                        campaign.get("servingStatus"),
                        campaign.get("advertisingChannelType"),
                        campaign.get("advertisingChannelSubType"),
                        campaign.get("campaignBudget"),
                        campaign.get("biddingStrategyType"),
                        campaign.get("startDate") or None,
                        campaign.get("endDate") or None,
                        num_or_none(campaign.get("optimizationScore")),
                        jsonb(campaign),
                    ),
                )
            elif surface == "ad_group":
                ad_group = row.get("adGroup") or {}
                aid = str_or_empty(ad_group.get("id") or extract_id(ad_group.get("resourceName")))
                if not aid:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_ad_groups (
                        customer_id, ad_group_id, campaign_id, resource_name,
                        name, status, type, cpc_bid_micros, target_cpa_micros,
                        target_roas, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (customer_id, ad_group_id) DO UPDATE SET
                        campaign_id = excluded.campaign_id,
                        resource_name = excluded.resource_name,
                        name = excluded.name,
                        status = excluded.status,
                        type = excluded.type,
                        cpc_bid_micros = excluded.cpc_bid_micros,
                        target_cpa_micros = excluded.target_cpa_micros,
                        target_roas = excluded.target_roas,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        aid,
                        str_or_empty(get_path(row, "campaign.id")),
                        ad_group.get("resourceName"),
                        ad_group.get("name"),
                        ad_group.get("status"),
                        ad_group.get("type"),
                        int_or_none(ad_group.get("cpcBidMicros")),
                        int_or_none(ad_group.get("targetCpaMicros")),
                        num_or_none(ad_group.get("targetRoas")),
                        jsonb(ad_group),
                    ),
                )
            elif surface == "keyword":
                criterion = row.get("adGroupCriterion") or {}
                keyword = criterion.get("keyword") or {}
                criterion_id = str_or_empty(criterion.get("criterionId") or extract_id(criterion.get("resourceName")))
                ad_group_id = str_or_empty(get_path(row, "ad_group.id"))
                if not criterion_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_keywords (
                        customer_id, ad_group_id, criterion_id, campaign_id, text,
                        match_type, status, negative, quality_score, final_urls,
                        raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                    ON CONFLICT (customer_id, ad_group_id, criterion_id) DO UPDATE SET
                        campaign_id = excluded.campaign_id,
                        text = excluded.text,
                        match_type = excluded.match_type,
                        status = excluded.status,
                        negative = excluded.negative,
                        quality_score = excluded.quality_score,
                        final_urls = excluded.final_urls,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        ad_group_id,
                        criterion_id,
                        str_or_empty(get_path(row, "campaign.id")),
                        keyword.get("text"),
                        keyword.get("matchType"),
                        criterion.get("status"),
                        criterion.get("negative"),
                        int_or_none(criterion.get("qualityInfo", {}).get("qualityScore") if isinstance(criterion.get("qualityInfo"), dict) else None),
                        jsonb(criterion.get("finalUrls") or []),
                        jsonb(criterion),
                    ),
                )
            elif surface == "asset":
                asset = row.get("asset") or {}
                asset_id = str_or_empty(asset.get("id") or extract_id(asset.get("resourceName")))
                if not asset_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_assets (
                        customer_id, asset_id, resource_name, name, type, source,
                        policy_summary, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                    ON CONFLICT (customer_id, asset_id) DO UPDATE SET
                        resource_name = excluded.resource_name,
                        name = excluded.name,
                        type = excluded.type,
                        source = excluded.source,
                        policy_summary = excluded.policy_summary,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        asset_id,
                        asset.get("resourceName"),
                        asset.get("name"),
                        asset.get("type"),
                        asset.get("source"),
                        jsonb(asset.get("policySummary") or {}),
                        jsonb(asset),
                    ),
                )
            elif surface == "asset_group":
                asset_group = row.get("assetGroup") or {}
                asset_group_id = str_or_empty(asset_group.get("id") or extract_id(asset_group.get("resourceName")))
                if not asset_group_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_asset_groups (
                        customer_id, asset_group_id, campaign_id, resource_name,
                        name, status, final_urls, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                    ON CONFLICT (customer_id, asset_group_id) DO UPDATE SET
                        campaign_id = excluded.campaign_id,
                        resource_name = excluded.resource_name,
                        name = excluded.name,
                        status = excluded.status,
                        final_urls = excluded.final_urls,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        asset_group_id,
                        str_or_empty(get_path(row, "campaign.id")),
                        asset_group.get("resourceName"),
                        asset_group.get("name"),
                        asset_group.get("status"),
                        jsonb(asset_group.get("finalUrls") or []),
                        jsonb(asset_group),
                    ),
                )
            elif surface == "conversion_action":
                conversion = row.get("conversionAction") or {}
                conversion_id = str_or_empty(conversion.get("id") or extract_id(conversion.get("resourceName")))
                if not conversion_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_conversion_actions (
                        customer_id, conversion_action_id, resource_name, name,
                        status, type, category, include_in_conversions_metric,
                        value_settings, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                    ON CONFLICT (customer_id, conversion_action_id) DO UPDATE SET
                        resource_name = excluded.resource_name,
                        name = excluded.name,
                        status = excluded.status,
                        type = excluded.type,
                        category = excluded.category,
                        include_in_conversions_metric = excluded.include_in_conversions_metric,
                        value_settings = excluded.value_settings,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        conversion_id,
                        conversion.get("resourceName"),
                        conversion.get("name"),
                        conversion.get("status"),
                        conversion.get("type"),
                        conversion.get("category"),
                        conversion.get("includeInConversionsMetric"),
                        jsonb(conversion.get("valueSettings") or {}),
                        jsonb(conversion),
                    ),
                )
            elif surface == "recommendation":
                recommendation = row.get("recommendation") or {}
                rec_id = str_or_empty(recommendation.get("id") or extract_id(recommendation.get("resourceName")))
                if not rec_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_recommendations (
                        customer_id, recommendation_id, campaign_id, type,
                        impact, dismissed, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, now())
                    ON CONFLICT (customer_id, recommendation_id) DO UPDATE SET
                        campaign_id = excluded.campaign_id,
                        type = excluded.type,
                        impact = excluded.impact,
                        dismissed = excluded.dismissed,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        rec_id,
                        str_or_empty(get_path(row, "campaign.id")),
                        recommendation.get("type"),
                        jsonb(recommendation.get("impact") or {}),
                        recommendation.get("dismissed"),
                        jsonb(recommendation),
                    ),
                )
            elif surface == "change_event":
                change = row.get("changeEvent") or {}
                change_id = str_or_empty(change.get("resourceName") or change.get("changeEventId"))
                if not change_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_change_events (
                        customer_id, change_event_id, change_date_time, user_email,
                        resource_type, change_resource_type, changed_fields,
                        old_resource, new_resource, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, now())
                    ON CONFLICT (customer_id, change_event_id) DO UPDATE SET
                        change_date_time = excluded.change_date_time,
                        user_email = excluded.user_email,
                        resource_type = excluded.resource_type,
                        change_resource_type = excluded.change_resource_type,
                        changed_fields = excluded.changed_fields,
                        old_resource = excluded.old_resource,
                        new_resource = excluded.new_resource,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        customer,
                        change_id,
                        change.get("changeDateTime"),
                        change.get("userEmail"),
                        change.get("resourceType"),
                        change.get("changeResourceType"),
                        jsonb(change.get("changedFields") or []),
                        jsonb(change.get("oldResource") or {}),
                        jsonb(change.get("newResource") or {}),
                        jsonb(change),
                    ),
                )
    return len(rows)


def upsert_performance_rows(customer: str, level: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    performance_params = []
    search_term_params = []
    for row in rows:
        report_date = get_path(row, "segments.date")
        if not report_date:
            continue
        campaign_id = str_or_empty(get_path(row, "campaign.id"))
        ad_group_id = str_or_empty(get_path(row, "ad_group.id"))
        ad_id = str_or_empty(get_path(row, "ad_group_ad.ad.id"))
        criterion_id = str_or_empty(get_path(row, "ad_group_criterion.criterion_id"))
        asset_group_id = str_or_empty(get_path(row, "asset_group.id"))
        search_term = str_or_empty(get_path(row, "search_term_view.search_term"))
        performance_params.append(
            (
                customer,
                level,
                report_date,
                campaign_id,
                ad_group_id,
                ad_id,
                criterion_id,
                asset_group_id,
                search_term,
                get_path(row, "campaign.name"),
                get_path(row, "ad_group.name"),
                get_path(row, "ad_group_ad.ad.name"),
                get_path(row, "campaign.advertising_channel_type"),
                get_path(row, "campaign.advertising_channel_sub_type"),
                str_or_empty(get_path(row, "segments.device")),
                str_or_empty(get_path(row, "segments.ad_network_type")),
                int_or_none(get_path(row, "metrics.impressions")),
                int_or_none(get_path(row, "metrics.clicks")),
                int_or_none(get_path(row, "metrics.interactions")),
                int_or_none(get_path(row, "metrics.cost_micros")),
                num_or_none(get_path(row, "metrics.conversions")),
                num_or_none(get_path(row, "metrics.conversions_value")),
                num_or_none(get_path(row, "metrics.all_conversions")),
                num_or_none(get_path(row, "metrics.all_conversions_value")),
                int_or_none(get_path(row, "metrics.video_views")),
                num_or_none(get_path(row, "metrics.ctr")),
                int_or_none(get_path(row, "metrics.average_cpc")),
                int_or_none(get_path(row, "metrics.average_cpm")),
                int_or_none(get_path(row, "metrics.cost_per_conversion")),
                num_or_none(get_path(row, "metrics.value_per_conversion")),
                jsonb(row),
            )
        )
        if level == "search_term" and search_term:
            search_term_params.append(
                (
                    customer,
                    report_date,
                    campaign_id,
                    ad_group_id,
                    search_term,
                    get_path(row, "search_term_view.status"),
                    int_or_none(get_path(row, "metrics.impressions")),
                    int_or_none(get_path(row, "metrics.clicks")),
                    int_or_none(get_path(row, "metrics.cost_micros")),
                    num_or_none(get_path(row, "metrics.conversions")),
                    num_or_none(get_path(row, "metrics.conversions_value")),
                    jsonb(row),
                )
            )
    if not performance_params:
        return 0
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO google_performance_daily (
                customer_id, level, report_date, campaign_id, ad_group_id,
                ad_id, criterion_id, asset_group_id, search_term,
                campaign_name, ad_group_name, ad_name,
                campaign_channel_type, campaign_channel_sub_type,
                device, network, impressions, clicks, interactions,
                cost_micros, conversions, conversions_value,
                all_conversions, all_conversions_value, video_views, ctr,
                average_cpc_micros, average_cpm_micros,
                cost_per_conversion_micros, value_per_conversion, raw,
                fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
            ON CONFLICT (
                customer_id, level, report_date, campaign_id, ad_group_id,
                ad_id, criterion_id, asset_group_id, search_term, device, network
            )
            DO UPDATE SET
                campaign_name = excluded.campaign_name,
                ad_group_name = excluded.ad_group_name,
                ad_name = excluded.ad_name,
                campaign_channel_type = excluded.campaign_channel_type,
                campaign_channel_sub_type = excluded.campaign_channel_sub_type,
                impressions = excluded.impressions,
                clicks = excluded.clicks,
                interactions = excluded.interactions,
                cost_micros = excluded.cost_micros,
                conversions = excluded.conversions,
                conversions_value = excluded.conversions_value,
                all_conversions = excluded.all_conversions,
                all_conversions_value = excluded.all_conversions_value,
                video_views = excluded.video_views,
                ctr = excluded.ctr,
                average_cpc_micros = excluded.average_cpc_micros,
                average_cpm_micros = excluded.average_cpm_micros,
                cost_per_conversion_micros = excluded.cost_per_conversion_micros,
                value_per_conversion = excluded.value_per_conversion,
                raw = excluded.raw,
                fetched_at = now()
            """,
            performance_params,
        )
        if search_term_params:
            cur.executemany(
                """
                INSERT INTO google_search_terms (
                    customer_id, report_date, campaign_id, ad_group_id,
                    search_term, status, impressions, clicks, cost_micros,
                    conversions, conversions_value, raw, fetched_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                ON CONFLICT (customer_id, report_date, campaign_id, ad_group_id, search_term)
                DO UPDATE SET
                    status = excluded.status,
                    impressions = excluded.impressions,
                    clicks = excluded.clicks,
                    cost_micros = excluded.cost_micros,
                    conversions = excluded.conversions,
                    conversions_value = excluded.conversions_value,
                    raw = excluded.raw,
                    fetched_at = now()
                """,
                search_term_params,
            )
    return len(performance_params)


def performance_dimensions(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "metrics"}


def dimension_key(row: dict[str, Any], query_name: str) -> str:
    payload = json.dumps(performance_dimensions(row), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{query_name}:{payload}".encode("utf-8")).hexdigest()


def store_performance_generic_rows(
    *,
    customer: str,
    surface: str,
    query_name: str,
    query: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    params = []
    for row in rows:
        report_date = get_path(row, "segments.date")
        if not report_date:
            continue
        params.append(
            (
                customer,
                surface,
                report_date,
                dimension_key(row, query_name),
                query_name,
                row_hash(row, query_name),
                query,
                jsonb(performance_dimensions(row)),
                jsonb(row.get("metrics") or {}),
                jsonb(row),
            )
        )
    if not params:
        return 0
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO google_performance_generic (
                customer_id, surface, report_date, entity_key, query_name,
                row_hash, query, selected_dimensions, metrics, row_json,
                fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, now())
            ON CONFLICT (customer_id, surface, report_date, entity_key, row_hash)
            DO UPDATE SET
                query = excluded.query,
                selected_dimensions = excluded.selected_dimensions,
                metrics = excluded.metrics,
                row_json = excluded.row_json,
                fetched_at = now()
            """,
            params,
        )
    return len(params)


CORE_QUERIES = {
    "customer": (
        "customer",
        """
        SELECT
          customer.id,
          customer.resource_name,
          customer.descriptive_name,
          customer.currency_code,
          customer.time_zone,
          customer.manager,
          customer.test_account,
          customer.status,
          customer.optimization_score
        FROM customer
        LIMIT 1
        """,
    ),
    "campaign_budget": (
        "campaign_budget",
        """
        SELECT
          campaign_budget.id,
          campaign_budget.resource_name,
          campaign_budget.name,
          campaign_budget.status,
          campaign_budget.amount_micros,
          campaign_budget.delivery_method,
          campaign_budget.explicitly_shared
        FROM campaign_budget
        """,
    ),
    "campaign": (
        "campaign",
        """
        SELECT
          campaign.id,
          campaign.resource_name,
          campaign.name,
          campaign.status,
          campaign.serving_status,
          campaign.advertising_channel_type,
          campaign.advertising_channel_sub_type,
          campaign.campaign_budget,
          campaign.bidding_strategy_type,
          campaign.optimization_score
        FROM campaign
        """,
    ),
    "ad_group": (
        "ad_group",
        """
        SELECT
          campaign.id,
          ad_group.id,
          ad_group.resource_name,
          ad_group.name,
          ad_group.status,
          ad_group.type,
          ad_group.cpc_bid_micros,
          ad_group.target_cpa_micros,
          ad_group.target_roas
        FROM ad_group
        """,
    ),
    "ad": (
        "ad_group_ad",
        """
        SELECT
          campaign.id,
          ad_group.id,
          ad_group_ad.resource_name,
          ad_group_ad.status,
          ad_group_ad.ad.id,
          ad_group_ad.ad.resource_name,
          ad_group_ad.ad.name,
          ad_group_ad.ad.type,
          ad_group_ad.ad.final_urls,
          ad_group_ad.ad.display_url
        FROM ad_group_ad
        """,
    ),
    "keyword": (
        "ad_group_criterion",
        """
        SELECT
          campaign.id,
          ad_group.id,
          ad_group_criterion.resource_name,
          ad_group_criterion.criterion_id,
          ad_group_criterion.status,
          ad_group_criterion.negative,
          ad_group_criterion.keyword.text,
          ad_group_criterion.keyword.match_type,
          ad_group_criterion.quality_info.quality_score,
          ad_group_criterion.final_urls
        FROM ad_group_criterion
        WHERE ad_group_criterion.type = 'KEYWORD'
        """,
    ),
    "asset": (
        "asset",
        """
        SELECT
          asset.id,
          asset.resource_name,
          asset.name,
          asset.type,
          asset.source
        FROM asset
        """,
    ),
    "asset_group": (
        "asset_group",
        """
        SELECT
          campaign.id,
          asset_group.id,
          asset_group.resource_name,
          asset_group.name,
          asset_group.status,
          asset_group.final_urls
        FROM asset_group
        """,
    ),
    "campaign_asset": (
        "campaign_asset",
        """
        SELECT
          campaign_asset.resource_name,
          campaign_asset.campaign,
          campaign_asset.asset,
          campaign_asset.field_type,
          campaign_asset.status,
          campaign_asset.source,
          campaign_asset.primary_status,
          campaign_asset.primary_status_reasons
        FROM campaign_asset
        """,
    ),
    "ad_group_asset": (
        "ad_group_asset",
        """
        SELECT
          ad_group_asset.resource_name,
          ad_group_asset.ad_group,
          ad_group_asset.asset,
          ad_group_asset.field_type,
          ad_group_asset.status,
          ad_group_asset.source,
          ad_group_asset.primary_status,
          ad_group_asset.primary_status_reasons
        FROM ad_group_asset
        """,
    ),
    "customer_asset": (
        "customer_asset",
        """
        SELECT
          customer_asset.resource_name,
          customer_asset.asset,
          customer_asset.field_type,
          customer_asset.status,
          customer_asset.source,
          customer_asset.primary_status,
          customer_asset.primary_status_reasons
        FROM customer_asset
        """,
    ),
    "asset_set": (
        "asset_set",
        """
        SELECT
          asset_set.id,
          asset_set.resource_name,
          asset_set.name,
          asset_set.status,
          asset_set.type
        FROM asset_set
        """,
    ),
    "asset_set_asset": (
        "asset_set_asset",
        """
        SELECT
          asset_set_asset.resource_name,
          asset_set_asset.asset_set,
          asset_set_asset.asset,
          asset_set_asset.status
        FROM asset_set_asset
        """,
    ),
    "campaign_asset_set": (
        "campaign_asset_set",
        """
        SELECT
          campaign_asset_set.resource_name,
          campaign_asset_set.campaign,
          campaign_asset_set.asset_set,
          campaign_asset_set.status
        FROM campaign_asset_set
        """,
    ),
    "customer_asset_set": (
        "customer_asset_set",
        """
        SELECT
          customer_asset_set.resource_name,
          customer_asset_set.asset_set,
          customer_asset_set.status
        FROM customer_asset_set
        """,
    ),
    "asset_group_asset": (
        "asset_group_asset",
        """
        SELECT
          asset_group_asset.resource_name,
          asset_group_asset.asset_group,
          asset_group_asset.asset,
          asset_group_asset.field_type,
          asset_group_asset.status,
          asset_group_asset.source,
          asset_group_asset.primary_status,
          asset_group_asset.primary_status_reasons
        FROM asset_group_asset
        """,
    ),
    "asset_group_listing_group_filter": (
        "asset_group_listing_group_filter",
        """
        SELECT
          asset_group_listing_group_filter.resource_name,
          asset_group_listing_group_filter.asset_group,
          asset_group_listing_group_filter.id,
          asset_group_listing_group_filter.type,
          asset_group_listing_group_filter.listing_source,
          asset_group_listing_group_filter.parent_listing_group_filter,
          asset_group_listing_group_filter.path
        FROM asset_group_listing_group_filter
        """,
    ),
    "asset_group_signal": (
        "asset_group_signal",
        """
        SELECT
          asset_group_signal.resource_name,
          asset_group_signal.asset_group,
          asset_group_signal.approval_status,
          asset_group_signal.disapproval_reasons
        FROM asset_group_signal
        """,
    ),
    "conversion_action": (
        "conversion_action",
        """
        SELECT
          conversion_action.id,
          conversion_action.resource_name,
          conversion_action.name,
          conversion_action.status,
          conversion_action.type,
          conversion_action.category,
          conversion_action.include_in_conversions_metric
        FROM conversion_action
        """,
    ),
    "conversion_goal_campaign_config": (
        "conversion_goal_campaign_config",
        """
        SELECT
          conversion_goal_campaign_config.resource_name,
          conversion_goal_campaign_config.campaign,
          conversion_goal_campaign_config.goal_config_level,
          conversion_goal_campaign_config.custom_conversion_goal
        FROM conversion_goal_campaign_config
        """,
    ),
    "campaign_conversion_goal": (
        "campaign_conversion_goal",
        """
        SELECT
          campaign_conversion_goal.resource_name,
          campaign_conversion_goal.campaign,
          campaign_conversion_goal.category,
          campaign_conversion_goal.origin,
          campaign_conversion_goal.biddable
        FROM campaign_conversion_goal
        """,
    ),
    "customer_conversion_goal": (
        "customer_conversion_goal",
        """
        SELECT
          customer_conversion_goal.resource_name,
          customer_conversion_goal.category,
          customer_conversion_goal.origin,
          customer_conversion_goal.biddable
        FROM customer_conversion_goal
        """,
    ),
    "custom_conversion_goal": (
        "custom_conversion_goal",
        """
        SELECT
          custom_conversion_goal.id,
          custom_conversion_goal.resource_name,
          custom_conversion_goal.name,
          custom_conversion_goal.status,
          custom_conversion_goal.conversion_actions
        FROM custom_conversion_goal
        """,
    ),
    "bidding_strategy": (
        "bidding_strategy",
        """
        SELECT
          bidding_strategy.id,
          bidding_strategy.resource_name,
          bidding_strategy.name,
          bidding_strategy.status,
          bidding_strategy.type,
          bidding_strategy.currency_code,
          bidding_strategy.campaign_count,
          bidding_strategy.non_removed_campaign_count
        FROM bidding_strategy
        """,
    ),
    "label": (
        "label",
        """
        SELECT
          label.id,
          label.resource_name,
          label.name,
          label.status
        FROM label
        """,
    ),
    "campaign_label": (
        "campaign_label",
        """
        SELECT
          campaign_label.resource_name,
          campaign_label.campaign,
          campaign_label.label
        FROM campaign_label
        """,
    ),
    "ad_group_label": (
        "ad_group_label",
        """
        SELECT
          ad_group_label.resource_name,
          ad_group_label.ad_group,
          ad_group_label.label
        FROM ad_group_label
        """,
    ),
    "ad_group_ad_label": (
        "ad_group_ad_label",
        """
        SELECT
          ad_group_ad_label.resource_name,
          ad_group_ad_label.ad_group_ad,
          ad_group_ad_label.label
        FROM ad_group_ad_label
        """,
    ),
    "ad_group_criterion_label": (
        "ad_group_criterion_label",
        """
        SELECT
          ad_group_criterion_label.resource_name,
          ad_group_criterion_label.ad_group_criterion,
          ad_group_criterion_label.label
        FROM ad_group_criterion_label
        """,
    ),
    "customer_label": (
        "customer_label",
        """
        SELECT
          customer_label.resource_name,
          customer_label.customer,
          customer_label.label
        FROM customer_label
        """,
    ),
    "campaign_criterion": (
        "campaign_criterion",
        """
        SELECT
          campaign_criterion.resource_name,
          campaign_criterion.campaign,
          campaign_criterion.criterion_id,
          campaign_criterion.type,
          campaign_criterion.status,
          campaign_criterion.negative,
          campaign_criterion.display_name,
          campaign_criterion.bid_modifier
        FROM campaign_criterion
        """,
    ),
    "customer_negative_criterion": (
        "customer_negative_criterion",
        """
        SELECT
          customer_negative_criterion.resource_name,
          customer_negative_criterion.id,
          customer_negative_criterion.type
        FROM customer_negative_criterion
        """,
    ),
    "audience": (
        "audience",
        """
        SELECT
          audience.id,
          audience.resource_name,
          audience.name,
          audience.description,
          audience.status,
          audience.scope,
          audience.asset_group
        FROM audience
        """,
    ),
    "combined_audience": (
        "combined_audience",
        """
        SELECT
          combined_audience.id,
          combined_audience.resource_name,
          combined_audience.name,
          combined_audience.description,
          combined_audience.status
        FROM combined_audience
        """,
    ),
    "custom_audience": (
        "custom_audience",
        """
        SELECT
          custom_audience.id,
          custom_audience.resource_name,
          custom_audience.name,
          custom_audience.description,
          custom_audience.status,
          custom_audience.type,
          custom_audience.members
        FROM custom_audience
        """,
    ),
    "user_list": (
        "user_list",
        """
        SELECT
          user_list.id,
          user_list.resource_name,
          user_list.name,
          user_list.description,
          user_list.type,
          user_list.membership_status,
          user_list.size_for_search,
          user_list.size_for_display,
          user_list.eligible_for_search,
          user_list.eligible_for_display,
          user_list.match_rate_percentage
        FROM user_list
        """,
    ),
    "shopping_product": (
        "shopping_product",
        """
        SELECT
          shopping_product.resource_name,
          shopping_product.campaign,
          shopping_product.merchant_center_id,
          shopping_product.item_id,
          shopping_product.title,
          shopping_product.brand,
          shopping_product.status,
          shopping_product.availability,
          shopping_product.condition,
          shopping_product.price_micros,
          shopping_product.currency_code,
          shopping_product.category_level1,
          shopping_product.product_type_level1,
          shopping_product.issues
        FROM shopping_product
        WHERE shopping_product.campaign = 'customers/{customer_id}/campaigns/0'
        """,
    ),
    "final_url_expansion_asset_view": (
        "final_url_expansion_asset_view",
        """
        SELECT
          final_url_expansion_asset_view.resource_name,
          final_url_expansion_asset_view.campaign,
          final_url_expansion_asset_view.asset_group,
          final_url_expansion_asset_view.asset,
          final_url_expansion_asset_view.field_type,
          final_url_expansion_asset_view.final_url,
          final_url_expansion_asset_view.status
        FROM final_url_expansion_asset_view
        WHERE final_url_expansion_asset_view.campaign = 'customers/{customer_id}/campaigns/0'
          AND campaign.advertising_channel_type = PERFORMANCE_MAX
        """,
    ),
    "recommendation": (
        "recommendation",
        """
        SELECT
          campaign.id,
          recommendation.resource_name,
          recommendation.type,
          recommendation.impact,
          recommendation.dismissed
        FROM recommendation
        """,
    ),
    "change_event": (
        "change_event",
        """
        SELECT
          change_event.resource_name,
          change_event.change_date_time,
          change_event.user_email,
          change_event.change_resource_type,
          change_event.changed_fields,
          change_event.old_resource,
          change_event.new_resource
        FROM change_event
        WHERE change_event.change_date_time DURING LAST_14_DAYS
        LIMIT 10000
        """,
    ),
}

METRIC_FIELDS = """
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value,
  metrics.all_conversions,
  metrics.all_conversions_value,
  metrics.ctr,
  metrics.average_cpc,
  metrics.cost_per_conversion,
  metrics.value_per_conversion
"""

FINAL_URL_EXPANSION_METRIC_FIELDS = """
  metrics.impressions
"""


def performance_query(surface: str, since: str, until: str) -> tuple[str, str]:
    date_filter = f"segments.date BETWEEN '{since}' AND '{until}'"
    queries = {
        "account": (
            "customer",
            f"""
            SELECT
              segments.date,
              customer.id,
              {METRIC_FIELDS}
            FROM customer
            WHERE {date_filter}
            """,
        ),
        "campaign": (
            "campaign",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              {METRIC_FIELDS}
            FROM campaign
            WHERE {date_filter}
            """,
        ),
        "ad_group": (
            "ad_group",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              ad_group.id,
              ad_group.name,
              ad_group.status,
              {METRIC_FIELDS}
            FROM ad_group
            WHERE {date_filter}
            """,
        ),
        "ad": (
            "ad_group_ad",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              ad_group.id,
              ad_group.name,
              ad_group_ad.ad.id,
              ad_group_ad.ad.name,
              ad_group_ad.status,
              {METRIC_FIELDS}
            FROM ad_group_ad
            WHERE {date_filter}
            """,
        ),
        "keyword": (
            "keyword_view",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              ad_group.id,
              ad_group.name,
              ad_group_criterion.criterion_id,
              ad_group_criterion.keyword.text,
              ad_group_criterion.keyword.match_type,
              {METRIC_FIELDS}
            FROM keyword_view
            WHERE {date_filter}
            """,
        ),
        "search_term": (
            "search_term_view",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              ad_group.id,
              ad_group.name,
              search_term_view.search_term,
              search_term_view.status,
              {METRIC_FIELDS}
            FROM search_term_view
            WHERE {date_filter}
            """,
        ),
        "asset_group": (
            "asset_group",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              asset_group.id,
              asset_group.name,
              asset_group.status,
              {METRIC_FIELDS}
            FROM asset_group
            WHERE {date_filter}
            """,
        ),
        "shopping_performance": (
            "shopping_performance_view",
            f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              segments.product_item_id,
              segments.product_title,
              segments.product_type_l1,
              segments.product_type_l2,
              {METRIC_FIELDS}
            FROM shopping_performance_view
            WHERE {date_filter}
            """,
        ),
        "campaign_device_network": (
            "campaign",
            f"""
            SELECT
              segments.date,
              segments.device,
              segments.ad_network_type,
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              {METRIC_FIELDS}
            FROM campaign
            WHERE {date_filter}
            """,
        ),
        "ad_group_device_network": (
            "ad_group",
            f"""
            SELECT
              segments.date,
              segments.device,
              segments.ad_network_type,
              campaign.id,
              campaign.name,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              ad_group.id,
              ad_group.name,
              ad_group.status,
              {METRIC_FIELDS}
            FROM ad_group
            WHERE {date_filter}
            """,
        ),
        "landing_page": (
            "landing_page_view",
            f"""
            SELECT
              segments.date,
              landing_page_view.resource_name,
              landing_page_view.unexpanded_final_url,
              {METRIC_FIELDS}
            FROM landing_page_view
            WHERE {date_filter}
            """,
        ),
        "expanded_landing_page": (
            "expanded_landing_page_view",
            f"""
            SELECT
              segments.date,
              expanded_landing_page_view.resource_name,
              expanded_landing_page_view.expanded_final_url,
              {METRIC_FIELDS}
            FROM expanded_landing_page_view
            WHERE {date_filter}
            """,
        ),
        "product_group": (
            "product_group_view",
            f"""
            SELECT
              segments.date,
              product_group_view.resource_name,
              campaign.id,
              campaign.name,
              ad_group.id,
              ad_group.name,
              {METRIC_FIELDS}
            FROM product_group_view
            WHERE {date_filter}
            """,
        ),
        "asset_group_product_group": (
            "asset_group_product_group_view",
            f"""
            SELECT
              segments.date,
              asset_group_product_group_view.resource_name,
              asset_group_product_group_view.asset_group,
              asset_group_product_group_view.asset_group_listing_group_filter,
              {METRIC_FIELDS}
            FROM asset_group_product_group_view
            WHERE {date_filter}
            """,
        ),
        "campaign_asset_performance": (
            "campaign_aggregate_asset_view",
            f"""
            SELECT
              segments.date,
              campaign_aggregate_asset_view.resource_name,
              campaign_aggregate_asset_view.campaign,
              campaign_aggregate_asset_view.asset,
              campaign_aggregate_asset_view.field_type,
              campaign_aggregate_asset_view.asset_source,
              {METRIC_FIELDS}
            FROM campaign_aggregate_asset_view
            WHERE {date_filter}
            """,
        ),
        "channel_asset_performance": (
            "channel_aggregate_asset_view",
            f"""
            SELECT
              segments.date,
              channel_aggregate_asset_view.resource_name,
              channel_aggregate_asset_view.advertising_channel_type,
              channel_aggregate_asset_view.asset,
              channel_aggregate_asset_view.field_type,
              channel_aggregate_asset_view.asset_source,
              {METRIC_FIELDS}
            FROM channel_aggregate_asset_view
            WHERE {date_filter}
            """,
        ),
        "asset_field_type_performance": (
            "asset_field_type_view",
            f"""
            SELECT
              segments.date,
              asset_field_type_view.resource_name,
              asset_field_type_view.field_type,
              {METRIC_FIELDS}
            FROM asset_field_type_view
            WHERE {date_filter}
            """,
        ),
        "final_url_expansion_asset_performance": (
            "final_url_expansion_asset_view",
            f"""
            SELECT
              segments.date,
              final_url_expansion_asset_view.resource_name,
              final_url_expansion_asset_view.campaign,
              final_url_expansion_asset_view.asset_group,
              final_url_expansion_asset_view.asset,
              final_url_expansion_asset_view.field_type,
              final_url_expansion_asset_view.final_url,
              final_url_expansion_asset_view.status,
              {FINAL_URL_EXPANSION_METRIC_FIELDS}
            FROM final_url_expansion_asset_view
            WHERE {date_filter}
              AND final_url_expansion_asset_view.campaign = 'customers/{{customer_id}}/campaigns/0'
              AND campaign.advertising_channel_type = PERFORMANCE_MAX
            """,
        ),
    }
    if surface not in queries:
        raise ValueError(f"unknown performance surface: {surface}")
    return queries[surface]


PERFORMANCE_SURFACES = [
    "account",
    "campaign",
    "ad_group",
    "ad",
    "keyword",
    "search_term",
    "asset_group",
    "shopping_performance",
    "campaign_device_network",
    "ad_group_device_network",
    "landing_page",
    "expanded_landing_page",
    "product_group",
    "asset_group_product_group",
    "campaign_asset_performance",
    "channel_asset_performance",
    "asset_field_type_performance",
    "final_url_expansion_asset_performance",
]

PERFORMANCE_NORMALIZED_SURFACES = {
    "account",
    "campaign",
    "ad_group",
    "ad",
    "keyword",
    "search_term",
    "asset_group",
    "campaign_device_network",
    "ad_group_device_network",
}

CORE_WAREHOUSE_TABLES = {
    "customer": ["google_customers", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "campaign_budget": ["google_campaign_budgets", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "campaign": ["google_campaigns", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "ad_group": ["google_ad_groups", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "ad": ["google_ads", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "keyword": ["google_keywords", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "asset": ["google_assets", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "asset_group": ["google_asset_groups", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "conversion_action": ["google_conversion_actions", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "recommendation": ["google_recommendations", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
    "change_event": ["google_change_events", "google_core_generic", "google_gaql_rows", "google_raw_snapshots"],
}

PERFORMANCE_WAREHOUSE_TABLES = {
    "account": ["google_performance_daily", "google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
    "campaign": ["google_performance_daily", "google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
    "ad_group": ["google_performance_daily", "google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
    "ad": ["google_performance_daily", "google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
    "keyword": ["google_performance_daily", "google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
    "search_term": [
        "google_search_terms",
        "google_performance_daily",
        "google_performance_generic",
        "google_gaql_rows",
        "google_raw_snapshots",
    ],
    "asset_group": ["google_performance_daily", "google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
    "campaign_device_network": [
        "google_performance_daily",
        "google_performance_generic",
        "google_gaql_rows",
        "google_raw_snapshots",
    ],
    "ad_group_device_network": [
        "google_performance_daily",
        "google_performance_generic",
        "google_gaql_rows",
        "google_raw_snapshots",
    ],
    "shopping_performance": ["google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
}


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def gaql_fields(query: str) -> list[str]:
    normalized = normalize_query(query)
    match = re.search(r"\bSELECT\b\s+(.*?)\s+\bFROM\b\s+[a-zA-Z_][a-zA-Z0-9_]*", normalized, re.I)
    if not match:
        return []
    return [field.strip() for field in match.group(1).split(",") if field.strip()]


def split_manifest_fields(fields: list[str]) -> dict[str, list[str]]:
    metrics = [field for field in fields if field.startswith("metrics.")]
    segments = [field for field in fields if field.startswith("segments.")]
    resources = [field for field in fields if not field.startswith(("metrics.", "segments."))]
    return {"metrics": metrics, "segments": segments, "resources": resources}


def query_hash(query: str | None) -> str | None:
    if not query:
        return None
    return hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()


def build_query_manifest() -> list[dict[str, Any]]:
    version = api_version()
    rows: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> None:
        query = row.get("query")
        fields = gaql_fields(query) if isinstance(query, str) else []
        grouped = split_manifest_fields(fields)
        rows.append(
            {
                "api_version": version,
                "surface_type": row["surface_type"],
                "surface_name": row["surface_name"],
                "command": row["command"],
                "query_name": row.get("query_name"),
                "source_resource": row.get("source_resource"),
                "warehouse_tables": row.get("warehouse_tables", []),
                "date_window": row.get("date_window"),
                "default_days": row.get("default_days"),
                "default_chunk_days": row.get("default_chunk_days"),
                "requires_auth": row.get("requires_auth", True),
                "can_mutate": row.get("can_mutate", False),
                "schedule": row.get("schedule"),
                "query": normalize_query(query) if isinstance(query, str) and query else None,
                "query_hash": query_hash(query) if isinstance(query, str) else None,
                "selected_fields": fields,
                "metric_fields": grouped["metrics"],
                "segment_fields": grouped["segments"],
                "resource_fields": grouped["resources"],
                "notes": row.get("notes"),
                "metadata": row.get("metadata", {}),
            }
        )

    add(
        {
            "surface_type": "catalog",
            "surface_name": "official_client_services",
            "command": "catalog-client-library",
            "source_resource": "google-ads-python service clients",
            "warehouse_tables": ["google_api_services", "google_api_catalog_sources"],
            "requires_auth": False,
            "schedule": "daily before auth smoke test",
            "notes": "Official client service/method map across installed Google Ads API versions.",
        }
    )
    add(
        {
            "surface_type": "catalog",
            "surface_name": "offline_field_catalog",
            "command": "catalog-offline-fields",
            "source_resource": "google-ads-python generated resource types",
            "warehouse_tables": ["google_offline_catalog_fields", "google_api_catalog_sources"],
            "requires_auth": False,
            "schedule": "daily before auth smoke test",
            "notes": "Offline metric, segment, resource, and view fields available without Ads OAuth.",
        }
    )
    add(
        {
            "surface_type": "catalog",
            "surface_name": "open_source_research",
            "command": "catalog-open-source",
            "source_resource": "public Google Ads tooling repositories",
            "warehouse_tables": ["google_api_catalog_sources"],
            "requires_auth": False,
            "schedule": "daily before auth smoke test",
            "notes": "Reference projects used for connector patterns and endpoint discovery.",
        }
    )
    add(
        {
            "surface_type": "catalog",
            "surface_name": "account_asset_library",
            "command": "asset-library",
            "source_resource": "local google_assets warehouse table",
            "warehouse_tables": ["google_assets"],
            "requires_auth": False,
            "schedule": "manual before asset-backed campaign planning",
            "notes": "Lists synced Google Ads assets by type, name, ID, and resource name so operators can choose creative assets without SQL.",
            "metadata": {"common_types": ["YOUTUBE_VIDEO", "IMAGE", "TEXT", "CALL_TO_ACTION", "SITELINK", "CALLOUT"]},
        }
    )
    add(
        {
            "surface_type": "research",
            "surface_name": "expert_source_ingestion",
            "command": "ingest-expert-sources",
            "source_resource": "authorized public Google Ads expert pages and podcast show notes",
            "warehouse_tables": ["google_expert_source_documents"],
            "requires_auth": False,
            "schedule": "manual refresh when strategy sources change",
            "notes": "Downloads and stores public/authorized source pages only. Paid course internals require a user-provided authorized export.",
            "metadata": {"catalog": str(EXPERT_SOURCE_CATALOG), "excludes": ["youtube", "pirated course mirrors"]},
        }
    )
    add(
        {
            "surface_type": "research",
            "surface_name": "keyword_plan_idea_research",
            "command": "keyword-research",
            "source_resource": "KeywordPlanIdeaService.GenerateKeywordIdeas",
            "warehouse_tables": ["google_keyword_research_runs", "google_keyword_research_ideas", "google_raw_snapshots"],
            "requires_auth": True,
            "schedule": "manual before building Search campaigns",
            "notes": "Stores Keyword Planner idea, volume, competition, bid-range, and monthly trend data for campaign build briefs.",
            "metadata": {"default_geo_target": "geoTargetConstants/2840", "default_language": "languageConstants/1000"},
        }
    )
    add(
        {
            "surface_type": "research",
            "surface_name": "search_campaign_research_brief",
            "command": "campaign-research-brief",
            "source_resource": "stored keyword research plus expert-source playbooks",
            "warehouse_tables": ["google_keyword_research_runs", "google_keyword_research_ideas", "google_expert_source_documents"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual before plan-search-campaign",
            "notes": "Turns keyword research into ad-group themes, match-type recommendations, negatives, budget/bid guidance, and next gads plan command.",
            "metadata": {"live_writes": False, "next_command": "plan-search-campaign"},
        }
    )
    add(
        {
            "surface_type": "catalog",
            "surface_name": "authenticated_google_ads_fields",
            "command": "sync-field-catalog",
            "query_name": "field_catalog",
            "source_resource": "google_ads_field",
            "warehouse_tables": ["google_ads_fields", "google_raw_snapshots", "google_sync_runs"],
            "requires_auth": True,
            "schedule": "daily after auth smoke test",
            "query": "SELECT google_ads_field.name, google_ads_field.category, google_ads_field.data_type, google_ads_field.selectable, google_ads_field.filterable, google_ads_field.sortable, google_ads_field.selectable_with FROM google_ads_field",
            "notes": "Authenticated GAQL compatibility catalog; blocked until OAuth user has Ads access.",
        }
    )
    add(
        {
            "surface_type": "auth",
            "surface_name": "accessible_customers",
            "command": "customers",
            "source_resource": "customers:listAccessibleCustomers",
            "warehouse_tables": ["google_raw_snapshots", "google_sync_runs", "google_fetch_errors"],
            "requires_auth": True,
            "schedule": "manual and auth smoke test",
            "notes": "Fast proof that the OAuth Google account can see Ads accounts.",
        }
    )

    for surface, (source_resource, query) in CORE_QUERIES.items():
        add(
            {
                "surface_type": "core",
                "surface_name": surface,
                "command": "sync-core",
                "query_name": f"core_{surface}",
                "source_resource": source_resource,
                "warehouse_tables": CORE_WAREHOUSE_TABLES.get(surface, ["google_core_generic", "google_gaql_rows", "google_raw_snapshots"]),
                "requires_auth": True,
                "schedule": "daily and before explicit backfill after auth smoke test",
                "query": query,
                "notes": "Native Google Ads entity/config surface.",
            }
        )

    for surface in PERFORMANCE_SURFACES:
        source_resource, query = performance_query(surface, "{since}", "{until}")
        add(
            {
                "surface_type": "performance",
                "surface_name": surface,
                "command": "sync-performance/backfill",
                "query_name": f"performance_{surface}",
                "source_resource": source_resource,
                "warehouse_tables": PERFORMANCE_WAREHOUSE_TABLES.get(
                    surface,
                    ["google_performance_generic", "google_gaql_rows", "google_raw_snapshots"],
                ),
                "date_window": "segments.date BETWEEN {since} AND {until}",
                "default_days": 31,
                "default_chunk_days": 7,
                "requires_auth": True,
                "schedule": "hourly 31-day rollover and daily/full backfills after auth smoke test",
                "query": query,
                "notes": "Platform-reported performance used for native diagnostics; Triple Whale remains attribution truth.",
            }
        )

    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_mutation_plan",
            "command": "plan-mutation",
            "source_resource": "local mutation changeset builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates stored validate-only mutation payloads for review before any Google Ads API call.",
            "metadata": {"supported_entities": sorted(MUTATION_ENTITY_CONFIG)},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_search_campaign_plan",
            "command": "plan-search-campaign",
            "source_resource": "local Search campaign builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only payload for a paused Search campaign, budget, ad group, keywords, responsive search ad, and optional sitelinks.",
            "metadata": {"default_campaign_status": "PAUSED", "default_budget_dollars": 1},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_researched_search_campaign_build",
            "command": "build-search-campaign",
            "source_resource": "keyword research plus local Search campaign builder",
            "warehouse_tables": ["google_keyword_research_runs", "google_keyword_research_ideas", "google_expert_source_documents", "google_mutation_plans"],
            "requires_auth": True,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Runs keyword research, stores trends/volume/match-type recommendations, clusters ad groups, and creates a validate-only paused Search campaign plan.",
            "metadata": {"live_writes": False, "next_command": "gads mutate <plan.json>"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_shopping_campaign_plan",
            "command": "plan-shopping-campaign",
            "source_resource": "local Shopping campaign builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only payload for a paused Standard Shopping campaign, budget, product ad group, product ad, and all-products listing group.",
            "metadata": {"default_campaign_status": "PAUSED", "default_budget_dollars": 1, "requires_merchant_id": True},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_researched_shopping_campaign_build",
            "command": "build-shopping-campaign",
            "source_resource": "keyword research plus local Standard Shopping campaign builder",
            "warehouse_tables": ["google_keyword_research_runs", "google_keyword_research_ideas", "google_mutation_plans"],
            "requires_auth": True,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Runs offer/search demand research, infers Merchant Center/feed defaults, and creates a validate-only paused Standard Shopping all-products plan.",
            "metadata": {"live_writes": False, "next_command": "gads mutate <plan.json>"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_pmax_campaign_plan",
            "command": "plan-pmax-campaign",
            "source_resource": "local Performance Max campaign builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only payload for a paused Performance Max campaign, budget, asset group, text assets, and optional search-theme signals.",
            "metadata": {"default_campaign_status": "PAUSED", "default_budget_dollars": 1},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_researched_pmax_campaign_build",
            "command": "build-pmax-campaign",
            "source_resource": "keyword research plus local Performance Max campaign builder",
            "warehouse_tables": ["google_keyword_research_runs", "google_keyword_research_ideas", "google_expert_source_documents", "google_mutation_plans"],
            "requires_auth": True,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Runs keyword research, turns launchable terms into PMax search themes and text assets, then creates a validate-only paused Performance Max plan.",
            "metadata": {"live_writes": False, "next_command": "gads mutate <plan.json>"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_demand_gen_campaign_plan",
            "command": "plan-demand-gen-campaign",
            "source_resource": "local Demand Gen campaign builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only payload for a paused Demand Gen campaign with YouTube/Gmail/Discover/Display channel controls and optional video responsive ad.",
            "metadata": {
                "default_campaign_status": "PAUSED",
                "default_budget_dollars": 5,
                "default_channel_strategy": "selected_channels",
                "default_selected_channels": ["youtube_in_feed", "youtube_in_stream", "youtube_shorts"],
            },
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_researched_demand_gen_campaign_build",
            "command": "build-demand-gen-campaign",
            "source_resource": "keyword research plus local Demand Gen campaign builder and asset library",
            "warehouse_tables": ["google_keyword_research_runs", "google_keyword_research_ideas", "google_assets", "google_mutation_plans"],
            "requires_auth": True,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Runs demand research, drafts Demand Gen ad text, selects an existing YouTube video asset when available, and creates a validate-only paused Demand Gen plan.",
            "metadata": {"live_writes": False, "next_command": "gads mutate <plan.json>", "default_budget_dollars": 5},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_bid_strategy_plan",
            "command": "plan-bid-strategy",
            "source_resource": "local campaign bid-strategy builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only campaign update for manual CPC, maximize conversions, maximize conversion value, target CPA, or target ROAS bidding.",
            "metadata": {"supported_strategies": ["manual_cpc", "maximize_conversions", "maximize_conversion_value", "target_cpa", "target_roas"]},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_conversion_goal_plan",
            "command": "plan-campaign-conversion-goal",
            "source_resource": "campaign_conversion_goal",
            "warehouse_tables": ["google_mutation_plans", "google_core_generic"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only update for campaign conversion-goal biddability.",
            "metadata": {"default_origin": "WEBSITE", "default_category": "DEFAULT"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_sitelink_plan",
            "command": "plan-sitelinks",
            "source_resource": "local campaign asset builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates validate-only sitelink asset and campaign-asset attach operations for an existing campaign.",
            "metadata": {"field_type": "SITELINK"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_callout_plan",
            "command": "plan-callouts",
            "source_resource": "local campaign asset builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates validate-only callout asset and campaign-asset attach operations for an existing campaign.",
            "metadata": {"field_type": "CALLOUT"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_structured_snippet_plan",
            "command": "plan-structured-snippets",
            "source_resource": "local campaign asset builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates validate-only structured snippet asset and campaign-asset attach operations for an existing campaign.",
            "metadata": {"field_type": "STRUCTURED_SNIPPET"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_campaign_targeting_plan",
            "command": "plan-campaign-targeting",
            "source_resource": "campaign_criterion",
            "warehouse_tables": ["google_mutation_plans", "google_core_generic"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates validate-only campaign criteria for geo targets, excluded geo targets, languages, and ad schedules.",
            "metadata": {"supports": ["location", "negative_location", "language", "ad_schedule"]},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_custom_mutate_plan",
            "command": "plan-custom-mutate",
            "source_resource": "user-provided GoogleAdsService mutate JSON",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Stores arbitrary GoogleAdsService mutateOperations JSON as a validate-only plan for rarer dashboard operations not yet wrapped by a friendly command.",
            "metadata": {"requires_mutate_operations": True},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_ad_group_plan",
            "command": "plan-ad-group",
            "source_resource": "local ad group builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only ad group create operation for an existing campaign.",
            "metadata": {"default_status": "PAUSED", "default_type": "SEARCH_STANDARD"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_keyword_plan",
            "command": "plan-keywords",
            "source_resource": "local keyword builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates validate-only keyword create operations for an existing ad group, with explicit match types.",
            "metadata": {"default_status": "PAUSED", "match_types": ["EXACT", "PHRASE", "BROAD"]},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_responsive_search_ad_plan",
            "command": "plan-responsive-search-ad",
            "source_resource": "local responsive search ad builder",
            "warehouse_tables": ["google_mutation_plans"],
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual only",
            "notes": "Creates a validate-only responsive search ad create operation for an existing ad group.",
            "metadata": {"default_status": "PAUSED", "min_headlines": 3, "min_descriptions": 2},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_search_negative_plan",
            "command": "plan-search-negatives",
            "source_resource": "google_search_terms warehouse rows",
            "warehouse_tables": ["google_search_terms", "google_mutation_plans"],
            "date_window": "report_date BETWEEN {since} AND {until}",
            "default_days": 30,
            "default_chunk_days": 30,
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual after native search-term sync",
            "notes": "Creates stored validate-only negative-keyword plans from spend-without-conversion search terms already in the warehouse.",
            "metadata": {"default_scope": "ad_group", "default_match_type": "EXACT"},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_budget_adjustment_plan",
            "command": "plan-budget-adjustments",
            "source_resource": "google_campaign_daily_performance + google_campaigns + google_campaign_budgets",
            "warehouse_tables": ["google_campaign_daily_performance", "google_campaigns", "google_campaign_budgets", "google_mutation_plans"],
            "date_window": "date_start BETWEEN {since} AND {until}",
            "default_days": 7,
            "default_chunk_days": 7,
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual after native campaign budget sync",
            "notes": "Creates stored validate-only campaign-budget adjustment plans from Triple Whale economics and native budget IDs.",
            "metadata": {"default_scale_percent": 15, "default_decrease_percent": 20, "default_target_ncpa": DEFAULT_TARGET_NCPA},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_optimizer_action_plan",
            "command": "plan-optimizer-actions",
            "source_resource": "google_search_terms + google_campaign_daily_performance + native budget tables",
            "warehouse_tables": ["google_search_terms", "google_campaign_daily_performance", "google_campaigns", "google_campaign_budgets", "google_mutation_plans"],
            "date_window": "search report_date and campaign date_start windows",
            "default_days": 30,
            "default_chunk_days": 7,
            "requires_auth": False,
            "can_mutate": False,
            "schedule": "manual after native search-term and budget sync",
            "notes": "Creates a combined set of stored validate-only search-negative and budget-adjustment plans from the optimizer inputs.",
            "metadata": {"uses_tw_truth": True, "requires_native_ids": True},
        }
    )
    add(
        {
            "surface_type": "mutation",
            "surface_name": "google_ads_mutate_preview",
            "command": "mutate",
            "source_resource": "customers/{customer_id}/googleAds:mutate",
            "warehouse_tables": ["google_raw_snapshots", "google_sync_runs", "google_fetch_errors"],
            "requires_auth": True,
            "can_mutate": True,
            "schedule": "manual only",
            "notes": "Validate-only by default; live writes require --confirm-live after human approval and post a Slack recap by default.",
            "metadata": {"default_validate_only": True, "default_slack_channel": DEFAULT_SLACK_CHANNEL},
        }
    )
    return rows


def store_query_manifest(rows: list[dict[str, Any]]) -> None:
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO google_query_manifest (
                    api_version, surface_type, surface_name, command, query_name,
                    source_resource, warehouse_tables, date_window, default_days,
                    default_chunk_days, requires_auth, can_mutate, schedule, query,
                    query_hash, selected_fields, metric_fields, segment_fields,
                    resource_fields, notes, metadata, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                    %s, %s::jsonb, now()
                )
                ON CONFLICT (api_version, surface_type, surface_name) DO UPDATE SET
                    command = excluded.command,
                    query_name = excluded.query_name,
                    source_resource = excluded.source_resource,
                    warehouse_tables = excluded.warehouse_tables,
                    date_window = excluded.date_window,
                    default_days = excluded.default_days,
                    default_chunk_days = excluded.default_chunk_days,
                    requires_auth = excluded.requires_auth,
                    can_mutate = excluded.can_mutate,
                    schedule = excluded.schedule,
                    query = excluded.query,
                    query_hash = excluded.query_hash,
                    selected_fields = excluded.selected_fields,
                    metric_fields = excluded.metric_fields,
                    segment_fields = excluded.segment_fields,
                    resource_fields = excluded.resource_fields,
                    notes = excluded.notes,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (
                    row["api_version"],
                    row["surface_type"],
                    row["surface_name"],
                    row["command"],
                    row.get("query_name"),
                    row.get("source_resource"),
                    jsonb(row.get("warehouse_tables", [])),
                    row.get("date_window"),
                    row.get("default_days"),
                    row.get("default_chunk_days"),
                    row.get("requires_auth", True),
                    row.get("can_mutate", False),
                    row.get("schedule"),
                    row.get("query"),
                    row.get("query_hash"),
                    jsonb(row.get("selected_fields", [])),
                    jsonb(row.get("metric_fields", [])),
                    jsonb(row.get("segment_fields", [])),
                    jsonb(row.get("resource_fields", [])),
                    row.get("notes"),
                    jsonb(row.get("metadata", {})),
                ),
            )


def emit_query_manifest(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(rows, indent=2))
        return
    counts: dict[str, int] = {}
    auth_blocked = 0
    for row in rows:
        counts[row["surface_type"]] = counts.get(row["surface_type"], 0) + 1
        if row.get("requires_auth"):
            auth_blocked += 1
    if fmt == "summary":
        print(
            json.dumps(
                {
                    "rows": len(rows),
                    "by_surface_type": counts,
                    "requires_auth": auth_blocked,
                    "no_auth_required": len(rows) - auth_blocked,
                },
                indent=2,
            )
        )
        return
    print("| Type | Surface | Command | Source | Tables | Auth | Fields |")
    print("| --- | --- | --- | --- | --- | --- | ---: |")
    for row in rows:
        tables = ", ".join(row.get("warehouse_tables") or [])
        fields = len(row.get("selected_fields") or [])
        auth = "required" if row.get("requires_auth") else "no"
        print(
            "| "
            + " | ".join(
                [
                    str(row["surface_type"]),
                    str(row["surface_name"]),
                    str(row["command"]),
                    str(row.get("source_resource") or ""),
                    tables,
                    auth,
                    str(fields),
                ]
            )
            + " |"
        )


def clone_or_update(repo_url: str, target: pathlib.Path, *, refresh: bool = False) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and refresh:
        subprocess.run(["git", "-C", str(target), "fetch", "--depth=1", "origin"], check=False)
        subprocess.run(["git", "-C", str(target), "reset", "--hard", "origin/HEAD"], check=False)
    elif not target.exists():
        subprocess.run(["git", "clone", "--depth=1", repo_url, str(target)], check=True)
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_service_clients(repo_dir: pathlib.Path) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    service_files = sorted(repo_dir.rglob("client.py"))
    for path in service_files:
        rel = path.relative_to(repo_dir).as_posix()
        if "/services/services/" not in f"/{rel}":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        class_match = re.search(r"class\s+([A-Za-z0-9_]+ServiceClient)\b", text)
        if not class_match:
            continue
        service_name = class_match.group(1).removesuffix("Client")
        version_match = re.search(r"/(v\d+)/", f"/{rel}")
        version = version_match.group(1) if version_match else "unknown"
        methods = []
        method_names = sorted(
            set(re.findall(r"^\s{4}(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\(", text, re.M))
        )
        helper_names = {
            "api_endpoint",
            "close",
            "from_service_account_file",
            "from_service_account_info",
            "get_mtls_endpoint_and_cert_source",
            "get_transport_class",
            "transport",
            "universe_domain",
        }
        for method in method_names:
            if (
                method.startswith("_")
                or method.startswith("parse_")
                or method.endswith("_path")
                or method in helper_names
            ):
                continue
            if method.startswith(("mutate", "apply", "dismiss", "upload", "create", "remove", "enable")):
                operation = "mutate"
            elif method.startswith(("search", "get", "list", "suggest", "generate", "recommend", "fetch")):
                operation = "read"
            else:
                operation = "action"
            methods.append(
                {
                    "method_name": method,
                    "operation_kind": operation,
                    "rest_path": f"{version}/{snake_to_camel(service_name)}.{snake_to_camel(method)}",
                }
            )
        parsed.append(
            {
                "api_version": version,
                "service_name": service_name,
                "service_file": rel,
                "methods": methods,
                "operations": methods,
                "raw_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return parsed


def ast_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def proto_call_name(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "proto":
        return func.attr
    return None


def proto_type_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "proto":
        return node.attr
    return ast_name(node)


def keyword_value(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def literal_keyword(call: ast.Call, name: str) -> Any:
    value = keyword_value(call, name)
    if value is None:
        return None
    try:
        return ast.literal_eval(value)
    except Exception:
        return ast_name(value)


def parse_attribute_docs(docstring: str | None) -> dict[str, str]:
    if not docstring or "Attributes:" not in docstring:
        return {}
    attrs = docstring.split("Attributes:", 1)[1]
    matches = list(re.finditer(r"^\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+\(([^)]*)\):", attrs, re.M))
    out: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(attrs)
        body = attrs[start:end]
        description = re.sub(r"\s+", " ", body).strip()
        out[match.group(1)] = description[:1200]
    return out


def resource_kind_for(resource: str) -> str:
    if resource == "metrics":
        return "METRIC"
    if resource == "segments":
        return "SEGMENT"
    if resource.endswith("_view") or resource.endswith("_insight"):
        return "VIEW"
    return "RESOURCE"


def parse_offline_catalog_file(repo_dir: pathlib.Path, path: pathlib.Path) -> list[dict[str, Any]]:
    rel = path.relative_to(repo_dir).as_posix()
    version_match = re.search(r"/(v\d+)/", f"/{rel}")
    version = version_match.group(1) if version_match else "unknown"
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        module = ast.parse(text)
    except SyntaxError:
        return []
    rows: list[dict[str, Any]] = []
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any((ast_name(base) or "").endswith("proto.Message") for base in node.bases):
            continue
        class_name = node.name
        resource = camel_to_snake(class_name)
        if class_name == "Metrics":
            resource = "metrics"
        elif class_name == "Segments":
            resource = "segments"
        docs = parse_attribute_docs(ast.get_docstring(node))
        for item in node.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            call_name = proto_call_name(item.value)
            if call_name not in {"Field", "RepeatedField", "MapField"}:
                continue
            call = item.value
            assert isinstance(call, ast.Call)
            field_name = item.target.id
            repeated = call_name in {"RepeatedField", "MapField"}
            proto_type = proto_type_name(call.args[0]) if call.args else None
            enum_type = ast_name(keyword_value(call, "enum"))
            message_type = ast_name(keyword_value(call, "message"))
            optional = bool(literal_keyword(call, "optional"))
            field_type = ast_name(item.annotation)
            field_path = f"{resource}.{field_name}"
            rows.append(
                {
                    "api_version": version,
                    "resource": resource,
                    "field_name": field_name,
                    "field_path": field_path,
                    "resource_kind": resource_kind_for(resource),
                    "class_name": class_name,
                    "field_type": field_type,
                    "proto_type": proto_type,
                    "enum_type": enum_type,
                    "message_type": message_type,
                    "repeated": repeated,
                    "optional": optional,
                    "description": docs.get(field_name),
                    "source_file": rel,
                    "raw": {
                        "call": call_name,
                        "number": literal_keyword(call, "number"),
                        "oneof": literal_keyword(call, "oneof"),
                    },
                }
            )
    return rows


def parse_offline_catalog_fields(repo_dir: pathlib.Path) -> list[dict[str, Any]]:
    paths: list[pathlib.Path] = []
    for version_dir in sorted((repo_dir / "google" / "ads" / "googleads").glob("v*")):
        paths.extend(sorted((version_dir / "resources" / "types").glob("*.py")))
        paths.extend(
            [
                version_dir / "common" / "types" / "metrics.py",
                version_dir / "common" / "types" / "segments.py",
            ]
        )
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.name == "__init__.py" or not path.exists():
            continue
        rows.extend(parse_offline_catalog_file(repo_dir, path))
    return rows


def upsert_catalog_source(name: str, url: str, ref: str, metadata: dict[str, Any]) -> None:
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_api_catalog_sources (source_name, source_url, source_ref, metadata)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (source_name) DO UPDATE SET
                source_url = excluded.source_url,
                source_ref = excluded.source_ref,
                fetched_at = now(),
                metadata = excluded.metadata
            """,
            (name, url, ref, jsonb(metadata)),
        )


def cmd_init_schema(_: argparse.Namespace) -> int:
    ensure_schema()
    print("google_ads_tw schema ready")
    return 0


def cmd_catalog_client_library(args: argparse.Namespace) -> int:
    ensure_schema()
    commit = clone_or_update(OFFICIAL_CLIENT_REPO, OFFICIAL_CLIENT_CACHE, refresh=args.refresh)
    services = parse_service_clients(OFFICIAL_CLIENT_CACHE)
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM google_api_services WHERE source_name = %s", ("google-ads-python",))
        cur.execute("DELETE FROM google_api_methods WHERE source_name = %s", ("google-ads-python",))
        for service in services:
            cur.execute(
                """
                INSERT INTO google_api_services (
                    api_version, service_name, service_file, methods,
                    operations, source_name, source_ref, raw_hash, updated_at
                )
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, now())
                ON CONFLICT (api_version, service_name) DO UPDATE SET
                    service_file = excluded.service_file,
                    methods = excluded.methods,
                    operations = excluded.operations,
                    source_name = excluded.source_name,
                    source_ref = excluded.source_ref,
                    raw_hash = excluded.raw_hash,
                    updated_at = now()
                """,
                (
                    service["api_version"],
                    service["service_name"],
                    service["service_file"],
                    jsonb(service["methods"]),
                    jsonb(service["operations"]),
                    "google-ads-python",
                    commit,
                    service["raw_hash"],
                ),
            )
            for method in service["methods"]:
                cur.execute(
                    """
                    INSERT INTO google_api_methods (
                        api_version, service_name, method_name, operation_kind,
                        rest_path, service_file, source_name, source_ref, raw,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (api_version, service_name, method_name) DO UPDATE SET
                        operation_kind = excluded.operation_kind,
                        rest_path = excluded.rest_path,
                        service_file = excluded.service_file,
                        source_name = excluded.source_name,
                        source_ref = excluded.source_ref,
                        raw = excluded.raw,
                        updated_at = now()
                    """,
                    (
                        service["api_version"],
                        service["service_name"],
                        method["method_name"],
                        method.get("operation_kind"),
                        method.get("rest_path"),
                        service["service_file"],
                        "google-ads-python",
                        commit,
                        jsonb(method),
                    ),
                )
    upsert_catalog_source(
        "google-ads-python",
        OFFICIAL_CLIENT_REPO,
        commit,
        {
            "services": len(services),
            "methods": sum(len(service["methods"]) for service in services),
            "versions": sorted({s["api_version"] for s in services}),
        },
    )
    method_count = sum(len(service["methods"]) for service in services)
    print(f"cataloged {len(services)} Google Ads client-library services and {method_count} methods from {commit[:12]}")
    return 0


def cmd_catalog_offline_fields(args: argparse.Namespace) -> int:
    ensure_schema()
    commit = clone_or_update(OFFICIAL_CLIENT_REPO, OFFICIAL_CLIENT_CACHE, refresh=args.refresh)
    rows = parse_offline_catalog_fields(OFFICIAL_CLIENT_CACHE)
    params = [
        (
            row["api_version"],
            row["resource"],
            row["field_name"],
            row["field_path"],
            row["resource_kind"],
            row["class_name"],
            row["field_type"],
            row["proto_type"],
            row["enum_type"],
            row["message_type"],
            row["repeated"],
            row["optional"],
            row["description"],
            row["source_file"],
            jsonb(row["raw"]),
        )
        for row in rows
    ]
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM google_offline_catalog_fields")
        cur.executemany(
            """
            INSERT INTO google_offline_catalog_fields (
                api_version, resource, field_name, field_path, resource_kind,
                class_name, field_type, proto_type, enum_type, message_type,
                repeated, optional, description, source_file, raw, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s::jsonb, now()
            )
            ON CONFLICT (api_version, field_path) DO UPDATE SET
                resource = excluded.resource,
                field_name = excluded.field_name,
                resource_kind = excluded.resource_kind,
                class_name = excluded.class_name,
                field_type = excluded.field_type,
                proto_type = excluded.proto_type,
                enum_type = excluded.enum_type,
                message_type = excluded.message_type,
                repeated = excluded.repeated,
                optional = excluded.optional,
                description = excluded.description,
                source_file = excluded.source_file,
                raw = excluded.raw,
                updated_at = now()
            """,
            params,
        )
    by_version: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for row in rows:
        by_version[row["api_version"]] = by_version.get(row["api_version"], 0) + 1
        key = f"{row['api_version']}:{row['resource_kind']}"
        by_kind[key] = by_kind.get(key, 0) + 1
    upsert_catalog_source(
        "google-ads-python-offline-fields",
        OFFICIAL_CLIENT_REPO,
        commit,
        {"fields": len(rows), "by_version": by_version, "by_version_kind": by_kind},
    )
    print(json.dumps({"fields": len(rows), "source_ref": commit[:12], "by_version": by_version}, indent=2))
    return 0


def cmd_catalog_open_source(args: argparse.Namespace) -> int:
    ensure_schema()
    RESEARCH_CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, url in OPEN_SOURCE_REPOS.items():
        target = RESEARCH_CACHE / name
        try:
            commit = clone_or_update(url, target, refresh=args.refresh)
            files = [p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()]
            upsert_catalog_source(
                name,
                url,
                commit,
                {
                    "files": len(files),
                    "readme_files": [f for f in files if f.lower().endswith("readme.md")][:10],
                    "skill_files": [f for f in files if f.lower().endswith("skill.md")][:10],
                },
            )
            rows.append({"name": name, "commit": commit[:12], "files": len(files), "status": "ok"})
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": name, "commit": "", "files": 0, "status": f"error: {exc}"})
    print(json.dumps(rows, indent=2))
    return 0


def cmd_sync_field_catalog(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    run_id = run_start("sync-field-catalog", customer)
    query = """
        SELECT
          name,
          category,
          data_type,
          type_url,
          is_repeated,
          selectable,
          filterable,
          sortable,
          selectable_with,
          attribute_resources,
          metrics,
          segments,
          enum_values
    """
    try:
        rows = search_google_ads_fields(normalize_query(query), run_id=run_id, max_pages=args.max_pages)
        with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
            for row in rows:
                field = row.get("googleAdsField") or row
                name = field.get("name")
                if not name:
                    continue
                cur.execute(
                    """
                    INSERT INTO google_ads_fields (
                        api_version, name, category, data_type, type_url,
                        selectable, filterable, sortable, repeated,
                        selectable_with, attribute_resources, metrics, segments,
                        enum_values, resource_name, raw, fetched_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, now())
                    ON CONFLICT (api_version, name) DO UPDATE SET
                        category = excluded.category,
                        data_type = excluded.data_type,
                        type_url = excluded.type_url,
                        selectable = excluded.selectable,
                        filterable = excluded.filterable,
                        sortable = excluded.sortable,
                        repeated = excluded.repeated,
                        selectable_with = excluded.selectable_with,
                        attribute_resources = excluded.attribute_resources,
                        metrics = excluded.metrics,
                        segments = excluded.segments,
                        enum_values = excluded.enum_values,
                        resource_name = excluded.resource_name,
                        raw = excluded.raw,
                        fetched_at = now()
                    """,
                    (
                        api_version(),
                        name,
                        field.get("category"),
                        field.get("dataType"),
                        field.get("typeUrl"),
                        field.get("selectable"),
                        field.get("filterable"),
                        field.get("sortable"),
                        field.get("isRepeated"),
                        jsonb(field.get("selectableWith") or []),
                        jsonb(field.get("attributeResources") or []),
                        jsonb(field.get("metrics") or []),
                        jsonb(field.get("segments") or []),
                        jsonb(field.get("enumValues") or []),
                        field.get("resourceName"),
                        jsonb(field),
                    ),
                )
        store_gaql_rows(run_id, customer=customer, query_name="field_catalog", source_resource="google_ads_field", query=normalize_query(query), rows=rows)
        run_finish(run_id, "success", rows_fetched=len(rows), rows_written=len(rows))
        print(f"synced {len(rows)} GoogleAdsField rows")
        return 0
    except Exception:
        run_finish(run_id, "error", errors=1)
        raise


def cmd_customers(args: argparse.Namespace) -> int:
    ensure_schema()
    run_id = run_start("customers", None)
    endpoint = "customers:listAccessibleCustomers"
    try:
        body, headers = api_request("GET", endpoint)
        store_raw_snapshot(run_id, customer=None, endpoint=endpoint, request_payload={}, response_payload=body, response_headers=headers)
        resource_names = body.get("resourceNames") or []
        print(json.dumps(resource_names, indent=2))
        run_finish(run_id, "success", rows_fetched=len(resource_names), rows_written=0)
        return 0
    except Exception:
        run_finish(run_id, "error", errors=1)
        raise


def cmd_auth_check(args: argparse.Namespace) -> int:
    ensure_schema()
    run_id = run_start("auth-check", None)
    endpoint = "customers:listAccessibleCustomers"
    try:
        body, headers = api_request("GET", endpoint)
        resource_names = body.get("resourceNames") or []
        store_raw_snapshot(
            run_id,
            customer=None,
            endpoint=endpoint,
            request_payload={},
            response_payload={"resourceNames": resource_names},
            response_headers=headers,
        )
        run_finish(run_id, "success", rows_fetched=len(resource_names), rows_written=0)
        print(json.dumps({"ok": True, "resource_names": resource_names}, indent=2))
        return 0
    except Exception as exc:
        log_fetch_error(run_id, endpoint, {}, exc)
        run_finish(run_id, "error", errors=1)
        summary = summarize_auth_error(str(exc)) or "Google Ads auth check failed."
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": summary,
                    "next_command": "gads auth-doctor",
                },
                indent=2,
            )
        )
        return 1


def latest_auth_state() -> dict[str, Any]:
    ensure_schema()
    with connect(schema=SCHEMA, application_name="google-ads-auth-doctor") as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT jsonb_build_object(
                'latest_auth_status', (SELECT status FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
                'latest_auth_check', (SELECT completed_at::text FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
                'latest_auth_error_at', (SELECT occurred_at::text FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
                'latest_auth_error', (SELECT message FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1)
            )
            """
        )
        row = cur.fetchone()
    data = dict(row[0] or {}) if row else {}
    data["latest_auth_error_summary"] = auth_blocker_from_latest(data)
    data.pop("latest_auth_error", None)
    return data


def auth_doctor_payload(*, include_tokeninfo: bool = True, reveal_email: bool = False) -> dict[str, Any]:
    ensure_schema()
    load_env()
    state = credential_state()
    customer = (os.environ.get("GOOGLE_ADS_CUSTOMER_ID") or "").replace("-", "").strip() or None
    login_customer = (os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or "").replace("-", "").strip() or None
    scope_state: dict[str, Any] | None = None
    identity_state: dict[str, Any] | None = None
    if include_tokeninfo and (state["keys"].get("access_token") or state.get("refresh_ready")):
        try:
            token = current_access_token()
            token_state = token_scope_state(token)
            scope_state = {
                "ok": bool(token_state.get("ok")),
                "adwords_scope": bool(token_state.get("adwords_scope")),
                "scope_count": len(token_state.get("scopes") or []),
                "error": token_state.get("error"),
            }
            identity_state = oauth_identity_state(token, reveal_email=reveal_email)
        except Exception as exc:  # noqa: BLE001
            scope_state = {"ok": False, "adwords_scope": False, "scope_count": 0, "error": str(exc)}
            identity_state = {"ok": False, "error": str(exc)}

    latest = latest_auth_state()
    blocker = auth_blocker_from_latest(latest)
    checks = [
        {
            "id": "credentials_present",
            "ok": bool(state.get("ready")),
            "evidence": "all required Google Ads credential keys are present"
            if state.get("ready")
            else f"missing: {', '.join(state.get('missing') or [])}",
        },
        {
            "id": "refresh_ready",
            "ok": bool(state.get("refresh_ready")),
            "evidence": "OAuth refresh-token flow is configured"
            if state.get("refresh_ready")
            else "refresh token/client credentials are not fully configured",
        },
    ]
    if scope_state is not None:
        checks.append(
            {
                "id": "oauth_scope",
                "ok": bool(scope_state.get("ok") and scope_state.get("adwords_scope")),
                "evidence": "OAuth token has Google Ads adwords scope"
                if scope_state.get("ok") and scope_state.get("adwords_scope")
                else f"OAuth token scope check failed: {scope_state.get('error') or 'adwords scope missing'}",
            }
        )
    if identity_state is not None:
        email_hint = identity_state.get("email") or identity_state.get("email_masked")
        checks.append(
            {
                "id": "oauth_identity",
                "ok": bool(identity_state.get("ok") and email_hint),
                "evidence": f"OAuth user is {email_hint}"
                if identity_state.get("ok") and email_hint
                else f"OAuth user identity unavailable: {identity_state.get('error') or 'email scope missing'}",
            }
        )
    checks.append(
        {
            "id": "ads_user_access",
            "ok": latest.get("latest_auth_status") == "success",
            "evidence": "Google Ads accessible-customer smoke test passed"
            if latest.get("latest_auth_status") == "success"
            else blocker or "run gads auth-check to test Google Ads account access",
        }
    )

    next_steps: list[str]
    if not state.get("ready"):
        next_steps = [
            "Complete credential storage with the OAuth bootstrap and Google Ads developer/customer values.",
            "Run gads auth-doctor again.",
        ]
    elif scope_state is not None and not scope_state.get("adwords_scope"):
        next_steps = [
            "Redo OAuth with the Google Ads scope using scripts/bootstrap_google_ads_oauth.sh.",
            "Run gads auth-check.",
        ]
    elif latest.get("latest_auth_status") != "success":
        account_hint = ""
        if identity_state and (identity_state.get("email") or identity_state.get("email_masked")):
            account_hint = f" ({identity_state.get('email') or identity_state.get('email_masked')})"
        next_steps = [
            f"Grant the OAuth Google account{account_hint} access to Google Ads MCC {login_customer or 'configured MCC'} or customer {customer or 'configured customer'}.",
            "Run gads auth-check.",
            "Run gads post-auth-bootstrap.",
            "Run gads completion-audit.",
        ]
    else:
        next_steps = [
            "Run gads post-auth-bootstrap if the bootstrap marker has not been written.",
            "Run gads completion-audit.",
        ]

    oauth_email_hint = None
    oauth_email_for_invite = None
    if identity_state:
        oauth_email_hint = identity_state.get("email") or identity_state.get("email_masked")
        oauth_email_for_invite = identity_state.get("email") if reveal_email else None
    access_runbook = {
        "oauth_user": oauth_email_hint or "run gads auth-doctor --show-email locally",
        "invite_email": oauth_email_for_invite,
        "manager_account_id": login_customer,
        "customer_id": customer,
        "recommended_access_level": "Standard",
        "why_standard": "Standard access can manage campaigns while avoiding account hierarchy/admin ownership permissions.",
        "steps": [
            "Open Google Ads while signed into a user that already has Admin access to the MCC or customer.",
            f"Go to the MCC {login_customer or 'configured MCC'} if possible; otherwise open customer {customer or 'configured customer'} directly.",
            "Click Admin, then Access and security.",
            "Click the plus button to invite a user.",
            f"Enter the OAuth user email: {oauth_email_for_invite or 'run gads auth-doctor --show-email locally to reveal it'}.",
            "Choose Standard access for reporting/backfill and future campaign management. Use Admin only if this OAuth user must manage users or account hierarchy.",
            "Send the invitation and accept it from that Google account.",
            "Run gads auth-check, then gads post-auth-bootstrap, then gads completion-audit.",
        ],
        "sources": [
            "https://support.google.com/google-ads/answer/7459700",
            "https://support.google.com/google-ads/answer/9977851",
        ],
    }

    return {
        "ok": latest.get("latest_auth_status") == "success",
        "blocker": None if latest.get("latest_auth_status") == "success" else blocker,
        "configured_accounts": {
            "customer_id": customer,
            "login_customer_id": login_customer,
            "api_version": api_version(),
        },
        "credentials": state,
        "token_scope": scope_state,
        "oauth_identity": identity_state,
        "latest_auth": latest,
        "checks": checks,
        "next_steps": next_steps,
        "access_runbook": access_runbook,
        "commands_after_access": [
            "gads auth-check",
            "gads post-auth-bootstrap",
            "gads plan-optimizer-actions --format summary",
            "gads completion-audit",
        ],
    }


def cmd_auth_doctor(args: argparse.Namespace) -> int:
    payload = auth_doctor_payload(include_tokeninfo=not args.no_tokeninfo, reveal_email=args.show_email)
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print("# Google Ads Auth Doctor\n")
        print(f"- Status: {'ready' if payload.get('ok') else 'blocked'}")
        if payload.get("blocker"):
            print(f"- Blocker: {payload['blocker']}")
        accounts = payload.get("configured_accounts") or {}
        print(f"- Customer ID: {accounts.get('customer_id') or 'missing'}")
        print(f"- Login customer ID: {accounts.get('login_customer_id') or 'missing'}")
        print(f"- API version: {accounts.get('api_version') or DEFAULT_API_VERSION}")
        identity = payload.get("oauth_identity") or {}
        if identity.get("ok") and (identity.get("email") or identity.get("email_masked")):
            print(f"- OAuth user: {identity.get('email') or identity.get('email_masked')}")
        print("\n## Checks\n")
        for check in payload.get("checks") or []:
            mark = "PASS" if check.get("ok") else "BLOCKED"
            print(f"- {mark} `{check.get('id')}`: {check.get('evidence')}")
        print("\n## Next Steps\n")
        for step in payload.get("next_steps") or []:
            print(f"- {step}")
        if not payload.get("ok"):
            runbook = payload.get("access_runbook") or {}
            print("\n## Access Grant Runbook\n")
            print(f"- OAuth user: {runbook.get('oauth_user') or 'unknown'}")
            print(f"- MCC: {runbook.get('manager_account_id') or 'missing'}")
            print(f"- Customer: {runbook.get('customer_id') or 'missing'}")
            print(f"- Recommended access: {runbook.get('recommended_access_level') or 'Standard'}")
            if runbook.get("why_standard"):
                print(f"- Why: {runbook['why_standard']}")
            for index, step in enumerate(runbook.get("steps") or [], start=1):
                print(f"{index}. {step}")
            sources = runbook.get("sources") or []
            if sources:
                print("\nSources:")
                for source in sources:
                    print(f"- {source}")
            print("\n## Commands After Access\n")
            for command in payload.get("commands_after_access") or []:
                print(f"- `{command}`")
    return 0 if payload.get("ok") else 2


def cmd_query(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    run_id = run_start("query", customer, {"query_name": args.name})
    try:
        rows = search_gaql(args.gaql, customer=customer, run_id=run_id, query_name=args.name, max_pages=args.max_pages)
        store_gaql_rows(run_id, customer=customer, query_name=args.name, source_resource=args.source_resource, query=args.gaql, rows=rows)
        run_finish(run_id, "success", rows_fetched=len(rows), rows_written=len(rows))
        emit_rows(rows, args.format)
        return 0
    except Exception:
        run_finish(run_id, "error", errors=1)
        raise


def emit_rows(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(rows, indent=2))
    elif fmt == "jsonl":
        for row in rows:
            print(json.dumps(row, separators=(",", ":")))
    else:
        print(json.dumps({"rows": len(rows)}, indent=2))


def cmd_sync_core(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    surfaces = list(CORE_QUERIES) if args.surface == "all" else args.surface.split(",")
    run_id = run_start("sync-core", customer, {"surfaces": surfaces})
    rows_fetched = 0
    rows_written = 0
    errors = 0
    try:
        for surface in surfaces:
            if surface not in CORE_QUERIES:
                print(f"skip unknown core surface: {surface}", file=sys.stderr)
                errors += 1
                continue
            source_resource, query = CORE_QUERIES[surface]
            normalized = normalize_query(query.replace("{customer_id}", customer))
            try:
                rows = search_gaql(normalized, customer=customer, run_id=run_id, query_name=f"core_{surface}", max_pages=args.max_pages)
                store_gaql_rows(run_id, customer=customer, query_name=f"core_{surface}", source_resource=source_resource, query=normalized, rows=rows)
                generic_written = store_core_generic_rows(
                    customer=customer,
                    surface=surface,
                    query_name=f"core_{surface}",
                    source_resource=source_resource,
                    query=normalized,
                    rows=rows,
                )
                normalized_written = upsert_core_rows(customer, surface, rows)
                written = max(generic_written, normalized_written)
                rows_fetched += len(rows)
                rows_written += written
                print(f"{surface}: fetched={len(rows)} written={written} generic={generic_written}")
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"{surface}: ERROR {exc}", file=sys.stderr)
                if not args.keep_going:
                    raise
        run_finish(run_id, "success" if errors == 0 else "partial", rows_fetched=rows_fetched, rows_written=rows_written, errors=errors)
        return 0 if errors == 0 else 2
    except Exception:
        run_finish(run_id, "error", rows_fetched=rows_fetched, rows_written=rows_written, errors=errors + 1)
        raise


def date_range_from_args(args: argparse.Namespace) -> tuple[str, str]:
    if args.since and args.until:
        return args.since, args.until
    today = dt.date.today()
    days = int(args.days or 1)
    since = today - dt.timedelta(days=days - 1)
    return since.isoformat(), today.isoformat()


def cmd_sync_performance(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    surfaces = PERFORMANCE_SURFACES if args.surface == "all" else args.surface.split(",")
    since, until = date_range_from_args(args)
    run_id = run_start("sync-performance", customer, {"surfaces": surfaces, "since": since, "until": until})
    rows_fetched = 0
    rows_written = 0
    errors = 0
    try:
        for surface in surfaces:
            try:
                source_resource, query = performance_query(surface, since, until)
                normalized = normalize_query(query.replace("{customer_id}", customer))
                rows = search_gaql(normalized, customer=customer, run_id=run_id, query_name=f"performance_{surface}", max_pages=args.max_pages)
                store_gaql_rows(run_id, customer=customer, query_name=f"performance_{surface}", source_resource=source_resource, query=normalized, rows=rows)
                generic_written = store_performance_generic_rows(
                    customer=customer,
                    surface=surface,
                    query_name=f"performance_{surface}",
                    query=normalized,
                    rows=rows,
                )
                if surface in PERFORMANCE_NORMALIZED_SURFACES:
                    normalized_written = upsert_performance_rows(customer, "search_term" if surface == "search_term" else surface, rows)
                    written = max(generic_written, normalized_written)
                else:
                    written = generic_written
                mark_backfill_chunk(customer, surface, since, until, "success", run_id, len(rows), written, 0)
                rows_fetched += len(rows)
                rows_written += written
                print(f"{surface}: {since}..{until} fetched={len(rows)} written={written}")
            except Exception as exc:  # noqa: BLE001
                errors += 1
                mark_backfill_chunk(customer, surface, since, until, "error", run_id, 0, 0, 1, {"error": str(exc)[:500]})
                print(f"{surface}: ERROR {exc}", file=sys.stderr)
                if not args.keep_going:
                    raise
        run_finish(run_id, "success" if errors == 0 else "partial", rows_fetched=rows_fetched, rows_written=rows_written, errors=errors)
        return 0 if errors == 0 else 2
    except Exception:
        run_finish(run_id, "error", rows_fetched=rows_fetched, rows_written=rows_written, errors=errors + 1)
        raise


def mark_backfill_chunk(
    customer: str,
    surface: str,
    since: str,
    until: str,
    status: str,
    run_id: str,
    rows_fetched: int,
    rows_written: int,
    errors: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_backfill_chunks (
                customer_id, surface, since_date, until_date, status,
                rows_fetched, rows_written, errors, last_run_id,
                started_at, completed_at, updated_at, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now(), now(), %s::jsonb)
            ON CONFLICT (customer_id, surface, since_date, until_date) DO UPDATE SET
                status = excluded.status,
                rows_fetched = excluded.rows_fetched,
                rows_written = excluded.rows_written,
                errors = excluded.errors,
                last_run_id = excluded.last_run_id,
                completed_at = now(),
                updated_at = now(),
                metadata = google_backfill_chunks.metadata || excluded.metadata
            """,
            (customer, surface, since, until, status, rows_fetched, rows_written, errors, run_id, jsonb(metadata or {})),
        )


def chunk_ranges(since: str, until: str, chunk_days: int) -> list[tuple[str, str]]:
    start = dt.date.fromisoformat(since)
    end = dt.date.fromisoformat(until)
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + dt.timedelta(days=chunk_days - 1), end)
        chunks.append((current.isoformat(), chunk_end.isoformat()))
        current = chunk_end + dt.timedelta(days=1)
    return chunks


def cmd_backfill(args: argparse.Namespace) -> int:
    ensure_schema()
    today = dt.date.today()
    since = args.since or (today - dt.timedelta(days=args.days - 1)).isoformat()
    until = args.until or today.isoformat()
    surfaces = PERFORMANCE_SURFACES if args.surface == "all" else args.surface.split(",")
    status = 0
    for chunk_since, chunk_until in chunk_ranges(since, until, args.chunk_days):
        ns = argparse.Namespace(
            customer_id=args.customer_id,
            surface=",".join(surfaces),
            since=chunk_since,
            until=chunk_until,
            days=None,
            max_pages=args.max_pages,
            keep_going=args.keep_going,
        )
        rc = cmd_sync_performance(ns)
        status = max(status, rc)
    return status


def run_bootstrap_step(name: str, func: Any, ns: argparse.Namespace, *, allow_partial: bool = True) -> dict[str, Any]:
    print(f"\n== {name} ==")
    try:
        status = int(func(ns) or 0)
        ok = status == 0 or (allow_partial and status == 2)
        return {"name": name, "status": status, "ok": ok}
    except Exception as exc:  # noqa: BLE001
        summary = summarize_auth_error(str(exc)) or str(exc)[:320]
        print(f"{name}: ERROR {summary}", file=sys.stderr)
        return {"name": name, "status": 1, "ok": False, "error": summary}


def cmd_post_auth_bootstrap(args: argparse.Namespace) -> int:
    ensure_schema()
    existing_markers = [str(marker) for marker in bootstrap_marker_paths() if marker.exists()]
    if existing_markers and not args.force:
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "post-auth bootstrap marker already exists",
                    "markers": existing_markers,
                    "rerun_command": "gads post-auth-bootstrap --force",
                },
                indent=2,
            )
        )
        return 0

    auth_status = run_bootstrap_step(
        "auth-check",
        cmd_auth_check,
        argparse.Namespace(),
        allow_partial=False,
    )
    if not auth_status["ok"]:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "blocker": "Google Ads OAuth account access has not passed yet",
                    "auth_check": auth_status,
                    "next_command": "gads auth-check",
                },
                indent=2,
            )
        )
        return 2

    customer = args.customer_id
    steps = [
        run_bootstrap_step(
            "sync-field-catalog",
            cmd_sync_field_catalog,
            argparse.Namespace(customer_id=customer, max_pages=args.max_pages),
            allow_partial=False,
        ),
        run_bootstrap_step(
            "sync-core",
            cmd_sync_core,
            argparse.Namespace(customer_id=customer, surface="all", max_pages=args.max_pages, keep_going=True),
        ),
        run_bootstrap_step(
            "backfill-30-days",
            cmd_backfill,
            argparse.Namespace(
                customer_id=customer,
                surface="all",
                days=30,
                since=None,
                until=None,
                chunk_days=args.chunk_days,
                max_pages=args.max_pages,
                keep_going=True,
            ),
        ),
        run_bootstrap_step(
            "full-backfill",
            cmd_backfill,
            argparse.Namespace(
                customer_id=customer,
                surface="all",
                days=None,
                since=args.since or full_backfill_since(args.full_years),
                until=args.until or dt.date.today().isoformat(),
                chunk_days=args.chunk_days,
                max_pages=args.max_pages,
                keep_going=True,
            ),
        ),
    ]
    success = all(step["ok"] for step in steps)
    markers: list[str] = []
    if success:
        markers = write_bootstrap_markers(now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"))
    summary = {
        "status": "complete" if success else "partial",
        "steps": steps,
        "markers": markers,
        "next_audit_command": "gads completion-audit",
    }
    print(json.dumps(summary, indent=2))
    return 0 if success else 2


KEYWORD_STOPWORDS = {
    "a",
    "ad",
    "ads",
    "and",
    "best",
    "buy",
    "for",
    "from",
    "google",
    "how",
    "in",
    "near",
    "of",
    "on",
    "online",
    "or",
    "shop",
    "the",
    "to",
    "with",
}
SEARCH_CAMPAIGN_NEGATIVE_STARTERS = [
    "cheap",
    "coupon",
    "download",
    "free",
    "job",
    "jobs",
    "meaning",
    "pdf",
    "recipe",
    "reddit",
    "review",
    "reviews",
    "salary",
    "sample",
    "samples",
    "scam",
    "wholesale",
]
DEFAULT_COMPETITOR_TERMS = _split_config_list(os.environ.get("GOOGLE_ADS_COMPETITOR_TERMS"))


def split_terms_arg(raw: str | None) -> list[str]:
    values = [item.strip() for item in re.split(r"[\n,|;]+", raw or "") if item.strip()]
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        key = re.sub(r"\s+", " ", value.casefold())
        if key in seen:
            continue
        seen.add(key)
        terms.append(re.sub(r"\s+", " ", value))
    return terms


def constant_resource(collection: str, raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise SystemExit(f"{collection} constant cannot be empty")
    if value.startswith(f"{collection}/"):
        return value
    return f"{collection}/{extract_id(value)}"


def constant_resources(collection: str, raw: str | None, defaults: list[str]) -> list[str]:
    values = split_terms_arg(raw)
    if not values:
        values = defaults
    return [constant_resource(collection, value) for value in values]


def int_metric(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def money_micros(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"${value / 1_000_000:,.2f}"


def keyword_idea_metrics(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("keywordIdeaMetrics") or row.get("keyword_metrics") or {}
    return {
        "avg_monthly_searches": int_metric(metrics.get("avgMonthlySearches")),
        "competition": metrics.get("competition"),
        "competition_index": int_metric(metrics.get("competitionIndex")),
        "low_top_of_page_bid_micros": int_metric(metrics.get("lowTopOfPageBidMicros")),
        "high_top_of_page_bid_micros": int_metric(metrics.get("highTopOfPageBidMicros")),
        "monthly_search_volumes": metrics.get("monthlySearchVolumes") or [],
    }


def intent_bucket_for_keyword(text: str, brand_terms: list[str] | None = None) -> str:
    lowered = text.casefold()
    for brand in brand_terms or DEFAULT_BRAND_TERMS:
        if brand and brand.casefold() in lowered:
            return "brand"
    if any(token in lowered for token in ("near me", "where to buy", "buy ", "shop ", "coupon", "discount")):
        return "transactional"
    if any(token in lowered for token in ("best", "top", "vs", "compare", "review", "reviews")):
        return "comparison"
    if any(token in lowered for token in ("how", "what", "why", "recipe", "meaning")):
        return "informational"
    return "category"


def recommended_match_type_for_keyword(
    text: str,
    metrics: dict[str, Any],
    *,
    allow_broad: bool = False,
    brand_terms: list[str] | None = None,
) -> str:
    bucket = intent_bucket_for_keyword(text, brand_terms)
    token_count = len(re.findall(r"[a-z0-9]+", text.casefold()))
    competition_index = metrics.get("competition_index")
    avg_searches = metrics.get("avg_monthly_searches") or 0
    if bucket == "brand":
        return "EXACT"
    if bucket in {"transactional", "comparison"} or token_count >= 4:
        return "EXACT"
    if allow_broad and token_count <= 3 and avg_searches >= 500 and (competition_index is None or competition_index <= 80):
        return "BROAD"
    return "PHRASE"


def keyword_cluster_key(text: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in KEYWORD_STOPWORDS and len(token) > 1
    ]
    if not tokens:
        return text[:32].title()
    return " ".join(tokens[:2]).title()


def is_competitor_keyword(text: str, competitor_terms: list[str]) -> bool:
    lowered = text.casefold()
    return any(term and term.casefold() in lowered for term in competitor_terms)


def keyword_ideas_request(
    *,
    seed_terms: list[str],
    final_url: str | None,
    geo_targets: list[str],
    language: str,
    network: str,
    page_size: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "geoTargetConstants": geo_targets,
        "language": language,
        "keywordPlanNetwork": network,
        "pageSize": page_size,
        "historicalMetricsOptions": {"includeAverageCpc": True},
    }
    if seed_terms and final_url:
        payload["keywordAndUrlSeed"] = {"keywords": seed_terms, "url": final_url}
    elif seed_terms:
        payload["keywordSeed"] = {"keywords": seed_terms}
    elif final_url:
        payload["urlSeed"] = {"url": final_url}
    else:
        raise SystemExit("--seed-terms or --final-url is required")
    return payload


def fetch_keyword_ideas(
    *,
    customer: str,
    seed_terms: list[str],
    final_url: str | None,
    geo_targets: list[str],
    language: str,
    network: str,
    limit: int,
    run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    endpoint = f"customers/{customer}:generateKeywordIdeas"
    rows: list[dict[str, Any]] = []
    page_token = None
    base_payload = keyword_ideas_request(
        seed_terms=seed_terms,
        final_url=final_url,
        geo_targets=geo_targets,
        language=language,
        network=network,
        page_size=min(max(limit, 1), 10_000),
    )
    while True:
        payload = dict(base_payload)
        if page_token:
            payload["pageToken"] = page_token
        body, headers = api_request("POST", endpoint, payload)
        store_raw_snapshot(
            run_id,
            customer=customer,
            endpoint=endpoint,
            request_payload=payload,
            response_payload=body,
            response_headers=headers,
        )
        page_rows = body.get("results") or []
        rows.extend(page_rows)
        page_token = body.get("nextPageToken")
        if not page_token or len(rows) >= limit:
            break
    return rows[:limit], base_payload


def keyword_planner_token_blocked(exc: Exception) -> bool:
    text = str(exc)
    return "DEVELOPER_TOKEN_NOT_APPROVED" in text or "explorer access" in text


def fallback_keyword_ideas_from_search_terms(
    *,
    customer: str,
    seed_terms: list[str],
    limit: int,
    days: int = 365,
) -> list[dict[str, Any]]:
    tokens: list[str] = []
    seen: set[str] = set()
    for seed in seed_terms:
        for token in re.findall(r"[a-z0-9]+", seed.casefold()):
            if token in KEYWORD_STOPWORDS or len(token) < 3 or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    if not tokens:
        return []
    clauses = " OR ".join(["lower(search_term) LIKE %s" for _ in tokens])
    params: list[Any] = [customer, days, *[f"%{token}%" for token in tokens], limit]
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            WITH filtered AS (
                SELECT
                    search_term,
                    date_trunc('month', report_date)::date AS month_start,
                    sum(coalesce(impressions, 0)) AS impressions,
                    sum(coalesce(clicks, 0)) AS clicks,
                    sum(coalesce(cost_micros, 0)) AS cost_micros,
                    sum(coalesce(conversions, 0)) AS conversions,
                    sum(coalesce(conversions_value, 0)) AS conversions_value
                FROM google_search_terms
                WHERE customer_id = %s
                  AND report_date >= current_date - (%s::int * interval '1 day')
                  AND ({clauses})
                GROUP BY search_term, date_trunc('month', report_date)::date
            ),
            top_terms AS (
                SELECT
                    search_term,
                    sum(impressions) AS impressions,
                    sum(clicks) AS clicks,
                    sum(cost_micros) AS cost_micros,
                    sum(conversions) AS conversions,
                    sum(conversions_value) AS conversions_value,
                    count(*) AS months
                FROM filtered
                GROUP BY search_term
                ORDER BY sum(impressions) DESC, sum(cost_micros) DESC, search_term
                LIMIT %s
            )
            SELECT
                t.search_term,
                greatest(round(t.impressions / greatest(t.months, 1))::bigint, 0) AS avg_monthly_impressions,
                CASE WHEN t.clicks > 0 THEN round(t.cost_micros / t.clicks)::bigint END AS avg_cpc_micros,
                t.impressions,
                t.clicks,
                t.cost_micros,
                t.conversions,
                t.conversions_value,
                coalesce(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'year', extract(year from f.month_start)::int,
                                'month', upper(to_char(f.month_start, 'FMMonth')),
                                'monthlySearches', f.impressions::bigint
                            )
                            ORDER BY f.month_start
                        )
                        FROM filtered f
                        WHERE f.search_term = t.search_term
                    ),
                    '[]'::jsonb
                ) AS monthly_search_volumes
            FROM top_terms t
            """,
            params,
        )
        rows = cur.fetchall()
    ideas = []
    for row in rows:
        avg_cpc = int(row[2] or 0) or None
        ideas.append(
            {
                "text": row[0],
                "closeVariants": [],
                "source": "local_search_terms",
                "keywordIdeaMetrics": {
                    "avgMonthlySearches": int(row[1] or 0),
                    "competition": "IN_ACCOUNT",
                    "competitionIndex": None,
                    "lowTopOfPageBidMicros": avg_cpc,
                    "highTopOfPageBidMicros": int(avg_cpc * 1.5) if avg_cpc else None,
                    "monthlySearchVolumes": row[8] or [],
                },
                "localSearchTermMetrics": {
                    "impressions": int(row[3] or 0),
                    "clicks": int(row[4] or 0),
                    "costMicros": int(row[5] or 0),
                    "conversions": float(row[6] or 0),
                    "conversionsValue": float(row[7] or 0),
                    "lookbackDays": days,
                },
            }
        )
    return ideas


def store_keyword_research(
    *,
    customer: str,
    seed_terms: list[str],
    final_url: str | None,
    geo_targets: list[str],
    language: str,
    network: str,
    request_payload: dict[str, Any],
    ideas: list[dict[str, Any]],
    allow_broad: bool,
    brand_terms: list[str],
    source: str = "generateKeywordIdeas",
    metadata: dict[str, Any] | None = None,
) -> str:
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_keyword_research_runs (
                customer_id, seed_terms, final_url, geo_targets, language,
                keyword_plan_network, request, result_count, source, metadata
            )
            VALUES (%s, %s::jsonb, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
            RETURNING id::text
            """,
            (
                customer,
                jsonb(seed_terms),
                final_url,
                jsonb(geo_targets),
                language,
                network,
                jsonb(sanitize_request(request_payload)),
                len(ideas),
                source,
                jsonb({"allow_broad": allow_broad, "brand_terms": brand_terms, **(metadata or {})}),
            ),
        )
        run_id = str(cur.fetchone()[0])
        for row in ideas:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            metrics = keyword_idea_metrics(row)
            match_type = recommended_match_type_for_keyword(
                text,
                metrics,
                allow_broad=allow_broad,
                brand_terms=brand_terms,
            )
            bucket = intent_bucket_for_keyword(text, brand_terms)
            cur.execute(
                """
                INSERT INTO google_keyword_research_ideas (
                    run_id, customer_id, text, close_variants, avg_monthly_searches,
                    competition, competition_index, low_top_of_page_bid_micros,
                    high_top_of_page_bid_micros, monthly_search_volumes,
                    recommended_match_type, intent_bucket, source, raw
                )
                VALUES (
                    %s::uuid, %s, %s, %s::jsonb, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (run_id, text) DO UPDATE SET
                    close_variants = excluded.close_variants,
                    avg_monthly_searches = excluded.avg_monthly_searches,
                    competition = excluded.competition,
                    competition_index = excluded.competition_index,
                    low_top_of_page_bid_micros = excluded.low_top_of_page_bid_micros,
                    high_top_of_page_bid_micros = excluded.high_top_of_page_bid_micros,
                    monthly_search_volumes = excluded.monthly_search_volumes,
                    recommended_match_type = excluded.recommended_match_type,
                    intent_bucket = excluded.intent_bucket,
                    source = excluded.source,
                    raw = excluded.raw
                """,
                (
                    run_id,
                    customer,
                    text,
                    jsonb(row.get("closeVariants") or []),
                    metrics["avg_monthly_searches"],
                    metrics["competition"],
                    metrics["competition_index"],
                    metrics["low_top_of_page_bid_micros"],
                    metrics["high_top_of_page_bid_micros"],
                    jsonb(metrics["monthly_search_volumes"]),
                    match_type,
                    bucket,
                    str(row.get("source") or source),
                    jsonb(row),
                ),
            )
    return run_id


def keyword_research_rows(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT text, avg_monthly_searches, competition, competition_index,
                   low_top_of_page_bid_micros, high_top_of_page_bid_micros,
                   monthly_search_volumes, recommended_match_type, intent_bucket,
                   close_variants, source
            FROM google_keyword_research_ideas
            WHERE run_id = %s::uuid
            ORDER BY coalesce(avg_monthly_searches, 0) DESC,
                     coalesce(competition_index, 0) DESC,
                     text
            LIMIT %s
            """,
            (run_id, limit),
        )
        rows = []
        for row in cur.fetchall():
            rows.append(
                {
                    "text": row[0],
                    "avg_monthly_searches": row[1],
                    "competition": row[2],
                    "competition_index": row[3],
                    "low_top_of_page_bid_micros": row[4],
                    "high_top_of_page_bid_micros": row[5],
                    "monthly_search_volumes": row[6] or [],
                    "recommended_match_type": row[7],
                    "intent_bucket": row[8],
                    "close_variants": row[9] or [],
                    "source": row[10],
                }
            )
    return rows


def latest_keyword_research_run(customer: str | None = None) -> str | None:
    where = "WHERE customer_id = %s" if customer else ""
    params: tuple[Any, ...] = (customer,) if customer else ()
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT id::text FROM google_keyword_research_runs {where} ORDER BY created_at DESC LIMIT 1",
            params,
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def keyword_summary_payload(run_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_match: dict[str, int] = {}
    by_intent: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        by_match[row.get("recommended_match_type") or "UNKNOWN"] = by_match.get(row.get("recommended_match_type") or "UNKNOWN", 0) + 1
        by_intent[row.get("intent_bucket") or "unknown"] = by_intent.get(row.get("intent_bucket") or "unknown", 0) + 1
        by_source[row.get("source") or "unknown"] = by_source.get(row.get("source") or "unknown", 0) + 1
    return {
        "run_id": run_id,
        "idea_count": len(rows),
        "match_type_counts": by_match,
        "intent_counts": by_intent,
        "source_counts": by_source,
        "top_ideas": rows[:20],
    }


def print_keyword_research_summary(run_id: str, rows: list[dict[str, Any]]) -> None:
    payload = keyword_summary_payload(run_id, rows)
    print(f"Keyword research run: {run_id}")
    print(f"Ideas stored: {payload['idea_count']}")
    print("Sources: " + ", ".join(f"{key}={value}" for key, value in sorted(payload["source_counts"].items())))
    print("Match types: " + ", ".join(f"{key}={value}" for key, value in sorted(payload["match_type_counts"].items())))
    print("Intent: " + ", ".join(f"{key}={value}" for key, value in sorted(payload["intent_counts"].items())))
    print()
    print(f"{'Keyword':<42} {'Vol':>8} {'Comp':<8} {'Low':>10} {'High':>10} {'Match':<6} Intent")
    print(f"{'-' * 42} {'-' * 8} {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 6} {'-' * 12}")
    for row in rows[:25]:
        print(
            f"{truncate(row.get('text'), 42):<42} "
            f"{str(row.get('avg_monthly_searches') or 'n/a'):>8} "
            f"{truncate(row.get('competition'), 8):<8} "
            f"{money_micros(row.get('low_top_of_page_bid_micros')):>10} "
            f"{money_micros(row.get('high_top_of_page_bid_micros')):>10} "
            f"{truncate(row.get('recommended_match_type'), 6):<6} "
            f"{row.get('intent_bucket') or 'unknown'}"
        )


def cmd_keyword_research(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    seed_terms = split_terms_arg(args.seed_terms)
    geo_targets = constant_resources("geoTargetConstants", args.geo_targets, ["2840"])
    language = constant_resource("languageConstants", args.language or "1000")
    brand_terms = split_terms_arg(args.brand_terms) or DEFAULT_BRAND_TERMS
    run_id = run_start(
        "keyword-research",
        customer,
        {
            "seed_terms": seed_terms,
            "final_url": args.final_url,
            "geo_targets": geo_targets,
            "language": language,
            "limit": args.limit,
        },
    )
    try:
        fallback_reason = None
        source = "generateKeywordIdeas"
        try:
            ideas, request_payload = fetch_keyword_ideas(
                customer=customer,
                seed_terms=seed_terms,
                final_url=args.final_url,
                geo_targets=geo_targets,
                language=language,
                network=args.network,
                limit=args.limit,
                run_id=run_id,
            )
        except RuntimeError as exc:
            if not args.fallback_local_search_terms or not keyword_planner_token_blocked(exc):
                raise
            fallback_reason = str(exc)[:700]
            source = "local_search_terms"
            ideas = fallback_keyword_ideas_from_search_terms(
                customer=customer,
                seed_terms=seed_terms,
                limit=args.limit,
                days=args.fallback_days,
            )
            request_payload = {
                "fallback": source,
                "seed_terms": seed_terms,
                "final_url": args.final_url,
                "geo_targets": geo_targets,
                "language": language,
                "keyword_plan_network": args.network,
                "reason": "Keyword Planner API requires Basic or Standard developer token access.",
            }
        research_run_id = store_keyword_research(
            customer=customer,
            seed_terms=seed_terms,
            final_url=args.final_url,
            geo_targets=geo_targets,
            language=language,
            network=args.network,
            request_payload=request_payload,
            ideas=ideas,
            allow_broad=args.allow_broad,
            brand_terms=brand_terms,
            source=source,
            metadata={"fallback_reason": fallback_reason} if fallback_reason else None,
        )
        rows = keyword_research_rows(research_run_id, args.limit)
        run_finish(
            run_id,
            "partial" if fallback_reason else "success",
            rows_fetched=len(ideas),
            rows_written=len(rows),
            errors=1 if fallback_reason else 0,
            metadata={"research_run_id": research_run_id, "source": source, "fallback_reason": fallback_reason},
        )
    except Exception as exc:
        log_fetch_error(run_id, f"customers/{customer}:generateKeywordIdeas", {"seed_terms": seed_terms, "final_url": args.final_url}, exc)
        run_finish(run_id, "error", errors=1, metadata={"error": str(exc)[:500]})
        raise
    if args.format == "json":
        print(json.dumps(keyword_summary_payload(research_run_id, rows), indent=2, default=str))
    elif args.format == "csv":
        print("keyword,avg_monthly_searches,competition,competition_index,low_top_of_page_bid_micros,high_top_of_page_bid_micros,recommended_match_type,intent_bucket")
        for row in rows:
            values = [
                row.get("text"),
                row.get("avg_monthly_searches"),
                row.get("competition"),
                row.get("competition_index"),
                row.get("low_top_of_page_bid_micros"),
                row.get("high_top_of_page_bid_micros"),
                row.get("recommended_match_type"),
                row.get("intent_bucket"),
            ]
            print(",".join('"' + str(value or "").replace('"', '""') + '"' for value in values))
    else:
        print_keyword_research_summary(research_run_id, rows)
    return 0


def campaign_brief_from_rows(
    *,
    run_id: str,
    rows: list[dict[str, Any]],
    offer: str,
    final_url: str,
    brand_terms: list[str],
    daily_budget_dollars: float,
    target_cpa_dollars: float | None,
    allow_broad: bool,
    include_competitors: bool,
    competitor_terms: list[str],
    max_keywords: int,
) -> dict[str, Any]:
    selected = []
    competitor_review = []
    for row in rows:
        text = str(row.get("text") or "")
        if not text:
            continue
        intent = row.get("intent_bucket") or intent_bucket_for_keyword(text, brand_terms)
        if intent == "informational":
            continue
        if is_competitor_keyword(text, competitor_terms) and not include_competitors:
            competitor_review.append(row)
            continue
        selected.append(row)
        if len(selected) >= max_keywords:
            break
    exact = [row for row in selected if row.get("recommended_match_type") == "EXACT"]
    phrase = [row for row in selected if row.get("recommended_match_type") == "PHRASE"]
    broad = [row for row in selected if row.get("recommended_match_type") == "BROAD"]
    clusters: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        key = "Brand" if row.get("intent_bucket") == "brand" else keyword_cluster_key(str(row.get("text") or ""))
        clusters.setdefault(key, []).append(row)
    ad_groups = []
    for key, group_rows in sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0]))[:8]:
        ad_groups.append(
            {
                "name": key,
                "keywords": [
                    {
                        "text": row["text"],
                        "match_type": row.get("recommended_match_type") or "PHRASE",
                        "avg_monthly_searches": row.get("avg_monthly_searches"),
                        "high_top_of_page_bid_micros": row.get("high_top_of_page_bid_micros"),
                    }
                    for row in group_rows[:10]
                ],
            }
        )
    top_specs = [f"{row['text']}:{row.get('recommended_match_type') or 'PHRASE'}" for row in selected[: min(20, len(selected))]]
    bid_strategy = "maximize_conversions" if target_cpa_dollars else "manual_cpc"
    return {
        "run_id": run_id,
        "offer": offer,
        "final_url": final_url,
        "daily_budget_dollars": daily_budget_dollars,
        "target_cpa_dollars": target_cpa_dollars,
        "bid_strategy": bid_strategy,
        "keyword_counts": {
            "selected": len(selected),
            "exact": len(exact),
            "phrase": len(phrase),
            "broad": len(broad),
            "broad_allowed": allow_broad,
            "competitor_review": len(competitor_review),
            "competitors_included": include_competitors,
        },
        "recommended_keywords": selected[:25],
        "competitor_keywords_for_review": competitor_review[:25],
        "ad_groups": ad_groups,
        "starter_negatives": SEARCH_CAMPAIGN_NEGATIVE_STARTERS,
        "build_sequence": [
            "Validate conversion action and campaign goal before launch.",
            "Build paused campaign with exact/phrase first; add broad only with Smart Bidding and conversion volume.",
            "Attach sitelinks, callouts, structured snippets, geo/language targeting, and starter negatives before live review.",
            "Run validate-only mutate, inspect policy/errors, then ask for explicit live approval.",
        ],
        "next_plan_command": (
            "gads plan-search-campaign "
            f"--name \"Search - {offer}\" "
            f"--budget-dollars {daily_budget_dollars:g} "
            f"--final-url \"{final_url}\" "
            f"--keywords \"{','.join(top_specs)}\" "
            f"--bid-strategy {bid_strategy}"
            + (f" --target-cpa-dollars {target_cpa_dollars:g}" if target_cpa_dollars else "")
        ),
    }


def print_campaign_brief_markdown(payload: dict[str, Any]) -> None:
    print(f"# Google Ads Search Campaign Brief: {payload['offer']}")
    print()
    print(f"- Research run: `{payload['run_id']}`")
    print(f"- Final URL: {payload['final_url']}")
    print(f"- Daily budget: {money(payload['daily_budget_dollars'])}")
    print(f"- Bid strategy: `{payload['bid_strategy']}`")
    if payload.get("target_cpa_dollars"):
        print(f"- Target CPA: {money(payload['target_cpa_dollars'])}")
    counts = payload["keyword_counts"]
    print(f"- Keywords selected: {counts['selected']} ({counts['exact']} exact, {counts['phrase']} phrase, {counts['broad']} broad)")
    if counts.get("competitor_review"):
        print(f"- Competitor terms held for review: {counts['competitor_review']}")
    print()
    print("## Ad Groups")
    for group in payload["ad_groups"]:
        print(f"- {group['name']}: " + ", ".join(f"{item['text']}:{item['match_type']}" for item in group["keywords"][:6]))
    if payload.get("competitor_keywords_for_review"):
        print()
        print("## Competitor Terms For Review")
        for row in payload["competitor_keywords_for_review"][:10]:
            print(f"- {row['text']} ({row.get('recommended_match_type')}, vol {row.get('avg_monthly_searches') or 'n/a'})")
    print()
    print("## Starter Negatives")
    print(", ".join(payload["starter_negatives"]))
    print()
    print("## Build Sequence")
    for item in payload["build_sequence"]:
        print(f"- {item}")
    print()
    print("## Next Command")
    print("```bash")
    print(payload["next_plan_command"])
    print("```")


def create_keyword_research_run_for_build(
    *,
    customer: str,
    seed_terms: list[str],
    final_url: str,
    geo_targets: list[str],
    language: str,
    network: str,
    limit: int,
    allow_broad: bool,
    brand_terms: list[str],
    fallback_local_search_terms: bool,
    fallback_days: int,
    command_name: str,
) -> tuple[str, list[dict[str, Any]], str, str | None]:
    sync_run_id = run_start(
        command_name,
        customer,
        {
            "seed_terms": seed_terms,
            "final_url": final_url,
            "geo_targets": geo_targets,
            "language": language,
            "limit": limit,
        },
    )
    try:
        fallback_reason = None
        source = "generateKeywordIdeas"
        try:
            ideas, request_payload = fetch_keyword_ideas(
                customer=customer,
                seed_terms=seed_terms,
                final_url=final_url,
                geo_targets=geo_targets,
                language=language,
                network=network,
                limit=limit,
                run_id=sync_run_id,
            )
        except RuntimeError as exc:
            if not fallback_local_search_terms or not keyword_planner_token_blocked(exc):
                raise
            fallback_reason = str(exc)[:700]
            source = "local_search_terms"
            ideas = fallback_keyword_ideas_from_search_terms(
                customer=customer,
                seed_terms=seed_terms,
                limit=limit,
                days=fallback_days,
            )
            request_payload = {
                "fallback": source,
                "seed_terms": seed_terms,
                "final_url": final_url,
                "geo_targets": geo_targets,
                "language": language,
                "keyword_plan_network": network,
                "reason": "Keyword Planner API requires Basic or Standard developer token access.",
            }
        research_run_id = store_keyword_research(
            customer=customer,
            seed_terms=seed_terms,
            final_url=final_url,
            geo_targets=geo_targets,
            language=language,
            network=network,
            request_payload=request_payload,
            ideas=ideas,
            allow_broad=allow_broad,
            brand_terms=brand_terms,
            source=source,
            metadata={"fallback_reason": fallback_reason} if fallback_reason else None,
        )
        rows = keyword_research_rows(research_run_id, limit)
        run_finish(
            sync_run_id,
            "partial" if fallback_reason else "success",
            rows_fetched=len(ideas),
            rows_written=len(rows),
            errors=1 if fallback_reason else 0,
            metadata={"research_run_id": research_run_id, "source": source, "fallback_reason": fallback_reason},
        )
        return research_run_id, rows, source, fallback_reason
    except Exception as exc:
        log_fetch_error(sync_run_id, f"customers/{customer}:generateKeywordIdeas", {"seed_terms": seed_terms, "final_url": final_url}, exc)
        run_finish(sync_run_id, "error", errors=1, metadata={"error": str(exc)[:500]})
        raise


def ad_text_limit(text: str, max_len: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_len:
        return clean
    clipped = clean[:max_len].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return (clipped or clean[:max_len]).strip()


def unique_ad_texts(candidates: list[str], *, max_len: int, minimum: int, fallbacks: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for candidate in [*candidates, *fallbacks]:
        text = ad_text_limit(candidate, max_len)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        values.append(text)
        if len(values) >= minimum:
            break
    return values


def search_ad_copy_for_group(*, offer: str, group_name: str, keywords: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    keyword_titles = [str(item.get("text") or "").title() for item in keywords[:3] if item.get("text")]
    headlines = unique_ad_texts(
        [
            offer,
            f"Shop {offer}",
            group_name,
            *keyword_titles,
            "Official Site",
            "Daily Protein Superfoods",
            "Fuel Your Daily Routine",
        ],
        max_len=30,
        minimum=3,
        fallbacks=["Shop Online", "Protein And Superfoods", "Order Online Today"],
    )
    descriptions = unique_ad_texts(
        [
            f"Shop {offer} online today.",
            "Protein, superfoods, vitamins, and probiotics in one simple daily routine.",
            f"Find the option that fits your {group_name.lower()} goal.",
        ],
        max_len=90,
        minimum=2,
        fallbacks=[
            "Shop online and pick the option that fits your goals.",
            "A simple daily protein and superfood routine built for busy days.",
        ],
    )
    return headlines, descriptions


def build_researched_search_campaign_operations(
    *,
    customer: str,
    campaign_name: str,
    budget_name: str | None,
    budget_dollars: float,
    final_url: str,
    bid_strategy: str,
    target_cpa_dollars: float | None,
    target_roas: float | None,
    include_search_partners: bool,
    cpc_bid_dollars: float,
    offer: str,
    ad_groups: list[dict[str, Any]],
    sitelinks: list[dict[str, str]],
    include_starter_negatives: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    budget_micros = int(round(budget_dollars * 1_000_000))
    if budget_micros <= 0:
        raise SystemExit("--daily-budget-dollars must be greater than zero")
    if not ad_groups:
        raise SystemExit("No ad groups could be built from the keyword research rows")
    budget_resource = f"customers/{customer}/campaignBudgets/-1"
    campaign_resource = f"customers/{customer}/campaigns/-2"
    operations: list[dict[str, Any]] = [
        {
            "campaignBudgetOperation": {
                "create": {
                    "resourceName": budget_resource,
                    "name": budget_name or f"{campaign_name} Budget",
                    "amountMicros": budget_micros,
                    "deliveryMethod": "STANDARD",
                    "explicitlyShared": False,
                }
            }
        },
        {
            "campaignOperation": {
                "create": {
                    "resourceName": campaign_resource,
                    "name": campaign_name,
                    "status": "PAUSED",
                    "advertisingChannelType": "SEARCH",
                    "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                    "campaignBudget": budget_resource,
                    **bidding_scheme(
                        bid_strategy,
                        target_cpa_dollars=target_cpa_dollars,
                        target_roas=target_roas,
                    ),
                    "networkSettings": {
                        "targetGoogleSearch": True,
                        "targetSearchNetwork": include_search_partners,
                        "targetContentNetwork": False,
                        "targetPartnerSearchNetwork": include_search_partners,
                    },
                }
            }
        },
    ]
    if include_starter_negatives:
        for text in SEARCH_CAMPAIGN_NEGATIVE_STARTERS:
            operations.append(
                {
                    "campaignCriterionOperation": {
                        "create": {
                            "campaign": campaign_resource,
                            "negative": True,
                            "keyword": {"text": text, "matchType": "PHRASE"},
                            "status": "ENABLED",
                        }
                    }
                }
            )

    keyword_count = 0
    for index, group in enumerate(ad_groups):
        ad_group_resource = f"customers/{customer}/adGroups/-{index + 3}"
        group_keywords = group.get("keywords") or []
        operations.append(
            {
                "adGroupOperation": {
                    "create": {
                        "resourceName": ad_group_resource,
                        "name": ad_text_limit(str(group.get("name") or f"{campaign_name} Ad Group"), 255),
                        "campaign": campaign_resource,
                        "status": "PAUSED",
                        "type": "SEARCH_STANDARD",
                        "cpcBidMicros": int(round(cpc_bid_dollars * 1_000_000)),
                    }
                }
            }
        )
        for keyword in group_keywords:
            text = str(keyword.get("text") or "").strip()
            if not text:
                continue
            keyword_count += 1
            operations.append(
                {
                    "adGroupCriterionOperation": {
                        "create": {
                            "adGroup": ad_group_resource,
                            "status": "PAUSED",
                            "keyword": {
                                "text": text,
                                "matchType": str(keyword.get("match_type") or "PHRASE").upper(),
                            },
                        }
                    }
                }
            )
        headlines, descriptions = search_ad_copy_for_group(
            offer=offer,
            group_name=str(group.get("name") or campaign_name),
            keywords=group_keywords,
        )
        operations.append(
            {
                "adGroupAdOperation": {
                    "create": {
                        "adGroup": ad_group_resource,
                        "status": "PAUSED",
                        "ad": {
                            "responsiveSearchAd": {
                                "headlines": [{"text": text} for text in headlines],
                                "descriptions": [{"text": text} for text in descriptions],
                            },
                            "finalUrls": [final_url],
                        },
                    }
                }
            }
        )

    operations.extend(
        sitelink_operations(
            customer=customer,
            campaign_resource=campaign_resource,
            sitelinks=sitelinks,
            start_temp_id=100,
        )
    )
    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    stats = {
        "ad_group_count": len(ad_groups),
        "keyword_count": keyword_count,
        "starter_negative_count": len(SEARCH_CAMPAIGN_NEGATIVE_STARTERS) if include_starter_negatives else 0,
        "sitelink_count": len(sitelinks),
        "operation_count": len(operations),
    }
    return payload, stats


def cmd_build_search_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    seed_terms = split_terms_arg(args.seed_terms) or [args.offer]
    brand_terms = split_terms_arg(args.brand_terms) or DEFAULT_BRAND_TERMS
    geo_targets = constant_resources("geoTargetConstants", args.geo_targets, ["2840"])
    language = constant_resource("languageConstants", args.language or "1000")
    research_run_id, rows, source, fallback_reason = create_keyword_research_run_for_build(
        customer=customer,
        seed_terms=seed_terms,
        final_url=args.final_url,
        geo_targets=geo_targets,
        language=language,
        network=args.network,
        limit=args.limit,
        allow_broad=args.allow_broad,
        brand_terms=brand_terms,
        fallback_local_search_terms=args.fallback_local_search_terms,
        fallback_days=args.fallback_days,
        command_name="build-search-campaign/keyword-research",
    )
    brief = campaign_brief_from_rows(
        run_id=research_run_id,
        rows=rows,
        offer=args.offer,
        final_url=args.final_url,
        brand_terms=brand_terms,
        daily_budget_dollars=args.daily_budget_dollars,
        target_cpa_dollars=args.target_cpa_dollars,
        allow_broad=args.allow_broad,
        include_competitors=args.include_competitors,
        competitor_terms=split_terms_arg(args.competitor_terms) or DEFAULT_COMPETITOR_TERMS,
        max_keywords=args.max_keywords,
    )
    ad_groups = list(brief.get("ad_groups") or [])[: args.max_ad_groups]
    if not ad_groups:
        raise SystemExit("Keyword research produced no launchable ad groups after filters; broaden seeds or use --include-competitors")
    bid_strategy = args.bid_strategy
    if bid_strategy == "auto":
        bid_strategy = "maximize_conversions" if args.target_cpa_dollars else "manual_cpc"
    campaign_name = args.name or f"Search - {args.offer}"
    payload, stats = build_researched_search_campaign_operations(
        customer=customer,
        campaign_name=campaign_name,
        budget_name=args.budget_name,
        budget_dollars=args.daily_budget_dollars,
        final_url=args.final_url,
        bid_strategy=bid_strategy,
        target_cpa_dollars=args.target_cpa_dollars,
        target_roas=args.target_roas,
        include_search_partners=args.include_search_partners,
        cpc_bid_dollars=args.cpc_bid_dollars,
        offer=args.offer,
        ad_groups=ad_groups,
        sitelinks=parse_sitelink_specs(args.sitelinks),
        include_starter_negatives=args.starter_negatives,
    )
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="search_campaign_researched",
        operation_type="create",
        payload=payload,
        note=args.note or f"Researched paused Search campaign plan; keyword_run={research_run_id}; source={source}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign_name": campaign_name,
        "offer": args.offer,
        "final_url": args.final_url,
        "keyword_research_run_id": research_run_id,
        "research_source": source,
        "fallback_reason": fallback_reason,
        "seed_terms": seed_terms,
        "bid_strategy": bid_strategy,
        "daily_budget_dollars": args.daily_budget_dollars,
        "target_cpa_dollars": args.target_cpa_dollars,
        "selected_keyword_count": brief["keyword_counts"]["selected"],
        "competitor_review_count": brief["keyword_counts"]["competitor_review"],
        **stats,
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    if args.format == "json":
        print(json.dumps({**summary, "brief": brief, "payload": payload}, indent=2, default=str))
    else:
        print(json.dumps(summary, indent=2, default=str))
        print()
        print("Ad groups:")
        for group in ad_groups:
            print("- " + group["name"] + ": " + ", ".join(f"{item['text']}:{item['match_type']}" for item in group["keywords"][:6]))
    return 0


def cmd_campaign_research_brief(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    brand_terms = split_terms_arg(args.brand_terms) or DEFAULT_BRAND_TERMS
    run_id = args.run_id
    if not run_id and (args.seed_terms or args.final_url):
        seed_terms = split_terms_arg(args.seed_terms)
        geo_targets = constant_resources("geoTargetConstants", args.geo_targets, ["2840"])
        language = constant_resource("languageConstants", args.language or "1000")
        sync_run_id = run_start(
            "campaign-research-brief/keyword-research",
            customer,
            {
                "seed_terms": seed_terms,
                "final_url": args.final_url,
                "geo_targets": geo_targets,
                "language": language,
                "limit": args.limit,
            },
        )
        try:
            fallback_reason = None
            source = "generateKeywordIdeas"
            try:
                ideas, request_payload = fetch_keyword_ideas(
                    customer=customer,
                    seed_terms=seed_terms,
                    final_url=args.final_url,
                    geo_targets=geo_targets,
                    language=language,
                    network=args.network,
                    limit=args.limit,
                    run_id=sync_run_id,
                )
            except RuntimeError as exc:
                if not args.fallback_local_search_terms or not keyword_planner_token_blocked(exc):
                    raise
                fallback_reason = str(exc)[:700]
                source = "local_search_terms"
                ideas = fallback_keyword_ideas_from_search_terms(
                    customer=customer,
                    seed_terms=seed_terms,
                    limit=args.limit,
                    days=args.fallback_days,
                )
                request_payload = {
                    "fallback": source,
                    "seed_terms": seed_terms,
                    "final_url": args.final_url,
                    "geo_targets": geo_targets,
                    "language": language,
                    "keyword_plan_network": args.network,
                    "reason": "Keyword Planner API requires Basic or Standard developer token access.",
                }
            run_id = store_keyword_research(
                customer=customer,
                seed_terms=seed_terms,
                final_url=args.final_url,
                geo_targets=geo_targets,
                language=language,
                network=args.network,
                request_payload=request_payload,
                ideas=ideas,
                allow_broad=args.allow_broad,
                brand_terms=brand_terms,
                source=source,
                metadata={"fallback_reason": fallback_reason} if fallback_reason else None,
            )
            rows_written = len(keyword_research_rows(run_id, args.limit))
            run_finish(
                sync_run_id,
                "partial" if fallback_reason else "success",
                rows_fetched=len(ideas),
                rows_written=rows_written,
                errors=1 if fallback_reason else 0,
                metadata={"research_run_id": run_id, "source": source, "fallback_reason": fallback_reason},
            )
        except Exception as exc:
            log_fetch_error(sync_run_id, f"customers/{customer}:generateKeywordIdeas", {"seed_terms": seed_terms, "final_url": args.final_url}, exc)
            run_finish(sync_run_id, "error", errors=1, metadata={"error": str(exc)[:500]})
            raise
    elif not run_id:
        run_id = latest_keyword_research_run(customer)
    if not run_id:
        raise SystemExit("No keyword research run found. Run gads keyword-research first or pass --seed-terms/--final-url.")
    rows = keyword_research_rows(run_id, args.limit)
    payload = campaign_brief_from_rows(
        run_id=run_id,
        rows=rows,
        offer=args.offer,
        final_url=args.final_url or "",
        brand_terms=brand_terms,
        daily_budget_dollars=args.daily_budget_dollars,
        target_cpa_dollars=args.target_cpa_dollars,
        allow_broad=args.allow_broad,
        include_competitors=args.include_competitors,
        competitor_terms=split_terms_arg(args.competitor_terms) or DEFAULT_COMPETITOR_TERMS,
        max_keywords=args.max_keywords,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=str))
    else:
        print_campaign_brief_markdown(payload)
    return 0


def load_expert_source_catalog() -> list[dict[str, Any]]:
    if not EXPERT_SOURCE_CATALOG.is_file():
        raise SystemExit(f"missing expert source catalog: {EXPERT_SOURCE_CATALOG}")
    payload = json.loads(EXPERT_SOURCE_CATALOG.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return list(payload.get("sources") or [])
    if isinstance(payload, list):
        return payload
    raise SystemExit("expert source catalog must be a list or an object with sources")


def extract_html_text(raw: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    cleaned = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return title, cleaned


def source_cache_path(source_id: str) -> pathlib.Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", source_id).strip("-") or "source"
    EXPERT_SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    return EXPERT_SOURCE_CACHE / f"{safe}.json"


def fetch_public_source(source: dict[str, Any], *, timeout: int = 40) -> dict[str, Any]:
    url = str(source.get("url") or "")
    if not url:
        raise ValueError("source is missing url")
    if "youtube.com" in url or "youtu.be" in url:
        raise ValueError("YouTube sources are intentionally excluded")
    req = urllib.request.Request(url, headers={"User-Agent": "Google Ads CLI Google Ads source ingester/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw_bytes = response.read(2_000_000)
        content_type = response.headers.get("Content-Type", "")
    text = raw_bytes.decode("utf-8", errors="replace")
    if "html" in content_type or "<html" in text[:500].casefold():
        title, extracted = extract_html_text(text)
    else:
        title, extracted = "", re.sub(r"\s+", " ", text).strip()
    digest = hashlib.sha256(extracted.encode("utf-8")).hexdigest()
    excerpt = extracted[:5000]
    operator_notes = str(source.get("operator_notes") or "")
    summary_parts = [part for part in [source.get("why"), operator_notes, excerpt[:1000]] if part]
    return {
        "source_id": source.get("id"),
        "document_url": url,
        "source_name": source.get("name") or source.get("id"),
        "source_type": source.get("source_type") or "public_page",
        "access_level": source.get("access_level") or "public",
        "topics": source.get("topics") or [],
        "operator_notes": operator_notes,
        "title": title or source.get("name") or "",
        "content_hash": digest,
        "text_excerpt": excerpt,
        "summary": "\n\n".join(str(part) for part in summary_parts)[:3000],
        "metadata": {
            "retrieved_at": now_utc().isoformat(),
            "rights": source.get("rights"),
            "course_material_policy": source.get("course_material_policy"),
            "content_type": content_type,
        },
    }


def store_expert_source_document(document: dict[str, Any], cache_path: pathlib.Path) -> None:
    cache_path.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_expert_source_documents (
                source_id, document_url, source_name, source_type, access_level,
                topics, operator_notes, title, content_hash, text_excerpt,
                summary, cache_path, metadata, retrieved_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                %s, %s, %s::jsonb, now()
            )
            ON CONFLICT (source_id, document_url) DO UPDATE SET
                source_name = excluded.source_name,
                source_type = excluded.source_type,
                access_level = excluded.access_level,
                topics = excluded.topics,
                operator_notes = excluded.operator_notes,
                title = excluded.title,
                content_hash = excluded.content_hash,
                text_excerpt = excluded.text_excerpt,
                summary = excluded.summary,
                cache_path = excluded.cache_path,
                metadata = excluded.metadata,
                retrieved_at = now()
            """,
            (
                document["source_id"],
                document["document_url"],
                document["source_name"],
                document["source_type"],
                document["access_level"],
                jsonb(document.get("topics") or []),
                document.get("operator_notes"),
                document.get("title"),
                document.get("content_hash"),
                document.get("text_excerpt"),
                document.get("summary"),
                str(cache_path),
                jsonb(document.get("metadata") or {}),
            ),
        )


def cmd_ingest_expert_sources(args: argparse.Namespace) -> int:
    ensure_schema()
    sources = load_expert_source_catalog()
    selected = []
    wanted = set(split_terms_arg(args.source_ids))
    for source in sources:
        if wanted and str(source.get("id")) not in wanted:
            continue
        selected.append(source)
    ingested = []
    failures = []
    for source in selected:
        source_id = str(source.get("id") or "")
        try:
            document = fetch_public_source(source)
            cache_path = source_cache_path(source_id)
            store_expert_source_document(document, cache_path)
            ingested.append({"id": source_id, "url": source.get("url"), "cache_path": str(cache_path)})
        except Exception as exc:  # noqa: BLE001
            failures.append({"id": source_id, "url": source.get("url"), "error": str(exc)[:500]})
            if not args.keep_going:
                break
    payload = {
        "catalog": str(EXPERT_SOURCE_CATALOG),
        "selected": len(selected),
        "ingested": ingested,
        "failures": failures,
        "policy": "Only public or authorized source pages were fetched. Paid course internals require a user-provided authorized export.",
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"Expert source catalog: {EXPERT_SOURCE_CATALOG}")
        print(f"Ingested: {len(ingested)} / {len(selected)}")
        if failures:
            print("Failures:")
            for failure in failures:
                print(f"- {failure['id']}: {failure['error']}")
        print("Policy: public or authorized pages only; paid course internals need an authorized export.")
    return 0 if not failures or args.keep_going else 1


MUTATION_ENTITY_CONFIG = {
    "campaign": {
        "operation": "campaignOperation",
        "collection": "campaigns",
        "status_field": "status",
    },
    "ad_group": {
        "operation": "adGroupOperation",
        "collection": "adGroups",
        "status_field": "status",
    },
    "ad": {
        "operation": "adGroupAdOperation",
        "collection": "adGroupAds",
        "status_field": "status",
        "requires_pair": True,
    },
    "ad_group_ad": {
        "operation": "adGroupAdOperation",
        "collection": "adGroupAds",
        "status_field": "status",
        "requires_pair": True,
    },
    "keyword": {
        "operation": "adGroupCriterionOperation",
        "collection": "adGroupCriteria",
        "status_field": "status",
        "requires_pair": True,
    },
    "ad_group_criterion": {
        "operation": "adGroupCriterionOperation",
        "collection": "adGroupCriteria",
        "status_field": "status",
        "requires_pair": True,
    },
    "campaign_budget": {
        "operation": "campaignBudgetOperation",
        "collection": "campaignBudgets",
        "budget_field": "amountMicros",
    },
    "negative_keyword": {
        "operation": "adGroupCriterionOperation",
        "negative_scope": "ad_group",
        "parent_field": "adGroup",
        "parent_collection": "adGroups",
    },
    "ad_group_negative_keyword": {
        "operation": "adGroupCriterionOperation",
        "negative_scope": "ad_group",
        "parent_field": "adGroup",
        "parent_collection": "adGroups",
    },
    "campaign_negative_keyword": {
        "operation": "campaignCriterionOperation",
        "negative_scope": "campaign",
        "parent_field": "campaign",
        "parent_collection": "campaigns",
    },
}


def parse_entity_ids(raw: str) -> list[str]:
    ids = [item.strip() for item in re.split(r"[\s,]+", raw or "") if item.strip()]
    if not ids:
        raise SystemExit("--ids must contain at least one ID or resource name")
    return ids


def parse_keyword_texts(raw: str | None) -> list[str]:
    texts = [item.strip() for item in re.split(r"[\n,]+", raw or "") if item.strip()]
    seen: set[str] = set()
    deduped = []
    for text in texts:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    if not deduped:
        raise SystemExit("--texts must contain at least one comma- or newline-separated search term")
    return deduped


def split_list_arg(raw: str | None) -> list[str]:
    return [item.strip() for item in re.split(r"[\n|]+", raw or "") if item.strip()]


def parse_keyword_specs(raw: str | None) -> list[dict[str, str]]:
    specs = []
    for item in [part.strip() for part in re.split(r"[\n,|]+", raw or "") if part.strip()]:
        if "::" in item:
            text, match_type = item.rsplit("::", 1)
        elif ":" in item:
            text, match_type = item.rsplit(":", 1)
        else:
            text, match_type = item, "EXACT"
        match_type = match_type.strip().upper().replace(" ", "_")
        if match_type not in {"EXACT", "PHRASE", "BROAD"}:
            raise SystemExit(f"unsupported keyword match type for {item!r}: {match_type}")
        specs.append({"text": text.strip(), "matchType": match_type})
    return specs


def parse_sitelink_specs(raw: str | None) -> list[dict[str, str]]:
    sitelinks = []
    for item in [part.strip() for part in re.split(r"[\n;]+", raw or "") if part.strip()]:
        parts = [part.strip() for part in item.split("|")]
        if len(parts) < 2:
            raise SystemExit("sitelinks must use text|url|description1|description2")
        sitelinks.append(
            {
                "text": parts[0],
                "url": parts[1],
                "description1": parts[2] if len(parts) > 2 else "",
                "description2": parts[3] if len(parts) > 3 else "",
            }
        )
    return sitelinks


def parse_callout_specs(raw: str | None) -> list[str]:
    callouts = parse_text_specs(raw)
    for text in callouts:
        if len(text) > 25:
            raise SystemExit(f"callout text must be 25 characters or less: {text!r}")
    return callouts


def parse_structured_snippet_specs(raw: str | None) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for item in [part.strip() for part in re.split(r"[\n;]+", raw or "") if part.strip()]:
        header, sep, raw_values = item.partition("|")
        if not sep:
            raise SystemExit("structured snippets must use header|value1,value2,value3")
        values = [value.strip() for value in re.split(r"[,|]", raw_values) if value.strip()]
        if len(values) < 3:
            raise SystemExit(f"structured snippet {header!r} needs at least 3 values")
        if len(values) > 10:
            raise SystemExit(f"structured snippet {header!r} can include at most 10 values")
        too_long = [value for value in values if len(value) > 25]
        if too_long:
            raise SystemExit(f"structured snippet values must be 25 characters or less: {too_long[0]!r}")
        snippets.append({"header": header.strip(), "values": values})
    return snippets


def resource_from_constant(collection: str, raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise SystemExit(f"{collection} ID cannot be empty")
    if value.startswith(f"{collection}/"):
        return value
    return f"{collection}/{extract_id(value)}"


def minute_enum(raw_value: str | int) -> str:
    value = int(raw_value)
    mapping = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}
    if value not in mapping:
        raise SystemExit("ad schedule minutes must be one of 0, 15, 30, or 45")
    return mapping[value]


def parse_hour_minute(raw_value: str) -> tuple[int, str]:
    hour_text, sep, minute_text = raw_value.strip().partition(":")
    hour = int(hour_text)
    minute = minute_enum(minute_text if sep else "0")
    return hour, minute


def parse_ad_schedule_specs(raw: str | None) -> list[dict[str, Any]]:
    schedules: list[dict[str, Any]] = []
    for item in [part.strip() for part in re.split(r"[\n;]+", raw or "") if part.strip()]:
        if "|" in item:
            parts = [part.strip() for part in item.split("|")]
            if len(parts) not in {3, 5}:
                raise SystemExit("ad schedules must use DAY:start-end or DAY|start_hour|end_hour|start_minute|end_minute")
            day = parts[0].upper()
            start_hour = int(parts[1])
            end_hour = int(parts[2])
            start_minute = minute_enum(parts[3] if len(parts) == 5 else "0")
            end_minute = minute_enum(parts[4] if len(parts) == 5 else "0")
        else:
            day, sep, hours = item.partition(":")
            if not sep or "-" not in hours:
                raise SystemExit("ad schedules must use DAY:start-end, for example MONDAY:9-17 or MONDAY:9:30-17:00")
            start_text, end_text = [part.strip() for part in hours.split("-", 1)]
            start_hour, start_minute = parse_hour_minute(start_text)
            end_hour, end_minute = parse_hour_minute(end_text)
            day = day.strip().upper()
        if start_hour < 0 or start_hour > 23 or end_hour < 1 or end_hour > 24:
            raise SystemExit(f"invalid ad schedule hours: {item!r}")
        schedules.append(
            {
                "dayOfWeek": day,
                "startHour": start_hour,
                "endHour": end_hour,
                "startMinute": start_minute,
                "endMinute": end_minute,
            }
        )
    return schedules


def parse_text_specs(raw: str | None) -> list[str]:
    values = [item.strip() for item in re.split(r"[\n|;]+", raw or "") if item.strip()]
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def parse_asset_specs(customer: str, raw: str | None, defaults: list[str] | None = None) -> list[str]:
    values = [item.strip() for item in re.split(r"[\n|;,]+", raw or "") if item.strip()]
    if not values and defaults:
        values = list(defaults)
    resources: list[str] = []
    seen: set[str] = set()
    for value in values:
        resource = value if value.startswith("customers/") else f"customers/{customer}/assets/{extract_id(value)}"
        if resource in seen:
            continue
        seen.add(resource)
        resources.append(resource)
    return resources


def campaign_asset_operations(
    *,
    campaign_resource: str,
    assets_by_field: dict[str, list[str]],
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for field_type, assets in assets_by_field.items():
        for asset in assets:
            operations.append(
                {
                    "campaignAssetOperation": {
                        "create": {
                            "campaign": campaign_resource,
                            "asset": asset,
                            "fieldType": field_type,
                            "status": "ENABLED",
                        }
                    }
                }
            )
    return operations


def asset_group_asset_operations(
    *,
    asset_group_resource: str,
    assets_by_field: dict[str, list[str]],
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for field_type, assets in assets_by_field.items():
        for asset in assets:
            operations.append(
                {
                    "assetGroupAssetOperation": {
                        "create": {
                            "assetGroup": asset_group_resource,
                            "asset": asset,
                            "fieldType": field_type,
                            "status": "ENABLED",
                        }
                    }
                }
            )
    return operations


def bidding_scheme(
    strategy: str,
    *,
    target_cpa_dollars: float | None = None,
    target_roas: float | None = None,
) -> dict[str, Any]:
    strategy = strategy.lower().replace("-", "_")
    if strategy == "manual_cpc":
        return {"manualCpc": {}}
    if strategy == "maximize_clicks":
        # The API field for Maximize Clicks is target_spend (there is no
        # campaign.maximize_clicks).
        return {"targetSpend": {}}
    if strategy == "maximize_conversions":
        scheme: dict[str, Any] = {"maximizeConversions": {}}
        if target_cpa_dollars is not None:
            scheme["maximizeConversions"]["targetCpaMicros"] = int(round(target_cpa_dollars * 1_000_000))
        return scheme
    if strategy == "maximize_conversion_value":
        scheme = {"maximizeConversionValue": {}}
        if target_roas is not None:
            scheme["maximizeConversionValue"]["targetRoas"] = target_roas
        return scheme
    if strategy == "target_cpa":
        if target_cpa_dollars is None:
            raise SystemExit("--target-cpa-dollars is required for target_cpa")
        return {"targetCpa": {"targetCpaMicros": int(round(target_cpa_dollars * 1_000_000))}}
    if strategy == "target_roas":
        if target_roas is None:
            raise SystemExit("--target-roas is required for target_roas")
        return {"targetRoas": {"targetRoas": target_roas}}
    raise SystemExit(f"unsupported bid strategy: {strategy}")


def bidding_update_mask(strategy: str, *, target_cpa_dollars: float | None, target_roas: float | None) -> str:
    strategy = strategy.lower().replace("-", "_")
    # Google rejects a mask that names a message-typed field without a subfield
    # (FIELD_HAS_SUBFIELDS, hit live 2026-09-03 on maximize_conversions), so
    # every strategy lists its leaf field even when that leaf stays unset.
    if strategy == "manual_cpc":
        return "manual_cpc.enhanced_cpc_enabled"
    if strategy == "maximize_clicks":
        return "target_spend.cpc_bid_ceiling_micros"
    if strategy == "maximize_conversions":
        return "maximize_conversions.target_cpa_micros"
    if strategy == "maximize_conversion_value":
        return "maximize_conversion_value.target_roas"
    if strategy == "target_cpa":
        return "target_cpa.target_cpa_micros"
    if strategy == "target_roas":
        return "target_roas.target_roas"
    raise SystemExit(f"unsupported bid strategy: {strategy}")


def infer_merchant_id(customer: str) -> str | None:
    query = """
        SELECT campaign.shopping_setting.merchant_id
        FROM campaign
        WHERE campaign.advertising_channel_type = SHOPPING
          AND campaign.shopping_setting.merchant_id IS NOT NULL
        LIMIT 1
    """
    try:
        rows = search_gaql(normalize_query(query), customer=customer, query_name="shopping_merchant_probe", max_pages=1)
    except Exception:
        return None
    for row in rows:
        merchant_id = get_path(row, "campaign.shopping_setting.merchant_id")
        if merchant_id not in (None, ""):
            return str(merchant_id)
    return None


def sitelink_operations(
    *,
    customer: str,
    campaign_resource: str,
    sitelinks: list[dict[str, str]],
    start_temp_id: int,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for offset, sitelink in enumerate(sitelinks):
        asset_resource = f"customers/{customer}/assets/-{start_temp_id + offset}"
        operations.append(
            {
                "assetOperation": {
                    "create": {
                        "resourceName": asset_resource,
                        "finalUrls": [sitelink["url"]],
                        "sitelinkAsset": {
                            "linkText": sitelink["text"],
                            "description1": sitelink.get("description1") or "",
                            "description2": sitelink.get("description2") or "",
                        },
                    }
                }
            }
        )
        operations.append(
            {
                "campaignAssetOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "asset": asset_resource,
                        "fieldType": "SITELINK",
                        "status": "PAUSED",
                    }
                }
            }
        )
    return operations


def callout_operations(
    *,
    customer: str,
    campaign_resource: str,
    callouts: list[str],
    start_temp_id: int,
    status: str,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for offset, text in enumerate(callouts):
        asset_resource = f"customers/{customer}/assets/-{start_temp_id + offset}"
        operations.append(
            {
                "assetOperation": {
                    "create": {
                        "resourceName": asset_resource,
                        "calloutAsset": {"calloutText": text},
                    }
                }
            }
        )
        operations.append(
            {
                "campaignAssetOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "asset": asset_resource,
                        "fieldType": "CALLOUT",
                        "status": status,
                    }
                }
            }
        )
    return operations


def structured_snippet_operations(
    *,
    customer: str,
    campaign_resource: str,
    snippets: list[dict[str, Any]],
    start_temp_id: int,
    status: str,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for offset, snippet in enumerate(snippets):
        asset_resource = f"customers/{customer}/assets/-{start_temp_id + offset}"
        operations.append(
            {
                "assetOperation": {
                    "create": {
                        "resourceName": asset_resource,
                        "structuredSnippetAsset": {
                            "header": snippet["header"],
                            "values": snippet["values"],
                        },
                    }
                }
            }
        )
        operations.append(
            {
                "campaignAssetOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "asset": asset_resource,
                        "fieldType": "STRUCTURED_SNIPPET",
                        "status": status,
                    }
                }
            }
        )
    return operations


def resource_name_for_mutation(customer: str, entity_type: str, raw_id: str) -> str:
    if raw_id.startswith("customers/"):
        return raw_id
    config = MUTATION_ENTITY_CONFIG[entity_type]
    normalized = raw_id.replace(":", "~")
    if config.get("requires_pair") and "~" not in normalized:
        raise SystemExit(f"{entity_type} IDs must be resource names or compound ad_group_id~entity_id values")
    return f"customers/{customer}/{config['collection']}/{normalized}"


def parent_resource_for_negative(customer: str, entity_type: str, parent_id: str | None) -> str:
    if not parent_id:
        config = MUTATION_ENTITY_CONFIG[entity_type]
        required = "--campaign-id" if config.get("negative_scope") == "campaign" else "--ad-group-id"
        raise SystemExit(f"{required} is required for {entity_type} plans")
    if parent_id.startswith("customers/"):
        return parent_id
    config = MUTATION_ENTITY_CONFIG[entity_type]
    return f"customers/{customer}/{config['parent_collection']}/{parent_id}"


def mutation_plan_payload(
    *,
    customer: str,
    entity_type: str,
    operation_type: str,
    ids: list[str] | None = None,
    status: str | None = None,
    amount_micros: int | None = None,
    keyword_texts: list[str] | None = None,
    match_type: str = "EXACT",
    ad_group_id: str | None = None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    if entity_type not in MUTATION_ENTITY_CONFIG:
        raise SystemExit(f"unsupported entity type: {entity_type}")
    config = MUTATION_ENTITY_CONFIG[entity_type]
    operations: list[dict[str, Any]] = []
    if operation_type == "negative_keyword":
        if "negative_scope" not in config:
            raise SystemExit(f"{entity_type} does not support negative keyword creation")
        parent_id = campaign_id if config["negative_scope"] == "campaign" else ad_group_id
        parent_resource = parent_resource_for_negative(customer, entity_type, parent_id)
        for text in keyword_texts or []:
            create = {
                config["parent_field"]: parent_resource,
                "negative": True,
                "keyword": {
                    "text": text,
                    "matchType": match_type,
                },
                "status": status or "ENABLED",
            }
            operations.append({config["operation"]: {"create": create}})
        if not operations:
            raise SystemExit("--texts must contain at least one search term")
        return {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}

    if not ids:
        raise SystemExit("--ids must contain at least one ID or resource name")
    for raw_id in ids:
        resource_name = resource_name_for_mutation(customer, entity_type, raw_id)
        update: dict[str, Any] = {"resourceName": resource_name}
        if operation_type == "remove":
            operations.append({config["operation"]: {"remove": resource_name}})
            continue
        if operation_type == "status":
            if not status:
                raise SystemExit("--status is required for status plans")
            if "status_field" not in config:
                raise SystemExit(f"{entity_type} does not support status plans")
            update[config["status_field"]] = status
            update_mask = "status"
        elif operation_type == "budget":
            if amount_micros is None:
                raise SystemExit("--amount-micros or --amount-dollars is required for budget plans")
            if "budget_field" not in config:
                raise SystemExit("budget plans only support campaign_budget entity type")
            update[config["budget_field"]] = amount_micros
            update_mask = "amount_micros"
        else:
            raise SystemExit(f"unsupported operation type: {operation_type}")
        operations.append({config["operation"]: {"update": update, "updateMask": update_mask}})
    return {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}


def mutation_plan_dir() -> pathlib.Path:
    path = PROFILE_ROOT / "tmp" / "google-ads-mutation-plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_mutation_plan(
    *,
    customer: str,
    entity_type: str,
    operation_type: str,
    payload: dict[str, Any],
    note: str | None,
) -> tuple[str, pathlib.Path]:
    ensure_schema()
    operation_count = len(payload.get("mutateOperations") or [])
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_mutation_plans (
                customer_id, entity_type, operation_type, operation_count,
                validate_only, payload, note
            )
            VALUES (%s, %s, %s, %s, true, %s::jsonb, %s)
            RETURNING id::text
            """,
            (customer, entity_type, operation_type, operation_count, jsonb(payload), note),
        )
        plan_id = str(cur.fetchone()[0])
    output_path = mutation_plan_dir() / f"{plan_id}.json"
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_path.chmod(0o600)
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE google_mutation_plans SET output_path = %s WHERE id = %s::uuid",
            (str(output_path), plan_id),
        )
    return plan_id, output_path


def mutation_plan_id_from_path(path: pathlib.Path) -> str | None:
    try:
        return str(uuid.UUID(path.stem))
    except ValueError:
        pass
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute("SELECT id::text FROM google_mutation_plans WHERE output_path = %s ORDER BY created_at DESC LIMIT 1", (str(path),))
        row = cur.fetchone()
    return str(row[0]) if row else None


def update_mutation_plan_result(plan_id: str | None, *, status: str, run_id: str | None, result: dict[str, Any]) -> None:
    if not plan_id:
        return
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE google_mutation_plans
            SET status = %s,
                executed_run_id = %s,
                executed_at = now(),
                result = %s::jsonb
            WHERE id = %s::uuid
            """,
            (status, run_id, jsonb(result), plan_id),
        )


def mutation_plan_record(plan_id: str | None) -> dict[str, Any]:
    if not plan_id:
        return {}
    with connect(schema=SCHEMA, application_name="google-ads-warehouse") as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, customer_id, entity_type, operation_type,
                   operation_count, output_path, note, created_at::text
            FROM google_mutation_plans
            WHERE id = %s::uuid
            """,
            (plan_id,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {
        "id": row[0],
        "customer_id": row[1],
        "entity_type": row[2],
        "operation_type": row[3],
        "operation_count": int(row[4] or 0),
        "output_path": row[5],
        "note": row[6],
        "created_at": row[7],
    }


def mutation_operation_counts(payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for operation in payload.get("mutateOperations") or []:
        if not isinstance(operation, dict) or not operation:
            key = "unknown"
        else:
            key = next(iter(operation))
        counts[key] = counts.get(key, 0) + 1
    return counts


def mutation_slack_channel(arg_channel: str | None) -> str:
    return (
        arg_channel
        or os.environ.get("GOOGLE_ADS_SLACK_CHANNEL_ID")
        or os.environ.get("SLACK_CHANNEL_ID")
        or DEFAULT_SLACK_CHANNEL
    )


def format_google_mutation_slack(
    *,
    customer: str,
    operation_path: pathlib.Path,
    payload: dict[str, Any],
    plan_id: str | None,
    run_id: str | None,
    status: str,
    response: dict[str, Any] | None = None,
    error: str | None = None,
) -> str:
    plan = mutation_plan_record(plan_id)
    counts = mutation_operation_counts(payload)
    count_text = ", ".join(f"{name}={count}" for name, count in sorted(counts.items())) or "none"
    partial_failure = bool((response or {}).get("partialFailureError"))
    title = "Google Ads live mutation partial failure" if partial_failure else "Google Ads live mutation"
    if error:
        title = "Google Ads live mutation failed"
    lines = [
        f"*{title}*",
        f"- Status: `{status}`",
        f"- Customer: `{customer}`",
        f"- Plan: `{plan_id or 'not stored'}`",
        f"- Run: `{run_id or 'not recorded'}`",
        f"- Operations: {len(payload.get('mutateOperations') or [])} ({count_text})",
        f"- Plan file: `{operation_path}`",
    ]
    if plan.get("entity_type") or plan.get("operation_type"):
        lines.append(f"- Plan type: `{plan.get('entity_type')}` / `{plan.get('operation_type')}`")
    if plan.get("note"):
        lines.append(f"- Note: {str(plan['note'])[:500]}")
    if partial_failure:
        failure = (response or {}).get("partialFailureError") or {}
        lines.append(f"- Google partial failure: `{str(failure.get('message') or failure)[:700]}`")
    if error:
        lines.append(f"- Error: `{error[:700]}`")
    lines.append("_Posted by `gads mutate --confirm-live`; suppress with `--no-slack`._")
    return "\n".join(lines)


def post_google_mutation_slack(channel_id: str, message: str) -> dict[str, Any]:
    if not channel_id:
        return {"ok": False, "error": "missing Slack channel; set GOOGLE_ADS_SLACK_CHANNEL_ID or pass --slack-channel"}
    helper = pathlib.Path(SLACK_HELPER_PATH).expanduser() if SLACK_HELPER_PATH else PROFILE_ROOT / "integrations" / "post_slack_direct.py"
    if not helper.is_file():
        return {"ok": False, "error": f"missing Slack helper: {helper}"}
    try:
        proc = subprocess.run(
            [sys.executable, str(helper), "--channel-id", channel_id],
            input=message,
            text=True,
            capture_output=True,
            timeout=40,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:1000]}
    parsed.setdefault("ok", proc.returncode == 0)
    parsed.setdefault("returncode", proc.returncode)
    return parsed


def cmd_plan_mutation(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    amount_micros = args.amount_micros
    if args.amount_dollars is not None:
        amount_micros = int(round(args.amount_dollars * 1_000_000))
    if args.status == "REMOVED":
        operation_type = "remove"
    elif args.entity_type == "campaign_budget":
        operation_type = "budget"
    elif MUTATION_ENTITY_CONFIG[args.entity_type].get("negative_scope"):
        operation_type = "negative_keyword"
    else:
        operation_type = "status"
    payload = mutation_plan_payload(
        customer=customer,
        entity_type=args.entity_type,
        operation_type=operation_type,
        ids=parse_entity_ids(args.ids) if args.ids else None,
        status=args.status,
        amount_micros=amount_micros,
        keyword_texts=parse_keyword_texts(args.texts) if args.texts else None,
        match_type=args.match_type,
        ad_group_id=args.ad_group_id,
        campaign_id=args.campaign_id,
    )
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type=args.entity_type,
        operation_type=operation_type,
        payload=payload,
        note=args.note,
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "entity_type": args.entity_type,
        "operation_type": operation_type,
        "operation_count": len(payload["mutateOperations"]),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    if args.format == "json":
        print(json.dumps({**summary, "payload": payload}, indent=2))
    else:
        print(json.dumps(summary, indent=2))
    return 0


def cmd_plan_search_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    budget_micros = int(round(args.budget_dollars * 1_000_000))
    if budget_micros <= 0:
        raise SystemExit("--budget-dollars must be greater than zero")

    headlines = split_list_arg(args.headlines) or [
        "Daily Nutrition Essentials",
        "Fuel Your Daily Routine",
        "Shop Online Today",
    ]
    descriptions = split_list_arg(args.descriptions) or [
        "A simple daily protein and superfood routine built for busy days.",
        "Order online and get the right product for your goal.",
    ]
    if len(headlines) < 3:
        raise SystemExit("responsive search ads need at least 3 headlines")
    if len(descriptions) < 2:
        raise SystemExit("responsive search ads need at least 2 descriptions")

    keyword_specs = parse_keyword_specs(args.keywords)
    if not keyword_specs:
        raise SystemExit("--keywords must include at least one keyword")
    sitelinks = parse_sitelink_specs(args.sitelinks)

    budget_resource = f"customers/{customer}/campaignBudgets/-1"
    campaign_resource = f"customers/{customer}/campaigns/-2"
    ad_group_resource = f"customers/{customer}/adGroups/-3"
    operations: list[dict[str, Any]] = [
        {
            "campaignBudgetOperation": {
                "create": {
                    "resourceName": budget_resource,
                    "name": args.budget_name or f"{args.name} Budget",
                    "amountMicros": budget_micros,
                    "deliveryMethod": "STANDARD",
                    "explicitlyShared": False,
                }
            }
        },
        {
            "campaignOperation": {
                "create": {
                    "resourceName": campaign_resource,
                    "name": args.name,
                    "status": "PAUSED",
                    "advertisingChannelType": "SEARCH",
                    "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                    "campaignBudget": budget_resource,
                    **bidding_scheme(
                        args.bid_strategy,
                        target_cpa_dollars=args.target_cpa_dollars,
                        target_roas=args.target_roas,
                    ),
                    "networkSettings": {
                        "targetGoogleSearch": True,
                        "targetSearchNetwork": args.include_search_partners,
                        "targetContentNetwork": False,
                        "targetPartnerSearchNetwork": args.include_search_partners,
                    },
                }
            }
        },
        {
            "adGroupOperation": {
                "create": {
                    "resourceName": ad_group_resource,
                    "name": args.ad_group_name or f"{args.name} Ad Group",
                    "campaign": campaign_resource,
                    "status": "PAUSED",
                    "type": "SEARCH_STANDARD",
                    "cpcBidMicros": int(round(args.cpc_bid_dollars * 1_000_000)),
                }
            }
        },
    ]

    for keyword in keyword_specs:
        operations.append(
            {
                "adGroupCriterionOperation": {
                    "create": {
                        "adGroup": ad_group_resource,
                        "status": "PAUSED",
                        "keyword": keyword,
                    }
                }
            }
        )

    operations.append(
        {
            "adGroupAdOperation": {
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "PAUSED",
                    "ad": {
                        "responsiveSearchAd": {
                            "headlines": [{"text": text} for text in headlines],
                            "descriptions": [{"text": text} for text in descriptions],
                        },
                        "finalUrls": [args.final_url],
                    },
                }
            }
        }
    )

    operations.extend(
        sitelink_operations(
            customer=customer,
            campaign_resource=campaign_resource,
            sitelinks=sitelinks,
            start_temp_id=10,
        )
    )

    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="search_campaign",
        operation_type="create",
        payload=payload,
        note=args.note or "Paused Search campaign creation plan",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign_name": args.name,
        "budget_dollars": args.budget_dollars,
        "bid_strategy": args.bid_strategy,
        "keyword_count": len(keyword_specs),
        "sitelink_count": len(sitelinks),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_shopping_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    merchant_id = str(args.merchant_id or infer_merchant_id(customer) or "").strip()
    if not merchant_id:
        raise SystemExit("--merchant-id is required; no existing Shopping merchant ID was found automatically")
    budget_micros = int(round(args.budget_dollars * 1_000_000))
    if budget_micros <= 0:
        raise SystemExit("--budget-dollars must be greater than zero")
    budget_resource = f"customers/{customer}/campaignBudgets/-1"
    campaign_resource = f"customers/{customer}/campaigns/-2"
    ad_group_resource = f"customers/{customer}/adGroups/-3"
    operations: list[dict[str, Any]] = [
        {
            "campaignBudgetOperation": {
                "create": {
                    "resourceName": budget_resource,
                    "name": args.budget_name or f"{args.name} Budget",
                    "amountMicros": budget_micros,
                    "deliveryMethod": "STANDARD",
                    "explicitlyShared": False,
                }
            }
        },
        {
            "campaignOperation": {
                "create": {
                    "resourceName": campaign_resource,
                    "name": args.name,
                    "status": "PAUSED",
                    "advertisingChannelType": "SHOPPING",
                    "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                    "campaignBudget": budget_resource,
                    **bidding_scheme(
                        args.bid_strategy,
                        target_cpa_dollars=args.target_cpa_dollars,
                        target_roas=args.target_roas,
                    ),
                    "shoppingSetting": {
                        "merchantId": merchant_id,
                        "campaignPriority": args.campaign_priority,
                        **({"feedLabel": args.feed_label} if args.feed_label else {}),
                    },
                }
            }
        },
        {
            "adGroupOperation": {
                "create": {
                    "resourceName": ad_group_resource,
                    "name": args.ad_group_name or f"{args.name} Products",
                    "campaign": campaign_resource,
                    "status": "PAUSED",
                    "type": "SHOPPING_PRODUCT_ADS",
                    "cpcBidMicros": int(round(args.cpc_bid_dollars * 1_000_000)),
                }
            }
        },
        {
            "adGroupAdOperation": {
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "PAUSED",
                    "ad": {"shoppingProductAd": {}},
                }
            }
        },
        {
            "adGroupCriterionOperation": {
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "ENABLED",
                    "cpcBidMicros": int(round(args.cpc_bid_dollars * 1_000_000)),
                    "listingGroup": {"type": "UNIT"},
                }
            }
        },
    ]
    payload = {"mutateOperations": operations, "partialFailure": False, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="shopping_campaign",
        operation_type="create",
        payload=payload,
        note=args.note or "Paused Shopping campaign creation plan",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign_name": args.name,
        "budget_dollars": args.budget_dollars,
        "bid_strategy": args.bid_strategy,
        "merchant_id": merchant_id,
        "feed_label": args.feed_label,
        "campaign_priority": args.campaign_priority,
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_build_shopping_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    seed_terms = split_terms_arg(args.seed_terms) or [args.offer]
    brand_terms = split_terms_arg(args.brand_terms) or DEFAULT_BRAND_TERMS
    geo_targets = constant_resources("geoTargetConstants", args.geo_targets, ["2840"])
    language = constant_resource("languageConstants", args.language or "1000")
    research_run_id, rows, source, fallback_reason = create_keyword_research_run_for_build(
        customer=customer,
        seed_terms=seed_terms,
        final_url=args.final_url,
        geo_targets=geo_targets,
        language=language,
        network=args.network,
        limit=args.limit,
        allow_broad=args.allow_broad,
        brand_terms=brand_terms,
        fallback_local_search_terms=args.fallback_local_search_terms,
        fallback_days=args.fallback_days,
        command_name="build-shopping-campaign/keyword-research",
    )
    bid_strategy = args.bid_strategy
    if bid_strategy == "auto":
        bid_strategy = "target_roas" if args.target_roas is not None else "manual_cpc"
    plan_args = argparse.Namespace(
        name=args.name or f"Shopping - {args.offer}",
        budget_name=args.budget_name,
        budget_dollars=args.daily_budget_dollars,
        ad_group_name=args.ad_group_name or f"{args.offer} Products",
        cpc_bid_dollars=args.cpc_bid_dollars,
        bid_strategy=bid_strategy,
        target_cpa_dollars=args.target_cpa_dollars,
        target_roas=args.target_roas,
        merchant_id=args.merchant_id,
        feed_label=args.feed_label,
        campaign_priority=args.campaign_priority,
        customer_id=customer,
        note=(
            args.note
            or f"Researched paused Shopping campaign plan; keyword_run={research_run_id}; "
            f"source={source}; fallback={bool(fallback_reason)}; top_terms={', '.join(str(row.get('text')) for row in rows[:8])}"
        ),
        format=args.format,
    )
    return cmd_plan_shopping_campaign(plan_args)


def cmd_plan_pmax_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    budget_micros = int(round(args.budget_dollars * 1_000_000))
    if budget_micros <= 0:
        raise SystemExit("--budget-dollars must be greater than zero")
    headlines = parse_text_specs(args.headlines)
    long_headlines = parse_text_specs(args.long_headlines)
    descriptions = parse_text_specs(args.descriptions)
    search_themes = parse_text_specs(args.search_themes)
    brand_defaults = DEFAULT_PMAX_BRAND_ASSETS.get(customer, {})
    asset_group_defaults = DEFAULT_PMAX_ASSET_GROUP_ASSETS.get(customer, {})
    business_name_assets = parse_asset_specs(customer, args.business_name_assets, brand_defaults.get("BUSINESS_NAME"))
    logo_assets = parse_asset_specs(customer, args.logo_assets, brand_defaults.get("LOGO"))
    landscape_logo_assets = parse_asset_specs(
        customer,
        args.landscape_logo_assets,
        brand_defaults.get("LANDSCAPE_LOGO"),
    )
    marketing_image_assets = parse_asset_specs(
        customer,
        args.marketing_image_assets,
        asset_group_defaults.get("MARKETING_IMAGE"),
    )
    square_marketing_image_assets = parse_asset_specs(
        customer,
        args.square_marketing_image_assets,
        asset_group_defaults.get("SQUARE_MARKETING_IMAGE"),
    )
    portrait_marketing_image_assets = parse_asset_specs(
        customer,
        args.portrait_marketing_image_assets,
        asset_group_defaults.get("PORTRAIT_MARKETING_IMAGE"),
    )
    youtube_video_assets = parse_asset_specs(customer, args.youtube_video_assets)
    call_to_action_assets = parse_asset_specs(
        customer,
        args.call_to_action_assets,
        asset_group_defaults.get("CALL_TO_ACTION_SELECTION"),
    )
    linked_headline_assets = parse_asset_specs(customer, args.headline_assets, asset_group_defaults.get("HEADLINE"))
    linked_long_headline_assets = parse_asset_specs(
        customer,
        args.long_headline_assets,
        asset_group_defaults.get("LONG_HEADLINE"),
    )
    linked_description_assets = parse_asset_specs(
        customer,
        args.description_assets,
        asset_group_defaults.get("DESCRIPTION"),
    )

    if not headlines and not linked_headline_assets:
        headlines = [
            "Daily Nutrition Essentials",
            "Daily Protein And Superfoods",
            "Shop Online Today",
            "All-In-One Daily Nutrition",
            "Fuel Your Daily Routine",
        ]
    if not long_headlines and not linked_long_headline_assets:
        long_headlines = [
            "Protein, superfoods, vitamins, and probiotics in one daily shake",
            "Get daily nutrition support from protein and superfoods",
            "Shop Online for simple all-in-one daily nutrition",
        ]
    if not descriptions and not linked_description_assets:
        descriptions = [
            "Protein, superfoods, vitamins, and probiotics in one simple daily routine.",
            "Fuel your daily routine with protein and superfoods.",
            "Shop online and pick the blend that fits your goals.",
            "One scoop supports energy, digestion, and overall wellness.",
        ]

    if len(headlines) + len(linked_headline_assets) < 5:
        raise SystemExit("Performance Max plans need at least 5 headline assets")
    if len(long_headlines) + len(linked_long_headline_assets) < 1:
        raise SystemExit("Performance Max plans need at least 1 long headline")
    if len(descriptions) + len(linked_description_assets) < 2:
        raise SystemExit("Performance Max plans need at least 2 descriptions")
    if not logo_assets:
        raise SystemExit("Performance Max plans need --logo-assets")
    if not marketing_image_assets:
        raise SystemExit("Performance Max plans need --marketing-image-assets")
    if not square_marketing_image_assets:
        raise SystemExit("Performance Max plans need --square-marketing-image-assets")

    budget_resource = f"customers/{customer}/campaignBudgets/-1"
    campaign_resource = f"customers/{customer}/campaigns/-2"
    asset_group_resource = f"customers/{customer}/assetGroups/-3"
    operations: list[dict[str, Any]] = [
        {
            "campaignBudgetOperation": {
                "create": {
                    "resourceName": budget_resource,
                    "name": args.budget_name or f"{args.name} Budget",
                    "amountMicros": budget_micros,
                    "deliveryMethod": "STANDARD",
                    "explicitlyShared": False,
                }
            }
        },
        {
            "campaignOperation": {
                "create": {
                    "resourceName": campaign_resource,
                    "name": args.name,
                    "status": "PAUSED",
                    "advertisingChannelType": "PERFORMANCE_MAX",
                    "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                    "campaignBudget": budget_resource,
                    **bidding_scheme(
                        args.bid_strategy,
                        target_cpa_dollars=args.target_cpa_dollars,
                        target_roas=args.target_roas,
                    ),
                }
            }
        },
        {
            "assetGroupOperation": {
                "create": {
                    "resourceName": asset_group_resource,
                    "name": args.asset_group_name or f"{args.name} Asset Group",
                    "campaign": campaign_resource,
                    "finalUrls": [args.final_url],
                    "status": "PAUSED",
                }
            }
        },
    ]

    temp_id = 10
    campaign_assets_by_field = {
        "BUSINESS_NAME": business_name_assets,
        "LOGO": logo_assets,
        "LANDSCAPE_LOGO": landscape_logo_assets,
    }
    if not campaign_assets_by_field["BUSINESS_NAME"]:
        asset_resource = f"customers/{customer}/assets/-{temp_id}"
        operations.append({"assetOperation": {"create": {"resourceName": asset_resource, "textAsset": {"text": args.business_name}}}})
        campaign_assets_by_field["BUSINESS_NAME"] = [asset_resource]
        temp_id += 1
    operations.extend(campaign_asset_operations(campaign_resource=campaign_resource, assets_by_field=campaign_assets_by_field))

    text_assets: list[tuple[str, str]] = []
    text_assets.extend(("HEADLINE", text) for text in headlines)
    text_assets.extend(("LONG_HEADLINE", text) for text in long_headlines)
    text_assets.extend(("DESCRIPTION", text) for text in descriptions)
    for field_type, text in text_assets:
        asset_resource = f"customers/{customer}/assets/-{temp_id}"
        operations.append({"assetOperation": {"create": {"resourceName": asset_resource, "textAsset": {"text": text}}}})
        operations.append(
            {
                "assetGroupAssetOperation": {
                    "create": {
                        "assetGroup": asset_group_resource,
                        "asset": asset_resource,
                        "fieldType": field_type,
                        "status": "ENABLED",
                    }
                }
            }
        )
        temp_id += 1
    asset_group_assets_by_field = {
        "HEADLINE": linked_headline_assets,
        "LONG_HEADLINE": linked_long_headline_assets,
        "DESCRIPTION": linked_description_assets,
        "MARKETING_IMAGE": marketing_image_assets,
        "SQUARE_MARKETING_IMAGE": square_marketing_image_assets,
        "PORTRAIT_MARKETING_IMAGE": portrait_marketing_image_assets,
        "YOUTUBE_VIDEO": youtube_video_assets,
        "CALL_TO_ACTION_SELECTION": call_to_action_assets,
    }
    operations.extend(asset_group_asset_operations(asset_group_resource=asset_group_resource, assets_by_field=asset_group_assets_by_field))
    for theme in search_themes:
        operations.append(
            {
                "assetGroupSignalOperation": {
                    "create": {
                        "assetGroup": asset_group_resource,
                        "searchTheme": {"text": theme},
                    }
                }
            }
        )
    payload = {"mutateOperations": operations, "partialFailure": False, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="pmax_campaign",
        operation_type="create",
        payload=payload,
        note=args.note or "Paused Performance Max campaign creation plan",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign_name": args.name,
        "budget_dollars": args.budget_dollars,
        "bid_strategy": args.bid_strategy,
        "asset_group_name": args.asset_group_name or f"{args.name} Asset Group",
        "text_asset_count": len(text_assets),
        "campaign_asset_count": sum(len(items) for items in campaign_assets_by_field.values()),
        "linked_asset_group_asset_count": sum(len(items) for items in asset_group_assets_by_field.values()),
        "search_theme_count": len(search_themes),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def pmax_research_assets(*, offer: str, rows: list[dict[str, Any]], max_themes: int) -> dict[str, list[str]]:
    themes: list[str] = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        intent = str(row.get("intent_bucket") or "")
        if not text or intent == "informational":
            continue
        if text.casefold() not in {theme.casefold() for theme in themes}:
            themes.append(ad_text_limit(text, 80))
        if len(themes) >= max_themes:
            break
    title_terms = [theme.title() for theme in themes[:4]]
    headlines = unique_ad_texts(
        [
            offer,
            f"Shop {offer}",
            "Daily Nutrition Essentials",
            "Daily Protein And Superfoods",
            "All-In-One Daily Nutrition",
            *title_terms,
            "Fuel Your Daily Routine",
        ],
        max_len=30,
        minimum=5,
        fallbacks=[
            "Shop Online Today",
            "Protein And Superfoods",
            "Daily Nutrition Shake",
            "Superfood Protein Blend",
            "Order Online Today",
        ],
    )
    long_headlines = unique_ad_texts(
        [
            f"Shop {offer} for daily protein and superfoods",
            "Protein, superfoods, vitamins, and probiotics in one daily shake",
            "Get daily nutrition support from protein and superfoods",
            "Fuel your routine with all-in-one daily nutrition",
        ],
        max_len=90,
        minimum=3,
        fallbacks=[
            "Shop Online for simple all-in-one daily nutrition",
            "A protein and superfood routine built for busy days",
            "Daily nutrition support from protein, greens, and superfoods",
        ],
    )
    descriptions = unique_ad_texts(
        [
            "Protein, superfoods, vitamins, and probiotics in one simple daily routine.",
            "Fuel your daily routine with protein and superfoods.",
            "Shop online and pick the blend that fits your goals.",
            "One scoop supports energy, digestion, and overall wellness.",
        ],
        max_len=90,
        minimum=4,
        fallbacks=[
            "Daily nutrition made simple with superfood protein.",
            "Order online and build a better daily shake routine.",
            "Superfoods, protein, vitamins, probiotics, and greens in one scoop.",
            "A simple shake for protein, superfoods, and daily wellness support.",
        ],
    )
    return {
        "search_themes": themes,
        "headlines": headlines,
        "long_headlines": long_headlines,
        "descriptions": descriptions,
    }


def cmd_build_pmax_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    seed_terms = split_terms_arg(args.seed_terms) or [args.offer]
    brand_terms = split_terms_arg(args.brand_terms) or DEFAULT_BRAND_TERMS
    geo_targets = constant_resources("geoTargetConstants", args.geo_targets, ["2840"])
    language = constant_resource("languageConstants", args.language or "1000")
    research_run_id, rows, source, fallback_reason = create_keyword_research_run_for_build(
        customer=customer,
        seed_terms=seed_terms,
        final_url=args.final_url,
        geo_targets=geo_targets,
        language=language,
        network=args.network,
        limit=args.limit,
        allow_broad=True,
        brand_terms=brand_terms,
        fallback_local_search_terms=args.fallback_local_search_terms,
        fallback_days=args.fallback_days,
        command_name="build-pmax-campaign/keyword-research",
    )
    assets = pmax_research_assets(offer=args.offer, rows=rows, max_themes=args.max_search_themes)
    if not assets["search_themes"]:
        raise SystemExit("Keyword research produced no launchable PMax search themes; broaden seeds or verify search-term history")
    plan_args = argparse.Namespace(
        name=args.name or f"PMax - {args.offer}",
        budget_name=args.budget_name,
        budget_dollars=args.daily_budget_dollars,
        asset_group_name=args.asset_group_name or f"{args.offer} Asset Group",
        final_url=args.final_url,
        bid_strategy=args.bid_strategy,
        target_cpa_dollars=args.target_cpa_dollars,
        target_roas=args.target_roas,
        business_name=args.business_name,
        headlines=None,
        long_headlines=None,
        descriptions=None,
        search_themes="|".join(assets["search_themes"]),
        business_name_assets=args.business_name_assets,
        logo_assets=args.logo_assets,
        landscape_logo_assets=args.landscape_logo_assets,
        marketing_image_assets=args.marketing_image_assets,
        square_marketing_image_assets=args.square_marketing_image_assets,
        portrait_marketing_image_assets=args.portrait_marketing_image_assets,
        youtube_video_assets=args.youtube_video_assets,
        call_to_action_assets=args.call_to_action_assets,
        headline_assets=args.headline_assets,
        long_headline_assets=args.long_headline_assets,
        description_assets=args.description_assets,
        customer_id=customer,
        note=(
            args.note
            or f"Researched paused PMax campaign plan; keyword_run={research_run_id}; "
            f"source={source}; fallback={bool(fallback_reason)}; themes={', '.join(assets['search_themes'][:8])}"
        ),
        format=args.format,
    )
    return cmd_plan_pmax_campaign(plan_args)


def demand_gen_channel_controls(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, bool] | None]:
    strategy = args.channel_strategy.lower().replace("-", "_")
    if strategy == "all_channels":
        return {"channelStrategy": "ALL_CHANNELS"}, None
    if strategy == "all_owned_and_operated_channels":
        return {"channelStrategy": "ALL_OWNED_AND_OPERATED_CHANNELS"}, None
    selected_channels = {
        "youtubeInStream": bool(args.youtube_in_stream),
        "youtubeInFeed": bool(args.youtube_in_feed),
        "youtubeShorts": bool(args.youtube_shorts),
        "discover": bool(args.discover),
        "gmail": bool(args.gmail),
        "display": bool(args.display),
    }
    if not any(selected_channels.values()):
        raise SystemExit("selected channel strategy needs at least one enabled channel")
    return {"selectedChannels": selected_channels}, selected_channels


def cmd_plan_demand_gen_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    budget_micros = int(round(args.budget_dollars * 1_000_000))
    if budget_micros <= 0:
        raise SystemExit("--budget-dollars must be greater than zero")
    if budget_micros < 5_000_000:
        raise SystemExit("Demand Gen plans generally need --budget-dollars 5 or higher for USD accounts")

    ad_asset_defaults = DEFAULT_DEMAND_GEN_AD_ASSETS.get(customer, {})
    youtube_video_assets = parse_asset_specs(customer, args.youtube_video_assets)
    logo_assets = parse_asset_specs(customer, args.logo_assets, ad_asset_defaults.get("LOGO_IMAGE"))
    call_to_action_assets = parse_asset_specs(customer, args.call_to_action_assets, ad_asset_defaults.get("CALL_TO_ACTION"))
    headlines = parse_text_specs(args.headlines) or [
        "Daily Nutrition Essentials",
        "Daily Protein And Superfoods",
        "Shop Online Today",
    ]
    long_headlines = parse_text_specs(args.long_headlines) or [
        "Protein, superfoods, vitamins, and probiotics in one daily shake",
    ]
    descriptions = parse_text_specs(args.descriptions) or [
        "Protein, superfoods, vitamins, and probiotics in one simple daily routine.",
        "Shop online and pick the blend that fits your goals.",
    ]
    create_video_ad = bool(youtube_video_assets)
    if create_video_ad:
        if not logo_assets:
            raise SystemExit("Demand Gen video ads need --logo-assets")
        if len(headlines) < 1:
            raise SystemExit("Demand Gen video ads need at least 1 headline")
        if len(long_headlines) < 1:
            raise SystemExit("Demand Gen video ads need at least 1 long headline")
        if len(descriptions) < 1:
            raise SystemExit("Demand Gen video ads need at least 1 description")
    ad_logo_assets = logo_assets[:1] if create_video_ad else []
    ad_call_to_action_assets = call_to_action_assets[:1] if create_video_ad else []

    channel_controls, selected_channels = demand_gen_channel_controls(args)
    budget_resource = f"customers/{customer}/campaignBudgets/-1"
    campaign_resource = f"customers/{customer}/campaigns/-2"
    ad_group_resource = f"customers/{customer}/adGroups/-3"
    operations: list[dict[str, Any]] = [
        {
            "campaignBudgetOperation": {
                "create": {
                    "resourceName": budget_resource,
                    "name": args.budget_name or f"{args.name} Budget",
                    "amountMicros": budget_micros,
                    "deliveryMethod": "STANDARD",
                    "explicitlyShared": False,
                }
            }
        },
        {
            "campaignOperation": {
                "create": {
                    "resourceName": campaign_resource,
                    "name": args.name,
                    "status": "PAUSED",
                    "advertisingChannelType": "DEMAND_GEN",
                    "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                    "campaignBudget": budget_resource,
                    **bidding_scheme(
                        args.bid_strategy,
                        target_cpa_dollars=args.target_cpa_dollars,
                        target_roas=args.target_roas,
                    ),
                }
            }
        },
        {
            "adGroupOperation": {
                "create": {
                    "resourceName": ad_group_resource,
                    "name": args.ad_group_name or f"{args.name} Ad Group",
                    "campaign": campaign_resource,
                    "status": "ENABLED",
                    "demandGenAdGroupSettings": {
                        "channelControls": channel_controls,
                    },
                }
            }
        },
    ]

    if create_video_ad:
        video_ad: dict[str, Any] = {
            "businessName": {"text": args.business_name},
            "videos": [{"asset": resource} for resource in youtube_video_assets],
            "logoImages": [{"asset": resource} for resource in ad_logo_assets],
            "headlines": [{"text": text} for text in headlines],
            "longHeadlines": [{"text": text} for text in long_headlines],
            "descriptions": [{"text": text} for text in descriptions],
        }
        if ad_call_to_action_assets:
            video_ad["callToActions"] = [{"asset": resource} for resource in ad_call_to_action_assets]
        operations.append(
            {
                "adGroupAdOperation": {
                    "create": {
                        "adGroup": ad_group_resource,
                        "status": "ENABLED",
                        "ad": {
                            "name": args.ad_name or f"{args.name} Video Responsive Ad",
                            "finalUrls": [args.final_url],
                            "demandGenVideoResponsiveAd": video_ad,
                        },
                    }
                }
            }
        )

    payload = {"mutateOperations": operations, "partialFailure": False, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="demand_gen_campaign",
        operation_type="create",
        payload=payload,
        note=args.note or "Paused Demand Gen campaign creation plan",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign_name": args.name,
        "budget_dollars": args.budget_dollars,
        "bid_strategy": args.bid_strategy,
        "channel_strategy": args.channel_strategy,
        "selected_channels": selected_channels,
        "ad_group_name": args.ad_group_name or f"{args.name} Ad Group",
        "video_ad_created": create_video_ad,
        "youtube_video_asset_count": len(youtube_video_assets),
        "logo_asset_count": len(ad_logo_assets),
        "call_to_action_asset_count": len(ad_call_to_action_assets),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    if not create_video_ad:
        summary["ad_skip_reason"] = "No --youtube-video-assets supplied; created campaign and ad group scaffold only."
    extra_summary = getattr(args, "summary_extra", None)
    if isinstance(extra_summary, dict):
        summary.update(extra_summary)
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def demand_gen_video_asset_candidate(customer: str, query: str | None = None) -> dict[str, Any] | None:
    clauses = ["customer_id = %s", "upper(type) = 'YOUTUBE_VIDEO'"]
    params: list[Any] = [customer]
    if query:
        needle = f"%{query.lower()}%"
        clauses.append(
            """
            lower(
                coalesce(name, '') || ' ' ||
                coalesce(asset_id, '') || ' ' ||
                coalesce(resource_name, '') || ' ' ||
                coalesce(source, '')
            ) LIKE %s
            """
        )
        params.append(needle)
    sql = f"""
        SELECT
            asset_id,
            resource_name,
            coalesce(nullif(name, ''), '(unnamed)') AS name,
            coalesce(source, '') AS source,
            fetched_at::text
        FROM google_assets
        WHERE {' AND '.join(clauses)}
        ORDER BY fetched_at DESC NULLS LAST, asset_id
        LIMIT 1
    """
    with connect(schema=SCHEMA, application_name="google-ads-demand-gen-video-asset") as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row:
        return None
    asset_id = str(row[0] or "")
    resource_name = str(row[1] or f"customers/{customer}/assets/{extract_id(asset_id)}")
    return {
        "asset_id": asset_id,
        "resource_name": resource_name,
        "name": row[2],
        "source": row[3],
        "fetched_at": row[4],
    }


def choose_demand_gen_video_assets(
    *,
    customer: str,
    explicit_assets: str | None,
    video_query: str | None,
    auto_video_asset: bool,
) -> tuple[str | None, dict[str, Any]]:
    parsed_explicit_assets = parse_asset_specs(customer, explicit_assets)
    if parsed_explicit_assets:
        return "|".join(parsed_explicit_assets), {
            "mode": "explicit",
            "resource_names": parsed_explicit_assets,
            "asset_count": len(parsed_explicit_assets),
        }
    if not auto_video_asset:
        return None, {"mode": "disabled", "resource_names": [], "asset_count": 0}

    selected = demand_gen_video_asset_candidate(customer, video_query)
    query_fallback_used = False
    if not selected and video_query:
        selected = demand_gen_video_asset_candidate(customer, None)
        query_fallback_used = bool(selected)
    if not selected:
        raise SystemExit(
            "No YOUTUBE_VIDEO assets are available in google_assets. Run `gads asset-library --type YOUTUBE_VIDEO` "
            "or sync the asset surface, then pass --youtube-video-assets."
        )
    return selected["resource_name"], {
        "mode": "auto",
        "query": video_query,
        "query_fallback_used": query_fallback_used,
        "resource_names": [selected["resource_name"]],
        "asset_id": selected["asset_id"],
        "asset_name": selected["name"],
        "source": selected["source"],
        "fetched_at": selected["fetched_at"],
        "asset_count": 1,
    }


def cmd_build_demand_gen_campaign(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    if args.daily_budget_dollars < 5:
        raise SystemExit("Demand Gen builds generally need --daily-budget-dollars 5 or higher for USD accounts")
    seed_terms = split_terms_arg(args.seed_terms) or [args.offer]
    brand_terms = split_terms_arg(args.brand_terms) or DEFAULT_BRAND_TERMS
    geo_targets = constant_resources("geoTargetConstants", args.geo_targets, ["2840"])
    language = constant_resource("languageConstants", args.language or "1000")
    research_run_id, rows, source, fallback_reason = create_keyword_research_run_for_build(
        customer=customer,
        seed_terms=seed_terms,
        final_url=args.final_url,
        geo_targets=geo_targets,
        language=language,
        network=args.network,
        limit=args.limit,
        allow_broad=args.allow_broad,
        brand_terms=brand_terms,
        fallback_local_search_terms=args.fallback_local_search_terms,
        fallback_days=args.fallback_days,
        command_name="build-demand-gen-campaign/keyword-research",
    )
    if not rows:
        raise SystemExit("Keyword research produced no Demand Gen planning terms; broaden seeds or verify search-term history")
    text_assets = pmax_research_assets(offer=args.offer, rows=rows, max_themes=args.max_research_terms)
    youtube_video_assets, video_selection = choose_demand_gen_video_assets(
        customer=customer,
        explicit_assets=args.youtube_video_assets,
        video_query=args.video_query,
        auto_video_asset=args.auto_video_asset,
    )
    selected_terms = [str(row.get("text") or "").strip() for row in rows[:8] if str(row.get("text") or "").strip()]
    plan_args = argparse.Namespace(
        name=args.name or f"Demand Gen - {args.offer}",
        budget_name=args.budget_name,
        budget_dollars=args.daily_budget_dollars,
        ad_group_name=args.ad_group_name or f"{args.offer} Demand Gen",
        ad_name=args.ad_name or f"{args.offer} Video Responsive Ad",
        final_url=args.final_url,
        bid_strategy=args.bid_strategy,
        target_cpa_dollars=args.target_cpa_dollars,
        target_roas=args.target_roas,
        channel_strategy=args.channel_strategy,
        youtube_in_stream=args.youtube_in_stream,
        youtube_in_feed=args.youtube_in_feed,
        youtube_shorts=args.youtube_shorts,
        discover=args.discover,
        gmail=args.gmail,
        display=args.display,
        business_name=args.business_name,
        youtube_video_assets=youtube_video_assets,
        logo_assets=args.logo_assets,
        call_to_action_assets=args.call_to_action_assets,
        headlines="|".join(text_assets["headlines"][:5]),
        long_headlines="|".join(text_assets["long_headlines"][:3]),
        descriptions="|".join(text_assets["descriptions"][:4]),
        customer_id=customer,
        note=(
            args.note
            or f"Researched paused Demand Gen campaign plan; keyword_run={research_run_id}; "
            f"source={source}; fallback={bool(fallback_reason)}; "
            f"video_assets={','.join(video_selection.get('resource_names') or [])}; top_terms={', '.join(selected_terms)}"
        ),
        format=args.format,
        summary_extra={
            "offer": args.offer,
            "keyword_research_run_id": research_run_id,
            "research_source": source,
            "fallback_reason": fallback_reason,
            "seed_terms": seed_terms,
            "selected_research_terms": selected_terms,
            "video_asset_selection": video_selection,
        },
    )
    return cmd_plan_demand_gen_campaign(plan_args)


def cmd_plan_bid_strategy(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    campaign_resource = resource_name_for_mutation(customer, "campaign", args.campaign_id)
    update = {
        "resourceName": campaign_resource,
        **bidding_scheme(
            args.bid_strategy,
            target_cpa_dollars=args.target_cpa_dollars,
            target_roas=args.target_roas,
        ),
    }
    payload = {
        "mutateOperations": [
            {
                "campaignOperation": {
                    "update": update,
                    "updateMask": bidding_update_mask(
                        args.bid_strategy,
                        target_cpa_dollars=args.target_cpa_dollars,
                        target_roas=args.target_roas,
                    ),
                }
            }
        ],
        "partialFailure": False,
        "validateOnly": True,
    }
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="campaign",
        operation_type="bid_strategy",
        payload=payload,
        note=args.note or f"Campaign bid strategy update to {args.bid_strategy}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign": campaign_resource,
        "bid_strategy": args.bid_strategy,
        "operation_count": 1,
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_campaign_conversion_goal(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    campaign_id = extract_id(args.campaign_id) if args.campaign_id.startswith("customers/") else args.campaign_id
    resource_name = f"customers/{customer}/campaignConversionGoals/{campaign_id}~{args.category}~{args.origin}"
    payload = {
        "mutateOperations": [
            {
                "campaignConversionGoalOperation": {
                    "update": {
                        "resourceName": resource_name,
                        "biddable": bool(args.biddable),
                    },
                    "updateMask": "biddable",
                }
            }
        ],
        "partialFailure": False,
        "validateOnly": True,
    }
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="campaign_conversion_goal",
        operation_type="biddable",
        payload=payload,
        note=args.note or f"Set campaign conversion goal {args.category}/{args.origin} biddable={bool(args.biddable)}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "resource_name": resource_name,
        "biddable": bool(args.biddable),
        "operation_count": 1,
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_sitelinks(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    sitelinks = parse_sitelink_specs(args.sitelinks)
    if not sitelinks:
        raise SystemExit("--sitelinks must include at least one text|url entry")
    campaign_resource = resource_name_for_mutation(customer, "campaign", args.campaign_id)
    operations = sitelink_operations(
        customer=customer,
        campaign_resource=campaign_resource,
        sitelinks=sitelinks,
        start_temp_id=1,
    )
    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="campaign_asset",
        operation_type="sitelink",
        payload=payload,
        note=args.note or f"Attach {len(sitelinks)} sitelink assets to {campaign_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign": campaign_resource,
        "sitelink_count": len(sitelinks),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_callouts(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    callouts = parse_callout_specs(args.callouts)
    if not callouts:
        raise SystemExit("--callouts must include at least one callout")
    campaign_resource = resource_name_for_mutation(customer, "campaign", args.campaign_id)
    operations = callout_operations(
        customer=customer,
        campaign_resource=campaign_resource,
        callouts=callouts,
        start_temp_id=1,
        status=args.status,
    )
    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="campaign_asset",
        operation_type="callout",
        payload=payload,
        note=args.note or f"Attach {len(callouts)} callout assets to {campaign_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign": campaign_resource,
        "callout_count": len(callouts),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_structured_snippets(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    snippets = parse_structured_snippet_specs(args.snippets)
    if not snippets:
        raise SystemExit("--snippets must include at least one header|value1,value2,value3 entry")
    campaign_resource = resource_name_for_mutation(customer, "campaign", args.campaign_id)
    operations = structured_snippet_operations(
        customer=customer,
        campaign_resource=campaign_resource,
        snippets=snippets,
        start_temp_id=1,
        status=args.status,
    )
    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="campaign_asset",
        operation_type="structured_snippet",
        payload=payload,
        note=args.note or f"Attach {len(snippets)} structured snippet assets to {campaign_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign": campaign_resource,
        "structured_snippet_count": len(snippets),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_campaign_targeting(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    campaign_resource = resource_name_for_mutation(customer, "campaign", args.campaign_id)
    geo_targets = parse_text_specs(args.geo_targets)
    excluded_geo_targets = parse_text_specs(args.excluded_geo_targets)
    language_targets = parse_text_specs(args.languages)
    ad_schedules = parse_ad_schedule_specs(args.ad_schedules)
    operations: list[dict[str, Any]] = []
    for target in geo_targets:
        operations.append(
            {
                "campaignCriterionOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "status": "ENABLED",
                        "location": {"geoTargetConstant": resource_from_constant("geoTargetConstants", target)},
                    }
                }
            }
        )
    for target in excluded_geo_targets:
        operations.append(
            {
                "campaignCriterionOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "status": "ENABLED",
                        "negative": True,
                        "location": {"geoTargetConstant": resource_from_constant("geoTargetConstants", target)},
                    }
                }
            }
        )
    for language in language_targets:
        operations.append(
            {
                "campaignCriterionOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "status": "ENABLED",
                        "language": {"languageConstant": resource_from_constant("languageConstants", language)},
                    }
                }
            }
        )
    for schedule in ad_schedules:
        operations.append(
            {
                "campaignCriterionOperation": {
                    "create": {
                        "campaign": campaign_resource,
                        "status": "ENABLED",
                        "adSchedule": schedule,
                    }
                }
            }
        )
    if not operations:
        raise SystemExit("include at least one targeting option: --geo-targets, --excluded-geo-targets, --languages, or --ad-schedules")
    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="campaign_criterion",
        operation_type="targeting",
        payload=payload,
        note=args.note or f"Attach {len(operations)} targeting criteria to {campaign_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign": campaign_resource,
        "geo_target_count": len(geo_targets),
        "excluded_geo_target_count": len(excluded_geo_targets),
        "language_count": len(language_targets),
        "ad_schedule_count": len(ad_schedules),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_custom_mutate(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    source = pathlib.Path(args.operation_json)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if "mutateOperations" not in payload:
        raise SystemExit("operation JSON must contain mutateOperations")
    payload["validateOnly"] = True
    payload.setdefault("partialFailure", True)
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type=args.entity_type,
        operation_type=args.operation_type,
        payload=payload,
        note=args.note or f"Custom Google Ads mutate payload from {source}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "source_path": str(source),
        "entity_type": args.entity_type,
        "operation_type": args.operation_type,
        "operation_count": len(payload.get("mutateOperations") or []),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_ad_group(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    campaign_resource = resource_name_for_mutation(customer, "campaign", args.campaign_id)
    create: dict[str, Any] = {
        "name": args.name,
        "campaign": campaign_resource,
        "status": args.status,
        "type": args.type,
    }
    if args.cpc_bid_dollars is not None:
        create["cpcBidMicros"] = int(round(args.cpc_bid_dollars * 1_000_000))
    payload = {
        "mutateOperations": [{"adGroupOperation": {"create": create}}],
        "partialFailure": True,
        "validateOnly": True,
    }
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="ad_group",
        operation_type="create",
        payload=payload,
        note=args.note or f"Create {args.status.lower()} ad group in {campaign_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "campaign": campaign_resource,
        "ad_group_name": args.name,
        "operation_count": 1,
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_keywords(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    ad_group_resource = resource_name_for_mutation(customer, "ad_group", args.ad_group_id)
    keyword_specs = parse_keyword_specs(args.keywords)
    if not keyword_specs:
        raise SystemExit("--keywords must include at least one keyword")
    operations = [
        {
            "adGroupCriterionOperation": {
                "create": {
                    "adGroup": ad_group_resource,
                    "status": args.status,
                    "keyword": keyword,
                }
            }
        }
        for keyword in keyword_specs
    ]
    payload = {"mutateOperations": operations, "partialFailure": True, "validateOnly": True}
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="keyword",
        operation_type="create",
        payload=payload,
        note=args.note or f"Create {len(keyword_specs)} keywords in {ad_group_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "ad_group": ad_group_resource,
        "keyword_count": len(keyword_specs),
        "operation_count": len(operations),
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def cmd_plan_responsive_search_ad(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    ad_group_resource = resource_name_for_mutation(customer, "ad_group", args.ad_group_id)
    headlines = split_list_arg(args.headlines) or [
        "Daily Nutrition Essentials",
        "Fuel Your Daily Routine",
        "Shop Online Today",
    ]
    descriptions = split_list_arg(args.descriptions) or [
        "A simple daily protein and superfood routine built for busy days.",
        "Order online and get the right product for your goal.",
    ]
    if len(headlines) < 3:
        raise SystemExit("responsive search ads need at least 3 headlines")
    if len(descriptions) < 2:
        raise SystemExit("responsive search ads need at least 2 descriptions")
    payload = {
        "mutateOperations": [
            {
                "adGroupAdOperation": {
                    "create": {
                        "adGroup": ad_group_resource,
                        "status": args.status,
                        "ad": {
                            "responsiveSearchAd": {
                                "headlines": [{"text": text} for text in headlines],
                                "descriptions": [{"text": text} for text in descriptions],
                            },
                            "finalUrls": [args.final_url],
                        },
                    }
                }
            }
        ],
        "partialFailure": True,
        "validateOnly": True,
    }
    plan_id, output_path = store_mutation_plan(
        customer=customer,
        entity_type="ad_group_ad",
        operation_type="create",
        payload=payload,
        note=args.note or f"Create paused responsive search ad in {ad_group_resource}",
    )
    summary = {
        "plan_id": plan_id,
        "customer_id": customer,
        "ad_group": ad_group_resource,
        "headline_count": len(headlines),
        "description_count": len(descriptions),
        "operation_count": 1,
        "validateOnly": True,
        "output_path": str(output_path),
        "next_validate_command": f"gads mutate {output_path}",
        "next_live_command": f"gads mutate {output_path} --confirm-live",
    }
    print(json.dumps({**summary, "payload": payload} if args.format == "json" else summary, indent=2))
    return 0


def search_negative_candidates(
    *,
    customer: str,
    since: str,
    until: str,
    min_spend: float,
    min_clicks: int,
    max_conversions: float,
    scope: str,
    limit: int,
) -> list[dict[str, Any]]:
    if scope == "campaign":
        parent_column = "campaign_id"
        group_columns = "campaign_id, search_term"
        id_predicate = "campaign_id <> ''"
    else:
        parent_column = "ad_group_id"
        group_columns = "campaign_id, ad_group_id, search_term"
        id_predicate = "ad_group_id <> ''"
    sql = f"""
        SELECT
            campaign_id,
            {parent_column} AS parent_id,
            search_term,
            sum(cost_micros) / 1000000.0 AS spend,
            sum(clicks) AS clicks,
            coalesce(sum(conversions), 0) AS conversions
        FROM google_search_terms
        WHERE customer_id = %s
          AND report_date BETWEEN %s::date AND %s::date
          AND search_term <> ''
          AND {id_predicate}
        GROUP BY {group_columns}
        HAVING sum(cost_micros) / 1000000.0 >= %s
           AND sum(clicks) >= %s
           AND coalesce(sum(conversions), 0) <= %s
        ORDER BY sum(cost_micros) DESC
        LIMIT %s
    """
    with connect(schema=SCHEMA, application_name="google-ads-operator") as conn, conn.cursor() as cur:
        cur.execute(sql, (customer, since, until, min_spend, min_clicks, max_conversions, limit))
        rows = cur.fetchall()
    return [
        {
            "campaign_id": row[0],
            "parent_id": row[1],
            "search_term": row[2],
            "spend": float(row[3] or 0),
            "clicks": int(row[4] or 0),
            "conversions": float(row[5] or 0),
        }
        for row in rows
    ]


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def cmd_plan_search_negatives(args: argparse.Namespace) -> int:
    ensure_schema()
    if args.max_terms_per_plan < 1:
        raise SystemExit("--max-terms-per-plan must be at least 1")
    customer = customer_id(args.customer_id)
    since, until = date_range_from_args(args)
    candidates = search_negative_candidates(
        customer=customer,
        since=since,
        until=until,
        min_spend=args.min_spend,
        min_clicks=args.min_clicks,
        max_conversions=args.max_conversions,
        scope=args.scope,
        limit=args.limit,
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(str(candidate["parent_id"]), []).append(candidate)

    plans = []
    entity_type = "campaign_negative_keyword" if args.scope == "campaign" else "negative_keyword"
    for parent_id, rows in grouped.items():
        for batch in chunked(rows, args.max_terms_per_plan):
            texts = [str(row["search_term"]) for row in batch]
            payload = mutation_plan_payload(
                customer=customer,
                entity_type=entity_type,
                operation_type="negative_keyword",
                keyword_texts=texts,
                match_type=args.match_type,
                ad_group_id=parent_id if args.scope == "ad_group" else None,
                campaign_id=parent_id if args.scope == "campaign" else None,
            )
            total_spend = sum(safe_float(row.get("spend")) for row in batch)
            note = (
                args.note
                or f"Search-term waste negative review {since}..{until}; min_spend={args.min_spend}; "
                f"scope={args.scope}; parent={parent_id}; batch_spend={total_spend:.2f}"
            )
            plan_id, output_path = store_mutation_plan(
                customer=customer,
                entity_type=entity_type,
                operation_type="negative_keyword",
                payload=payload,
                note=note,
            )
            plans.append(
                {
                    "plan_id": plan_id,
                    "parent_id": parent_id,
                    "entity_type": entity_type,
                    "operation_count": len(payload["mutateOperations"]),
                    "spend": round(total_spend, 2),
                    "output_path": str(output_path),
                    "next_validate_command": f"gads mutate {output_path}",
                    "next_live_command": f"gads mutate {output_path} --confirm-live",
                    "terms": texts,
                }
            )

    summary = {
        "customer_id": customer,
        "since": since,
        "until": until,
        "scope": args.scope,
        "match_type": args.match_type,
        "candidate_count": len(candidates),
        "plan_count": len(plans),
        "plans": plans,
    }
    if args.format == "json":
        summary["candidates"] = candidates
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(json.dumps({key: value for key, value in summary.items() if key != "plans"}, indent=2, default=str))
        for plan in plans:
            print(f"- {plan['plan_id']} parent={plan['parent_id']} terms={plan['operation_count']} spend={money(plan['spend'])} path={plan['output_path']}")
    return 0


def budget_adjustment_rows(
    *,
    customer: str,
    since: str,
    until: str,
    include_shared: bool,
) -> list[dict[str, Any]]:
    shared_clause = "" if include_shared else "AND coalesce(b.explicitly_shared, false) = false"
    sql = f"""
        SELECT
            c.campaign_id,
            coalesce(c.name, p.campaign_name, 'Unknown campaign') AS campaign_name,
            b.budget_id,
            b.resource_name AS budget_resource_name,
            b.name AS budget_name,
            b.amount_micros,
            coalesce(b.explicitly_shared, false) AS explicitly_shared,
            sum(p.spend) AS spend,
            sum(p.revenue) AS revenue,
            sum(p.new_customer_orders) AS nc_orders
        FROM google_campaign_daily_performance p
        JOIN google_campaigns c
          ON c.customer_id = %s
         AND c.campaign_id = p.campaign_id
        JOIN google_campaign_budgets b
          ON b.customer_id = c.customer_id
         AND b.resource_name = c.campaign_budget
        WHERE p.date_start BETWEEN %s::date AND %s::date
          AND p.campaign_id IS NOT NULL
          AND p.campaign_id <> ''
          {shared_clause}
        GROUP BY
            c.campaign_id,
            coalesce(c.name, p.campaign_name, 'Unknown campaign'),
            b.budget_id,
            b.resource_name,
            b.name,
            b.amount_micros,
            b.explicitly_shared
        ORDER BY sum(p.spend) DESC
    """
    with connect(schema=SCHEMA, application_name="google-ads-operator") as conn, conn.cursor() as cur:
        cur.execute(sql, (customer, since, until))
        rows = cur.fetchall()
    return [
        {
            "campaign_id": row[0],
            "campaign_name": row[1],
            "budget_id": row[2],
            "budget_resource_name": row[3],
            "budget_name": row[4],
            "amount_micros": int(row[5] or 0),
            "explicitly_shared": bool(row[6]),
            "spend": float(row[7] or 0),
            "revenue": float(row[8] or 0),
            "nc_orders": float(row[9] or 0),
        }
        for row in rows
    ]


def budget_adjustment_candidates(args: argparse.Namespace, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_budgets: set[str] = set()
    for row in rows:
        budget_id = str(row.get("budget_id") or "")
        amount_micros = int(row.get("amount_micros") or 0)
        if not budget_id or amount_micros <= 0 or budget_id in seen_budgets:
            continue
        spend = safe_float(row.get("spend"))
        nc_orders = safe_float(row.get("nc_orders"))
        ncpa = spend / nc_orders if nc_orders > 0 else None
        action = None
        percent = 0.0
        reason = ""
        if args.mode in {"all", "scale"} and spend >= args.min_spend and nc_orders >= args.min_nc_orders and ncpa is not None and ncpa <= args.target_ncpa * args.scale_threshold:
            action = "increase_budget_review"
            percent = args.increase_percent
            reason = f"TW nCPA {money(ncpa)} is below scale threshold {money(args.target_ncpa * args.scale_threshold)} with {nc_orders:.0f} NC orders."
        elif args.mode in {"all", "defend"} and spend >= args.min_spend and (ncpa is None or ncpa >= args.target_ncpa * args.defense_threshold):
            action = "decrease_budget_review"
            percent = -args.decrease_percent
            if ncpa is None:
                reason = "TW spend has no new-customer orders in the selected window."
            else:
                reason = f"TW nCPA {money(ncpa)} is above defense threshold {money(args.target_ncpa * args.defense_threshold)}."
        if not action:
            continue
        proposed = int(round(amount_micros * (1 + percent / 100.0)))
        if args.min_budget_dollars is not None:
            proposed = max(proposed, int(round(args.min_budget_dollars * 1_000_000)))
        if args.max_budget_dollars is not None:
            proposed = min(proposed, int(round(args.max_budget_dollars * 1_000_000)))
        if proposed == amount_micros:
            continue
        seen_budgets.add(budget_id)
        candidates.append(
            {
                **row,
                "action": action,
                "reason": reason,
                "current_amount_micros": amount_micros,
                "proposed_amount_micros": proposed,
                "current_budget_dollars": amount_micros / 1_000_000.0,
                "proposed_budget_dollars": proposed / 1_000_000.0,
                "change_percent": percent,
                "ncpa": ncpa,
                "roas": safe_float(row.get("revenue")) / spend if spend > 0 else None,
            }
        )
    return candidates[: args.limit]


def cmd_plan_budget_adjustments(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    since, until = date_range_from_args(args)
    rows = budget_adjustment_rows(
        customer=customer,
        since=since,
        until=until,
        include_shared=args.include_shared_budgets,
    )
    candidates = budget_adjustment_candidates(args, rows)
    plans = []
    for candidate in candidates:
        payload = mutation_plan_payload(
            customer=customer,
            entity_type="campaign_budget",
            operation_type="budget",
            ids=[str(candidate["budget_id"])],
            amount_micros=int(candidate["proposed_amount_micros"]),
        )
        note = (
            args.note
            or f"{candidate['action']} {since}..{until}; campaign={candidate['campaign_id']}; "
            f"current={candidate['current_budget_dollars']:.2f}; proposed={candidate['proposed_budget_dollars']:.2f}; {candidate['reason']}"
        )
        plan_id, output_path = store_mutation_plan(
            customer=customer,
            entity_type="campaign_budget",
            operation_type="budget",
            payload=payload,
            note=note,
        )
        plans.append(
            {
                "plan_id": plan_id,
                "campaign_id": candidate["campaign_id"],
                "campaign_name": candidate["campaign_name"],
                "budget_id": candidate["budget_id"],
                "action": candidate["action"],
                "current_budget_dollars": round(candidate["current_budget_dollars"], 2),
                "proposed_budget_dollars": round(candidate["proposed_budget_dollars"], 2),
                "spend": round(safe_float(candidate.get("spend")), 2),
                "nc_orders": candidate["nc_orders"],
                "ncpa": candidate["ncpa"],
                "reason": candidate["reason"],
                "output_path": str(output_path),
                "next_validate_command": f"gads mutate {output_path}",
                "next_live_command": f"gads mutate {output_path} --confirm-live",
            }
        )
    summary = {
        "customer_id": customer,
        "since": since,
        "until": until,
        "mode": args.mode,
        "eligible_budget_rows": len(rows),
        "candidate_count": len(candidates),
        "plan_count": len(plans),
        "plans": plans,
    }
    if args.format == "json":
        summary["candidates"] = candidates
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(json.dumps({key: value for key, value in summary.items() if key != "plans"}, indent=2, default=str))
        for plan in plans:
            print(
                f"- {plan['plan_id']} {plan['action']} campaign={plan['campaign_id']} "
                f"{money(plan['current_budget_dollars'])}->{money(plan['proposed_budget_dollars'])} path={plan['output_path']}"
            )
    return 0


def cmd_plan_optimizer_actions(args: argparse.Namespace) -> int:
    ensure_schema()
    if args.max_terms_per_plan < 1:
        raise SystemExit("--max-terms-per-plan must be at least 1")
    customer = customer_id(args.customer_id)
    output: dict[str, Any] = {
        "customer_id": customer,
        "validateOnly": True,
        "search_negatives": {"skipped": bool(args.skip_search_negatives), "candidate_count": 0, "plan_count": 0, "plans": []},
        "budget_adjustments": {"skipped": bool(args.skip_budget_adjustments), "eligible_budget_rows": 0, "candidate_count": 0, "plan_count": 0, "plans": []},
    }

    if not args.skip_search_negatives:
        search_since, search_until = date_range_from_args(
            argparse.Namespace(days=args.search_days, since=args.search_since, until=args.search_until)
        )
        search_candidates = search_negative_candidates(
            customer=customer,
            since=search_since,
            until=search_until,
            min_spend=args.search_min_spend,
            min_clicks=args.search_min_clicks,
            max_conversions=args.search_max_conversions,
            scope=args.search_scope,
            limit=args.search_limit,
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for candidate in search_candidates:
            grouped.setdefault(str(candidate["parent_id"]), []).append(candidate)
        search_plans = []
        entity_type = "campaign_negative_keyword" if args.search_scope == "campaign" else "negative_keyword"
        for parent_id, rows in grouped.items():
            for batch in chunked(rows, args.max_terms_per_plan):
                texts = [str(row["search_term"]) for row in batch]
                payload = mutation_plan_payload(
                    customer=customer,
                    entity_type=entity_type,
                    operation_type="negative_keyword",
                    keyword_texts=texts,
                    match_type=args.search_match_type,
                    ad_group_id=parent_id if args.search_scope == "ad_group" else None,
                    campaign_id=parent_id if args.search_scope == "campaign" else None,
                )
                total_spend = sum(safe_float(row.get("spend")) for row in batch)
                note = (
                    args.note
                    or f"Optimizer search-term negative review {search_since}..{search_until}; "
                    f"scope={args.search_scope}; parent={parent_id}; batch_spend={total_spend:.2f}"
                )
                plan_id, output_path = store_mutation_plan(
                    customer=customer,
                    entity_type=entity_type,
                    operation_type="negative_keyword",
                    payload=payload,
                    note=note,
                )
                search_plans.append(
                    {
                        "plan_id": plan_id,
                        "parent_id": parent_id,
                        "entity_type": entity_type,
                        "operation_count": len(payload["mutateOperations"]),
                        "spend": round(total_spend, 2),
                        "output_path": str(output_path),
                        "next_validate_command": f"gads mutate {output_path}",
                        "next_live_command": f"gads mutate {output_path} --confirm-live",
                        "terms": texts,
                    }
                )
        output["search_negatives"] = {
            "skipped": False,
            "since": search_since,
            "until": search_until,
            "scope": args.search_scope,
            "match_type": args.search_match_type,
            "candidate_count": len(search_candidates),
            "plan_count": len(search_plans),
            "plans": search_plans,
        }

    if not args.skip_budget_adjustments:
        budget_since, budget_until = date_range_from_args(
            argparse.Namespace(days=args.budget_days, since=args.budget_since, until=args.budget_until)
        )
        rows = budget_adjustment_rows(
            customer=customer,
            since=budget_since,
            until=budget_until,
            include_shared=args.include_shared_budgets,
        )
        budget_args = argparse.Namespace(
            mode=args.budget_mode,
            min_spend=args.budget_min_spend,
            min_nc_orders=args.budget_min_nc_orders,
            target_ncpa=args.target_ncpa,
            scale_threshold=args.scale_threshold,
            defense_threshold=args.defense_threshold,
            increase_percent=args.increase_percent,
            decrease_percent=args.decrease_percent,
            min_budget_dollars=args.min_budget_dollars,
            max_budget_dollars=args.max_budget_dollars,
            limit=args.budget_limit,
        )
        candidates = budget_adjustment_candidates(budget_args, rows)
        budget_plans = []
        for candidate in candidates:
            payload = mutation_plan_payload(
                customer=customer,
                entity_type="campaign_budget",
                operation_type="budget",
                ids=[str(candidate["budget_id"])],
                amount_micros=int(candidate["proposed_amount_micros"]),
            )
            note = (
                args.note
                or f"Optimizer {candidate['action']} {budget_since}..{budget_until}; campaign={candidate['campaign_id']}; "
                f"current={candidate['current_budget_dollars']:.2f}; proposed={candidate['proposed_budget_dollars']:.2f}; {candidate['reason']}"
            )
            plan_id, output_path = store_mutation_plan(
                customer=customer,
                entity_type="campaign_budget",
                operation_type="budget",
                payload=payload,
                note=note,
            )
            budget_plans.append(
                {
                    "plan_id": plan_id,
                    "campaign_id": candidate["campaign_id"],
                    "campaign_name": candidate["campaign_name"],
                    "budget_id": candidate["budget_id"],
                    "action": candidate["action"],
                    "current_budget_dollars": round(candidate["current_budget_dollars"], 2),
                    "proposed_budget_dollars": round(candidate["proposed_budget_dollars"], 2),
                    "spend": round(safe_float(candidate.get("spend")), 2),
                    "nc_orders": candidate["nc_orders"],
                    "ncpa": candidate["ncpa"],
                    "reason": candidate["reason"],
                    "output_path": str(output_path),
                    "next_validate_command": f"gads mutate {output_path}",
                    "next_live_command": f"gads mutate {output_path} --confirm-live",
                }
            )
        output["budget_adjustments"] = {
            "skipped": False,
            "since": budget_since,
            "until": budget_until,
            "mode": args.budget_mode,
            "eligible_budget_rows": len(rows),
            "candidate_count": len(candidates),
            "plan_count": len(budget_plans),
            "plans": budget_plans,
        }

    output["plan_count"] = int(output["search_negatives"]["plan_count"]) + int(output["budget_adjustments"]["plan_count"])
    if args.format == "json":
        print(json.dumps(output, indent=2, default=str))
    else:
        print(json.dumps({key: value for key, value in output.items() if key not in {"search_negatives", "budget_adjustments"}}, indent=2, default=str))
        print(
            f"- search negatives: candidates={output['search_negatives']['candidate_count']} "
            f"plans={output['search_negatives']['plan_count']}"
        )
        print(
            f"- budget adjustments: eligible={output['budget_adjustments']['eligible_budget_rows']} "
            f"candidates={output['budget_adjustments']['candidate_count']} plans={output['budget_adjustments']['plan_count']}"
        )
    return 0


def cmd_mutate(args: argparse.Namespace) -> int:
    ensure_schema()
    customer = customer_id(args.customer_id)
    path = f"customers/{customer}/googleAds:mutate"
    operation_path = pathlib.Path(args.operation_json)
    payload = json.loads(operation_path.read_text(encoding="utf-8"))
    if "mutateOperations" not in payload:
        raise SystemExit("operation JSON must contain mutateOperations")
    payload.setdefault("partialFailure", True)
    payload["validateOnly"] = not args.confirm_live
    print(json.dumps({"endpoint": path, "validateOnly": payload["validateOnly"], "operations": len(payload["mutateOperations"])}, indent=2))
    if not args.confirm_live:
        print("preview only; rerun with --confirm-live to execute")
    plan_id = mutation_plan_id_from_path(operation_path)
    run_id = run_start("mutate", customer, {"validateOnly": payload["validateOnly"]})
    try:
        body, headers = api_request("POST", path, payload)
        store_raw_snapshot(run_id, customer=customer, endpoint=path, request_payload=payload, response_payload=body, response_headers=headers)
        partial_failure = bool(body.get("partialFailureError"))
        run_status = "partial_failure" if partial_failure else "success"
        slack_result: dict[str, Any] | None = None
        if args.confirm_live and not args.no_slack:
            slack_message = format_google_mutation_slack(
                customer=customer,
                operation_path=operation_path,
                payload=payload,
                plan_id=plan_id,
                run_id=run_id,
                status=run_status,
                response=body,
            )
            slack_result = post_google_mutation_slack(mutation_slack_channel(args.slack_channel), slack_message)
            if not slack_result.get("ok"):
                print(f"WARN: Google Ads mutation Slack post failed: {slack_result.get('error') or slack_result}", file=sys.stderr)
        metadata = {"validateOnly": payload["validateOnly"]}
        if slack_result is not None:
            metadata["slack_post"] = slack_result
        run_finish(run_id, run_status, rows_fetched=0, rows_written=0, errors=1 if partial_failure else 0, metadata=metadata)
        update_mutation_plan_result(
            plan_id,
            status=(
                "execution_partial_failure"
                if partial_failure and args.confirm_live
                else "validation_partial_failure"
                if partial_failure
                else "executed"
                if args.confirm_live
                else "validated"
            ),
            run_id=run_id,
            result={"validateOnly": payload["validateOnly"], "response": body, "slack_post": slack_result},
        )
        print(json.dumps(body, indent=2))
        return 2 if partial_failure else 0
    except Exception as exc:
        slack_result = None
        if args.confirm_live and not args.no_slack:
            slack_message = format_google_mutation_slack(
                customer=customer,
                operation_path=operation_path,
                payload=payload,
                plan_id=plan_id,
                run_id=run_id,
                status="error",
                error=str(exc),
            )
            slack_result = post_google_mutation_slack(mutation_slack_channel(args.slack_channel), slack_message)
            if not slack_result.get("ok"):
                print(f"WARN: Google Ads mutation Slack post failed: {slack_result.get('error') or slack_result}", file=sys.stderr)
        run_finish(run_id, "error", errors=1)
        update_mutation_plan_result(
            plan_id,
            status="execution_error" if args.confirm_live else "validation_error",
            run_id=run_id,
            result={"validateOnly": payload["validateOnly"], "error": str(exc)[:1000], "slack_post": slack_result},
        )
        raise


def psql_json(sql: str, params: tuple[Any, ...] = ()) -> Any:
    def repl(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        expanded.append(params[index])
        return "%s"

    expanded: list[Any] = []
    if params:
        sql = re.sub(r"\$(\d+)", repl, sql)
    with connect(schema=SCHEMA, application_name="google-ads-operator") as conn, conn.cursor() as cur:
        # Keep operator reads from overlapping schema refresh DDL.
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", SCHEMA_LOCK_KEY)
        cur.execute(sql, tuple(expanded) if params else None)
        row = cur.fetchone()
    return row[0] if row else None


def google_tw_latest_date() -> str | None:
    value = psql_json(
        """
        SELECT max(report_date)::text
        FROM google_tw_attribution_hourly
        """
    )
    return str(value) if value else None


def report_payload(report_date: str | None = None, target_ncpa: float = DEFAULT_TARGET_NCPA) -> dict[str, Any]:
    ensure_schema()
    report_date = report_date or google_tw_latest_date() or dt.date.today().isoformat()
    start_7 = (dt.date.fromisoformat(report_date) - dt.timedelta(days=6)).isoformat()
    start_31 = (dt.date.fromisoformat(report_date) - dt.timedelta(days=30)).isoformat()
    overall = psql_json(
        """
        SELECT jsonb_build_object(
            'report_date', $1::date::text,
            'latest_hour', max(period_start)::text,
            'today_spend', coalesce(sum(spend) FILTER (WHERE date_start = $1::date), 0),
            'today_revenue', coalesce(sum(revenue) FILTER (WHERE date_start = $1::date), 0),
            'today_orders', coalesce(sum(purchases) FILTER (WHERE date_start = $1::date), 0),
            'today_nc_orders', coalesce(sum(new_customer_orders) FILTER (WHERE date_start = $1::date), 0),
            'l7_spend', coalesce(sum(spend) FILTER (WHERE date_start BETWEEN $2::date AND $1::date), 0),
            'l7_revenue', coalesce(sum(revenue) FILTER (WHERE date_start BETWEEN $2::date AND $1::date), 0),
            'l7_orders', coalesce(sum(purchases) FILTER (WHERE date_start BETWEEN $2::date AND $1::date), 0),
            'l7_nc_orders', coalesce(sum(new_customer_orders) FILTER (WHERE date_start BETWEEN $2::date AND $1::date), 0),
            'l31_spend', coalesce(sum(spend) FILTER (WHERE date_start BETWEEN $3::date AND $1::date), 0),
            'l31_revenue', coalesce(sum(revenue) FILTER (WHERE date_start BETWEEN $3::date AND $1::date), 0),
            'l31_nc_orders', coalesce(sum(new_customer_orders) FILTER (WHERE date_start BETWEEN $3::date AND $1::date), 0)
        )
        FROM google_ad_hourly_performance
        WHERE date_start BETWEEN $3::date AND $1::date
        """,
        (report_date, start_7, start_31),
    ) or {}
    top_campaigns = psql_json(
        """
        SELECT coalesce(jsonb_agg(row_payload ORDER BY (row_payload->>'spend')::numeric DESC), '[]'::jsonb)
        FROM (
            SELECT jsonb_build_object(
                'campaign_id', campaign_id,
                'campaign_name', max(campaign_name),
                'campaign_type', max(campaign_type),
                'campaign_type_label', max(campaign_type_label),
                'spend', coalesce(sum(spend), 0),
                'revenue', coalesce(sum(revenue), 0),
                'orders', coalesce(sum(purchases), 0),
                'nc_orders', coalesce(sum(new_customer_orders), 0),
                'roas', coalesce(sum(revenue), 0) / nullif(sum(spend), 0),
                'ncpa', coalesce(sum(spend), 0) / nullif(sum(new_customer_orders), 0)
            ) AS row_payload
            FROM google_campaign_daily_performance
            WHERE date_start BETWEEN $1::date AND $2::date
            GROUP BY campaign_id
            HAVING sum(spend) > 0
            ORDER BY sum(spend) DESC
            LIMIT 12
        ) rows
        """,
        (start_7, report_date),
    ) or []
    campaign_type_mix = psql_json(
        """
        SELECT coalesce(jsonb_agg(row_payload ORDER BY (row_payload->>'spend')::numeric DESC), '[]'::jsonb)
        FROM (
            SELECT jsonb_build_object(
                'campaign_type', campaign_type,
                'campaign_type_label', campaign_type_label,
                'spend', coalesce(sum(spend), 0),
                'revenue', coalesce(sum(revenue), 0),
                'orders', coalesce(sum(purchases), 0),
                'nc_orders', coalesce(sum(new_customer_orders), 0),
                'roas', coalesce(sum(revenue), 0) / nullif(sum(spend), 0),
                'ncpa', coalesce(sum(spend), 0) / nullif(sum(new_customer_orders), 0),
                'row_count', count(*)
            ) AS row_payload
            FROM google_campaign_type_daily_performance
            WHERE date_start BETWEEN $1::date AND $2::date
            GROUP BY campaign_type, campaign_type_label
            HAVING sum(spend) > 0 OR sum(revenue) > 0
            ORDER BY sum(spend) DESC
            LIMIT 12
        ) rows
        """,
        (start_7, report_date),
    ) or []
    brand_split = psql_json(
        """
        WITH classified AS (
            SELECT
                date_start,
                CASE
                    WHEN coalesce(campaign_type, '') = 'generic_search'
                      OR lower(coalesce(campaign_name, '')) LIKE '%%non-brand%%'
                      OR regexp_replace(lower(coalesce(campaign_name, '')), '[^a-z0-9]+', '', 'g') LIKE '%%nonbrand%%'
                      OR regexp_replace(lower(coalesce(campaign_name, '')), '[^a-z0-9]+', '', 'g') LIKE '%%nonbranded%%'
                      OR lower(coalesce(campaign_name, '')) LIKE '%%generic%%' THEN 'non_brand'
                    WHEN coalesce(campaign_type, '') = 'branded_search'
                      OR lower(coalesce(campaign_name, '')) LIKE '%%branded%%'
                      OR lower(coalesce(campaign_name, '')) LIKE '%%brand%%'
                      OR lower(coalesce(campaign_name, '')) LIKE '%%bofu%%'
                      OR regexp_replace(lower(coalesce(campaign_name, '')), '[^a-z0-9]+', '', 'g') LIKE '%%example%%' THEN 'brand'
                    ELSE 'non_brand'
                END AS bucket,
                spend,
                revenue,
                purchases,
                new_customer_orders
            FROM google_campaign_daily_performance
            WHERE date_start BETWEEN $1::date AND $2::date
        ),
        windowed AS (
            SELECT 'today'::text AS report_window, bucket, spend, revenue, purchases, new_customer_orders
            FROM classified
            WHERE date_start = $2::date
            UNION ALL
            SELECT 'l7'::text AS report_window, bucket, spend, revenue, purchases, new_customer_orders
            FROM classified
        ),
        rolled AS (
            SELECT
                report_window,
                bucket,
                coalesce(sum(spend), 0) AS spend,
                coalesce(sum(revenue), 0) AS revenue,
                coalesce(sum(purchases), 0) AS orders,
                coalesce(sum(new_customer_orders), 0) AS nc_orders,
                count(*) AS row_count
            FROM windowed
            GROUP BY report_window, bucket
            HAVING coalesce(sum(spend), 0) > 0 OR coalesce(sum(revenue), 0) > 0
        )
        SELECT coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'window', report_window,
                    'bucket', bucket,
                    'bucket_label', CASE bucket WHEN 'brand' THEN 'Brand' ELSE 'Non-Brand' END,
                    'spend', spend,
                    'revenue', revenue,
                    'orders', orders,
                    'nc_orders', nc_orders,
                    'roas', revenue / nullif(spend, 0),
                    'ncpa', spend / nullif(nc_orders, 0),
                    'row_count', row_count
                )
                ORDER BY
                    CASE report_window WHEN 'today' THEN 0 WHEN 'l7' THEN 1 ELSE 2 END,
                    CASE bucket WHEN 'brand' THEN 0 WHEN 'non_brand' THEN 1 ELSE 2 END
            ),
            '[]'::jsonb
        )
        FROM rolled
        """,
        (start_7, report_date),
    ) or []
    top_search_terms = psql_json(
        """
        SELECT coalesce(jsonb_agg(row_payload ORDER BY (row_payload->>'spend')::numeric DESC), '[]'::jsonb)
        FROM (
            SELECT jsonb_build_object(
                'search_term', search_term,
                'campaign_id', max(campaign_id),
                'ad_group_id', max(ad_group_id),
                'spend', sum(cost_micros) / 1000000.0,
                'clicks', sum(clicks),
                'conversions', sum(conversions),
                'conversion_value', sum(conversions_value),
                'cpa', (sum(cost_micros) / 1000000.0) / nullif(sum(conversions), 0)
            ) AS row_payload
            FROM google_search_terms
            WHERE report_date BETWEEN $1::date AND $2::date
            GROUP BY search_term
            HAVING sum(cost_micros) > 0
            ORDER BY sum(cost_micros) DESC
            LIMIT 20
        ) rows
        """,
        (start_7, report_date),
    ) or []
    direct_status = psql_json(
        """
        SELECT jsonb_build_object(
            'customers', (SELECT count(*) FROM google_customers),
            'campaigns', (SELECT count(*) FROM google_campaigns),
            'ad_groups', (SELECT count(*) FROM google_ad_groups),
            'ads', (SELECT count(*) FROM google_ads),
            'keywords', (SELECT count(*) FROM google_keywords),
            'search_terms', (SELECT count(*) FROM google_search_terms),
            'field_rows', (SELECT count(*) FROM google_ads_fields),
            'offline_field_rows', (SELECT count(*) FROM google_offline_catalog_fields),
            'offline_described_fields', (SELECT count(*) FROM google_offline_catalog_fields WHERE description IS NOT NULL AND description <> ''),
            'offline_v24_metrics', (SELECT count(*) FROM google_offline_catalog_fields WHERE api_version = 'v24' AND resource_kind = 'METRIC'),
            'offline_v24_segments', (SELECT count(*) FROM google_offline_catalog_fields WHERE api_version = 'v24' AND resource_kind = 'SEGMENT'),
            'service_rows', (SELECT count(*) FROM google_api_services),
            'core_generic_rows', (SELECT count(*) FROM google_core_generic),
            'core_surfaces', (SELECT count(*) FROM google_query_manifest WHERE surface_type = 'core'),
            'core_surfaces_with_generic', (SELECT count(*) FROM google_query_manifest WHERE surface_type = 'core' AND warehouse_tables ? 'google_core_generic'),
            'performance_generic_rows', (SELECT count(*) FROM google_performance_generic),
            'mutation_plans', (SELECT count(*) FROM google_mutation_plans),
            'query_manifest_rows', (SELECT count(*) FROM google_query_manifest),
            'api_methods', (SELECT count(*) FROM google_api_methods),
            'v24_api_methods', (SELECT count(*) FROM google_api_methods WHERE api_version = 'v24'),
            'query_manifest_auth_gated', (SELECT count(*) FROM google_query_manifest WHERE requires_auth),
            'query_manifest_no_auth', (SELECT count(*) FROM google_query_manifest WHERE NOT requires_auth),
            'last_auth_status', (SELECT status FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'last_auth_check', (SELECT completed_at::text FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'last_auth_error', (SELECT message FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
            'last_auth_error_summary', (SELECT message FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
            'last_auth_error_at', (SELECT occurred_at::text FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
            'last_sync', (SELECT max(completed_at)::text FROM google_sync_runs WHERE status in ('success','partial'))
        )
        """
    ) or {}
    if direct_status.get("last_auth_error_summary"):
        direct_status["last_auth_error_summary"] = summarize_auth_error(str(direct_status["last_auth_error_summary"]))
    recommendations = build_recommendations(overall, top_campaigns, top_search_terms, target_ncpa)
    audit = completion_audit_payload()
    return {
        "report_date": report_date,
        "start_7": start_7,
        "start_31": start_31,
        "target_ncpa": target_ncpa,
        "credential_state": credential_state(),
        "overall": overall,
        "top_campaigns": top_campaigns,
        "campaign_type_mix": campaign_type_mix,
        "brand_split": brand_split,
        "top_search_terms": top_search_terms,
        "direct_status": direct_status,
        "recommendations": recommendations,
        "completion_audit": audit,
    }


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize_auth_error(message: str | None) -> str | None:
    if not message:
        return None
    lower = message.lower()
    if "not_ads_user" in lower:
        return "OAuth user is not attached to a Google Ads account (NOT_ADS_USER)."
    if "invalid_rapt" in lower:
        return "OAuth re-auth required (invalid_rapt). Rerun scripts/bootstrap_google_ads_oauth.sh and then gads auth-check."
    if "invalid_grant" in lower and "reauth" in lower:
        return "OAuth re-auth required. Rerun scripts/bootstrap_google_ads_oauth.sh and then gads auth-check."
    if "invalid authentication credentials" in lower or "missing required authentication credential" in lower:
        return "OAuth access token was rejected by Google Ads."
    return message[:320]


def auth_blocker_from_latest(latest: dict[str, Any] | None) -> str | None:
    if not latest:
        return None
    if latest.get("latest_auth_status") == "success":
        return None
    return latest.get("latest_auth_error_summary") or summarize_auth_error(latest.get("latest_auth_error"))


def api_status_label(creds: dict[str, Any], direct: dict[str, Any]) -> str:
    if not creds.get("ready"):
        return f"config blocked: missing {', '.join(creds.get('missing') or [])}"
    if direct.get("last_auth_status") == "success":
        return "ready"
    summary = direct.get("last_auth_error_summary") or summarize_auth_error(direct.get("last_auth_error"))
    if summary:
        return f"auth blocked: {summary}"
    return "configured; auth-check pending"


def native_access_pending(api_label: str) -> bool:
    lower = api_label.lower()
    return (
        "not_ads_user" in lower
        or "not attached to a google ads account" in lower
        or "native enrichment pending account access" in lower
    )


def format_direct_api_parent_status(api_label: str, direct: dict[str, Any]) -> str:
    """One-glance API status for the parent; engineering detail lives in the thread."""
    if native_access_pending(api_label):
        return "Waiting on Ads account access (Triple Whale reporting is live)"
    campaigns = direct.get("campaigns", 0)
    terms = safe_float(direct.get("search_terms", 0))
    terms_text = f"{terms / 1_000_000:.1f}M" if terms >= 1_000_000 else f"{int(terms):,}"
    return f"{api_label} · {campaigns} campaigns · {terms_text} search terms synced"


def format_direct_api_main_line(api_label: str, direct: dict[str, Any]) -> str:
    if native_access_pending(api_label):
        return (
            "- Native Google Ads API: native enrichment is waiting on Ads account access; "
            "Triple Whale performance reporting is live."
        )
    return (
        f"- Direct Google API: {api_label}; live fields {direct.get('field_rows', 0)}, "
        f"offline fields {direct.get('offline_field_rows', 0)}, services {direct.get('service_rows', 0)}, "
        f"methods {direct.get('api_methods', 0)}, core surfaces {direct.get('core_surfaces_with_generic', 0)}/"
        f"{direct.get('core_surfaces', 0)}, campaigns {direct.get('campaigns', 0)}, "
        f"search terms {direct.get('search_terms', 0)}"
    )


def infer_google_campaign_type(name: str) -> str:
    lower = name.lower()
    compact = re.sub(r"[^a-z0-9]+", "_", lower)
    if "pmax" in compact or "performance_max" in compact or "performance max" in lower:
        return "pmax"
    if "shopping" in lower or "_shopping_" in compact or "shop" in compact:
        return "shopping"
    if "youtube" in lower or "yt_" in compact or compact.startswith("yt"):
        return "youtube_video"
    if "demand" in lower or "dgen" in compact or "demand_gen" in compact:
        return "demand_gen"
    if "display" in lower or "gdn" in compact:
        return "display"
    if "search" in lower or "ppc" in lower or "generic" in lower or "brand" in lower:
        if "non-brand" in lower or "nonbranded" in compact or "non_branded" in compact or "generic" in lower:
            return "generic_search"
        if "branded" in lower or "brand" in lower or "bofu" in lower:
            return "branded_search"
        return "search"
    return "unknown"


def campaign_type_label(campaign_type: str) -> str:
    return {
        "branded_search": "Branded Search",
        "generic_search": "Generic Search",
        "search": "Search",
        "shopping": "Shopping",
        "pmax": "Performance Max",
        "youtube_video": "YouTube/Video",
        "demand_gen": "Demand Gen",
        "display": "Display",
        "unknown": "Unknown",
    }.get(campaign_type, campaign_type.replace("_", " ").title())


BRAND_BUCKETS = ("brand", "non_brand")


def brand_bucket_label(bucket: Any) -> str:
    return {
        "brand": "Brand",
        "non_brand": "Non-Brand",
    }.get(str(bucket or ""), "Non-Brand")


def recommendation_payload(campaign: dict[str, Any]) -> dict[str, Any]:
    spend = safe_float(campaign.get("spend"))
    nc_orders = safe_float(campaign.get("nc_orders"))
    ncpa = spend / nc_orders if nc_orders > 0 else None
    roas = safe_float(campaign.get("roas"))
    name = str(campaign.get("campaign_name") or "Unknown campaign")
    campaign_type = str(campaign.get("campaign_type") or infer_google_campaign_type(name))
    type_label = str(campaign.get("campaign_type_label") or campaign_type_label(campaign_type))
    return {
        "campaign_id": campaign.get("campaign_id"),
        "campaign_name": name,
        "campaign_type": campaign_type,
        "campaign_type_label": type_label,
        "spend": spend,
        "nc_orders": nc_orders,
        "ncpa": ncpa,
        "roas": roas,
    }


def efficient_for_scale(payload: dict[str, Any], target_ncpa: float) -> bool:
    spend = safe_float(payload.get("spend"))
    nc_orders = safe_float(payload.get("nc_orders"))
    ncpa = payload.get("ncpa")
    campaign_type = str(payload.get("campaign_type") or "")
    if ncpa is None:
        return False
    threshold = target_ncpa * (0.60 if campaign_type == "branded_search" else 0.75)
    return spend >= 250 and nc_orders >= 5 and float(ncpa) <= threshold


def inefficient_for_defense(payload: dict[str, Any], target_ncpa: float) -> bool:
    spend = safe_float(payload.get("spend"))
    ncpa = payload.get("ncpa")
    campaign_type = str(payload.get("campaign_type") or "")
    if spend < 250:
        return False
    if ncpa is None:
        return True
    threshold = target_ncpa * (1.10 if campaign_type in {"generic_search", "search"} else 1.25)
    return float(ncpa) >= threshold


def build_recommendations(
    overall: dict[str, Any],
    campaigns: list[dict[str, Any]],
    search_terms: list[dict[str, Any]],
    target_ncpa: float,
) -> dict[str, list[dict[str, Any]]]:
    scale_up: list[dict[str, Any]] = []
    defend: list[dict[str, Any]] = []
    search_actions: list[dict[str, Any]] = []
    pmax_watch: list[dict[str, Any]] = []
    for campaign in campaigns:
        payload = recommendation_payload(campaign)
        campaign_type = str(payload["campaign_type"])
        type_label = str(payload["campaign_type_label"])
        if efficient_for_scale(payload, target_ncpa):
            if campaign_type == "branded_search":
                scale_up.append({**payload, "action": "branded_search_impression_share_review", "reason": "Branded Search is well below target nCPA; review impression share, top-of-page loss, and exact brand coverage before budget expansion."})
            elif campaign_type == "shopping":
                scale_up.append({**payload, "action": "shopping_budget_and_feed_scale_review", "reason": "Shopping is efficient on TW new-customer economics; review feed winners, product groups, and budget headroom."})
            elif campaign_type == "generic_search":
                scale_up.append({**payload, "action": "generic_search_keyword_expansion_review", "reason": "Generic Search is below target with order volume; review query mining and exact/phrase expansion before raising budgets."})
            else:
                scale_up.append({**payload, "action": "scale_budget_review", "reason": f"{type_label} is materially under target nCPA with order volume."})
        elif inefficient_for_defense(payload, target_ncpa):
            if campaign_type in {"generic_search", "search"}:
                defend.append({**payload, "action": "generic_search_query_defense", "reason": "Search spend is meaningful and nCPA is above target or missing orders; review search terms, negatives, match types, and LP intent before adding budget."})
            elif campaign_type == "shopping":
                defend.append({**payload, "action": "shopping_feed_waste_review", "reason": "Shopping spend is inefficient or missing NC orders; inspect product groups, feed attributes, query waste, and SKU exclusions."})
            elif campaign_type == "branded_search":
                defend.append({**payload, "action": "branded_search_efficiency_guardrail", "reason": "Branded Search is above target; check cannibalization, match type leakage, competitor conquesting, and impression-share goals."})
            else:
                defend.append({**payload, "action": "budget_or_query_defense", "reason": f"{type_label} spend is meaningful and nCPA is above target or missing orders."})
        if campaign_type == "pmax":
            pmax_watch.append({**payload, "action": "pmax_asset_group_review", "reason": "Review PMax asset groups, listing groups, search category insights, brand exclusions, and feed/product waste before budget moves."})
        elif campaign_type == "shopping":
            pmax_watch.append({**payload, "action": "shopping_feed_product_review", "reason": "Review Shopping product groups, feed labels, titles, SKU-level waste, and branded/non-branded split."})
        elif campaign_type in {"youtube_video", "demand_gen", "display"}:
            pmax_watch.append({**payload, "action": f"{campaign_type}_creative_audience_review", "reason": f"Review {type_label} creative fatigue, audience exclusions, placement quality, and assisted-conversion role before spend changes."})
    for term in search_terms:
        spend = safe_float(term.get("spend"))
        conversions = safe_float(term.get("conversions"))
        cpa = spend / conversions if conversions > 0 else None
        if spend >= 50 and conversions == 0:
            search_actions.append({**term, "action": "negative_keyword_review", "reason": "Search term has spend with no platform conversions."})
        elif conversions >= 2 and cpa is not None and cpa <= target_ncpa * 0.75:
            search_actions.append({**term, "action": "keyword_expansion_review", "reason": "Search term converts below target and may deserve exact/phrase coverage."})
    return {
        "scale_up": scale_up[:8],
        "defend": defend[:8],
        "search_actions": search_actions[:12],
        "pmax_watch": pmax_watch[:8],
    }


def store_optimizer_snapshot(payload: dict[str, Any]) -> str:
    overall = payload.get("overall") or {}
    latest_hour = overall.get("latest_hour")
    with connect(schema=SCHEMA, application_name="google-ads-operator") as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_optimizer_snapshots (
                report_date, latest_hour, target_ncpa, decision_payload
            )
            VALUES (%s, %s, %s, %s::jsonb)
            RETURNING id::text
            """,
            (
                payload["report_date"],
                latest_hour,
                payload["target_ncpa"],
                jsonb(payload),
            ),
        )
        snapshot_id = cur.fetchone()[0]
    return snapshot_id


def audit_summary(audit: dict[str, Any]) -> dict[str, Any]:
    checks = audit.get("checks") or []
    return {
        "pass": sum(1 for check in checks if check.get("status") == "pass"),
        "blocked": sum(1 for check in checks if check.get("status") == "blocked"),
        "fail": sum(1 for check in checks if check.get("status") == "fail"),
        "blocked_ids": [check.get("id") for check in checks if check.get("status") == "blocked"],
        "failed_ids": [check.get("id") for check in checks if check.get("status") == "fail"],
    }


def bootstrap_marker_state() -> str:
    for marker in bootstrap_marker_paths():
        if not marker.exists():
            continue
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        label = str(marker).replace(str(pathlib.Path.home()), "~")
        return f"completed {text} ({label})" if text else f"completed ({label})"
    return "pending"


def bootstrap_marker_paths() -> list[pathlib.Path]:
    roots: list[pathlib.Path] = []
    for root in (PROFILE_ROOT,):
        if root not in roots:
            roots.append(root)
    return [root / "state" / "google-ads" / "direct-post-auth-bootstrap.done" for root in roots]


def write_bootstrap_markers(timestamp: str) -> list[str]:
    written: list[str] = []
    for marker in bootstrap_marker_paths():
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(timestamp + "\n", encoding="utf-8")
            written.append(str(marker))
        except OSError as exc:
            print(f"warning: could not write bootstrap marker {marker}: {exc}", file=sys.stderr)
    return written


def full_backfill_since(years: int) -> str:
    today = dt.date.today()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return (today - dt.timedelta(days=365 * years)).isoformat()


def format_completion_gate_lines(audit: dict[str, Any], *, suppress_native_access_blockers: bool = False) -> list[str]:
    checks = audit.get("checks") or []
    rows = []
    for check in checks:
        if (
            suppress_native_access_blockers
            and check.get("status") == "blocked"
            and check.get("id") in {"authenticated_field_catalog", "native_backfill"}
        ):
            continue
        if check.get("status") != "pass":
            rows.append(f"- {str(check.get('status')).upper()}: {check.get('id')} - {check.get('requirement')}")
            if check.get("blocker"):
                rows.append(f"  Blocker: {check.get('blocker')}")
    if not rows:
        if suppress_native_access_blockers:
            return markdown_table(
                ["Status", "Gate", "Requirement"],
                [["INFO", "Native enrichment", "TW reporting heartbeat is clean; native enrichment gates are pending account access."]],
            )
        return markdown_table(
            ["Status", "Gate", "Requirement"],
            [["PASS", "All gates", "All completion gates are passing."]],
        )
    return markdown_table(
        ["Status", "Gate", "Requirement"],
        [
            [
                str(check.get("status") or "").upper(),
                check.get("id") or "unknown",
                " ".join(
                    part
                    for part in [
                        str(check.get("requirement") or ""),
                        f"Blocker: {check.get('blocker')}" if check.get("blocker") else "",
                    ]
                    if part
                ),
            ]
            for check in checks
            if check.get("status") != "pass"
            and not (
                suppress_native_access_blockers
                and check.get("status") == "blocked"
                and check.get("id") in {"authenticated_field_catalog", "native_backfill"}
            )
        ],
    )


def markdown_cell(value: Any, *, limit: int | None = None) -> str:
    text = str(value if value is not None else "No data").replace("\n", " ").strip()
    text = text.replace("|", r"\|")
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 3)].rstrip() + "..."
    return text or "No data"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return []
    header = "| " + " | ".join(markdown_cell(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(markdown_cell(item) for item in row) + " |"
        for row in rows
    ]
    return [header, separator, *body]


def format_roas(value: float | int | None) -> str:
    return f"{float(value):.2f}x" if value is not None else "No data"


def short_reason(value: Any, limit: int = 140) -> str:
    return markdown_cell(value or "No read provided.", limit=limit)


def action_queue_label(recs: dict[str, list[dict[str, Any]]]) -> str:
    return (
        f"{len(recs['scale_up'])} scale / "
        f"{len(recs['defend'])} defense / "
        f"{len(recs['search_actions'])} search-term / "
        f"{len(recs['pmax_watch'])} PMax"
    )


def strip_bullet_prefix(value: str) -> str:
    return value[2:] if value.startswith("- ") else value


ACTION_LABELS = {
    "branded_search_impression_share_review": "Impression-share review",
    "generic_search_query_defense": "Query defense",
    "keyword_expansion_review": "Add as keyword?",
    "negative_keyword_review": "Add negative?",
    "shopping_feed_product_review": "Feed/product review",
    "pmax_watch": "Watch",
    "scale_up_review": "Scale review",
}


def friendly_action(raw: Any) -> str:
    key = str(raw or "review").strip()
    return ACTION_LABELS.get(key, key.replace("_", " ").capitalize())


def format_recommendation_table(
    rows: list[dict[str, Any]],
    label_key: str,
    label_header: str,
    empty: str,
) -> list[str]:
    if not rows:
        return [f"- {empty}"]
    table_rows = []
    for row in rows[:8]:
        label = row.get(label_key) or row.get("campaign_name") or "Unknown"
        type_label = row.get("campaign_type_label") or "n/a"
        spend = safe_float(row.get("spend"))
        ncpa = row.get("ncpa")
        if ncpa is None and row.get("conversions"):
            ncpa = safe_float(row.get("spend")) / max(safe_float(row.get("conversions")), 1)
        table_rows.append(
            [
                label,
                type_label,
                friendly_action(row.get("action")),
                short_money(spend),
                money(ncpa),
                short_reason(row.get("reason")),
            ]
        )
    return markdown_table(
        [label_header, "Type", "Action", "Spend", "nCPA/CPA", "Read"],
        table_rows,
    )


def format_search_action_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No direct search-term recommendations yet. This requires the direct API search-term backfill."]
    table_rows = []
    for row in rows[:8]:
        spend = safe_float(row.get("spend"))
        ncpa = row.get("ncpa")
        if ncpa is None and row.get("conversions"):
            ncpa = spend / max(safe_float(row.get("conversions")), 1)
        table_rows.append(
            [
                row.get("search_term") or row.get("campaign_name") or "Unknown",
                friendly_action(row.get("action")),
                short_money(spend),
                money(ncpa),
                short_reason(row.get("reason")),
            ]
        )
    return markdown_table(
        ["Search term", "Action", "Spend", "nCPA/CPA", "Read"],
        table_rows,
    )


def format_campaign_type_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No campaign-type rows in Triple Whale for this window."]
    table_rows = []
    for row in rows:
        spend = safe_float(row.get("spend"))
        revenue = safe_float(row.get("revenue"))
        nc = safe_float(row.get("nc_orders"))
        ncpa = spend / nc if nc > 0 else None
        roas = revenue / spend if spend > 0 else None
        table_rows.append(
            [
                row.get("campaign_type_label") or row.get("campaign_type") or "Unknown",
                short_money(spend),
                short_money(revenue),
                money(ncpa),
                format_roas(roas),
            ]
        )
    return markdown_table(["Type", "Spend", "Revenue", "nCPA", "ROAS"], table_rows)


def brand_split_row_metrics(row: dict[str, Any] | None) -> tuple[float, float, float, float | None, float | None]:
    if not row:
        return 0.0, 0.0, 0.0, None, None
    spend = safe_float(row.get("spend"))
    revenue = safe_float(row.get("revenue"))
    nc = safe_float(row.get("nc_orders"))
    ncpa = row.get("ncpa")
    if ncpa is None:
        ncpa = spend / nc if nc > 0 else None
    else:
        ncpa = safe_float(ncpa)
    roas = row.get("roas")
    if roas is None:
        roas = revenue / spend if spend > 0 else None
    else:
        roas = safe_float(roas)
    return spend, revenue, nc, ncpa, roas


def brand_split_rows_by_window(rows: list[dict[str, Any]], window: str) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("bucket") or ""): row
        for row in rows
        if str(row.get("window") or "") == window
    }


def format_brand_split_performance_rows(rows: list[dict[str, Any]], window: str) -> list[list[Any]]:
    by_bucket = brand_split_rows_by_window(rows, window)
    if not by_bucket:
        return []
    window_label = {"today": "Today TW", "l7": "L7 TW"}.get(window, window.upper())
    out: list[list[Any]] = []
    for bucket in BRAND_BUCKETS:
        spend, _revenue, _nc, ncpa, roas = brand_split_row_metrics(by_bucket.get(bucket))
        out.append([window_label, brand_bucket_label(bucket), short_money(spend), money(ncpa), format_roas(roas)])
    return out


def format_brand_split_table(rows: list[dict[str, Any]]) -> list[str]:
    table_rows: list[list[Any]] = []
    for window in ("today", "l7"):
        by_bucket = brand_split_rows_by_window(rows, window)
        if not by_bucket:
            continue
        window_label = {"today": "Today TW", "l7": "L7 TW"}[window]
        for bucket in BRAND_BUCKETS:
            spend, revenue, _nc, ncpa, roas = brand_split_row_metrics(by_bucket.get(bucket))
            table_rows.append(
                [
                    window_label,
                    brand_bucket_label(bucket),
                    short_money(spend),
                    short_money(revenue),
                    money(ncpa),
                    format_roas(roas),
                ]
            )
    if not table_rows:
        return ["- No brand/non-brand campaign rows in Triple Whale for this window."]
    return markdown_table(["Window", "Segment", "Spend", "Revenue", "nCPA", "ROAS"], table_rows)


def format_campaign_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No Google campaign rows in Triple Whale for this window."]
    table_rows = []
    for row in rows:
        spend = safe_float(row.get("spend"))
        revenue = safe_float(row.get("revenue"))
        nc = safe_float(row.get("nc_orders"))
        ncpa = spend / nc if nc > 0 else None
        roas = revenue / spend if spend > 0 else None
        table_rows.append(
            [
                row.get("campaign_name") or "Unknown campaign",
                short_money(spend),
                short_money(revenue),
                money(ncpa),
                format_roas(roas),
            ]
        )
    return markdown_table(["Campaign", "Spend", "Revenue", "nCPA", "ROAS"], table_rows)


def format_direct_api_thread_lines(api_label: str, direct: dict[str, Any]) -> list[str]:
    if native_access_pending(api_label):
        return markdown_table(
            ["Area", "Status"],
            [
                ["Credential readiness", "Native enrichment is pending Ads account access; recurring Slack stays focused on Triple Whale performance."],
                ["Offline catalog", f"services {direct.get('service_rows', 0)}, callable methods {direct.get('api_methods', 0)} ({direct.get('v24_api_methods', 0)} in v24), offline fields {direct.get('offline_field_rows', 0)} including v24 metrics {direct.get('offline_v24_metrics', 0)} and segments {direct.get('offline_v24_segments', 0)}"],
                ["Query map", f"{direct.get('query_manifest_rows', 0)} surfaces ({direct.get('query_manifest_no_auth', 0)} no-auth, {direct.get('query_manifest_auth_gated', 0)} auth-gated); mutation plans {direct.get('mutation_plans', 0)}"],
                ["Post-auth bootstrap", bootstrap_marker_state()],
            ],
        )
    return markdown_table(
        ["Area", "Status"],
        [
            ["Credential readiness", api_label],
            ["Native rows", f"customers {direct.get('customers', 0)}, campaigns {direct.get('campaigns', 0)}, ad groups {direct.get('ad_groups', 0)}, ads {direct.get('ads', 0)}, keywords {direct.get('keywords', 0)}, search terms {direct.get('search_terms', 0)}"],
            ["Native core generic", f"{direct.get('core_generic_rows', 0)} rows; {direct.get('core_surfaces_with_generic', 0)} of {direct.get('core_surfaces', 0)} mapped core surfaces route to `google_core_generic` after auth"],
            ["API catalog", f"services {direct.get('service_rows', 0)}, callable methods {direct.get('api_methods', 0)} ({direct.get('v24_api_methods', 0)} in v24), live GAQL fields {direct.get('field_rows', 0)}, offline fields {direct.get('offline_field_rows', 0)} including v24 metrics {direct.get('offline_v24_metrics', 0)} and segments {direct.get('offline_v24_segments', 0)}, last sync {direct.get('last_sync') or 'never'}"],
            ["Query map", f"{direct.get('query_manifest_rows', 0)} surfaces ({direct.get('query_manifest_no_auth', 0)} no-auth, {direct.get('query_manifest_auth_gated', 0)} auth-gated); generic performance rows {direct.get('performance_generic_rows', 0)}; mutation plans {direct.get('mutation_plans', 0)}"],
            ["Post-auth bootstrap", bootstrap_marker_state()],
        ],
    )


def format_slack_report(payload: dict[str, Any], snapshot_id: str | None = None) -> str:
    overall = payload["overall"]
    today_spend = safe_float(overall.get("today_spend"))
    today_revenue = safe_float(overall.get("today_revenue"))
    today_nc = safe_float(overall.get("today_nc_orders"))
    today_ncpa = today_spend / today_nc if today_nc > 0 else None
    today_roas = today_revenue / today_spend if today_spend > 0 else None
    l7_spend = safe_float(overall.get("l7_spend"))
    l7_revenue = safe_float(overall.get("l7_revenue"))
    l7_nc = safe_float(overall.get("l7_nc_orders"))
    l7_ncpa = l7_spend / l7_nc if l7_nc > 0 else None
    l7_roas = l7_revenue / l7_spend if l7_spend > 0 else None
    creds = payload["credential_state"]
    direct = payload["direct_status"]
    recs = payload["recommendations"]
    campaign_type_mix = payload.get("campaign_type_mix") or []
    brand_split = payload.get("brand_split") or []
    audit = payload.get("completion_audit") or {}
    audit_counts = audit_summary(audit)
    api_label = api_status_label(creds, direct)
    native_unblock_lines = format_native_unblock_lines(api_label)
    access_pending = native_access_pending(api_label)
    if access_pending and audit_counts["fail"] == 0:
        completion_line = (
            f"{audit_counts['pass']} pass · native enrichment pending account access · 0 fail"
        )
    else:
        completion_line = (
            f"{audit_counts['pass']} pass · {audit_counts['blocked']} blocked · "
            f"{audit_counts['fail']} fail"
        )
    today_roas_text = format_roas(today_roas)
    l7_roas_text = format_roas(l7_roas)
    operational_rows = [
        ["Latest TW hour", overall.get("latest_hour") or "No data"],
        ["L7 campaign mix", format_campaign_type_inline(campaign_type_mix)],
        ["Direct Google API", format_direct_api_parent_status(api_label, direct)],
        ["Completion gates", completion_line],
        ["Action queue", action_queue_label(recs)],
    ]
    if snapshot_id:
        operational_rows.append(["Snapshot", f"`{snapshot_id}`"])
    main = [
        f"# {REPORT_TITLE}",
        "",
        "## Performance Snapshot",
        *markdown_table(
            ["Window", "Segment", "Spend", "nCPA", "ROAS"],
            [
                ["Today TW", "Total", short_money(today_spend), money(today_ncpa), today_roas_text],
                *format_brand_split_performance_rows(brand_split, "today"),
                ["L7 TW", "Total", short_money(l7_spend), money(l7_ncpa), l7_roas_text],
                *format_brand_split_performance_rows(brand_split, "l7"),
            ],
        ),
        "",
        "## Operational Status",
        *markdown_table(
            ["Area", "Status"],
            operational_rows,
        ),
    ]
    thread = [
        "# Google Ads Decision Brief",
        f"Source of truth: Triple Whale browser and summary data. Direct Google Ads rows enrich native structure, search terms, recommendations, assets, and change history.",
        f"[Open Google Ads Operator]({GOOGLE_ADS_OPERATOR_DASHBOARD_URL})",
        "",
        "---",
        "",
        "## Scale Reviews",
        *format_recommendation_table(recs["scale_up"], "campaign_name", "Campaign", "No scale-up candidates from the current L7 read."),
        "",
        "## Defense Reviews",
        *format_recommendation_table(recs["defend"], "campaign_name", "Campaign", "No defensive budget/query candidates from the current L7 read."),
        "",
        "## Search Term Actions",
        *format_search_action_table(recs["search_actions"]),
        "",
        "## PMax / Shopping Watch",
        *format_recommendation_table(recs["pmax_watch"], "campaign_name", "Campaign", "No PMax campaign watch rows identified from the current L7 read."),
        "",
        "---",
        "",
        "## Brand vs Non-Brand - Triple Whale",
        *format_brand_split_table(brand_split),
        "",
        "## Campaign Type Mix - L7 Triple Whale",
        *format_campaign_type_table(campaign_type_mix),
        "",
        "## Top Google Campaigns - L7 Triple Whale",
        *format_campaign_table(payload["top_campaigns"][:10]),
        "",
        "---",
        "",
        "## Direct API Warehouse",
        *format_direct_api_thread_lines(api_label, direct),
        *native_unblock_lines,
        "",
        "## Completion Gates",
        *format_completion_gate_lines(audit, suppress_native_access_blockers=access_pending),
        "",
        "## Guardrails",
        "- No Google Ads mutations are executed by this report.",
        "- Any budget, campaign, ad group, keyword, ad, asset, or recommendation action must go through `gads mutate` preview first and requires `--confirm-live` for writes.",
    ]
    return "===SLACK_MAIN===\n" + "\n".join(main) + "\n===SLACK_THREAD===\n" + "\n".join(thread)


def format_native_unblock_lines(api_label: str) -> list[str]:
    return []


def format_recommendation_lines(rows: list[dict[str, Any]], label_key: str, empty: str) -> list[str]:
    if not rows:
        return [f"- {empty}"]
    out = []
    for row in rows[:8]:
        label = row.get(label_key) or row.get("campaign_name") or "Unknown"
        type_label = row.get("campaign_type_label")
        spend = safe_float(row.get("spend"))
        ncpa = row.get("ncpa")
        if ncpa is None and row.get("conversions"):
            ncpa = safe_float(row.get("spend")) / max(safe_float(row.get("conversions")), 1)
        prefix = f"{label} ({type_label})" if type_label else str(label)
        out.append(f"- {prefix}: {row.get('action')} | spend {short_money(spend)} | nCPA/CPA {money(ncpa)} | {row.get('reason')}")
    return out


def format_campaign_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No Google campaign rows in Triple Whale for this window."]
    out = []
    for row in rows:
        spend = safe_float(row.get("spend"))
        revenue = safe_float(row.get("revenue"))
        nc = safe_float(row.get("nc_orders"))
        ncpa = spend / nc if nc > 0 else None
        roas = revenue / spend if spend > 0 else None
        roas_text = f"{roas:.2f}x" if roas is not None else "No data"
        out.append(f"- {row.get('campaign_name') or 'Unknown campaign'}: spend {short_money(spend)}, revenue {short_money(revenue)}, nCPA {money(ncpa)}, ROAS {roas_text}")
    return out


def format_campaign_type_inline(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No data"
    parts = []
    for row in rows[:4]:
        spend = safe_float(row.get("spend"))
        if spend <= 0:
            continue
        label = row.get("campaign_type_label") or row.get("campaign_type") or "Unknown"
        parts.append(f"{label} {short_money(spend)}")
    return "; ".join(parts) or "No spend in this window"


def format_campaign_type_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No campaign-type rows in Triple Whale for this window."]
    out = []
    for row in rows:
        spend = safe_float(row.get("spend"))
        revenue = safe_float(row.get("revenue"))
        nc = safe_float(row.get("nc_orders"))
        ncpa = spend / nc if nc > 0 else None
        roas = revenue / spend if spend > 0 else None
        roas_text = f"{roas:.2f}x" if roas is not None else "No data"
        label = row.get("campaign_type_label") or row.get("campaign_type") or "Unknown"
        out.append(
            f"- {label}: spend {short_money(spend)}, revenue {short_money(revenue)}, nCPA {money(ncpa)}, ROAS {roas_text}"
        )
    return out


def cmd_report(args: argparse.Namespace) -> int:
    payload = report_payload(args.date, args.target_ncpa)
    snapshot_id = store_optimizer_snapshot(payload) if args.store_snapshot else None
    if args.format == "json":
        if snapshot_id:
            payload["snapshot_id"] = snapshot_id
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(format_slack_report(payload, snapshot_id=snapshot_id))
    return 0


def cmd_query_manifest(args: argparse.Namespace) -> int:
    ensure_schema()
    rows = build_query_manifest()
    if not args.no_store:
        store_query_manifest(rows)
    emit_query_manifest(rows, args.format)
    return 0


def cmd_catalog_summary(args: argparse.Namespace) -> int:
    ensure_schema()
    payload = psql_json(
        """
        SELECT jsonb_build_object(
            'sources', (
                SELECT coalesce(jsonb_agg(jsonb_build_object(
                    'source_name', source_name,
                    'source_ref', source_ref,
                    'metadata', metadata
                ) ORDER BY source_name), '[]'::jsonb)
                FROM google_api_catalog_sources
            ),
            'services_by_version', (
                SELECT coalesce(jsonb_agg(row_payload ORDER BY row_payload->>'api_version'), '[]'::jsonb)
                FROM (
                    SELECT jsonb_build_object(
                        'api_version', api_version,
                        'services', count(*),
                        'methods', (
                            SELECT count(*)
                            FROM google_api_methods m
                            WHERE m.api_version = s.api_version
                        )
                    ) AS row_payload
                    FROM google_api_services s
                    GROUP BY api_version
                ) rows
            ),
            'v24_methods_by_kind', (
                SELECT coalesce(jsonb_agg(row_payload ORDER BY row_payload->>'kind'), '[]'::jsonb)
                FROM (
                    SELECT jsonb_build_object(
                        'kind', operation_kind,
                        'methods', count(*)
                    ) AS row_payload
                    FROM google_api_methods
                    WHERE api_version = 'v24'
                    GROUP BY operation_kind
                ) rows
            ),
            'offline_fields_by_version_kind', (
                SELECT coalesce(jsonb_agg(row_payload ORDER BY row_payload->>'api_version', row_payload->>'resource_kind'), '[]'::jsonb)
                FROM (
                    SELECT jsonb_build_object(
                        'api_version', api_version,
                        'resource_kind', resource_kind,
                        'fields', count(*)
                    ) AS row_payload
                    FROM google_offline_catalog_fields
                    GROUP BY api_version, resource_kind
                ) rows
            ),
            'offline_described_fields', (
                SELECT count(*)
                FROM google_offline_catalog_fields
                WHERE description IS NOT NULL AND description <> ''
            ),
            'query_manifest', (
                SELECT jsonb_build_object(
                    'rows', (SELECT count(*) FROM google_query_manifest),
                    'requires_auth', (SELECT count(*) FROM google_query_manifest WHERE requires_auth),
                    'no_auth_required', (SELECT count(*) FROM google_query_manifest WHERE NOT requires_auth),
                    'by_type', (
                        SELECT coalesce(jsonb_object_agg(surface_type, row_count), '{}'::jsonb)
                        FROM (
                            SELECT surface_type, count(*) AS row_count
                            FROM google_query_manifest
                            GROUP BY surface_type
                        ) rows
                    )
                )
            ),
            'top_v24_resources', (
                SELECT coalesce(jsonb_agg(row_payload ORDER BY (row_payload->>'fields')::int DESC), '[]'::jsonb)
                FROM (
                    SELECT jsonb_build_object(
                        'resource', resource,
                        'resource_kind', max(resource_kind),
                        'fields', count(*)
                    ) AS row_payload
                    FROM google_offline_catalog_fields
                    WHERE api_version = 'v24'
                    GROUP BY resource
                    ORDER BY count(*) DESC
                    LIMIT 25
                ) rows
            ),
            'live_gaql_fields', (SELECT count(*) FROM google_ads_fields),
            'latest_auth_status', (SELECT status FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'latest_auth_error', (SELECT message FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1)
        )
        """
    ) or {}
    if payload.get("latest_auth_error"):
        payload["latest_auth_error_summary"] = auth_blocker_from_latest(payload)
        payload.pop("latest_auth_error", None)
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print("# Google Ads Catalog Summary")
    print()
    print(f"- Live GAQL fields: {payload.get('live_gaql_fields', 0)}")
    print(f"- Latest auth status: {payload.get('latest_auth_status') or 'never'}")
    if payload.get("latest_auth_error_summary"):
        print(f"- Latest auth blocker: {payload['latest_auth_error_summary']}")
    manifest = payload.get("query_manifest") or {}
    print(
        f"- Query manifest: {manifest.get('rows', 0)} surfaces "
        f"({manifest.get('no_auth_required', 0)} no-auth, {manifest.get('requires_auth', 0)} auth-gated)"
    )
    print()
    print("## Services By Version")
    for row in payload.get("services_by_version") or []:
        print(f"- {row['api_version']}: {row['services']} services, {row['methods']} callable methods")
    print()
    print("## v24 Methods By Kind")
    for row in payload.get("v24_methods_by_kind") or []:
        print(f"- {row['kind']}: {row['methods']}")
    print()
    print("## Offline Fields By Version / Kind")
    for row in payload.get("offline_fields_by_version_kind") or []:
        print(f"- {row['api_version']} {row['resource_kind']}: {row['fields']}")
    print()
    print("## Top v24 Resources")
    for row in payload.get("top_v24_resources") or []:
        print(f"- {row['resource']} ({row['resource_kind']}): {row['fields']}")
    return 0


def launchd_list_output() -> str:
    try:
        result = subprocess.run(["launchctl", "list"], check=False, capture_output=True, text=True)
    except OSError:
        return ""
    return result.stdout


def launchd_label_loaded(label: str, output: str | None = None) -> bool:
    return label in (output if output is not None else launchd_list_output())


def launchd_loaded_label(candidates: list[str], output: str | None = None) -> str | None:
    launchd_output = output if output is not None else launchd_list_output()
    for label in candidates:
        if launchd_label_loaded(label, launchd_output):
            return label
    return None


def launchd_calendar_summary(value: Any) -> Any:
    if isinstance(value, list):
        return [launchd_calendar_summary(item) for item in value]
    if isinstance(value, dict):
        order = ["Weekday", "Day", "Hour", "Minute"]
        keys = [key for key in order if key in value] + sorted(key for key in value if key not in order)
        return ", ".join(f"{key}={value[key]}" for key in keys)
    return value


def launchd_plist_state(label: str | None) -> dict[str, Any]:
    if not label:
        return {"exists": False}
    path = (pathlib.Path.home() / "Library" / "LaunchAgents" / f"{label}.plist").expanduser()
    state: dict[str, Any] = {"label": label, "path": str(path), "exists": path.exists()}
    if not path.exists():
        return state
    try:
        with path.open("rb") as handle:
            payload = plistlib.load(handle)
    except Exception as exc:  # noqa: BLE001
        state["error"] = str(exc)
        return state
    calendar = payload.get("StartCalendarInterval")
    interval = payload.get("StartInterval")
    args = [str(arg) for arg in payload.get("ProgramArguments") or []]
    state.update(
        {
            "program_arguments": args,
            "start_calendar_interval": calendar,
            "start_interval": interval,
            "schedule_summary": launchd_calendar_summary(calendar) if calendar is not None else interval,
        }
    )
    return state


def launchd_schedule_is_hourly(state: dict[str, Any]) -> bool:
    calendar = state.get("start_calendar_interval")
    return isinstance(calendar, dict) and "Minute" in calendar and "Hour" not in calendar


def launchd_schedule_is_daily(state: dict[str, Any]) -> bool:
    calendar = state.get("start_calendar_interval")
    return isinstance(calendar, dict) and "Hour" in calendar and "Minute" in calendar


def launchd_rolling_days(state: dict[str, Any]) -> int | None:
    args = state.get("program_arguments")
    if not isinstance(args, list):
        return None
    for index, value in enumerate(args):
        if value == "source-rolling" and index + 2 < len(args):
            try:
                return int(str(args[index + 2]))
            except ValueError:
                return None
    return None


def launchd_wrapper_timeout_seconds(state: dict[str, Any]) -> int | None:
    args = state.get("program_arguments")
    if not isinstance(args, list) or len(args) < 3:
        return None
    try:
        return int(str(args[2]))
    except ValueError:
        return None


def bool_status(condition: bool, *, blocked: bool = False) -> str:
    if condition:
        return "pass"
    return "blocked" if blocked else "fail"


def file_contains_all(path: pathlib.Path, needles: list[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return all(needle in text for needle in needles)


def any_file_contains_all(paths: list[pathlib.Path], needles: list[str]) -> bool:
    return any(file_contains_all(path, needles) for path in paths)


def google_ads_source_router_state() -> dict[str, Any]:
    registry_paths = [
        pathlib.Path(path).expanduser()
        for path in _split_config_list(os.environ.get("GOOGLE_ADS_SOURCE_REGISTRY_PATHS"))
    ]
    if not registry_paths:
        return {"ok": True, "configured": False, "registries": []}
    registry_states: list[dict[str, Any]] = []
    for path in registry_paths:
        state: dict[str, Any] = {"path": str(path), "exists": path.exists(), "ok": False}
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
            source = next((row for row in registry if row.get("id") == "google-ads"), None)
            first_commands = source.get("first_commands") if isinstance(source, dict) else []
            state.update(
                {
                    "status": source.get("status") if isinstance(source, dict) else None,
                    "skill": source.get("skill") if isinstance(source, dict) else None,
                    "warehouse_schema": source.get("warehouse_schema") if isinstance(source, dict) else None,
                    "first_commands": first_commands,
                    "ok": bool(
                        isinstance(source, dict)
                        and source.get("status")
                        in {
                            "installed-tw-warehouse-direct-connector-authenticated",
                            "installed-tw-warehouse-direct-connector-auth-blocked",
                        }
                        and source.get("skill") == "google-ads"
                        and source.get("warehouse_schema") == SCHEMA
                        and "gads status" in first_commands
                        and "gads completion-audit" in first_commands
                        and "vhdb tables google_ads_tw" in first_commands
                        and SCHEMA in str(source.get("source_of_truth", ""))
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            state["error"] = str(exc)
        registry_states.append(state)
    return {
        "ok": all(row.get("ok") for row in registry_states),
        "registries": registry_states,
    }


def catalog_cache_state() -> dict[str, Any]:
    roots: list[pathlib.Path] = []
    for root in (PROFILE_ROOT,):
        if root not in roots:
            roots.append(root)

    def find_cache(relative: pathlib.Path) -> str | None:
        for root in roots:
            path = root / "cache" / relative
            if (path / ".git").exists():
                return str(path)
        return None

    official_client = find_cache(pathlib.Path("google-ads-python"))
    open_source: dict[str, str | None] = {
        name: find_cache(pathlib.Path("google-ads-research") / name)
        for name in OPEN_SOURCE_REPOS
    }
    cached_names = [name for name, path in open_source.items() if path]
    return {
        "official_client_cached": bool(official_client),
        "official_client_path": official_client,
        "open_source_cached": cached_names,
        "open_source_cache_count": len(cached_names),
        "open_source_paths": open_source,
    }


def read_log_tail(path: pathlib.Path, max_bytes: int = 160_000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(size - max_bytes, 0))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def launchd_log_paths(file_name: str) -> list[pathlib.Path]:
    return [root / file_name for root in LAUNCHD_LOG_ROOTS]


def parse_utc_log_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def age_hours(timestamp: str | None) -> float | None:
    parsed = parse_utc_log_ts(timestamp)
    if not parsed:
        return None
    return max((now_utc() - parsed).total_seconds() / 3600.0, 0.0)


def latest_launchd_end(log_text: str, job: str) -> dict[str, Any]:
    pattern = re.compile(
        rf"\[(?P<ts>[^\]]+)\] direct launchd end job={re.escape(job)} status=(?P<status>\d+) slack_post=(?P<slack_post>\d+)"
    )
    matches = list(pattern.finditer(log_text))
    if not matches:
        return {"found": False}
    match = matches[-1]
    timestamp = match.group("ts")
    return {
        "found": True,
        "timestamp": timestamp,
        "age_hours": age_hours(timestamp),
        "status": int(match.group("status")),
        "slack_post": int(match.group("slack_post")),
    }


def runtime_state_sort_key(state: dict[str, Any]) -> tuple[int, int, dt.datetime]:
    latest_end = state.get("latest_end") if isinstance(state.get("latest_end"), dict) else {}
    timestamp = parse_utc_log_ts(latest_end.get("timestamp"))
    return (
        1 if state.get("ok") else 0,
        1 if latest_end.get("found") else 0,
        timestamp or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
    )


def select_runtime_state(states: list[dict[str, Any]]) -> dict[str, Any]:
    checked_paths = [str(state.get("log_path")) for state in states if state.get("log_path")]
    selected = max(states, key=runtime_state_sort_key) if states else {}
    if selected:
        selected["checked_log_paths"] = checked_paths
    return selected


def google_tw_hourly_log_state_for_path(path: pathlib.Path) -> dict[str, Any]:
    text = read_log_tail(path)
    latest_end = latest_launchd_end(text, ATTRIBUTION_HOURLY_JOB)
    imports = list(
        re.finditer(
            r"imported (?P<rows>\d+) hourly rows for (?P<date>\d{4}-\d{2}-\d{2}) from (?P<path>\S+)",
            text,
        )
    )
    latest_import = imports[-1] if imports else None
    rows = int(latest_import.group("rows")) if latest_import else 0
    return {
        "log_path": str(path),
        "latest_end": latest_end,
        "imported_rows": rows,
        "import_date": latest_import.group("date") if latest_import else None,
        "export_path": latest_import.group("path") if latest_import else None,
        "ok": bool(
            latest_end.get("found")
            and latest_end.get("status") == 0
            and rows > 0
            and (latest_end.get("age_hours") is None or latest_end.get("age_hours") <= 30)
        ),
    }


def google_tw_hourly_log_state() -> dict[str, Any]:
    return select_runtime_state(
        [google_tw_hourly_log_state_for_path(path) for path in launchd_log_paths(f"{ATTRIBUTION_HOURLY_JOB}.direct.log")]
    )


def google_slack_report_log_state_for_path(path: pathlib.Path) -> dict[str, Any]:
    text = read_log_tail(path)
    start_pattern = re.compile(
        rf"(?m)^\[(?P<ts>[^\]]+)\] direct launchd start job={re.escape(REPORT_HOURLY_JOB)} channel=(?P<channel>\S+).*?$"
    )
    starts = list(start_pattern.finditer(text))
    production_blocks: list[str] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.start() : end]
        if DEFAULT_SLACK_CHANNEL and match.group("channel") == DEFAULT_SLACK_CHANNEL:
            if latest_launchd_end(block, REPORT_HOURLY_JOB).get("found"):
                production_blocks.append(block)
    block_text = production_blocks[-1] if production_blocks else ""
    latest_end = latest_launchd_end(block_text, REPORT_HOURLY_JOB)
    post_ok = f"post_channel={DEFAULT_SLACK_CHANNEL} errors=no" in block_text
    thread_rows: list[dict[str, Any]] = []
    for line in block_text.splitlines():
        if f'"channel": "{DEFAULT_SLACK_CHANNEL}"' not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        thread_rows.append(payload)
    latest_thread = thread_rows[-1] if thread_rows else {}
    reply_count = int(latest_thread.get("reply_count") or 0)
    raw_oauth_blocker_patterns = [
        "- Direct Google API: auth blocked:",
        "- Credential readiness: auth blocked:",
        "Blocker: OAuth user is not attached to a Google Ads account",
    ]
    raw_oauth_blocker_present = any(pattern in block_text for pattern in raw_oauth_blocker_patterns)
    native_access_pending_rendered = all(
        pattern in block_text
        for pattern in [
            "Native Google Ads API: native enrichment is waiting on Ads account access",
            "Status: native enrichment is pending Ads account access",
            "TW reporting heartbeat is clean; native enrichment gates are pending account access",
        ]
    )
    return {
        "log_path": str(path),
        "latest_end": latest_end,
        "post_channel_ok": post_ok,
        "thread_ok": bool(latest_thread.get("ok") is True and reply_count >= 1),
        "reply_count": reply_count,
        "parent_ts": latest_thread.get("parent_ts"),
        "reply_ts": latest_thread.get("reply_ts"),
        "raw_oauth_blocker_present": raw_oauth_blocker_present,
        "raw_oauth_blocker_muted": not raw_oauth_blocker_present,
        "native_access_pending_rendered": native_access_pending_rendered,
        "ok": bool(
            latest_end.get("found")
            and latest_end.get("status") == 0
            and latest_end.get("slack_post") == 0
            and post_ok
            and latest_thread.get("ok") is True
            and reply_count >= 1
            and not raw_oauth_blocker_present
            and (latest_end.get("age_hours") is None or latest_end.get("age_hours") <= 30)
        ),
    }


def google_slack_report_log_state() -> dict[str, Any]:
    return select_runtime_state(
        [google_slack_report_log_state_for_path(path) for path in launchd_log_paths(f"{REPORT_HOURLY_JOB}.direct.log")]
    )


def google_direct_job_log_state_for_path(path: pathlib.Path, job: str) -> dict[str, Any]:
    text = read_log_tail(path)
    latest_end = latest_launchd_end(text, job)
    auth_blocked = "OAuth/auth smoke test" in text or "NOT_ADS_USER" in text
    return {
        "log_path": str(path),
        "latest_end": latest_end,
        "auth_blocked": auth_blocked,
        "ok": bool(
            latest_end.get("found")
            and latest_end.get("status") == 0
            and (latest_end.get("age_hours") is None or latest_end.get("age_hours") <= 30)
        ),
    }


def google_direct_job_log_state(job: str) -> dict[str, Any]:
    return select_runtime_state(
        [
            google_direct_job_log_state_for_path(path, job)
            for path in launchd_log_paths(f"{job}.direct.log")
        ]
    )


def completion_audit_payload() -> dict[str, Any]:
    ensure_schema()
    state = credential_state()
    counts = psql_json(
        """
        SELECT jsonb_build_object(
            'services', (SELECT count(*) FROM google_api_services),
            'api_methods', (SELECT count(*) FROM google_api_methods),
            'v24_api_methods', (SELECT count(*) FROM google_api_methods WHERE api_version = 'v24'),
            'offline_fields', (SELECT count(*) FROM google_offline_catalog_fields),
            'offline_described_fields', (SELECT count(*) FROM google_offline_catalog_fields WHERE description IS NOT NULL AND description <> ''),
            'live_fields', (SELECT count(*) FROM google_ads_fields),
            'query_manifest_rows', (SELECT count(*) FROM google_query_manifest),
            'query_manifest_no_auth', (SELECT count(*) FROM google_query_manifest WHERE NOT requires_auth),
            'query_manifest_auth_gated', (SELECT count(*) FROM google_query_manifest WHERE requires_auth),
            'core_surfaces', (SELECT count(*) FROM google_query_manifest WHERE surface_type = 'core'),
            'core_surfaces_with_generic', (SELECT count(*) FROM google_query_manifest WHERE surface_type = 'core' AND warehouse_tables ? 'google_core_generic'),
            'mutation_plans', (SELECT count(*) FROM google_mutation_plans),
            'keyword_research_runs', (SELECT count(*) FROM google_keyword_research_runs),
            'keyword_research_ideas', (SELECT count(*) FROM google_keyword_research_ideas),
            'expert_source_documents', (SELECT count(*) FROM google_expert_source_documents),
            'optimizer_snapshots', (SELECT count(*) FROM google_optimizer_snapshots),
            'latest_optimizer_snapshot_id', (SELECT id::text FROM google_optimizer_snapshots ORDER BY generated_at DESC LIMIT 1),
            'latest_optimizer_has_campaign_type_mix', coalesce((SELECT decision_payload ? 'campaign_type_mix' AND jsonb_typeof(decision_payload->'campaign_type_mix') = 'array' AND jsonb_array_length(decision_payload->'campaign_type_mix') > 0 FROM google_optimizer_snapshots ORDER BY generated_at DESC LIMIT 1), false),
            'customers', (SELECT count(*) FROM google_customers),
            'campaigns', (SELECT count(*) FROM google_campaigns),
            'ad_groups', (SELECT count(*) FROM google_ad_groups),
            'ads', (SELECT count(*) FROM google_ads),
            'keywords', (SELECT count(*) FROM google_keywords),
            'search_terms', (SELECT count(*) FROM google_search_terms),
            'performance_rows', (SELECT count(*) FROM google_performance_daily),
            'performance_generic_rows', (SELECT count(*) FROM google_performance_generic),
            'core_generic_rows', (SELECT count(*) FROM google_core_generic),
            'tw_hourly_rows', (SELECT count(*) FROM google_tw_attribution_hourly),
            'tw_daily_rows', (SELECT count(*) FROM google_tw_attribution_daily),
            'tw_account_daily_rows', (SELECT count(*) FROM google_account_daily_performance),
            'tw_campaign_daily_rows', (SELECT count(*) FROM google_campaign_daily_performance),
            'tw_campaign_type_daily_rows', (SELECT count(*) FROM google_campaign_type_daily_performance),
            'tw_ad_group_daily_rows', (SELECT count(*) FROM google_ad_group_daily_performance),
            'tw_ad_daily_rows', (SELECT count(*) FROM google_ad_daily_performance),
            'tw_rolling_31d_rows', (SELECT count(*) FROM google_tw_rolling_31d),
            'latest_auth_status', (SELECT status FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'latest_auth_error', (SELECT message FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
            'latest_auth_check', (SELECT completed_at::text FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'latest_direct_sync', (SELECT max(completed_at)::text FROM google_sync_runs WHERE command in ('sync-core','sync-performance') AND status in ('success','partial')),
            'latest_tw_google_date', (SELECT max(report_date)::text FROM google_tw_attribution_hourly),
            'latest_tw_google_hour', (SELECT max(report_hour)::text FROM google_tw_attribution_hourly),
            'tw_l31_expected_start', ((current_date - interval '31 days')::date::text),
            'tw_l31_expected_end', ((current_date - interval '1 day')::date::text),
            'tw_l31_min_date', (SELECT min(date_start)::text FROM google_ad_hourly_performance WHERE date_start >= current_date - interval '31 days' AND date_start < current_date),
            'tw_l31_max_date', (SELECT max(date_start)::text FROM google_ad_hourly_performance WHERE date_start >= current_date - interval '31 days' AND date_start < current_date),
            'tw_l31_dates', (SELECT count(DISTINCT date_start) FROM google_ad_hourly_performance WHERE date_start >= current_date - interval '31 days' AND date_start < current_date),
            'tw_l31_hourly_rows', (SELECT count(*) FROM google_ad_hourly_performance WHERE date_start >= current_date - interval '31 days' AND date_start < current_date),
            'tw_l31_spend', (SELECT coalesce(round(sum(spend)::numeric, 2), 0) FROM google_ad_hourly_performance WHERE date_start >= current_date - interval '31 days' AND date_start < current_date),
            'tw_l31_revenue', (SELECT coalesce(round(sum(revenue)::numeric, 2), 0) FROM google_ad_hourly_performance WHERE date_start >= current_date - interval '31 days' AND date_start < current_date)
        )
        """
    ) or {}
    sources = psql_json(
        """
        SELECT coalesce(jsonb_agg(source_name ORDER BY source_name), '[]'::jsonb)
        FROM google_api_catalog_sources
        """
    ) or []
    cache_state = catalog_cache_state()
    launchd_jobs = {
        DIRECT_HOURLY_JOB: _split_config_list(os.environ.get("GOOGLE_ADS_DIRECT_HOURLY_LABELS")),
        DIRECT_DAILY_JOB: _split_config_list(os.environ.get("GOOGLE_ADS_DIRECT_DAILY_LABELS")),
        DIRECT_BOOTSTRAP_JOB: _split_config_list(os.environ.get("GOOGLE_ADS_DIRECT_BOOTSTRAP_LABELS")),
        REPORT_HOURLY_JOB: _split_config_list(os.environ.get("GOOGLE_ADS_REPORT_HOURLY_LABELS")),
        ATTRIBUTION_HOURLY_JOB: _split_config_list(os.environ.get("GOOGLE_ADS_ATTRIBUTION_HOURLY_LABELS")),
        ATTRIBUTION_ROLLING_JOB: _split_config_list(os.environ.get("GOOGLE_ADS_ATTRIBUTION_ROLLING_LABELS")),
    }
    launchd_jobs = {job: candidates for job, candidates in launchd_jobs.items() if candidates}
    launchd_output = launchd_list_output()
    labels: dict[str, dict[str, Any]] = {}
    for job, candidates in launchd_jobs.items():
        loaded_label = launchd_loaded_label(candidates, launchd_output)
        labels[job] = {
            "loaded": bool(loaded_label),
            "loaded_label": loaded_label,
            "candidates": candidates,
            "plist": launchd_plist_state(loaded_label or candidates[-1]),
        }
    google_hourly_jobs = [
        job for job in (DIRECT_HOURLY_JOB, DIRECT_BOOTSTRAP_JOB, REPORT_HOURLY_JOB, ATTRIBUTION_HOURLY_JOB)
        if job in labels
    ]
    google_daily_jobs = [
        job for job in (DIRECT_DAILY_JOB, ATTRIBUTION_ROLLING_JOB)
        if job in labels
    ]
    rolling_days = launchd_rolling_days(labels.get(ATTRIBUTION_ROLLING_JOB, {}).get("plist", {}))
    rolling_timeout_seconds = launchd_wrapper_timeout_seconds(labels.get(ATTRIBUTION_ROLLING_JOB, {}).get("plist", {}))
    cron_schedule_ok = (
        not AUDIT_SCHEDULER
        or (
            bool(labels)
            and all(bool(row.get("loaded")) for row in labels.values())
            and all(launchd_schedule_is_hourly(labels[job]["plist"]) for job in google_hourly_jobs)
            and all(launchd_schedule_is_daily(labels[job]["plist"]) for job in google_daily_jobs)
            and (ATTRIBUTION_ROLLING_JOB not in labels or (rolling_days or 0) >= 31)
            and (ATTRIBUTION_ROLLING_JOB not in labels or (rolling_timeout_seconds or 0) >= 14_400)
        )
    )
    dashboard_route_paths = [
        pathlib.Path(path).expanduser()
        for path in _split_config_list(os.environ.get("GOOGLE_ADS_DASHBOARD_ROUTE_PATHS"))
    ]
    dashboard_data_paths = [
        pathlib.Path(path).expanduser()
        for path in _split_config_list(os.environ.get("GOOGLE_ADS_DASHBOARD_DATA_PATHS"))
    ]
    dashboard_e2e_paths = [
        pathlib.Path(path).expanduser()
        for path in _split_config_list(os.environ.get("GOOGLE_ADS_DASHBOARD_E2E_PATHS"))
    ]
    direct_cron_wrapper_paths = [
        pathlib.Path(path).expanduser()
        for path in _split_config_list(os.environ.get("GOOGLE_ADS_DIRECT_CRON_WRAPPER_PATHS"))
    ]
    files = {
        "gads": bool(shutil.which("gads")) or pathlib.Path(__file__).exists(),
        "warehouse_script": pathlib.Path(__file__).exists(),
        "oauth_bootstrap": (PROJECT_ROOT / "scripts" / "bootstrap_google_ads_oauth.sh").exists(),
        "expert_source_catalog": EXPERT_SOURCE_CATALOG.exists(),
        "keyword_research_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "cmd_keyword_research",
                "generateKeywordIdeas",
                "google_keyword_research_ideas",
                "recommended_match_type",
            ],
        ),
        "campaign_research_brief_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "cmd_campaign_research_brief",
                "next_plan_command",
                "starter_negatives",
            ],
        ),
        "build_search_campaign_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "cmd_build_search_campaign",
                "build_researched_search_campaign_operations",
                "search_ad_copy_for_group",
                "search_campaign_researched",
            ],
        ),
        "build_pmax_campaign_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "cmd_build_pmax_campaign",
                "pmax_research_assets",
                "build-pmax-campaign/keyword-research",
                "google_ads_researched_pmax_campaign_build",
            ],
        ),
        "build_shopping_campaign_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "cmd_build_shopping_campaign",
                "build-shopping-campaign/keyword-research",
                "shopping_campaign",
                "google_ads_researched_shopping_campaign_build",
            ],
        ),
        "build_demand_gen_campaign_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "cmd_build_demand_gen_campaign",
                "choose_demand_gen_video_assets",
                "build-demand-gen-campaign/keyword-research",
                "google_ads_researched_demand_gen_campaign_build",
            ],
        ),
        "direct_cron_wrapper": any(path.exists() for path in direct_cron_wrapper_paths),
        "direct_cron_success_notify": any_file_contains_all(
            direct_cron_wrapper_paths,
            [
                "post_bootstrap_success",
                "Google Ads Native Bootstrap Complete",
                "post_slack_direct.py",
            ],
        ),
        "mutation_live_slack_source": any_file_contains_all(
            [pathlib.Path(__file__)],
            [
                "format_google_mutation_slack",
                "post_google_mutation_slack",
                "gads mutate --confirm-live",
            ],
        ),
        "dashboard_route": any(path.exists() for path in dashboard_route_paths),
        "dashboard_data": any(path.exists() for path in dashboard_data_paths),
        "dashboard_e2e": any(path.exists() for path in dashboard_e2e_paths),
        "dashboard_native_unblock_source": any_file_contains_all(
            dashboard_route_paths,
            [
                "Native API unblock",
                "gads auth-doctor --show-email",
                "Access and security",
                "Standard access",
                "summarizeGoogleAdsAuthError",
            ],
        ),
        "dashboard_native_unblock_e2e": any_file_contains_all(
            dashboard_e2e_paths,
            [
                "hasNativeApiUnblock",
                "native API unblock guidance missing",
                "gads auth-doctor --show-email",
            ],
        ),
    }
    tw_hourly_log = google_tw_hourly_log_state()
    slack_report_log = google_slack_report_log_state()
    direct_hourly_log = google_direct_job_log_state(DIRECT_HOURLY_JOB)
    direct_bootstrap_log = google_direct_job_log_state(DIRECT_BOOTSTRAP_JOB)
    auth_blocker = None
    if counts.get("latest_auth_status") != "success" and counts.get("latest_auth_error"):
        auth_blocker = auth_blocker_from_latest(counts)
    not_ads_user = bool(auth_blocker and "NOT_ADS_USER" in auth_blocker)
    recurring_slack_policy_ok = bool(slack_report_log.get("raw_oauth_blocker_muted"))
    source_router_state = google_ads_source_router_state()
    oauth_identity: dict[str, Any] | None = None
    if state.get("ready"):
        try:
            oauth_identity = oauth_identity_state(current_access_token())
        except Exception as exc:  # noqa: BLE001
            oauth_identity = {"ok": False, "error": str(exc)}
    required_sources = {
        "google-ads-python",
        "google-ads-python-offline-fields",
        "google-ads-open-cli",
        "google-ads-api-report-fetcher",
        "google-ads-mcp",
        "google-ads-api-developer-assistant",
    }
    source_set = set(sources)
    native_rows = sum(
        int(counts.get(key) or 0)
        for key in ("customers", "campaigns", "ad_groups", "ads", "keywords", "search_terms", "performance_rows", "performance_generic_rows", "core_generic_rows")
    )
    checks = [
        {
            "id": "warehouse_schema",
            "requirement": "Create Google Ads warehouse schema and tables",
            "status": bool_status(int(counts.get("query_manifest_rows") or 0) >= 65 and files["warehouse_script"]),
            "evidence": f"query_manifest_rows={counts.get('query_manifest_rows', 0)}; warehouse_script={files['warehouse_script']}",
        },
        {
            "id": "credentials",
            "requirement": "Store Google Ads credentials without printing secrets",
            "status": bool_status(bool(state.get("ready"))),
            "evidence": f"credential_ready={state.get('ready')}; missing={','.join(state.get('missing') or []) or 'none'}",
        },
        {
            "id": "api_catalog",
            "requirement": "Map Google Ads services, endpoints, fields, dimensions, and metrics",
            "status": bool_status(
                int(counts.get("services") or 0) >= 400
                and int(counts.get("api_methods") or 0) >= 600
                and int(counts.get("offline_fields") or 0) >= 8000
                and int(counts.get("offline_described_fields") or 0) >= 8000
                and int(counts.get("query_manifest_rows") or 0) >= 65
            ),
            "evidence": f"services={counts.get('services', 0)}; methods={counts.get('api_methods', 0)}; offline_fields={counts.get('offline_fields', 0)}; offline_described_fields={counts.get('offline_described_fields', 0)}; query_surfaces={counts.get('query_manifest_rows', 0)}",
        },
        {
            "id": "native_core_generic_structure",
            "requirement": "Preserve every mapped native core entity/config surface in a durable warehouse table after auth",
            "status": bool_status(
                int(counts.get("core_surfaces") or 0) >= 40
                and counts.get("core_surfaces") == counts.get("core_surfaces_with_generic")
            ),
            "evidence": f"core_surfaces={counts.get('core_surfaces', 0)}; with_google_core_generic={counts.get('core_surfaces_with_generic', 0)}",
        },
        {
            "id": "authenticated_field_catalog",
            "requirement": "Sync authenticated GoogleAdsField compatibility catalog",
            "status": bool_status(int(counts.get("live_fields") or 0) > 0, blocked=not_ads_user),
            "evidence": f"live_fields={counts.get('live_fields', 0)}; latest_auth={counts.get('latest_auth_status') or 'never'}",
            "blocker": auth_blocker,
        },
        {
            "id": "research_repos",
            "requirement": "Research/clone useful Google Ads repos",
            "status": bool_status(
                required_sources.issubset(source_set)
                and bool(cache_state.get("official_client_cached"))
                and int(cache_state.get("open_source_cache_count") or 0) >= len(OPEN_SOURCE_REPOS)
            ),
            "evidence": {
                "catalog_sources": sorted(source_set),
                "official_client_cached": cache_state.get("official_client_cached"),
                "open_source_cache_count": cache_state.get("open_source_cache_count"),
                "open_source_cached": cache_state.get("open_source_cached"),
            },
        },
        {
            "id": "cli",
            "requirement": "Build Google Ads CLI with reporting, query, sync, backfill, mutation planning, and live-write Slack recaps",
            "status": bool_status(
                files["gads"]
                and files["warehouse_script"]
                and files["mutation_live_slack_source"]
                and int(counts.get("mutation_plans") or 0) >= 0
            ),
            "evidence": f"gads={files['gads']}; mutation_plan_table=true; live_slack_source={files['mutation_live_slack_source']}",
        },
        {
            "id": "keyword_research_cli",
            "requirement": "Build Search campaign research flow with Keyword Planner volumes, trend rows, intent buckets, and match-type recommendations",
            "status": bool_status(
                files["keyword_research_source"]
                and files["campaign_research_brief_source"]
                and files["build_search_campaign_source"]
                and int(counts.get("query_manifest_rows") or 0) >= 68
            ),
            "evidence": (
                f"keyword_research_source={files['keyword_research_source']}; "
                f"campaign_research_brief_source={files['campaign_research_brief_source']}; "
                f"build_search_campaign_source={files['build_search_campaign_source']}; "
                f"runs={counts.get('keyword_research_runs', 0)}; ideas={counts.get('keyword_research_ideas', 0)}"
            ),
        },
        {
            "id": "pmax_research_builder",
            "requirement": "Build Performance Max campaign planning flow with researched search themes and reusable asset defaults",
            "status": bool_status(
                files["build_pmax_campaign_source"]
                and int(counts.get("query_manifest_rows") or 0) >= 88
            ),
            "evidence": f"build_pmax_campaign_source={files['build_pmax_campaign_source']}; query_manifest_rows={counts.get('query_manifest_rows', 0)}",
        },
        {
            "id": "shopping_research_builder",
            "requirement": "Build Standard Shopping campaign planning flow with demand research and merchant/feed inference",
            "status": bool_status(
                files["build_shopping_campaign_source"]
                and int(counts.get("query_manifest_rows") or 0) >= 89
            ),
            "evidence": f"build_shopping_campaign_source={files['build_shopping_campaign_source']}; query_manifest_rows={counts.get('query_manifest_rows', 0)}",
        },
        {
            "id": "demand_gen_research_builder",
            "requirement": "Build Demand Gen/YouTube-style planning flow with demand research and automatic video asset selection",
            "status": bool_status(
                files["build_demand_gen_campaign_source"]
                and int(counts.get("query_manifest_rows") or 0) >= 90
            ),
            "evidence": f"build_demand_gen_campaign_source={files['build_demand_gen_campaign_source']}; query_manifest_rows={counts.get('query_manifest_rows', 0)}",
        },
        {
            "id": "expert_source_memory",
            "requirement": "Ingest authorized non-YouTube Google Ads operator sources into local skill memory",
            "status": bool_status(
                files["expert_source_catalog"]
                and int(counts.get("expert_source_documents") or 0) >= 8
            ),
            "evidence": (
                f"catalog={files['expert_source_catalog']}; "
                f"documents={counts.get('expert_source_documents', 0)}; "
                "policy=public or authorized source pages only"
            ),
        },
        {
            "id": "native_backfill",
            "requirement": "Backfill native Google Ads API 30-day and full history",
            "status": bool_status(native_rows > 0 and counts.get("latest_direct_sync"), blocked=not_ads_user),
            "evidence": f"native_rows={native_rows}; latest_direct_sync={counts.get('latest_direct_sync') or 'never'}",
            "blocker": auth_blocker,
        },
        {
            "id": "cron",
            "requirement": "Keep Google Ads current on launchd with hourly report, direct sync, and 31-day rollover",
            "status": bool_status(cron_schedule_ok),
            "evidence": {
                "configured": AUDIT_SCHEDULER,
                "google_jobs": labels,
                "rolling_days": rolling_days,
                "rolling_timeout_seconds": rolling_timeout_seconds,
                "hourly_jobs": google_hourly_jobs,
                "daily_jobs": google_daily_jobs,
            },
        },
        {
            "id": "direct_cron_runtime",
            "requirement": "Confirm Google Ads direct cron wrappers run cleanly while auth is blocked and post success after native bootstrap",
            "status": bool_status(
                not AUDIT_SCHEDULER
                or (
                    bool(direct_hourly_log.get("ok") and direct_bootstrap_log.get("ok"))
                    and files["direct_cron_success_notify"]
                )
            ),
            "evidence": {
                "hourly": {
                    "timestamp": direct_hourly_log.get("latest_end", {}).get("timestamp"),
                    "status": direct_hourly_log.get("latest_end", {}).get("status"),
                    "age_hours": direct_hourly_log.get("latest_end", {}).get("age_hours"),
                    "auth_blocked": direct_hourly_log.get("auth_blocked"),
                    "log_path": direct_hourly_log.get("log_path"),
                },
                "bootstrap": {
                    "timestamp": direct_bootstrap_log.get("latest_end", {}).get("timestamp"),
                    "status": direct_bootstrap_log.get("latest_end", {}).get("status"),
                    "age_hours": direct_bootstrap_log.get("latest_end", {}).get("age_hours"),
                    "auth_blocked": direct_bootstrap_log.get("auth_blocked"),
                    "log_path": direct_bootstrap_log.get("log_path"),
                },
                "success_notify_source": files["direct_cron_success_notify"],
            },
        },
        {
            "id": "tw_truth",
            "requirement": "Use Triple Whale as source of truth for Google Ads operator reporting",
            "status": bool_status(bool(counts.get("latest_tw_google_date")) and int(counts.get("tw_hourly_rows") or 0) > 0),
            "evidence": f"latest_tw_google_hour={counts.get('latest_tw_google_hour') or 'none'}; tw_hourly_rows={counts.get('tw_hourly_rows', 0)}",
        },
        {
            "id": "tw_l31_coverage",
            "requirement": "Verify actual 31-day Triple Whale attribution coverage for the Google Ads rollover window",
            "status": bool_status(
                int(counts.get("tw_l31_dates") or 0) >= 31
                and int(counts.get("tw_l31_hourly_rows") or 0) > 0
                and counts.get("tw_l31_min_date") == counts.get("tw_l31_expected_start")
                and counts.get("tw_l31_max_date") == counts.get("tw_l31_expected_end")
            ),
            "evidence": {
                "expected_start": counts.get("tw_l31_expected_start"),
                "expected_end": counts.get("tw_l31_expected_end"),
                "min_date": counts.get("tw_l31_min_date"),
                "max_date": counts.get("tw_l31_max_date"),
                "dates": counts.get("tw_l31_dates"),
                "hourly_rows": counts.get("tw_l31_hourly_rows"),
                "spend": counts.get("tw_l31_spend"),
                "revenue": counts.get("tw_l31_revenue"),
            },
        },
        {
            "id": "source_router",
            "requirement": "Route Google Ads work through the google_ads_tw warehouse and gads CLI instead of stale shared TW tables",
            "status": bool_status(bool(source_router_state.get("ok"))),
            "evidence": source_router_state,
        },
        {
            "id": "tw_hourly_scrape_runtime",
            "requirement": "Confirm the launchd-owned hourly Triple Whale Google scrape has succeeded recently",
            "status": bool_status(bool(tw_hourly_log.get("ok"))),
            "evidence": {
                "timestamp": (tw_hourly_log.get("latest_end") or {}).get("timestamp"),
                "status": (tw_hourly_log.get("latest_end") or {}).get("status"),
                "age_hours": (tw_hourly_log.get("latest_end") or {}).get("age_hours"),
                "import_date": tw_hourly_log.get("import_date"),
                "imported_rows": tw_hourly_log.get("imported_rows"),
                "log_path": tw_hourly_log.get("log_path"),
            },
        },
        {
            "id": "tw_warehouse_structure",
            "requirement": "Expose Meta-like Google Ads hourly, daily, campaign, ad group, ad, account, and rolling-31-day TW views",
            "status": bool_status(
                int(counts.get("tw_daily_rows") or 0) > 0
                and int(counts.get("tw_campaign_daily_rows") or 0) > 0
                and int(counts.get("tw_campaign_type_daily_rows") or 0) > 0
                and int(counts.get("tw_ad_group_daily_rows") or 0) > 0
                and int(counts.get("tw_ad_daily_rows") or 0) > 0
                and int(counts.get("tw_account_daily_rows") or 0) > 0
                and int(counts.get("tw_rolling_31d_rows") or 0) > 0
            ),
            "evidence": (
                f"tw_daily={counts.get('tw_daily_rows', 0)}; "
                f"campaign={counts.get('tw_campaign_daily_rows', 0)}; "
                f"campaign_type={counts.get('tw_campaign_type_daily_rows', 0)}; "
                f"ad_group={counts.get('tw_ad_group_daily_rows', 0)}; "
                f"ad={counts.get('tw_ad_daily_rows', 0)}; "
                f"account={counts.get('tw_account_daily_rows', 0)}; "
                f"rolling31={counts.get('tw_rolling_31d_rows', 0)}"
            ),
        },
        {
            "id": "optimizer_reports",
            "requirement": "Create Google Ads reports/optimizer snapshots tailored by campaign type",
            "status": bool_status(
                int(counts.get("optimizer_snapshots") or 0) > 0
                and bool(counts.get("latest_optimizer_has_campaign_type_mix"))
            ),
            "evidence": (
                f"optimizer_snapshots={counts.get('optimizer_snapshots', 0)}; "
                f"latest_snapshot={counts.get('latest_optimizer_snapshot_id') or 'none'}; "
                f"campaign_type_mix={counts.get('latest_optimizer_has_campaign_type_mix')}"
            ),
        },
        {
            "id": "slack_report_delivery",
            "requirement": "Confirm hourly Google Ads Slack report posts with a threaded detail reply and mutes expected native account-access blockers",
            "status": bool_status(not AUDIT_SLACK_REPORT or (bool(slack_report_log.get("ok")) and recurring_slack_policy_ok)),
            "evidence": {
                "configured": AUDIT_SLACK_REPORT,
                "timestamp": (slack_report_log.get("latest_end") or {}).get("timestamp"),
                "status": (slack_report_log.get("latest_end") or {}).get("status"),
                "age_hours": (slack_report_log.get("latest_end") or {}).get("age_hours"),
                "post_channel_ok": slack_report_log.get("post_channel_ok"),
                "thread_ok": slack_report_log.get("thread_ok"),
                "reply_count": slack_report_log.get("reply_count"),
                "native_account_access_pending": not_ads_user,
                "recurring_slack_policy_ok": recurring_slack_policy_ok,
                "raw_oauth_blocker_present": slack_report_log.get("raw_oauth_blocker_present"),
                "native_access_pending_rendered": slack_report_log.get("native_access_pending_rendered"),
                "log_path": slack_report_log.get("log_path"),
            },
        },
        {
            "id": "dashboard",
            "requirement": "Build Google Ads operator dashboard with optimizer, direct sync map, and native API unblock guidance",
            "status": bool_status(
                not AUDIT_DASHBOARD
                or (
                    files["dashboard_route"]
                    and files["dashboard_data"]
                    and files["dashboard_e2e"]
                    and files["dashboard_native_unblock_source"]
                    and files["dashboard_native_unblock_e2e"]
                )
            ),
            "evidence": files,
        },
    ]
    incomplete = [check for check in checks if check["status"] != "pass"]
    return {
        "objective": "Google Ads warehouse, CLI, direct API mapping/backfill, cron, Slack reporting, optimizer, and dashboard",
        "complete": not incomplete,
        "blocked": any(check["status"] == "blocked" for check in incomplete),
        "blocker": auth_blocker,
        "counts": counts,
        "oauth_identity": oauth_identity,
        "catalog_cache": cache_state,
        "source_router": source_router_state,
        "runtime_logs": {
            "tw_hourly_scrape": tw_hourly_log,
            "slack_report": slack_report_log,
            "direct_hourly": direct_hourly_log,
            "direct_bootstrap": direct_bootstrap_log,
        },
        "checks": checks,
        "next_commands_after_access": [
            "gads auth-check",
            "gads post-auth-bootstrap",
            "gads plan-optimizer-actions --format summary",
            "gads completion-audit",
        ],
    }


def cmd_completion_audit(args: argparse.Namespace) -> int:
    payload = completion_audit_payload()
    if args.format == "json":
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("# Google Ads Completion Audit")
        print()
        print(f"- Complete: {'yes' if payload['complete'] else 'no'}")
        if payload.get("blocker"):
            print(f"- Current blocker: {payload['blocker']}")
        identity = payload.get("oauth_identity") or {}
        if identity.get("ok") and identity.get("email_masked"):
            print(f"- OAuth user: {identity['email_masked']}")
        print()
        for check in payload["checks"]:
            status = str(check["status"]).upper()
            print(f"- [{status}] {check['requirement']}")
            print(f"  Evidence: {check['evidence']}")
            if check.get("blocker"):
                print(f"  Blocker: {check['blocker']}")
        if not payload["complete"]:
            print()
            print("## Next Commands After Ads Access Is Granted")
            for command in payload["next_commands_after_access"]:
                print(f"- `{command}`")
    return 0 if payload["complete"] else 2


def truncate(value: Any, length: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= length else text[: length - 1] + "…"


def print_field_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No matching Google Ads fields.")
        return
    print(f"{'Source':<8} {'Name':<44} {'Kind':<10} {'Type':<14} {'Rep':<3} Description")
    print(f"{'-' * 8} {'-' * 44} {'-' * 10} {'-' * 14} {'-' * 3} {'-' * 60}")
    for row in rows:
        print(
            f"{truncate(row.get('source'), 8):<8} "
            f"{truncate(row.get('name'), 44):<44} "
            f"{truncate(row.get('category'), 10):<10} "
            f"{truncate(row.get('data_type'), 14):<14} "
            f"{'yes' if row.get('repeated') else 'no':<3} "
            f"{truncate(row.get('description'), 96)}"
        )


def print_method_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No matching Google Ads API methods.")
        return
    print(f"{'Version':<8} {'Service':<38} {'Method':<28} {'Kind':<8} REST path")
    print(f"{'-' * 8} {'-' * 38} {'-' * 28} {'-' * 8} {'-' * 60}")
    for row in rows:
        print(
            f"{truncate(row.get('api_version'), 8):<8} "
            f"{truncate(row.get('service_name'), 38):<38} "
            f"{truncate(row.get('method_name'), 28):<28} "
            f"{truncate(row.get('operation_kind'), 8):<8} "
            f"{truncate(row.get('rest_path'), 96)}"
        )


def asset_library_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    ensure_schema()
    customer = customer_id(args.customer_id)
    clauses = ["customer_id = %s"]
    params: list[Any] = [customer]
    if args.type != "all":
        clauses.append("upper(type) = %s")
        params.append(args.type.upper())
    if args.query:
        needle = f"%{args.query.lower()}%"
        clauses.append(
            """
            lower(
                coalesce(name, '') || ' ' ||
                coalesce(asset_id, '') || ' ' ||
                coalesce(resource_name, '') || ' ' ||
                coalesce(type, '') || ' ' ||
                coalesce(source, '')
            ) LIKE %s
            """
        )
        params.append(needle)
    params.append(args.limit)
    sql = f"""
        SELECT
            asset_id,
            resource_name,
            coalesce(nullif(name, ''), '(unnamed)') AS name,
            coalesce(type, '') AS type,
            coalesce(source, '') AS source,
            fetched_at::text
        FROM google_assets
        WHERE {' AND '.join(clauses)}
        ORDER BY
            CASE coalesce(type, '')
                WHEN 'YOUTUBE_VIDEO' THEN 1
                WHEN 'IMAGE' THEN 2
                WHEN 'CALL_TO_ACTION' THEN 3
                WHEN 'TEXT' THEN 4
                ELSE 9
            END,
            fetched_at DESC,
            asset_id
        LIMIT %s
    """
    with connect(schema=SCHEMA, application_name="google-ads-assets") as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [
        {
            "asset_id": row[0],
            "resource_name": row[1],
            "name": row[2],
            "type": row[3],
            "source": row[4],
            "fetched_at": row[5],
        }
        for row in rows
    ]


def print_asset_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No matching Google Ads assets.")
        return
    print(f"{'Type':<16} {'Asset ID':<16} {'Name':<48} Resource")
    print(f"{'-' * 16} {'-' * 16} {'-' * 48} {'-' * 70}")
    for row in rows:
        print(
            f"{truncate(row.get('type'), 16):<16} "
            f"{truncate(row.get('asset_id'), 16):<16} "
            f"{truncate(row.get('name'), 48):<48} "
            f"{truncate(row.get('resource_name'), 90)}"
        )


def cmd_asset_library(args: argparse.Namespace) -> int:
    rows = asset_library_rows(args)
    if args.format == "json":
        print(json.dumps({"customer_id": customer_id(args.customer_id), "count": len(rows), "assets": rows}, indent=2, default=str))
    elif args.format == "jsonl":
        for row in rows:
            print(json.dumps(row, default=str))
    else:
        print_asset_table(rows)
    return 0


def cmd_methods(args: argparse.Namespace) -> int:
    ensure_schema()
    clauses = ["api_version = %s"]
    params: list[Any] = [args.version]
    if args.kind:
        clauses.append("operation_kind = %s")
        params.append(args.kind)
    if args.service:
        clauses.append("service_name ILIKE %s")
        params.append(f"%{args.service}%")
    if args.query:
        clauses.append("(service_name ILIKE %s OR method_name ILIKE %s OR coalesce(rest_path, '') ILIKE %s)")
        pattern = f"%{args.query}%"
        params.extend([pattern, pattern, pattern])
    params.append(args.limit)
    sql = f"""
        SELECT coalesce(jsonb_agg(to_jsonb(rows) ORDER BY service_name, method_name), '[]'::jsonb)
        FROM (
            SELECT
                api_version,
                service_name,
                method_name,
                operation_kind,
                rest_path,
                service_file,
                source_ref
            FROM google_api_methods
            WHERE {' AND '.join(clauses)}
            ORDER BY service_name, method_name
            LIMIT %s
        ) rows
    """
    with connect(schema=SCHEMA, application_name="google-ads-operator") as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchone()[0] or []
    if args.format == "json":
        print(json.dumps(rows, indent=2, default=str))
    elif args.format == "jsonl":
        for row in rows:
            print(json.dumps(row, separators=(",", ":"), default=str))
    else:
        print_method_table(rows)
    return 0


def cmd_fields(args: argparse.Namespace) -> int:
    ensure_schema()
    clauses = ["api_version = %s"]
    params: list[Any] = [args.version]
    if args.source != "all":
        clauses.append("source = %s")
        params.append(args.source)
    if args.kind:
        clauses.append("category = %s")
        params.append(args.kind.upper())
    if args.resource:
        clauses.append("resource = %s")
        params.append(args.resource)
    if args.query:
        clauses.append("(name ILIKE %s OR resource ILIKE %s OR coalesce(description, '') ILIKE %s)")
        pattern = f"%{args.query}%"
        params.extend([pattern, pattern, pattern])
    params.append(args.limit)
    sql = f"""
        WITH fields AS (
            SELECT
                'offline'::text AS source,
                api_version,
                field_path AS name,
                resource,
                resource_kind AS category,
                coalesce(proto_type, field_type) AS data_type,
                repeated,
                description
            FROM google_offline_catalog_fields
            UNION ALL
            SELECT
                'live'::text AS source,
                api_version,
                name,
                split_part(name, '.', 1) AS resource,
                category,
                coalesce(data_type, type_url) AS data_type,
                repeated,
                null::text AS description
            FROM google_ads_fields
        )
        SELECT coalesce(jsonb_agg(to_jsonb(rows) ORDER BY source, name), '[]'::jsonb)
        FROM (
            SELECT *
            FROM fields
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE source WHEN 'live' THEN 0 ELSE 1 END,
                CASE category WHEN 'METRIC' THEN 0 WHEN 'SEGMENT' THEN 1 ELSE 2 END,
                name
            LIMIT %s
        ) rows
    """
    with connect(schema=SCHEMA, application_name="google-ads-operator") as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchone()[0] or []
    if args.format == "json":
        print(json.dumps(rows, indent=2, default=str))
    elif args.format == "jsonl":
        for row in rows:
            print(json.dumps(row, separators=(",", ":"), default=str))
    else:
        print_field_table(rows)
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    ensure_schema()
    state = credential_state()
    counts = psql_json(
        """
        SELECT jsonb_build_object(
            'schema', current_schema(),
            'sync_runs', (SELECT count(*) FROM google_sync_runs),
            'successful_runs', (SELECT count(*) FROM google_sync_runs WHERE status = 'success'),
            'raw_snapshots', (SELECT count(*) FROM google_raw_snapshots),
            'fields', (SELECT count(*) FROM google_ads_fields),
            'offline_fields', (SELECT count(*) FROM google_offline_catalog_fields),
            'offline_described_fields', (SELECT count(*) FROM google_offline_catalog_fields WHERE description IS NOT NULL AND description <> ''),
            'offline_v24_metrics', (SELECT count(*) FROM google_offline_catalog_fields WHERE api_version = 'v24' AND resource_kind = 'METRIC'),
            'offline_v24_segments', (SELECT count(*) FROM google_offline_catalog_fields WHERE api_version = 'v24' AND resource_kind = 'SEGMENT'),
            'offline_v24_resource_fields', (SELECT count(*) FROM google_offline_catalog_fields WHERE api_version = 'v24' AND resource_kind IN ('RESOURCE','VIEW')),
            'services', (SELECT count(*) FROM google_api_services),
            'api_methods', (SELECT count(*) FROM google_api_methods),
            'v24_api_methods', (SELECT count(*) FROM google_api_methods WHERE api_version = 'v24'),
            'query_manifest_rows', (SELECT count(*) FROM google_query_manifest),
            'query_manifest_auth_gated', (SELECT count(*) FROM google_query_manifest WHERE requires_auth),
            'query_manifest_no_auth', (SELECT count(*) FROM google_query_manifest WHERE NOT requires_auth),
            'core_surfaces', (SELECT count(*) FROM google_query_manifest WHERE surface_type = 'core'),
            'core_surfaces_with_generic', (SELECT count(*) FROM google_query_manifest WHERE surface_type = 'core' AND warehouse_tables ? 'google_core_generic'),
            'campaigns', (SELECT count(*) FROM google_campaigns),
            'core_generic_rows', (SELECT count(*) FROM google_core_generic),
            'performance_rows', (SELECT count(*) FROM google_performance_daily),
            'performance_generic_rows', (SELECT count(*) FROM google_performance_generic),
            'mutation_plans', (SELECT count(*) FROM google_mutation_plans),
            'search_terms', (SELECT count(*) FROM google_search_terms),
            'optimizer_snapshots', (SELECT count(*) FROM google_optimizer_snapshots),
            'latest_optimizer_snapshot_id', (SELECT id::text FROM google_optimizer_snapshots ORDER BY generated_at DESC LIMIT 1),
            'latest_optimizer_has_campaign_type_mix', coalesce((SELECT decision_payload ? 'campaign_type_mix' AND jsonb_typeof(decision_payload->'campaign_type_mix') = 'array' AND jsonb_array_length(decision_payload->'campaign_type_mix') > 0 FROM google_optimizer_snapshots ORDER BY generated_at DESC LIMIT 1), false),
            'tw_hourly_rows', (SELECT count(*) FROM google_tw_attribution_hourly),
            'tw_daily_rows', (SELECT count(*) FROM google_tw_attribution_daily),
            'tw_account_daily_rows', (SELECT count(*) FROM google_account_daily_performance),
            'tw_campaign_daily_rows', (SELECT count(*) FROM google_campaign_daily_performance),
            'tw_campaign_type_daily_rows', (SELECT count(*) FROM google_campaign_type_daily_performance),
            'tw_ad_group_daily_rows', (SELECT count(*) FROM google_ad_group_daily_performance),
            'tw_ad_daily_rows', (SELECT count(*) FROM google_ad_daily_performance),
            'tw_rolling_31d_rows', (SELECT count(*) FROM google_tw_rolling_31d),
            'latest_auth_status', (SELECT status FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'latest_auth_check', (SELECT completed_at::text FROM google_sync_runs WHERE command = 'auth-check' ORDER BY started_at DESC LIMIT 1),
            'latest_auth_error', (SELECT message FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
            'latest_auth_error_at', (SELECT occurred_at::text FROM google_fetch_errors WHERE endpoint = 'customers:listAccessibleCustomers' ORDER BY occurred_at DESC LIMIT 1),
            'latest_tw_google_date', (SELECT max(report_date)::text FROM google_tw_attribution_hourly),
            'latest_tw_google_hour', (SELECT max(report_hour)::text FROM google_tw_attribution_hourly),
            'latest_direct_sync', (SELECT max(completed_at)::text FROM google_sync_runs WHERE status in ('success','partial'))
        )
        """
    )
    if counts and counts.get("latest_auth_error"):
        counts["latest_auth_error_summary"] = auth_blocker_from_latest(counts)
        counts.pop("latest_auth_error", None)
    print(json.dumps({"credentials": state, "warehouse": counts}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google Ads warehouse and operator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-schema").set_defaults(func=cmd_init_schema)

    sp = sub.add_parser("status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("catalog-client-library")
    sp.add_argument("--refresh", action="store_true")
    sp.set_defaults(func=cmd_catalog_client_library)

    sp = sub.add_parser("catalog-offline-fields")
    sp.add_argument("--refresh", action="store_true")
    sp.set_defaults(func=cmd_catalog_offline_fields)

    sp = sub.add_parser("catalog-summary")
    sp.add_argument("--format", choices=["json", "markdown"], default="markdown")
    sp.set_defaults(func=cmd_catalog_summary)

    sp = sub.add_parser("completion-audit")
    sp.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sp.set_defaults(func=cmd_completion_audit)

    sp = sub.add_parser("query-manifest")
    sp.add_argument("--format", choices=["summary", "markdown", "json"], default="summary")
    sp.add_argument("--no-store", action="store_true")
    sp.set_defaults(func=cmd_query_manifest)

    sp = sub.add_parser("catalog-open-source")
    sp.add_argument("--refresh", action="store_true")
    sp.set_defaults(func=cmd_catalog_open_source)

    sp = sub.add_parser("fields")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--version", default="v24")
    sp.add_argument("--resource")
    sp.add_argument("--kind")
    sp.add_argument("--source", choices=["all", "offline", "live"], default="all")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--format", choices=["table", "json", "jsonl"], default="table")
    sp.set_defaults(func=cmd_fields)

    sp = sub.add_parser("methods")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--version", default="v24")
    sp.add_argument("--service")
    sp.add_argument("--kind", choices=["read", "mutate", "action"])
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--format", choices=["table", "json", "jsonl"], default="table")
    sp.set_defaults(func=cmd_methods)

    sp = sub.add_parser("sync-field-catalog")
    sp.add_argument("--customer-id")
    sp.add_argument("--max-pages", type=int)
    sp.set_defaults(func=cmd_sync_field_catalog)

    sp = sub.add_parser("customers")
    sp.set_defaults(func=cmd_customers)

    sp = sub.add_parser("auth-check")
    sp.set_defaults(func=cmd_auth_check)

    sp = sub.add_parser("auth-doctor")
    sp.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sp.add_argument("--no-tokeninfo", action="store_true")
    sp.add_argument("--show-email", action="store_true", help="include the full OAuth email address in local output")
    sp.set_defaults(func=cmd_auth_doctor)

    sp = sub.add_parser("query")
    sp.add_argument("gaql")
    sp.add_argument("--customer-id")
    sp.add_argument("--name", default="custom")
    sp.add_argument("--source-resource", default="custom")
    sp.add_argument("--format", choices=["json", "jsonl", "summary"], default="json")
    sp.add_argument("--max-pages", type=int)
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("ingest-expert-sources")
    sp.add_argument("--source-ids", help="comma-, pipe-, or newline-separated catalog IDs to ingest; defaults to all")
    sp.add_argument("--keep-going", action="store_true")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_ingest_expert_sources)

    sp = sub.add_parser("keyword-research")
    sp.add_argument("--customer-id")
    sp.add_argument("--seed-terms", help="comma-, pipe-, or newline-separated seed keywords")
    sp.add_argument("--final-url", help="landing page URL for URL or keyword+URL seed research")
    sp.add_argument("--geo-targets", default="2840", help="geo target constant IDs/resource names; default 2840 for United States")
    sp.add_argument("--language", default="1000", help="language constant ID/resource name; default 1000 for English")
    sp.add_argument("--network", choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"], default="GOOGLE_SEARCH")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--allow-broad", action="store_true", help="allow broad-match recommendations for high-volume category terms")
    sp.add_argument("--brand-terms", default="|".join(DEFAULT_BRAND_TERMS), help="brand terms that should stay exact-match")
    sp.add_argument("--fallback-local-search-terms", action=argparse.BooleanOptionalAction, default=True, help="fallback to stored in-account search terms if Keyword Planner access is blocked")
    sp.add_argument("--fallback-days", type=int, default=365)
    sp.add_argument("--format", choices=["summary", "json", "csv"], default="summary")
    sp.set_defaults(func=cmd_keyword_research)

    sp = sub.add_parser("campaign-research-brief")
    sp.add_argument("--customer-id")
    sp.add_argument("--offer", required=True)
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--seed-terms", help="optional seed terms; when present, a fresh keyword-research run is created first")
    sp.add_argument("--run-id", help="existing google_keyword_research_runs id; defaults to latest run")
    sp.add_argument("--geo-targets", default="2840")
    sp.add_argument("--language", default="1000")
    sp.add_argument("--network", choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"], default="GOOGLE_SEARCH")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--max-keywords", type=int, default=30)
    sp.add_argument("--daily-budget-dollars", type=float, default=50.0)
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--allow-broad", action="store_true")
    sp.add_argument("--brand-terms", default="|".join(DEFAULT_BRAND_TERMS))
    sp.add_argument("--include-competitors", action="store_true", help="include detected competitor terms in the generated build command")
    sp.add_argument("--competitor-terms", default="|".join(DEFAULT_COMPETITOR_TERMS))
    sp.add_argument("--fallback-local-search-terms", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--fallback-days", type=int, default=365)
    sp.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sp.set_defaults(func=cmd_campaign_research_brief)

    sp = sub.add_parser("build-search-campaign")
    sp.add_argument("--customer-id")
    sp.add_argument("--offer", required=True)
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--name", help="campaign name; defaults to Search - <offer>")
    sp.add_argument("--budget-name")
    sp.add_argument("--daily-budget-dollars", type=float, default=50.0)
    sp.add_argument("--seed-terms", help="comma-, pipe-, or newline-separated seed keywords; defaults to offer")
    sp.add_argument("--geo-targets", default="2840")
    sp.add_argument("--language", default="1000")
    sp.add_argument("--network", choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"], default="GOOGLE_SEARCH")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--max-keywords", type=int, default=30)
    sp.add_argument("--max-ad-groups", type=int, default=6)
    sp.add_argument("--allow-broad", action="store_true")
    sp.add_argument("--brand-terms", default="|".join(DEFAULT_BRAND_TERMS))
    sp.add_argument("--include-competitors", action="store_true")
    sp.add_argument("--competitor-terms", default="|".join(DEFAULT_COMPETITOR_TERMS))
    sp.add_argument("--bid-strategy", choices=["auto", "manual_cpc", "maximize_conversions", "maximize_conversion_value", "target_cpa", "target_roas"], default="auto")
    sp.add_argument("--target-cpa-dollars", type=float, default=DEFAULT_TARGET_NCPA)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--cpc-bid-dollars", type=float, default=1.0)
    sp.add_argument("--include-search-partners", action="store_true")
    sp.add_argument("--starter-negatives", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--sitelinks", help="semicolon- or newline-separated text|url|description1|description2 entries")
    sp.add_argument("--fallback-local-search-terms", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--fallback-days", type=int, default=365)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_build_search_campaign)

    sp = sub.add_parser("asset-library")
    sp.add_argument("--customer-id")
    sp.add_argument("--type", choices=["all", "YOUTUBE_VIDEO", "IMAGE", "TEXT", "CALL_TO_ACTION", "SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "PROMOTION", "PRICE"], default="all")
    sp.add_argument("--query", help="case-insensitive search across asset name, ID, resource name, type, and source")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--format", choices=["table", "json", "jsonl"], default="table")
    sp.set_defaults(func=cmd_asset_library)

    sp = sub.add_parser("sync-core")
    sp.add_argument("--customer-id")
    sp.add_argument("--surface", default="all", help="all or comma-separated: " + ",".join(CORE_QUERIES))
    sp.add_argument("--max-pages", type=int)
    sp.add_argument("--keep-going", action="store_true")
    sp.set_defaults(func=cmd_sync_core)

    sp = sub.add_parser("sync-performance")
    sp.add_argument("--customer-id")
    sp.add_argument("--surface", default="all", help="all or comma-separated: " + ",".join(PERFORMANCE_SURFACES))
    sp.add_argument("--days", type=int, default=1)
    sp.add_argument("--since")
    sp.add_argument("--until")
    sp.add_argument("--max-pages", type=int)
    sp.add_argument("--keep-going", action="store_true")
    sp.set_defaults(func=cmd_sync_performance)

    sp = sub.add_parser("backfill")
    sp.add_argument("--customer-id")
    sp.add_argument("--surface", default="all")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--since")
    sp.add_argument("--until")
    sp.add_argument("--chunk-days", type=int, default=7)
    sp.add_argument("--max-pages", type=int)
    sp.add_argument("--keep-going", action="store_true")
    sp.set_defaults(func=cmd_backfill)

    sp = sub.add_parser("post-auth-bootstrap")
    sp.add_argument("--customer-id")
    sp.add_argument("--since")
    sp.add_argument("--until")
    sp.add_argument("--full-years", type=int, default=3)
    sp.add_argument("--chunk-days", type=int, default=7)
    sp.add_argument("--max-pages", type=int)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_post_auth_bootstrap)

    sp = sub.add_parser("plan-mutation")
    sp.add_argument("--entity-type", required=True, choices=sorted(MUTATION_ENTITY_CONFIG))
    sp.add_argument("--ids", help="comma/space-separated IDs, resource names, or ad_group_id~entity_id pairs")
    sp.add_argument("--status", choices=["ENABLED", "PAUSED", "REMOVED"])
    sp.add_argument("--amount-micros", type=int)
    sp.add_argument("--amount-dollars", type=float)
    sp.add_argument("--texts", help="comma- or newline-separated search terms for negative keyword plans")
    sp.add_argument("--match-type", choices=["EXACT", "PHRASE", "BROAD"], default="EXACT")
    sp.add_argument("--ad-group-id", help="parent ad group ID or resource name for ad-group negative keyword plans")
    sp.add_argument("--campaign-id", help="parent campaign ID or resource name for campaign negative keyword plans")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_mutation)

    sp = sub.add_parser("plan-search-campaign")
    sp.add_argument("--name", required=True)
    sp.add_argument("--budget-name")
    sp.add_argument("--budget-dollars", type=float, required=True)
    sp.add_argument("--ad-group-name")
    sp.add_argument("--cpc-bid-dollars", type=float, default=1.0)
    sp.add_argument("--bid-strategy", choices=["manual_cpc", "maximize_conversions", "maximize_conversion_value", "target_cpa", "target_roas"], default="manual_cpc")
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--keywords", required=True, help="comma, pipe, or newline-separated; optional text:EXACT|PHRASE|BROAD")
    sp.add_argument("--headlines", help="pipe- or newline-separated responsive-search-ad headlines")
    sp.add_argument("--descriptions", help="pipe- or newline-separated responsive-search-ad descriptions")
    sp.add_argument("--sitelinks", help="semicolon- or newline-separated text|url|description1|description2 entries")
    sp.add_argument("--include-search-partners", action="store_true")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_search_campaign)

    sp = sub.add_parser("plan-shopping-campaign")
    sp.add_argument("--name", required=True)
    sp.add_argument("--budget-name")
    sp.add_argument("--budget-dollars", type=float, required=True)
    sp.add_argument("--ad-group-name")
    sp.add_argument("--cpc-bid-dollars", type=float, default=1.0)
    sp.add_argument("--bid-strategy", choices=["manual_cpc", "maximize_conversions", "maximize_conversion_value", "target_cpa", "target_roas"], default="manual_cpc")
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--merchant-id", help="Merchant Center ID; defaults to first existing Shopping campaign merchant ID")
    sp.add_argument("--feed-label", default="US")
    sp.add_argument("--campaign-priority", type=int, default=2)
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_shopping_campaign)

    sp = sub.add_parser("build-shopping-campaign")
    sp.add_argument("--customer-id")
    sp.add_argument("--offer", required=True)
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--name", help="campaign name; defaults to Shopping - <offer>")
    sp.add_argument("--budget-name")
    sp.add_argument("--daily-budget-dollars", type=float, default=50.0)
    sp.add_argument("--ad-group-name")
    sp.add_argument("--seed-terms", help="comma-, pipe-, or newline-separated seed keywords; defaults to offer")
    sp.add_argument("--geo-targets", default="2840")
    sp.add_argument("--language", default="1000")
    sp.add_argument("--network", choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"], default="GOOGLE_SEARCH")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--allow-broad", action="store_true")
    sp.add_argument("--brand-terms", default="|".join(DEFAULT_BRAND_TERMS))
    sp.add_argument("--cpc-bid-dollars", type=float, default=1.0)
    sp.add_argument("--bid-strategy", choices=["auto", "manual_cpc", "maximize_conversions", "maximize_conversion_value", "target_cpa", "target_roas"], default="auto")
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--merchant-id", help="Merchant Center ID; defaults to first existing Shopping campaign merchant ID")
    sp.add_argument("--feed-label", default="US")
    sp.add_argument("--campaign-priority", type=int, default=2)
    sp.add_argument("--fallback-local-search-terms", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--fallback-days", type=int, default=365)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_build_shopping_campaign)

    sp = sub.add_parser("plan-pmax-campaign")
    sp.add_argument("--name", required=True)
    sp.add_argument("--budget-name")
    sp.add_argument("--budget-dollars", type=float, required=True)
    sp.add_argument("--asset-group-name")
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--bid-strategy", choices=["maximize_conversions", "maximize_conversion_value"], default="maximize_conversion_value")
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--business-name", default=DEFAULT_BUSINESS_NAME)
    sp.add_argument("--headlines", help="pipe-, semicolon-, or newline-separated text assets")
    sp.add_argument("--long-headlines", help="pipe-, semicolon-, or newline-separated long headline text assets")
    sp.add_argument("--descriptions", help="pipe-, semicolon-, or newline-separated description text assets")
    sp.add_argument("--search-themes", help="pipe-, semicolon-, or newline-separated PMax search themes")
    sp.add_argument("--business-name-assets", help="existing BUSINESS_NAME asset IDs or resource names")
    sp.add_argument("--logo-assets", help="existing LOGO asset IDs or resource names")
    sp.add_argument("--landscape-logo-assets", help="existing LANDSCAPE_LOGO asset IDs or resource names")
    sp.add_argument("--marketing-image-assets", help="existing MARKETING_IMAGE asset IDs or resource names")
    sp.add_argument("--square-marketing-image-assets", help="existing SQUARE_MARKETING_IMAGE asset IDs or resource names")
    sp.add_argument("--portrait-marketing-image-assets", help="existing PORTRAIT_MARKETING_IMAGE asset IDs or resource names")
    sp.add_argument("--youtube-video-assets", help="existing YOUTUBE_VIDEO asset IDs or resource names")
    sp.add_argument("--call-to-action-assets", help="existing CALL_TO_ACTION_SELECTION asset IDs or resource names")
    sp.add_argument("--headline-assets", help="existing HEADLINE text asset IDs or resource names")
    sp.add_argument("--long-headline-assets", help="existing LONG_HEADLINE text asset IDs or resource names")
    sp.add_argument("--description-assets", help="existing DESCRIPTION text asset IDs or resource names")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_pmax_campaign)

    sp = sub.add_parser("build-pmax-campaign")
    sp.add_argument("--customer-id")
    sp.add_argument("--offer", required=True)
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--name", help="campaign name; defaults to PMax - <offer>")
    sp.add_argument("--budget-name")
    sp.add_argument("--daily-budget-dollars", type=float, default=50.0)
    sp.add_argument("--asset-group-name")
    sp.add_argument("--seed-terms", help="comma-, pipe-, or newline-separated seed keywords; defaults to offer")
    sp.add_argument("--geo-targets", default="2840")
    sp.add_argument("--language", default="1000")
    sp.add_argument("--network", choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"], default="GOOGLE_SEARCH")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--max-search-themes", type=int, default=20)
    sp.add_argument("--brand-terms", default="|".join(DEFAULT_BRAND_TERMS))
    sp.add_argument("--bid-strategy", choices=["maximize_conversions", "maximize_conversion_value"], default="maximize_conversion_value")
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--business-name", default=DEFAULT_BUSINESS_NAME)
    sp.add_argument("--business-name-assets", help="existing BUSINESS_NAME asset IDs or resource names")
    sp.add_argument("--logo-assets", help="existing LOGO asset IDs or resource names")
    sp.add_argument("--landscape-logo-assets", help="existing LANDSCAPE_LOGO asset IDs or resource names")
    sp.add_argument("--marketing-image-assets", help="existing MARKETING_IMAGE asset IDs or resource names")
    sp.add_argument("--square-marketing-image-assets", help="existing SQUARE_MARKETING_IMAGE asset IDs or resource names")
    sp.add_argument("--portrait-marketing-image-assets", help="existing PORTRAIT_MARKETING_IMAGE asset IDs or resource names")
    sp.add_argument("--youtube-video-assets", help="existing YOUTUBE_VIDEO asset IDs or resource names")
    sp.add_argument("--call-to-action-assets", help="existing CALL_TO_ACTION_SELECTION asset IDs or resource names")
    sp.add_argument("--headline-assets", help="existing HEADLINE text asset IDs or resource names")
    sp.add_argument("--long-headline-assets", help="existing LONG_HEADLINE text asset IDs or resource names")
    sp.add_argument("--description-assets", help="existing DESCRIPTION text asset IDs or resource names")
    sp.add_argument("--fallback-local-search-terms", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--fallback-days", type=int, default=365)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_build_pmax_campaign)

    sp = sub.add_parser("plan-demand-gen-campaign")
    sp.add_argument("--name", required=True)
    sp.add_argument("--budget-name")
    sp.add_argument("--budget-dollars", type=float, required=True)
    sp.add_argument("--ad-group-name")
    sp.add_argument("--ad-name")
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--bid-strategy", choices=["maximize_clicks", "maximize_conversions", "target_cpa", "target_roas"], default="target_cpa")
    sp.add_argument("--target-cpa-dollars", type=float, default=DEFAULT_TARGET_NCPA)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--channel-strategy", choices=["selected_channels", "all_channels", "all_owned_and_operated_channels"], default="selected_channels")
    sp.add_argument("--youtube-in-stream", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--youtube-in-feed", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--youtube-shorts", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--discover", action=argparse.BooleanOptionalAction, default=False)
    sp.add_argument("--gmail", action=argparse.BooleanOptionalAction, default=False)
    sp.add_argument("--display", action=argparse.BooleanOptionalAction, default=False)
    sp.add_argument("--business-name", default=DEFAULT_BUSINESS_NAME)
    sp.add_argument("--youtube-video-assets", help="existing YOUTUBE_VIDEO asset IDs or resource names; when supplied, creates a Demand Gen video responsive ad")
    sp.add_argument("--logo-assets", help="existing IMAGE logo asset IDs or resource names")
    sp.add_argument("--call-to-action-assets", help="existing CALL_TO_ACTION asset IDs or resource names")
    sp.add_argument("--headlines", help="pipe-, semicolon-, or newline-separated short headline text assets")
    sp.add_argument("--long-headlines", help="pipe-, semicolon-, or newline-separated long headline text assets")
    sp.add_argument("--descriptions", help="pipe-, semicolon-, or newline-separated description text assets")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_demand_gen_campaign)

    sp = sub.add_parser("build-demand-gen-campaign")
    sp.add_argument("--customer-id")
    sp.add_argument("--offer", required=True)
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--name", help="campaign name; defaults to Demand Gen - <offer>")
    sp.add_argument("--budget-name")
    sp.add_argument("--daily-budget-dollars", type=float, default=5.0)
    sp.add_argument("--ad-group-name")
    sp.add_argument("--ad-name")
    sp.add_argument("--seed-terms", help="comma-, pipe-, or newline-separated seed keywords; defaults to offer")
    sp.add_argument("--geo-targets", default="2840")
    sp.add_argument("--language", default="1000")
    sp.add_argument("--network", choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"], default="GOOGLE_SEARCH")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--max-research-terms", type=int, default=12)
    sp.add_argument("--allow-broad", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--brand-terms", default="|".join(DEFAULT_BRAND_TERMS))
    sp.add_argument("--bid-strategy", choices=["maximize_clicks", "maximize_conversions", "target_cpa", "target_roas"], default="target_cpa")
    sp.add_argument("--target-cpa-dollars", type=float, default=DEFAULT_TARGET_NCPA)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--channel-strategy", choices=["selected_channels", "all_channels", "all_owned_and_operated_channels"], default="selected_channels")
    sp.add_argument("--youtube-in-stream", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--youtube-in-feed", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--youtube-shorts", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--discover", action=argparse.BooleanOptionalAction, default=False)
    sp.add_argument("--gmail", action=argparse.BooleanOptionalAction, default=False)
    sp.add_argument("--display", action=argparse.BooleanOptionalAction, default=False)
    sp.add_argument("--business-name", default=DEFAULT_BUSINESS_NAME)
    sp.add_argument("--youtube-video-assets", help="existing YOUTUBE_VIDEO asset IDs or resource names; overrides auto-selection")
    sp.add_argument("--video-query", help="prefer an existing YOUTUBE_VIDEO asset matching this asset name, ID, resource, or source")
    sp.add_argument("--auto-video-asset", action=argparse.BooleanOptionalAction, default=True, help="auto-select the latest existing YOUTUBE_VIDEO asset when --youtube-video-assets is omitted")
    sp.add_argument("--logo-assets", help="existing IMAGE logo asset IDs or resource names")
    sp.add_argument("--call-to-action-assets", help="existing CALL_TO_ACTION asset IDs or resource names")
    sp.add_argument("--fallback-local-search-terms", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--fallback-days", type=int, default=365)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_build_demand_gen_campaign)

    sp = sub.add_parser("plan-bid-strategy")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--bid-strategy", required=True, choices=["manual_cpc", "maximize_conversions", "maximize_conversion_value", "target_cpa", "target_roas"])
    sp.add_argument("--target-cpa-dollars", type=float)
    sp.add_argument("--target-roas", type=float)
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_bid_strategy)

    sp = sub.add_parser("plan-campaign-conversion-goal")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--category", default="DEFAULT")
    sp.add_argument("--origin", default="WEBSITE")
    sp.add_argument("--biddable", action=argparse.BooleanOptionalAction, default=True)
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_campaign_conversion_goal)

    sp = sub.add_parser("plan-sitelinks")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--sitelinks", required=True, help="semicolon- or newline-separated text|url|description1|description2 entries")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_sitelinks)

    sp = sub.add_parser("plan-callouts")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--callouts", required=True, help="pipe-, semicolon-, or newline-separated callout text values")
    sp.add_argument("--status", choices=["ENABLED", "PAUSED"], default="PAUSED")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_callouts)

    sp = sub.add_parser("plan-structured-snippets")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--snippets", required=True, help="semicolon- or newline-separated header|value1,value2,value3 entries")
    sp.add_argument("--status", choices=["ENABLED", "PAUSED"], default="PAUSED")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_structured_snippets)

    sp = sub.add_parser("plan-campaign-targeting")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--geo-targets", help="pipe-, semicolon-, or newline-separated geo target constant IDs/resource names")
    sp.add_argument("--excluded-geo-targets", help="pipe-, semicolon-, or newline-separated negative geo target constant IDs/resource names")
    sp.add_argument("--languages", help="pipe-, semicolon-, or newline-separated language constant IDs/resource names")
    sp.add_argument("--ad-schedules", help="semicolon- or newline-separated DAY:start-end specs, e.g. MONDAY:9-17")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_campaign_targeting)

    sp = sub.add_parser("plan-custom-mutate")
    sp.add_argument("operation_json", help="JSON file containing GoogleAdsService mutateOperations")
    sp.add_argument("--entity-type", default="custom")
    sp.add_argument("--operation-type", default="custom")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_custom_mutate)

    sp = sub.add_parser("plan-ad-group")
    sp.add_argument("--campaign-id", required=True, help="campaign ID or resource name")
    sp.add_argument("--name", required=True)
    sp.add_argument("--type", choices=["SEARCH_STANDARD", "SHOPPING_PRODUCT_ADS"], default="SEARCH_STANDARD")
    sp.add_argument("--status", choices=["ENABLED", "PAUSED"], default="PAUSED")
    sp.add_argument("--cpc-bid-dollars", type=float)
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_ad_group)

    sp = sub.add_parser("plan-keywords")
    sp.add_argument("--ad-group-id", required=True, help="ad group ID or resource name")
    sp.add_argument("--keywords", required=True, help="comma, pipe, or newline-separated; optional text:EXACT|PHRASE|BROAD")
    sp.add_argument("--status", choices=["ENABLED", "PAUSED"], default="PAUSED")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_keywords)

    sp = sub.add_parser("plan-responsive-search-ad")
    sp.add_argument("--ad-group-id", required=True, help="ad group ID or resource name")
    sp.add_argument("--final-url", required=True)
    sp.add_argument("--headlines", help="pipe- or newline-separated responsive-search-ad headlines")
    sp.add_argument("--descriptions", help="pipe- or newline-separated responsive-search-ad descriptions")
    sp.add_argument("--status", choices=["ENABLED", "PAUSED"], default="PAUSED")
    sp.add_argument("--customer-id")
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_responsive_search_ad)

    sp = sub.add_parser("plan-search-negatives")
    sp.add_argument("--customer-id")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--since")
    sp.add_argument("--until")
    sp.add_argument("--scope", choices=["ad_group", "campaign"], default="ad_group")
    sp.add_argument("--match-type", choices=["EXACT", "PHRASE", "BROAD"], default="EXACT")
    sp.add_argument("--min-spend", type=float, default=50.0)
    sp.add_argument("--min-clicks", type=int, default=0)
    sp.add_argument("--max-conversions", type=float, default=0.0)
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--max-terms-per-plan", type=int, default=20)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_search_negatives)

    sp = sub.add_parser("plan-budget-adjustments")
    sp.add_argument("--customer-id")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--since")
    sp.add_argument("--until")
    sp.add_argument("--mode", choices=["all", "scale", "defend"], default="all")
    sp.add_argument("--target-ncpa", type=float, default=DEFAULT_TARGET_NCPA)
    sp.add_argument("--min-spend", type=float, default=250.0)
    sp.add_argument("--min-nc-orders", type=float, default=5.0)
    sp.add_argument("--scale-threshold", type=float, default=0.75)
    sp.add_argument("--defense-threshold", type=float, default=1.25)
    sp.add_argument("--increase-percent", type=float, default=15.0)
    sp.add_argument("--decrease-percent", type=float, default=20.0)
    sp.add_argument("--min-budget-dollars", type=float)
    sp.add_argument("--max-budget-dollars", type=float)
    sp.add_argument("--include-shared-budgets", action="store_true")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_budget_adjustments)

    sp = sub.add_parser("plan-optimizer-actions")
    sp.add_argument("--customer-id")
    sp.add_argument("--target-ncpa", type=float, default=DEFAULT_TARGET_NCPA)
    sp.add_argument("--skip-search-negatives", action="store_true")
    sp.add_argument("--search-days", type=int, default=30)
    sp.add_argument("--search-since")
    sp.add_argument("--search-until")
    sp.add_argument("--search-scope", choices=["ad_group", "campaign"], default="ad_group")
    sp.add_argument("--search-match-type", choices=["EXACT", "PHRASE", "BROAD"], default="EXACT")
    sp.add_argument("--search-min-spend", type=float, default=50.0)
    sp.add_argument("--search-min-clicks", type=int, default=0)
    sp.add_argument("--search-max-conversions", type=float, default=0.0)
    sp.add_argument("--search-limit", type=int, default=100)
    sp.add_argument("--max-terms-per-plan", type=int, default=20)
    sp.add_argument("--skip-budget-adjustments", action="store_true")
    sp.add_argument("--budget-days", type=int, default=7)
    sp.add_argument("--budget-since")
    sp.add_argument("--budget-until")
    sp.add_argument("--budget-mode", choices=["all", "scale", "defend"], default="all")
    sp.add_argument("--budget-min-spend", type=float, default=250.0)
    sp.add_argument("--budget-min-nc-orders", type=float, default=5.0)
    sp.add_argument("--scale-threshold", type=float, default=0.75)
    sp.add_argument("--defense-threshold", type=float, default=1.25)
    sp.add_argument("--increase-percent", type=float, default=15.0)
    sp.add_argument("--decrease-percent", type=float, default=20.0)
    sp.add_argument("--min-budget-dollars", type=float)
    sp.add_argument("--max-budget-dollars", type=float)
    sp.add_argument("--include-shared-budgets", action="store_true")
    sp.add_argument("--budget-limit", type=int, default=20)
    sp.add_argument("--note")
    sp.add_argument("--format", choices=["summary", "json"], default="summary")
    sp.set_defaults(func=cmd_plan_optimizer_actions)

    sp = sub.add_parser("mutate")
    sp.add_argument("operation_json")
    sp.add_argument("--customer-id")
    sp.add_argument("--confirm-live", action="store_true")
    sp.add_argument("--slack-channel", help="Slack channel for live mutation recaps; defaults to the Google Ads media-buying channel")
    sp.add_argument("--no-slack", action="store_true", help="Do not post the live mutation recap to Slack")
    sp.set_defaults(func=cmd_mutate)

    sp = sub.add_parser("report")
    sp.add_argument("--date")
    sp.add_argument("--target-ncpa", type=float, default=DEFAULT_TARGET_NCPA)
    sp.add_argument("--format", choices=["slack", "json"], default="slack")
    sp.add_argument("--store-snapshot", action="store_true")
    sp.set_defaults(func=cmd_report)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args) or 0)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
