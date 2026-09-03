#!/usr/bin/env python3
"""Weekly Google Ads / Ampd / PixelMe / Northbeam review — warehouse pull (read-only)."""
import json, sys, os, decimal, datetime
sys.path.insert(0, os.path.expanduser('~/Tools/ampd-cli'))
from ampd_cli import config
import psycopg2, psycopg2.extras
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
conn = psycopg2.connect(config.pg_dsn()); conn.set_session(readonly=True, autocommit=True)
W = {'L30':('2026-08-04','2026-09-02'),'P30':('2026-07-05','2026-08-03'),'STABLE':('2026-07-21','2026-08-19'),
     'L14':('2026-08-20','2026-09-02'),'P14':('2026-08-06','2026-08-19')}
WIN_VALUES = "(VALUES " + ",".join(f"('{k}','{s}'::date,'{e}'::date)" for k,(s,e) in W.items()) + ") w(win,s,e)"
def conv(o):
    if isinstance(o, decimal.Decimal): return float(o)
    if isinstance(o,(datetime.date,datetime.datetime)): return o.isoformat()
    return str(o)
def q(name, sql, show=25, params=None):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET statement_timeout = '120s'")
    try:
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"\n##### {name}: ERROR {e}"); conn.rollback(); return []
    with open(os.path.join(OUT, name+'.json'),'w') as f: json.dump(rows, f, default=conv, indent=0)
    print(f"\n##### {name} ({len(rows)} rows)")
    if rows:
        cols = list(rows[0].keys()); print("\t".join(cols))
        for r in rows[:show]:
            print("\t".join("" if r[c] is None else (f"{r[c]:.2f}" if isinstance(r[c],(float,decimal.Decimal)) else str(r[c]))[:60] for c in cols))
        if len(rows)>show: print(f"... {len(rows)-show} more")
    return rows

LANE = """CASE WHEN campaign_name ILIKE '[ampd]%%' THEN 'ampd' WHEN campaign_name ~* '^(mec|sani)' OR campaign_name IN ('1','2','3','4','5') THEN 'mec' ELSE 'website' END"""

q('lane_windows', f"""
WITH c AS (SELECT report_date, campaign_id, campaign_name, cost_micros/1e6 AS spend, impressions, clicks, conversions, conversions_value, {LANE} AS lane
  FROM google_ads_tw.google_performance_daily WHERE customer_id='7304176160' AND level='campaign' AND report_date BETWEEN '2026-07-05' AND '2026-09-02')
SELECT w.win, lane, ROUND(SUM(spend)::numeric,2) spend, SUM(impressions) impr, SUM(clicks) clicks, ROUND(SUM(conversions)::numeric,1) conv, ROUND(SUM(conversions_value)::numeric,2) conv_value,
  COUNT(DISTINCT campaign_id) FILTER (WHERE spend>0) campaigns
FROM c JOIN {WIN_VALUES} ON report_date BETWEEN w.s AND w.e GROUP BY 1,2 ORDER BY 1,2""", show=30)

q('cgk_daily_lane', f"""
SELECT report_date::text d, {LANE} AS lane, ROUND(SUM(cost_micros)/1e6::numeric,2) spend, SUM(clicks) clicks, ROUND(SUM(conversions)::numeric,1) conv, ROUND(SUM(conversions_value)::numeric,2) conv_value
FROM google_ads_tw.google_performance_daily WHERE customer_id='7304176160' AND level='campaign' AND report_date BETWEEN '2026-06-01' AND '2026-09-02' GROUP BY 1,2 ORDER BY 1,2""", show=6)

q('ampd_daily', """
SELECT date::text d, ROUND(SUM(google_cost)::numeric,2) cost, ROUND(SUM(amazon_revenue)::numeric,2) rev, ROUND(SUM(brand_referral_bonus)::numeric,2) brb,
  SUM(amazon_conversions) conv, SUM(clicks) clicks, ROUND(SUM(google_cost) FILTER (WHERE NOT has_attribution)::numeric,2) unattributed_cost
FROM ampd.campaign_daily_complete WHERE date BETWEEN '2026-06-01' AND '2026-09-02' GROUP BY 1 ORDER BY 1""", show=8)

