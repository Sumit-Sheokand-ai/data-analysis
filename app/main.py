from __future__ import annotations
import os
import sys
import json
import shutil
from pathlib import Path
from io import BytesIO
from datetime import datetime, timezone
from zipfile import BadZipFile, ZipFile
from urllib import error as urllib_error
from urllib import request as urllib_request
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
PYTHON_DIR_STR = str(PROJECT_ROOT / "python")
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)
if PYTHON_DIR_STR not in sys.path:
    sys.path.insert(0, PYTHON_DIR_STR)

try:
    from python.analysis.pipeline import run_pipeline
except ModuleNotFoundError:
    from analysis.pipeline import run_pipeline
try:
    from python.analysis.data_loader import load_from_csv
    from python.analysis.validation import DataValidationError, validate_frames
except ModuleNotFoundError:
    from analysis.data_loader import load_from_csv
    from analysis.validation import DataValidationError, validate_frames
try:
    from python.connectors.ad_spend import map_ad_spend_export
except ModuleNotFoundError:
    from connectors.ad_spend import map_ad_spend_export
try:
    from python.analysis.entitlements import (
        get_plan,
        has_feature,
        list_plan_slugs,
        next_plan_for_feature,
        normalize_plan_slug,
    )
except ModuleNotFoundError:
    from analysis.entitlements import (
        get_plan,
        has_feature,
        list_plan_slugs,
        next_plan_for_feature,
        normalize_plan_slug,
    )
try:
    from python.analysis.diagnostics import (
        build_channel_metric_deltas,
        build_overview_deltas,
        load_snapshot_csv,
    )
except ModuleNotFoundError:
    from analysis.diagnostics import (
        build_channel_metric_deltas,
        build_overview_deltas,
        load_snapshot_csv,
    )
try:
    from python.analysis.kpis import attribute_customers_last_non_direct, prep_orders_with_margin
except ModuleNotFoundError:
    from analysis.kpis import attribute_customers_last_non_direct, prep_orders_with_margin
try:
    from python.analysis.optimizer import optimize_budget_allocation
except ModuleNotFoundError:
    from analysis.optimizer import optimize_budget_allocation
try:
    from python.analysis.security import (
        build_webhook_signature,
        mask_destination_target,
        parse_webhook_allowed_hosts,
        validate_webhook_target_url,
    )
except ModuleNotFoundError:
    from analysis.security import (
        build_webhook_signature,
        mask_destination_target,
        parse_webhook_allowed_hosts,
        validate_webhook_target_url,
    )

load_dotenv()


RAW_DIR = Path(os.getenv("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DATA_DIR", PROJECT_ROOT / "data" / "processed"))
APP_DATA_SOURCE = os.getenv("DATA_SOURCE", "csv").strip().lower()
APP_VALIDATION_MODE = os.getenv("VALIDATION_MODE", "warn").strip().lower()
APP_AUTO_RUN_PIPELINE_ON_START = os.getenv("APP_AUTO_RUN_PIPELINE_ON_START", "1").strip().lower() in {"1", "true", "yes", "y"}
APP_ALLOW_PROXY_SPEND = os.getenv("APP_ALLOW_PROXY_SPEND", "0").strip().lower() in {"1", "true", "yes", "y"}
APP_DEFAULT_PLAN = normalize_plan_slug(os.getenv("APP_PLAN", "starter"))
APP_ALLOW_PLAN_SWITCH = os.getenv("APP_ALLOW_PLAN_SWITCH", "1").strip().lower() in {"1", "true", "yes", "y"}
APP_STRIPE_CHECKOUT_URL = os.getenv("APP_STRIPE_CHECKOUT_URL", "").strip()
APP_STRIPE_PORTAL_URL = os.getenv("APP_STRIPE_PORTAL_URL", "").strip()
APP_CONTACT_SALES_URL = os.getenv("APP_CONTACT_SALES_URL", "").strip()
APP_TRIAL_END_DATE = os.getenv("APP_TRIAL_END_DATE", "").strip()
APP_SYNC_DEFAULT_FREQUENCY = os.getenv("APP_SYNC_DEFAULT_FREQUENCY", "daily").strip().lower()
APP_SYNC_DEFAULT_HOUR_UTC = int(os.getenv("APP_SYNC_DEFAULT_HOUR_UTC", "2").strip() or 2)
APP_WEBHOOK_TIMEOUT_SECONDS = int(os.getenv("APP_WEBHOOK_TIMEOUT_SECONDS", "10").strip() or 10)
APP_WEBHOOK_ALLOWED_HOSTS = parse_webhook_allowed_hosts(os.getenv("APP_WEBHOOK_ALLOWED_HOSTS", ""))
APP_ENFORCE_HTTPS_WEBHOOKS = os.getenv("APP_ENFORCE_HTTPS_WEBHOOKS", "1").strip().lower() in {"1", "true", "yes", "y"}
APP_WEBHOOK_SIGNING_SECRET = os.getenv("APP_WEBHOOK_SIGNING_SECRET", "").strip()
APP_PARTNER_REFERRAL_URL = os.getenv("APP_PARTNER_REFERRAL_URL", "").strip()
RAW_MARKETING_SPEND_PATH = RAW_DIR / "raw_marketing_spend.csv"
PREVIOUS_OUTPUTS_DIR = PROCESSED_DIR / "previous"

REQUIRED_OUTPUTS = [
    "kpi_overview",
    "cac_by_channel",
    "retention_monthly",
    "ltv_by_customer",
    "channel_profitability",
    "data_quality",
    "anomaly_report",
]
PAGE_FEATURE_REQUIREMENTS = {
    "Cohort Retention & LTV": "advanced_analytics",
    "Customer Profitability": "advanced_analytics",
    "Anomaly Alerts": "alert_actions",
    "Budget Planner": "scenario_planner",
    "Scheduled Reports": "scheduled_reports",
    "Connectors & Sync": "connector_health",
    "What Changed": "what_changed_diagnostics",
    "Attribution Deep Dive": "attribution_depth",
    "Scenario Optimizer": "scenario_optimizer",
    "White Label Studio": "white_label_controls",
    "Security Center": "security_center",
    "Enterprise Controls": "enterprise_controls",
    "Partner Hub": "partner_hub",
}

CANONICAL_RAW_FILES = {
    "sessions": "raw_sessions.csv",
    "customers": "raw_customers.csv",
    "orders": "raw_orders.csv",
    "refunds": "raw_refunds.csv",
    "marketing_spend": "raw_marketing_spend.csv",
}
UPLOAD_SESSION_FLAG = "user_uploaded_data_this_session"
ACTIVE_PLAN_STATE_KEY = "active_plan_slug"
USAGE_COUNTERS_STATE_KEY = "usage_counters"
ALERT_DESTINATIONS_STATE_KEY = "alert_destinations"
SYNC_JOBS_STATE_KEY = "sync_jobs"
BRANDING_STATE_KEY = "branding_config"
AUDIT_LOG_STATE_KEY = "audit_log_events"
TEAM_MEMBERS_STATE_KEY = "team_members"
SECURITY_POLICY_STATE_KEY = "security_policy"
PARTNER_PIPELINE_STATE_KEY = "partner_pipeline"

CORE_PAGES = [
    "No-Code Upload Center",
    "Executive Overview",
    "Channel Performance",
    "Data Quality",
    "Billing & Plan",
]
ADVANCED_PAGES = [
    "Connectors & Sync",
    "What Changed",
    "Security Center",
    "Enterprise Controls",
    "Partner Hub",
    "Attribution Deep Dive",
    "Scenario Optimizer",
    "White Label Studio",
    "Cohort Retention & LTV",
    "Customer Profitability",
    "Anomaly Alerts",
    "Budget Planner",
    "Scheduled Reports",
]


def _mark_user_uploaded_data() -> None:
    st.session_state[UPLOAD_SESSION_FLAG] = True


def _clear_user_uploaded_data_flag() -> None:
    st.session_state[UPLOAD_SESSION_FLAG] = False


def _has_user_uploaded_data() -> bool:
    return bool(st.session_state.get(UPLOAD_SESSION_FLAG, False))


def _get_active_plan_slug() -> str:
    if ACTIVE_PLAN_STATE_KEY not in st.session_state:
        st.session_state[ACTIVE_PLAN_STATE_KEY] = APP_DEFAULT_PLAN
    return normalize_plan_slug(st.session_state[ACTIVE_PLAN_STATE_KEY])


def _set_active_plan_slug(slug: str) -> None:
    st.session_state[ACTIVE_PLAN_STATE_KEY] = normalize_plan_slug(slug)


def _current_plan():
    return get_plan(_get_active_plan_slug())


def _has_entitlement(feature: str) -> bool:
    return has_feature(_get_active_plan_slug(), feature)


def _get_usage_counters() -> dict[str, int]:
    if USAGE_COUNTERS_STATE_KEY not in st.session_state:
        st.session_state[USAGE_COUNTERS_STATE_KEY] = {
            "report_exports": 0,
            "scheduled_reports_created": 0,
            "pipeline_runs": 0,
            "connector_sync_runs": 0,
            "alerts_acknowledged": 0,
            "alert_dispatches": 0,
        }
    return st.session_state[USAGE_COUNTERS_STATE_KEY]


def _increment_usage_counter(counter_name: str, amount: int = 1) -> None:
    counters = _get_usage_counters()
    counters[counter_name] = int(counters.get(counter_name, 0)) + int(amount)
    st.session_state[USAGE_COUNTERS_STATE_KEY] = counters

def _get_audit_events() -> list[dict[str, str]]:
    if AUDIT_LOG_STATE_KEY not in st.session_state:
        st.session_state[AUDIT_LOG_STATE_KEY] = []
    return st.session_state[AUDIT_LOG_STATE_KEY]


def _append_audit_event(action: str, outcome: str, detail: str, category: str = "app") -> None:
    events = _get_audit_events()
    events.append(
        {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "category": str(category).strip().lower() or "app",
            "action": str(action).strip(),
            "outcome": str(outcome).strip().lower() or "success",
            "workspace": str(st.session_state.get("workspace_name", "Default Workspace")).strip(),
            "detail": str(detail).strip(),
        }
    )
    st.session_state[AUDIT_LOG_STATE_KEY] = events[-1000:]


def _get_security_policy() -> dict[str, object]:
    if SECURITY_POLICY_STATE_KEY not in st.session_state:
        st.session_state[SECURITY_POLICY_STATE_KEY] = {
            "sso_domain": "",
            "require_sso": False,
            "ip_allowlist": [],
        }
    return st.session_state[SECURITY_POLICY_STATE_KEY]


def _set_security_policy(policy: dict[str, object]) -> None:
    st.session_state[SECURITY_POLICY_STATE_KEY] = {
        "sso_domain": str(policy.get("sso_domain", "")).strip().lower(),
        "require_sso": bool(policy.get("require_sso", False)),
        "ip_allowlist": [str(value).strip() for value in policy.get("ip_allowlist", []) if str(value).strip()],
    }


