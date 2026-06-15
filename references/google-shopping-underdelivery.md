# Google Shopping underdelivery / not working

Use this when a Shopping campaign has stopped spending or the user asks whether Shopping is budget-limited.

## Key lesson

Do not assume low or zero Shopping delivery means the daily campaign budget is too low. First prove budget limitation from native Google Ads status. In a recent diagnosis, the live campaign had `$600/day` budget, zero spend, and Google returned `primary_status=NOT_ELIGIBLE`; increasing budget would have been the wrong live write.

## Fast diagnosis sequence

1. Verify sync/auth freshness:

```bash
gads status
```

2. Identify enabled Shopping / Smart Shopping / PMax Shopping-ish campaigns and budgets from the warehouse:

```sql
SELECT c.customer_id, c.campaign_id, c.name, c.status, c.serving_status,
       c.advertising_channel_type, c.advertising_channel_sub_type,
       c.bidding_strategy_type, c.campaign_budget,
       b.budget_id, b.name AS budget_name, b.status AS budget_status,
       round(b.amount_micros / 1000000.0, 2) AS daily_budget,
       b.delivery_method, b.explicitly_shared, c.fetched_at
FROM google_ads_tw.google_campaigns c
LEFT JOIN google_ads_tw.google_campaign_budgets b
  ON b.customer_id = c.customer_id
 AND b.resource_name = c.campaign_budget
WHERE lower(c.name) LIKE '%shopping%'
   OR c.advertising_channel_type = 'SHOPPING'
   OR c.advertising_channel_sub_type LIKE '%SHOPPING%'
ORDER BY c.status, c.name;
```

3. Compare today / recent spend with budget using TW and native performance. If budget is high and spend is near zero, look for eligibility/product issues before budget changes.

```sql
SELECT p.date_start, p.campaign_id, p.campaign_name, c.status, c.serving_status,
       c.bidding_strategy_type, round(b.amount_micros / 1000000.0, 2) AS daily_budget,
       round(p.spend, 2) AS spend, p.impressions, p.clicks,
       p.new_customer_orders, round(p.revenue, 2) AS revenue,
       round(p.ncpa, 2) AS ncpa, round(p.roas, 2) AS roas
FROM google_ads_tw.google_campaign_daily_performance p
LEFT JOIN google_ads_tw.google_campaigns c ON c.campaign_id = p.campaign_id
LEFT JOIN google_ads_tw.google_campaign_budgets b
  ON b.customer_id = c.customer_id
 AND b.resource_name = c.campaign_budget
WHERE p.date_start = (SELECT max(date_start) FROM google_ads_tw.google_campaign_daily_performance)
  AND (lower(p.campaign_name) LIKE '%shopping%' OR c.advertising_channel_type = 'SHOPPING')
ORDER BY p.spend DESC;
```

4. Use live GAQL for Google's own status signal before changing budget:

```bash
gads query "SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status, campaign.primary_status, campaign.primary_status_reasons, campaign_budget.amount_micros, campaign.bidding_strategy_type FROM campaign WHERE campaign.id IN (<campaign_ids>)" --format json --max-pages 1
```

Interpretation:

- `primary_status_reasons` includes budget reasons -> budget action may be appropriate, still plan/validate before live.
- `primary_status=NOT_ELIGIBLE`, `primary_status_reasons=[UNKNOWN]`, or `serving_status=ENDED` -> do not raise budget as the first fix.
- `serving_status=ENDED` / `primary_status=ENDED` / reason `CAMPAIGN_ENDED` -> campaign date/state issue; budget will not revive it.

5. If not budget-limited, inspect the Shopping product surface:

```bash
gads query "SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status, ad_group.type, ad_group.cpc_bid_micros, ad_group.target_roas, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.ad.type FROM ad_group_ad WHERE campaign.id IN (<campaign_ids>)" --format json --max-pages 1

gads query "SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id, ad_group_criterion.status, ad_group_criterion.negative, ad_group_criterion.listing_group.type FROM ad_group_criterion WHERE campaign.id = <campaign_id> AND ad_group_criterion.type = LISTING_GROUP" --format json --max-pages 1
```