q('ampd_campaigns', f"""
WITH b AS (SELECT c.campaign_id, c.name, c.status, c.bidding_strategy_type, cb.amount_micros/1e6 AS budget
  FROM google_ads_tw.google_campaigns c LEFT JOIN google_ads_tw.google_campaign_budgets cb ON cb.resource_name=c.campaign_budget AND cb.customer_id=c.customer_id
  WHERE c.customer_id='7304176160'),
d AS (SELECT w.win, x.campaign_id, x.campaign_name, ampd.region_of(x.campaign_name) region,
  SUM(google_cost) cost, SUM(amazon_revenue) rev, SUM(brand_referral_bonus) brb, SUM(amazon_conversions) conv, SUM(clicks) clicks, SUM(impressions) impr,
  SUM(ntb_revenue) ntb_rev, COUNT(*) FILTER (WHERE has_attribution) attr_days, COUNT(DISTINCT date) days, SUM(google_cost) FILTER (WHERE NOT has_attribution) unattr_cost
  FROM ampd.campaign_daily_complete x JOIN {WIN_VALUES} ON x.date BETWEEN w.s AND w.e GROUP BY 1,2,3,4)
SELECT d.win, d.campaign_id, d.campaign_name, d.region, b.status, b.bidding_strategy_type strategy, b.budget,
  ROUND(cost::numeric,2) cost, ROUND(rev::numeric,2) rev, ROUND(brb::numeric,2) brb, conv, clicks, impr,
  CASE WHEN rev>0 THEN ROUND(((cost-brb)/rev)::numeric,3) END aacos, ROUND(ntb_rev::numeric,0) ntb_rev, attr_days, days, ROUND(unattr_cost::numeric,2) unattr_cost
FROM d LEFT JOIN b ON b.campaign_id=d.campaign_id WHERE cost>0 ORDER BY win, cost DESC""", show=0)

q('kw_class_weekly', """
SELECT (date_trunc('week', date))::date::text wk, is_amazon_keyword, ROUND(SUM(cost)::numeric,0) cost, ROUND(SUM(revenue)::numeric,0) rev, ROUND(SUM(brand_referral_bonus)::numeric,0) brb,
  SUM(clicks) clicks, SUM(impressions) impr, SUM(conversions) conv, COUNT(DISTINCT keyword) FILTER (WHERE impressions>0) kws_serving,
  CASE WHEN SUM(revenue)>0 THEN ROUND(((SUM(cost)-SUM(brand_referral_bonus))/SUM(revenue))::numeric,3) END aacos
FROM ampd.keyword_daily_v WHERE date BETWEEN '2026-06-29' AND '2026-09-01' GROUP BY 1,2 ORDER BY 1,2""", show=40)

q('kw_class_daily_recent', """
SELECT date::text d, is_amazon_keyword, ROUND(SUM(cost)::numeric,0) cost, SUM(impressions) impr, SUM(clicks) clicks, ROUND(SUM(revenue)::numeric,0) rev, COUNT(DISTINCT keyword) FILTER (WHERE impressions>0) kws
FROM ampd.keyword_daily_v WHERE date BETWEEN '2026-08-15' AND '2026-09-01' GROUP BY 1,2 ORDER BY 1,2""", show=40)

q('ampd_kw_top_stable', """
SELECT campaign_name, keyword, is_amazon_keyword amz, ROUND(SUM(cost)::numeric,0) cost, ROUND(SUM(revenue)::numeric,0) rev, ROUND(SUM(brand_referral_bonus)::numeric,0) brb, SUM(clicks) clicks, SUM(conversions) conv,
  CASE WHEN SUM(revenue)>0 THEN ROUND(((SUM(cost)-SUM(brand_referral_bonus))/SUM(revenue))::numeric,3) END aacos, ROUND((SUM(cost)/NULLIF(SUM(clicks),0))::numeric,2) cpc
FROM ampd.keyword_daily_v WHERE date BETWEEN '2026-07-21' AND '2026-08-19' GROUP BY 1,2,3 HAVING SUM(cost)>=150 ORDER BY cost DESC LIMIT 60""", show=60)

