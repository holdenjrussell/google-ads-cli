# Weekly Google Ads review — CGK Linens family (Ampd, website, PixelMe)

The Wednesday review of every Google Ads account we run, delivered as a branded
PDF to Slack `C0APU5A56F4` with Holden tagged. First edition 2026-09-03
(`~/Reports/google-ads-weekly/CGK-Google-Ads-Weekly-Review-2026-09-03.pdf`).
Owner-approved format; once stable it is scheduled through Hermes.

## 0. Read the logs before touching data (mandatory)

Every review starts by reading what was analyzed and what was changed since the
last one, so recommendations are judged against prior ones and nothing is
re-proposed or re-litigated:

1. Obsidian `Hermes/Google Ads/Analysis Log.md` — every prior audit/review, its
   headline findings, which recommendations were accepted, which were rejected
   (and why), and what is still open.
2. Obsidian `Hermes/Google Ads/Account Changelog.md` — every change in every
   account by date, brand, actor, and evidence source. Cross-check it against
   `google_ads_tw.google_change_events` (re-sync it first, see step 2) and
   `ampd.change_log`.
3. Memory: `project_cgk_google_ads_audit_20260806`, `project_cgk_gads_audit_20260824`,
   `project_cgk_gads_audit_execution_20260826`, `project_google_ads_weekly_review`.
4. The previous PDF in `~/Reports/google-ads-weekly/`.

Anything judged "judge by <date>" in the previous edition is due this week if
the date has passed; report the verdict explicitly (kept / reverted / extended).

## 1. Scope and lanes

| Lane | Account | Attribution truth | Notes |
| --- | --- | --- | --- |
| CGK Ampd (Amazon-bound) | 730-417-6160, campaigns `[Ampd]%` | `ampd.*` (Amazon revenue, BRB, AACOS) | Google conversions are ~0 by design |
| CGK website (cgk.com) | 730-417-6160, everything else (exclude `^(mec\|sani)` and names `1`–`5`) | Google conversion value (last click) **and** Northbeam `northbeam.export_daily` | Northbeam valid for Google only from 2026-08-27 (cgk.com became a managed domain on 08-26) |
| Beckham Home (PixelMe) | 381-888-5747 | `pixelme.product_daily` (Amazon revenue by ASIN); Google conversions = PixelMe upload, 3–4 day lag, zero for un-rewritten campaigns | Brand token in-account is Becky Cameron |
| SafeRest (PixelMe) | 559-064-2315 | `pixelme.product_daily` | |
| Hotel Sheets Direct, DTC Beckham, CGK Walmart | 881-986-7229, 675-743-0621, 242-570-9513 | — | state "no spend" when the sync writes 0 rows |

Never blend lanes or brands. Amazon-bound and website campaigns have different
truth sources and different targets.

## 2. Windows and freshness

- **Last 30** = yesterday-29 … yesterday (Google); Ampd/PixelMe end one day
  earlier (exports land the next morning).
- **Prior 30** = the 30 days before that (trend).
- **Stable 30** = the 30 days ending 14 days ago. Amazon attribution (Ampd and
  PixelMe) is a 14-day post-click window that settles over 10–17 days; every
  bid/budget decision on an Amazon-bound campaign is made on this window only.
  (`ampd.campaign_optimization_window(30,10)` is the same idea with a 10-day cut.)
- **Last 14 / Prior 14** = direction only; label them "immature" wherever shown.
- Calendar month-to-date and last full month for the topline.

Freshness to state in the header: `google_ads_tw.google_sync_runs` (all six
accounts), `ampd.sync_runs`, `pixelme.sync_runs`, `northbeam.sync_runs`, last
`google_change_events` date per account, last `google_recommendations` fetch.

Before pulling, refresh the two feeds the daily sync does not carry:

```bash
for cid in 7304176160 3818885747 5590642315; do
  gads sync-core --customer-id $cid --surface change_event --keep-going
  gads sync-core --customer-id $cid --surface recommendation --keep-going
done
```

## 3. Pull

