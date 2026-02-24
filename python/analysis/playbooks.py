from __future__ import annotations

import numpy as np
import pandas as pd


def seed_playbooks_from_signals(
    recommendations_df: pd.DataFrame,
    anomaly_df: pd.DataFrame,
    max_items: int = 20,
) -> pd.DataFrame:
    items: list[dict[str, str | int]] = []
    remaining = max(int(max_items), 1)

    if not recommendations_df.empty:
        for _, row in recommendations_df.head(remaining).iterrows():
            priority = str(row.get("priority", "medium")).strip().lower() or "medium"
            action = str(row.get("action", "")).strip() or "Review growth recommendation"
            theme = str(row.get("theme", "growth")).strip().lower() or "growth"
            items.append(
                {
                    "title": action,
                    "source": f"copilot:{theme}",
                    "priority": priority,
                    "status": "open",
                    "owner": "Growth Team",
                    "sla_days": 7 if priority == "high" else 14,
                }
            )

    remaining = max(int(max_items) - len(items), 0)
    if remaining > 0 and not anomaly_df.empty:
        anomaly_view = anomaly_df.copy()
        if "severity" in anomaly_view.columns:
            anomaly_view["severity"] = anomaly_view["severity"].astype(str).str.strip().str.lower()
            anomaly_view = anomaly_view[anomaly_view["severity"].isin(["error", "warn"])]
        for _, row in anomaly_view.head(remaining).iterrows():
            check = str(row.get("check", "anomaly")).strip() or "anomaly"
            channel = str(row.get("channel", "all")).strip() or "all"
            severity = str(row.get("severity", "warn")).strip().lower() or "warn"
            items.append(
                {
                    "title": f"Investigate {check} impact on {channel}",
                    "source": "anomaly_monitoring",
                    "priority": "high" if severity == "error" else "medium",
                    "status": "open",
                    "owner": "Ops Team",
                    "sla_days": 3 if severity == "error" else 7,
                }
            )

    if not items:
        items.append(
            {
                "title": "Collect one more cycle of complete real data",
                "source": "system",
                "priority": "low",
                "status": "open",
                "owner": "Analytics Team",
                "sla_days": 14,
            }
        )

    out = pd.DataFrame(items).head(max_items).reset_index(drop=True)
    out.insert(0, "playbook_id", [f"PB-{idx + 1:04d}" for idx in range(len(out))])
    return out


def summarize_playbook_status(playbooks_df: pd.DataFrame) -> dict[str, int]:
    if playbooks_df.empty or "status" not in playbooks_df.columns:
        return {"open": 0, "in_progress": 0, "completed": 0, "blocked": 0}
    status_series = playbooks_df["status"].astype(str).str.strip().str.lower()
    return {
        "open": int((status_series == "open").sum()),
        "in_progress": int((status_series == "in_progress").sum()),
        "completed": int((status_series == "completed").sum()),
        "blocked": int((status_series == "blocked").sum()),
    }


def build_experiment_roi_forecast(
    experiments_df: pd.DataFrame,
    profitability_df: pd.DataFrame,
    baseline_net_revenue: float,
    period_days: int = 90,
) -> pd.DataFrame:
    if experiments_df.empty:
        return pd.DataFrame(
            columns=[
                "name",
                "channel",
                "status",
                "target_uplift_pct",
                "confidence_factor",
                "projected_revenue_delta",
            ]
        )

    period_factor = max(float(period_days), 1.0) / 90.0
    experiments = experiments_df.copy()
    experiments["target_uplift_pct"] = pd.to_numeric(experiments.get("target_uplift_pct"), errors="coerce").fillna(0.0)
    experiments["channel"] = experiments.get("channel", "all").astype(str).str.strip().replace("", "all")
    experiments["status"] = experiments.get("status", "planned").astype(str).str.strip().str.lower().replace("", "planned")
    experiments["name"] = experiments.get("name", "Experiment").astype(str).str.strip().replace("", "Experiment")

    confidence_map = {"planned": 0.30, "running": 0.60, "completed": 0.90, "archived": 0.00}
    experiments["confidence_factor"] = experiments["status"].map(confidence_map).fillna(0.30)

    revenue = max(float(baseline_net_revenue), 0.0)
    if profitability_df.empty or "channel" not in profitability_df.columns:
        channel_weights = pd.DataFrame({"channel": ["all"], "weight": [1.0]})
    else:
        channel_weights = profitability_df.copy()
        if "customers" in channel_weights.columns:
            channel_weights["customers"] = pd.to_numeric(channel_weights["customers"], errors="coerce").fillna(0.0)
            total_customers = float(channel_weights["customers"].sum())
            if total_customers > 0:
                channel_weights["weight"] = channel_weights["customers"] / total_customers
            else:
                channel_weights["weight"] = 1.0 / max(len(channel_weights), 1)
        else:
            channel_weights["weight"] = 1.0 / max(len(channel_weights), 1)
        channel_weights["channel"] = channel_weights["channel"].astype(str).str.strip().replace("", "all")
        channel_weights = channel_weights[["channel", "weight"]].drop_duplicates(subset=["channel"], keep="first")
        if channel_weights.empty:
            channel_weights = pd.DataFrame({"channel": ["all"], "weight": [1.0]})

    merged = experiments.merge(channel_weights, on="channel", how="left")
    merged["weight"] = merged["weight"].fillna(1.0 / max(len(channel_weights), 1))
    merged["target_uplift_pct"] = merged["target_uplift_pct"].clip(lower=-100.0, upper=500.0)
    merged["projected_revenue_delta"] = (
        revenue
        * merged["weight"]
        * (merged["target_uplift_pct"] / 100.0)
        * merged["confidence_factor"]
        * period_factor
    )
    merged["projected_revenue_delta"] = np.where(np.isfinite(merged["projected_revenue_delta"]), merged["projected_revenue_delta"], 0.0)

    out_cols = [
        "name",
        "channel",
        "status",
        "target_uplift_pct",
        "confidence_factor",
        "projected_revenue_delta",
    ]
    return merged[out_cols].sort_values("projected_revenue_delta", ascending=False).reset_index(drop=True)