q('ampd_kw_top_l30', """
SELECT campaign_name, keyword, is_amazon_keyword amz, ROUND(SUM(cost)::numeric,0) cost, ROUND(SUM(revenue)::numeric,0) rev, ROUND(SUM(brand_referral_bonus)::numeric,0) brb, SUM(clicks) clicks, SUM(conversions) conv,
  CASE WHEN SUM(revenue)>0 THEN ROUND(((SUM(cost)-SUM(brand_referral_bonus))/SUM(revenue))::numeric,3) END aacos, ROUND((SUM(cost)/NULLIF(SUM(clicks),0))::numeric,2) cpc
FROM ampd.keyword_daily_v WHERE date BETWEEN '2026-08-04' AND '2026-09-01' GROUP BY 1,2,3 HAVING SUM(cost)>=150 ORDER BY cost DESC LIMIT 60""", show=60)

q('website_campaigns', f"""
WITH b AS (SELECT c.campaign_id, c.name, c.status, c.advertising_channel_type ch, c.advertising_channel_sub_type sub, c.bidding_strategy_type strat, cb.amount_micros/1e6 AS budget,
    (c.raw->'campaign'->'targetRoas'->>'targetRoas')::numeric troas, (c.raw->'campaign'->'maximizeConversionValue'->>'targetRoas')::numeric mcv_troas, (c.raw->'campaign'->'targetCpa'->>'targetCpaMicros')::numeric/1e6 tcpa
  FROM google_ads_tw.google_campaigns c LEFT JOIN google_ads_tw.google_campaign_budgets cb ON cb.resource_name=c.campaign_budget AND cb.customer_id=c.customer_id WHERE c.customer_id='7304176160'),
p AS (SELECT w.win, campaign_id, campaign_name, SUM(cost_micros)/1e6 spend, SUM(clicks) clicks, SUM(impressions) impr, SUM(conversions) conv, SUM(conversions_value) cv
  FROM google_ads_tw.google_performance_daily x JOIN {WIN_VALUES} ON x.report_date BETWEEN w.s AND w.e
  WHERE customer_id='7304176160' AND level='campaign' AND NOT (campaign_name ILIKE '[ampd]%%') AND NOT (campaign_name ~* '^(mec|sani)' OR campaign_name IN ('1','2','3','4','5')) GROUP BY 1,2,3),
nb AS (SELECT campaign_id, w.win,
  SUM(rev) FILTER (WHERE attribution_model_id='northbeam_custom' AND accounting_mode='accrual' AND attribution_window='7') nb_rev7,
  SUM(transactions) FILTER (WHERE attribution_model_id='northbeam_custom' AND accounting_mode='accrual' AND attribution_window='7') nb_txn7,
  SUM(rev) FILTER (WHERE attribution_model_id='northbeam_custom' AND accounting_mode='accrual' AND attribution_window='1') nb_rev1,
  SUM(rev) FILTER (WHERE attribution_model_id='northbeam_custom' AND accounting_mode='cash') nb_rev_cash,
  SUM(spend) FILTER (WHERE attribution_model_id='northbeam_custom' AND accounting_mode='accrual' AND attribution_window='7') nb_spend,
  SUM(visits) FILTER (WHERE attribution_model_id='northbeam_custom' AND accounting_mode='accrual' AND attribution_window='7') nb_visits,
  MAX(breakdown) nb_breakdown
  FROM northbeam.export_daily n JOIN {WIN_VALUES} ON n.day BETWEEN w.s AND w.e WHERE platform_norm='google' AND kind='' GROUP BY 1,2)
SELECT p.win, p.campaign_id, p.campaign_name, b.status, b.ch, b.sub, b.strat, b.budget, COALESCE(b.troas,b.mcv_troas) troas, b.tcpa,
  ROUND(spend::numeric,2) spend, clicks, impr, ROUND(conv::numeric,1) conv, ROUND(cv::numeric,2) conv_value, CASE WHEN spend>0 THEN ROUND((cv/spend)::numeric,2) END roas,
  ROUND(nb.nb_rev7::numeric,0) nb_rev7, nb.nb_txn7, ROUND(nb.nb_rev1::numeric,0) nb_rev1, ROUND(nb.nb_rev_cash::numeric,0) nb_rev_cash, ROUND(nb.nb_spend::numeric,0) nb_spend, nb.nb_visits, nb.nb_breakdown,
  CASE WHEN spend>0 THEN ROUND((nb.nb_rev7/spend)::numeric,2) END nb_roas7
FROM p LEFT JOIN b ON b.campaign_id=p.campaign_id LEFT JOIN nb ON nb.campaign_id=p.campaign_id AND nb.win=p.win WHERE spend>0 ORDER BY win, spend DESC""", show=0)

