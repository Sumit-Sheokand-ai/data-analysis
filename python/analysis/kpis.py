from __future__ import annotations

from typing import Dict
from contextlib import redirect_stderr, redirect_stdout
import io
import warnings
import numpy as np
import pandas as pd


def _to_utc_naive(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_localize(None)


def _to_month_start(series: pd.Series) -> pd.Series:
    return _to_utc_naive(series).dt.to_period("M").dt.to_timestamp()


def prep_orders_with_margin(orders: pd.DataFrame, refunds: pd.DataFrame) -> pd.DataFrame:
    refunds_agg = (
        refunds.groupby("order_id", as_index=False)["refund_amount"].sum()
        if not refunds.empty
        else pd.DataFrame(columns=["order_id", "refund_amount"])
    )
    merged = orders.merge(refunds_agg, on="order_id", how="left")
    merged["refund_amount"] = merged["refund_amount"].fillna(0.0)
    merged["discount"] = merged["discount"].fillna(0.0)
    merged["cogs"] = merged["cogs"].fillna(0.0)
    merged["order_ts"] = _to_utc_naive(merged["order_ts"])
    merged["net_revenue"] = merged["gross_revenue"] - merged["discount"] - merged["refund_amount"]
    merged["contribution_margin"] = merged["net_revenue"] - merged["cogs"]
    merged["order_month"] = _to_month_start(merged["order_ts"])
    return merged


def attribute_customers_last_non_direct(
    customers: pd.DataFrame, orders: pd.DataFrame, sessions: pd.DataFrame
) -> pd.DataFrame:
    orders = orders.copy()
    sessions = sessions.copy()
    orders["order_ts"] = _to_utc_naive(orders["order_ts"])
    sessions["session_ts"] = _to_utc_naive(sessions["session_ts"])

    first_orders = (
        orders.sort_values(["customer_id", "order_ts"])
        .groupby("customer_id", as_index=False)
        .first()[["customer_id", "order_id", "order_ts"]]
        .rename(columns={"order_id": "first_order_id", "order_ts": "first_order_ts"})
    )

    sessions_sorted = sessions.sort_values(["customer_id", "session_ts"])
    merged = sessions_sorted.merge(first_orders, on="customer_id", how="inner")
    eligible = merged[merged["session_ts"] <= merged["first_order_ts"]].copy()
    non_direct = eligible[eligible["channel"].str.lower().fillna("direct") != "direct"]

    last_touch = (
        non_direct.sort_values(["customer_id", "session_ts"])
        .groupby("customer_id", as_index=False)
        .last()[["customer_id", "channel"]]
        .rename(columns={"channel": "attributed_channel"})
    )

    out = first_orders.merge(customers[["customer_id", "acquisition_channel"]], on="customer_id", how="left")
    out = out.merge(last_touch, on="customer_id", how="left")
    out["attributed_channel"] = out["attributed_channel"].fillna(out["acquisition_channel"]).fillna("unknown")
    out["first_order_month"] = _to_month_start(out["first_order_ts"])
    return out


def compute_cac(marketing_spend: pd.DataFrame, attributions: pd.DataFrame) -> pd.DataFrame:
    spend = marketing_spend.copy()
    spend["date"] = pd.to_datetime(spend["date"], utc=True, errors="coerce").dt.date
    spend_rollup = (
        spend.groupby("channel", as_index=False)[["spend", "sales_cost"]].sum()
        .assign(total_cost=lambda d: d["spend"] + d["sales_cost"])
    )

    new_customers = (
        attributions.groupby("attributed_channel", as_index=False)["customer_id"]
        .nunique()
        .rename(columns={"attributed_channel": "channel", "customer_id": "new_customers"})
    )

    out = spend_rollup.merge(new_customers, on="channel", how="outer").fillna(0)
    out["cac"] = np.where(out["new_customers"] > 0, out["total_cost"] / out["new_customers"], np.nan)
    return out.sort_values("channel").reset_index(drop=True)


def compute_retention(orders_with_margin: pd.DataFrame) -> pd.DataFrame:
    first_month = (
        orders_with_margin.groupby("customer_id", as_index=False)["order_month"]
        .min()
        .rename(columns={"order_month": "cohort_month"})
    )
    cohort_data = orders_with_margin[["customer_id", "order_month"]].merge(first_month, on="customer_id", how="left")

    cohort_data["month_index"] = (
        (cohort_data["order_month"].dt.year - cohort_data["cohort_month"].dt.year) * 12
        + (cohort_data["order_month"].dt.month - cohort_data["cohort_month"].dt.month)
    )

    grouped = (
        cohort_data.groupby(["cohort_month", "month_index"], as_index=False)["customer_id"]
        .nunique()
        .rename(columns={"customer_id": "active_customers"})
    )
    base = grouped[grouped["month_index"] == 0][["cohort_month", "active_customers"]].rename(
        columns={"active_customers": "cohort_size"}
    )
    retention = grouped.merge(base, on="cohort_month", how="left")
    retention["retention_rate"] = np.where(
        retention["cohort_size"] > 0, retention["active_customers"] / retention["cohort_size"], np.nan
    )
    return retention.sort_values(["cohort_month", "month_index"]).reset_index(drop=True)


def compute_realized_ltv(orders_with_margin: pd.DataFrame) -> pd.DataFrame:
    ltv = (
        orders_with_margin.groupby("customer_id", as_index=False)
        .agg(
            realized_ltv=("contribution_margin", "sum"),
            total_net_revenue=("net_revenue", "sum"),
            order_count=("order_id", "count"),
            first_order_ts=("order_ts", "min"),
            last_order_ts=("order_ts", "max"),
        )
        .sort_values("realized_ltv", ascending=False)
        .reset_index(drop=True)
    )
    return ltv


def _predictive_ltv_fallback(realized_ltv: pd.DataFrame) -> pd.DataFrame:
    avg_margin = realized_ltv["realized_ltv"].clip(lower=0).mean() if not realized_ltv.empty else 0.0
    repeat_rate = (realized_ltv["order_count"] > 1).mean() if not realized_ltv.empty else 0.0
    churn_rate = max(0.05, 1.0 - repeat_rate)
    expected_lifetime_months = min(36.0, max(3.0, 1.0 / churn_rate))
    monthly_margin = avg_margin / max(1.0, realized_ltv["order_count"].mean() if not realized_ltv.empty else 1.0)

    out = realized_ltv[["customer_id"]].copy()
    out["predicted_ltv"] = monthly_margin * expected_lifetime_months
    out["prediction_method"] = "fallback_proxy"
    return out


def compute_predictive_ltv(orders_with_margin: pd.DataFrame, horizon_months: int = 12) -> pd.DataFrame:
    realized = compute_realized_ltv(orders_with_margin)
    try:
        from lifetimes import BetaGeoFitter, GammaGammaFitter
        from lifetimes.utils import summary_data_from_transaction_data
    except Exception:
        return _predictive_ltv_fallback(realized)

    tx = orders_with_margin.copy()
    tx["order_date"] = _to_utc_naive(tx["order_ts"])

    try:
        summary = summary_data_from_transaction_data(
            tx,
            customer_id_col="customer_id",
            datetime_col="order_date",
            monetary_value_col="contribution_margin",
            observation_period_end=tx["order_date"].max(),
            freq="D",
        )
    except Exception:
        return _predictive_ltv_fallback(realized)

    if summary.empty or summary["frequency"].sum() <= 0:
        return _predictive_ltv_fallback(realized)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            warnings.filterwarnings("ignore", category=UserWarning)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                bgf = BetaGeoFitter(penalizer_coef=0.01)
                bgf.fit(summary["frequency"], summary["recency"], summary["T"], verbose=False)

                returning = summary[summary["frequency"] > 0].copy()
                if returning.empty:
                    return _predictive_ltv_fallback(realized)

                ggf = GammaGammaFitter(penalizer_coef=0.01)
                ggf.fit(returning["frequency"], returning["monetary_value"], verbose=False)

            summary["predicted_purchases"] = bgf.conditional_expected_number_of_purchases_up_to_time(
                horizon_months * 30, summary["frequency"], summary["recency"], summary["T"]
            )

            summary["expected_monetary_value"] = np.nan
            summary.loc[returning.index, "expected_monetary_value"] = ggf.conditional_expected_average_profit(
                returning["frequency"], returning["monetary_value"]
            )
            summary["expected_monetary_value"] = summary["expected_monetary_value"].fillna(
                summary["monetary_value"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            )

            summary["predicted_ltv"] = summary["predicted_purchases"] * summary["expected_monetary_value"]
            out = summary.reset_index()[["customer_id", "predicted_ltv"]]
            out["prediction_method"] = "bgnbd_gamma_gamma"
            return out
    except Exception:
        return _predictive_ltv_fallback(realized)


def compute_channel_profitability(
    attributions: pd.DataFrame,
    realized_ltv: pd.DataFrame,
    predictive_ltv: pd.DataFrame,
    cac_by_channel: pd.DataFrame,
) -> pd.DataFrame:
    ltv = realized_ltv.merge(predictive_ltv[["customer_id", "predicted_ltv"]], on="customer_id", how="left")
    ltv = ltv.merge(attributions[["customer_id", "attributed_channel"]], on="customer_id", how="left")

    agg = (
        ltv.groupby("attributed_channel", as_index=False)
        .agg(
            customers=("customer_id", "nunique"),
            avg_realized_ltv=("realized_ltv", "mean"),
            avg_predicted_ltv=("predicted_ltv", "mean"),
            avg_order_count=("order_count", "mean"),
        )
        .rename(columns={"attributed_channel": "channel"})
    )

    out = agg.merge(cac_by_channel[["channel", "cac"]], on="channel", how="left")
    out["ltv_cac_ratio"] = np.where(out["cac"] > 0, out["avg_predicted_ltv"] / out["cac"], np.nan)
    avg_monthly_margin = out["avg_realized_ltv"] / out["avg_order_count"].replace(0, np.nan)
    out["payback_months_est"] = np.where(avg_monthly_margin > 0, out["cac"] / avg_monthly_margin, np.nan)
    return out.sort_values("channel").reset_index(drop=True)


def build_overview_kpis(
    orders_with_margin: pd.DataFrame,
    cac_by_channel: pd.DataFrame,
    channel_profitability: pd.DataFrame,
) -> pd.DataFrame:
    total_net_revenue = float(orders_with_margin["net_revenue"].sum())
    total_contribution_margin = float(orders_with_margin["contribution_margin"].sum())
    customers = int(orders_with_margin["customer_id"].nunique())
    orders = int(orders_with_margin["order_id"].nunique())
    avg_cac = float(cac_by_channel["cac"].dropna().mean()) if not cac_by_channel.empty else np.nan
    avg_ltv_cac = (
        float(channel_profitability["ltv_cac_ratio"].dropna().mean())
        if not channel_profitability.empty
        else np.nan
    )

    return pd.DataFrame(
        [
            {"metric": "total_net_revenue", "value": total_net_revenue},
            {"metric": "total_contribution_margin", "value": total_contribution_margin},
            {"metric": "customers", "value": customers},
            {"metric": "orders", "value": orders},
            {"metric": "avg_cac", "value": avg_cac},
            {"metric": "avg_ltv_cac_ratio", "value": avg_ltv_cac},
        ]
    )


def build_data_quality_report(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in frames.items():
        rows.append(
            {
                "table": name,
                "row_count": int(len(df)),
                "duplicate_rows": int(df.duplicated().sum()),
                "null_cells": int(df.isna().sum().sum()),
            }
        )
    return pd.DataFrame(rows)


def run_all_kpis(frames: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    orders_with_margin = prep_orders_with_margin(frames["orders"], frames["refunds"])
    attributions = attribute_customers_last_non_direct(frames["customers"], orders_with_margin, frames["sessions"])
    cac = compute_cac(frames["marketing_spend"], attributions)
    retention = compute_retention(orders_with_margin)
    realized_ltv = compute_realized_ltv(orders_with_margin)
    predictive_ltv = compute_predictive_ltv(orders_with_margin)
    profitability = compute_channel_profitability(attributions, realized_ltv, predictive_ltv, cac)
    overview = build_overview_kpis(orders_with_margin, cac, profitability)
    quality = build_data_quality_report(frames)

    return {
        "orders_with_margin": orders_with_margin,
        "customer_attribution": attributions,
        "cac_by_channel": cac,
        "retention_monthly": retention,
        "ltv_by_customer": realized_ltv.merge(
            predictive_ltv[["customer_id", "predicted_ltv", "prediction_method"]],
            on="customer_id",
            how="left",
        ),
        "channel_profitability": profitability,
        "kpi_overview": overview,
        "data_quality": quality,
    }
