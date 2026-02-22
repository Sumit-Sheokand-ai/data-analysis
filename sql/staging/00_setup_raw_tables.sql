CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS raw.marketing_spend (
    date DATE,
    channel TEXT,
    campaign TEXT,
    spend NUMERIC,
    clicks INTEGER,
    impressions INTEGER,
    sales_cost NUMERIC
);

CREATE TABLE IF NOT EXISTS raw.sessions (
    session_id TEXT,
    session_ts TIMESTAMPTZ,
    customer_id TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    channel TEXT,
    is_direct BOOLEAN
);

CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id TEXT,
    acquired_at TIMESTAMPTZ,
    acquisition_channel TEXT,
    region TEXT
);

CREATE TABLE IF NOT EXISTS raw.orders (
    order_id TEXT,
    customer_id TEXT,
    order_ts TIMESTAMPTZ,
    gross_revenue NUMERIC,
    discount NUMERIC,
    cogs NUMERIC,
    status TEXT
);

CREATE TABLE IF NOT EXISTS raw.refunds (
    refund_id TEXT,
    order_id TEXT,
    refund_amount NUMERIC,
    refund_ts TIMESTAMPTZ,
    status TEXT
);

-- Example COPY commands:
-- COPY raw.marketing_spend FROM 'data/raw/raw_marketing_spend.csv' CSV HEADER;
-- COPY raw.sessions FROM 'data/raw/raw_sessions.csv' CSV HEADER;
-- COPY raw.customers FROM 'data/raw/raw_customers.csv' CSV HEADER;
-- COPY raw.orders FROM 'data/raw/raw_orders.csv' CSV HEADER;
-- COPY raw.refunds FROM 'data/raw/raw_refunds.csv' CSV HEADER;
