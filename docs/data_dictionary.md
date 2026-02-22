# Data dictionary
This project uses a dual data strategy:
- Primary: real ecommerce export data
- Secondary: synthetic data for QA/edge cases

## Canonical raw entities
### `raw_marketing_spend`
- `date` (date)
- `channel` (text)
- `campaign` (text)
- `spend` (numeric)
- `clicks` (integer)
- `impressions` (integer)
- `sales_cost` (numeric, attributable sales-support cost)

### `raw_sessions`
- `session_id` (text)
- `session_ts` (timestamp)
- `customer_id` (text)
- `utm_source` (text)
- `utm_medium` (text)
- `utm_campaign` (text)
- `channel` (text)
- `is_direct` (boolean)

### `raw_customers`
- `customer_id` (text)
- `acquired_at` (timestamp)
- `acquisition_channel` (text)
- `region` (text)

### `raw_orders`
- `order_id` (text)
- `customer_id` (text)
- `order_ts` (timestamp)
- `gross_revenue` (numeric)
- `discount` (numeric)
- `cogs` (numeric)
- `status` (text)

### `raw_refunds`
- `refund_id` (text)
- `order_id` (text)
- `refund_amount` (numeric)
- `refund_ts` (timestamp)
- `status` (text)

## Standardization rules
- Timezone: UTC
- Currency: single reporting currency per run
- Channel taxonomy: normalized in SQL staging layer
- Direct traffic: excluded from last-non-direct-touch attribution unless no non-direct touch exists
