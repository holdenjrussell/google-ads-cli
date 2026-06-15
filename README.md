# Google Ads CLI

Installable Google Ads API warehouse and operator CLI.

This repo packages the `gads` command for Google Ads API auth checks, field and
method cataloging, native sync/backfill, keyword research, campaign planning,
validate-only mutation previews, optional live mutations, reports, and audits.

No account credentials, customer IDs, Slack channels, local paths, or brand
defaults are committed. Put machine/account-specific values in
`~/.google-ads-cli/.env`.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create a local config:

```bash
mkdir -p ~/.google-ads-cli
cp .env.example ~/.google-ads-cli/.env
chmod 600 ~/.google-ads-cli/.env
```

Create the database and schema:

```bash
createdb google_ads_cli
gads init-schema
```

You can also inspect or apply the schema-only example in
`schema/google_ads_tw.sql`.

## Configuration

Required for live Google Ads API calls:

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CUSTOMER_ID`
- `GOOGLE_ADS_ACCESS_TOKEN` or the refresh-token trio:
  `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CLIENT_ID`,
  `GOOGLE_ADS_CLIENT_SECRET`

Common optional settings:

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` for MCC access
- `GOOGLE_ADS_CLI_PG_DSN` for Postgres
- `GOOGLE_ADS_BUSINESS_NAME`, `GOOGLE_ADS_BRAND_TERMS`, and
  `GOOGLE_ADS_COMPETITOR_TERMS` for planner defaults
- `GOOGLE_ADS_PMAX_BRAND_ASSETS_FILE`,
  `GOOGLE_ADS_PMAX_ASSET_GROUP_ASSETS_FILE`, and
  `GOOGLE_ADS_DEMAND_GEN_AD_ASSETS_FILE` for reusable asset defaults
- `GOOGLE_ADS_SLACK_CHANNEL_ID` and `GOOGLE_ADS_SLACK_HELPER` for optional live
  mutation recap posts

See `docs/customization.md` for the full customization contract and
`docs/database.md` for schema details.

OAuth bootstrap:

```bash
cp /path/to/google-oauth-desktop-client.json ~/.google-ads-cli/google-ads-oauth-client.json
scripts/bootstrap_google_ads_oauth.sh
```

## Commands

Core setup and discovery:

```bash
gads status
gads init-schema
gads auth-check
gads auth-doctor
gads customers
gads catalog-client-library --refresh
gads catalog-offline-fields --refresh
gads catalog-open-source --refresh
gads sync-field-catalog
gads fields campaign.status
gads methods --version v24 --limit 25
gads query-manifest --format summary
```

Native sync and backfill:

```bash
gads sync-core --surface all --keep-going
gads sync-performance --days 7 --surface all --keep-going
gads backfill --days 30 --surface all --chunk-days 7 --keep-going
gads post-auth-bootstrap
```

Research and campaign planning:

```bash
gads keyword-research --seed-terms "running shoes|trail shoes" --final-url "https://example.com/products/shoes"
gads campaign-research-brief --offer "Trail Shoes" --final-url "https://example.com/products/shoes" --seed-terms "trail shoes|running shoes"
gads build-search-campaign --offer "Trail Shoes" --final-url "https://example.com/products/shoes" --seed-terms "trail shoes|running shoes"
gads build-shopping-campaign --offer "Trail Shoes" --final-url "https://example.com/products/shoes" --daily-budget-dollars 50
gads build-pmax-campaign --offer "Trail Shoes" --final-url "https://example.com/products/shoes" --logo-assets 2222222222 --marketing-image-assets 1010101010 --square-marketing-image-assets 1212121212
gads build-demand-gen-campaign --offer "Trail Shoes" --final-url "https://example.com/products/shoes" --youtube-video-assets 1515151515 --logo-assets 2222222222
```

Manual planners:

```bash
gads plan-search-campaign --name "Search - Trail Shoes" --budget-dollars 50 --final-url "https://example.com/products/shoes" --keywords "trail shoes:EXACT,running shoes:PHRASE"
gads plan-shopping-campaign --name "Shopping - Trail Shoes" --budget-dollars 50 --feed-label US --merchant-id 1234567890
gads plan-pmax-campaign --name "PMax - Trail Shoes" --budget-dollars 50 --final-url "https://example.com/products/shoes" --logo-assets 2222222222 --marketing-image-assets 1010101010 --square-marketing-image-assets 1212121212
gads plan-demand-gen-campaign --name "Demand Gen - Trail Shoes" --budget-dollars 5 --final-url "https://example.com/products/shoes" --youtube-video-assets 1515151515 --logo-assets 2222222222
gads plan-ad-group --campaign-id 123 --name "Trail Shoes"
gads plan-keywords --ad-group-id 456 --keywords "trail shoes:EXACT,running shoes:PHRASE"
gads plan-responsive-search-ad --ad-group-id 456 --final-url "https://example.com/products/shoes" --headlines "Trail Shoes|Shop Running Shoes|Order Online" --descriptions "Find trail shoes online.|Shop running gear today."
gads plan-bid-strategy --campaign-id 123 --bid-strategy maximize_conversions
gads plan-campaign-conversion-goal --campaign-id 123 --category DEFAULT --origin WEBSITE --biddable
gads plan-sitelinks --campaign-id 123 --sitelinks "Shoes|https://example.com/products/shoes|Shop shoes|Order online"
gads plan-callouts --campaign-id 123 --callouts "Free Shipping|Easy Returns|New Styles"
gads plan-structured-snippets --campaign-id 123 --snippets "Types|Trail,Running,Walking"
gads plan-campaign-targeting --campaign-id 123 --geo-targets 2840 --languages 1000
gads plan-mutation --entity-type campaign --ids 123 --status PAUSED
gads plan-search-negatives --days 30 --min-spend 50
gads plan-budget-adjustments --days 7 --mode all --target-ncpa 70
gads plan-optimizer-actions --target-ncpa 70
gads plan-custom-mutate /path/to/googleads-mutate-operations.json
```

Mutation execution is validate-only unless you explicitly confirm live writes:

```bash
gads mutate ~/.google-ads-cli/mutation-plans/<plan-id>.json
gads mutate ~/.google-ads-cli/mutation-plans/<plan-id>.json --confirm-live
```

Reporting and audits:

```bash
gads report --format json
gads report --store-snapshot --format slack
gads completion-audit
```

The report and optimizer commands can use optional attribution-export tables if
you populate the `google_tw_*` and `google_*_daily_performance` views/tables.
Direct Google Ads API setup, sync/backfill, planners, and mutation workflows do
not require those optional attribution tables.

## Safety

- Mutations are validate-only by default.
- Live writes require `--confirm-live`.
- Secrets belong in `~/.google-ads-cli/.env`, never in the repo.
- OAuth email is masked by default. Use `gads auth-doctor --show-email` only in
  your local terminal when granting account access.