q('nb_google_platform', f"""
WITH a AS (SELECT campaign_id FROM google_ads_tw.google_campaigns WHERE customer_id='7304176160' AND name ILIKE '[ampd]%%')
SELECT w.win, CASE WHEN n.campaign_id IN (SELECT campaign_id FROM a) THEN 'ampd' ELSE 'website' END lane, n.breakdown, attribution_model_id model, attribution_window win_d, accounting_mode mode,
  ROUND(SUM(spend)::numeric,0) spend, ROUND(SUM(rev)::numeric,0) rev, SUM(transactions) txns, SUM(visits) visits
FROM northbeam.export_daily n JOIN {WIN_VALUES} ON n.day BETWEEN w.s AND w.e
WHERE platform_norm='google' AND kind='' AND attribution_model_id IN ('northbeam_custom','northbeam_custom__enh','last_touch') AND ((accounting_mode='accrual' AND attribution_window IN ('1','7','30')) OR accounting_mode='cash') AND w.win IN ('L30','P30')
GROUP BY 1,2,3,4,5,6 ORDER BY 1,2,3,4,5,6""", show=80)

q('nb_dtc_platforms', """
SELECT platform_norm, ROUND(SUM(spend)::numeric,0) spend, ROUND(SUM(rev)::numeric,0) rev, SUM(transactions) txns
FROM northbeam.export_daily WHERE day BETWEEN '2026-08-04' AND '2026-09-02' AND accounting_mode='accrual' AND attribution_model_id='northbeam_custom' AND attribution_window='7'
  AND platform_norm NOT IN ('amazon','excluded') GROUP BY 1 ORDER BY 2 DESC""", show=20)

q('search_terms_freshness', "SELECT customer_id, MAX(report_date) mx, MIN(report_date) mn, COUNT(*) n FROM google_ads_tw.google_search_terms WHERE report_date >= '2026-07-05' GROUP BY 1")

q('website_st_waste', """
WITH st AS (SELECT s.campaign_id, c.name campaign_name, s.search_term, SUM(s.cost_micros)/1e6 spend, SUM(clicks) clicks, SUM(conversions) conv, SUM(conversions_value) cv
  FROM google_ads_tw.google_search_terms s JOIN google_ads_tw.google_campaigns c ON c.campaign_id=s.campaign_id AND c.customer_id=s.customer_id
  WHERE s.customer_id='7304176160' AND s.report_date BETWEEN '2026-08-04' AND '2026-09-02' AND NOT (c.name ILIKE '[ampd]%') GROUP BY 1,2,3)
SELECT campaign_name, search_term, ROUND(spend::numeric,2) spend, clicks, ROUND(conv::numeric,1) conv, ROUND(cv::numeric,0) cv FROM st WHERE spend>=40 AND conv<0.5 ORDER BY spend DESC LIMIT 40""", show=40)

q('website_st_winners', """
WITH st AS (SELECT s.campaign_id, c.name campaign_name, s.search_term, SUM(s.cost_micros)/1e6 spend, SUM(clicks) clicks, SUM(conversions) conv, SUM(conversions_value) cv
  FROM google_ads_tw.google_search_terms s JOIN google_ads_tw.google_campaigns c ON c.campaign_id=s.campaign_id AND c.customer_id=s.customer_id
  WHERE s.customer_id='7304176160' AND s.report_date BETWEEN '2026-08-04' AND '2026-09-02' AND NOT (c.name ILIKE '[ampd]%') GROUP BY 1,2,3),
kw AS (SELECT DISTINCT lower(text) t FROM google_ads_tw.google_keywords WHERE customer_id='7304176160' AND match_type='EXACT' AND NOT negative AND status='ENABLED')
SELECT campaign_name, search_term, ROUND(spend::numeric,2) spend, clicks, ROUND(conv::numeric,1) conv, ROUND(cv::numeric,0) cv, ROUND((cv/NULLIF(spend,0))::numeric,2) roas,
  EXISTS (SELECT 1 FROM kw WHERE kw.t=lower(st.search_term)) has_exact
FROM st WHERE conv>=2 AND cv/NULLIF(spend,0)>=2.5 ORDER BY cv DESC LIMIT 40""", show=40)

