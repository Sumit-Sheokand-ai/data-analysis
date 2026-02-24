from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import uuid4

from python.analysis.pipeline import run_pipeline
from python.services.service_auth import actor_from_headers, is_request_authorized, should_require_health_auth


PipelineRunner = Callable[..., dict[str, Any]]


def execute_pipeline_request(
    payload: dict[str, Any],
    pipeline_runner: PipelineRunner = run_pipeline,
) -> dict[str, Any]:
    data_source = str(payload.get("data_source", "csv")).strip().lower()
    if data_source not in {"csv", "postgres"}:
        raise ValueError("`data_source` must be one of: csv, postgres")
    validation_mode = str(payload.get("validation_mode", "strict")).strip().lower()
    if validation_mode not in {"strict", "warn"}:
        raise ValueError("`validation_mode` must be one of: strict, warn")

    raw_data_dir = Path(str(payload.get("raw_data_dir", "data/raw")).strip() or "data/raw")
    processed_data_dir = Path(str(payload.get("processed_data_dir", "data/processed")).strip() or "data/processed")
    database_url_raw = str(payload.get("database_url", "")).strip()
    database_url = database_url_raw or None

    outputs = pipeline_runner(
        data_source=data_source,
        raw_data_dir=raw_data_dir,
        processed_data_dir=processed_data_dir,
        database_url=database_url,
        validation_mode=validation_mode,
    )

    return {
        "status": "completed",
        "job_id": f"job-{uuid4().hex[:12]}",
        "mode": "service",
        "data_source": data_source,
        "validation_mode": validation_mode,
        "output_tables": len(outputs),
    }


def _parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or 0)
    if content_length <= 0:
        return {}
    raw = handler.rfile.read(content_length)
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _write_json(handler: BaseHTTPRequestHandler, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _authorize_request(
    handler: BaseHTTPRequestHandler,
    *,
    health_endpoint: bool = False,
) -> bool:
    if health_endpoint and not should_require_health_auth():
        return True
    if is_request_authorized(handler.headers):
        return True
    _write_json(handler, 401, {"status": "error", "message": "Unauthorized"})
    return False


def create_pipeline_http_server(
    host: str = "127.0.0.1",
    port: int = 8091,
    pipeline_runner: PipelineRunner = run_pipeline,
) -> ThreadingHTTPServer:
    class PipelineRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                if not _authorize_request(self, health_endpoint=True):
                    return
                _write_json(self, 200, {"status": "ok", "service": "analytics-pipeline-service"})
                return
            _write_json(self, 404, {"status": "error", "message": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/jobs/run":
                _write_json(self, 404, {"status": "error", "message": "Not found"})
                return
            if not _authorize_request(self):
                return
            try:
                payload = _parse_json_body(self)
                result = execute_pipeline_request(payload=payload, pipeline_runner=pipeline_runner)
            except ValueError as exc:
                _write_json(self, 400, {"status": "error", "message": str(exc)})
                return
            except Exception as exc:
                _write_json(self, 500, {"status": "error", "message": f"Pipeline execution failed: {exc}"})
                return
            actor = actor_from_headers(self.headers)
            result["workspace_id"] = actor["workspace_id"]
            result["requested_by"] = actor["user_id"]
            _write_json(self, 200, result)

    return ThreadingHTTPServer((host, int(port)), PipelineRequestHandler)

