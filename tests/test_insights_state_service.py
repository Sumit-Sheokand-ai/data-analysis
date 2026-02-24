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
        )
        jobs = get_state_value(
            state_key="sync_jobs",
            default_value=[],
            state_file=tmp_path / "ignored.json",
            service_url=service_url,
            timeout_seconds=5,
        )
        assert isinstance(jobs, list)
        assert jobs
        assert jobs[0]["name"] == "Primary D2C Sync"
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
