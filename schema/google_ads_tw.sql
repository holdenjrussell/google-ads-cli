--
-- PostgreSQL database dump
--

\restrict DoFWxsXlJwEHaZvVcFMcxGDgwH57AVhAF48yAP9zDUIsy4YedVZ9SraS9FkkUq6

-- Dumped from database version 17.9 (Homebrew)
-- Dumped by pg_dump version 17.9 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: google_ads_tw; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA google_ads_tw;


--
-- Name: google_campaign_type_label(text); Type: FUNCTION; Schema: google_ads_tw; Owner: -
--

CREATE FUNCTION google_ads_tw.google_campaign_type_label(campaign_type text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
            SELECT CASE coalesce(campaign_type, 'unknown')
                WHEN 'branded_search' THEN 'Branded Search'
                WHEN 'generic_search' THEN 'Generic Search'
                WHEN 'search' THEN 'Search'
                WHEN 'shopping' THEN 'Shopping'
                WHEN 'pmax' THEN 'Performance Max'
                WHEN 'youtube_video' THEN 'YouTube / Video'
                WHEN 'demand_gen' THEN 'Demand Gen'
                WHEN 'display' THEN 'Display'
                ELSE 'Unknown'
            END
        $$;


--
-- Name: google_infer_campaign_type(text); Type: FUNCTION; Schema: google_ads_tw; Owner: -
--

CREATE FUNCTION google_ads_tw.google_infer_campaign_type(name text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
            SELECT CASE
                WHEN coalesce(name, '') = '' THEN 'unknown'
                WHEN regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%pmax%'
                  OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%performancemax%'
                  OR lower(name) LIKE '%performance max%' THEN 'pmax'
                WHEN lower(name) LIKE '%shopping%'
                  OR lower(name) LIKE '%standard shop%'
                  OR lower(name) LIKE '%product shopping%' THEN 'shopping'
                WHEN lower(name) LIKE '%youtube%'
                  OR lower(name) LIKE '%video%' THEN 'youtube_video'
                WHEN lower(name) LIKE '%demand gen%'
                  OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%demandgen%'
                  OR lower(name) LIKE '%discovery%' THEN 'demand_gen'
                WHEN lower(name) LIKE '%display%'
                  OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%gdn%' THEN 'display'
                WHEN lower(name) LIKE '%search%'
                  OR lower(name) LIKE '%rsa%'
                  OR lower(name) LIKE '%brand%'
                  OR lower(name) LIKE '%bofu%'
                  OR lower(name) LIKE '%generic%' THEN
                    CASE
                        WHEN lower(name) LIKE '%non-brand%'
                          OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%nonbrand%'
                          OR regexp_replace(lower(name), '[^a-z0-9]+', '', 'g') LIKE '%nonbranded%'
                          OR lower(name) LIKE '%generic%' THEN 'generic_search'
                        WHEN lower(name) LIKE '%brand%'
                          OR lower(name) LIKE '%bofu%' THEN 'branded_search'
                        ELSE 'search'
                    END
                ELSE 'unknown'
            END
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: google_attribution_level_daily_imports; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_attribution_level_daily_imports (
    report_date date,
    level text,
    channel text,
    campaign_id text,
    campaign_name text,
    adset_id text,
    adset_name text,
    ad_id text,
    ad_name text,
    shop_domain text,
    preset_name text,
    attribution_model text,
    attribution_window text,
    accounting_mode text,
    subscription_filter text,
    ad_spend double precision,
    combined_net_revenue double precision,
    pixel_purchases double precision,
    pixel_new_customer_purchases double precision,
    impressions double precision,
    clicks double precision,
    pixel_sessions double precision,
    pixel_new_visitors double precision,
    pixel_new_customer_revenue double precision,
    pixel_unique_add_to_carts double precision,
    outbound_clicks double precision,
    source_row_count integer,
    hour_count integer,
    rolled_up_at timestamp with time zone
);


--
-- Name: google_tw_attribution_daily; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_tw_attribution_daily AS
 SELECT report_date,
        CASE
            WHEN (level = 'adset'::text) THEN 'ad_group'::text
            ELSE level
        END AS level,
    channel,
    campaign_id,
    campaign_name,
    adset_id AS ad_group_id,
    adset_name AS ad_group_name,
    ad_id,
    ad_name,
    sum(ad_spend) AS tw_spend,
    sum(combined_net_revenue) AS tw_revenue,
    sum(pixel_purchases) AS tw_purchases,
    sum(pixel_new_customer_purchases) AS tw_new_customer_orders,
        CASE
            WHEN (sum(ad_spend) > (0)::double precision) THEN (sum(combined_net_revenue) / sum(ad_spend))
            ELSE NULL::double precision
        END AS tw_roas,
        CASE
            WHEN (sum(pixel_new_customer_purchases) > (0)::double precision) THEN (sum(ad_spend) / sum(pixel_new_customer_purchases))
            ELSE NULL::double precision
        END AS tw_ncpa,
        CASE
            WHEN (sum(pixel_purchases) > (0)::double precision) THEN (sum(ad_spend) / sum(pixel_purchases))
            ELSE NULL::double precision
        END AS tw_cpa,
    shop_domain,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    sum(ad_spend) AS ad_spend,
    sum(pixel_new_customer_purchases) AS pixel_new_customer_purchases,
        CASE
            WHEN (sum(pixel_new_customer_purchases) > (0)::double precision) THEN (sum(ad_spend) / sum(pixel_new_customer_purchases))
            ELSE NULL::double precision
        END AS pixel_new_customer_cpa,
    sum(pixel_purchases) AS pixel_purchases,
        CASE
            WHEN (sum(pixel_purchases) > (0)::double precision) THEN (sum(ad_spend) / sum(pixel_purchases))
            ELSE NULL::double precision
        END AS pixel_cpa,
        CASE
            WHEN (sum(pixel_purchases) > (0)::double precision) THEN (sum(pixel_new_customer_purchases) / sum(pixel_purchases))
            ELSE NULL::double precision
        END AS pixel_new_customer_purchases_percent,
    (sum(impressions))::bigint AS impressions,
        CASE
            WHEN (sum(impressions) > (0)::double precision) THEN ((sum(ad_spend) / sum(impressions)) * (1000)::double precision)
            ELSE NULL::double precision
        END AS cpm,
        CASE
            WHEN (sum(impressions) > (0)::double precision) THEN (sum(outbound_clicks) / sum(impressions))
            ELSE NULL::double precision
        END AS outbound_ctr,
    (sum(clicks))::bigint AS clicks,
    sum(pixel_sessions) AS pixel_sessions,
        CASE
            WHEN (sum(pixel_sessions) > (0)::double precision) THEN (sum(ad_spend) / sum(pixel_sessions))
            ELSE NULL::double precision
        END AS pixel_cost_per_visitors,
    sum(pixel_new_visitors) AS pixel_new_visitors,
        CASE
            WHEN (sum(pixel_new_visitors) > (0)::double precision) THEN (sum(ad_spend) / sum(pixel_new_visitors))
            ELSE NULL::double precision
        END AS pixel_cost_per_new_visitors,
        CASE
            WHEN (sum(pixel_sessions) > (0)::double precision) THEN (sum(pixel_new_visitors) / sum(pixel_sessions))
            ELSE NULL::double precision
        END AS pixel_new_visitor_percent,
        CASE
            WHEN (sum(pixel_new_customer_purchases) > (0)::double precision) THEN (sum(pixel_new_customer_revenue) / sum(pixel_new_customer_purchases))
            ELSE NULL::double precision
        END AS pixel_new_customer_aov,
        CASE
            WHEN (sum(pixel_purchases) > (0)::double precision) THEN (sum(combined_net_revenue) / sum(pixel_purchases))
            ELSE NULL::double precision
        END AS pixel_aov,
        CASE
            WHEN (sum(pixel_sessions) > (0)::double precision) THEN (sum(pixel_new_customer_purchases) / sum(pixel_sessions))
            ELSE NULL::double precision
        END AS pixel_new_customer_conversion_rate,
        CASE
            WHEN (sum(pixel_sessions) > (0)::double precision) THEN (sum(pixel_purchases) / sum(pixel_sessions))
            ELSE NULL::double precision
        END AS pixel_conversion_rate,
    sum(combined_net_revenue) AS combined_net_revenue,
        CASE
            WHEN (sum(ad_spend) > (0)::double precision) THEN (sum(combined_net_revenue) / sum(ad_spend))
            ELSE NULL::double precision
        END AS pixel_roas,
        CASE
            WHEN (sum(ad_spend) > (0)::double precision) THEN (sum(pixel_new_customer_revenue) / sum(ad_spend))
            ELSE NULL::double precision
        END AS pixel_new_customers_roas,
    sum(pixel_unique_add_to_carts) AS pixel_unique_add_to_carts,
        CASE
            WHEN (sum(impressions) > (0)::double precision) THEN (sum(clicks) / sum(impressions))
            ELSE NULL::double precision
        END AS ctr,
        CASE
            WHEN (sum(clicks) > (0)::double precision) THEN (sum(ad_spend) / sum(clicks))
            ELSE NULL::double precision
        END AS cpc,
    sum(outbound_clicks) AS outbound_clicks,
    sum(pixel_new_customer_revenue) AS pixel_new_customer_revenue,
    (sum(source_row_count))::integer AS source_row_count,
    max(hour_count) AS hour_count,
    max(rolled_up_at) AS rolled_up_at,
    google_ads_tw.google_infer_campaign_type(campaign_name) AS campaign_type,
    google_ads_tw.google_campaign_type_label(google_ads_tw.google_infer_campaign_type(campaign_name)) AS campaign_type_label
   FROM google_ads_tw.google_attribution_level_daily_imports
  WHERE (channel = ANY (ARRAY['Google'::text, 'Google Ads'::text]))
  GROUP BY report_date,
        CASE
            WHEN (level = 'adset'::text) THEN 'ad_group'::text
            ELSE level
        END, channel, campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name, shop_domain, preset_name, attribution_model, attribution_window, accounting_mode, subscription_filter;


--
-- Name: google_account_daily_performance; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_account_daily_performance AS
 SELECT NULL::text AS customer_id,
    report_date AS date_start,
    report_date AS date_stop,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    sum(tw_spend) AS spend,
    (sum(impressions))::bigint AS impressions,
    (sum(clicks))::bigint AS clicks,
    sum(outbound_clicks) AS outbound_clicks,
        CASE
            WHEN (sum(impressions) > (0)::numeric) THEN (sum(clicks) / sum(impressions))
            ELSE NULL::numeric
        END AS ctr,
        CASE
            WHEN (sum(clicks) > (0)::numeric) THEN (sum(tw_spend) / (sum(clicks))::double precision)
            ELSE NULL::double precision
        END AS cpc,
        CASE
            WHEN (sum(impressions) > (0)::numeric) THEN ((sum(tw_spend) / (sum(impressions))::double precision) * (1000)::double precision)
            ELSE NULL::double precision
        END AS cpm,
    sum(tw_purchases) AS purchases,
    sum(tw_new_customer_orders) AS new_customer_orders,
    sum(tw_revenue) AS revenue,
        CASE
            WHEN (sum(tw_spend) > (0)::double precision) THEN (sum(tw_revenue) / sum(tw_spend))
            ELSE NULL::double precision
        END AS roas,
        CASE
            WHEN (sum(tw_purchases) > (0)::double precision) THEN (sum(tw_spend) / sum(tw_purchases))
            ELSE NULL::double precision
        END AS cpa,
        CASE
            WHEN (sum(tw_new_customer_orders) > (0)::double precision) THEN (sum(tw_spend) / sum(tw_new_customer_orders))
            ELSE NULL::double precision
        END AS ncpa,
    max(rolled_up_at) AS fetched_at,
    'triple_whale_daily'::text AS source,
    'all'::text AS campaign_type,
    'All Campaign Types'::text AS campaign_type_label
   FROM google_ads_tw.google_tw_attribution_daily
  WHERE (level = 'campaign'::text)
  GROUP BY report_date, shop_domain, channel, preset_name, attribution_model, attribution_window, accounting_mode, subscription_filter;


--
-- Name: google_ad_daily_performance; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_ad_daily_performance AS
 SELECT NULL::text AS customer_id,
    report_date AS date_start,
    report_date AS date_stop,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    ad_id,
    ad_name,
    tw_spend AS spend,
    impressions,
    clicks,
    outbound_clicks,
    ctr,
    cpc,
    cpm,
    tw_purchases AS purchases,
    tw_new_customer_orders AS new_customer_orders,
    tw_revenue AS revenue,
    tw_roas AS roas,
    tw_cpa AS cpa,
    tw_ncpa AS ncpa,
    rolled_up_at AS fetched_at,
    'triple_whale_daily'::text AS source,
    campaign_type,
    campaign_type_label
   FROM google_ads_tw.google_tw_attribution_daily
  WHERE (level = 'ad'::text);


--
-- Name: google_ad_group_daily_performance; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_ad_group_daily_performance AS
 SELECT NULL::text AS customer_id,
    report_date AS date_start,
    report_date AS date_stop,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    tw_spend AS spend,
    impressions,
    clicks,
    outbound_clicks,
    ctr,
    cpc,
    cpm,
    tw_purchases AS purchases,
    tw_new_customer_orders AS new_customer_orders,
    tw_revenue AS revenue,
    tw_roas AS roas,
    tw_cpa AS cpa,
    tw_ncpa AS ncpa,
    rolled_up_at AS fetched_at,
    'triple_whale_daily'::text AS source,
    campaign_type,
    campaign_type_label
   FROM google_ads_tw.google_tw_attribution_daily
  WHERE (level = 'ad_group'::text);


--
-- Name: google_ad_groups; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_ad_groups (
    customer_id text NOT NULL,
    ad_group_id text NOT NULL,
    campaign_id text,
    resource_name text,
    name text,
    status text,
    type text,
    cpc_bid_micros bigint,
    target_cpa_micros bigint,
    target_roas numeric,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_attribution_hourly_imports; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_attribution_hourly_imports (
    report_date date,
    report_hour timestamp with time zone,
    shop_domain text,
    channel text,
    preset_name text,
    attribution_model text,
    attribution_window text,
    accounting_mode text,
    subscription_filter text,
    campaign_id text,
    campaign_name text,
    adset_id text,
    adset_name text,
    ad_id text,
    ad_name text,
    ad_spend double precision,
    combined_net_revenue double precision,
    pixel_purchases double precision,
    pixel_new_customer_purchases double precision,
    pixel_new_customer_cpa double precision,
    pixel_cpa double precision,
    pixel_new_customer_purchases_percent double precision,
    impressions double precision,
    cpm double precision,
    outbound_ctr double precision,
    clicks double precision,
    pixel_sessions double precision,
    pixel_cost_per_visitors double precision,
    pixel_new_visitors double precision,
    pixel_cost_per_new_visitors double precision,
    pixel_new_visitor_percent double precision,
    pixel_new_customer_aov double precision,
    pixel_aov double precision,
    pixel_new_customer_conversion_rate double precision,
    pixel_conversion_rate double precision,
    pixel_roas double precision,
    pixel_new_customers_roas double precision,
    pixel_unique_add_to_carts double precision,
    ctr double precision,
    cpc double precision,
    outbound_clicks double precision,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_file text,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_tw_attribution_hourly; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_tw_attribution_hourly AS
 SELECT report_date,
    report_hour,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    campaign_id,
    campaign_name,
    adset_id AS ad_group_id,
    adset_name AS ad_group_name,
    ad_id,
    ad_name,
    ad_spend AS tw_spend,
    combined_net_revenue AS tw_revenue,
    pixel_purchases AS tw_purchases,
    pixel_new_customer_purchases AS tw_new_customer_orders,
        CASE
            WHEN (ad_spend > (0)::double precision) THEN (combined_net_revenue / ad_spend)
            ELSE NULL::double precision
        END AS tw_roas,
        CASE
            WHEN (pixel_new_customer_purchases > (0)::double precision) THEN (ad_spend / pixel_new_customer_purchases)
            ELSE NULL::double precision
        END AS tw_ncpa,
        CASE
            WHEN (pixel_purchases > (0)::double precision) THEN (ad_spend / pixel_purchases)
            ELSE NULL::double precision
        END AS tw_cpa,
    ad_spend,
    pixel_new_customer_purchases,
    pixel_new_customer_cpa,
    pixel_purchases,
    pixel_cpa,
    pixel_new_customer_purchases_percent,
    impressions,
    cpm,
    outbound_ctr,
    clicks,
    pixel_sessions,
    pixel_cost_per_visitors,
    pixel_new_visitors,
    pixel_cost_per_new_visitors,
    pixel_new_visitor_percent,
    pixel_new_customer_aov,
    pixel_aov,
    pixel_new_customer_conversion_rate,
    pixel_conversion_rate,
    combined_net_revenue,
    pixel_roas,
    pixel_new_customers_roas,
    pixel_unique_add_to_carts,
    ctr,
    cpc,
    outbound_clicks,
    raw,
    source_file,
    fetched_at,
    google_ads_tw.google_infer_campaign_type(campaign_name) AS campaign_type,
    google_ads_tw.google_campaign_type_label(google_ads_tw.google_infer_campaign_type(campaign_name)) AS campaign_type_label
   FROM google_ads_tw.google_attribution_hourly_imports
  WHERE (channel = ANY (ARRAY['Google'::text, 'Google Ads'::text]));


--
-- Name: google_ad_hourly_performance; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_ad_hourly_performance AS
 SELECT NULL::text AS customer_id,
    report_date AS date_start,
    report_date AS date_stop,
    report_hour AS period_start,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    ad_id,
    ad_name,
    tw_spend AS spend,
    impressions,
    clicks,
    outbound_clicks,
    ctr,
    cpc,
    cpm,
    tw_purchases AS purchases,
    tw_new_customer_orders AS new_customer_orders,
    tw_revenue AS revenue,
    tw_roas AS roas,
    tw_cpa AS cpa,
    tw_ncpa AS ncpa,
    fetched_at,
    'triple_whale_hourly'::text AS source,
    campaign_type,
    campaign_type_label
   FROM google_ads_tw.google_tw_attribution_hourly;


--
-- Name: google_ads; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_ads (
    customer_id text NOT NULL,
    ad_group_id text DEFAULT ''::text NOT NULL,
    ad_id text NOT NULL,
    campaign_id text,
    resource_name text,
    name text,
    status text,
    ad_type text,
    final_urls jsonb DEFAULT '[]'::jsonb NOT NULL,
    display_url text,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_ads_fields; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_ads_fields (
    api_version text NOT NULL,
    name text NOT NULL,
    category text,
    data_type text,
    type_url text,
    selectable boolean,
    filterable boolean,
    sortable boolean,
    repeated boolean,
    selectable_with jsonb DEFAULT '[]'::jsonb NOT NULL,
    attribute_resources jsonb DEFAULT '[]'::jsonb NOT NULL,
    metrics jsonb DEFAULT '[]'::jsonb NOT NULL,
    segments jsonb DEFAULT '[]'::jsonb NOT NULL,
    enum_values jsonb DEFAULT '[]'::jsonb NOT NULL,
    resource_name text,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_api_catalog_sources; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_api_catalog_sources (
    source_name text NOT NULL,
    source_url text NOT NULL,
    source_ref text,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_api_methods; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_api_methods (
    api_version text NOT NULL,
    service_name text NOT NULL,
    method_name text NOT NULL,
    operation_kind text,
    rest_path text,
    service_file text,
    source_name text,
    source_ref text,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_api_services; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_api_services (
    api_version text NOT NULL,
    service_name text NOT NULL,
    service_file text,
    methods jsonb DEFAULT '[]'::jsonb NOT NULL,
    operations jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_name text,
    source_ref text,
    raw_hash text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_asset_groups; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_asset_groups (
    customer_id text NOT NULL,
    asset_group_id text NOT NULL,
    campaign_id text,
    resource_name text,
    name text,
    status text,
    final_urls jsonb DEFAULT '[]'::jsonb NOT NULL,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_assets; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_assets (
    customer_id text NOT NULL,
    asset_id text NOT NULL,
    resource_name text,
    name text,
    type text,
    source text,
    policy_summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_backfill_chunks; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_backfill_chunks (
    customer_id text NOT NULL,
    surface text NOT NULL,
    since_date date NOT NULL,
    until_date date NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    rows_fetched integer DEFAULT 0 NOT NULL,
    rows_written integer DEFAULT 0 NOT NULL,
    errors integer DEFAULT 0 NOT NULL,
    last_run_id text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_campaign_budgets; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_campaign_budgets (
    customer_id text NOT NULL,
    budget_id text NOT NULL,
    resource_name text,
    name text,
    status text,
    amount_micros bigint,
    delivery_method text,
    explicitly_shared boolean,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_campaign_daily_performance; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_campaign_daily_performance AS
 SELECT NULL::text AS customer_id,
    report_date AS date_start,
    report_date AS date_stop,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    campaign_id,
    campaign_name,
    tw_spend AS spend,
    impressions,
    clicks,
    outbound_clicks,
    ctr,
    cpc,
    cpm,
    tw_purchases AS purchases,
    tw_new_customer_orders AS new_customer_orders,
    tw_revenue AS revenue,
    tw_roas AS roas,
    tw_cpa AS cpa,
    tw_ncpa AS ncpa,
    rolled_up_at AS fetched_at,
    'triple_whale_daily'::text AS source,
    campaign_type,
    campaign_type_label
   FROM google_ads_tw.google_tw_attribution_daily
  WHERE (level = 'campaign'::text);


--
-- Name: google_campaign_type_daily_performance; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_campaign_type_daily_performance AS
 SELECT NULL::text AS customer_id,
    report_date AS date_start,
    report_date AS date_stop,
    shop_domain,
    channel,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    campaign_type,
    campaign_type_label,
    sum(tw_spend) AS spend,
    (sum(impressions))::bigint AS impressions,
    (sum(clicks))::bigint AS clicks,
    sum(outbound_clicks) AS outbound_clicks,
        CASE
            WHEN (sum(impressions) > (0)::numeric) THEN (sum(clicks) / sum(impressions))
            ELSE NULL::numeric
        END AS ctr,
        CASE
            WHEN (sum(clicks) > (0)::numeric) THEN (sum(tw_spend) / (sum(clicks))::double precision)
            ELSE NULL::double precision
        END AS cpc,
        CASE
            WHEN (sum(impressions) > (0)::numeric) THEN ((sum(tw_spend) / (sum(impressions))::double precision) * (1000)::double precision)
            ELSE NULL::double precision
        END AS cpm,
    sum(tw_purchases) AS purchases,
    sum(tw_new_customer_orders) AS new_customer_orders,
    sum(tw_revenue) AS revenue,
        CASE
            WHEN (sum(tw_spend) > (0)::double precision) THEN (sum(tw_revenue) / sum(tw_spend))
            ELSE NULL::double precision
        END AS roas,
        CASE
            WHEN (sum(tw_purchases) > (0)::double precision) THEN (sum(tw_spend) / sum(tw_purchases))
            ELSE NULL::double precision
        END AS cpa,
        CASE
            WHEN (sum(tw_new_customer_orders) > (0)::double precision) THEN (sum(tw_spend) / sum(tw_new_customer_orders))
            ELSE NULL::double precision
        END AS ncpa,
    max(rolled_up_at) AS fetched_at,
    'triple_whale_daily'::text AS source
   FROM google_ads_tw.google_tw_attribution_daily
  WHERE (level = 'campaign'::text)
  GROUP BY report_date, shop_domain, channel, preset_name, attribution_model, attribution_window, accounting_mode, subscription_filter, campaign_type, campaign_type_label;


--
-- Name: google_campaigns; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_campaigns (
    customer_id text NOT NULL,
    campaign_id text NOT NULL,
    resource_name text,
    name text,
    status text,
    serving_status text,
    advertising_channel_type text,
    advertising_channel_sub_type text,
    campaign_budget text,
    bidding_strategy_type text,
    start_date date,
    end_date date,
    optimization_score numeric,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_change_events; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_change_events (
    customer_id text NOT NULL,
    change_event_id text NOT NULL,
    change_date_time timestamp with time zone,
    user_email text,
    resource_type text,
    change_resource_type text,
    changed_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    old_resource jsonb DEFAULT '{}'::jsonb NOT NULL,
    new_resource jsonb DEFAULT '{}'::jsonb NOT NULL,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_conversion_actions; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_conversion_actions (
    customer_id text NOT NULL,
    conversion_action_id text NOT NULL,
    resource_name text,
    name text,
    status text,
    type text,
    category text,
    include_in_conversions_metric boolean,
    value_settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_core_generic; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_core_generic (
    customer_id text NOT NULL,
    surface text NOT NULL,
    entity_key text NOT NULL,
    query_name text NOT NULL,
    source_resource text NOT NULL,
    row_hash text NOT NULL,
    query text NOT NULL,
    selected_fields jsonb DEFAULT '{}'::jsonb NOT NULL,
    row_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_customers; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_customers (
    customer_id text NOT NULL,
    resource_name text,
    descriptive_name text,
    currency_code text,
    time_zone text,
    manager boolean,
    test_account boolean,
    status text,
    optimization_score numeric,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_expert_source_documents; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_expert_source_documents (
    source_id text NOT NULL,
    document_url text NOT NULL,
    source_name text NOT NULL,
    source_type text NOT NULL,
    access_level text NOT NULL,
    topics jsonb DEFAULT '[]'::jsonb NOT NULL,
    operator_notes text,
    title text,
    content_hash text,
    text_excerpt text,
    summary text,
    cache_path text,
    retrieved_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_fetch_errors; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_fetch_errors (
    id bigint NOT NULL,
    sync_run_id text,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    endpoint text NOT NULL,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    error jsonb DEFAULT '{}'::jsonb NOT NULL,
    message text
);


--
-- Name: google_fetch_errors_id_seq; Type: SEQUENCE; Schema: google_ads_tw; Owner: -
--

CREATE SEQUENCE google_ads_tw.google_fetch_errors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: google_fetch_errors_id_seq; Type: SEQUENCE OWNED BY; Schema: google_ads_tw; Owner: -
--

ALTER SEQUENCE google_ads_tw.google_fetch_errors_id_seq OWNED BY google_ads_tw.google_fetch_errors.id;


--
-- Name: google_gaql_rows; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_gaql_rows (
    id bigint NOT NULL,
    sync_run_id text,
    customer_id text NOT NULL,
    query_name text NOT NULL,
    source_resource text NOT NULL,
    report_date date,
    row_hash text NOT NULL,
    query text NOT NULL,
    row_json jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_gaql_rows_id_seq; Type: SEQUENCE; Schema: google_ads_tw; Owner: -
--

CREATE SEQUENCE google_ads_tw.google_gaql_rows_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: google_gaql_rows_id_seq; Type: SEQUENCE OWNED BY; Schema: google_ads_tw; Owner: -
--

ALTER SEQUENCE google_ads_tw.google_gaql_rows_id_seq OWNED BY google_ads_tw.google_gaql_rows.id;


--
-- Name: google_keyword_research_ideas; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_keyword_research_ideas (
    run_id uuid NOT NULL,
    customer_id text NOT NULL,
    text text NOT NULL,
    close_variants jsonb DEFAULT '[]'::jsonb NOT NULL,
    avg_monthly_searches bigint,
    competition text,
    competition_index integer,
    low_top_of_page_bid_micros bigint,
    high_top_of_page_bid_micros bigint,
    monthly_search_volumes jsonb DEFAULT '[]'::jsonb NOT NULL,
    recommended_match_type text,
    intent_bucket text,
    source text DEFAULT 'generateKeywordIdeas'::text NOT NULL,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_keyword_research_runs; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_keyword_research_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_id text NOT NULL,
    seed_terms jsonb DEFAULT '[]'::jsonb NOT NULL,
    final_url text,
    geo_targets jsonb DEFAULT '[]'::jsonb NOT NULL,
    language text,
    keyword_plan_network text,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    result_count integer DEFAULT 0 NOT NULL,
    source text DEFAULT 'generateKeywordIdeas'::text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_keywords; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_keywords (
    customer_id text NOT NULL,
    ad_group_id text DEFAULT ''::text NOT NULL,
    criterion_id text NOT NULL,
    campaign_id text,
    text text,
    match_type text,
    status text,
    negative boolean,
    quality_score integer,
    final_urls jsonb DEFAULT '[]'::jsonb NOT NULL,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_mutation_plans; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_mutation_plans (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_id text NOT NULL,
    entity_type text NOT NULL,
    operation_type text NOT NULL,
    operation_count integer DEFAULT 0 NOT NULL,
    validate_only boolean DEFAULT true NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_path text,
    note text,
    status text DEFAULT 'planned'::text NOT NULL,
    executed_run_id text,
    executed_at timestamp with time zone,
    result jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_offline_catalog_fields; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_offline_catalog_fields (
    api_version text NOT NULL,
    resource text NOT NULL,
    field_name text NOT NULL,
    field_path text NOT NULL,
    resource_kind text NOT NULL,
    class_name text,
    field_type text,
    proto_type text,
    enum_type text,
    message_type text,
    repeated boolean DEFAULT false NOT NULL,
    optional boolean DEFAULT false NOT NULL,
    description text,
    source_file text,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_optimizer_snapshots; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_optimizer_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    report_date date NOT NULL,
    latest_hour timestamp with time zone,
    target_ncpa numeric NOT NULL,
    decision_payload jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_performance_daily; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_performance_daily (
    customer_id text NOT NULL,
    level text NOT NULL,
    report_date date NOT NULL,
    campaign_id text DEFAULT ''::text NOT NULL,
    ad_group_id text DEFAULT ''::text NOT NULL,
    ad_id text DEFAULT ''::text NOT NULL,
    criterion_id text DEFAULT ''::text NOT NULL,
    asset_group_id text DEFAULT ''::text NOT NULL,
    search_term text DEFAULT ''::text NOT NULL,
    campaign_name text,
    ad_group_name text,
    ad_name text,
    campaign_channel_type text,
    campaign_channel_sub_type text,
    device text DEFAULT ''::text NOT NULL,
    network text DEFAULT ''::text NOT NULL,
    impressions bigint,
    clicks bigint,
    interactions bigint,
    cost_micros bigint,
    conversions numeric,
    conversions_value numeric,
    all_conversions numeric,
    all_conversions_value numeric,
    video_views bigint,
    ctr numeric,
    average_cpc_micros bigint,
    average_cpm_micros bigint,
    cost_per_conversion_micros bigint,
    value_per_conversion numeric,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_performance_daily_summary; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_performance_daily_summary AS
 SELECT customer_id,
    level,
    report_date,
    campaign_id,
    max(campaign_name) AS campaign_name,
    (sum(cost_micros) / 1000000.0) AS spend,
    sum(impressions) AS impressions,
    sum(clicks) AS clicks,
    sum(conversions) AS conversions,
    sum(conversions_value) AS conversion_value,
        CASE
            WHEN (sum(cost_micros) > (0)::numeric) THEN (sum(conversions_value) / (sum(cost_micros) / 1000000.0))
            ELSE NULL::numeric
        END AS roas,
        CASE
            WHEN (sum(conversions) > (0)::numeric) THEN ((sum(cost_micros) / 1000000.0) / sum(conversions))
            ELSE NULL::numeric
        END AS cpa
   FROM google_ads_tw.google_performance_daily
  GROUP BY customer_id, level, report_date, campaign_id;


--
-- Name: google_performance_generic; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_performance_generic (
    customer_id text NOT NULL,
    surface text NOT NULL,
    report_date date NOT NULL,
    entity_key text NOT NULL,
    query_name text NOT NULL,
    row_hash text NOT NULL,
    query text NOT NULL,
    selected_dimensions jsonb DEFAULT '{}'::jsonb NOT NULL,
    metrics jsonb DEFAULT '{}'::jsonb NOT NULL,
    row_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_query_manifest; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_query_manifest (
    api_version text NOT NULL,
    surface_type text NOT NULL,
    surface_name text NOT NULL,
    command text NOT NULL,
    query_name text,
    source_resource text,
    warehouse_tables jsonb DEFAULT '[]'::jsonb NOT NULL,
    date_window text,
    default_days integer,
    default_chunk_days integer,
    requires_auth boolean DEFAULT true NOT NULL,
    can_mutate boolean DEFAULT false NOT NULL,
    schedule text,
    query text,
    query_hash text,
    selected_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    metric_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    segment_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    resource_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    notes text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_raw_snapshots; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_raw_snapshots (
    id bigint NOT NULL,
    sync_run_id text,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    api_version text,
    customer_id text,
    endpoint text NOT NULL,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    response jsonb NOT NULL,
    headers jsonb DEFAULT '{}'::jsonb NOT NULL,
    row_count integer,
    status text DEFAULT 'ok'::text NOT NULL
);


--
-- Name: google_raw_snapshots_id_seq; Type: SEQUENCE; Schema: google_ads_tw; Owner: -
--

CREATE SEQUENCE google_ads_tw.google_raw_snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: google_raw_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: google_ads_tw; Owner: -
--

ALTER SEQUENCE google_ads_tw.google_raw_snapshots_id_seq OWNED BY google_ads_tw.google_raw_snapshots.id;


--
-- Name: google_recommendations; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_recommendations (
    customer_id text NOT NULL,
    recommendation_id text NOT NULL,
    campaign_id text,
    type text,
    impact jsonb DEFAULT '{}'::jsonb NOT NULL,
    dismissed boolean,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_search_terms; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_search_terms (
    customer_id text NOT NULL,
    report_date date NOT NULL,
    campaign_id text DEFAULT ''::text NOT NULL,
    ad_group_id text DEFAULT ''::text NOT NULL,
    search_term text NOT NULL,
    status text,
    impressions bigint,
    clicks bigint,
    cost_micros bigint,
    conversions numeric,
    conversions_value numeric,
    raw jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: google_sync_runs; Type: TABLE; Schema: google_ads_tw; Owner: -
--

CREATE TABLE google_ads_tw.google_sync_runs (
    id text NOT NULL,
    command text NOT NULL,
    status text NOT NULL,
    customer_id text,
    api_version text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    rows_fetched integer DEFAULT 0 NOT NULL,
    rows_written integer DEFAULT 0 NOT NULL,
    errors integer DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: google_tw_attribution_level_daily; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_tw_attribution_level_daily AS
 SELECT report_date,
    level,
    channel,
    campaign_id,
    campaign_name,
    ad_group_id,
    ad_group_name,
    ad_id,
    ad_name,
    tw_spend,
    tw_revenue,
    tw_purchases,
    tw_new_customer_orders,
    tw_roas,
    tw_ncpa,
    tw_cpa,
    shop_domain,
    preset_name,
    attribution_model,
    attribution_window,
    accounting_mode,
    subscription_filter,
    ad_spend,
    pixel_new_customer_purchases,
    pixel_new_customer_cpa,
    pixel_purchases,
    pixel_cpa,
    pixel_new_customer_purchases_percent,
    impressions,
    cpm,
    outbound_ctr,
    clicks,
    pixel_sessions,
    pixel_cost_per_visitors,
    pixel_new_visitors,
    pixel_cost_per_new_visitors,
    pixel_new_visitor_percent,
    pixel_new_customer_aov,
    pixel_aov,
    pixel_new_customer_conversion_rate,
    pixel_conversion_rate,
    combined_net_revenue,
    pixel_roas,
    pixel_new_customers_roas,
    pixel_unique_add_to_carts,
    ctr,
    cpc,
    outbound_clicks,
    pixel_new_customer_revenue,
    source_row_count,
    hour_count,
    rolled_up_at,
    campaign_type,
    campaign_type_label
   FROM google_ads_tw.google_tw_attribution_daily;


--
-- Name: google_tw_platform_comparison_daily; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_tw_platform_comparison_daily AS
 SELECT COALESCE(t.report_date, p.report_date) AS report_date,
    COALESCE(t.campaign_id, p.campaign_id) AS campaign_id,
    COALESCE(t.campaign_name, p.campaign_name) AS campaign_name,
    t.tw_spend,
    t.tw_revenue,
    t.tw_purchases,
    t.tw_new_customer_orders,
    t.tw_roas,
    t.tw_ncpa,
    p.spend AS google_reported_spend,
    p.conversions AS google_reported_conversions,
    p.conversion_value AS google_reported_conversion_value,
    p.roas AS google_reported_roas,
    p.cpa AS google_reported_cpa
   FROM (google_ads_tw.google_tw_attribution_daily t
     FULL JOIN google_ads_tw.google_performance_daily_summary p ON (((p.report_date = t.report_date) AND (p.level = 'campaign'::text) AND (p.campaign_id = COALESCE(t.campaign_id, ''::text)))))
  WHERE (COALESCE(t.level, 'campaign'::text) = 'campaign'::text);


--
-- Name: google_tw_rolling_31d; Type: VIEW; Schema: google_ads_tw; Owner: -
--

CREATE VIEW google_ads_tw.google_tw_rolling_31d AS
 WITH latest AS (
         SELECT max(google_tw_attribution_daily.report_date) AS end_date
           FROM google_ads_tw.google_tw_attribution_daily
        )
 SELECT (latest.end_date - 30) AS window_start,
    latest.end_date AS window_end,
    d.level,
    d.campaign_id,
    max(d.campaign_name) AS campaign_name,
    d.ad_group_id,
    max(d.ad_group_name) AS ad_group_name,
    d.ad_id,
    max(d.ad_name) AS ad_name,
    sum(d.tw_spend) AS spend,
    (sum(d.impressions))::bigint AS impressions,
    (sum(d.clicks))::bigint AS clicks,
    sum(d.tw_purchases) AS purchases,
    sum(d.tw_new_customer_orders) AS new_customer_orders,
    sum(d.tw_revenue) AS revenue,
        CASE
            WHEN (sum(d.tw_spend) > (0)::double precision) THEN (sum(d.tw_revenue) / sum(d.tw_spend))
            ELSE NULL::double precision
        END AS roas,
        CASE
            WHEN (sum(d.tw_purchases) > (0)::double precision) THEN (sum(d.tw_spend) / sum(d.tw_purchases))
            ELSE NULL::double precision
        END AS cpa,
        CASE
            WHEN (sum(d.tw_new_customer_orders) > (0)::double precision) THEN (sum(d.tw_spend) / sum(d.tw_new_customer_orders))
            ELSE NULL::double precision
        END AS ncpa,
    max(d.rolled_up_at) AS rolled_up_at,
    google_ads_tw.google_infer_campaign_type(max(d.campaign_name)) AS campaign_type,
    google_ads_tw.google_campaign_type_label(google_ads_tw.google_infer_campaign_type(max(d.campaign_name))) AS campaign_type_label
   FROM (google_ads_tw.google_tw_attribution_daily d
     JOIN latest ON (true))
  WHERE ((latest.end_date IS NOT NULL) AND ((d.report_date >= (latest.end_date - 30)) AND (d.report_date <= latest.end_date)))
  GROUP BY latest.end_date, d.level, d.campaign_id, d.ad_group_id, d.ad_id;


--
-- Name: google_fetch_errors id; Type: DEFAULT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_fetch_errors ALTER COLUMN id SET DEFAULT nextval('google_ads_tw.google_fetch_errors_id_seq'::regclass);


--
-- Name: google_gaql_rows id; Type: DEFAULT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_gaql_rows ALTER COLUMN id SET DEFAULT nextval('google_ads_tw.google_gaql_rows_id_seq'::regclass);


--
-- Name: google_raw_snapshots id; Type: DEFAULT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_raw_snapshots ALTER COLUMN id SET DEFAULT nextval('google_ads_tw.google_raw_snapshots_id_seq'::regclass);


--
-- Name: google_ad_groups google_ad_groups_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_ad_groups
    ADD CONSTRAINT google_ad_groups_pkey PRIMARY KEY (customer_id, ad_group_id);


--
-- Name: google_ads_fields google_ads_fields_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_ads_fields
    ADD CONSTRAINT google_ads_fields_pkey PRIMARY KEY (api_version, name);


--
-- Name: google_ads google_ads_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_ads
    ADD CONSTRAINT google_ads_pkey PRIMARY KEY (customer_id, ad_group_id, ad_id);


--
-- Name: google_api_catalog_sources google_api_catalog_sources_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_api_catalog_sources
    ADD CONSTRAINT google_api_catalog_sources_pkey PRIMARY KEY (source_name);


--
-- Name: google_api_methods google_api_methods_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_api_methods
    ADD CONSTRAINT google_api_methods_pkey PRIMARY KEY (api_version, service_name, method_name);


--
-- Name: google_api_services google_api_services_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_api_services
    ADD CONSTRAINT google_api_services_pkey PRIMARY KEY (api_version, service_name);


--
-- Name: google_asset_groups google_asset_groups_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_asset_groups
    ADD CONSTRAINT google_asset_groups_pkey PRIMARY KEY (customer_id, asset_group_id);


--
-- Name: google_assets google_assets_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_assets
    ADD CONSTRAINT google_assets_pkey PRIMARY KEY (customer_id, asset_id);


--
-- Name: google_backfill_chunks google_backfill_chunks_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_backfill_chunks
    ADD CONSTRAINT google_backfill_chunks_pkey PRIMARY KEY (customer_id, surface, since_date, until_date);


--
-- Name: google_campaign_budgets google_campaign_budgets_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_campaign_budgets
    ADD CONSTRAINT google_campaign_budgets_pkey PRIMARY KEY (customer_id, budget_id);


--
-- Name: google_campaigns google_campaigns_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_campaigns
    ADD CONSTRAINT google_campaigns_pkey PRIMARY KEY (customer_id, campaign_id);


--
-- Name: google_change_events google_change_events_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_change_events
    ADD CONSTRAINT google_change_events_pkey PRIMARY KEY (customer_id, change_event_id);


--
-- Name: google_conversion_actions google_conversion_actions_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_conversion_actions
    ADD CONSTRAINT google_conversion_actions_pkey PRIMARY KEY (customer_id, conversion_action_id);


--
-- Name: google_core_generic google_core_generic_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_core_generic
    ADD CONSTRAINT google_core_generic_pkey PRIMARY KEY (customer_id, surface, entity_key);


--
-- Name: google_customers google_customers_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_customers
    ADD CONSTRAINT google_customers_pkey PRIMARY KEY (customer_id);


--
-- Name: google_expert_source_documents google_expert_source_documents_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_expert_source_documents
    ADD CONSTRAINT google_expert_source_documents_pkey PRIMARY KEY (source_id, document_url);


--
-- Name: google_fetch_errors google_fetch_errors_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_fetch_errors
    ADD CONSTRAINT google_fetch_errors_pkey PRIMARY KEY (id);


--
-- Name: google_gaql_rows google_gaql_rows_customer_id_query_name_row_hash_key; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_gaql_rows
    ADD CONSTRAINT google_gaql_rows_customer_id_query_name_row_hash_key UNIQUE (customer_id, query_name, row_hash);


--
-- Name: google_gaql_rows google_gaql_rows_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_gaql_rows
    ADD CONSTRAINT google_gaql_rows_pkey PRIMARY KEY (id);


--
-- Name: google_keyword_research_ideas google_keyword_research_ideas_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_keyword_research_ideas
    ADD CONSTRAINT google_keyword_research_ideas_pkey PRIMARY KEY (run_id, text);


--
-- Name: google_keyword_research_runs google_keyword_research_runs_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_keyword_research_runs
    ADD CONSTRAINT google_keyword_research_runs_pkey PRIMARY KEY (id);


--
-- Name: google_keywords google_keywords_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_keywords
    ADD CONSTRAINT google_keywords_pkey PRIMARY KEY (customer_id, ad_group_id, criterion_id);


--
-- Name: google_mutation_plans google_mutation_plans_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_mutation_plans
    ADD CONSTRAINT google_mutation_plans_pkey PRIMARY KEY (id);


--
-- Name: google_offline_catalog_fields google_offline_catalog_fields_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_offline_catalog_fields
    ADD CONSTRAINT google_offline_catalog_fields_pkey PRIMARY KEY (api_version, field_path);


--
-- Name: google_optimizer_snapshots google_optimizer_snapshots_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_optimizer_snapshots
    ADD CONSTRAINT google_optimizer_snapshots_pkey PRIMARY KEY (id);


--
-- Name: google_performance_daily google_performance_daily_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_performance_daily
    ADD CONSTRAINT google_performance_daily_pkey PRIMARY KEY (customer_id, level, report_date, campaign_id, ad_group_id, ad_id, criterion_id, asset_group_id, search_term, device, network);


--
-- Name: google_performance_generic google_performance_generic_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_performance_generic
    ADD CONSTRAINT google_performance_generic_pkey PRIMARY KEY (customer_id, surface, report_date, entity_key, row_hash);


--
-- Name: google_query_manifest google_query_manifest_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_query_manifest
    ADD CONSTRAINT google_query_manifest_pkey PRIMARY KEY (api_version, surface_type, surface_name);


--
-- Name: google_raw_snapshots google_raw_snapshots_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_raw_snapshots
    ADD CONSTRAINT google_raw_snapshots_pkey PRIMARY KEY (id);


--
-- Name: google_recommendations google_recommendations_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_recommendations
    ADD CONSTRAINT google_recommendations_pkey PRIMARY KEY (customer_id, recommendation_id);


--
-- Name: google_search_terms google_search_terms_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_search_terms
    ADD CONSTRAINT google_search_terms_pkey PRIMARY KEY (customer_id, report_date, campaign_id, ad_group_id, search_term);


--
-- Name: google_sync_runs google_sync_runs_pkey; Type: CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_sync_runs
    ADD CONSTRAINT google_sync_runs_pkey PRIMARY KEY (id);


--
-- Name: idx_google_api_methods_kind; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_api_methods_kind ON google_ads_tw.google_api_methods USING btree (api_version, operation_kind);


--
-- Name: idx_google_backfill_status; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_backfill_status ON google_ads_tw.google_backfill_chunks USING btree (status, surface);


--
-- Name: idx_google_core_generic_hash; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_core_generic_hash ON google_ads_tw.google_core_generic USING btree (row_hash);


--
-- Name: idx_google_core_generic_surface; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_core_generic_surface ON google_ads_tw.google_core_generic USING btree (surface, fetched_at DESC);


--
-- Name: idx_google_expert_sources_type; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_expert_sources_type ON google_ads_tw.google_expert_source_documents USING btree (source_type, retrieved_at DESC);


--
-- Name: idx_google_fields_category; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_fields_category ON google_ads_tw.google_ads_fields USING btree (api_version, category);


--
-- Name: idx_google_gaql_query_date; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_gaql_query_date ON google_ads_tw.google_gaql_rows USING btree (query_name, report_date);


--
-- Name: idx_google_keyword_ideas_intent; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_keyword_ideas_intent ON google_ads_tw.google_keyword_research_ideas USING btree (intent_bucket, recommended_match_type);


--
-- Name: idx_google_keyword_ideas_volume; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_keyword_ideas_volume ON google_ads_tw.google_keyword_research_ideas USING btree (avg_monthly_searches DESC NULLS LAST);


--
-- Name: idx_google_mutation_plans_created; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_mutation_plans_created ON google_ads_tw.google_mutation_plans USING btree (created_at DESC, entity_type, operation_type);


--
-- Name: idx_google_optimizer_date; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_optimizer_date ON google_ads_tw.google_optimizer_snapshots USING btree (report_date, generated_at DESC);


--
-- Name: idx_google_perf_campaign; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_perf_campaign ON google_ads_tw.google_performance_daily USING btree (campaign_id);


--
-- Name: idx_google_perf_date_level; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_perf_date_level ON google_ads_tw.google_performance_daily USING btree (report_date, level);


--
-- Name: idx_google_perf_generic_surface; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_perf_generic_surface ON google_ads_tw.google_performance_generic USING btree (surface, report_date);


--
-- Name: idx_google_perf_search_term; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_perf_search_term ON google_ads_tw.google_performance_daily USING btree (search_term) WHERE (search_term <> ''::text);


--
-- Name: idx_google_query_manifest_type; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_query_manifest_type ON google_ads_tw.google_query_manifest USING btree (api_version, surface_type, requires_auth);


--
-- Name: idx_google_raw_endpoint; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_raw_endpoint ON google_ads_tw.google_raw_snapshots USING btree (endpoint);


--
-- Name: idx_google_raw_run; Type: INDEX; Schema: google_ads_tw; Owner: -
--

CREATE INDEX idx_google_raw_run ON google_ads_tw.google_raw_snapshots USING btree (sync_run_id);


--
-- Name: google_backfill_chunks google_backfill_chunks_last_run_id_fkey; Type: FK CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_backfill_chunks
    ADD CONSTRAINT google_backfill_chunks_last_run_id_fkey FOREIGN KEY (last_run_id) REFERENCES google_ads_tw.google_sync_runs(id) ON DELETE SET NULL;


--
-- Name: google_fetch_errors google_fetch_errors_sync_run_id_fkey; Type: FK CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_fetch_errors
    ADD CONSTRAINT google_fetch_errors_sync_run_id_fkey FOREIGN KEY (sync_run_id) REFERENCES google_ads_tw.google_sync_runs(id) ON DELETE SET NULL;


--
-- Name: google_gaql_rows google_gaql_rows_sync_run_id_fkey; Type: FK CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_gaql_rows
    ADD CONSTRAINT google_gaql_rows_sync_run_id_fkey FOREIGN KEY (sync_run_id) REFERENCES google_ads_tw.google_sync_runs(id) ON DELETE SET NULL;


--
-- Name: google_keyword_research_ideas google_keyword_research_ideas_run_id_fkey; Type: FK CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_keyword_research_ideas
    ADD CONSTRAINT google_keyword_research_ideas_run_id_fkey FOREIGN KEY (run_id) REFERENCES google_ads_tw.google_keyword_research_runs(id) ON DELETE CASCADE;


--
-- Name: google_mutation_plans google_mutation_plans_executed_run_id_fkey; Type: FK CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_mutation_plans
    ADD CONSTRAINT google_mutation_plans_executed_run_id_fkey FOREIGN KEY (executed_run_id) REFERENCES google_ads_tw.google_sync_runs(id) ON DELETE SET NULL;


--
-- Name: google_raw_snapshots google_raw_snapshots_sync_run_id_fkey; Type: FK CONSTRAINT; Schema: google_ads_tw; Owner: -
--

ALTER TABLE ONLY google_ads_tw.google_raw_snapshots
    ADD CONSTRAINT google_raw_snapshots_sync_run_id_fkey FOREIGN KEY (sync_run_id) REFERENCES google_ads_tw.google_sync_runs(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict DoFWxsXlJwEHaZvVcFMcxGDgwH57AVhAF48yAP9zDUIsy4YedVZ9SraS9FkkUq6

