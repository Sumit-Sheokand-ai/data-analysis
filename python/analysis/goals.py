from __future__ import annotations

import math
import pandas as pd


def _extract_overview_metric(overview_df: pd.DataFrame, metric_name: str) -> float:
    if overview_df.empty or not {"metric", "value"}.issubset(overview_df.columns):
        return float("nan")
    series = overview_df.loc[
        overview_df["metric"].astype(str).str.strip().eq(metric_name),
        "value",
    ]
    if series.empty:
        return float("nan")
    value = pd.to_numeric(series.iloc[0], errors="coerce")
    return float(value) if pd.notna(value) else float("nan")


def _extract_month1_retention(retention_df: pd.DataFrame) -> float:
    if retention_df.empty or not {"month_index", "retention_rate"}.issubset(retention_df.columns):
        return float("nan")
    r1 = retention_df[retention_df["month_index"] == 1].copy()
    if r1.empty:
        return float("nan")
    r1["retention_rate"] = pd.to_numeric(r1["retention_rate"], errors="coerce")
    med = r1["retention_rate"].median()
    return float(med) if pd.notna(med) else float("nan")


def _extract_active_error_alerts(anomaly_df: pd.DataFrame) -> float:
    if anomaly_df.empty or "severity" not in anomaly_df.columns:
        return 0.0
    sev = anomaly_df["severity"].astype(str).str.strip().str.lower()
    return float((sev == "error").sum())


def _evaluate_status(current: float, target: float, direction: str) -> tuple[str, float]:
    if not math.isfinite(current) or not math.isfinite(target):
        return "unknown", float("nan")
    if direction == "low":
        if current <= target:
            return "on_track", current - target
        if current <= target * 1.10:
            return "at_risk", current - target
        return "off_track", current - target
    if current >= target:
        return "on_track", current - target
    if current >= target * 0.90:
        return "at_risk", current - target
    return "off_track", current - target


def build_goal_snapshot(
    overview_df: pd.DataFrame,
    retention_df: pd.DataFrame,
    anomaly_df: pd.DataFrame,
    targets: dict[str, float],
) -> pd.DataFrame:
    definitions = [
        ("avg_cac", "low"),
        ("avg_ltv_cac_ratio", "high"),
        ("month1_retention", "high"),
        ("active_error_alerts", "low"),
    ]
    current_values = {
        "avg_cac": _extract_overview_metric(overview_df, "avg_cac"),
        "avg_ltv_cac_ratio": _extract_overview_metric(overview_df, "avg_ltv_cac_ratio"),
        "month1_retention": _extract_month1_retention(retention_df),
        "active_error_alerts": _extract_active_error_alerts(anomaly_df),
    }
    rows: list[dict[str, float | str]] = []
    for metric, direction in definitions:
        current = float(current_values.get(metric, float("nan")))
        target = float(targets.get(metric, float("nan")))
        status, delta = _evaluate_status(current, target, direction)
        rows.append(
            {
                "metric": metric,
                "direction": direction,
                "current_value": current,
                "target_value": target,
                "delta_to_target": delta,
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def recommend_autopilot_actions(goal_snapshot_df: pd.DataFrame, max_items: int = 8) -> pd.DataFrame:
    if goal_snapshot_df.empty:
        return pd.DataFrame(columns=["metric", "priority", "action", "owner"])

    actions: list[dict[str, str]] = []
    for _, row in goal_snapshot_df.iterrows():
        status = str(row.get("status", "")).strip().lower()
        metric = str(row.get("metric", "")).strip()
        if status not in {"off_track", "at_risk"}:
            continue
        if metric == "avg_cac":
            action = "Pause highest-CAC clusters and reallocate budget to top-efficiency channels."
            owner = "Performance Marketing"
        elif metric == "avg_ltv_cac_ratio":
            action = "Shift spend toward channels with better LTV:CAC and tighten creative targeting."
            owner = "Growth Strategy"
        elif metric == "month1_retention":
            action = "Launch 30-day retention playbook (welcome flow, replenishment nudges, winback offers)."
            owner = "CRM Team"
        elif metric == "active_error_alerts":
            action = "Resolve active error alerts and assign owners with 24h SLA."
            owner = "Analytics Ops"
        else:
            action = "Investigate metric variance and assign remediation owner."
            owner = "Analytics Team"
        priority = "high" if status == "off_track" else "medium"
        actions.append(
            {
                "metric": metric,
                "priority": priority,
                "action": action,
                "owner": owner,
            }
        )
    if not actions:
        actions.append(
            {
                "metric": "none",
                "priority": "low",
                "action": "All tracked goals are on track. Keep monitoring current strategy.",
                "owner": "System",
            }
        )
    return pd.DataFrame(actions).head(max(max_items, 1)).reset_index(drop=True)
