from pathlib import Path
import pandas as pd

from python.analysis.data_loader import load_from_csv
from python.analysis.kpis import run_all_kpis


def test_kpi_outputs_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    frames = load_from_csv(root / "data" / "raw")
    outputs = run_all_kpis(frames)

    required = {
        "cac_by_channel",
        "retention_monthly",
        "ltv_by_customer",
        "channel_profitability",
        "kpi_overview",
        "data_quality",
    }
    assert required.issubset(set(outputs.keys()))


def test_cac_computation_positive_for_known_channels() -> None:
    root = Path(__file__).resolve().parents[1]
    frames = load_from_csv(root / "data" / "raw")
    outputs = run_all_kpis(frames)
    cac = outputs["cac_by_channel"]
    meta = cac[cac["channel"] == "Meta"]
    assert not meta.empty
    assert float(meta["cac"].iloc[0]) > 0


def test_retention_has_cohort_zero() -> None:
    root = Path(__file__).resolve().parents[1]
    frames = load_from_csv(root / "data" / "raw")
    outputs = run_all_kpis(frames)
    retention = outputs["retention_monthly"]
    assert (retention["month_index"] == 0).any()
