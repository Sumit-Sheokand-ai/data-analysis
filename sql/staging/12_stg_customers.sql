CREATE OR REPLACE VIEW stg.customers AS
SELECT DISTINCT
    TRIM(customer_id) AS customer_id,
    acquired_at::timestamptz AS acquired_at,
    COALESCE(NULLIF(TRIM(acquisition_channel), ''), 'unknown') AS acquisition_channel,
    COALESCE(NULLIF(TRIM(region), ''), 'unknown') AS region
FROM raw.customers
WHERE customer_id IS NOT NULL;
