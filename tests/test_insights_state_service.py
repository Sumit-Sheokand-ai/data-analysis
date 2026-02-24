import json
import threading
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

from python.services.insights_api import create_insights_http_server
from python.services.insights_state_service import get_state_value, set_state_value


def test_local_state_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "insights_state.json"
    default_value = [{"type": "email", "target": "owner@company.com"}]
    initial = get_state_value(
        state_key="alert_destinations",
        default_value=default_value,
        state_file=state_file,
    )
    assert initial == default_value

    updated_value = [{"type": "webhook", "target": "https://hooks.example.com"}]
    set_state_value(
        state_key="alert_destinations",
        value=updated_value,
        state_file=state_file,
    )
    persisted = get_state_value(
        state_key="alert_destinations",
        default_value=[],
        state_file=state_file,
    )
    assert persisted == updated_value


def test_local_state_is_workspace_scoped(tmp_path: Path) -> None:
    state_file = tmp_path / "insights_state.json"
    set_state_value(
        state_key="sync_jobs",
        value=[{"name": "Workspace A Job"}],
        state_file=state_file,
        workspace_id="workspace-a",
    )
    set_state_value(
        state_key="sync_jobs",
        value=[{"name": "Workspace B Job"}],
        state_file=state_file,
        workspace_id="workspace-b",
    )

    workspace_a_jobs = get_state_value(
        state_key="sync_jobs",
        default_value=[],
        state_file=state_file,
        workspace_id="workspace-a",
    )
    workspace_b_jobs = get_state_value(
        state_key="sync_jobs",
        default_value=[],
        state_file=state_file,
        workspace_id="workspace-b",
    )
    assert workspace_a_jobs[0]["name"] == "Workspace A Job"
    assert workspace_b_jobs[0]["name"] == "Workspace B Job"


def test_service_mode_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "service_state.json"
    server = create_insights_http_server(host="127.0.0.1", port=0, state_file=state_file)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service_url = f"http://127.0.0.1:{server.server_port}"
    try:
        set_state_value(
            state_key="sync_jobs",
            value=[{"name": "Primary D2C Sync", "frequency": "daily", "hour_utc": "2", "status": "enabled"}],
            state_file=tmp_path / "ignored.json",
            service_url=service_url,
            timeout_seconds=5,
            workspace_id="workspace-service",
        )
        jobs = get_state_value(
            state_key="sync_jobs",
            default_value=[],
            state_file=tmp_path / "ignored.json",
            service_url=service_url,
            timeout_seconds=5,
            workspace_id="workspace-service",
        )
        assert isinstance(jobs, list)
        assert jobs
        assert jobs[0]["name"] == "Primary D2C Sync"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_insights_api_requires_auth_when_token_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SERVICE_API_AUTH_TOKEN", "insights-token")
    server = create_insights_http_server(host="127.0.0.1", port=0, state_file=tmp_path / "state.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized_request = urllib_request.Request(
            url=f"{base_url}/state/sync_jobs",
            method="GET",
        )
        with pytest.raises(urllib_error.HTTPError) as exc_info:
            urllib_request.urlopen(unauthorized_request, timeout=5)
        assert exc_info.value.code == 401

        set_state_value(
            state_key="sync_jobs",
            value=[{"name": "Authed Job"}],
            state_file=tmp_path / "ignored.json",
            service_url=base_url,
            timeout_seconds=5,
            workspace_id="authed-workspace",
            service_token="insights-token",
        )
        jobs = get_state_value(
            state_key="sync_jobs",
            default_value=[],
            state_file=tmp_path / "ignored.json",
            service_url=base_url,
            timeout_seconds=5,
            workspace_id="authed-workspace",
            service_token="insights-token",
        )
        assert jobs[0]["name"] == "Authed Job"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unsupported_state_key_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported insights state key"):
        get_state_value(
            state_key="unknown_key",
            default_value={},
            state_file=tmp_path / "state.json",
        )
    with pytest.raises(ValueError, match="Unsupported insights state key"):
        set_state_value(
            state_key="unknown_key",
            value={},
            state_file=tmp_path / "state.json",
        )


def test_insights_api_health_and_invalid_key_response(tmp_path: Path) -> None:
    server = create_insights_http_server(host="127.0.0.1", port=0, state_file=tmp_path / "state.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib_request.urlopen(f"{base_url}/health", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "ok"

        bad_request = urllib_request.Request(
            url=f"{base_url}/state/not_allowed",
            data=json.dumps({"value": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            urllib_request.urlopen(bad_request, timeout=5)
            assert False, "Expected HTTPError for unsupported key"
        except urllib_error.HTTPError as exc:
            assert exc.code == 400
            body = json.loads(exc.read().decode("utf-8"))
            assert body["status"] == "error"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
