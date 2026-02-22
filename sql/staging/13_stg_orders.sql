CREATE OR REPLACE VIEW stg.orders AS
SELECT
    TRIM(order_id) AS order_id,
    TRIM(customer_id) AS customer_id,
    order_ts::timestamptz AS order_ts,
    GREATEST(COALESCE(gross_revenue, 0), 0) AS gross_revenue,
    GREATEST(COALESCE(discount, 0), 0) AS discount,
    GREATEST(COALESCE(cogs, 0), 0) AS cogs,
    LOWER(TRIM(status)) AS status
FROM raw.orders
WHERE order_id IS NOT NULL
  AND customer_id IS NOT NULL
  AND LOWER(TRIM(status)) = 'completed';
