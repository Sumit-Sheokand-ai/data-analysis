# Real export connector mapping
Use connector scripts to map real platform exports into this project's canonical raw schema.

## Supported templates (v1)
- Shopify orders export -> `raw_orders.csv`, `raw_customers.csv`
- GA4 sessions export -> `raw_sessions.csv`

## Run mapping
```bash
python -m python.pipeline.prepare_real_exports --shopify-orders path/to/shopify_orders.csv --ga4-sessions path/to/ga4_sessions.csv --output-dir data/raw --validation-mode strict
```

You can pass either source independently:
```bash
python -m python.pipeline.prepare_real_exports --shopify-orders path/to/shopify_orders.csv --validation-mode strict
python -m python.pipeline.prepare_real_exports --ga4-sessions path/to/ga4_sessions.csv --validation-mode strict
```

## Column matching behavior
Connectors support common column-name variants and map the first matching column.
If a required field is missing:
- Numeric fields default to `0`
- Text fields default to `"unknown"` or `""`
- Datetime fields are parsed to UTC where possible
- In strict mode, mapped outputs must pass schema + business-rule validation before being accepted.

## Recommended workflow
1. Export CSVs from platforms.
2. Run connector mapping command.
3. Review generated canonical files in `data/raw/`.
4. Review `data/raw/connector_validation_report.csv` and resolve any errors.
5. Run analytics pipeline:
   - `python -m python.pipeline.run_pipeline --data-source csv --validation-mode strict`
