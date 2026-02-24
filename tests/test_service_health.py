import socket
import threading
from pathlib import Path

import pandas as pd
import pytest

from python.services.pipeline_api import create_pipeline_http_server
from python.services.service_health import (
    assert_services_healthy,
    check_service_health,
    health_url_for_service,
)


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_health_url_for_service_normalizes_paths() -> None:
    assert health_url_for_service("http://127.0.0.1:8091") == "http://127.0.0.1:8091/health"
    assert health_url_for_service("http://127.0.0.1:8091/") == "http://127.0.0.1:8091/health"
    assert health_url_for_service("http://127.0.0.1:8091/health") == "http://127.0.0.1:8091/health"


def test_check_service_health_reports_ok_for_running_service(tmp_path: Path) -> None:
    def fake_runner(**kwargs):
        return {"kpi_overview": pd.DataFrame([{"metric": "orders", "value": 1}])}

    server = create_pipeline_http_server(host="127.0.0.1", port=0, pipeline_runner=fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        result = check_service_health(base_url, timeout_seconds=5)
        assert result["ok"] is True
        assert int(result["status_code"]) == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_check_service_health_reports_failure_for_http_error(tmp_path: Path) -> None:
    def fake_runner(**kwargs):
        return {"kpi_overview": pd.DataFrame([{"metric": "orders", "value": 1}])}

    server = create_pipeline_http_server(host="127.0.0.1", port=0, pipeline_runner=fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = check_service_health(f"http://127.0.0.1:{server.server_port}/missing", timeout_seconds=5)
        assert result["ok"] is False
        assert int(result["status_code"]) == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_assert_services_healthy_raises_on_unreachable_service() -> None:
    bad_port = _unused_local_port()
    with pytest.raises(RuntimeError, match="pipeline"):
        assert_services_healthy({"pipeline": f"http://127.0.0.1:{bad_port}"}, timeout_seconds=1)

