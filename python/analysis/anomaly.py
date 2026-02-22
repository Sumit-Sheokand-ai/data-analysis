from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List
import numpy as np
import pandas as pd

from .kpis import attribute_customers_last_non_direct, prep_orders_with_margin


@dataclass
class Anomaly:
    check: str
    severity: str
    date: str
    channel: str
    metric: str
    value: float
    threshold: float
    detail: str


def _upper_threshold(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return np.inf
    if len(s) >= 5:
        baseline = s[s <= s.quantile(0.90)]
        if baseline.empty:
            baseline = s
    else:
        baseline = s
    q1, q3 = baseline.quantile(0.25), baseline.quantile(0.75)
    iqr = q3 - q1
    iqr_threshold = q3 + 3 * iqr
    median_threshold = baseline.median() * 3
    return float(max(iqr_threshold, median_threshold))


def _build_daily_channel_attribution(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders_margin = prep_orders_with_margin(frames["orders"], frames["refunds"])
    attributions = attribute_customers_last_non_direct(frames["customers"], orders_margin, frames["sessions"])
    attributions["date"] = pd.to_datetime(attributions["first_order_ts"], utc=True, errors="coerce").dt.date
    out = (
        attributions.groupby(["date", "attributed_channel"], as_index=False)["customer_id"]
        .nunique()
        .rename(columns={"attributed_channel": "channel", "customer_id": "new_customers"})
    )
    return out


def _detect_cac_spikes(frames: Dict[str, pd.DataFrame]) -> List[Anomaly]:
    spend = frames["marketing_spend"].copy()
    spend["date"] = pd.to_datetime(spend["date"], utc=True, errors="coerce").dt.date
    spend["total_cost"] = pd.to_numeric(spend["spend"], errors="coerce").fillna(0) + pd.to_numeric(
        spend["sales_cost"], errors="coerce"
    ).fillna(0)
    spend = spend.groupby(["date", "channel"], as_index=False)["total_cost"].sum()

    new_customers = _build_daily_channel_attribution(frames)
    merged = spend.merge(new_customers, on=["date", "channel"], how="left")
    merged["new_customers"] = merged["new_customers"].fillna(0)
    merged["cac"] = np.where(merged["new_customers"] > 0, merged["total_cost"] / merged["new_customers"], np.nan)

    valid = merged.dropna(subset=["cac"]).copy()
    threshold = _upper_threshold(valid["cac"])
    rows = valid[valid["cac"] > threshold]
    anomalies: List[Anomaly] = []
    for r in rows.itertuples(index=False):
        anomalies.append(
            Anomaly(
                check="cac_spike",
                severity="warn",
                date=str(r.date),
                channel=str(r.channel),
                metric="cac",
                value=float(r.cac),
                threshold=float(threshold),
                detail="CAC exceeds robust upper threshold (IQR/median/std guardrails).",
            )
        )
    return anomalies


def _detect_refund_ratio_spikes(frames: Dict[str, pd.DataFrame]) -> List[Anomaly]:
    orders = frames["orders"][["order_id", "order_ts", "gross_revenue"]].copy()
    refunds = frames["refunds"][["order_id", "refund_amount"]].copy()
    merged = orders.merge(refunds, on="order_id", how="left")
    merged["refund_amount"] = pd.to_numeric(merged["refund_amount"], errors="coerce").fillna(0)
    merged["gross_revenue"] = pd.to_numeric(merged["gross_revenue"], errors="coerce").fillna(0)
    merged["date"] = pd.to_datetime(merged["order_ts"], utc=True, errors="coerce").dt.date

    daily = (
        merged.groupby("date", as_index=False)[["refund_amount", "gross_revenue"]]
        .sum()
        .assign(refund_ratio=lambda d: np.where(d["gross_revenue"] > 0, d["refund_amount"] / d["gross_revenue"], np.nan))
    )
    valid = daily.dropna(subset=["refund_ratio"]).copy()
    threshold = _upper_threshold(valid["refund_ratio"])
    hard_floor = 0.30
    effective_threshold = max(float(threshold), hard_floor)
    rows = valid[valid["refund_ratio"] > effective_threshold]

    anomalies: List[Anomaly] = []
    for r in rows.itertuples(index=False):
        anomalies.append(
            Anomaly(
                check="refund_ratio_spike",
                severity="warn",
                date=str(r.date),
                channel="all",
                metric="refund_ratio",
                value=float(r.refund_ratio),
                threshold=float(effective_threshold),
                detail="Refund ratio exceeds robust/hard threshold.",
            )
        )
    return anomalies


def _detect_conversion_spikes(frames: Dict[str, pd.DataFrame]) -> List[Anomaly]:
    sessions = frames["sessions"].copy()
    sessions["date"] = pd.to_datetime(sessions["session_ts"], utc=True, errors="coerce").dt.date
    session_counts = (
        sessions.groupby(["date", "channel"], as_index=False)["session_id"]
        .nunique()
        .rename(columns={"session_id": "sessions"})
    )

    new_customers = _build_daily_channel_attribution(frames)
    merged = session_counts.merge(new_customers, on=["date", "channel"], how="left")
    merged["new_customers"] = merged["new_customers"].fillna(0)
    merged["conversion_rate"] = np.where(merged["sessions"] > 0, merged["new_customers"] / merged["sessions"], np.nan)

    valid = merged.dropna(subset=["conversion_rate"]).copy()
    high_threshold = max(_upper_threshold(valid["conversion_rate"]), 0.35)
    rows = valid[(valid["conversion_rate"] > high_threshold) | (valid["conversion_rate"] > 1)]

    anomalies: List[Anomaly] = []
    for r in rows.itertuples(index=False):
        anomalies.append(
            Anomaly(
                check="conversion_rate_spike",
                severity="warn",
                date=str(r.date),
                channel=str(r.channel),
                metric="conversion_rate",
                value=float(r.conversion_rate),
                threshold=float(high_threshold),
                detail="Conversion rate exceeds robust threshold (or impossible > 1).",
            )
        )
    return anomalies


def build_anomaly_report(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    anomalies: List[Anomaly] = []
    anomalies.extend(_detect_cac_spikes(frames))
    anomalies.extend(_detect_refund_ratio_spikes(frames))
    anomalies.extend(_detect_conversion_spikes(frames))

    if not anomalies:
        return pd.DataFrame(
            [
                {
                    "check": "anomaly_monitoring_passed",
                    "severity": "info",
                    "date": "all",
                    "channel": "all",
                    "metric": "n/a",
                    "value": 0.0,
                    "threshold": 0.0,
                    "detail": "No anomaly spikes detected for monitored metrics.",
                }
            ]
        )

    return pd.DataFrame([asdict(a) for a in anomalies])
