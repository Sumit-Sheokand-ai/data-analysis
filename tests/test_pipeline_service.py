import json
from pathlib import Path
from urllib import error as urllib_error

import pandas as pd
import pytest

from python.services.pipeline_service import trigger_pipeline_job


def test_trigger_pipeline_job_runs_local_pipeline_when_service_url_missing(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def fake_run_pipeline(**kwargs):
        calls.update(kwargs)
        return {"kpi_overview": pd.DataFrame([{"metric": "orders", "value": 1}])}

    monkeypatch.setattr("python.services.pipeline_service.run_pipeline", fake_run_pipeline)
    result = trigger_pipeline_job(
        data_source="csv",
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
        validation_mode="warn",
    )
    assert result["mode"] == "local"
    assert result["status"] == "completed"
    assert int(result["output_tables"]) == 1
    assert calls["data_source"] == "csv"
    assert calls["validation_mode"] == "warn"


def test_trigger_pipeline_job_calls_service_when_url_provided(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        headers = {str(key).strip().lower(): str(value).strip() for key, value in request.header_items()}
        captured["authorization"] = headers.get("authorization")
        captured["workspace"] = headers.get("x-workspace-id")
        captured["user_id"] = headers.get("x-user-id")
        captured["user_role"] = headers.get("x-user-role")
        return FakeResponse({"status": "accepted", "job_id": "job-123"})

    monkeypatch.setattr("python.services.pipeline_service.urllib_request.urlopen", fake_urlopen)
    result = trigger_pipeline_job(
        data_source="postgres",
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
        validation_mode="strict",
        database_url="postgresql://db",
        service_url="https://pipeline.internal",
        timeout_seconds=45,
        workspace_id="acme",
        user_id="analyst@acme",
        user_role="analyst",
        service_token="svc-token",
    )
    assert result["mode"] == "service"
    assert result["status"] == "accepted"
    assert result["job_id"] == "job-123"
    assert captured["url"] == "https://pipeline.internal/jobs/run"
    assert captured["timeout"] == 45
    assert captured["payload"]["data_source"] == "postgres"
    assert captured["payload"]["validation_mode"] == "strict"
    assert captured["authorization"] == "Bearer svc-token"
    assert captured["workspace"] == "acme"
    assert captured["user_id"] == "analyst@acme"
    assert captured["user_role"] == "analyst"


def test_trigger_pipeline_job_raises_on_service_failure_status(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"status": "failed", "message": "worker unavailable"}).encode("utf-8")

    def fake_urlopen(request, timeout: int):
        return FakeResponse()

    monkeypatch.setattr("python.services.pipeline_service.urllib_request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="worker unavailable"):
        trigger_pipeline_job(
            data_source="csv",
            raw_data_dir=tmp_path / "raw",
            processed_data_dir=tmp_path / "processed",
            validation_mode="warn",
            service_url="https://pipeline.internal",
        )


def test_trigger_pipeline_job_raises_on_http_error(monkeypatch, tmp_path: Path) -> None:
    def fake_urlopen(request, timeout: int):
        raise urllib_error.HTTPError(
            url=request.full_url,
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("python.services.pipeline_service.urllib_request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="HTTP 502"):
        trigger_pipeline_job(
            data_source="csv",
            raw_data_dir=tmp_path / "raw",
            processed_data_dir=tmp_path / "processed",
            validation_mode="warn",
            service_url="https://pipeline.internal",
        )
