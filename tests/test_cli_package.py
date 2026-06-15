from __future__ import annotations

import importlib
import pathlib


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
