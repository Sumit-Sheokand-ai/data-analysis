import pandas as pd

from python.analysis.optimizer import optimize_budget_allocation


def test_optimize_budget_allocation_generates_recommendations() -> None:
    cac = pd.DataFrame(
        [
            {"channel": "Google", "cac": 20.0},
            {"channel": "Meta", "cac": 10.0},
        ]
    )
    profitability = pd.DataFrame(
        [
            {"channel": "Google", "avg_predicted_ltv": 80.0},
            {"channel": "Meta", "avg_predicted_ltv": 40.0},
        ]
    )
    result, summary = optimize_budget_allocation(cac, profitability, total_budget=1000.0, target_max_cac=25.0, reserve_pct=0.0)
    assert not result.empty
    assert abs(float(result["recommended_spend"].sum()) - 1000.0) < 1e-6
    assert summary.projected_customers > 0
    assert summary.blended_cac > 0


def test_optimize_budget_allocation_applies_budget_reserve() -> None:
    cac = pd.DataFrame([{"channel": "Search", "cac": 10.0}])
    profitability = pd.DataFrame([{"channel": "Search", "avg_predicted_ltv": 30.0}])
    result, summary = optimize_budget_allocation(cac, profitability, total_budget=1000.0, target_max_cac=15.0, reserve_pct=20.0)
    assert not result.empty
    assert abs(float(result["recommended_spend"].sum()) - 800.0) < 1e-6
    assert abs(summary.usable_budget - 800.0) < 1e-6