q('ampd_st_top', """
SELECT c.name campaign_name, s.search_term, ROUND(SUM(s.cost_micros)/1e6::numeric,2) spend, SUM(clicks) clicks
FROM google_ads_tw.google_search_terms s JOIN google_ads_tw.google_campaigns c ON c.campaign_id=s.campaign_id AND c.customer_id=s.customer_id
WHERE s.customer_id='7304176160' AND s.report_date BETWEEN '2026-08-04' AND '2026-09-02' AND c.name ILIKE '[ampd]%' GROUP BY 1,2 HAVING SUM(s.cost_micros)/1e6>=60 ORDER BY spend DESC LIMIT 60""", show=60)

q('change_events_summary', """
SELECT customer_id, user_email, change_resource_type, COUNT(*) n, MIN(change_date_time)::date first, MAX(change_date_time)::date last
FROM google_ads_tw.google_change_events WHERE change_date_time >= '2026-08-04' GROUP BY 1,2,3 ORDER BY 1,4 DESC""", show=40)

q('change_events_detail', """
SELECT customer_id, change_date_time::date d, user_email, change_resource_type ty, changed_fields::text cf,
  COALESCE(new_resource->'campaign'->>'name', new_resource->'campaignBudget'->>'name', new_resource->'adGroup'->>'name', old_resource->'campaign'->>'name') nm,
  LEFT(old_resource::text,160) oldv, LEFT(new_resource::text,160) newv
FROM google_ads_tw.google_change_events WHERE change_date_time >= '2026-08-04' AND change_resource_type IN ('CAMPAIGN','CAMPAIGN_BUDGET') ORDER BY change_date_time""", show=0)

q('ampd_change_log', """
SELECT detected_at::date d, campaign_name, change_type, entity, old_value, new_value, source, source_detail, aacos_at_change
FROM ampd.change_log WHERE detected_at >= '2026-08-04' ORDER BY detected_at""", show=0)

