from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def load_snapshot_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def build_overview_deltas(current: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    if current.empty or previous.empty:
        return pd.DataFrame()
    if not {"metric", "value"}.issubset(current.columns) or not {"metric", "value"}.issubset(previous.columns):
        return pd.DataFrame()

    cur = current[["metric", "value"]].copy()
    prev = previous[["metric", "value"]].copy()
    cur["value"] = pd.to_numeric(cur["value"], errors="coerce")
    prev["value"] = pd.to_numeric(prev["value"], errors="coerce")

    merged = cur.merge(prev, on="metric", how="inner", suffixes=("_current", "_previous"))
    if merged.empty:
        return pd.DataFrame()

    merged["delta"] = merged["value_current"] - merged["value_previous"]
    merged["delta_pct"] = np.where(
        merged["value_previous"].abs() > 1e-9,
        (merged["delta"] / merged["value_previous"]) * 100.0,
        np.nan,
    )
    return merged.sort_values("metric").reset_index(drop=True)


def build_channel_metric_deltas(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    metric_col: str,
) -> pd.DataFrame:
    if current.empty or previous.empty:
        return pd.DataFrame()
    if "channel" not in current.columns or "channel" not in previous.columns:
        return pd.DataFrame()
    if metric_col not in current.columns or metric_col not in previous.columns:
        return pd.DataFrame()

    cur = current[["channel", metric_col]].copy()
    prev = previous[["channel", metric_col]].copy()
    cur[metric_col] = pd.to_numeric(cur[metric_col], errors="coerce")
    prev[metric_col] = pd.to_numeric(prev[metric_col], errors="coerce")

    merged = cur.merge(prev, on="channel", how="inner", suffixes=("_current", "_previous"))
    value_current = f"{metric_col}_current"
    value_previous = f"{metric_col}_previous"
    if merged.empty:
        return pd.DataFrame()

    merged["delta"] = merged[value_current] - merged[value_previous]
    merged["delta_pct"] = np.where(
        merged[value_previous].abs() > 1e-9,
        (merged["delta"] / merged[value_previous]) * 100.0,
        np.nan,
    )
    return merged.sort_values("delta", ascending=False).reset_index(drop=True)
