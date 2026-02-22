CREATE OR REPLACE VIEW mart.customer_first_order_attribution AS
WITH first_orders AS (
    SELECT
        customer_id,
        MIN(order_ts) AS first_order_ts
    FROM mart.orders
    GROUP BY 1
),
first_order_id AS (
    SELECT DISTINCT ON (o.customer_id)
        o.customer_id,
        o.order_id AS first_order_id,
        o.order_ts AS first_order_ts
    FROM mart.orders o
    JOIN first_orders f
      ON o.customer_id = f.customer_id
     AND o.order_ts = f.first_order_ts
    ORDER BY o.customer_id, o.order_ts, o.order_id
),
last_non_direct_touch AS (
    SELECT DISTINCT ON (s.customer_id)
        s.customer_id,
        s.channel AS attributed_channel
    FROM stg.sessions s
    JOIN first_orders f
      ON s.customer_id = f.customer_id
     AND s.session_ts <= f.first_order_ts
    WHERE COALESCE(LOWER(s.channel), 'direct') <> 'direct'
    ORDER BY s.customer_id, s.session_ts DESC
)
SELECT
    c.customer_id,
    fo.first_order_id,
    fo.first_order_ts,
    COALESCE(l.attributed_channel, c.acquisition_channel) AS attributed_channel
FROM stg.customers c
JOIN first_order_id fo USING (customer_id)
LEFT JOIN last_non_direct_touch l USING (customer_id);
