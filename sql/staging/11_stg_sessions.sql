CREATE OR REPLACE VIEW stg.sessions AS
SELECT
    TRIM(session_id) AS session_id,
    session_ts::timestamptz AS session_ts,
    TRIM(customer_id) AS customer_id,
    NULLIF(TRIM(utm_source), '') AS utm_source,
    NULLIF(TRIM(utm_medium), '') AS utm_medium,
    NULLIF(TRIM(utm_campaign), '') AS utm_campaign,
    COALESCE(NULLIF(TRIM(channel), ''), 'direct') AS channel,
    COALESCE(is_direct, FALSE) AS is_direct
FROM raw.sessions
WHERE session_id IS NOT NULL
  AND customer_id IS NOT NULL;
