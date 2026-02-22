from __future__ import annotations
import os
import sys
from pathlib import Path
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
from python.analysis.pipeline import run_pipeline

load_dotenv()


RAW_DIR = Path(os.getenv("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DATA_DIR", PROJECT_ROOT / "data" / "processed"))
APP_DATA_SOURCE = os.getenv("DATA_SOURCE", "csv").strip().lower()
APP_VALIDATION_MODE = os.getenv("VALIDATION_MODE", "warn").strip().lower()
APP_AUTO_RUN_PIPELINE_ON_START = os.getenv("APP_AUTO_RUN_PIPELINE_ON_START", "1").strip().lower() in {"1", "true", "yes", "y"}

REQUIRED_OUTPUTS = [
    "kpi_overview",
    "cac_by_channel",
    "retention_monthly",
    "ltv_by_customer",
    "channel_profitability",
    "data_quality",
    "anomaly_report",
]


def _load_csv(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _missing_outputs() -> list[str]:
    return [name for name in REQUIRED_OUTPUTS if not (PROCESSED_DIR / f"{name}.csv").exists()]


def _ensure_processed_outputs() -> tuple[bool, str]:
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
        return "🔴 ERROR"
    if sev == "warn":
        return "🟠 WARN"
    if sev == "info":
        return "🔵 INFO"
    return f"⚪ {sev.upper()}"


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
    with st.spinner("Checking analytics data readiness..."):
        ready, message = _ensure_processed_outputs()
    if not ready:
        st.warning(message)

    data = load_outputs()

    page = st.sidebar.radio(
        "Page",
        [
            "Executive Overview",
            "Channel Performance",
            "Cohort Retention & LTV",
            "Customer Profitability",
            "Data Quality",
            "Anomaly Alerts",
        ],
    )

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
    else:
        show_anomaly_alerts(data)


if __name__ == "__main__":
    main()
