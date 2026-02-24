# Syntellia
End-to-end marketing profitability analytics web app with:
- SQL-first cleaning/modeling (PostgreSQL scripts)
- Python KPI analysis (CAC, retention, realized + predictive LTV)
- Streamlit web app dashboard
- Scheduled pipeline (GitHub Actions)

## Project structure
- `data/raw/` raw source CSVs (sample + synthetic)
- `data/processed/` generated KPI outputs for the dashboard
- `sql/staging/` cleaning and standardization SQL
- `sql/marts/` curated fact/mart SQL for analytics
- `sql/quality/` data quality checks
- `python/analysis/` reusable analytics modules
- `python/pipeline/` CLI entrypoint for refresh
- `app/` Streamlit dashboard
- `tests/` KPI tests
- `.github/workflows/` scheduled pipeline workflow
- `docs/` data dictionary, KPI definitions, deployment notes

## KPI scope
- **CAC** (channel-level, last-non-direct-touch attribution on first order)
- **Retention rate** (cohort-based monthly retention)
- **LTV**
  - Realized LTV: cumulative contribution margin per customer
  - Predictive LTV: BG/NBD + Gamma-Gamma (fallback proxy if model is not fit-ready)
- **Profitability**: LTV:CAC ratio and estimated payback period

## Quick start
1. Create and activate a Python environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run pipeline using sample CSV data:
   - `python -m python.pipeline.run_pipeline --data-source csv --validation-mode strict`
4. Launch dashboard:
   - `streamlit run app/main.py`

## Hosted authentication and tenant-aware mode
For hosted/public deployments, enable auth and bind users to workspaces:
- `APP_REQUIRE_AUTH=1`
- `APP_AUTH_MODE=basic` (or replace with your managed auth adapter)
- `APP_AUTH_BASIC_USERS_JSON='{"alice":{"password":"...","workspace_id":"acme","role":"admin","plan_slug":"growth"}}'`
- `APP_WORKSPACE_PLAN_MAP_JSON='{"acme":"growth","globex":"pro"}'` (optional workspace-to-plan overrides)

With auth enabled, workspace and plan are identity-bound in the app shell and service-backed state/usage is scoped by `workspace_id`.

## Custom domain
- Primary domain: `https://syntellia.ca`
- Set `APP_PUBLIC_BASE_URL=https://syntellia.ca`
- In Render, add `syntellia.ca` in **Settings → Custom Domains** and complete DNS/TLS verification.

### Optional: run pipeline in service mode
- Start the service runtime:
  - `python -m python.pipeline.run_pipeline_service --host 127.0.0.1 --port 8091`
- Trigger a job through the service:
  - `python -m python.pipeline.run_pipeline --data-source csv --service-url http://127.0.0.1:8091`
- App integration:
  - set `APP_PIPELINE_SERVICE_URL=http://127.0.0.1:8091`
  - set `APP_PIPELINE_SERVICE_TIMEOUT_SECONDS=30` (optional)
  - set `APP_SERVICE_AUTH_TOKEN=<shared-service-token>`
  - set `SERVICE_API_AUTH_TOKEN=<shared-service-token>` in service runtime environments
  - optional: set `SERVICE_HEALTH_REQUIRE_AUTH=1` to protect `/health`

### Optional: run insights automation state in service mode
- Start the state service runtime:
  - `python -m python.pipeline.run_insights_service --host 127.0.0.1 --port 8092`
- App integration:
  - set `APP_INSIGHTS_SERVICE_URL=http://127.0.0.1:8092`
  - set `APP_INSIGHTS_SERVICE_TIMEOUT_SECONDS=10` (optional)
  - set `APP_INSIGHTS_STATE_FILE=data/processed/insights_state.json` (local fallback path)

### Optional: run entitlements and usage policy in service mode
- Start the policy service runtime:
  - `python -m python.pipeline.run_policy_service --host 127.0.0.1 --port 8093`
- App integration:
  - set `APP_POLICY_SERVICE_URL=http://127.0.0.1:8093`
  - set `APP_POLICY_SERVICE_TIMEOUT_SECONDS=10` (optional)
  - set `APP_POLICY_STATE_FILE=data/processed/policy_state.json` (local fallback path)

### Service preflight check command
- Validate service health endpoints before cutover or CI service-mode runs:
  - `python -m python.pipeline.check_service_health --pipeline-url http://127.0.0.1:8091 --insights-url http://127.0.0.1:8092 --policy-url http://127.0.0.1:8093`

