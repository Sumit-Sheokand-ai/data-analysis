from __future__ import annotations
import os
import sys
from pathlib import Path
from io import BytesIO
from zipfile import BadZipFile, ZipFile
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

load_dotenv()


RAW_DIR = Path(os.getenv("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DATA_DIR", PROJECT_ROOT / "data" / "processed"))
APP_DATA_SOURCE = os.getenv("DATA_SOURCE", "csv").strip().lower()
APP_VALIDATION_MODE = os.getenv("VALIDATION_MODE", "warn").strip().lower()
APP_AUTO_RUN_PIPELINE_ON_START = os.getenv("APP_AUTO_RUN_PIPELINE_ON_START", "1").strip().lower() in {"1", "true", "yes", "y"}
APP_ALLOW_PROXY_SPEND = os.getenv("APP_ALLOW_PROXY_SPEND", "0").strip().lower() in {"1", "true", "yes", "y"}
RAW_MARKETING_SPEND_PATH = RAW_DIR / "raw_marketing_spend.csv"

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
UPLOAD_SESSION_FLAG = "user_uploaded_data_this_session"


def _mark_user_uploaded_data() -> None:
    st.session_state[UPLOAD_SESSION_FLAG] = True


def _clear_user_uploaded_data_flag() -> None:
    st.session_state[UPLOAD_SESSION_FLAG] = False


def _has_user_uploaded_data() -> bool:
    return bool(st.session_state.get(UPLOAD_SESSION_FLAG, False))


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
        return False, f"Could not map uploaded spend file: {exc}"
    finally:
        temp_input.unlink(missing_ok=True)

    _clear_processed_outputs()
    _mark_user_uploaded_data()
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
    try:
        run_pipeline(
            data_source=APP_DATA_SOURCE,
            raw_data_dir=RAW_DIR,
            processed_data_dir=PROCESSED_DIR,
            validation_mode=mode,
        )
    except Exception as exc:
        return False, f"Pipeline run failed: {exc}"
    return True, f"Pipeline completed in `{mode}` mode."


def _render_no_code_sidebar_controls() -> None:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Quick Actions")
    st.sidebar.caption("Replace spend data or run pipeline instantly.")

    proxy_detected = _is_proxy_marketing_spend_present()
    if not RAW_MARKETING_SPEND_PATH.exists():
        st.sidebar.info("No marketing spend file uploaded yet.")
    elif proxy_detected:
        st.sidebar.warning("Current spend file looks proxy/dummy.")
    else:
        st.sidebar.success("Current spend file looks real/non-proxy.")

    uploaded_spend = st.sidebar.file_uploader(
        "Upload Real Ad Spend CSV",
        type=["csv"],
        key="real_ad_spend_upload",
        help="Google/Meta/Bing export with spend/clicks/impressions columns.",
    )

    if st.sidebar.button("Replace Spend Data", use_container_width=True):
        ok, message = _replace_marketing_spend_from_uploaded_csv(uploaded_spend)
        if ok:
            st.sidebar.success(message)
        else:
            st.sidebar.error(message)

    if st.sidebar.button("Remove Dummy/Proxy Spend", use_container_width=True):
        if RAW_MARKETING_SPEND_PATH.exists() and _is_proxy_marketing_spend_present():
            RAW_MARKETING_SPEND_PATH.unlink(missing_ok=True)
            _clear_processed_outputs()
            _clear_user_uploaded_data_flag()
            st.sidebar.success("Proxy/dummy spend data removed. Upload real spend CSV to continue.")
        elif RAW_MARKETING_SPEND_PATH.exists():
            st.sidebar.info("Current spend data is not flagged as proxy.")
        else:
            st.sidebar.info("No raw_marketing_spend.csv found.")

    chosen_validation = st.sidebar.selectbox("Run pipeline mode", options=["strict", "warn"], index=1)
    if st.sidebar.button("Run Pipeline Now", use_container_width=True):
        with st.spinner("Running analytics pipeline..."):
            ok, message = _run_pipeline_now(chosen_validation)
        if ok:
            st.sidebar.success(message)
        else:
            st.sidebar.error(message)


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
    m4.metric("Uploaded This Session", "Yes" if _has_user_uploaded_data() else "No")
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

def show_anomaly_alerts(data: dict[str, pd.DataFrame]) -> None:
    st.subheader("Anomaly Alerts")
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
    _apply_alert_action(filtered)

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
    st.title("D2C Marketing & Customer Profitability Analytics")
    st.caption("CAC, LTV, retention, and profitability insights")
    _render_no_code_sidebar_controls()

    page = st.sidebar.radio(
        "Page",
        [
            "No-Code Upload Center",
            "Executive Overview",
            "Channel Performance",
            "Cohort Retention & LTV",
            "Customer Profitability",
            "Data Quality",
            "Anomaly Alerts",
            "Budget Planner",
        ],
    )

    if page == "No-Code Upload Center":
        show_data_upload_center()
        return

    if not _has_user_uploaded_data():
        st.warning("This app is upload-first. Please upload your own data before opening analytics pages.")
        st.info("Go to 'No-Code Upload Center' and upload CSV files (or a ZIP bundle), then run the pipeline.")
        return

    with st.spinner("Checking analytics data readiness..."):
        ready, message = _ensure_processed_outputs()
    if not ready:
        st.warning(message)
        st.info("Use 'No-Code Upload Center' page to upload real data and run pipeline.")
        return

    data = load_outputs()

    if page == "Executive Overview":
        show_overview(data)
    elif page == "Channel Performance":
        show_channel_performance(data)
    elif page == "Cohort Retention & LTV":
        show_retention_ltv(data)
    elif page == "Customer Profitability":
        show_customer_profitability(data)
    elif page == "Data Quality":
        show_data_quality(data)
    elif page == "Budget Planner":
        show_budget_planner(data)
    else:
        show_anomaly_alerts(data)


if __name__ == "__main__":
    main()
