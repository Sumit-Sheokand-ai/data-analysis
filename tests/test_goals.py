import pandas as pd

from python.analysis.goals import build_goal_snapshot, recommend_autopilot_actions


def test_build_goal_snapshot_marks_on_track_and_off_track() -> None:
    overview = pd.DataFrame(
        [
            {"metric": "avg_cac", "value": 95.0},
            {"metric": "avg_ltv_cac_ratio", "value": 2.1},
        ]
    )
    retention = pd.DataFrame(
        [
            {"month_index": 1, "retention_rate": 0.28},
            {"month_index": 2, "retention_rate": 0.21},
        ]
    )
    anomaly = pd.DataFrame(
        [
            {"severity": "error"},
            {"severity": "warn"},
        ]
    )
    targets = {
        "avg_cac": 80.0,
        "avg_ltv_cac_ratio": 2.5,
        "month1_retention": 0.35,
        "active_error_alerts": 0.0,
    }
    out = build_goal_snapshot(overview, retention, anomaly, targets)
    assert len(out) == 4
    assert set(["metric", "current_value", "target_value", "status"]).issubset(out.columns)
    assert (out["status"] == "off_track").any()


def test_recommend_autopilot_actions_outputs_action_rows() -> None:
    snapshot = pd.DataFrame(
        [
            {"metric": "avg_cac", "status": "off_track"},
            {"metric": "avg_ltv_cac_ratio", "status": "on_track"},
            {"metric": "month1_retention", "status": "at_risk"},
        ]
    )
    out = recommend_autopilot_actions(snapshot, max_items=5)
    assert not out.empty
    assert set(["metric", "priority", "action", "owner"]).issubset(out.columns)
    assert (out["metric"] == "avg_cac").any()
