from __future__ import annotations

from pathlib import Path
from typing import Dict
import pandas as pd
from sqlalchemy import create_engine


RAW_FILES = {
    "marketing_spend": "raw_marketing_spend.csv",
    "sessions": "raw_sessions.csv",
    "customers": "raw_customers.csv",
    "orders": "raw_orders.csv",
    "refunds": "raw_refunds.csv",
}


def _normalize_channels(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = df[col].fillna("unknown").astype(str).str.strip()
    return df


def _parse_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def load_from_csv(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    frames: Dict[str, pd.DataFrame] = {}
    for key, filename in RAW_FILES.items():
        frames[key] = pd.read_csv(raw_dir / filename)

    frames["marketing_spend"] = _parse_dates(frames["marketing_spend"], ["date"])
    frames["sessions"] = _parse_dates(frames["sessions"], ["session_ts"])
    frames["customers"] = _parse_dates(frames["customers"], ["acquired_at"])
    frames["orders"] = _parse_dates(frames["orders"], ["order_ts"])
    frames["refunds"] = _parse_dates(frames["refunds"], ["refund_ts"])

    frames["sessions"] = _normalize_channels(frames["sessions"], "channel")
    frames["customers"] = _normalize_channels(frames["customers"], "acquisition_channel")
    frames["marketing_spend"] = _normalize_channels(frames["marketing_spend"], "channel")

    return frames


def load_from_postgres(database_url: str) -> Dict[str, pd.DataFrame]:
    engine = create_engine(database_url)
    frames = {
        "marketing_spend": pd.read_sql("SELECT * FROM stg.marketing_spend", engine),
        "sessions": pd.read_sql("SELECT * FROM stg.sessions", engine),
        "customers": pd.read_sql("SELECT * FROM stg.customers", engine),
        "orders": pd.read_sql("SELECT * FROM stg.orders", engine),
        "refunds": pd.read_sql("SELECT * FROM stg.refunds", engine),
    }

    frames["marketing_spend"] = _parse_dates(frames["marketing_spend"], ["date"])
    frames["sessions"] = _parse_dates(frames["sessions"], ["session_ts"])
    frames["customers"] = _parse_dates(frames["customers"], ["acquired_at"])
    frames["orders"] = _parse_dates(frames["orders"], ["order_ts"])
    frames["refunds"] = _parse_dates(frames["refunds"], ["refund_ts"])
    return frames