## Monetization-ready features (Phase 1)
- Plan-aware entitlements in app (`Starter`, `Growth`, `Pro / Agency`, `Enterprise`)
- Billing page with plan limits + usage counters
- Feature gating for advanced pages and alert workflows
- Scheduled report setup + export usage metering
- Connectors & Sync control center with connector health checks
- What Changed diagnostics using previous-vs-current KPI snapshots
- Alert destination manager (email/webhook test dispatch)
- Attribution Deep Dive (touch-depth + first-touch vs last-non-direct crosswalk)
- Scenario Optimizer (constraint-aware budget recommendation engine)
- White Label Studio (brand name/color/logo configuration + brand-kit export)
- Security Center (webhook policy hardening + session audit log visibility/export)
- Enterprise Controls (seat/role management, SSO policy, IP allowlist, SLA panel)
- Partner Hub (opportunity pipeline tracking and co-sell template export)
- Growth Copilot (AI-prioritized growth actions from CAC/LTV/retention/anomaly signals)
- Experiment Studio (hypothesis backlog, status workflow, and experiment log export)
- Playbook Automation (convert signals to executable owner/SLA playbook tasks)
- ROI Forecast (experiment-weighted projected revenue impact for next planning window)
- Goal Tracker (target-vs-actual monitoring for CAC, LTV:CAC, retention, and error alerts)
- Autopilot Queue (auto-generated execution queue for off-track goals with owner/status workflow)

### Optional environment variables for billing UX
- `APP_PLAN` (default: `starter`)
- `APP_ALLOW_PLAN_SWITCH` (default: `1`; set `0` to lock plan server-side)
- `APP_REQUIRE_AUTH` (default: `0` in development; set `1` for hosted/public usage)
- `APP_AUTH_MODE` (`disabled` or `basic`)
- `APP_AUTH_BASIC_USERS_JSON` (basic login users with `password`, `workspace_id`, optional `role`, optional `plan_slug`)
- `APP_WORKSPACE_PLAN_MAP_JSON` (optional workspace-to-plan map)
- `APP_STRIPE_CHECKOUT_URL` (upgrade CTA link)
- `APP_STRIPE_PORTAL_URL` (billing portal link)
- `APP_CONTACT_SALES_URL` (enterprise/contact sales link)
- `APP_TRIAL_END_DATE` (display trial expiry in sidebar)
- `APP_SYNC_DEFAULT_FREQUENCY` (default sync job frequency, e.g. `daily`)
- `APP_SYNC_DEFAULT_HOUR_UTC` (default UTC hour for sync jobs)
- `APP_WEBHOOK_TIMEOUT_SECONDS` (timeout for webhook test dispatch)
- `APP_WEBHOOK_ALLOWED_HOSTS` (comma-separated webhook host allowlist for alert destinations)
- `APP_ENFORCE_HTTPS_WEBHOOKS` (default: `1`; enforce HTTPS webhook targets except localhost)
- `APP_WEBHOOK_SIGNING_SECRET` (optional HMAC secret for `X-D2C-Signature` webhook header)
- `APP_PARTNER_REFERRAL_URL` (optional link shown in Partner Hub for referral flow)
- `APP_COPILOT_MAX_RECOMMENDATIONS` (max actions generated per Growth Copilot batch; default `6`)
- `APP_FORECAST_PERIOD_DAYS` (default horizon for ROI Forecast in days; default `90`)
- `APP_AUTOPILOT_MAX_ACTIONS` (max actions queued per Goal Tracker autopilot run; default `8`)
- `APP_SERVICE_AUTH_TOKEN` (bearer token attached to app -> service calls)
- `SERVICE_API_AUTH_TOKEN` (token required by service APIs when set)
- `SERVICE_HEALTH_REQUIRE_AUTH` (default: `0`; set `1` to protect service `/health`)
- `APP_DISABLE_LOCAL_STATE_FALLBACK` (set `1` in production to require service-backed state/policy paths)
- `APP_DISABLE_LOCAL_PIPELINE_FALLBACK` (set `1` in production to require pipeline service)
## Real export connectors (Shopify + GA4)
Map real platform exports into canonical raw tables:
- `python -m python.pipeline.prepare_real_exports --shopify-orders path/to/shopify_orders.csv --ga4-sessions path/to/ga4_sessions.csv --output-dir data/raw --validation-mode strict`

Connector details and template headers are in `docs/connectors.md` and `data/raw/templates/`.

## Optional PostgreSQL mode
Set `DATABASE_URL` in `.env` and run:
- `python -m python.pipeline.run_pipeline --data-source postgres --validation-mode strict`

The SQL models in `sql/` can be run in order:
1. `sql/staging/00_setup_raw_tables.sql`
2. `sql/staging/*.sql`
3. `sql/marts/*.sql`
4. `sql/quality/01_data_quality_checks.sql`

## Refresh cadence (v1)
- Every 6 hours: incremental pipeline run
- Daily: full refresh

## Notes
- The included raw CSVs are starter synthetic data for development.
- For production-like behavior, replace/add real D2C exports while keeping the same contract.
- Validation defaults to strict fail-fast mode for reliability; use `--validation-mode warn` only for exploratory ingestion.
- Strict mode enforces business-rule checks too (for example: `clicks <= impressions`, `discount <= gross_revenue`, `refund_amount <= order_gross`, and temporal consistency checks).
- The pipeline also writes `anomaly_report.csv` with warning-level monitoring for CAC spikes, conversion-rate spikes, and refund-ratio spikes.
