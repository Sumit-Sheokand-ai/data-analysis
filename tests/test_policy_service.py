import json
import threading
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

from python.services.policy_api import create_policy_http_server
from python.services.policy_service import (
    get_plan_metadata,
    get_usage_counters,
    has_feature_for_plan,
    set_usage_counters,
)


def test_policy_service_local_entitlements_and_plan_metadata() -> None:
    assert has_feature_for_plan(plan_slug="growth", feature="scheduled_reports")
    assert not has_feature_for_plan(plan_slug="starter", feature="scheduled_reports")
    plan = get_plan_metadata(plan_slug="pro")
    assert plan["slug"] == "pro"
    assert int(plan["limits"]["max_stores"]) > 0
    assert "feature_flags" in plan


def test_policy_service_local_usage_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "policy_state.json"
    defaults = {"report_exports": 0, "pipeline_runs": 0}
    initial = get_usage_counters(default_counters=defaults, state_file=state_file)
    assert initial == defaults

    set_usage_counters(
        counters={"report_exports": 3, "pipeline_runs": 1},
        state_file=state_file,
    )
    persisted = get_usage_counters(default_counters=defaults, state_file=state_file)
    assert persisted["report_exports"] == 3
    assert persisted["pipeline_runs"] == 1


def test_policy_service_usage_is_workspace_scoped(tmp_path: Path) -> None:
    state_file = tmp_path / "policy_state.json"
    defaults = {"report_exports": 0, "pipeline_runs": 0}
    set_usage_counters(
        counters={"report_exports": 2, "pipeline_runs": 1},
        state_file=state_file,
        workspace_id="workspace-a",
    )
    set_usage_counters(
        counters={"report_exports": 9, "pipeline_runs": 4},
        state_file=state_file,
        workspace_id="workspace-b",
    )
    usage_a = get_usage_counters(default_counters=defaults, state_file=state_file, workspace_id="workspace-a")
    usage_b = get_usage_counters(default_counters=defaults, state_file=state_file, workspace_id="workspace-b")
    assert usage_a["report_exports"] == 2
    assert usage_b["report_exports"] == 9


def test_policy_service_http_mode_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "policy_state.json"
    server = create_policy_http_server(host="127.0.0.1", port=0, state_file=state_file)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service_url = f"http://127.0.0.1:{server.server_port}"
    try:
        set_usage_counters(
            counters={"report_exports": 8, "pipeline_runs": 2},
            state_file=tmp_path / "ignored.json",
            service_url=service_url,
            timeout_seconds=5,
        )
        usage = get_usage_counters(
            default_counters={"report_exports": 0, "pipeline_runs": 0},
            state_file=tmp_path / "ignored.json",
            service_url=service_url,
            timeout_seconds=5,
        )
        assert usage["report_exports"] == 8
        assert usage["pipeline_runs"] == 2
        assert has_feature_for_plan(
            plan_slug="enterprise",
            feature="ai_growth_copilot",
            service_url=service_url,
            timeout_seconds=5,
        )
        assert not has_feature_for_plan(
            plan_slug="starter",
            feature="ai_growth_copilot",
            service_url=service_url,
            timeout_seconds=5,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_policy_api_requires_auth_when_token_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SERVICE_API_AUTH_TOKEN", "policy-token")
    server = create_policy_http_server(host="127.0.0.1", port=0, state_file=tmp_path / "policy_state.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized_request = urllib_request.Request(url=f"{base_url}/usage", method="GET")
        with pytest.raises(urllib_error.HTTPError) as exc_info:
            urllib_request.urlopen(unauthorized_request, timeout=5)
        assert exc_info.value.code == 401

        set_usage_counters(
            counters={"report_exports": 5, "pipeline_runs": 2},
            state_file=tmp_path / "ignored.json",
            service_url=base_url,
            timeout_seconds=5,
            workspace_id="secure-workspace",
            service_token="policy-token",
        )
        usage = get_usage_counters(
            default_counters={"report_exports": 0, "pipeline_runs": 0},
            state_file=tmp_path / "ignored.json",
            service_url=base_url,
            timeout_seconds=5,
            workspace_id="secure-workspace",
            service_token="policy-token",
        )
        assert usage["report_exports"] == 5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_policy_api_usage_endpoint_validates_payload(tmp_path: Path) -> None:
    server = create_policy_http_server(host="127.0.0.1", port=0, state_file=tmp_path / "policy_state.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        bad_request = urllib_request.Request(
            url=f"{base_url}/usage",
            data=json.dumps({"usage_counters": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with pytest.raises(urllib_error.HTTPError) as exc_info:
            urllib_request.urlopen(bad_request, timeout=5)
        assert exc_info.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
