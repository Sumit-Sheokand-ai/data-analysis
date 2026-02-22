CREATE OR REPLACE VIEW mart.orders AS
WITH refunds AS (
    SELECT order_id, SUM(refund_amount) AS total_refund
    FROM stg.refunds
    GROUP BY 1
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.gross_revenue,
    o.discount,
    o.cogs,
    COALESCE(r.total_refund, 0) AS refund_amount,
    (o.gross_revenue - o.discount - COALESCE(r.total_refund, 0)) AS net_revenue,
    (o.gross_revenue - o.discount - COALESCE(r.total_refund, 0) - o.cogs) AS contribution_margin
FROM stg.orders o
LEFT JOIN refunds r USING (order_id);
