# Customization

All account-specific values belong outside the repository.

The CLI loads `~/.google-ads-cli/.env` by default. You can override that with
`GOOGLE_ADS_CLI_CONFIG_DIR`.

## Core Defaults

```bash
GOOGLE_ADS_CLI_HOME=~/.google-ads-cli
GOOGLE_ADS_CLI_PG_DSN=postgresql:///google_ads_cli
GOOGLE_ADS_BUSINESS_NAME=Your Business
GOOGLE_ADS_BRAND_TERMS=brand term one|brand term two
GOOGLE_ADS_COMPETITOR_TERMS=competitor one|competitor two
GOOGLE_ADS_TARGET_NCPA=70
GOOGLE_ADS_REPORT_TITLE=Google Ads Heartbeat
```

## Asset Defaults

PMax and Demand Gen build commands can use existing account assets from JSON
files. See:

- `examples/pmax-brand-assets.example.json`
- `examples/pmax-asset-group-assets.example.json`
- `examples/demand-gen-assets.example.json`

Enable them in `.env`:

```bash
GOOGLE_ADS_PMAX_BRAND_ASSETS_FILE=/absolute/path/pmax-brand-assets.json
GOOGLE_ADS_PMAX_ASSET_GROUP_ASSETS_FILE=/absolute/path/pmax-asset-group-assets.json
GOOGLE_ADS_DEMAND_GEN_AD_ASSETS_FILE=/absolute/path/demand-gen-assets.json
```

You can also pass assets directly per command with flags like `--logo-assets`,
`--marketing-image-assets`, `--square-marketing-image-assets`, and
`--youtube-video-assets`.

## Optional Slack Recaps

Live mutation recap posts are optional.

```bash
GOOGLE_ADS_SLACK_CHANNEL_ID=C0123456789
GOOGLE_ADS_SLACK_HELPER=/absolute/path/to/post_slack_direct.py
```

The helper should accept `--channel-id <id>` and read the message body from
stdin. If no helper/channel is configured, live mutations still run but Slack
recap posting is skipped with a warning unless you pass `--no-slack`.

## Optional Scheduler Audit

The CLI can audit local macOS launchd jobs, but this is disabled by default.

```bash
GOOGLE_ADS_AUDIT_SCHEDULER=true
GOOGLE_ADS_DIRECT_HOURLY_JOB=google-ads-direct-hourly
GOOGLE_ADS_DIRECT_HOURLY_LABELS=com.example.google-ads-direct-hourly
GOOGLE_ADS_DIRECT_DAILY_LABELS=com.example.google-ads-direct-daily
GOOGLE_ADS_DIRECT_BOOTSTRAP_LABELS=com.example.google-ads-direct-bootstrap
GOOGLE_ADS_REPORT_HOURLY_LABELS=com.example.google-ads-report-hourly
GOOGLE_ADS_ATTRIBUTION_HOURLY_LABELS=com.example.google-ads-attribution-hourly
GOOGLE_ADS_ATTRIBUTION_ROLLING_LABELS=com.example.google-ads-attribution-rolling
```

Runtime logs default to `~/.google-ads-cli/logs/<job>.direct.log`.

## Optional Dashboard Audit

Dashboard checks are disabled by default.

```bash
GOOGLE_ADS_AUDIT_DASHBOARD=true
GOOGLE_ADS_DASHBOARD_ROUTE_PATHS=/path/to/src/app/google-ads/page.tsx
GOOGLE_ADS_DASHBOARD_DATA_PATHS=/path/to/src/lib/google-ads-report.ts
GOOGLE_ADS_DASHBOARD_E2E_PATHS=/path/to/scripts/google-ads-e2e.mjs
```

## Optional Attribution Imports

Direct Google Ads API features do not need attribution-export data. If you have
third-party attribution exports, load them into:

- `google_ads_tw.google_attribution_hourly_imports`
- `google_ads_tw.google_attribution_level_daily_imports`

The reporting views `google_tw_attribution_*` read from those import tables.
