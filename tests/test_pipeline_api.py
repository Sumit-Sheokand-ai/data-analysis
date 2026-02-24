import json
import threading
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import pandas as pd

from python.services.pipeline_api import create_pipeline_http_server, execute_pipeline_request
from python.services.pipeline_service import trigger_pipeline_job


def test_execute_pipeline_request_runs_pipeline_with_expected_contract(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {
            "kpi_overview": pd.DataFrame([{"metric": "orders", "value": 5}]),
            "anomaly_report": pd.DataFrame([]),
        }

    result = execute_pipeline_request(
        {
            "data_source": "csv",
            "raw_data_dir": str(tmp_path / "raw"),
            "processed_data_dir": str(tmp_path / "processed"),
            "validation_mode": "warn",
            "database_url": "",
        },
        pipeline_runner=fake_runner,
    )
    assert result["status"] == "completed"
    assert result["mode"] == "service"
    assert int(result["output_tables"]) == 2
    assert captured["data_source"] == "csv"
    assert captured["validation_mode"] == "warn"


def test_pipeline_http_server_supports_health_and_jobs_run(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {"kpi_overview": pd.DataFrame([{"metric": "orders", "value": 1}])}

    server = create_pipeline_http_server(host="127.0.0.1", port=0, pipeline_runner=fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib_request.urlopen(f"{base_url}/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["status"] == "ok"

        result = trigger_pipeline_job(
            data_source="postgres",
            raw_data_dir=tmp_path / "raw",
            processed_data_dir=tmp_path / "processed",
            validation_mode="strict",
            database_url="postgresql://db",
            service_url=base_url,
            timeout_seconds=5,
        )
        assert result["mode"] == "service"
        assert result["status"] == "completed"
        assert int(result["output_tables"]) == 1
        assert captured["data_source"] == "postgres"
        assert captured["validation_mode"] == "strict"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_pipeline_http_server_returns_validation_errors_for_bad_payload() -> None:
    server = create_pipeline_http_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = urllib_request.Request(
            url=f"{base_url}/jobs/run",
            data=json.dumps({"data_source": "invalid"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib_request.urlopen(request, timeout=5)
            assert False, "Expected HTTPError for invalid payload"
        except urllib_error.HTTPError as exc:
            assert exc.code == 400
            body = json.loads(exc.read().decode("utf-8"))
            assert body["status"] == "error"
            assert "data_source" in body["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
