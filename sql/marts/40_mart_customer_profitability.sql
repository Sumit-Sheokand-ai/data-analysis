CREATE OR REPLACE VIEW mart.customer_profitability AS
WITH customer_orders AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(net_revenue) AS total_net_revenue,
        SUM(contribution_margin) AS realized_ltv,
        MIN(order_ts) AS first_order_ts,
        MAX(order_ts) AS last_order_ts
    FROM mart.orders
    GROUP BY 1
)
SELECT
    co.customer_id,
    a.attributed_channel,
    co.order_count,
    co.total_net_revenue,
    co.realized_ltv,
    co.first_order_ts,
    co.last_order_ts
FROM customer_orders co
LEFT JOIN mart.customer_first_order_attribution a USING (customer_id);