```bash
cd ~/Tools/google-ads-cli/scripts/weekly_review
env -u NODE_OPTIONS python3 pull.py            # -> ./data/*.json (+ pull.log)
python3 show.py <name> ["<python filter>"] [cols]   # print any saved pull as a table
for c in kw-report bid-report strategy-audit "coverage --check" changes; do
  env -u NODE_OPTIONS ampd $c > ../../../../Reports/google-ads-weekly/ampd-$(date +%F)-$(echo $c|tr ' -' '__').txt; done
```

`pull.py` runs read-only against Neon (DSN via `ampd_cli.config.pg_dsn()`) and
saves one JSON per query: lane windows, daily series, Ampd campaigns by window,
keyword class weekly, top keywords (stable + L30), website campaigns with
Northbeam 7d/1d/cash beside Google, Northbeam platform split, search terms
(waste, winners with exact-keyword coverage flag, Ampd top terms), change events
(summary + detail), `ampd.change_log`, Beckham/SafeRest/Hotel Sheets campaigns
with PixelMe link status, PixelMe product windows, recommendations by type with
impact, budget utilisation L7, the post-change early read, region split.
Edit the window constants at the top of the file each week.

Live reads that the warehouse does not carry (quota is fine for these):

```bash
# impression share incl. lost-to-budget / lost-to-rank, per campaign, last 14 days
gads query --customer-id <cid> "SELECT campaign.id, campaign.name, metrics.cost_micros, metrics.search_impression_share, metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share, metrics.search_top_impression_share FROM campaign WHERE segments.date BETWEEN '<L14 start>' AND '<yesterday>' AND campaign.status='ENABLED' AND metrics.cost_micros > 100000000 ORDER BY metrics.cost_micros DESC" --format json
# live budgets, tROAS / tCPA, Max CPC ceilings (the warehouse copy is only as fresh as the last sync-core)
gads query --customer-id <cid> "SELECT campaign.id, campaign.name, campaign.bidding_strategy_type, campaign_budget.amount_micros, campaign.target_roas.target_roas, campaign.maximize_conversion_value.target_roas, campaign.target_cpa.target_cpa_micros, campaign.maximize_conversions.target_cpa_micros, campaign.target_spend.cpc_bid_ceiling_micros FROM campaign WHERE campaign.status='ENABLED'" --format json
```

## 4. Rules that shape the recommendations

