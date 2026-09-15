import io
import json
import os
import urllib.error

import pytest

from google_ads_cli import auth, auth_canary, cli


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_AUTH_MODE", "oauth")
    monkeypatch.setattr(cli, "load_env", lambda: None)


def test_key_permissions_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "key.json"
    path.write_text('{}')
    path.chmod(0o644)
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", str(path))
    with pytest.raises(auth.CredentialError, match="0600"):
        auth.service_account_token()
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", str(link))
    with pytest.raises(auth.CredentialError, match="regular file"):
        auth.service_account_token()


def test_key_exception_never_prints_secret(tmp_path, monkeypatch):
    path = tmp_path / "key.json"
    path.write_text('{"private_key":"secret-sentinel"}')
    path.chmod(0o600)
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", str(path))
    with pytest.raises(auth.CredentialError) as exc:
        auth.service_account_token()
    assert "secret-sentinel" not in str(exc.value)


def test_service_account_reuses_and_refreshes_token(tmp_path, monkeypatch):
    from google.oauth2 import service_account
    path = tmp_path / "key.json"
    path.write_text('{}')
    path.chmod(0o600)
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", str(path))
    calls = []
    class Credential:
        valid = False
        token = None
        def refresh(self, request):
            calls.append("refresh")
            self.valid = True
            self.token = "test-token"
    credential = Credential()
    def factory(path, *, scopes):
        assert scopes == ["https://www.googleapis.com/auth/adwords"]
        calls.append("load")
        return credential
    monkeypatch.setattr(service_account.Credentials, "from_service_account_file", factory)
    monkeypatch.setattr(auth, "_fingerprint", None)
    assert auth.service_account_token() == "test-token"
    assert auth.service_account_token() == "test-token"
    assert calls == ["load", "refresh"]
    credential.valid = False
    auth.service_account_token()
    assert calls == ["load", "refresh", "refresh"]


def test_auto_never_mutates(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_AUTH_MODE", "auto")
    with pytest.raises(auth.CredentialError, match="read-only"):
        cli.api_request("POST", "customers/123/googleAds:mutate", {})


def test_auto_uses_fallback_on_credential_failure(monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_ADS_AUTH_MODE", "auto")
    seen = []
    def headers():
        seen.append(auth.mode())
        if auth.mode() == "auto":
            raise auth.CredentialError("unavailable")
        return {}
    class Response(io.BytesIO):
        headers = {}
    monkeypatch.setattr(cli, "google_headers", headers)
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: Response(b'{}'))
    assert cli.api_request("GET", "customers:listAccessibleCustomers")[0] == {}
    assert seen == ["auto", "oauth"]
    assert auth.mode() == "auto"
    assert "CGK-GADS-ACCESS" in capsys.readouterr().err


@pytest.mark.parametrize("code,retry", [("CUSTOMER_NOT_ENABLED", False), ("USER_PERMISSION_DENIED", True), ("DEVELOPER_TOKEN_PROHIBITED", False)])
def test_api_error_retry_and_redaction(monkeypatch, code, retry):
    monkeypatch.setenv("GOOGLE_ADS_AUTH_MODE", "auto")
    monkeypatch.setattr(cli, "google_headers", lambda: {})
    calls = []
    class Response(io.BytesIO):
        headers = {}
    def urlopen(*a, **k):
        calls.append(auth.mode())
        if len(calls) == 1:
            body = {"error": {"status":"PERMISSION_DENIED", "message":"private-sentinel", "details":[{"requestId":"request-123", "errors":[{"errorCode":{"authorizationError":code},"message":"private-sentinel"}]}]}}
            raise urllib.error.HTTPError("https://example.com",403,"Forbidden",{},io.BytesIO(json.dumps(body).encode()))
        return Response(b'{}')
    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)
    if retry:
        cli.api_request("GET", "customers:listAccessibleCustomers")
        assert calls == ["auto","oauth"]
    else:
        with pytest.raises(auth.ApiError) as exc:
            cli.api_request("GET", "customers:listAccessibleCustomers")
        assert exc.value.summary["request_id"] == "request-123"
        assert code in str(exc.value)
        assert "private-sentinel" not in str(exc.value)
        assert calls == ["auto"]


def test_canary_catches_disabled_child_despite_accessible_manager(monkeypatch):
    queries = []
    def request(method,path,payload):
        queries.append((auth.mode(),path))
        if "222" in path:
            raise auth.ApiError({"http_status":403,"codes":["CUSTOMER_NOT_ENABLED"],"request_id":"req"})
        return {"results":[{"customer":{"status":"ENABLED"}}]},{}
    result = auth_canary.run(request=request,customers=["111","222"])
    assert not result["ok"] and not result["fallback_ok"]
    assert len(queries) == 6
    assert "222" not in json.dumps(result)
    assert auth.mode() == "oauth"


def test_canary_does_not_hide_primary_failure_with_fallback():
    def request(*args):
        if auth.mode() == "service_account":
            raise auth.CredentialError("unavailable")
        return {"results":[{"customer":{"status":"ENABLED"}}]},{}
    result=auth_canary.run(request=request,customers=["111"])
    assert not result["ok"] and result["fallback_ok"]


def test_receipt_mode_is_private(tmp_path):
    path=tmp_path/'receipt.json'
    auth_canary.atomic_receipt(path,{"ok":True})
    assert path.stat().st_mode & 0o777 == 0o600
