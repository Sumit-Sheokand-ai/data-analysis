# KPI definitions
## CAC
Customer Acquisition Cost by channel:
- `CAC = (Marketing Spend + Sales Cost) / New Customers`
- Attribution for new customers: **last non-direct touch** on first order.

## Retention rate
Monthly cohort retention:
- Cohort month = first purchase month.
- Retention at month `n`:
  - `customers active in month n / customers in cohort month 0`

## Realized LTV
Per customer:
- `Realized LTV = SUM(Contribution Margin across completed orders)`
- `Contribution Margin = Net Revenue - COGS`
- `Net Revenue = Gross Revenue - Discount - Refund Amount`

## Predictive LTV
Primary approach:
- BG/NBD model for purchase frequency (non-contractual behavior)
- Gamma-Gamma model for expected monetary value

Fallback when data is sparse:
- `Predictive LTV ≈ Avg Monthly Contribution Margin × Expected Lifetime Months`
- Expected lifetime derived from observed repeat/churn behavior.

## Profitability
- `LTV:CAC Ratio = Avg LTV per channel cohort / CAC`
- `Payback Months = CAC / Avg Monthly Contribution Margin per acquired customer`