Check for:

- Enabled product ad and ad group, but low ad-group CPC bid / strict tROAS.
- Paused root or subdivision listing groups.
- Mostly negative listing-group units or very narrow product targeting.
- Google recommendations such as `SHOPPING_ADD_PRODUCTS_TO_CAMPAIGN` or `SHOPPING_TARGET_ALL_OFFERS`.

6. If Google says products are excluded, inspect current Shopping product eligibility directly. This distinguishes an Ads budget issue from a Merchant Center / Shopify feed or product-ID mismatch:

```bash
gads query "SELECT shopping_product.item_id, shopping_product.title, shopping_product.status, shopping_product.availability, shopping_product.issues FROM shopping_product WHERE shopping_product.campaign = 'customers/<customer_id>/campaigns/<campaign_id>'" --format json --max-pages 5
```

Interpretation:

- `status=NOT_ELIGIBLE` with issue `not_eligible_excluded_product_listing_group` means the products are in excluded listing groups; do not raise budget.
- If the previously spending `shopping_product.item_id` values no longer return from a campaign-scoped `shopping_product` query, suspect feed/product-ID churn or a Merchant Center / Shopify-side change that made the Ads listing groups no longer match the live products.
- Current products can be `IN_STOCK` and still not deliver when all matching listing groups are excluded.

7. When the user asks "when did this change / who changed it," use Google Ads `change_event` but respect its query constraints:

```bash
gads query "SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, change_event.resource_name, change_event.change_resource_name, change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields, change_event.old_resource, change_event.new_resource FROM change_event WHERE change_event.change_date_time BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD' AND change_event.change_resource_type = 'AD_GROUP_CRITERION' ORDER BY change_event.change_date_time DESC LIMIT 10000" --format json --max-pages 1

gads query "SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, change_event.resource_name, change_event.change_resource_name, change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields, change_event.old_resource, change_event.new_resource FROM change_event WHERE change_event.change_date_time BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD' AND change_event.ad_group = 'customers/<customer_id>/adGroups/<ad_group_id>' ORDER BY change_event.change_date_time DESC LIMIT 10000" --format json --max-pages 1

gads query "SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, change_event.resource_name, change_event.change_resource_name, change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields, change_event.old_resource, change_event.new_resource FROM change_event WHERE change_event.change_date_time BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD' AND change_event.campaign = 'customers/<customer_id>/campaigns/<campaign_id>' ORDER BY change_event.change_date_time DESC LIMIT 10000" --format json --max-pages 1
```

Change-event pitfalls:

- The date range must be finite and cannot start more than 30 days back.
- Google Ads requires an explicit `LIMIT` of 10k or less.
- `change_event.change_resource_name` is selectable but cannot be used in `WHERE`; filter by `change_event.campaign`, `change_event.ad_group`, `change_resource_type`, or `user_email`, then inspect returned resource names.
- If no retained Ads change event ties to the affected campaign/ad group/product partition, say that plainly. Do not invent attribution; the likely cause may be Merchant Center/feed/product-ID change outside Google Ads change history.

Recommendation lookup:

```sql
SELECT recommendation_id, campaign_id, type, dismissed, impact, raw, fetched_at
FROM google_ads_tw.google_recommendations
WHERE campaign_id IN (<campaign_ids>)
ORDER BY fetched_at DESC
LIMIT 20;
```

## Response pattern

Be direct: answer budget first, then the likely blocker, then the safe next action.

Example:

```text
Not budget-limited. I did not raise budget.
Campaign X has $600/day but $0 spend.
Live Google says NOT_ELIGIBLE, not budget-limited.
Likely issue: products/listing group or tROAS/bid.
Next: validate product-targeting/listing-group fix before live.
```

## Safety

- Never increase budget just because the user asks if budget is the issue; verify `primary_status` / reasons first.
- Budget, bid strategy, listing-group, and recommendation changes must be planned and validated via `gads mutate` or a reviewed custom mutate plan, then run live only after explicit approval.
- If the local CLI lacks a named planner for a product-targeting recommendation, say so and use `plan-custom-mutate` with reviewed operations rather than improvising a live API write.
