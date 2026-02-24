from __future__ import annotations

import pandas as pd


def _safe_to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def build_growth_recommendations(
    cac_df: pd.DataFrame,
    profitability_df: pd.DataFrame,
    retention_df: pd.DataFrame,
    anomaly_df: pd.DataFrame,
    max_items: int = 5,
) -> pd.DataFrame:
    recommendations: list[dict[str, str]] = []

    if not cac_df.empty and {"channel", "cac"}.issubset(cac_df.columns):
        current_cac = cac_df.copy()
        current_cac["cac"] = _safe_to_numeric(current_cac["cac"])
        current_cac = current_cac[current_cac["cac"].notna()]
        if not current_cac.empty:
            highest_cac_row = current_cac.sort_values("cac", ascending=False).iloc[0]
            lowest_cac = float(current_cac["cac"].min())
            highest_cac = float(highest_cac_row["cac"])
            if highest_cac > 0 and lowest_cac / highest_cac <= 0.8:
                recommendations.append(
                    {
                        "priority": "high",
                        "theme": "channel_efficiency",
                        "action": f"Audit `{highest_cac_row['channel']}` spend mix and reduce low-converting segments.",
                        "rationale": f"CAC spread is wide (best {lowest_cac:.2f} vs worst {highest_cac:.2f}).",
                        "expected_impact": "Lower blended CAC in upcoming cycle",
                    }
                )

    if not profitability_df.empty and {"channel", "ltv_cac_ratio"}.issubset(profitability_df.columns):
        p = profitability_df.copy()
        p["ltv_cac_ratio"] = _safe_to_numeric(p["ltv_cac_ratio"])
        p = p[p["ltv_cac_ratio"].notna()]
        if not p.empty:
            best = p.sort_values("ltv_cac_ratio", ascending=False).iloc[0]
            recommendations.append(
                {
                    "priority": "medium",
                    "theme": "budget_reallocation",
                    "action": f"Shift incremental budget toward `{best['channel']}` and retest after one cycle.",
                    "rationale": f"Top LTV:CAC channel currently at {float(best['ltv_cac_ratio']):.2f}.",
                    "expected_impact": "Increase value-to-spend ratio",
                }
            )

    if not retention_df.empty and {"month_index", "retention_rate"}.issubset(retention_df.columns):
        month1 = retention_df[retention_df["month_index"] == 1].copy()
        month1["retention_rate"] = _safe_to_numeric(month1["retention_rate"])
        month1 = month1[month1["retention_rate"].notna()]
        if not month1.empty:
            median_r1 = float(month1["retention_rate"].median())
            if median_r1 < 0.35:
                recommendations.append(
                    {
                        "priority": "high",
                        "theme": "retention_recovery",
                        "action": "Launch post-purchase winback flow and loyalty trigger for first 30 days.",
                        "rationale": f"Median month-1 retention is {median_r1 * 100:.1f}%.",
                        "expected_impact": "Higher repeat purchase rate and realized LTV",
                    }
                )

    if not anomaly_df.empty and "severity" in anomaly_df.columns:
        sev = anomaly_df["severity"].astype(str).str.strip().str.lower()
        error_count = int((sev == "error").sum())
        warn_count = int((sev == "warn").sum())
        if error_count > 0 or warn_count > 0:
            recommendations.append(
                {
                    "priority": "high" if error_count > 0 else "medium",
                    "theme": "risk_mitigation",
                    "action": "Assign anomaly owners and enforce response SLA for active alerts.",
                    "rationale": f"Monitoring shows {warn_count} warnings and {error_count} errors.",
                    "expected_impact": "Reduce downside risk from spend or refund spikes",
                }
            )

    if not recommendations:
        recommendations.append(
            {
                "priority": "info",
                "theme": "data_readiness",
                "action": "Collect one more complete cycle of real data before optimization.",
                "rationale": "Insufficient variance signals for high-confidence recommendations.",
                "expected_impact": "Higher confidence for next recommendation batch",
            }
        )

    out = pd.DataFrame(recommendations).head(max(int(max_items), 1)).reset_index(drop=True)
    return out
