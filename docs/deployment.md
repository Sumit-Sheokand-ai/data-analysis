# Deployment notes (v1)
## Recommended stack
- App: Browser-native Python web server (serving root `index.html` + JSON APIs)
- Database: Supabase PostgreSQL (Neon also supported)
- Orchestration: GitHub Actions cron
## Split hosting path (GitHub Pages frontend + Render backend)
1. Frontend on GitHub Pages
   - Keep static files in repository root: `index.html`, `styles.css`, `app.js`.
   - In GitHub repository settings, enable Pages from the `main` branch root.
   - Set your frontend domain to `<your-domain>` in Pages custom domain settings.
   - In `index.html`, set `<meta name="api-base" content="https://api.<your-domain>">` when backend domain is live.
2. Backend on Render
   - Deploy this repository as a Render web service using `render.yaml`.
   - Confirm runtime command remains `python -m python.webapp.run_server --host 0.0.0.0 --port ${PORT}`.
   - Set backend custom domain to `api.<your-domain>`.
   - Add required secrets/environment values (see credentials section below).
   - Use `.env` for non-sensitive values and `secrets.env` for sensitive values, then copy those values into Render Environment settings.
3. Domain layout and DNS
   - Point `<your-domain>` DNS to GitHub Pages.
   - Point `api.<your-domain>` DNS to Render service hostname.
   - Keep frontend and backend on HTTPS.
   - Set backend CORS allowed origins to frontend URL only.

## Environment variables
- `APP_ENV` (`development` or `production`)
- `DATA_SOURCE` (`csv` or `postgres`)
- `RAW_DATA_DIR`
- `PROCESSED_DATA_DIR`
- `DATABASE_URL` (required for `postgres`; for Supabase use a Postgres URL with `sslmode=require`)
- `APP_REQUIRE_AUTH` (set `1` for hosted/public deployments)
- `APP_AUTH_MODE` (`disabled` or `basic`)
- `APP_AUTH_BASIC_USERS_JSON` (basic auth user records with workspace binding)
- `APP_WORKSPACE_PLAN_MAP_JSON` (optional workspace->plan overrides)
- `APP_PIPELINE_SERVICE_URL` (optional; if set, pipeline jobs are posted to `{url}/jobs/run`)
- `APP_PIPELINE_SERVICE_TIMEOUT_SECONDS` (optional; request timeout for service mode)
- `APP_INSIGHTS_SERVICE_URL` (optional; if set, automation state is fetched/stored via `{url}/state/{key}`)
- `APP_INSIGHTS_SERVICE_TIMEOUT_SECONDS` (optional; request timeout for insights state service mode)
- `APP_INSIGHTS_STATE_FILE` (optional; local fallback JSON path for automation state)
- `APP_POLICY_SERVICE_URL` (optional; if set, entitlement/usage policy checks run via service endpoints)
- `APP_POLICY_SERVICE_TIMEOUT_SECONDS` (optional; request timeout for policy service mode)
- `APP_POLICY_STATE_FILE` (optional; local fallback JSON path for usage counters)
- `APP_PUBLIC_BASE_URL` (public app URL, e.g. `https://syntellia.ca`)
- `APP_CORS_ALLOWED_ORIGINS` (comma-separated frontend origins allowed to call backend APIs)
- `APP_CORS_ALLOW_CREDENTIALS` (set `1` to allow cookie/session auth from allowed origins)
- `APP_SERVICE_AUTH_TOKEN` (bearer token sent by app to internal services)
- `SERVICE_API_AUTH_TOKEN` (required token for service APIs when configured)
- `SERVICE_HEALTH_REQUIRE_AUTH` (set `1` to require auth on `/health`)
- `APP_DISABLE_LOCAL_STATE_FALLBACK` (set `1` in production)
- `APP_DISABLE_LOCAL_PIPELINE_FALLBACK` (set `1` in production)

## Scheduled runs
- Every 6 hours for incremental refresh
- Daily full refresh

## Optional pipeline service mode
- Start service locally: `python -m python.pipeline.run_pipeline_service --host 127.0.0.1 --port 8091`
- Trigger pipeline via service: `python -m python.pipeline.run_pipeline --data-source csv --service-url http://127.0.0.1:8091`
- Health check endpoint: `GET /health`
- Job execution endpoint: `POST /jobs/run` (JSON payload with `data_source`, `raw_data_dir`, `processed_data_dir`, `validation_mode`, optional `database_url`)
- Auth: set shared `APP_SERVICE_AUTH_TOKEN` (app) and `SERVICE_API_AUTH_TOKEN` (service); app propagates `X-Workspace-Id`, `X-User-Id`, `X-User-Role`

