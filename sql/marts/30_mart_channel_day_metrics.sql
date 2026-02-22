CREATE OR REPLACE VIEW mart.channel_day_metrics AS
WITH customer_acq AS (
    SELECT
        DATE(first_order_ts) AS date,
        attributed_channel AS channel,
        COUNT(DISTINCT customer_id) AS new_customers
    FROM mart.customer_first_order_attribution
    GROUP BY 1, 2
),
order_contrib AS (
    SELECT
        DATE(o.order_ts) AS date,
        a.attributed_channel AS channel,
        SUM(o.net_revenue) AS net_revenue,
        SUM(o.contribution_margin) AS contribution_margin
    FROM mart.orders o
    JOIN mart.customer_first_order_attribution a
      ON o.customer_id = a.customer_id
    GROUP BY 1, 2
)
SELECT
    COALESCE(m.date, c.date, oc.date) AS date,
    COALESCE(m.channel, c.channel, oc.channel) AS channel,
    COALESCE(m.spend, 0) AS spend,
    COALESCE(m.sales_cost, 0) AS sales_cost,
    COALESCE(c.new_customers, 0) AS new_customers,
    COALESCE(oc.net_revenue, 0) AS net_revenue,
    COALESCE(oc.contribution_margin, 0) AS contribution_margin,
    CASE
        WHEN COALESCE(c.new_customers, 0) = 0 THEN NULL
        ELSE (COALESCE(m.spend, 0) + COALESCE(m.sales_cost, 0)) / c.new_customers::numeric
    END AS cac
FROM stg.marketing_spend m
FULL OUTER JOIN customer_acq c
  ON m.date = c.date
 AND m.channel = c.channel
FULL OUTER JOIN order_contrib oc
  ON COALESCE(m.date, c.date) = oc.date
 AND COALESCE(m.channel, c.channel) = oc.channel;
