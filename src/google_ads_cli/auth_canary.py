"""Small, database-free auth probe. Reports safe status; never sends messages."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile

from . import auth


def expected_customers() -> list[str]:
    raw = os.environ.get("GOOGLE_ADS_CUSTOMER_IDS", "")
    if raw:
        import re
        values = re.split(r"[,|\s]+", raw)
    else:
        path = os.environ.get("GOOGLE_ADS_CUSTOMER_ACCOUNTS_FILE", "")
        if not path:
            raise ValueError("Expected customer inventory is missing")
        data = json.loads(Path(path).expanduser().read_text())
        values = [row["customer_id"] for row in data["accounts"]]
    values = list(dict.fromkeys(str(x).replace("-", "") for x in values if x))
    if not values or any(not x.isdigit() for x in values):
        raise ValueError("Expected customer inventory is invalid")
    return values


def atomic_receipt(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(*, request, customers: list[str], require_service_account: bool = True) -> dict:
    previous_mode = os.environ.get("GOOGLE_ADS_AUTH_MODE")
    lanes = ["service_account", "oauth"] if require_service_account else ["oauth"]
    result = {"issue_id": "CGK-GADS-ACCESS", "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "expected_count": len(customers), "lanes": [], "ok": False}
    try:
        for lane in lanes:
            os.environ["GOOGLE_ADS_AUTH_MODE"] = lane
            checks = []
            def probe(label, method, path, payload=None):
                try:
                    body, headers = request(method, path, payload)
                    request_id = next((v for k, v in headers.items() if k.lower() == "request-id"), None)
                    item = {"target": label, "ok": True, "request_id": request_id}
                    if label != "accessible":
                        rows = body.get("results", [])
                        status = rows[0].get("customer", {}).get("status") if rows else None
                        item.update(status=status, ok=status == "ENABLED")
                    checks.append(item)
                except auth.ApiError as exc:
                    checks.append({"target": label, "ok": False, **exc.summary})
                except Exception:
                    checks.append({"target": label, "ok": False, "codes": ["CREDENTIAL_UNAVAILABLE"]})
            probe("accessible", "GET", "customers:listAccessibleCustomers")
            # Always query every expected customer. Listing alone misses a
            # canceled child under an otherwise healthy manager account.
            for customer in customers:
                label = hashlib.sha256(customer.encode()).hexdigest()[:12]
                probe(label, "POST", f"customers/{customer}/googleAds:search",
                      {"query": "SELECT customer.id, customer.status FROM customer"})
            result["lanes"].append({"mode": lane, "ok": all(x["ok"] for x in checks), "checks": checks})
        result["ok"] = result["lanes"][0]["ok"]
        result["fallback_ok"] = result["lanes"][-1]["ok"]
    finally:
        if previous_mode is None:
            os.environ.pop("GOOGLE_ADS_AUTH_MODE", None)
        else:
            os.environ["GOOGLE_ADS_AUTH_MODE"] = previous_mode
    return result


def command(args) -> int:
    from . import cli
    cli.load_env()
    try:
        if not os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
            raise ValueError("Manager login customer is missing")
        result = run(request=cli.api_request, customers=expected_customers(),
                     require_service_account=not args.oauth_only)
    except Exception:
        result = {"issue_id": "CGK-GADS-ACCESS", "ok": False, "codes": ["CANARY_CONFIGURATION_ERROR"]}
    if args.receipt:
        atomic_receipt(Path(args.receipt).expanduser(), result)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1
