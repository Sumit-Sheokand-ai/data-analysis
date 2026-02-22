from pathlib import Path

from python.analysis.anomaly import build_anomaly_report
from python.analysis.data_loader import load_from_csv


def test_anomaly_report_exists_for_baseline_data() -> None:
    root = Path(__file__).resolve().parents[1]
    frames = load_from_csv(root / "data" / "raw")
    report = build_anomaly_report(frames)
    assert not report.empty
    assert {"check", "severity", "metric", "detail"}.issubset(set(report.columns))


def test_anomaly_detects_forced_cac_spike() -> None:
    root = Path(__file__).resolve().parents[1]
    frames = load_from_csv(root / "data" / "raw")
    frames["marketing_spend"].loc[0, "spend"] = float(frames["marketing_spend"]["spend"].max()) * 1000
    report = build_anomaly_report(frames)
    assert (report["check"] == "cac_spike").any()
