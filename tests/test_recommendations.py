import pandas as pd

from python.analysis.recommendations import build_growth_recommendations


def test_build_growth_recommendations_returns_prioritized_actions() -> None:
    cac = pd.DataFrame(
        [
            {"channel": "Google", "cac": 120.0},
            {"channel": "Meta", "cac": 60.0},
        ]
    )
    profitability = pd.DataFrame(
        [
            {"channel": "Google", "ltv_cac_ratio": 1.2},
            {"channel": "Meta", "ltv_cac_ratio": 2.5},
        ]
    )
    retention = pd.DataFrame(
        [
            {"month_index": 1, "retention_rate": 0.25},
            {"month_index": 2, "retention_rate": 0.18},
        ]
    )
    anomaly = pd.DataFrame(
        [
            {"severity": "warn"},
            {"severity": "error"},
        ]
    )
    out = build_growth_recommendations(cac, profitability, retention, anomaly, max_items=5)
    assert not out.empty
    assert set(["priority", "theme", "action", "rationale", "expected_impact"]).issubset(out.columns)
    assert (out["priority"] == "high").any()


def test_build_growth_recommendations_returns_data_readiness_fallback() -> None:
    out = build_growth_recommendations(
        cac_df=pd.DataFrame(),
        profitability_df=pd.DataFrame(),
        retention_df=pd.DataFrame(),
        anomaly_df=pd.DataFrame(),
        max_items=3,
    )
    assert len(out) == 1
    assert out.iloc[0]["theme"] == "data_readiness"