## Optional insights automation state service mode
- Start service locally: `python -m python.pipeline.run_insights_service --host 127.0.0.1 --port 8092`
- Health check endpoint: `GET /health`
- State endpoints:
  - `GET /state/{key}`
  - `PUT /state/{key}` with body `{"value": ...}`
- Supported keys: `alert_destinations`, `sync_jobs`, `growth_experiments`, `activation_playbooks`, `goal_targets`, `autopilot_queue`
- State is now scoped by `workspace_id` (from `X-Workspace-Id` header or `workspace_id` query)

## Optional entitlements and usage policy service mode
- Start service locally: `python -m python.pipeline.run_policy_service --host 127.0.0.1 --port 8093`
- Health check endpoint: `GET /health`
- Policy endpoints:
  - `GET /plans/{slug}`
  - `GET /entitlements/{slug}/{feature}`
  - `GET /usage`
  - `PUT /usage` with body `{"usage_counters": {...}}`
- Usage counters are now scoped by `workspace_id` (from `X-Workspace-Id` header or `workspace_id` query)

## Browser web app deploy steps
1. Push repository to GitHub.
2. Connect repository to your Docker-capable host (for example, Render web service).
3. Ensure container starts with `python -m python.webapp.run_server --host 0.0.0.0 --port ${PORT}`.
4. Set health check path to `/health`.
5. Add environment variables and auth/service secrets.
6. Trigger initial pipeline run and verify dashboard API/UX.
## Credentials/secrets to set or rotate for split-host deployment
- `APP_AUTH_BASIC_USERS_JSON` (basic-auth user store; use strong passwords)
- `DATABASE_URL` (if using postgres mode)
- `APP_SERVICE_AUTH_TOKEN`
- `SERVICE_API_AUTH_TOKEN`
- `APP_CORS_ALLOWED_ORIGINS` should include only your frontend origin, e.g. `https://syntellia.ca`
- `APP_PUBLIC_BASE_URL` should point to frontend origin, e.g. `https://syntellia.ca`
## Supabase database setup (Render backend)
1. In Supabase, open **Project Settings -> Database** and copy your Postgres connection string.
2. Prefer the Supabase pooler connection string for production traffic.
3. In Render service env vars set:
   - `DATA_SOURCE=postgres`
   - `DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>?sslmode=require`
4. Ensure password characters are URL-encoded in `DATABASE_URL`.
5. Redeploy and validate backend health at `/health` before opening the frontend.

## Render custom domain (Syntellia)
1. Open the web service in Render and go to **Settings → Custom Domains**.
2. Add `syntellia.ca` (and optionally `www.syntellia.ca`).
3. Configure DNS records exactly as Render instructs.
4. Wait for TLS issuance and verify `https://syntellia.ca` serves the app.

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
4. Enable service auth:
   - set `SERVICE_API_AUTH_TOKEN` in each service runtime
   - set matching `APP_SERVICE_AUTH_TOKEN` in app runtime
5. Enable hardened production flags:
   - `APP_REQUIRE_AUTH=1`
   - `APP_DISABLE_LOCAL_STATE_FALLBACK=1`
   - `APP_DISABLE_LOCAL_PIPELINE_FALLBACK=1`
6. Monitor for one full schedule cycle and confirm test/metrics parity before finalizing.

## Rollback runbook
1. Unset service URLs in reverse dependency order:
   - unset `APP_POLICY_SERVICE_URL`
   - unset `APP_INSIGHTS_SERVICE_URL`
   - unset `APP_PIPELINE_SERVICE_URL`
2. Disable hardened flags if emergency local fallback is required:
   - set `APP_DISABLE_LOCAL_STATE_FALLBACK=0`
   - set `APP_DISABLE_LOCAL_PIPELINE_FALLBACK=0`
3. Keep local fallback files intact (`APP_INSIGHTS_STATE_FILE`, `APP_POLICY_STATE_FILE`) to preserve runtime continuity.
4. Re-run local mode checks:
   - `python -m python.pipeline.run_pipeline --data-source csv --validation-mode strict`
   - `python -m pytest -q`
5. If rollback is due to service instability, archive failing service logs and disable CI `PIPELINE_SERVICE_URL` secret until remediation.
