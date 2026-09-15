"""Service-account credentials for unattended, read-only warehouse callers."""
from __future__ import annotations

import os
from pathlib import Path
import stat


class CredentialError(RuntimeError):
    """Safe to log: never includes a credential or provider response body."""


_credentials = None
_fingerprint = None


def mode() -> str:
    value = os.environ.get("GOOGLE_ADS_AUTH_MODE", "oauth")
    if value not in {"oauth", "service_account", "auto"}:
        raise CredentialError("GOOGLE_ADS_AUTH_MODE must be oauth, service_account or auto")
    return value


def service_account_token() -> str:
    global _credentials, _fingerprint
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    raw = os.environ.get("GOOGLE_ADS_JSON_KEY_FILE_PATH", "")
    if not raw:
        raise CredentialError("GOOGLE_ADS_JSON_KEY_FILE_PATH is missing")
    path = Path(raw).expanduser()
    try:
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600):
            raise CredentialError("Service-account key must be an owned regular file with mode 0600")
        fingerprint = (str(path), metadata.st_ino, metadata.st_mtime_ns, metadata.st_size)
        if fingerprint != _fingerprint:
            _credentials = service_account.Credentials.from_service_account_file(
                str(path), scopes=["https://www.googleapis.com/auth/adwords"]
            )
            _fingerprint = fingerprint
        if not _credentials.valid:
            # No subject / domain-wide delegation. Google Ads grants access to
            # this identity directly, at the manager level.
            _credentials.refresh(Request())
        if not _credentials.token:
            raise CredentialError("Service-account token response was empty")
        return _credentials.token
    except CredentialError:
        raise
    except Exception as exc:
        raise CredentialError("Service-account credential could not mint an access token") from None


def safe_read_path(method: str, path: str) -> bool:
    path = path.lstrip("/")
    return ((method.upper() == "GET" and path == "customers:listAccessibleCustomers")
            or (method.upper() == "POST" and (path.endswith("/googleAds:search")
                or path.endswith("/googleAds:searchStream") or path == "googleAdsFields:search")))


def error_summary(status: int, body: dict, headers: dict) -> dict:
    error = body.get("error", {}) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    codes, request_id = [], None
    for detail in error.get("details", []):
        request_id = detail.get("requestId") or request_id
        for item in detail.get("errors", []):
            codes.extend(str(v) for v in item.get("errorCode", {}).values())
    if not request_id:
        request_id = next((v for k, v in headers.items() if k.lower() == "request-id"), None)
    return {"http_status": status, "status": error.get("status"),
            "codes": sorted(set(codes)), "request_id": request_id}


class ApiError(RuntimeError):
    def __init__(self, summary: dict):
        self.summary = summary
        import json
        super().__init__("Google Ads API " + json.dumps(summary, sort_keys=True))


def permits_oauth_retry(summary: dict) -> bool:
    codes = set(summary.get("codes", []))
    return bool(codes) and codes <= {
        "USER_PERMISSION_DENIED", "NOT_ADS_USER", "OAUTH_TOKEN_INVALID",
        "OAUTH_TOKEN_EXPIRED", "AUTHENTICATION_ERROR", "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
    }
