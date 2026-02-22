from __future__ import annotations

from pathlib import Path
from typing import Dict
import pandas as pd

from .config import RAW_DATA_DIR, PROCESSED_DATA_DIR, DATABASE_URL
from .anomaly import build_anomaly_report
from .data_loader import load_from_csv, load_from_postgres
from .kpis import run_all_kpis
from .validation import validate_frames


def run_pipeline(
    data_source: str = "csv",
    raw_data_dir: Path | None = None,
    processed_data_dir: Path | None = None,
    database_url: str | None = None,
    validation_mode: str = "strict",
) -> Dict[str, pd.DataFrame]:
    source = data_source.strip().lower()
    raw_dir = raw_data_dir or RAW_DATA_DIR
    out_dir = processed_data_dir or PROCESSED_DATA_DIR
    db_url = database_url or DATABASE_URL

    if source == "postgres":
        if not db_url:
            raise ValueError("DATABASE_URL is required when data_source='postgres'.")
        frames = load_from_postgres(db_url)
    else:
        frames = load_from_csv(Path(raw_dir))
    validation_report = validate_frames(frames, mode=validation_mode)
    anomaly_report = build_anomaly_report(frames)

    outputs = run_all_kpis(frames)
    outputs["validation_report"] = validation_report
    outputs["anomaly_report"] = anomaly_report
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False)
    return outputs
