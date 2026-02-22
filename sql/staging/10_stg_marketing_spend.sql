CREATE OR REPLACE VIEW stg.marketing_spend AS
SELECT
    date::date AS date,
    TRIM(channel) AS channel,
    TRIM(campaign) AS campaign,
    GREATEST(COALESCE(spend, 0), 0) AS spend,
    GREATEST(COALESCE(clicks, 0), 0) AS clicks,
    GREATEST(COALESCE(impressions, 0), 0) AS impressions,
    GREATEST(COALESCE(sales_cost, 0), 0) AS sales_cost
FROM raw.marketing_spend;
