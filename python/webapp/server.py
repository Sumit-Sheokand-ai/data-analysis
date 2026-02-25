from __future__ import annotations

import json
import mimetypes
import os
import secrets
from dataclasses import dataclass
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import pandas as pd
from python.analysis.diagnostics import build_channel_metric_deltas, build_overview_deltas, load_snapshot_csv

from python.analysis.entitlements import get_plan, normalize_plan_slug
from python.analysis.optimizer import optimize_budget_allocation
from python.analysis.recommendations import build_growth_recommendations
from python.services.pipeline_service import trigger_pipeline_job
from python.services.policy_service import get_usage_counters


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSION_COOKIE_NAME = "syntellia_session"

REQUIRED_OUTPUTS = [
    "kpi_overview",
    "cac_by_channel",
    "retention_monthly",
    "ltv_by_customer",
    "channel_profitability",
    "data_quality",
    "anomaly_report",
]

CANONICAL_RAW_FILES = {
    "sessions": "raw_sessions.csv",
    "customers": "raw_customers.csv",
    "orders": "raw_orders.csv",
    "refunds": "raw_refunds.csv",
    "marketing_spend": "raw_marketing_spend.csv",
}

DEFAULT_USAGE_COUNTERS = {
    "report_exports": 0,
    "scheduled_reports_created": 0,
    "pipeline_runs": 0,
    "connector_sync_runs": 0,
    "alerts_acknowledged": 0,
    "alert_dispatches": 0,
    "ai_insights_generated": 0,
    "experiments_logged": 0,
    "playbooks_created": 0,
    "forecasts_generated": 0,
    "goal_refreshes": 0,
    "autopilot_actions_generated": 0,
}