for acct, nm, pm_acct in (('3818885747','beckham','6584ada2c23f9400099c4577'),('5590642315','saferest','65c508387f3d58000863f22a'),('8819867229','hotelsheets','65e5eb75ce951e00084c7645'),('6757430621','dtc_beckham',None),('2425709513','walmart',None)):
    q(f'{nm}_campaigns', f"""
WITH b AS (SELECT c.campaign_id, c.name, c.status, c.advertising_channel_type ch, c.bidding_strategy_type strat, cb.amount_micros/1e6 AS budget,
    (c.raw->'campaign'->'maximizeConversions'->>'targetCpaMicros')::numeric/1e6 mc_tcpa, (c.raw->'campaign'->'targetRoas'->>'targetRoas')::numeric troas
  FROM google_ads_tw.google_campaigns c LEFT JOIN google_ads_tw.google_campaign_budgets cb ON cb.resource_name=c.campaign_budget AND cb.customer_id=c.customer_id WHERE c.customer_id='{acct}'),
p AS (SELECT w.win, campaign_id, campaign_name, SUM(cost_micros)/1e6 spend, SUM(clicks) clicks, SUM(impressions) impr, SUM(conversions) conv, SUM(conversions_value) cv
  FROM google_ads_tw.google_performance_daily x JOIN {WIN_VALUES} ON x.report_date BETWEEN w.s AND w.e WHERE customer_id='{acct}' AND level='campaign' GROUP BY 1,2,3),
pm AS (SELECT platform_campaign_id, MAX(status) pm_status, BOOL_OR(imported) imported, MAX(product_asin) asin, BOOL_OR(asin_mismatch) mism FROM pixelme.campaign_product WHERE provider_type ILIKE '%%google%%' GROUP BY 1)
SELECT p.win, p.campaign_id, p.campaign_name, b.status, b.ch, b.strat, b.budget, b.mc_tcpa, b.troas, ROUND(spend::numeric,2) spend, clicks, impr, ROUND(conv::numeric,1) conv, ROUND(cv::numeric,0) conv_value,
  ROUND((spend/NULLIF(conv,0))::numeric,2) cpa, pm.pm_status, pm.imported, pm.asin, pm.mism
FROM p LEFT JOIN b ON b.campaign_id=p.campaign_id LEFT JOIN pm ON pm.platform_campaign_id=p.campaign_id WHERE spend>0 ORDER BY win, spend DESC""", show=0)
    if pm_acct:
        q(f'{nm}_pixelme_products', f"""
SELECT w.win, d.product_external_id asin, LEFT(MAX(pr.name),50) name, ROUND(SUM(ad_cost)::numeric,0) ad_cost, ROUND(SUM(revenue)::numeric,0) rev, SUM(purchases) purchases, SUM(clicks) clicks, SUM(converted_clicks) conv_clicks,
  ROUND(SUM(total_revenue)::numeric,0) total_rev, SUM(total_purchases) total_purch, CASE WHEN SUM(ad_cost)>0 THEN ROUND((SUM(revenue)/SUM(ad_cost))::numeric,2) END roas, CASE WHEN SUM(revenue)>0 THEN ROUND((SUM(ad_cost)/SUM(revenue))::numeric,3) END acos,
  COUNT(DISTINCT date) days
FROM pixelme.product_daily d JOIN {WIN_VALUES} ON d.date BETWEEN w.s AND w.e LEFT JOIN pixelme.products pr ON pr.external_id=d.product_external_id AND pr.account_id=d.account_id
WHERE d.account_id='{pm_acct}' GROUP BY 1,2 HAVING SUM(ad_cost)>0 OR SUM(revenue)>0 ORDER BY win, ad_cost DESC""", show=0)

q('pixelme_campaign_status', """
SELECT a.name acct, cp.status, cp.imported, COUNT(*) n, ROUND(SUM(0)::numeric,0) z FROM pixelme.campaign_product cp JOIN pixelme.accounts a ON a.account_id=cp.account_id GROUP BY 1,2,3 ORDER BY 1,2""", show=30)
q('pixelme_daily', """
SELECT a.name acct, date::text d, ROUND(SUM(ad_cost)::numeric,0) cost, ROUND(SUM(revenue)::numeric,0) rev, SUM(purchases) purch
FROM pixelme.product_daily d JOIN pixelme.accounts a ON a.account_id=d.account_id WHERE date BETWEEN '2026-07-05' AND '2026-09-02' GROUP BY 1,2 ORDER BY 1,2""", show=0)

q('recs', """
SELECT customer_id, type, COUNT(*) n, COUNT(DISTINCT campaign_id) camps,
  ROUND(SUM((impact->'potentialMetrics'->>'costMicros')::numeric - (impact->'baseMetrics'->>'costMicros')::numeric)/1e6,0) d_cost,
  ROUND(SUM((impact->'potentialMetrics'->>'conversionsValue')::numeric - (impact->'baseMetrics'->>'conversionsValue')::numeric),0) d_value,
  ROUND(SUM((impact->'potentialMetrics'->>'conversions')::numeric - (impact->'baseMetrics'->>'conversions')::numeric),1) d_conv
FROM google_ads_tw.google_recommendations WHERE NOT dismissed GROUP BY 1,2 ORDER BY 1, n DESC""", show=60)

