---
name: google-ads
description: Use when working with Google Ads API auth, sync/backfill, fields, methods, campaigns, search terms, keywords, assets, budgets, recommendations, reports, or mutation plans through the installable gads CLI.
---

# Google Ads CLI Skill

Use the `gads` command from this repo for Google Ads API work.

## Storage And Config

- Config defaults to `~/.google-ads-cli/.env`.
- Override the config directory with `GOOGLE_ADS_CLI_CONFIG_DIR`.
- Runtime state, caches, mutation plans, and logs default to
  `~/.google-ads-cli/`.
- Postgres defaults to `postgresql:///google_ads_cli`; override with
  `GOOGLE_ADS_CLI_PG_DSN` or `DATABASE_URL`.
- Never print credential values.

Required credential keys for live Google Ads API calls:

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CUSTOMER_ID`
- `GOOGLE_ADS_ACCESS_TOKEN` or refresh credentials:
  `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CLIENT_ID`,
  `GOOGLE_ADS_CLIENT_SECRET`

Optional account defaults:

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
- `GOOGLE_ADS_BUSINESS_NAME`
- `GOOGLE_ADS_BRAND_TERMS`
- `GOOGLE_ADS_COMPETITOR_TERMS`
- `GOOGLE_ADS_TARGET_NCPA`
- `GOOGLE_ADS_PMAX_BRAND_ASSETS_FILE`
- `GOOGLE_ADS_PMAX_ASSET_GROUP_ASSETS_FILE`
- `GOOGLE_ADS_DEMAND_GEN_AD_ASSETS_FILE`

## First Commands

```bash
gads status
gads auth-doctor
gads init-schema
gads catalog-client-library --refresh
gads catalog-offline-fields --refresh
gads query-manifest --format summary
```

## Safe Mutation Workflow

1. Plan first with a `gads plan-*` or `gads build-*` command.
2. Validate the output JSON:

```bash
gads mutate --customer-id <id> ~/.google-ads-cli/mutation-plans/<plan-id>.json
```

3. Only after explicit human approval, run:

```bash
gads mutate --customer-id <id> ~/.google-ads-cli/mutation-plans/<plan-id>.json --confirm-live
```

> **Always pass `--customer-id` to `mutate`.** Omitting it does not fail: it
> falls back to the configured default account (`GOOGLE_ADS_CUSTOMER_ID`, in
> practice CGK Linens `7304176160`) and sends the mutate to that account's
> endpoint. A plan built elsewhere is rejected on mismatched
> `customers/<id>/...` resource names, but it still burns DEVELOPER-scoped
> quota — and a plan whose names *did* resolve there would apply to the wrong
> account. `plan-*` records the customer in the plan file; `mutate` does not
> read it back. Verified 2026-08-06.

## Common Commands

```bash
gads customers
gads sync-core --surface all --keep-going
gads sync-performance --days 7 --surface all --keep-going
gads backfill --days 30 --surface all --chunk-days 7 --keep-going
gads keyword-research --seed-terms "keyword one|keyword two" --final-url "https://example.com"
gads campaign-research-brief --offer "Offer Name" --final-url "https://example.com" --seed-terms "keyword one|keyword two"
gads build-search-campaign --offer "Offer Name" --final-url "https://example.com" --seed-terms "keyword one|keyword two"
gads build-shopping-campaign --offer "Offer Name" --final-url "https://example.com"
gads build-pmax-campaign --offer "Offer Name" --final-url "https://example.com" --logo-assets 2222222222 --marketing-image-assets 1010101010 --square-marketing-image-assets 1212121212
gads build-demand-gen-campaign --offer "Offer Name" --final-url "https://example.com" --youtube-video-assets 1515151515 --logo-assets 2222222222
gads plan-optimizer-actions --target-ncpa 70
gads report --format json
gads completion-audit
```

## Weekly Review

The CGK family runs a weekly Google Ads review (Ampd lane, website lane with
Northbeam, Beckham Home and SafeRest via PixelMe). Procedure, windows, rules
and the pull/render scripts: `docs/weekly-review.md` and
`scripts/weekly_review/`. Read the Obsidian analysis log and account
changelog before proposing changes; log every change afterwards.

## Safety

- Default to read-only or validate-only.
- Do not mutate campaigns, budgets, keywords, ads, assets, audiences, or
  conversion settings without a preview and explicit confirmation.
- Store OAuth credentials and developer tokens only in `.env`.
