-- Duplicate checks
SELECT 'raw.customers duplicate customer_id' AS check_name, COUNT(*) AS issue_count
FROM (
    SELECT customer_id
    FROM raw.customers
    GROUP BY customer_id
    HAVING COUNT(*) > 1
) d;

SELECT 'raw.orders duplicate order_id' AS check_name, COUNT(*) AS issue_count
FROM (
    SELECT order_id
    FROM raw.orders
    GROUP BY order_id
    HAVING COUNT(*) > 1
) d;

-- Null and domain checks
SELECT 'stg.orders null order_ts' AS check_name, COUNT(*) AS issue_count
FROM stg.orders
WHERE order_ts IS NULL;

SELECT 'stg.marketing_spend negative spend' AS check_name, COUNT(*) AS issue_count
FROM stg.marketing_spend
WHERE spend < 0 OR sales_cost < 0;

-- Referential integrity checks
SELECT 'stg.orders missing customer_id reference' AS check_name, COUNT(*) AS issue_count
FROM stg.orders o
LEFT JOIN stg.customers c USING (customer_id)
WHERE c.customer_id IS NULL;
