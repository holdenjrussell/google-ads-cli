# Database

The CLI uses Postgres schema `google_ads_tw`.

Fast setup:

```bash
createdb google_ads_cli
gads init-schema
```

Alternative setup from the checked-in schema example:

```bash
createdb google_ads_cli
psql -d google_ads_cli -f schema/google_ads_tw.sql
```

The schema file is generated with:

```bash
pg_dump -d google_ads_cli -n google_ads_tw --schema-only --no-owner --no-privileges > schema/google_ads_tw.sql
```

It contains structure only: tables, views, functions, indexes, and constraints.
It does not include customer rows, raw API payloads, tokens, or account IDs.

## Important Tables

- `google_sync_runs`: command run history and row counts
- `google_raw_snapshots`: sanitized request/response storage for debugging
- `google_gaql_rows`: normalized GAQL query rows
- `google_core_generic`: durable catch-all native entity/config rows
- `google_performance_daily` and `google_performance_generic`: native
  platform-reported performance rows
- `google_campaigns`, `google_ad_groups`, `google_ads`, `google_keywords`,
  `google_assets`, `google_asset_groups`: normalized core structures
- `google_search_terms`: search term performance
- `google_keyword_research_runs` and `google_keyword_research_ideas`: Keyword
  Planner and fallback research outputs
- `google_mutation_plans`: validate-only operation plans and execution results
- `google_attribution_hourly_imports` and
  `google_attribution_level_daily_imports`: optional third-party attribution
  imports for reporting

## Required Extensions

No non-core Postgres extensions are required.
