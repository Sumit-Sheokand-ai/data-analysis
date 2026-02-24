# Deployment notes (v1)
## Recommended stack
- App: Streamlit Community Cloud
- Database: Neon PostgreSQL
- Orchestration: GitHub Actions cron

## Environment variables
- `DATA_SOURCE` (`csv` or `postgres`)
- `RAW_DATA_DIR`
- `PROCESSED_DATA_DIR`
- `DATABASE_URL` (required for `postgres`)
- `APP_PIPELINE_SERVICE_URL` (optional; if set, pipeline jobs are posted to `{url}/jobs/run`)
- `APP_PIPELINE_SERVICE_TIMEOUT_SECONDS` (optional; request timeout for service mode)
- `APP_INSIGHTS_SERVICE_URL` (optional; if set, automation state is fetched/stored via `{url}/state/{key}`)
- `APP_INSIGHTS_SERVICE_TIMEOUT_SECONDS` (optional; request timeout for insights state service mode)
- `APP_INSIGHTS_STATE_FILE` (optional; local fallback JSON path for automation state)
- `APP_POLICY_SERVICE_URL` (optional; if set, entitlement/usage policy checks run via service endpoints)
- `APP_POLICY_SERVICE_TIMEOUT_SECONDS` (optional; request timeout for policy service mode)
- `APP_POLICY_STATE_FILE` (optional; local fallback JSON path for usage counters)

## Scheduled runs
- Every 6 hours for incremental refresh
- Daily full refresh

## Optional pipeline service mode
- Start service locally: `python -m python.pipeline.run_pipeline_service --host 127.0.0.1 --port 8091`
- Trigger pipeline via service: `python -m python.pipeline.run_pipeline --data-source csv --service-url http://127.0.0.1:8091`
- Health check endpoint: `GET /health`
- Job execution endpoint: `POST /jobs/run` (JSON payload with `data_source`, `raw_data_dir`, `processed_data_dir`, `validation_mode`, optional `database_url`)

## Optional insights automation state service mode
- Start service locally: `python -m python.pipeline.run_insights_service --host 127.0.0.1 --port 8092`
- Health check endpoint: `GET /health`
- State endpoints:
  - `GET /state/{key}`
  - `PUT /state/{key}` with body `{"value": ...}`
- Supported keys: `alert_destinations`, `sync_jobs`, `growth_experiments`, `activation_playbooks`, `goal_targets`, `autopilot_queue`

## Optional entitlements and usage policy service mode
- Start service locally: `python -m python.pipeline.run_policy_service --host 127.0.0.1 --port 8093`
- Health check endpoint: `GET /health`
- Policy endpoints:
  - `GET /plans/{slug}`
  - `GET /entitlements/{slug}/{feature}`
  - `GET /usage`
  - `PUT /usage` with body `{"usage_counters": {...}}`

## Streamlit deploy steps
1. Push repository to GitHub.
2. Connect repository in Streamlit Community Cloud.
3. Set app entrypoint to `app/main.py`.
4. Add environment variables in Streamlit secrets.
5. Trigger initial pipeline run and verify charts/kpis.

## Service cutover runbook (pipeline -> insights -> policy)
1. Start services in staging:
   - `python -m python.pipeline.run_pipeline_service --host 127.0.0.1 --port 8091`
   - `python -m python.pipeline.run_insights_service --host 127.0.0.1 --port 8092`
   - `python -m python.pipeline.run_policy_service --host 127.0.0.1 --port 8093`
2. Run preflight health checks:
   - `python -m python.pipeline.check_service_health --pipeline-url http://127.0.0.1:8091 --insights-url http://127.0.0.1:8092 --policy-url http://127.0.0.1:8093`
3. Cut over one service at a time:
   - set `APP_PIPELINE_SERVICE_URL` first and validate pipeline parity
   - set `APP_INSIGHTS_SERVICE_URL` second and validate state write/read paths
   - set `APP_POLICY_SERVICE_URL` last and validate page entitlements + usage counters
4. Keep fallback files configured during rollout:
   - `APP_INSIGHTS_STATE_FILE`
   - `APP_POLICY_STATE_FILE`
5. Monitor for one full schedule cycle and confirm test/metrics parity before finalizing.

## Rollback runbook
1. Unset service URLs in reverse dependency order:
   - unset `APP_POLICY_SERVICE_URL`
   - unset `APP_INSIGHTS_SERVICE_URL`
   - unset `APP_PIPELINE_SERVICE_URL`
2. Keep local fallback files intact (`APP_INSIGHTS_STATE_FILE`, `APP_POLICY_STATE_FILE`) to preserve runtime continuity.
3. Re-run local mode checks:
   - `python -m python.pipeline.run_pipeline --data-source csv --validation-mode strict`
   - `python -m pytest -q`
4. If rollback is due to service instability, archive failing service logs and disable CI `PIPELINE_SERVICE_URL` secret until remediation.
