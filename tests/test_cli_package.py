from __future__ import annotations

import importlib
import json
import pathlib
import sys
import types
from argparse import Namespace

import pytest


def test_parser_exposes_core_command_surface():
    module = importlib.import_module("google_ads_cli.cli")
    parser = module.build_parser()
    actions = [
        action
        for action in parser._actions
        if action.__class__.__name__ == "_SubParsersAction"
    ]
    assert actions, "parser should define subcommands"
    commands = set(actions[0].choices)
    expected = {
        "status",
        "init-schema",
        "auth-check",
        "auth-doctor",
        "customers",
        "query",
        "sync-core",
        "sync-performance",
        "backfill",
        "keyword-research",
        "campaign-research-brief",
        "build-search-campaign",
        "build-shopping-campaign",
        "build-pmax-campaign",
        "build-demand-gen-campaign",
        "plan-search-campaign",
        "plan-shopping-campaign",
        "plan-pmax-campaign",
        "plan-demand-gen-campaign",
        "plan-mutation",
        "plan-custom-mutate",
        "mutate",
        "report",
        "completion-audit",
    }
    assert expected.issubset(commands)


def test_report_format_is_generic_and_threaded(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_REPORT_TITLE", "Google Ads Heartbeat")
    module = importlib.reload(importlib.import_module("google_ads_cli.cli"))
    payload = {
        "report_date": "2026-06-12",
        "overall": {
            "latest_hour": "2026-06-12 10:00:00",
            "today_spend": 100,
            "today_revenue": 300,
            "today_nc_orders": 5,
            "l7_spend": 700,
            "l7_revenue": 2100,
            "l7_nc_orders": 35,
        },
        "credential_state": {"ready": True, "missing": []},
        "direct_status": {"last_auth_status": "success", "campaigns": 1, "last_sync": "2026-06-12"},
        "recommendations": {"scale_up": [], "defend": [], "search_actions": [], "pmax_watch": []},
        "campaign_type_mix": [],
        "brand_split": [],
        "top_campaigns": [],
        "completion_audit": {"checks": []},
    }
    text = module.format_slack_report(payload, snapshot_id="snapshot-123")
    assert text.startswith("===SLACK_MAIN===")
    assert "===SLACK_THREAD===" in text
    assert "# Google Ads Heartbeat" in text
    assert "snapshot-123" in text


def test_repository_has_no_workspace_or_account_literals():
    root = pathlib.Path(__file__).resolve().parents[1]
    needles = [
        "vita" + "hustle",
        "C" + "0B" + "492RE679",
        "679" + "7312797",
        "435" + "8524439",
        "/Users/" + "nova",
        ".her" + "mes",
        "ai.her" + "mes",
    ]
    scanned_suffixes = {".py", ".md", ".sh", ".toml", ".example", ".json", ".txt", ".sql"}
    offenders: list[str] = []
    for path in root.rglob("*"):
        if (
            any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in path.parts)
            or path.is_dir()
            or path.suffix not in scanned_suffixes
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        for needle in needles:
            if needle.casefold() in text:
                offenders.append(f"{path.relative_to(root)} contains {needle}")
    assert not offenders


def test_auth_blocker_ignores_stale_error_after_success():
    module = importlib.import_module("google_ads_cli.cli")
    invalid_rapt = (
        'Google OAuth refresh failed 400: {"error": "invalid_grant", '
        '"error_description": "reauth related error (invalid_rapt)", '
        '"error_subtype": "invalid_rapt"}'
    )

    assert "re-auth required" in module.summarize_auth_error(invalid_rapt)
    assert module.auth_blocker_from_latest(
        {"latest_auth_status": "success", "latest_auth_error": invalid_rapt}
    ) is None
    assert "re-auth required" in module.auth_blocker_from_latest(
        {"latest_auth_status": "error", "latest_auth_error": invalid_rapt}
    )


def test_auth_doctor_omits_access_grant_runbook_when_ready(monkeypatch, capsys):
    module = importlib.import_module("google_ads_cli.cli")

    monkeypatch.setattr(
        module,
        "auth_doctor_payload",
        lambda **kwargs: {
            "ok": True,
            "blocker": None,
            "configured_accounts": {
                "customer_id": "123",
                "login_customer_id": "456",
                "api_version": "v24",
            },
            "oauth_identity": {"ok": True, "email_masked": "te****@example.com"},
            "checks": [{"id": "ads_user_access", "ok": True, "evidence": "passed"}],
            "next_steps": ["Run gads completion-audit."],
            "access_runbook": {
                "oauth_user": "te****@example.com",
                "manager_account_id": "456",
                "customer_id": "123",
                "steps": ["Invite the OAuth user."],
            },
            "commands_after_access": ["gads auth-check"],
        },
    )

    assert module.cmd_auth_doctor(Namespace(no_tokeninfo=False, show_email=False, format="summary")) == 0
    output = capsys.readouterr().out
    assert "Status: ready" in output
    assert "Access Grant Runbook" not in output
    assert "Commands After Access" not in output


def test_catalog_offline_fields_batches_rows(monkeypatch, capsys):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []

    rows = [
        {
            "api_version": "v24",
            "resource": "campaign",
            "field_name": "id",
            "field_path": "campaign.id",
            "resource_kind": "resource",
            "class_name": "Campaign",
            "field_type": "int64",
            "proto_type": "TYPE_INT64",
            "enum_type": None,
            "message_type": None,
            "repeated": False,
            "optional": False,
            "description": None,
            "source_file": "campaign.py",
            "raw": {"name": "id"},
        },
        {
            "api_version": "v24",
            "resource": "metrics",
            "field_name": "cost_micros",
            "field_path": "metrics.cost_micros",
            "resource_kind": "metric",
            "class_name": "Metrics",
            "field_type": "int64",
            "proto_type": "TYPE_INT64",
            "enum_type": None,
            "message_type": None,
            "repeated": False,
            "optional": False,
            "description": None,
            "source_file": "metrics.py",
            "raw": {"name": "cost_micros"},
        },
    ]

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            calls.append(("execute", statement, params))

        def executemany(self, statement, params_seq):
            calls.append(("executemany", statement, list(params_seq)))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(module, "ensure_schema", lambda: None)
    monkeypatch.setattr(module, "clone_or_update", lambda *args, **kwargs: "abcdef123456")
    monkeypatch.setattr(module, "parse_offline_catalog_fields", lambda path: rows)
    monkeypatch.setattr(module, "upsert_catalog_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "connect", lambda **kwargs: FakeConnection())

    assert module.cmd_catalog_offline_fields(Namespace(refresh=False)) == 0
    capsys.readouterr()
    execute_inserts = [
        call for call in calls if call[0] == "execute" and "INSERT INTO google_offline_catalog_fields" in call[1]
    ]
    executemany_inserts = [
        call for call in calls if call[0] == "executemany" and "INSERT INTO google_offline_catalog_fields" in call[1]
    ]
    assert not execute_inserts
    assert len(executemany_inserts) == 1
    assert len(executemany_inserts[0][2]) == len(rows)


def test_pg_connect_keeps_schema_search_path_in_caller_transaction(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            calls.append(("execute", statement))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            calls.append(("commit", None))

    def fake_connect(*args, **kwargs):
        calls.append(("connect", args, kwargs))
        return FakeConnection()

    fake_psycopg = types.SimpleNamespace(connect=fake_connect)
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setenv("GOOGLE_ADS_CLI_PG_DSN", "postgresql://example/db")

    pg = importlib.reload(importlib.import_module("google_ads_cli.pg"))
    conn = pg.connect(schema="google_ads_tw", application_name="test-app")

    assert isinstance(conn, FakeConnection)
    connect_call = calls[0]
    assert connect_call[0] == "connect"
    assert connect_call[2] == {"application_name": "test-app"}
    assert ("execute", 'CREATE SCHEMA IF NOT EXISTS "google_ads_tw"') in calls
    assert ("execute", 'SET search_path TO "google_ads_tw", public') in calls
    assert ("commit", None) not in calls


def test_upsert_core_rows_batches_ad_rows(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            calls.append(("execute", statement, params))

        def executemany(self, statement, params_seq):
            params = list(params_seq)
            calls.append(("executemany", statement, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(module, "connect", lambda **kwargs: FakeConnection())

    rows = [
        {
            "campaign": {"id": "11"},
            "adGroup": {"id": "22"},
            "adGroupAd": {
                "resourceName": "customers/123/adGroupAds/22~33",
                "status": "ENABLED",
                "ad": {
                    "id": "33",
                    "resourceName": "customers/123/ads/33",
                    "name": "Ad 33",
                    "type": "RESPONSIVE_SEARCH_AD",
                    "finalUrls": ["https://example.com"],
                    "displayUrl": "example.com",
                },
            },
        },
        {
            "campaign": {"id": "11"},
            "adGroup": {"id": "22"},
            "adGroupAd": {
                "resourceName": "customers/123/adGroupAds/22~44",
                "status": "PAUSED",
                "ad": {
                    "id": "44",
                    "resourceName": "customers/123/ads/44",
                    "type": "TEXT_AD",
                },
            },
        },
    ]

    assert module.upsert_core_rows("123", "ad", rows) == 2
    executemany_calls = [call for call in calls if call[0] == "executemany"]
    assert len(executemany_calls) == 1
    assert len(executemany_calls[0][2]) == 2
    assert [params[:4] for params in executemany_calls[0][2]] == [
        ("123", "22", "33", "11"),
        ("123", "22", "44", "11"),
    ]
    assert executemany_calls[0][2][0][4:10] == (
        "customers/123/ads/33",
        "Ad 33",
        "ENABLED",
        "RESPONSIVE_SEARCH_AD",
        '["https://example.com"]',
        "example.com",
    )
    assert executemany_calls[0][2][0][10] == module.jsonb(rows[0]["adGroupAd"])
    assert not [
        call
        for call in calls
        if call[0] == "execute" and "INSERT INTO google_ads" in call[1]
    ]


def test_store_core_generic_rows_batches_rows(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            calls.append(("execute", statement, params))

        def executemany(self, statement, params_seq):
            params = list(params_seq)
            calls.append(("executemany", statement, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(module, "connect", lambda **kwargs: FakeConnection())

    rows = [
        {"campaign": {"resourceName": "customers/123/campaigns/1", "id": "1"}},
        {"campaign": {"resourceName": "customers/123/campaigns/2", "id": "2"}},
    ]

    assert (
        module.store_core_generic_rows(
            customer="123",
            surface="campaign",
            query_name="core_campaign",
            source_resource="campaign",
            query="select campaign.id from campaign",
            rows=rows,
        )
        == 2
    )
    executemany_calls = [call for call in calls if call[0] == "executemany"]
    assert len(executemany_calls) == 1
    assert len(executemany_calls[0][2]) == 2
    first_params = executemany_calls[0][2][0]
    assert first_params[:2] == ("123", "campaign")
    assert first_params[2] == module.core_entity_key("campaign", rows[0])
    assert first_params[3:7] == (
        "core_campaign",
        "campaign",
        module.row_hash(rows[0], "core_campaign"),
        "select campaign.id from campaign",
    )
    assert first_params[7:] == (
        module.jsonb(module.core_selected_fields(rows[0])),
        module.jsonb(rows[0]),
    )
    assert not [
        call
        for call in calls
        if call[0] == "execute" and "INSERT INTO google_core_generic" in call[1]
    ]


def test_performance_storage_batches_rows(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            calls.append(("execute", statement, params))

        def executemany(self, statement, params_seq):
            params = list(params_seq)
            calls.append(("executemany", statement, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(module, "connect", lambda **kwargs: FakeConnection())
    rows = [
        {
            "segments": {"date": "2026-06-24"},
            "campaign": {"id": "1", "name": "Campaign 1"},
            "metrics": {"impressions": "10", "clicks": "2", "costMicros": "1000000"},
        },
        {
            "segments": {"date": "2026-06-23"},
            "campaign": {"id": "2", "name": "Campaign 2"},
            "metrics": {"impressions": "20", "clicks": "3", "costMicros": "2000000"},
        },
    ]

    assert module.upsert_performance_rows("123", "campaign", rows) == 2
    assert (
        module.store_performance_generic_rows(
            customer="123",
            surface="campaign",
            query_name="performance_campaign",
            query="select campaign.id from campaign",
            rows=rows,
        )
        == 2
    )
    executemany_calls = [call for call in calls if call[0] == "executemany"]
    assert len(executemany_calls) == 2
    assert all(len(call[2]) == 2 for call in executemany_calls)
    assert not [
        call
        for call in calls
        if call[0] == "execute"
        and (
            "INSERT INTO google_performance_daily" in call[1]
            or "INSERT INTO google_performance_generic" in call[1]
        )
    ]


def test_store_gaql_rows_batches_rows(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            calls.append(("execute", statement, params))

        def executemany(self, statement, params_seq):
            params = list(params_seq)
            calls.append(("executemany", statement, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(module, "connect", lambda **kwargs: FakeConnection())
    rows = [{"campaign": {"id": "1"}}, {"campaign": {"id": "2"}}]

    assert (
        module.store_gaql_rows(
            "run-1",
            customer="123",
            query_name="core_campaign",
            source_resource="campaign",
            query="select campaign.id from campaign",
            rows=rows,
        )
        == 2
    )
    executemany_calls = [call for call in calls if call[0] == "executemany"]
    assert len(executemany_calls) == 1
    assert len(executemany_calls[0][2]) == 2
    first_params = executemany_calls[0][2][0]
    assert first_params == (
        "run-1",
        "123",
        "core_campaign",
        "campaign",
        None,
        module.row_hash(rows[0], "core_campaign"),
        "select campaign.id from campaign",
        module.jsonb(rows[0]),
    )
    assert not [
        call
        for call in calls
        if call[0] == "execute" and "INSERT INTO google_gaql_rows" in call[1]
    ]


def test_large_gaql_and_generic_writes_use_fresh_bounded_transactions(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []
    commits = []

    class FakeCursor:
        def __init__(self, connection_number):
            self.connection_number = connection_number

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, statement, params_seq):
            calls.append((self.connection_number, statement, list(params_seq)))

    class FakeConnection:
        def __init__(self, connection_number):
            self.connection_number = connection_number

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            assert exc_type is None
            commits.append(self.connection_number)
            return False

        def cursor(self):
            return FakeCursor(self.connection_number)

    def fake_connect(**kwargs):
        assert kwargs == {
            "schema": module.SCHEMA,
            "application_name": "google-ads-warehouse",
        }
        return FakeConnection(len(calls) + 1)

    monkeypatch.setattr(module, "WAREHOUSE_WRITE_BATCH_SIZE", 2)
    monkeypatch.setattr(module, "connect", fake_connect)
    rows = [
        {"campaign": {"id": str(index), "resourceName": f"customers/123/campaigns/{index}"}}
        for index in range(5)
    ]

    assert (
        module.store_gaql_rows(
            "run-1",
            customer="123",
            query_name="core_campaign",
            source_resource="campaign",
            query="select campaign.id from campaign",
            rows=rows,
        )
        == 5
    )
    assert (
        module.store_core_generic_rows(
            customer="123",
            surface="campaign",
            query_name="core_campaign",
            source_resource="campaign",
            query="select campaign.id from campaign",
            rows=rows,
        )
        == 5
    )

    assert [len(call[2]) for call in calls] == [2, 2, 1, 2, 2, 1]
    assert commits == [1, 2, 3, 4, 5, 6]
    assert all("ON CONFLICT" in call[1] for call in calls)


def test_large_keyword_write_uses_bounded_executemany(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            calls.append(("execute", statement, params))

        def executemany(self, statement, params_seq):
            calls.append(("executemany", statement, list(params_seq)))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(module, "WAREHOUSE_WRITE_BATCH_SIZE", 2)
    monkeypatch.setattr(module, "connect", lambda **kwargs: FakeConnection())
    rows = [
        {
            "campaign": {"id": "11"},
            "adGroup": {"id": "22"},
            "adGroupCriterion": {
                "resourceName": f"customers/123/adGroupCriteria/22~{index}",
                "criterionId": str(index),
                "status": "ENABLED",
                "negative": False,
                "keyword": {"text": f"keyword {index}", "matchType": "EXACT"},
                "qualityInfo": {"qualityScore": 8},
                "finalUrls": ["https://example.com"],
            },
        }
        for index in range(1, 6)
    ]

    assert module.upsert_core_rows("123", "keyword", rows) == 5
    executemany_calls = [call for call in calls if call[0] == "executemany"]
    assert [len(call[2]) for call in executemany_calls] == [2, 2, 1]
    assert all("INSERT INTO google_keywords" in call[1] for call in executemany_calls)
    assert executemany_calls[0][2][0] == (
        "123",
        "22",
        "1",
        "11",
        "keyword 1",
        "EXACT",
        "ENABLED",
        False,
        8,
        '["https://example.com"]',
        module.jsonb(rows[0]["adGroupCriterion"]),
    )
    assert not [call for call in calls if call[0] == "execute"]


def test_batch_commit_failure_stops_without_retry_and_reports_boundary(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    calls = []
    committed = []

    class FakeAdminShutdown(Exception):
        sqlstate = "57P01"

    class FakeCursor:
        def __init__(self, connection_number):
            self.connection_number = connection_number

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, statement, params_seq):
            calls.append((self.connection_number, list(params_seq)))

    class FakeConnection:
        def __init__(self, connection_number):
            self.connection_number = connection_number

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if self.connection_number == 2:
                raise FakeAdminShutdown(
                    "server closed postgresql://operator:super-secret@example/db "
                    "while writing SELECT private_payload"
                )
            committed.append(self.connection_number)
            return False

        def cursor(self):
            return FakeCursor(self.connection_number)

    def fake_connect(**kwargs):
        return FakeConnection(len(calls) + 1)

    monkeypatch.setattr(module, "WAREHOUSE_WRITE_BATCH_SIZE", 2)
    monkeypatch.setattr(module, "connect", fake_connect)
    rows = [
        {"campaign": {"id": str(index), "resourceName": f"customers/123/campaigns/{index}"}}
        for index in range(5)
    ]

    with pytest.raises(module.WarehouseBatchWriteError) as caught:
        module.store_core_generic_rows(
            customer="123",
            surface="campaign",
            query_name="core_campaign",
            source_resource="campaign",
            query="select campaign.id from campaign",
            rows=rows,
        )

    assert committed == [1]
    assert [len(call[1]) for call in calls] == [2, 2]
    assert isinstance(caught.value.__cause__, FakeAdminShutdown)
    assert caught.value.receipt() == {
        "operation": "store_core_generic_rows",
        "batch_number": 2,
        "batch_count": 3,
        "batch_rows": 2,
        "rows_confirmed": 2,
        "total_rows": 5,
        "automatic_retry": False,
        "cause_type": "FakeAdminShutdown",
        "sqlstate": "57P01",
    }
    serialized_receipt = json.dumps(caught.value.receipt(), sort_keys=True)
    assert len(serialized_receipt) < 512
    assert "super-secret" not in serialized_receipt
    assert "private_payload" not in serialized_receipt
    assert "super-secret" not in str(caught.value)
    assert "private_payload" not in str(caught.value)


def test_sync_core_records_bounded_write_failure_without_false_success(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    starts = []
    finishes = []
    rows = [{"adGroupCriterion": {"criterionId": str(index)}} for index in range(3)]
    failure = module.WarehouseBatchWriteError(
        operation="store_gaql_rows",
        batch_number=2,
        batch_count=2,
        batch_rows=1,
        rows_confirmed=2,
        total_rows=3,
    )

    def fail_store(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, "ensure_schema", lambda: None)
    monkeypatch.setattr(module, "customer_id", lambda value: value)
    monkeypatch.setattr(
        module,
        "run_start",
        lambda *args, **kwargs: starts.append((args, kwargs)) or "run-1",
    )
    monkeypatch.setattr(module, "search_gaql", lambda *args, **kwargs: rows)
    monkeypatch.setattr(module, "store_gaql_rows", fail_store)
    monkeypatch.setattr(
        module,
        "store_core_generic_rows",
        lambda **kwargs: pytest.fail("generic write must not run after GAQL failure"),
    )
    monkeypatch.setattr(
        module,
        "upsert_core_rows",
        lambda *args, **kwargs: pytest.fail("normalized write must not run after GAQL failure"),
    )
    monkeypatch.setattr(
        module,
        "run_finish",
        lambda run_id, status, **kwargs: finishes.append((run_id, status, kwargs)),
    )

    with pytest.raises(module.WarehouseBatchWriteError):
        module.cmd_sync_core(
            Namespace(
                customer_id="123",
                surface="keyword",
                max_pages=None,
                keep_going=False,
            )
        )

    assert starts == [(('sync-core', '123', {'surfaces': ['keyword']}), {})]
    assert finishes == [
        (
            "run-1",
            "error",
            {
                "rows_fetched": 3,
                "rows_written": 0,
                "errors": 1,
                "metadata": {
                    "warehouse_write_failures": [
                        {"surface": "keyword", **failure.receipt()}
                    ]
                },
            },
        )
    ]


def test_sync_core_finish_failure_does_not_issue_error_overwrite(monkeypatch):
    module = importlib.import_module("google_ads_cli.cli")
    finishes = []
    rows = [{"campaign": {"id": "1"}}]

    def fail_finish(run_id, status, **kwargs):
        finishes.append((run_id, status, kwargs))
        raise RuntimeError("receipt connection outcome unknown")

    monkeypatch.setattr(module, "ensure_schema", lambda: None)
    monkeypatch.setattr(module, "customer_id", lambda value: value)
    monkeypatch.setattr(module, "run_start", lambda *args, **kwargs: "run-1")
    monkeypatch.setattr(module, "search_gaql", lambda *args, **kwargs: rows)
    monkeypatch.setattr(module, "store_gaql_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(module, "store_core_generic_rows", lambda **kwargs: 1)
    monkeypatch.setattr(module, "upsert_core_rows", lambda *args, **kwargs: 1)
    monkeypatch.setattr(module, "run_finish", fail_finish)

    with pytest.raises(RuntimeError, match="receipt connection outcome unknown"):
        module.cmd_sync_core(
            Namespace(
                customer_id="123",
                surface="campaign",
                max_pages=None,
                keep_going=False,
            )
        )

    assert len(finishes) == 1
    assert finishes[0][0:2] == ("run-1", "success")
    assert finishes[0][2]["rows_fetched"] == 1
    assert finishes[0][2]["rows_written"] == 1