def _get_team_members() -> list[dict[str, str]]:
    if TEAM_MEMBERS_STATE_KEY not in st.session_state:
        st.session_state[TEAM_MEMBERS_STATE_KEY] = [
            {
                "name": "Workspace Owner",
                "email": "owner@company.com",
                "role": "owner",
                "status": "active",
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    return st.session_state[TEAM_MEMBERS_STATE_KEY]


def _set_team_members(members: list[dict[str, str]]) -> None:
    st.session_state[TEAM_MEMBERS_STATE_KEY] = members


def _get_partner_pipeline() -> list[dict[str, str | float]]:
    if PARTNER_PIPELINE_STATE_KEY not in st.session_state:
        st.session_state[PARTNER_PIPELINE_STATE_KEY] = []
    return st.session_state[PARTNER_PIPELINE_STATE_KEY]


def _set_partner_pipeline(pipeline: list[dict[str, str | float]]) -> None:
    st.session_state[PARTNER_PIPELINE_STATE_KEY] = pipeline


def _get_alert_destinations() -> list[dict[str, str]]:
    if ALERT_DESTINATIONS_STATE_KEY not in st.session_state:
        st.session_state[ALERT_DESTINATIONS_STATE_KEY] = []
    return st.session_state[ALERT_DESTINATIONS_STATE_KEY]


def _add_alert_destination(destination_type: str, target: str, label: str) -> None:
    destinations = _get_alert_destinations()
    normalized_type = destination_type.strip().lower()
    normalized_target = target.strip()
    normalized_label = label.strip() or destination_type.strip().title()
    destinations.append(
        {
            "type": normalized_type,
            "target": normalized_target,
            "label": normalized_label,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    st.session_state[ALERT_DESTINATIONS_STATE_KEY] = destinations
    _append_audit_event(
        action="add_alert_destination",
        outcome="success",
        detail=f"type={normalized_type}, label={normalized_label}, target={mask_destination_target(normalized_type, normalized_target)}",
        category="alerts",
    )


def _remove_alert_destination(index: int) -> None:
    destinations = _get_alert_destinations()
    if 0 <= index < len(destinations):
        removed = destinations.pop(index)
        st.session_state[ALERT_DESTINATIONS_STATE_KEY] = destinations
        _append_audit_event(
            action="remove_alert_destination",
            outcome="success",
            detail=f"label={removed.get('label', '')}, type={removed.get('type', '')}",
            category="alerts",
        )


def _send_test_webhook(url: str, payload: dict) -> tuple[bool, str]:
    allowed, reason = validate_webhook_target_url(
        target=url,
        allowed_hosts=APP_WEBHOOK_ALLOWED_HOSTS,
        enforce_https=APP_ENFORCE_HTTPS_WEBHOOKS,
    )
    if not allowed:
        return False, reason
    try:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if APP_WEBHOOK_SIGNING_SECRET:
            headers["X-D2C-Signature"] = build_webhook_signature(body, APP_WEBHOOK_SIGNING_SECRET)
        req = urllib_request.Request(
            url=url,
            data=body,
            method="POST",
            headers=headers,
        )
        with urllib_request.urlopen(req, timeout=APP_WEBHOOK_TIMEOUT_SECONDS) as resp:  # nosec B310
            code = int(getattr(resp, "status", 200))
        if 200 <= code < 300:
            return True, f"Webhook accepted (HTTP {code})."
        return False, f"Webhook returned HTTP {code}."
    except urllib_error.URLError as exc:
        return False, f"Webhook request failed: {exc}"
    except Exception as exc:
        return False, f"Webhook error: {exc}"


def _dispatch_sample_alert_to_destinations() -> tuple[int, int, list[str]]:
    destinations = _get_alert_destinations()
    if not destinations:
        return 0, 0, []
    success = 0
    fail = 0
    messages: list[str] = []
    payload = {
        "event": "anomaly_test_alert",
        "severity": "warn",
        "detail": "Test dispatch from D2C analytics app",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    for destination in destinations:
        d_type = destination.get("type", "")
        d_target = destination.get("target", "")
        d_label = destination.get("label", d_type)
        if d_type == "webhook":
            ok, msg = _send_test_webhook(d_target, payload)
            if ok:
                success += 1
            else:
                fail += 1
            messages.append(f"{d_label}: {msg}")
        elif d_type == "email":
            success += 1
            messages.append(f"{d_label}: queued (email delivery worker not configured yet).")
        else:
            fail += 1
            messages.append(f"{d_label}: unsupported destination type `{d_type}`.")
    _append_audit_event(
        action="dispatch_test_alert",
        outcome="success" if fail == 0 else ("partial" if success > 0 else "failed"),
        detail=f"destinations={len(destinations)}, success={success}, failed={fail}",
        category="alerts",
    )
    return success, fail, messages


def _get_sync_jobs() -> list[dict[str, str]]:
    if SYNC_JOBS_STATE_KEY not in st.session_state:
        st.session_state[SYNC_JOBS_STATE_KEY] = []
    return st.session_state[SYNC_JOBS_STATE_KEY]


def _upsert_default_sync_job() -> None:
    jobs = _get_sync_jobs()
    if jobs:
        return
    jobs.append(
        {
            "name": "Primary D2C Sync",
            "frequency": APP_SYNC_DEFAULT_FREQUENCY,
            "hour_utc": str(APP_SYNC_DEFAULT_HOUR_UTC),
            "status": "enabled",
        }
    )
    st.session_state[SYNC_JOBS_STATE_KEY] = jobs


def _build_connector_health_table() -> pd.DataFrame:
    rows: list[dict[str, str | int | bool]] = []
    for dataset, filename in CANONICAL_RAW_FILES.items():
        path = RAW_DIR / filename
        exists = path.exists()
        row_count = 0
        modified_utc = ""
        freshness = "missing"
        if exists:
            try:
                row_count = len(pd.read_csv(path))
            except Exception:
                row_count = -1
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            modified_utc = mtime.isoformat()
            age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0
            freshness = "fresh" if age_hours <= 72 else "stale"
        rows.append(
            {
                "connector": dataset,
                "file": filename,
                "available": exists,
                "rows": row_count,
                "last_modified_utc": modified_utc,
                "freshness": freshness,
            }
        )
    return pd.DataFrame(rows)


def _backup_processed_outputs_before_run() -> None:
    if not PROCESSED_DIR.exists():
        return
    PREVIOUS_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_OUTPUTS:
        src = PROCESSED_DIR / f"{name}.csv"
        if src.exists():
            dst = PREVIOUS_OUTPUTS_DIR / src.name
            shutil.copy2(src, dst)


def _load_previous_output(name: str) -> pd.DataFrame:
    return load_snapshot_csv(PREVIOUS_OUTPUTS_DIR / f"{name}.csv")


def _available_pages_for_current_plan(show_advanced_pages: bool) -> list[str]:
    pages = list(CORE_PAGES)
    if show_advanced_pages:
        for page in ADVANCED_PAGES:
            required_feature = PAGE_FEATURE_REQUIREMENTS.get(page)
            if required_feature is None or _has_entitlement(required_feature):
                pages.append(page)
    return pages


def _show_upgrade_cta(feature: str, reason: str) -> None:
    st.warning(reason)
    next_plan = next_plan_for_feature(_get_active_plan_slug(), feature)
    if next_plan is not None:
        st.info(
            f"Upgrade to **{next_plan.display_name}** to unlock this feature "
            f"(${next_plan.monthly_price_usd}/month)."
        )
    if APP_STRIPE_CHECKOUT_URL:
        st.markdown(f"[Upgrade now]({APP_STRIPE_CHECKOUT_URL})")
    if APP_STRIPE_PORTAL_URL:
        st.markdown(f"[Manage billing]({APP_STRIPE_PORTAL_URL})")
    if APP_CONTACT_SALES_URL:
        st.markdown(f"[Contact sales]({APP_CONTACT_SALES_URL})")


def _render_workspace_and_plan_sidebar() -> None:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Workspace & Plan")
    workspace_name = st.sidebar.text_input(
        "Workspace",
        value=st.session_state.get("workspace_name", "Default Workspace"),
        help="Name shown in exports and scheduled reports.",
    )
    st.session_state["workspace_name"] = workspace_name

    current_slug = _get_active_plan_slug()
    current_plan = _current_plan()
    if APP_ALLOW_PLAN_SWITCH:
        all_plan_slugs = list(list_plan_slugs())
        selected_slug = st.sidebar.selectbox(
            "Plan",
            options=all_plan_slugs,
            index=all_plan_slugs.index(current_slug),
            format_func=lambda slug: (
                f"{get_plan(slug).display_name} (${get_plan(slug).monthly_price_usd}/mo)"
                if get_plan(slug).monthly_price_usd > 0
                else f"{get_plan(slug).display_name} (Custom)"
            ),
        )
        _set_active_plan_slug(selected_slug)
        current_plan = _current_plan()
    else:
        st.sidebar.caption(f"Plan: **{current_plan.display_name}**")

    if APP_TRIAL_END_DATE:
        st.sidebar.caption(f"Trial ends: `{APP_TRIAL_END_DATE}`")

    st.sidebar.caption(
        f"Limits: stores {current_plan.limits['max_stores']} • "
        f"workspaces {current_plan.limits['max_workspaces']} • "
        f"exports/mo {current_plan.limits['monthly_report_exports']}"
    )
    if APP_STRIPE_CHECKOUT_URL:
        st.sidebar.markdown(f"[Upgrade plan]({APP_STRIPE_CHECKOUT_URL})")
    if APP_STRIPE_PORTAL_URL:
        st.sidebar.markdown(f"[Billing portal]({APP_STRIPE_PORTAL_URL})")


def _get_branding_config() -> dict[str, str]:
    if BRANDING_STATE_KEY not in st.session_state:
        st.session_state[BRANDING_STATE_KEY] = {
            "brand_name": "D2C Marketing & Customer Profitability Analytics",
            "subtitle": "CAC, LTV, retention, and profitability insights",
            "primary_color": "#2f6df6",
            "logo_url": "",
        }
    return st.session_state[BRANDING_STATE_KEY]


def _set_branding_config(config: dict[str, str]) -> None:
    st.session_state[BRANDING_STATE_KEY] = {
        "brand_name": str(config.get("brand_name", "")).strip(),
        "subtitle": str(config.get("subtitle", "")).strip(),
        "primary_color": str(config.get("primary_color", "#2f6df6")).strip(),
        "logo_url": str(config.get("logo_url", "")).strip(),
    }


def _apply_branding_styles() -> None:
    config = _get_branding_config()
    color = config.get("primary_color", "#2f6df6").strip() or "#2f6df6"
    st.markdown(
        f"""
        <style>
        .stApp a {{ color: {color}; }}
        .stMetric > label {{ color: {color}; font-weight: 600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_brand_header() -> None:
    config = _get_branding_config()
    brand_name = config.get("brand_name", "").strip() or "D2C Marketing & Customer Profitability Analytics"
    subtitle = config.get("subtitle", "").strip() or "CAC, LTV, retention, and profitability insights"
    logo_url = config.get("logo_url", "").strip()
    if logo_url:
        st.image(logo_url, width=72)
    st.title(brand_name)
    st.caption(subtitle)


def _safe_load_raw_frames() -> dict[str, pd.DataFrame] | None:
    try:
        return load_from_csv(RAW_DIR)
    except Exception:
        return None


def _has_full_raw_contract() -> bool:
    return all((RAW_DIR / filename).exists() for filename in CANONICAL_RAW_FILES.values())


def _is_real_data_ready() -> bool:
    if not _has_full_raw_contract():
        return False
    if APP_ALLOW_PROXY_SPEND:
        return True
    return not _is_proxy_marketing_spend_present()


def _can_access_analytics_pages() -> tuple[bool, str]:
    if _has_user_uploaded_data():
        return True, ""
    if not _has_full_raw_contract():
        return False, "This app is upload-first. Please upload your own data before opening analytics pages."
    if not APP_ALLOW_PROXY_SPEND and _is_proxy_marketing_spend_present():
        return False, "Proxy/dummy marketing spend data detected. Upload real spend data first."
    return True, "Using previously uploaded real data already present on this app instance."


def _load_csv(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


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


def _is_proxy_marketing_spend_present() -> bool:
    if not RAW_MARKETING_SPEND_PATH.exists():
        return False
    try:
        spend_df = pd.read_csv(RAW_MARKETING_SPEND_PATH)
    except Exception:
        return False
    return _looks_proxy_marketing_spend(spend_df)


def _clear_processed_outputs() -> None:
    if not PROCESSED_DIR.exists():
        return
    for path in PROCESSED_DIR.glob("*.csv"):
        path.unlink(missing_ok=True)


def _replace_marketing_spend_from_uploaded_csv(uploaded_file) -> tuple[bool, str]:
    if uploaded_file is None:
        return False, "Please upload an ad spend CSV first."
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    temp_input = RAW_DIR / "_uploaded_marketing_spend.csv"
    temp_input.write_bytes(uploaded_file.getbuffer())
    try:
        mapped = map_ad_spend_export(
            input_csv=temp_input,
            output_marketing_spend_csv=RAW_MARKETING_SPEND_PATH,
        )
    except Exception as exc:
        _append_audit_event(
            action="replace_marketing_spend",
            outcome="failed",
            detail=f"error={exc}",
            category="data",
        )
        return False, f"Could not map uploaded spend file: {exc}"
    finally:
        temp_input.unlink(missing_ok=True)

    _clear_processed_outputs()
    _mark_user_uploaded_data()
    _append_audit_event(
        action="replace_marketing_spend",
        outcome="success",
        detail=f"rows={len(mapped):,}",
        category="data",
    )
    return True, f"Replaced marketing spend with {len(mapped):,} validated rows from your upload."


def _missing_outputs() -> list[str]:
    return [name for name in REQUIRED_OUTPUTS if not (PROCESSED_DIR / f"{name}.csv").exists()]


def _ensure_processed_outputs() -> tuple[bool, str]:
    if not APP_ALLOW_PROXY_SPEND and _is_proxy_marketing_spend_present():
        return (
            False,
            "Proxy/dummy marketing spend data detected. Upload a real ad spend CSV from the sidebar "
            "and click 'Replace Spend Data'.",
        )
    missing = _missing_outputs()
    if not missing:
        return True, ""

    if not APP_AUTO_RUN_PIPELINE_ON_START:
        return False, (
            "Processed outputs are missing and auto-build is disabled. "
            "Run the pipeline first, or set APP_AUTO_RUN_PIPELINE_ON_START=1."
        )

    if APP_DATA_SOURCE not in {"csv", "postgres"}:
        return False, f"Unsupported DATA_SOURCE `{APP_DATA_SOURCE}`. Use `csv` or `postgres`."
    if APP_VALIDATION_MODE not in {"strict", "warn"}:
        return False, f"Unsupported VALIDATION_MODE `{APP_VALIDATION_MODE}`. Use `strict` or `warn`."
    _backup_processed_outputs_before_run()

    try:
        run_pipeline(
            data_source=APP_DATA_SOURCE,
            raw_data_dir=RAW_DIR,
            processed_data_dir=PROCESSED_DIR,
            validation_mode=APP_VALIDATION_MODE,
        )
    except Exception as exc:
        return False, f"Failed to build processed outputs on startup: {exc}"

    missing_after = _missing_outputs()
    if missing_after:
        return False, f"Output build completed but files are still missing: {missing_after}"
    return True, ""


def _run_pipeline_now(validation_mode: str) -> tuple[bool, str]:
    mode = validation_mode.strip().lower()
    if mode not in {"strict", "warn"}:
        mode = "warn"
    _backup_processed_outputs_before_run()
    try:
        run_pipeline(
            data_source=APP_DATA_SOURCE,
            raw_data_dir=RAW_DIR,
            processed_data_dir=PROCESSED_DIR,
            validation_mode=mode,
        )
    except Exception as exc:
        _append_audit_event(
            action="run_pipeline",
            outcome="failed",
            detail=f"mode={mode}, error={exc}",
            category="pipeline",
        )
        return False, f"Pipeline run failed: {exc}"
    _increment_usage_counter("pipeline_runs")
    _increment_usage_counter("connector_sync_runs")
    _append_audit_event(
        action="run_pipeline",
        outcome="success",
        detail=f"mode={mode}, source={APP_DATA_SOURCE}",
        category="pipeline",
    )
    return True, f"Pipeline completed in `{mode}` mode."


def _render_no_code_sidebar_controls() -> None:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Data Status")

    proxy_detected = _is_proxy_marketing_spend_present()
    if not RAW_MARKETING_SPEND_PATH.exists():
        st.sidebar.info("No marketing spend file uploaded yet.")
    elif proxy_detected:
        st.sidebar.warning("Current spend file looks proxy/dummy.")
    else:
        st.sidebar.success("Current spend file looks real/non-proxy.")
    with st.sidebar.expander("Quick Actions", expanded=False):
        st.caption("Replace spend data or run pipeline instantly.")
        uploaded_spend = st.file_uploader(
            "Upload Real Ad Spend CSV",
            type=["csv"],
            key="real_ad_spend_upload",
            help="Google/Meta/Bing export with spend/clicks/impressions columns.",
        )

        if st.button("Replace Spend Data", use_container_width=True):
            ok, message = _replace_marketing_spend_from_uploaded_csv(uploaded_spend)
            if ok:
                st.success(message)
            else:
                st.error(message)

        if st.button("Remove Dummy/Proxy Spend", use_container_width=True):
            if RAW_MARKETING_SPEND_PATH.exists() and _is_proxy_marketing_spend_present():
                RAW_MARKETING_SPEND_PATH.unlink(missing_ok=True)
                _clear_processed_outputs()
                _clear_user_uploaded_data_flag()
                st.success("Proxy/dummy spend data removed. Upload real spend CSV to continue.")
            elif RAW_MARKETING_SPEND_PATH.exists():
                st.info("Current spend data is not flagged as proxy.")
            else:
                st.info("No raw_marketing_spend.csv found.")

        chosen_validation = st.selectbox("Run pipeline mode", options=["strict", "warn"], index=1)
        if st.button("Run Pipeline Now", use_container_width=True):
            with st.spinner("Running analytics pipeline..."):
                ok, message = _run_pipeline_now(chosen_validation)
            if ok:
                st.success(message)
            else:
                st.error(message)


def _save_uploaded_csv(uploaded_file, target_path: Path) -> tuple[bool, str]:
    if uploaded_file is None:
        return False, "No file selected."
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_path.write_bytes(uploaded_file.getbuffer())
    except Exception as exc:
        return False, f"Failed to save {target_path.name}: {exc}"
    return True, f"Saved {target_path.name}"


def _import_uploaded_zip_bundle(uploaded_file) -> tuple[bool, str]:
    if uploaded_file is None:
        return False, "Please upload a .zip bundle first."

    canonical_lookup = {filename.lower(): filename for filename in CANONICAL_RAW_FILES.values()}
    saved: list[str] = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with ZipFile(BytesIO(uploaded_file.getbuffer())) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                basename = Path(member.filename).name.lower()
                canonical_name = canonical_lookup.get(basename)
                if canonical_name is None:
                    continue
                target = RAW_DIR / canonical_name
                target.write_bytes(archive.read(member))
                saved.append(canonical_name)
    except BadZipFile:
        return False, "The uploaded file is not a valid ZIP archive."
    except Exception as exc:
        return False, f"Could not import ZIP bundle: {exc}"

    if not saved:
        expected = ", ".join(CANONICAL_RAW_FILES.values())
        return False, f"No canonical files found in ZIP. Expected any of: {expected}"

    _clear_processed_outputs()
    _mark_user_uploaded_data()
    unique_saved = sorted(set(saved))
    return True, f"Imported {len(unique_saved)} file(s): {', '.join(unique_saved)}"


def _raw_files_status_table() -> pd.DataFrame:
    rows = []
    for label, filename in CANONICAL_RAW_FILES.items():
        path = RAW_DIR / filename
        exists = path.exists()
        row_count = 0
        if exists:
            try:
                row_count = len(pd.read_csv(path))
            except Exception:
                row_count = -1
        rows.append(
            {
                "dataset": label,
                "file": filename,
                "exists": exists,
                "rows": row_count,
            }
        )
    return pd.DataFrame(rows)


def _raw_contract_readiness(status_df: pd.DataFrame) -> tuple[int, int]:
    total = len(status_df)
    ready = int(status_df["exists"].sum()) if not status_df.empty and "exists" in status_df.columns else 0
    return ready, total


def _validate_raw_contract_strict() -> tuple[bool, str, pd.DataFrame]:
    try:
        frames = load_from_csv(RAW_DIR)
    except Exception as exc:
        return False, f"Could not load canonical raw files: {exc}", pd.DataFrame()
    try:
        report = validate_frames(frames, mode="strict")
    except DataValidationError as exc:
        return False, str(exc), pd.DataFrame()
    except Exception as exc:
        return False, f"Validation failed unexpectedly: {exc}", pd.DataFrame()
    return True, "Strict validation passed.", report


def show_data_upload_center() -> None:
    st.subheader("No-Code Data Upload Center")
    st.caption("Upload your CSVs, validate them, and run the full pipeline from this page.")
    st.info(
        "Step 1: Upload your data document (ZIP) or CSV files • "
        "Step 2: Validate Data (Strict) • "
        "Step 3: Run Pipeline"
    )

    status_df = _raw_files_status_table()
    ready_count, total_count = _raw_contract_readiness(status_df)
    proxy_flag = _is_proxy_marketing_spend_present()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Raw Files Ready", f"{ready_count}/{total_count}")
    m2.metric("Proxy Spend Detected", "Yes" if proxy_flag else "No")
    m3.metric("Processed Outputs", "Ready" if not _missing_outputs() else "Not Ready")
    m4.metric("Real Data Ready", "Yes" if _is_real_data_ready() else "No")
    st.dataframe(status_df, use_container_width=True, hide_index=True)

    st.markdown("### Upload one document (ZIP bundle)")
    bundle_upload = st.file_uploader(
        "data_bundle.zip (contains canonical CSV files)",
        type=["zip"],
        key="upload_zip_bundle",
        help="ZIP may include raw_sessions.csv, raw_customers.csv, raw_orders.csv, raw_refunds.csv, raw_marketing_spend.csv.",
    )
    if st.button("Import ZIP Bundle", use_container_width=True):
        ok, message = _import_uploaded_zip_bundle(bundle_upload)
        if ok:
            st.success(message)
        else:
            st.error(message)

    st.markdown("### Upload canonical raw files")
    u1, u2 = st.columns(2)
    with u1:
        sessions_upload = st.file_uploader("raw_sessions.csv", type=["csv"], key="upload_raw_sessions")
        customers_upload = st.file_uploader("raw_customers.csv", type=["csv"], key="upload_raw_customers")
        orders_upload = st.file_uploader("raw_orders.csv", type=["csv"], key="upload_raw_orders")
    with u2:
        refunds_upload = st.file_uploader("raw_refunds.csv", type=["csv"], key="upload_raw_refunds")
        canonical_spend_upload = st.file_uploader("raw_marketing_spend.csv", type=["csv"], key="upload_raw_marketing_spend")
        ad_export_upload = st.file_uploader(
            "Ad Platform Export (auto-map to raw_marketing_spend.csv)",
            type=["csv"],
            key="upload_ad_platform_export",
        )

    if st.button("Save Uploaded Files", use_container_width=True):
        messages: list[str] = []
        saved_any = False
        for uploaded, filename in [
            (sessions_upload, CANONICAL_RAW_FILES["sessions"]),
            (customers_upload, CANONICAL_RAW_FILES["customers"]),
            (orders_upload, CANONICAL_RAW_FILES["orders"]),
            (refunds_upload, CANONICAL_RAW_FILES["refunds"]),
            (canonical_spend_upload, CANONICAL_RAW_FILES["marketing_spend"]),
        ]:
            if uploaded is not None:
                ok, message = _save_uploaded_csv(uploaded, RAW_DIR / filename)
                messages.append(message if ok else f"ERROR: {message}")
                if ok:
                    saved_any = True

        if ad_export_upload is not None:
            ok, message = _replace_marketing_spend_from_uploaded_csv(ad_export_upload)
            messages.append(message if ok else f"ERROR: {message}")
            if ok:
                saved_any = True

        if saved_any:
            _mark_user_uploaded_data()
            _clear_processed_outputs()
        if messages:
            st.success(" | ".join(messages))
        else:
            st.info("No files were uploaded.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Validate Data (Strict)", use_container_width=True):
            ok, message, report = _validate_raw_contract_strict()
            if ok:
                st.success(message)
                if not report.empty:
                    st.dataframe(report, use_container_width=True)
            else:
                st.error(message)
    with c2:
        run_mode = st.selectbox("Pipeline Mode", options=["strict", "warn"], index=1, key="upload_center_run_mode")
        if st.button("Run Pipeline", use_container_width=True):
            with st.spinner("Running end-to-end analytics pipeline..."):
                ok, message = _run_pipeline_now(run_mode)
            if ok:
                st.success(message)
            else:
                st.error(message)


def load_outputs() -> dict[str, pd.DataFrame]:
    return {
        "overview": _load_csv("kpi_overview"),
        "cac": _load_csv("cac_by_channel"),
        "retention": _load_csv("retention_monthly"),
        "ltv": _load_csv("ltv_by_customer"),
        "profitability": _load_csv("channel_profitability"),
        "quality": _load_csv("data_quality"),
        "anomaly": _load_csv("anomaly_report"),
    }


def _prepare_anomaly(anomaly: pd.DataFrame) -> pd.DataFrame:
    if anomaly.empty:
        return anomaly
    out = anomaly.copy()
    if "severity" in out.columns:
        out["severity"] = out["severity"].astype(str).str.lower().str.strip()
    if "date" in out.columns:
        out["_date_sort"] = pd.to_datetime(out["date"], errors="coerce")
    else:
        out["_date_sort"] = pd.NaT
    return out

def _severity_badge(severity: str) -> str:
    sev = str(severity).strip().lower()
    if sev == "error":
        return "ERROR"
    if sev == "warn":
        return "WARN"
    if sev == "info":
        return "INFO"
    return sev.upper()


def _anomaly_row_id(row: pd.Series) -> str:
    cols = ["date", "channel", "check", "metric", "value", "threshold", "detail"]
    return "|".join(str(row.get(c, "")) for c in cols)


def _normalize_alert_state(anomaly: pd.DataFrame) -> pd.DataFrame:
    out = anomaly.copy()
    if out.empty:
        return out

    out["_row_id"] = out.apply(_anomaly_row_id, axis=1)

    if "anomaly_ack_ids" not in st.session_state:
        st.session_state["anomaly_ack_ids"] = []
    if "anomaly_snooze_until" not in st.session_state:
        st.session_state["anomaly_snooze_until"] = {}

    ack_ids = set(st.session_state["anomaly_ack_ids"])
    snooze_map = st.session_state["anomaly_snooze_until"]
    now = pd.Timestamp.utcnow().tz_localize(None)

    def status_for_row(row_id: str) -> str:
        if row_id in ack_ids:
            return "acknowledged"
        until = snooze_map.get(row_id)
        if until:
            try:
                snooze_until = pd.Timestamp(until).tz_localize(None)
                if snooze_until > now:
                    return "snoozed"
            except Exception:
                pass
        return "active"

    out["_alert_state"] = out["_row_id"].map(status_for_row)
    return out


def _apply_alert_action(alert_df: pd.DataFrame) -> None:
    if alert_df.empty:
        return
    options = alert_df["_row_id"].tolist()
    labels = {
        rid: f"{row.get('date', 'n/a')} | {row.get('channel', 'n/a')} | {row.get('check', 'n/a')}"
        for rid, row in alert_df.set_index("_row_id").to_dict("index").items()
    }
    selected = st.selectbox("Alert Action Target", options=options, format_func=lambda x: labels.get(x, x))
    snooze_hours = st.selectbox("Snooze Duration (hours)", options=[1, 4, 8, 24, 72], index=3)
    c1, c2, c3 = st.columns(3)

    ack_ids = set(st.session_state.get("anomaly_ack_ids", []))
    snooze_map = dict(st.session_state.get("anomaly_snooze_until", {}))
    now = pd.Timestamp.utcnow().tz_localize(None)

    with c1:
        if st.button("Acknowledge", use_container_width=True):
            ack_ids.add(selected)
            snooze_map.pop(selected, None)
            _increment_usage_counter("alerts_acknowledged")
    with c2:
        if st.button("Snooze", use_container_width=True):
            ack_ids.discard(selected)
            snooze_map[selected] = (now + pd.Timedelta(hours=int(snooze_hours))).isoformat()
    with c3:
        if st.button("Clear Status", use_container_width=True):
            ack_ids.discard(selected)
            snooze_map.pop(selected, None)

    st.session_state["anomaly_ack_ids"] = sorted(ack_ids)
    st.session_state["anomaly_snooze_until"] = snooze_map


def _show_anomaly_summary(data: dict[str, pd.DataFrame]) -> None:
    anomaly = _normalize_alert_state(_prepare_anomaly(data["anomaly"]))
    if anomaly.empty:
        st.info("No anomaly report found yet.")
        return
    actionable = anomaly[anomaly["severity"].isin(["warn", "error"])].copy() if "severity" in anomaly.columns else anomaly
    actionable = actionable[actionable["_alert_state"] == "active"].copy()
    if actionable.empty:
        st.success("No active anomaly alerts.")
        return

    latest_date = actionable["_date_sort"].max() if "_date_sort" in actionable.columns else pd.NaT
    latest_text = latest_date.strftime("%Y-%m-%d") if pd.notna(latest_date) else "n/a"
    warn_count = int((actionable["severity"] == "warn").sum()) if "severity" in actionable.columns else 0
    error_count = int((actionable["severity"] == "error").sum()) if "severity" in actionable.columns else 0

    st.subheader("Latest Anomaly Alerts")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Open Alerts", len(actionable))
    a2.metric("Warnings", warn_count)
    a3.metric("Errors", error_count)
    a4.metric("Last Alert Date", latest_text)
    view_cols = [c for c in ["date", "channel", "check", "metric", "value", "threshold", "severity", "detail"] if c in actionable.columns]
    display = actionable.sort_values("_date_sort", ascending=False, na_position="last")[view_cols].copy()
    if "severity" in display.columns:
        display["severity"] = display["severity"].map(_severity_badge)
    st.dataframe(
        display.head(8),
        use_container_width=True,
    )


def _build_actionable_insights(data: dict[str, pd.DataFrame]) -> list[str]:
    insights: list[str] = []
    cac = data.get("cac", pd.DataFrame()).copy()
    profitability = data.get("profitability", pd.DataFrame()).copy()
    retention = data.get("retention", pd.DataFrame()).copy()
    anomaly = data.get("anomaly", pd.DataFrame()).copy()

    if not cac.empty and {"channel", "cac"}.issubset(cac.columns):
        cac_valid = cac[pd.to_numeric(cac["cac"], errors="coerce").notna()].copy()
        if not cac_valid.empty:
            cac_valid["cac"] = pd.to_numeric(cac_valid["cac"], errors="coerce")
            worst = cac_valid.sort_values("cac", ascending=False).iloc[0]
            best_non_zero = cac_valid[cac_valid["cac"] > 0].sort_values("cac", ascending=True)
            if not best_non_zero.empty:
                best = best_non_zero.iloc[0]
                insights.append(
                    f"Lowest paid CAC is `{best['channel']}` at {best['cac']:.2f}; highest is `{worst['channel']}` at {worst['cac']:.2f}."
                )

    if not profitability.empty and {"channel", "ltv_cac_ratio"}.issubset(profitability.columns):
        p = profitability.copy()
        p["ltv_cac_ratio"] = pd.to_numeric(p["ltv_cac_ratio"], errors="coerce")
        p = p[p["ltv_cac_ratio"].notna()]
        if not p.empty:
            top = p.sort_values("ltv_cac_ratio", ascending=False).iloc[0]
            low = p.sort_values("ltv_cac_ratio", ascending=True).iloc[0]
            insights.append(
                f"Best efficiency channel is `{top['channel']}` (LTV:CAC {top['ltv_cac_ratio']:.2f}); weakest is `{low['channel']}` ({low['ltv_cac_ratio']:.2f})."
            )

    if not retention.empty and {"month_index", "retention_rate"}.issubset(retention.columns):
        r1 = retention[retention["month_index"] == 1].copy()
        if not r1.empty:
            m1 = pd.to_numeric(r1["retention_rate"], errors="coerce").dropna()
            if not m1.empty:
                insights.append(f"Median month-1 retention is {m1.median() * 100:.1f}%.")

    if not anomaly.empty and "severity" in anomaly.columns:
        sev = anomaly["severity"].astype(str).str.lower().str.strip()
        warn_count = int((sev == "warn").sum())
        error_count = int((sev == "error").sum())
        if warn_count or error_count:
            insights.append(f"Monitoring currently shows {warn_count} warnings and {error_count} errors needing review.")

    if not insights:
        insights.append("Run pipeline with complete real data to generate actionable insights.")
    return insights


def show_actionable_insights(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Actionable Insights")
    for item in _build_actionable_insights(data):
        st.markdown(f"- {item}")


def show_budget_planner(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Budget Planner (Scenario)")
    cac = data["cac"].copy()
    profitability = data["profitability"].copy()
    if cac.empty or profitability.empty:
        st.info("Need `cac_by_channel` and `channel_profitability` outputs before running budget planning.")
        return

    cac["cac"] = pd.to_numeric(cac["cac"], errors="coerce")
    cac["total_cost"] = pd.to_numeric(cac.get("total_cost"), errors="coerce")
    base = cac.merge(
        profitability[["channel", "avg_predicted_ltv"]],
        on="channel",
        how="left",
    )
    base = base[(base["cac"].notna()) & (base["cac"] > 0)].copy()
    if base.empty:
        st.warning("No channels with positive CAC are available for projection.")
        return

    default_budget = float(base["total_cost"].fillna(0).sum())
    if default_budget <= 0:
        default_budget = 10000.0
    total_budget = st.number_input("Planned Total Budget", min_value=0.0, value=round(default_budget, 2), step=100.0)

    st.markdown("#### Channel weight multipliers")
    weights: dict[str, float] = {}
    cols = st.columns(min(3, max(1, len(base))))
    for idx, row in enumerate(base.itertuples(index=False)):
        with cols[idx % len(cols)]:
            weights[row.channel] = st.number_input(
                f"{row.channel} weight",
                min_value=0.0,
                value=1.0,
                step=0.1,
                key=f"planner_weight_{row.channel}",
            )

    planner = base.copy()
    planner["weight"] = planner["channel"].map(weights).fillna(1.0)
    weight_sum = float(planner["weight"].sum())
    if weight_sum <= 0:
        st.warning("All channel weights are zero. Increase at least one weight.")
        return

    planner["budget_share"] = planner["weight"] / weight_sum
    planner["proposed_spend"] = planner["budget_share"] * total_budget
    planner["projected_new_customers"] = planner["proposed_spend"] / planner["cac"]
    planner["avg_predicted_ltv"] = pd.to_numeric(planner["avg_predicted_ltv"], errors="coerce").fillna(0.0)
    planner["projected_value"] = planner["projected_new_customers"] * planner["avg_predicted_ltv"]
    planner["projected_roi"] = np.where(planner["proposed_spend"] > 0, planner["projected_value"] / planner["proposed_spend"], 0.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Projected New Customers", f"{planner['projected_new_customers'].sum():,.0f}")
    c2.metric("Projected Value", f"{planner['projected_value'].sum():,.0f}")
    c3.metric("Projected Value/Spend", f"{(planner['projected_value'].sum() / total_budget) if total_budget > 0 else 0:.2f}")

    fig_spend = px.bar(planner.sort_values("proposed_spend", ascending=False), x="channel", y="proposed_spend", title="Proposed Spend by Channel")
    st.plotly_chart(fig_spend, use_container_width=True)
    fig_customers = px.bar(
        planner.sort_values("projected_new_customers", ascending=False),
        x="channel",
        y="projected_new_customers",
        title="Projected New Customers by Channel",
    )
    st.plotly_chart(fig_customers, use_container_width=True)

    view_cols = [
        "channel",
        "cac",
        "avg_predicted_ltv",
        "budget_share",
        "proposed_spend",
        "projected_new_customers",
        "projected_value",
        "projected_roi",
    ]
    st.dataframe(planner[view_cols], use_container_width=True)

def show_overview(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Executive Overview")
    overview = data["overview"]
    if overview.empty:
        st.warning("No processed outputs found. Run pipeline first.")
        return

    metrics = {row["metric"]: row["value"] for _, row in overview.iterrows()}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net Revenue", f"{metrics.get('total_net_revenue', 0):,.0f}")
    c2.metric("Contribution Margin", f"{metrics.get('total_contribution_margin', 0):,.0f}")
    c3.metric("Avg CAC", f"{metrics.get('avg_cac', 0):,.2f}")
    c4.metric("Avg LTV:CAC", f"{metrics.get('avg_ltv_cac_ratio', 0):,.2f}")

    cac = data["cac"]
    if not cac.empty:
        fig = px.bar(cac, x="channel", y="cac", title="CAC by Channel")
        st.plotly_chart(fig, use_container_width=True)
    _show_anomaly_summary(data)
    show_actionable_insights(data)


def show_channel_performance(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Channel Performance")
    p = data["profitability"]
    if p.empty:
        st.info("No channel profitability output yet.")
        return

    fig = px.scatter(
        p,
        x="cac",
        y="avg_predicted_ltv",
        size="customers",
        color="channel",
        hover_data=["ltv_cac_ratio", "payback_months_est"],
        title="Channel LTV vs CAC",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(p, use_container_width=True)


def show_retention_ltv(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Cohort Retention & LTV")
    retention = data["retention"]
    ltv = data["ltv"]

    if not retention.empty:
        retention["cohort_month"] = pd.to_datetime(retention["cohort_month"])
        fig = px.line(
            retention,
            x="month_index",
            y="retention_rate",
            color=retention["cohort_month"].dt.strftime("%Y-%m"),
            title="Monthly Retention Curves by Cohort",
        )
        st.plotly_chart(fig, use_container_width=True)

    if not ltv.empty:
        fig2 = px.histogram(
            ltv,
            x="predicted_ltv",
            nbins=20,
            title="Predicted LTV Distribution",
        )
        st.plotly_chart(fig2, use_container_width=True)


def show_customer_profitability(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Customer Profitability")
    ltv = data["ltv"]
    if ltv.empty:
        st.info("No customer LTV output yet.")
        return

    fig = px.scatter(
        ltv,
        x="order_count",
        y="realized_ltv",
        color="prediction_method",
        title="Realized LTV vs Order Count",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        ltv.sort_values("realized_ltv", ascending=False).head(50),
        use_container_width=True,
    )


def show_data_quality(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Data Quality & Freshness")
    quality = data["quality"]
    if quality.empty:
        st.info("No quality report found.")
        return
    st.dataframe(quality, use_container_width=True)


def show_billing_and_plan(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("Billing & Plan")
    plan = _current_plan()
    usage = _get_usage_counters()
    export_limit = int(plan.limits.get("monthly_report_exports", 0))
    exports_used = int(usage.get("report_exports", 0))
    exports_left = max(export_limit - exports_used, 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Plan", plan.display_name)
    c2.metric("Monthly Price", "Custom" if plan.monthly_price_usd == 0 else f"${plan.monthly_price_usd}")
    c3.metric("Report Exports Left", f"{exports_left}/{export_limit}")

    limits_df = pd.DataFrame(
        {
            "limit": list(plan.limits.keys()),
            "value": list(plan.limits.values()),
        }
    )
    st.markdown("#### Plan Limits")
    st.dataframe(limits_df, use_container_width=True, hide_index=True)

    st.markdown("#### Usage This Session")
    usage_df = pd.DataFrame(
        {
            "metric": list(usage.keys()),
            "value": list(usage.values()),
        }
    )
    st.dataframe(usage_df, use_container_width=True, hide_index=True)

    if APP_STRIPE_PORTAL_URL:
        st.markdown(f"[Open Billing Portal]({APP_STRIPE_PORTAL_URL})")
    if APP_STRIPE_CHECKOUT_URL:
        st.markdown(f"[Upgrade Plan]({APP_STRIPE_CHECKOUT_URL})")
    if APP_CONTACT_SALES_URL:
        st.markdown(f"[Talk to Sales]({APP_CONTACT_SALES_URL})")


def show_scheduled_reports(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Scheduled Reports")
    if not _has_entitlement("scheduled_reports"):
        _show_upgrade_cta(
            feature="scheduled_reports",
            reason="Scheduled reports are not available on your current plan.",
        )
        return

    plan = _current_plan()
    usage = _get_usage_counters()
    export_limit = int(plan.limits.get("monthly_report_exports", 0))
    exports_used = int(usage.get("report_exports", 0))
    exports_left = max(export_limit - exports_used, 0)

    st.caption("Set up recurring delivery of KPI snapshots for founders, finance, and growth teams.")
    r1, r2, r3 = st.columns(3)
    r1.metric("Exports Used", exports_used)
    r2.metric("Monthly Export Limit", export_limit)
    r3.metric("Exports Left", exports_left)

    destination = st.selectbox("Destination", options=["email", "slack_webhook", "csv_download"])
    frequency = st.selectbox("Frequency", options=["daily", "weekly", "monthly"], index=1)
    report_name = st.text_input("Report Name", value="Weekly Growth KPI Pack")
    recipients = st.text_input("Recipients / Channel", value="growth@company.com")

    if destination == "slack_webhook" and not _has_entitlement("slack_webhooks"):
        _show_upgrade_cta(
            feature="slack_webhooks",
            reason="Slack webhook destinations are available on Pro and above.",
        )
        return

    if st.button("Create Schedule", use_container_width=True):
        _increment_usage_counter("scheduled_reports_created")
        st.success(
            f"Scheduled `{report_name}` ({frequency}) to `{recipients}` via `{destination}`. "
            "Delivery workers can be wired in next."
        )

    if exports_left <= 0:
        _show_upgrade_cta(
            feature="scheduled_reports",
            reason="You have reached your monthly export limit.",
        )
        return

    overview = data.get("overview", pd.DataFrame())
    if overview.empty:
        st.info("Run the pipeline first to export a report snapshot.")
        return

    report_csv = overview.to_csv(index=False).encode("utf-8")
    if st.download_button(
        "Download KPI Snapshot (CSV)",
        data=report_csv,
        file_name="kpi_snapshot.csv",
        mime="text/csv",
        use_container_width=True,
    ):
        _increment_usage_counter("report_exports")


def _render_alert_destination_manager() -> None:
    st.markdown("### Alert Destinations")
    if not _has_entitlement("email_alerts") and not _has_entitlement("webhook_alerts"):
        _show_upgrade_cta(
            feature="email_alerts",
            reason="Destination alerting is not available on your current plan.",
        )
        return

    plan = _current_plan()
    destinations = _get_alert_destinations()
    max_destinations = int(plan.limits.get("alert_destinations", 0))
    st.caption(f"Configured destinations: {len(destinations)}/{max_destinations}")

    if destinations:
        destination_df = pd.DataFrame(destinations).copy()
        if "target" in destination_df.columns:
            destination_df["target"] = destination_df.apply(
                lambda row: mask_destination_target(
                    str(row.get("type", "")),
                    str(row.get("target", "")),
                ),
                axis=1,
            )
        st.dataframe(destination_df, use_container_width=True, hide_index=True)

    options = []
    if _has_entitlement("email_alerts"):
        options.append("email")
    if _has_entitlement("webhook_alerts") or _has_entitlement("slack_webhooks"):
        options.append("webhook")
    destination_type = st.selectbox("Destination Type", options=options, key="dest_type")
    destination_label = st.text_input("Destination Label", value="", key="dest_label")
    destination_target = st.text_input(
        "Target (email address or webhook URL)",
        value="",
        key="dest_target",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Add Destination", use_container_width=True):
            if len(destinations) >= max_destinations:
                _show_upgrade_cta(
                    feature="email_alerts",
                    reason=f"You reached destination limit ({max_destinations}) for this plan.",
                )
            elif not destination_target.strip():
                st.error("Target is required.")
            elif destination_type == "webhook":
                is_allowed, validation_message = validate_webhook_target_url(
                    target=destination_target,
                    allowed_hosts=APP_WEBHOOK_ALLOWED_HOSTS,
                    enforce_https=APP_ENFORCE_HTTPS_WEBHOOKS,
                )
                if not is_allowed:
                    st.error(validation_message)
                else:
                    _add_alert_destination(destination_type, destination_target, destination_label)
                    st.success("Destination added.")
            else:
                _add_alert_destination(destination_type, destination_target, destination_label)
                st.success("Destination added.")
    with c2:
        if st.button("Send Test Alert", use_container_width=True):
            ok_count, fail_count, messages = _dispatch_sample_alert_to_destinations()
            if ok_count + fail_count == 0:
                st.info("No destinations configured.")
            else:
                _increment_usage_counter("alert_dispatches")
                st.success(f"Test dispatch complete: {ok_count} succeeded, {fail_count} failed.")
                if messages:
                    st.code("\n".join(messages))

    if destinations:
        remove_index = st.selectbox(
            "Remove destination",
            options=list(range(len(destinations))),
            format_func=lambda idx: f"{destinations[idx].get('label', 'destination')} ({destinations[idx].get('type', '')})",
            key="dest_remove_index",
        )
        if st.button("Remove Selected Destination", use_container_width=True):
            _remove_alert_destination(int(remove_index))
            st.success("Destination removed.")


def show_connectors_and_sync(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("Connectors & Sync")
    if not _has_entitlement("connector_health"):
        _show_upgrade_cta(
            feature="connector_health",
            reason="Connector health monitoring is not available on your current plan.",
        )
        return

    health = _build_connector_health_table()
    if health.empty:
        st.info("No connector health data available yet.")
    else:
        fresh_count = int((health["freshness"] == "fresh").sum()) if "freshness" in health.columns else 0
        available_count = int(health["available"].sum()) if "available" in health.columns else 0
        h1, h2, h3 = st.columns(3)
        h1.metric("Connectors Available", available_count)
        h2.metric("Fresh Connectors", fresh_count)
        h3.metric("Total Connectors", len(health))
        st.dataframe(health, use_container_width=True, hide_index=True)

    st.markdown("### Sync Jobs")
    if not _has_entitlement("connector_sync"):
        _show_upgrade_cta(
            feature="connector_sync",
            reason="Scheduled sync jobs are available on Growth and above.",
        )
        return

    _upsert_default_sync_job()
    jobs = _get_sync_jobs()
    jobs_df = pd.DataFrame(jobs)
    st.dataframe(jobs_df, use_container_width=True, hide_index=True)
    sync_frequency = st.selectbox(
        "Sync Frequency",
        options=["hourly", "daily", "weekly"],
        index=1 if APP_SYNC_DEFAULT_FREQUENCY not in {"hourly", "weekly"} else (0 if APP_SYNC_DEFAULT_FREQUENCY == "hourly" else 2),
        key="sync_frequency",
    )
    sync_hour = st.number_input("Sync Hour (UTC)", min_value=0, max_value=23, value=max(min(APP_SYNC_DEFAULT_HOUR_UTC, 23), 0), step=1)
    sync_status = st.selectbox("Sync Status", options=["enabled", "paused"], index=0)
    if st.button("Save Sync Job", use_container_width=True):
        st.session_state[SYNC_JOBS_STATE_KEY] = [
            {
                "name": "Primary D2C Sync",
                "frequency": str(sync_frequency),
                "hour_utc": str(int(sync_hour)),
                "status": str(sync_status),
            }
        ]
        _append_audit_event(
            action="save_sync_job",
            outcome="success",
            detail=f"frequency={sync_frequency}, hour_utc={int(sync_hour)}, status={sync_status}",
            category="pipeline",
        )
        st.success("Sync job saved.")
    if st.button("Run Sync Now", use_container_width=True):
        with st.spinner("Running connector sync..."):
            ok, message = _run_pipeline_now("warn")
        if ok:
            _append_audit_event(
                action="run_sync_now",
                outcome="success",
                detail="manual connector sync completed",
                category="pipeline",
            )
            st.success(message)
        else:
            _append_audit_event(
                action="run_sync_now",
                outcome="failed",
                detail=message,
                category="pipeline",
            )
            st.error(message)


def show_what_changed(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("What Changed")
    if not _has_entitlement("what_changed_diagnostics"):
        _show_upgrade_cta(
            feature="what_changed_diagnostics",
            reason="What-changed diagnostics are available on Growth and above.",
        )
        return

    previous_overview = _load_previous_output("kpi_overview")
    previous_cac = _load_previous_output("cac_by_channel")
    previous_profitability = _load_previous_output("channel_profitability")
    if previous_overview.empty and previous_cac.empty and previous_profitability.empty:
        st.info("No previous snapshot found yet. Run pipeline at least twice to activate diagnostics.")
        return

    overview_deltas = build_overview_deltas(data.get("overview", pd.DataFrame()), previous_overview)
    cac_deltas = build_channel_metric_deltas(data.get("cac", pd.DataFrame()), previous_cac, metric_col="cac")
    ratio_deltas = build_channel_metric_deltas(
        data.get("profitability", pd.DataFrame()),
        previous_profitability,
        metric_col="ltv_cac_ratio",
    )

    if not overview_deltas.empty:
        top_abs = overview_deltas.reindex(overview_deltas["delta"].abs().sort_values(ascending=False).index).head(1)
        if not top_abs.empty:
            row = top_abs.iloc[0]
            st.success(
                f"Largest movement: `{row['metric']}` changed by {row['delta']:.2f} "
                f"({row['delta_pct']:.1f}% vs previous snapshot)."
            )
        st.markdown("### KPI Delta vs Previous Snapshot")
        st.dataframe(overview_deltas, use_container_width=True, hide_index=True)

    if not cac_deltas.empty:
        st.markdown("### CAC Delta by Channel")
        st.dataframe(cac_deltas, use_container_width=True, hide_index=True)

    if not ratio_deltas.empty:
        st.markdown("### LTV:CAC Ratio Delta by Channel")
        st.dataframe(ratio_deltas, use_container_width=True, hide_index=True)


def show_attribution_deep_dive(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("Attribution Deep Dive")
    if not _has_entitlement("attribution_depth"):
        _show_upgrade_cta(
            feature="attribution_depth",
            reason="Attribution deep-dive diagnostics are available on Pro and above.",
        )
        return

    frames = _safe_load_raw_frames()
    if frames is None:
        st.info("Could not load raw contract files for attribution deep dive.")
        return

    orders_with_margin = prep_orders_with_margin(frames["orders"], frames["refunds"])
    attributions = attribute_customers_last_non_direct(frames["customers"], orders_with_margin, frames["sessions"])
    if attributions.empty:
        st.info("No attribution data available yet.")
        return

    channel_dist = (
        attributions.groupby("attributed_channel", as_index=False)["customer_id"]
        .nunique()
        .rename(columns={"attributed_channel": "channel", "customer_id": "first_order_customers"})
        .sort_values("first_order_customers", ascending=False)
        .reset_index(drop=True)
    )
    total_customers = max(int(channel_dist["first_order_customers"].sum()), 1)
    channel_dist["share_pct"] = (channel_dist["first_order_customers"] / total_customers) * 100.0
    c1, c2 = st.columns(2)
    c1.metric("Attributed Customers", f"{total_customers:,}")
    c2.metric("Top Channel Share", f"{channel_dist.iloc[0]['share_pct']:.1f}%")
    st.dataframe(channel_dist, use_container_width=True, hide_index=True)
    fig_dist = px.bar(channel_dist, x="channel", y="first_order_customers", title="First-Order Attribution by Channel")
    st.plotly_chart(fig_dist, use_container_width=True)

    sessions = frames["sessions"].copy()
    sessions["session_ts"] = pd.to_datetime(sessions["session_ts"], errors="coerce")
    first_orders = attributions[["customer_id", "first_order_ts", "attributed_channel"]].copy()
    first_orders["first_order_ts"] = pd.to_datetime(first_orders["first_order_ts"], errors="coerce")
    eligible = sessions.merge(first_orders[["customer_id", "first_order_ts"]], on="customer_id", how="inner")
    eligible = eligible[eligible["session_ts"] <= eligible["first_order_ts"]].copy()
    if not eligible.empty:
        path_stats = (
            eligible.groupby("customer_id", as_index=False)
            .agg(
                total_touches=("session_id", "nunique"),
                unique_channels=("channel", "nunique"),
                non_direct_touches=("is_direct", lambda s: int((~s.astype(bool)).sum())),
            )
            .sort_values("total_touches", ascending=False)
        )
        p1, p2, p3 = st.columns(3)
        p1.metric("Median Touches", f"{path_stats['total_touches'].median():.1f}")
        p2.metric("Median Unique Channels", f"{path_stats['unique_channels'].median():.1f}")
        p3.metric("Multi-touch Customers", f"{int((path_stats['total_touches'] > 1).sum()):,}")
        touch_bins = (
            path_stats.groupby("total_touches", as_index=False)["customer_id"]
            .nunique()
            .rename(columns={"customer_id": "customers"})
            .sort_values("total_touches")
        )
        fig_touches = px.bar(touch_bins, x="total_touches", y="customers", title="Touch Depth Distribution")
        st.plotly_chart(fig_touches, use_container_width=True)

        first_touch = (
            eligible.sort_values(["customer_id", "session_ts"])
            .groupby("customer_id", as_index=False)
            .first()[["customer_id", "channel"]]
            .rename(columns={"channel": "first_touch_channel"})
        )
        compare = attributions[["customer_id", "attributed_channel"]].merge(first_touch, on="customer_id", how="left")
        compare["same_channel"] = compare["attributed_channel"] == compare["first_touch_channel"]
        match_rate = float(compare["same_channel"].mean()) * 100.0 if not compare.empty else 0.0
        st.caption(f"First-touch vs last-non-direct match rate: **{match_rate:.1f}%**")
        compare_dist = (
            compare.groupby(["first_touch_channel", "attributed_channel"], as_index=False)["customer_id"]
            .nunique()
            .rename(columns={"customer_id": "customers"})
        )
        if not compare_dist.empty:
            fig_compare = px.density_heatmap(
                compare_dist,
                x="first_touch_channel",
                y="attributed_channel",
                z="customers",
                color_continuous_scale="Blues",
                title="First-Touch vs Last-Non-Direct Attribution Crosswalk",
            )
            st.plotly_chart(fig_compare, use_container_width=True)


def show_scenario_optimizer(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Scenario Optimizer")
    if not _has_entitlement("scenario_optimizer"):
        _show_upgrade_cta(
            feature="scenario_optimizer",
            reason="Constrained scenario optimization is available on Pro and above.",
        )
        return

    cac = data.get("cac", pd.DataFrame()).copy()
    profitability = data.get("profitability", pd.DataFrame()).copy()
    if cac.empty or profitability.empty:
        st.info("Need `cac_by_channel` and `channel_profitability` outputs before optimization.")
        return

    default_budget = float(pd.to_numeric(cac.get("total_cost"), errors="coerce").fillna(0).sum())
    if default_budget <= 0:
        default_budget = 25000.0

    total_budget = st.number_input("Total Budget", min_value=0.0, value=round(default_budget, 2), step=100.0)
    target_max_cac = st.number_input("Target Max Blended CAC", min_value=0.0, value=80.0, step=1.0)
    reserve_pct = st.slider("Cash Reserve (%)", min_value=0, max_value=60, value=10, step=1)
    optimized, summary = optimize_budget_allocation(
        cac_df=cac,
        profitability_df=profitability,
        total_budget=float(total_budget),
        target_max_cac=float(target_max_cac),
        reserve_pct=float(reserve_pct),
    )
    if optimized.empty:
        st.warning("No eligible channels with positive CAC were found.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Usable Budget", f"{summary.usable_budget:,.0f}")
    m2.metric("Projected Customers", f"{summary.projected_customers:,.0f}")
    m3.metric("Projected Value", f"{summary.projected_value:,.0f}")
    m4.metric("Blended CAC", f"{summary.blended_cac:.2f}")
    st.caption(f"Projected Value/Spend: **{summary.blended_value_to_spend:.2f}**")
    if target_max_cac > 0 and summary.blended_cac > target_max_cac:
        st.warning("Projected blended CAC is still above target. Increase budget efficiency or relax constraints.")

    view = optimized.copy()
    view["recommended_share_pct"] = view["recommended_share"] * 100.0
    fig_spend = px.bar(view, x="channel", y="recommended_spend", title="Optimized Spend by Channel")
    st.plotly_chart(fig_spend, use_container_width=True)
    fig_value = px.bar(view, x="channel", y="projected_value", title="Projected Value by Channel")
    st.plotly_chart(fig_value, use_container_width=True)
    st.dataframe(
        view[
            [
                "channel",
                "cac",
                "avg_predicted_ltv",
                "efficiency_score",
                "recommended_share_pct",
                "recommended_spend",
                "projected_customers",
                "projected_value",
                "projected_value_to_spend",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def show_white_label_studio(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("White Label Studio")
    if not _has_entitlement("white_label_controls"):
        _show_upgrade_cta(
            feature="white_label_controls",
            reason="White-label branding controls are available on Pro / Agency and above.",
        )
        return

    current = _get_branding_config()
    brand_name = st.text_input("Brand Name", value=current.get("brand_name", ""))
    subtitle = st.text_input("Subtitle", value=current.get("subtitle", ""))
    primary_color = st.color_picker("Primary Color", value=current.get("primary_color", "#2f6df6"))
    logo_url = st.text_input("Logo URL", value=current.get("logo_url", ""))
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save Branding", use_container_width=True):
            _set_branding_config(
                {
                    "brand_name": brand_name,
                    "subtitle": subtitle,
                    "primary_color": primary_color,
                    "logo_url": logo_url,
                }
            )
            st.success("Branding settings saved for this workspace.")
    with c2:
        if st.button("Reset Branding", use_container_width=True):
            _set_branding_config(
                {
                    "brand_name": "D2C Marketing & Customer Profitability Analytics",
                    "subtitle": "CAC, LTV, retention, and profitability insights",
                    "primary_color": "#2f6df6",
                    "logo_url": "",
                }
            )
            st.success("Branding reset to defaults.")

    preview = {
        "brand_name": brand_name,
        "subtitle": subtitle,
        "primary_color": primary_color,
        "logo_url": logo_url,
    }
    st.markdown("### Export Brand Kit")
    st.download_button(
        "Download Brand Config (JSON)",
        data=json.dumps(preview, indent=2),
        file_name="brand_config.json",
        mime="application/json",
        use_container_width=True,
    )
    st.markdown("### Preview")
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
          <div style="font-size:24px;font-weight:700;color:{primary_color};">{brand_name or 'Brand Name'}</div>
          <div style="color:#6b7280;">{subtitle or 'Subtitle'}</div>
          <div style="margin-top:8px;font-size:12px;color:#9ca3af;">Preview shown using current white-label settings.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_security_center(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("Security Center")
    if not _has_entitlement("security_center"):
        _show_upgrade_cta(
            feature="security_center",
            reason="Security center controls are not available on your current plan.",
        )
        return

    controls = pd.DataFrame(
        [
            {"control": "Strict validation default", "status": "pass" if APP_VALIDATION_MODE == "strict" else "warn", "detail": f"VALIDATION_MODE={APP_VALIDATION_MODE}"},
            {"control": "Proxy spend blocked", "status": "pass" if not APP_ALLOW_PROXY_SPEND else "warn", "detail": f"APP_ALLOW_PROXY_SPEND={int(APP_ALLOW_PROXY_SPEND)}"},
            {"control": "HTTPS webhook enforcement", "status": "pass" if APP_ENFORCE_HTTPS_WEBHOOKS else "warn", "detail": f"APP_ENFORCE_HTTPS_WEBHOOKS={int(APP_ENFORCE_HTTPS_WEBHOOKS)}"},
            {"control": "Webhook host allowlist", "status": "pass" if bool(APP_WEBHOOK_ALLOWED_HOSTS) else "warn", "detail": "configured" if APP_WEBHOOK_ALLOWED_HOSTS else "not configured"},
            {"control": "Webhook payload signing", "status": "pass" if bool(APP_WEBHOOK_SIGNING_SECRET) else "warn", "detail": "X-D2C-Signature enabled" if APP_WEBHOOK_SIGNING_SECRET else "signing secret missing"},
            {"control": "Audit log capture", "status": "pass", "detail": f"{len(_get_audit_events())} event(s) tracked in session"},
        ]
    )
    pass_count = int((controls["status"] == "pass").sum())
    warn_count = int((controls["status"] == "warn").sum())
    s1, s2, s3 = st.columns(3)
    s1.metric("Controls Passing", pass_count)
    s2.metric("Controls Warning", warn_count)
    s3.metric("Webhook Allowlist Hosts", len(APP_WEBHOOK_ALLOWED_HOSTS))
    st.dataframe(controls, use_container_width=True, hide_index=True)

    st.markdown("### Webhook Policy")
    if APP_WEBHOOK_ALLOWED_HOSTS:
        st.caption("Allowed hosts configured via `APP_WEBHOOK_ALLOWED_HOSTS`")
        st.code(", ".join(sorted(APP_WEBHOOK_ALLOWED_HOSTS)))
    else:
        st.warning("No webhook host allowlist set. Configure `APP_WEBHOOK_ALLOWED_HOSTS` to restrict alert endpoints.")
    if APP_WEBHOOK_SIGNING_SECRET:
        st.success("Webhook payload signing is enabled via `APP_WEBHOOK_SIGNING_SECRET`.")
    else:
        st.info("Set `APP_WEBHOOK_SIGNING_SECRET` to attach HMAC signatures to webhook alerts.")

    st.markdown("### Audit Events")
    events = _get_audit_events()
    if not events:
        st.info("No audit events captured yet in this session.")
        return
    events_df = pd.DataFrame(events).sort_values("ts_utc", ascending=False).reset_index(drop=True)
    st.dataframe(events_df, use_container_width=True, hide_index=True)
    if _has_entitlement("audit_logs"):
        if st.download_button(
            "Download Audit Log (CSV)",
            data=events_df.to_csv(index=False).encode("utf-8"),
            file_name="audit_log.csv",
            mime="text/csv",
            use_container_width=True,
        ):
            _append_audit_event(
                action="export_audit_log",
                outcome="success",
                detail=f"rows={len(events_df)}",
                category="security",
            )
    else:
        _show_upgrade_cta(
            feature="audit_logs",
            reason="Audit log export is available on Pro / Agency and above.",
        )


def show_enterprise_controls(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("Enterprise Controls")
    if not _has_entitlement("enterprise_controls"):
        _show_upgrade_cta(
            feature="enterprise_controls",
            reason="Enterprise controls are available on Enterprise plan.",
        )
        return

    plan = _current_plan()
    members = _get_team_members()
    seat_limit = int(plan.limits.get("max_workspace_members", 0))
    e1, e2, e3 = st.columns(3)
    e1.metric("Seats Used", len(members))
    e2.metric("Seat Limit", seat_limit)
    e3.metric("Seats Available", max(seat_limit - len(members), 0))

    st.markdown("### Workspace Access")
    members_df = pd.DataFrame(members)
    st.dataframe(members_df, use_container_width=True, hide_index=True)
    m1, m2 = st.columns(2)
    with m1:
        member_name = st.text_input("Member Name", key="enterprise_member_name")
        member_email = st.text_input("Member Email", key="enterprise_member_email")
        member_role = st.selectbox("Role", options=["viewer", "analyst", "manager", "admin", "owner"], index=0, key="enterprise_member_role")
        if st.button("Add Team Member", use_container_width=True):
            if len(members) >= seat_limit:
                st.error(f"Seat limit reached ({seat_limit}).")
            elif "@" not in member_email.strip():
                st.error("Valid member email is required.")
            else:
                members.append(
                    {
                        "name": member_name.strip() or "Unnamed",
                        "email": member_email.strip().lower(),
                        "role": member_role,
                        "status": "active",
                        "added_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                _set_team_members(members)
                _append_audit_event(
                    action="add_team_member",
                    outcome="success",
                    detail=f"email={mask_destination_target('email', member_email)}, role={member_role}",
                    category="enterprise",
                )
                st.success("Team member added.")
    with m2:
        if members:
            remove_index = st.selectbox(
                "Remove Member",
                options=list(range(len(members))),
                format_func=lambda idx: f"{members[idx].get('email', '')} ({members[idx].get('role', '')})",
                key="enterprise_remove_member_idx",
            )
            if st.button("Remove Team Member", use_container_width=True):
                removed = members.pop(int(remove_index))
                _set_team_members(members)
                _append_audit_event(
                    action="remove_team_member",
                    outcome="success",
                    detail=f"email={mask_destination_target('email', str(removed.get('email', '')))}",
                    category="enterprise",
                )
                st.success("Team member removed.")

    st.markdown("### Identity & Network Policy")
    policy = _get_security_policy()
    sso_domain = st.text_input("SSO Domain (e.g. company.com)", value=str(policy.get("sso_domain", "")), key="enterprise_sso_domain")
    require_sso = st.toggle("Require SSO for all workspace users", value=bool(policy.get("require_sso", False)), key="enterprise_require_sso")
    ip_allowlist_text = st.text_area(
        "IP Allowlist (one CIDR/range per line)",
        value="\n".join(str(v) for v in policy.get("ip_allowlist", [])),
        key="enterprise_ip_allowlist",
        height=120,
    )
    if st.button("Save Enterprise Policy", use_container_width=True):
        parsed_ip_allowlist = [line.strip() for line in ip_allowlist_text.splitlines() if line.strip()]
        _set_security_policy(
            {
                "sso_domain": sso_domain,
                "require_sso": require_sso,
                "ip_allowlist": parsed_ip_allowlist,
            }
        )
        _append_audit_event(
            action="save_enterprise_policy",
            outcome="success",
            detail=f"sso_domain={sso_domain.strip().lower()}, require_sso={int(require_sso)}, ip_ranges={len(parsed_ip_allowlist)}",
            category="enterprise",
        )
        st.success("Enterprise policy saved.")

    if _has_entitlement("custom_sla"):
        st.markdown("### SLA Commitments")
        sla_df = pd.DataFrame(
            [
                {"severity": "SEV-1", "response_target": "30 minutes", "resolution_target": "4 hours"},
                {"severity": "SEV-2", "response_target": "2 hours", "resolution_target": "1 business day"},
                {"severity": "SEV-3", "response_target": "1 business day", "resolution_target": "3 business days"},
            ]
        )
        st.dataframe(sla_df, use_container_width=True, hide_index=True)


def show_partner_hub(data: dict[str, pd.DataFrame] | None = None) -> None:
    st.subheader("Partner Hub")
    if not _has_entitlement("partner_hub"):
        _show_upgrade_cta(
            feature="partner_hub",
            reason="Partner pipeline and co-sell workflows are available on Pro / Agency and above.",
        )
        return

    opportunities = _get_partner_pipeline()
    opportunity_limit = int(_current_plan().limits.get("partner_pipeline_opportunities", 0))
    opportunities_df = pd.DataFrame(opportunities) if opportunities else pd.DataFrame()
    total_pipeline_arr = float(pd.to_numeric(opportunities_df.get("estimated_arr_usd"), errors="coerce").fillna(0).sum()) if not opportunities_df.empty else 0.0
    won_count = int((opportunities_df.get("stage", pd.Series(dtype=str)).astype(str).str.lower() == "won").sum()) if not opportunities_df.empty else 0
    p1, p2, p3 = st.columns(3)
    p1.metric("Opportunities", len(opportunities))
    p2.metric("Estimated Pipeline ARR", f"{total_pipeline_arr:,.0f}")
    p3.metric("Won Deals", won_count)
    st.caption(f"Usage: {len(opportunities)}/{opportunity_limit} partner opportunities")
    if APP_PARTNER_REFERRAL_URL:
        st.markdown(f"[Partner Referral Link]({APP_PARTNER_REFERRAL_URL})")

    if not opportunities_df.empty:
        st.dataframe(opportunities_df, use_container_width=True, hide_index=True)
    else:
        st.info("No partner opportunities logged yet.")

    st.markdown("### Register Partner Opportunity")
    company = st.text_input("Company", key="partner_company")
    partner_type = st.selectbox("Partner Type", options=["agency", "system_integrator", "technology_partner", "affiliate"], key="partner_type")
    stage = st.selectbox("Stage", options=["qualified", "proposal", "pilot", "won", "lost"], key="partner_stage")
    estimated_arr_usd = st.number_input("Estimated ARR (USD)", min_value=0.0, value=12000.0, step=1000.0, key="partner_est_arr")
    owner = st.text_input("Opportunity Owner", value="BD Team", key="partner_owner")
    if st.button("Add Opportunity", use_container_width=True):
        if len(opportunities) >= opportunity_limit:
            _show_upgrade_cta(
                feature="partner_hub",
                reason=f"Opportunity limit reached ({opportunity_limit}) for this plan.",
            )
        elif not company.strip():
            st.error("Company name is required.")
        else:
            opportunities.append(
                {
                    "company": company.strip(),
                    "partner_type": partner_type,
                    "stage": stage,
                    "estimated_arr_usd": float(estimated_arr_usd),
                    "owner": owner.strip() or "BD Team",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _set_partner_pipeline(opportunities)
            _append_audit_event(
                action="add_partner_opportunity",
                outcome="success",
                detail=f"company={company.strip()}, stage={stage}, est_arr={float(estimated_arr_usd):.0f}",
                category="partner",
            )
            st.success("Partner opportunity added.")

    if opportunities:
        st.markdown("### Update Opportunity Stage")
        selected_idx = st.selectbox(
            "Opportunity",
            options=list(range(len(opportunities))),
            format_func=lambda idx: f"{opportunities[idx].get('company', '')} ({opportunities[idx].get('stage', '')})",
            key="partner_update_idx",
        )
        new_stage = st.selectbox("New Stage", options=["qualified", "proposal", "pilot", "won", "lost"], key="partner_update_stage")
        if st.button("Update Stage", use_container_width=True):
            opportunities[int(selected_idx)]["stage"] = new_stage
            _set_partner_pipeline(opportunities)
            _append_audit_event(
                action="update_partner_stage",
                outcome="success",
                detail=f"company={opportunities[int(selected_idx)].get('company', '')}, stage={new_stage}",
                category="partner",
            )
            st.success("Opportunity stage updated.")

    st.markdown("### Co-Sell Template Export")
    cosell_template = pd.DataFrame(
        [
            {"section": "brand_positioning", "value": "Profitability analytics with upload-first strict data controls"},
            {"section": "target_profile", "value": "D2C brands spending across 3+ paid channels"},
            {"section": "pilot_offer", "value": "14-day activation sprint + KPI baseline and optimization roadmap"},
        ]
    )
    st.download_button(
        "Download Co-Sell Template (CSV)",
        data=cosell_template.to_csv(index=False).encode("utf-8"),
        file_name="partner_cosell_template.csv",
        mime="text/csv",
        use_container_width=True,
    )


def show_anomaly_alerts(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Anomaly Alerts")
    _render_alert_destination_manager()
    anomaly = _normalize_alert_state(_prepare_anomaly(data["anomaly"]))
    if anomaly.empty:
        st.info("No anomaly report found.")
        return
    show_non_active = st.checkbox("Show acknowledged/snoozed alerts", value=False)

    severity_options = sorted(anomaly["severity"].dropna().unique().tolist()) if "severity" in anomaly.columns else []
    default_severity = [s for s in ["error", "warn", "info"] if s in severity_options] or severity_options
    selected = st.multiselect("Severity", severity_options, default=default_severity) if severity_options else []
    filtered = anomaly[anomaly["severity"].isin(selected)] if selected else anomaly
    if not show_non_active and "_alert_state" in filtered.columns:
        filtered = filtered[filtered["_alert_state"] == "active"]

    query = st.text_input("Search", value="", placeholder="check/channel/metric/detail")
    if query:
        q = query.lower().strip()
        search_cols = [c for c in ["check", "channel", "metric", "detail"] if c in filtered.columns]
        if search_cols:
            mask = pd.Series(False, index=filtered.index)
            for c in search_cols:
                mask = mask | filtered[c].astype(str).str.lower().str.contains(q, na=False)
            filtered = filtered[mask]
    if _has_entitlement("alert_actions"):
        _apply_alert_action(filtered)
    else:
        _show_upgrade_cta(
            feature="alert_actions",
            reason="Alert acknowledge/snooze workflows are available on Growth and above.",
        )

    filtered = filtered.sort_values("_date_sort", ascending=False, na_position="last")
    limit = st.slider("Rows", min_value=10, max_value=500, value=100, step=10)
    view_cols = [c for c in ["date", "channel", "check", "metric", "value", "threshold", "severity", "_alert_state", "detail"] if c in filtered.columns]
    display = filtered[view_cols].copy()
    if "severity" in display.columns:
        display["severity"] = display["severity"].map(_severity_badge)
    display = display.rename(columns={"_alert_state": "status"})
    st.dataframe(display.head(limit), use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="D2C Profitability Analytics", layout="wide")
    _apply_branding_styles()
    _render_brand_header()
    _render_workspace_and_plan_sidebar()
    show_advanced_pages = st.sidebar.toggle(
        "Show advanced pages",
        value=False,
        help="Enable diagnostics, security, enterprise, partner, and advanced analytics pages.",
    )
    page_options = _available_pages_for_current_plan(show_advanced_pages)
    page = st.sidebar.radio("Page", page_options)
    _render_no_code_sidebar_controls()

    if page == "No-Code Upload Center":
        show_data_upload_center()
        return

    can_access, access_message = _can_access_analytics_pages()
    if not can_access:
        st.warning(access_message)
        st.info("Go to 'No-Code Upload Center' and upload CSV files (or a ZIP bundle), then run the pipeline.")
        return
    if access_message:
        st.caption(access_message)

    with st.spinner("Checking analytics data readiness..."):
        ready, message = _ensure_processed_outputs()
    if not ready:
        st.warning(message)
        st.info("Use 'No-Code Upload Center' page to upload real data and run pipeline.")
        return

    data = load_outputs()
    required_feature = PAGE_FEATURE_REQUIREMENTS.get(page)
    if required_feature and not _has_entitlement(required_feature):
        _show_upgrade_cta(
            feature=required_feature,
            reason=f"`{page}` is not available on your current plan.",
        )
        return

    page_renderer = {
        "Executive Overview": show_overview,
        "Channel Performance": show_channel_performance,
        "Connectors & Sync": show_connectors_and_sync,
        "What Changed": show_what_changed,
        "Security Center": show_security_center,
        "Enterprise Controls": show_enterprise_controls,
        "Partner Hub": show_partner_hub,
        "Attribution Deep Dive": show_attribution_deep_dive,
        "Scenario Optimizer": show_scenario_optimizer,
        "White Label Studio": show_white_label_studio,
        "Cohort Retention & LTV": show_retention_ltv,
        "Customer Profitability": show_customer_profitability,
        "Data Quality": show_data_quality,
        "Anomaly Alerts": show_anomaly_alerts,
        "Budget Planner": show_budget_planner,
        "Billing & Plan": show_billing_and_plan,
        "Scheduled Reports": show_scheduled_reports,
    }.get(page)
    if page_renderer is None:
        st.warning("Unknown page selected.")
        return
    page_renderer(data)


if __name__ == "__main__":
    main()