- **AACOS** = (cost − Brand Referral Bonus) / Amazon revenue (Ampd's column).
  Target 30–35% US; ≈40% for amazon.ca (no BRB). PixelMe has no BRB column:
  its ACOS is gross, ~10 pts high.
- **Spend is Google-billed.** Sum spend from `google_ads_tw` or
  `ampd.campaign_daily_complete`, never from the raw Ampd mirror (it drops
  removed campaigns retroactively). State mirror coverage.
- **Renamed campaigns:** Google reports each day's name as it was that day;
  `ampd.campaign_name_fix` maps old → canonical and `ampd.google_lane_daily`
  applies it (fixed 2026-09-03). Add a row there whenever a `[Ampd]` campaign is
  renamed, or the pre-rename days read as unattributed.
- **Know the lever** (`ampd strategy-audit`): Maximize Clicks campaigns have one
  Max CPC ceiling (`campaign.target_spend.cpc_bid_ceiling_micros`); Manual CPC
  campaigns have an ad-group/keyword bid. Under automated strategies a single
  keyword can only be fixed by isolation or by converting to Manual CPC.
- **Bid math:** breakeven CPC = (target AACOS × revenue + BRB) / clicks. Step
  25% when AACOS ≥ 1.5× target, else 10%; never past breakeven. Scale only where
  impression share is lost to rank, not to budget, and AACOS is under target.
- **Website lane:** Google value is last-click and over-credits brand (7–10x
  vs Northbeam 2–3x). Report both; Northbeam wins for decisions from 08-27 on.
  Northbeam rows: `platform_norm='google'`, `kind=''`, `accounting_mode='accrual'`,
  `attribution_model_id='northbeam_custom'`, `attribution_window='7'`.
- **Change attribution:** `adwords-manager@metricstory.com` is Ampd — both a
  person clicking in the Ampd UI and Ampd's own automation write under it.
  `nova@` = our tooling, `holden@` = owner, others = agencies/vendors (Thrasio
  `mark.hoban@thras.io`, Flood Media `josh@floodmedia.co`). Unexplained
  adwords-manager changes at odd hours are automation until proven otherwise.
- **Google recommendations:** accept creative-only classes (RSA ad strength,
  sitelinks, callouts) on `[Ampd]` campaigns; reject every bidding opt-in on
  them (Maximize Conversions / Target CPA — they have no conversion signal),
  marginal-ROI budget raises, broad match, search partners, display expansion.
- **Never** propose a change that a previous edition rejected without saying so
  and why the evidence changed.

## 5. Compose and render

`build_report.py` is the rendered edition: it loads `./data/*.json`, draws the
inline-SVG charts (Raleway; palette navy `#182f5c` / powder `#d7e7f3` / linen
`#ede6df`; one shared $ axis; legend for ≥2 series), builds the tables, and
holds the hand-written prose, verdicts, changelog rows and ranked action list
for that week. Each week: copy last week's file, refresh the constants
(`ampd_win`, `l7`, `live_web`, `live_budget`, `live_ceiling`, `manual_bid`),
rewrite the prose and verdicts from the new pulls, then:

```bash
cp ~/cgk-adimages/brand/{cgk-logo-blue.png,raleway-variable.woff2,bitter-variable.woff2} .
env -u NODE_OPTIONS python3 build_report.py            # -> report.html
env -u NODE_OPTIONS /usr/bin/python3 pdf.py report.html report.pdf   # Playwright chromium; headless google-chrome hangs on this box
pdftoppm -r 55 -png report.pdf qa/p && ls qa            # look at every page before shipping
```

Document structure (keep it — the owner approved this order): header with
windows + sources + freshness → 4 KPI tiles (one per lane) → executive summary
(7 bullets + net-of-actions callout) → §1 Ampd lane (windows table, daily chart,
keyword class, campaign table with stable/L30/L14 and a verdict per row,
keyword concentration, early read on last week's changes) → §2 website lane
(KPI tiles, daily chart, campaign table with Google vs Northbeam, search
terms) → §3 Beckham Home (PixelMe product table, chart, campaign table with
link status) → §4 SafeRest → §5 account changelog for the window → §6 ranked
action list (#, lane, campaign ids, action, where the change is made, expected
effect, judge-by) → §7 open items that need a person → §8 Google
recommendations stance → §9 analysis log → appendix (definitions, freshness,
data fixes shipped).

Every number carries source + window; nothing is estimated without a stated
basis; no exclamation marks; logo on page 1 only.

## 6. Deliver and log

```bash
cp report.pdf ~/Reports/google-ads-weekly/CGK-Google-Ads-Weekly-Review-$(date +%F).pdf
cp report.pdf ~/Downloads/
# Slack: files.getUploadURLExternal -> POST file -> files.completeUploadExternal (channel C0APU5A56F4,
# initial_comment with the 5-line summary and <@U0ACL7UV3RV>)
```

Then, in the same session:

1. Append the edition to Obsidian `Hermes/Google Ads/Analysis Log.md`
   (findings, recommendations, decisions taken, judge-by dates).
2. Append every change found this week to `Hermes/Google Ads/Account
   Changelog.md` (date, account, actor, change, evidence), including our own.
3. Save the review note `Hermes/Google Ads/Weekly Review <date>.md` (summary +
   PDF path) and update `Hermes/Google Ads/00 Folder Index.md`.
4. Update memory `project_google_ads_weekly_review` with what changed in the
   format and any open decision.

## 7. Change-execution etiquette (after the owner approves items)

- CGK `[Ampd]`: campaign creation and ASIN linking only in Ampd (`ampd
  create-campaign`); keywords / negatives / budgets / bids / ceilings are
  attribution-safe via `gads` (attribution rides on the ad's tracking template,
  verified 2026-08-13) but Ampd Protection may reconcile them — read back after
  Ampd's next pass. Log each change to `ampd.change_log` (the CLI does this) and
  to the Obsidian changelog.
- PixelMe brands: structure in Google (`gads`), linkage only in PixelMe; never
  DELETE a campaign in PixelMe.
- `gads mutate` always with `--customer-id`; validate first; `--confirm-live`
  only after approval in-thread; Slack recap per plan.
