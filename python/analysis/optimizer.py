from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OptimizationSummary:
    usable_budget: float
    projected_customers: float
    projected_value: float
    blended_cac: float
    blended_value_to_spend: float


def optimize_budget_allocation(
    cac_df: pd.DataFrame,
    profitability_df: pd.DataFrame,
    total_budget: float,
    target_max_cac: float,
    reserve_pct: float = 0.0,
) -> tuple[pd.DataFrame, OptimizationSummary]:
    reserve_pct = float(np.clip(reserve_pct, 0.0, 95.0))
    usable_budget = max(float(total_budget), 0.0) * (1.0 - reserve_pct / 100.0)

    base = cac_df.copy()
    base["cac"] = pd.to_numeric(base.get("cac"), errors="coerce")
    merged = base.merge(
        profitability_df[["channel", "avg_predicted_ltv"]],
        on="channel",
        how="left",
    )
    merged["avg_predicted_ltv"] = pd.to_numeric(merged.get("avg_predicted_ltv"), errors="coerce")
    merged = merged[(merged["cac"] > 0) & merged["cac"].notna()].copy()
    if merged.empty:
        empty = pd.DataFrame(
            columns=[
                "channel",
                "cac",
                "avg_predicted_ltv",
                "efficiency_score",
                "recommended_share",
                "recommended_spend",
                "projected_customers",
                "projected_value",
                "projected_value_to_spend",
            ]
        )
        summary = OptimizationSummary(
            usable_budget=usable_budget,
            projected_customers=0.0,
            projected_value=0.0,
            blended_cac=0.0,
            blended_value_to_spend=0.0,
        )
        return empty, summary

    merged["avg_predicted_ltv"] = merged["avg_predicted_ltv"].fillna(0.0)
    merged["base_efficiency"] = merged["avg_predicted_ltv"] / merged["cac"]
    if target_max_cac > 0:
        merged["cac_penalty"] = np.where(
            merged["cac"] > target_max_cac,
            target_max_cac / merged["cac"],
            1.0,
        )
    else:
        merged["cac_penalty"] = 1.0

    merged["efficiency_score"] = (merged["base_efficiency"] * merged["cac_penalty"]).clip(lower=0.0)
    if float(merged["efficiency_score"].sum()) <= 0:
        merged["efficiency_score"] = 1.0 / merged["cac"]

    merged["recommended_share"] = merged["efficiency_score"] / merged["efficiency_score"].sum()
    merged["recommended_spend"] = merged["recommended_share"] * usable_budget
    merged["projected_customers"] = np.where(merged["cac"] > 0, merged["recommended_spend"] / merged["cac"], 0.0)
    merged["projected_value"] = merged["projected_customers"] * merged["avg_predicted_ltv"]
    merged["projected_value_to_spend"] = np.where(
        merged["recommended_spend"] > 0,
        merged["projected_value"] / merged["recommended_spend"],
        0.0,
    )

    projected_customers = float(merged["projected_customers"].sum())
    projected_value = float(merged["projected_value"].sum())
    blended_cac = float(usable_budget / projected_customers) if projected_customers > 0 else 0.0
    blended_value_to_spend = float(projected_value / usable_budget) if usable_budget > 0 else 0.0

    summary = OptimizationSummary(
        usable_budget=float(usable_budget),
        projected_customers=projected_customers,
        projected_value=projected_value,
        blended_cac=blended_cac,
        blended_value_to_spend=blended_value_to_spend,
    )
    output_cols = [
        "channel",
        "cac",
        "avg_predicted_ltv",
        "efficiency_score",
        "recommended_share",
        "recommended_spend",
        "projected_customers",
        "projected_value",
        "projected_value_to_spend",
    ]
    return merged[output_cols].sort_values("recommended_spend", ascending=False).reset_index(drop=True), summary