q('budget_util_l7', """
WITH s AS (SELECT customer_id, campaign_id, campaign_name, SUM(cost_micros)/1e6/7 avg_daily FROM google_ads_tw.google_performance_daily WHERE level='campaign' AND report_date BETWEEN '2026-08-27' AND '2026-09-02' GROUP BY 1,2,3)
SELECT s.customer_id, s.campaign_id, s.campaign_name, c.status, cb.amount_micros/1e6 budget, ROUND(avg_daily::numeric,2) avg_daily, ROUND((avg_daily/NULLIF(cb.amount_micros/1e6,0))::numeric,2) util
FROM s JOIN google_ads_tw.google_campaigns c ON c.campaign_id=s.campaign_id AND c.customer_id=s.customer_id LEFT JOIN google_ads_tw.google_campaign_budgets cb ON cb.resource_name=c.campaign_budget AND cb.customer_id=c.customer_id
WHERE c.status='ENABLED' AND avg_daily>0 ORDER BY util DESC NULLS LAST""", show=0)

q('post_0826_early', """
SELECT campaign_id, campaign_name,
  ROUND(SUM(google_cost) FILTER (WHERE date BETWEEN '2026-08-12' AND '2026-08-25')::numeric,0) cost_pre, ROUND(SUM(amazon_revenue) FILTER (WHERE date BETWEEN '2026-08-12' AND '2026-08-25')::numeric,0) rev_pre,
  CASE WHEN SUM(amazon_revenue) FILTER (WHERE date BETWEEN '2026-08-12' AND '2026-08-25')>0 THEN ROUND(((SUM(google_cost)-SUM(brand_referral_bonus)) FILTER (WHERE date BETWEEN '2026-08-12' AND '2026-08-25') / SUM(amazon_revenue) FILTER (WHERE date BETWEEN '2026-08-12' AND '2026-08-25'))::numeric,3) END aacos_pre,
  ROUND(SUM(google_cost) FILTER (WHERE date BETWEEN '2026-08-27' AND '2026-09-01')::numeric,0) cost_post, ROUND(SUM(amazon_revenue) FILTER (WHERE date BETWEEN '2026-08-27' AND '2026-09-01')::numeric,0) rev_post,
  CASE WHEN SUM(amazon_revenue) FILTER (WHERE date BETWEEN '2026-08-27' AND '2026-09-01')>0 THEN ROUND(((SUM(google_cost)-SUM(brand_referral_bonus)) FILTER (WHERE date BETWEEN '2026-08-27' AND '2026-09-01') / SUM(amazon_revenue) FILTER (WHERE date BETWEEN '2026-08-27' AND '2026-09-01'))::numeric,3) END aacos_post
FROM ampd.campaign_daily_complete WHERE campaign_id IN ('23859376713','23864624639','21510061819','23576925357','24139372252','22821667433','23676906151','23350268344','22452315321','21083360054','19876543583','21839192355','23451576927','23461114981','24182840078','24177022254','24176957259','21736166343','24128873457','24139407325','24139378924')
GROUP BY 1,2 ORDER BY cost_post DESC NULLS LAST""", show=30)

q('unattributed_check', """
SELECT campaign_id, campaign_name, MIN(date) mn, MAX(date) mx, ROUND(SUM(google_cost)::numeric,0) cost, ROUND(SUM(amazon_revenue)::numeric,0) rev, COUNT(*) FILTER (WHERE has_attribution) attr_days, COUNT(*) days
FROM ampd.campaign_daily_complete WHERE date BETWEEN '2026-08-04' AND '2026-09-01' AND campaign_id IN ('23350268344','21839192355') GROUP BY 1,2 ORDER BY 1,3""", show=20)

q('ampd_region_windows', f"""
SELECT w.win, ampd.region_of(campaign_name) region, ROUND(SUM(google_cost)::numeric,0) cost, ROUND(SUM(amazon_revenue)::numeric,0) rev, ROUND(SUM(brand_referral_bonus)::numeric,0) brb, SUM(amazon_conversions) conv,
  CASE WHEN SUM(amazon_revenue)>0 THEN ROUND(((SUM(google_cost)-SUM(brand_referral_bonus))/SUM(amazon_revenue))::numeric,3) END aacos, ROUND(SUM(google_cost) FILTER (WHERE NOT has_attribution)::numeric,0) unattr
FROM ampd.campaign_daily_complete x JOIN {WIN_VALUES} ON x.date BETWEEN w.s AND w.e GROUP BY 1,2 ORDER BY 1,2""", show=20)
print("\nDONE")