@dataclass
class WebAppConfig:
    app_env: str
    data_source: str
    raw_data_dir: Path
    processed_data_dir: Path
    database_url: str
    default_validation_mode: str
    allow_proxy_spend: bool
    pipeline_service_url: str
    pipeline_timeout_seconds: int
    policy_service_url: str
    policy_timeout_seconds: int
    policy_state_file: Path
    service_token: str
    disable_local_pipeline_fallback: bool
    require_auth: bool
    auth_mode: str
    default_workspace: str
    default_role: str
    default_plan: str
    workspace_plan_overrides: dict[str, str]
    basic_auth_users: dict[str, dict[str, str]]
    static_dir: Path


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, str | bool]] = {}
        self._lock = Lock()

    def create(self, context: dict[str, str | bool]) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = dict(context)
        return token

    def get(self, token: str) -> dict[str, str | bool] | None:
        with self._lock:
            value = self._sessions.get(token)
            return dict(value) if isinstance(value, dict) else None

    def delete(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_parse_json_object(raw_value: str) -> dict[str, object]:
    cleaned = str(raw_value).strip()
    if not cleaned:
        return {}
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _normalize_workspace_id(value: str) -> str:
    cleaned = str(value).strip().lower()
    return cleaned or "default"


def _normalize_role(value: str) -> str:
    cleaned = str(value).strip().lower()
    return cleaned or "viewer"


def _workspace_plan_slug(
    *,
    default_plan: str,
    workspace_plan_overrides: dict[str, str],
    workspace_id: str,
    preferred_plan_slug: str = "",
) -> str:
    if str(preferred_plan_slug).strip():
        return normalize_plan_slug(str(preferred_plan_slug))
    normalized_workspace = _normalize_workspace_id(workspace_id)
    mapped_plan = workspace_plan_overrides.get(normalized_workspace)
    if mapped_plan:
        return normalize_plan_slug(mapped_plan)
    return normalize_plan_slug(default_plan)


def _workspace_plan_overrides(raw_json: str) -> dict[str, str]:
    parsed = _safe_parse_json_object(raw_json)
    overrides: dict[str, str] = {}
    for workspace_key, plan_slug in parsed.items():
        workspace_id = _normalize_workspace_id(str(workspace_key))
        overrides[workspace_id] = normalize_plan_slug(str(plan_slug))
    return overrides


def _basic_auth_users(
    *,
    raw_json: str,
    default_workspace: str,
    default_role: str,
    default_plan: str,
    workspace_plan_overrides: dict[str, str],
) -> dict[str, dict[str, str]]:
    parsed = _safe_parse_json_object(raw_json)
    users: dict[str, dict[str, str]] = {}
    for username, record in parsed.items():
        if not isinstance(record, dict):
            continue
        normalized_username = str(username).strip().lower()
        password = str(record.get("password", "")).strip()
        if not normalized_username or not password:
            continue
        workspace_id = _normalize_workspace_id(str(record.get("workspace_id", default_workspace)))
        role = _normalize_role(str(record.get("role", default_role)))
        plan_slug = _workspace_plan_slug(
            default_plan=default_plan,
            workspace_plan_overrides=workspace_plan_overrides,
            workspace_id=workspace_id,
            preferred_plan_slug=str(record.get("plan_slug", "")),
        )
        users[normalized_username] = {
            "password": password,
            "user_id": str(record.get("user_id", normalized_username)).strip().lower() or normalized_username,
            "workspace_id": workspace_id,
            "role": role,
            "plan_slug": plan_slug,
        }
    return users


def load_webapp_config(project_root: Path | None = None) -> WebAppConfig:
    root = project_root or PROJECT_ROOT
    default_workspace = _normalize_workspace_id(os.getenv("APP_AUTH_DEFAULT_WORKSPACE", "default"))
    default_role = _normalize_role(os.getenv("APP_AUTH_DEFAULT_ROLE", "viewer"))
    default_plan = normalize_plan_slug(os.getenv("APP_PLAN", "starter"))
    workspace_overrides = _workspace_plan_overrides(os.getenv("APP_WORKSPACE_PLAN_MAP_JSON", "").strip())
    basic_users = _basic_auth_users(
        raw_json=os.getenv("APP_AUTH_BASIC_USERS_JSON", "").strip(),
        default_workspace=default_workspace,
        default_role=default_role,
        default_plan=default_plan,
        workspace_plan_overrides=workspace_overrides,
    )
    return WebAppConfig(
        app_env=os.getenv("APP_ENV", "development").strip().lower(),
        data_source=os.getenv("DATA_SOURCE", "csv").strip().lower(),
        raw_data_dir=Path(os.getenv("RAW_DATA_DIR", root / "data" / "raw")),
        processed_data_dir=Path(os.getenv("PROCESSED_DATA_DIR", root / "data" / "processed")),
        database_url=os.getenv("DATABASE_URL", "").strip(),
        default_validation_mode=os.getenv("VALIDATION_MODE", "warn").strip().lower(),
        allow_proxy_spend=_env_flag("APP_ALLOW_PROXY_SPEND", default=False),
        pipeline_service_url=os.getenv("APP_PIPELINE_SERVICE_URL", "").strip(),
        pipeline_timeout_seconds=int(os.getenv("APP_PIPELINE_SERVICE_TIMEOUT_SECONDS", "30").strip() or 30),
        policy_service_url=os.getenv("APP_POLICY_SERVICE_URL", "").strip(),
        policy_timeout_seconds=int(os.getenv("APP_POLICY_SERVICE_TIMEOUT_SECONDS", "10").strip() or 10),
        policy_state_file=Path(os.getenv("APP_POLICY_STATE_FILE", root / "data" / "processed" / "policy_state.json")),
        service_token=os.getenv("APP_SERVICE_AUTH_TOKEN", "").strip(),
        disable_local_pipeline_fallback=_env_flag("APP_DISABLE_LOCAL_PIPELINE_FALLBACK", default=False),
        require_auth=_env_flag("APP_REQUIRE_AUTH", default=False),
        auth_mode=os.getenv("APP_AUTH_MODE", "disabled").strip().lower(),
        default_workspace=default_workspace,
        default_role=default_role,
        default_plan=default_plan,
        workspace_plan_overrides=workspace_overrides,
        basic_auth_users=basic_users,
        static_dir=root / "web",
    )


def _parse_cookie_header(raw_cookie: str) -> dict[str, str]:
    jar = cookies.SimpleCookie()
    if raw_cookie:
        jar.load(raw_cookie)
    return {key: morsel.value for key, morsel in jar.items()}


def _session_token_from_headers(headers) -> str:
    cookie_header = str(headers.get("Cookie", "")).strip()
    parsed = _parse_cookie_header(cookie_header)
    return str(parsed.get(SESSION_COOKIE_NAME, "")).strip()


def _session_cookie_value(token: str, *, secure: bool = False, clear: bool = False) -> str:
    if clear:
        parts = [f"{SESSION_COOKIE_NAME}=deleted", "Path=/", "Max-Age=0", "HttpOnly", "SameSite=Lax"]
    else:
        parts = [f"{SESSION_COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def _anonymous_context(config: WebAppConfig) -> dict[str, str | bool]:
    workspace_id = _normalize_workspace_id(config.default_workspace)
    return {
        "authenticated": False,
        "user_id": "anonymous",
        "workspace_id": workspace_id,
        "role": _normalize_role(config.default_role),
        "plan_slug": _workspace_plan_slug(
            default_plan=config.default_plan,
            workspace_plan_overrides=config.workspace_plan_overrides,
            workspace_id=workspace_id,
        ),
    }


def _request_context(
    *,
    config: WebAppConfig,
    session_store: SessionStore,
    headers,
) -> dict[str, str | bool]:
    token = _session_token_from_headers(headers)
    if token:
        stored = session_store.get(token)
        if stored is not None:
            workspace_id = _normalize_workspace_id(str(stored.get("workspace_id", config.default_workspace)))
            preferred_plan = str(stored.get("plan_slug", "")).strip()
            return {
                "authenticated": True,
                "user_id": str(stored.get("user_id", "anonymous")).strip().lower() or "anonymous",
                "workspace_id": workspace_id,
                "role": _normalize_role(str(stored.get("role", config.default_role))),
                "plan_slug": _workspace_plan_slug(
                    default_plan=config.default_plan,
                    workspace_plan_overrides=config.workspace_plan_overrides,
                    workspace_id=workspace_id,
                    preferred_plan_slug=preferred_plan,
                ),
            }
    return _anonymous_context(config)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return float(value)
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value)


def _write_json(
    handler: BaseHTTPRequestHandler,
    status_code: int,
    payload: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(_json_safe(payload), ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if extra_headers:
        for key, value in extra_headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or 0)
    if content_length <= 0:
        return {}
    raw = handler.rfile.read(content_length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON payload.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON payload must be an object.")
    return parsed


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _looks_proxy_marketing_spend(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    if "campaign" not in df.columns or "channel" not in df.columns:
        return False
    campaign = df["campaign"].astype(str).str.strip().str.lower()
    channel = df["channel"].astype(str).str.strip().str.lower()
    proxy_campaign_markers = {"(direct)", "(organic/referral)"}
    has_proxy_campaigns = campaign.isin(proxy_campaign_markers).any()
    has_direct_channel = channel.eq("direct").any()
    return bool(has_proxy_campaigns or has_direct_channel)


def _is_proxy_marketing_spend_present(config: WebAppConfig) -> bool:
    spend_path = config.raw_data_dir / "raw_marketing_spend.csv"
    if not spend_path.exists():
        return False
    spend_df = _load_csv(spend_path)
    return _looks_proxy_marketing_spend(spend_df)


def _missing_outputs(config: WebAppConfig) -> list[str]:
    missing: list[str] = []
    for name in REQUIRED_OUTPUTS:
        path = config.processed_data_dir / f"{name}.csv"
        if not path.exists():
            missing.append(name)
    return missing


def _raw_contract_status(config: WebAppConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset, filename in CANONICAL_RAW_FILES.items():
        path = config.raw_data_dir / filename
        exists = path.exists()
        row_count = 0
        if exists:
            frame = _load_csv(path)
            row_count = int(len(frame))
        rows.append(
            {
                "dataset": dataset,
                "file": filename,
                "exists": bool(exists),
                "rows": row_count,
            }
        )
    return rows


def _build_readiness_payload(config: WebAppConfig) -> dict[str, Any]:
    raw_status = _raw_contract_status(config)
    raw_contract_ready = all(bool(row.get("exists", False)) for row in raw_status)
    proxy_detected = _is_proxy_marketing_spend_present(config)
    missing = _missing_outputs(config)
    outputs_ready = len(missing) == 0
    if not raw_contract_ready:
        status = "blocked"
        message = "Raw contract is incomplete. Add required raw files before using analytics views."
    elif proxy_detected and not config.allow_proxy_spend:
        status = "blocked"
        message = "Proxy/dummy spend data detected. Replace with real marketing spend data."
    elif not outputs_ready:
        status = "pending"
        message = "Processed outputs are missing. Run pipeline to generate dashboard data."
    else:
        status = "ready"
        message = "Dashboard data is ready."
    return {
        "status": status,
        "message": message,
        "raw_contract_ready": raw_contract_ready,
        "proxy_spend_detected": proxy_detected,
        "outputs_ready": outputs_ready,
        "missing_outputs": missing,
        "raw_files": raw_status,
    }


def _overview_payload(config: WebAppConfig) -> dict[str, Any]:
    overview = _load_csv(config.processed_data_dir / "kpi_overview.csv")
    if overview.empty or not {"metric", "value"}.issubset(overview.columns):
        return {}
    metrics: dict[str, Any] = {}
    for row in overview.itertuples(index=False):
        key = str(getattr(row, "metric", "")).strip()
        if not key:
            continue
        raw_value = getattr(row, "value", None)
        try:
            numeric = pd.to_numeric(raw_value, errors="coerce")
            metrics[key] = None if pd.isna(numeric) else float(numeric)
        except Exception:
            metrics[key] = str(raw_value)
    return metrics


def _table_records(frame: pd.DataFrame, *, max_rows: int = 200) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clipped = frame.head(max(int(max_rows), 1))
    safe = clipped.where(pd.notna(clipped), None)
    return [dict(record) for record in safe.to_dict("records")]


def _channel_performance_payload(config: WebAppConfig) -> list[dict[str, Any]]:
    frame = _load_csv(config.processed_data_dir / "channel_profitability.csv")
    if frame.empty:
        return []
    if "ltv_cac_ratio" in frame.columns:
        frame["ltv_cac_ratio"] = pd.to_numeric(frame["ltv_cac_ratio"], errors="coerce")
        frame = frame.sort_values("ltv_cac_ratio", ascending=False, na_position="last")
    return _table_records(frame, max_rows=100)


def _alerts_payload(config: WebAppConfig) -> list[dict[str, Any]]:
    frame = _load_csv(config.processed_data_dir / "anomaly_report.csv")
    if frame.empty:
        return []
    if "date" in frame.columns:
        frame["_date_sort"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values("_date_sort", ascending=False, na_position="last").drop(columns=["_date_sort"])
    return _table_records(frame, max_rows=200)


def _data_quality_payload(config: WebAppConfig) -> list[dict[str, Any]]:
    return _table_records(_load_csv(config.processed_data_dir / "data_quality.csv"), max_rows=100)
def _retention_payload(config: WebAppConfig) -> list[dict[str, Any]]:
    frame = _load_csv(config.processed_data_dir / "retention_monthly.csv")
    if frame.empty:
        return []
    if "cohort_month" in frame.columns:
        frame["cohort_month"] = pd.to_datetime(frame["cohort_month"], errors="coerce").dt.strftime("%Y-%m")
    if {"cohort_month", "month_index"}.issubset(frame.columns):
        frame = frame.sort_values(["cohort_month", "month_index"], ascending=[False, True], na_position="last")
    return _table_records(frame, max_rows=240)


def _ltv_payload(config: WebAppConfig) -> list[dict[str, Any]]:
    frame = _load_csv(config.processed_data_dir / "ltv_by_customer.csv")
    if frame.empty:
        return []
    if "predicted_ltv" in frame.columns:
        frame["predicted_ltv"] = pd.to_numeric(frame["predicted_ltv"], errors="coerce")
        frame = frame.sort_values("predicted_ltv", ascending=False, na_position="last")
    elif "realized_ltv" in frame.columns:
        frame["realized_ltv"] = pd.to_numeric(frame["realized_ltv"], errors="coerce")
        frame = frame.sort_values("realized_ltv", ascending=False, na_position="last")
    return _table_records(frame, max_rows=200)


def _what_changed_payload(config: WebAppConfig) -> dict[str, list[dict[str, Any]]]:
    previous_dir = config.processed_data_dir / "previous"
    current_overview = _load_csv(config.processed_data_dir / "kpi_overview.csv")
    current_cac = _load_csv(config.processed_data_dir / "cac_by_channel.csv")
    current_profitability = _load_csv(config.processed_data_dir / "channel_profitability.csv")

    previous_overview = load_snapshot_csv(previous_dir / "kpi_overview.csv")
    previous_cac = load_snapshot_csv(previous_dir / "cac_by_channel.csv")
    previous_profitability = load_snapshot_csv(previous_dir / "channel_profitability.csv")

    overview_deltas = build_overview_deltas(current_overview, previous_overview)
    cac_deltas = build_channel_metric_deltas(current_cac, previous_cac, metric_col="cac")
    ltv_cac_deltas = build_channel_metric_deltas(
        current_profitability,
        previous_profitability,
        metric_col="ltv_cac_ratio",
    )
    return {
        "overview_deltas": _table_records(overview_deltas, max_rows=100),
        "cac_deltas": _table_records(cac_deltas, max_rows=100),
        "ltv_cac_deltas": _table_records(ltv_cac_deltas, max_rows=100),
    }


def _recommendations_payload(config: WebAppConfig) -> list[dict[str, Any]]:
    recommendations = build_growth_recommendations(
        cac_df=_load_csv(config.processed_data_dir / "cac_by_channel.csv"),
        profitability_df=_load_csv(config.processed_data_dir / "channel_profitability.csv"),
        retention_df=_load_csv(config.processed_data_dir / "retention_monthly.csv"),
        anomaly_df=_load_csv(config.processed_data_dir / "anomaly_report.csv"),
        max_items=8,
    )
    return _table_records(recommendations, max_rows=20)


def _optimizer_payload(
    config: WebAppConfig,
    *,
    total_budget: float,
    target_max_cac: float,
    reserve_pct: float,
) -> dict[str, Any]:
    cac = _load_csv(config.processed_data_dir / "cac_by_channel.csv")
    profitability = _load_csv(config.processed_data_dir / "channel_profitability.csv")
    optimized, summary = optimize_budget_allocation(
        cac_df=cac,
        profitability_df=profitability,
        total_budget=float(max(total_budget, 0.0)),
        target_max_cac=float(max(target_max_cac, 0.0)),
        reserve_pct=float(reserve_pct),
    )
    return {
        "summary": {
            "usable_budget": float(summary.usable_budget),
            "projected_customers": float(summary.projected_customers),
            "projected_value": float(summary.projected_value),
            "blended_cac": float(summary.blended_cac),
            "blended_value_to_spend": float(summary.blended_value_to_spend),
        },
        "allocations": _table_records(optimized, max_rows=100),
    }


def _usage_payload(config: WebAppConfig, context: dict[str, str | bool]) -> dict[str, int]:
    try:
        usage = get_usage_counters(
            default_counters=DEFAULT_USAGE_COUNTERS,
            state_file=config.policy_state_file,
            service_url=config.policy_service_url,
            timeout_seconds=config.policy_timeout_seconds,
            workspace_id=str(context.get("workspace_id", config.default_workspace)),
            user_id=str(context.get("user_id", "anonymous")),
            user_role=str(context.get("role", config.default_role)),
            service_token=config.service_token,
        )
        return {key: int(usage.get(key, default_value)) for key, default_value in DEFAULT_USAGE_COUNTERS.items()}
    except Exception:
        return dict(DEFAULT_USAGE_COUNTERS)


def _plan_payload(plan_slug: str) -> dict[str, Any]:
    plan = get_plan(plan_slug)
    return {
        "slug": plan.slug,
        "display_name": plan.display_name,
        "monthly_price_usd": int(plan.monthly_price_usd),
        "annual_price_usd": int(plan.annual_price_usd),
        "limits": {key: int(value) for key, value in plan.limits.items()},
        "features": sorted(list(plan.feature_flags)),
    }


def _auth_payload(config: WebAppConfig, context: dict[str, str | bool]) -> dict[str, Any]:
    plan_slug = str(context.get("plan_slug", config.default_plan))
    return {
        "require_auth": bool(config.require_auth),
        "authenticated": bool(context.get("authenticated", False)),
        "user_id": str(context.get("user_id", "anonymous")),
        "workspace_id": str(context.get("workspace_id", config.default_workspace)),
        "role": str(context.get("role", config.default_role)),
        "plan": _plan_payload(plan_slug),
    }


def _dashboard_payload(config: WebAppConfig, context: dict[str, str | bool]) -> dict[str, Any]:
    plan_slug = str(context.get("plan_slug", config.default_plan))
    plan = _plan_payload(plan_slug)
    usage = _usage_payload(config, context)
    cac_frame = _load_csv(config.processed_data_dir / "cac_by_channel.csv")
    default_budget = float(pd.to_numeric(cac_frame.get("total_cost"), errors="coerce").fillna(0).sum()) if not cac_frame.empty else 0.0
    if default_budget <= 0:
        default_budget = 10000.0
    export_limit = int(plan["limits"].get("monthly_report_exports", 0))
    exports_used = int(usage.get("report_exports", 0))
    return {
        "auth": _auth_payload(config, context),
        "readiness": _build_readiness_payload(config),
        "overview": _overview_payload(config),
        "channel_performance": _channel_performance_payload(config),
        "alerts": _alerts_payload(config),
        "data_quality": _data_quality_payload(config),
        "retention": _retention_payload(config),
        "ltv_customers": _ltv_payload(config),
        "what_changed": _what_changed_payload(config),
        "recommendations": _recommendations_payload(config),
        "optimizer_defaults": {
            "total_budget": round(float(default_budget), 2),
            "target_max_cac": 80.0,
            "reserve_pct": 10.0,
        },
        "billing": {
            "plan": plan,
            "usage": usage,
            "report_exports_left": max(export_limit - exports_used, 0),
        },
    }


def _ensure_authorized(
    handler: BaseHTTPRequestHandler,
    *,
    config: WebAppConfig,
    context: dict[str, str | bool],
) -> bool:
    if not config.require_auth:
        return True
    if bool(context.get("authenticated", False)):
        return True
    _write_json(
        handler,
        401,
        {
            "status": "error",
            "message": "Authentication required.",
            "require_auth": True,
            "authenticated": False,
        },
    )
    return False


def _resolve_static_file(static_dir: Path, request_path: str) -> Path | None:
    relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
    candidate = (static_dir / relative).resolve()
    static_root = static_dir.resolve()
    if static_root not in candidate.parents and candidate != static_root:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def create_webapp_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8501,
    config: WebAppConfig | None = None,
    session_store: SessionStore | None = None,
) -> ThreadingHTTPServer:
    resolved_config = config or load_webapp_config()
    resolved_sessions = session_store or SessionStore()

    class WebAppRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _context(self) -> dict[str, str | bool]:
            return _request_context(
                config=resolved_config,
                session_store=resolved_sessions,
                headers=self.headers,
            )

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Allow", "GET,POST,OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path == "/health":
                _write_json(self, 200, {"status": "ok", "service": "syntellia-browser-webapp"})
                return

            if path == "/api/auth/me":
                context = self._context()
                if not _ensure_authorized(self, config=resolved_config, context=context):
                    return
                _write_json(self, 200, {"status": "ok", **_auth_payload(resolved_config, context)})
                return

            if path == "/api/readiness":
                context = self._context()
                if not _ensure_authorized(self, config=resolved_config, context=context):
                    return
                _write_json(self, 200, {"status": "ok", "readiness": _build_readiness_payload(resolved_config)})
                return

            if path == "/api/dashboard":
                context = self._context()
                if not _ensure_authorized(self, config=resolved_config, context=context):
                    return
                _write_json(self, 200, {"status": "ok", "dashboard": _dashboard_payload(resolved_config, context)})
                return

            if path.startswith("/api/"):
                _write_json(self, 404, {"status": "error", "message": "Not found"})
                return

            static_file = _resolve_static_file(resolved_config.static_dir, path)
            if static_file is None:
                self.send_error(404)
                return
            body = static_file.read_bytes()
            content_type, _ = mimetypes.guess_type(str(static_file))
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            path = parsed_url.path

            if path == "/api/auth/login":
                if resolved_config.auth_mode != "basic":
                    _write_json(self, 400, {"status": "error", "message": "Basic auth mode is not enabled."})
                    return
                try:
                    payload = _read_json_body(self)
                except ValueError as exc:
                    _write_json(self, 400, {"status": "error", "message": str(exc)})
                    return
                username = str(payload.get("username", "")).strip().lower()
                password = str(payload.get("password", ""))
                account = resolved_config.basic_auth_users.get(username)
                if account is None or password != str(account.get("password", "")):
                    _write_json(self, 401, {"status": "error", "message": "Invalid username or password."})
                    return
                context = {
                    "authenticated": True,
                    "user_id": str(account.get("user_id", username)),
                    "workspace_id": str(account.get("workspace_id", resolved_config.default_workspace)),
                    "role": str(account.get("role", resolved_config.default_role)),
                    "plan_slug": str(account.get("plan_slug", resolved_config.default_plan)),
                }
                token = resolved_sessions.create(context)
                _write_json(
                    self,
                    200,
                    {"status": "ok", **_auth_payload(resolved_config, context)},
                    extra_headers={
                        "Set-Cookie": _session_cookie_value(
                            token,
                            secure=resolved_config.app_env in {"production", "prod"},
                        )
                    },
                )
                return

            if path == "/api/auth/logout":
                token = _session_token_from_headers(self.headers)
                if token:
                    resolved_sessions.delete(token)
                _write_json(
                    self,
                    200,
                    {"status": "ok"},
                    extra_headers={
                        "Set-Cookie": _session_cookie_value(
                            "",
                            secure=resolved_config.app_env in {"production", "prod"},
                            clear=True,
                        )
                    },
                )
                return

            if path == "/api/pipeline/run":
                context = self._context()
                if not _ensure_authorized(self, config=resolved_config, context=context):
                    return
                try:
                    payload = _read_json_body(self)
                except ValueError as exc:
                    _write_json(self, 400, {"status": "error", "message": str(exc)})
                    return
                requested_mode = str(payload.get("validation_mode", resolved_config.default_validation_mode)).strip().lower()
                if requested_mode not in {"strict", "warn"}:
                    _write_json(self, 400, {"status": "error", "message": "`validation_mode` must be strict or warn."})
                    return
                if resolved_config.disable_local_pipeline_fallback and not resolved_config.pipeline_service_url:
                    _write_json(
                        self,
                        400,
                        {
                            "status": "error",
                            "message": "APP_PIPELINE_SERVICE_URL is required when local pipeline fallback is disabled.",
                        },
                    )
                    return
                try:
                    result = trigger_pipeline_job(
                        data_source=resolved_config.data_source,
                        raw_data_dir=resolved_config.raw_data_dir,
                        processed_data_dir=resolved_config.processed_data_dir,
                        validation_mode=requested_mode,
                        database_url=resolved_config.database_url or None,
                        service_url=resolved_config.pipeline_service_url,
                        timeout_seconds=resolved_config.pipeline_timeout_seconds,
                        workspace_id=str(context.get("workspace_id", resolved_config.default_workspace)),
                        user_id=str(context.get("user_id", "anonymous")),
                        user_role=str(context.get("role", resolved_config.default_role)),
                        service_token=resolved_config.service_token,
                    )
                except Exception as exc:
                    _write_json(self, 500, {"status": "error", "message": f"Pipeline run failed: {exc}"})
                    return
                _write_json(
                    self,
                    200,
                    {
                        "status": "ok",
                        "result": result,
                        "readiness": _build_readiness_payload(resolved_config),
                    },
                )
                return

            if path == "/api/optimizer/run":
                context = self._context()
                if not _ensure_authorized(self, config=resolved_config, context=context):
                    return
                try:
                    payload = _read_json_body(self)
                except ValueError as exc:
                    _write_json(self, 400, {"status": "error", "message": str(exc)})
                    return
                try:
                    total_budget = float(payload.get("total_budget", 0))
                    target_max_cac = float(payload.get("target_max_cac", 0))
                    reserve_pct = float(payload.get("reserve_pct", 0))
                except (TypeError, ValueError):
                    _write_json(
                        self,
                        400,
                        {
                            "status": "error",
                            "message": "`total_budget`, `target_max_cac`, and `reserve_pct` must be numeric.",
                        },
                    )
                    return
                if reserve_pct < 0 or reserve_pct > 95:
                    _write_json(
                        self,
                        400,
                        {
                            "status": "error",
                            "message": "`reserve_pct` must be between 0 and 95.",
                        },
                    )
                    return
                result = _optimizer_payload(
                    resolved_config,
                    total_budget=total_budget,
                    target_max_cac=target_max_cac,
                    reserve_pct=reserve_pct,
                )
                _write_json(self, 200, {"status": "ok", "optimizer": result})
                return
            _write_json(self, 404, {"status": "error", "message": "Not found"})

    server = ThreadingHTTPServer((host, int(port)), WebAppRequestHandler)
    server.daemon_threads = True
    return server

