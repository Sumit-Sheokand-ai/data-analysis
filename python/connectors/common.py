from __future__ import annotations

from typing import Iterable
import pandas as pd


def first_existing_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lowered = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        hit = lowered.get(candidate.lower())
        if hit:
            return hit
    return None


def pick_series(df: pd.DataFrame, candidates: Iterable[str], default_value=None) -> pd.Series:
    col = first_existing_column(df, candidates)
    if col:
        return df[col]
    return pd.Series([default_value] * len(df), index=df.index)
