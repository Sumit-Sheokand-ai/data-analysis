import pandas as pd

from python.analysis.diagnostics import build_channel_metric_deltas, build_overview_deltas


def test_build_overview_deltas_returns_expected_delta_rows() -> None:
    current = pd.DataFrame(
        [
            {"metric": "total_net_revenue", "value": 120.0},
            {"metric": "avg_cac", "value": 10.0},
        ]
    )
    previous = pd.DataFrame(
        [
            {"metric": "total_net_revenue", "value": 100.0},
            {"metric": "avg_cac", "value": 8.0},
        ]
    )
    out = build_overview_deltas(current, previous)
    assert len(out) == 2
    revenue_row = out[out["metric"] == "total_net_revenue"].iloc[0]
    assert float(revenue_row["delta"]) == 20.0


def test_build_channel_metric_deltas_returns_sorted_delta() -> None:
    current = pd.DataFrame(
        [
            {"channel": "Google", "cac": 12.0},
            {"channel": "Meta", "cac": 9.0},
        ]
    )
    previous = pd.DataFrame(
        [
            {"channel": "Google", "cac": 10.0},
            {"channel": "Meta", "cac": 10.0},
        ]
    )
    out = build_channel_metric_deltas(current, previous, metric_col="cac")
    assert len(out) == 2
    assert out.iloc[0]["channel"] == "Google"
    assert float(out.iloc[0]["delta"]) == 2.0
