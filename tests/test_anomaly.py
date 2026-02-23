import python.analysis.anomaly as anomaly_module
from python.analysis.anomaly import build_anomaly_report


def test_anomaly_report_exists_for_baseline_data(sample_frames) -> None:
    frames = sample_frames
    report = build_anomaly_report(frames)
    assert not report.empty
    assert {"check", "severity", "metric", "detail"}.issubset(set(report.columns))


def test_anomaly_detects_forced_cac_spike(sample_frames, monkeypatch) -> None:
    frames = sample_frames
    frames["marketing_spend"].loc[0, "spend"] = float(frames["marketing_spend"]["spend"].max()) * 1000
    monkeypatch.setattr(anomaly_module, "_upper_threshold", lambda _series: 1.0)
    report = build_anomaly_report(frames)
    assert (report["check"] == "cac_spike").any()
