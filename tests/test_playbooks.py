import pandas as pd

from python.analysis.playbooks import (
    build_experiment_roi_forecast,
    seed_playbooks_from_signals,
    summarize_playbook_status,
)


def test_seed_playbooks_from_signals_includes_recommendations_and_anomalies() -> None:
    recommendations = pd.DataFrame(
        [
            {"priority": "high", "theme": "channel_efficiency", "action": "Reduce low-performing spend clusters"},
        ]
    )
    anomalies = pd.DataFrame(
        [
            {"severity": "warn", "check": "cac_spike", "channel": "google"},
            {"severity": "error", "check": "refund_spike", "channel": "meta"},
        ]
    )
    out = seed_playbooks_from_signals(recommendations, anomalies, max_items=5)
    assert not out.empty
    assert "playbook_id" in out.columns
    assert len(out) >= 2
    assert out["status"].eq("open").all()


def test_summarize_playbook_status_counts_each_state() -> None:
    playbooks = pd.DataFrame(
        [
            {"status": "open"},
            {"status": "in_progress"},
            {"status": "completed"},
            {"status": "blocked"},
            {"status": "completed"},
        ]
    )
    summary = summarize_playbook_status(playbooks)
    assert summary["open"] == 1
    assert summary["in_progress"] == 1
    assert summary["completed"] == 2
    assert summary["blocked"] == 1


def test_build_experiment_roi_forecast_generates_ranked_projection() -> None:
    experiments = pd.DataFrame(
        [
            {"name": "Google creative test", "channel": "google", "status": "running", "target_uplift_pct": 12.0},
            {"name": "Meta landing page test", "channel": "meta", "status": "completed", "target_uplift_pct": 8.0},
        ]
    )
    profitability = pd.DataFrame(
        [
            {"channel": "google", "customers": 60},
            {"channel": "meta", "customers": 40},
        ]
    )
    out = build_experiment_roi_forecast(experiments, profitability, baseline_net_revenue=100000.0, period_days=90)
    assert len(out) == 2
    assert "projected_revenue_delta" in out.columns
    assert out["projected_revenue_delta"].iloc[0] >= out["projected_revenue_delta"].iloc[1]
