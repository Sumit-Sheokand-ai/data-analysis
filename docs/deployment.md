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

## Scheduled runs
- Every 6 hours for incremental refresh
- Daily full refresh

## Streamlit deploy steps
1. Push repository to GitHub.
2. Connect repository in Streamlit Community Cloud.
3. Set app entrypoint to `app/main.py`.
4. Add environment variables in Streamlit secrets.
5. Trigger initial pipeline run and verify charts/kpis.
