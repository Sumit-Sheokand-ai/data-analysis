CREATE OR REPLACE VIEW stg.refunds AS
SELECT
    TRIM(refund_id) AS refund_id,
    TRIM(order_id) AS order_id,
    GREATEST(COALESCE(refund_amount, 0), 0) AS refund_amount,
    refund_ts::timestamptz AS refund_ts
FROM raw.refunds
WHERE order_id IS NOT NULL
  AND LOWER(TRIM(status)) = 'processed';
