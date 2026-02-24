from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from python.services.insights_state_service import ALLOWED_STATE_KEYS


def _read_state_file(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {}
    try:
        parsed = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _write_state_file(state_file: Path, payload: dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def create_insights_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8092,
    state_file: Path = Path("data/processed/insights_state.json"),
) -> ThreadingHTTPServer:
    class InsightsRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                _write_json(self, 200, {"status": "ok", "service": "insights-automation-service"})
                return
            if path.startswith("/state/"):
                key = path.removeprefix("/state/").strip()
                if key not in ALLOWED_STATE_KEYS:
                    _write_json(self, 400, {"status": "error", "message": f"Unsupported key: {key}"})
                    return
                payload = _read_state_file(state_file)
                _write_json(self, 200, {"status": "ok", "mode": "service", "key": key, "value": payload.get(key)})
                return
            _write_json(self, 404, {"status": "error", "message": "Not found"})

        def do_PUT(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if not path.startswith("/state/"):
                _write_json(self, 404, {"status": "error", "message": "Not found"})
                return
            key = path.removeprefix("/state/").strip()
            if key not in ALLOWED_STATE_KEYS:
                _write_json(self, 400, {"status": "error", "message": f"Unsupported key: {key}"})
                return
            try:
                request_body = _parse_json_body(self)
            except ValueError as exc:
                _write_json(self, 400, {"status": "error", "message": str(exc)})
                return
            value = request_body.get("value")
            state = _read_state_file(state_file)
            state[key] = value
            _write_state_file(state_file, state)
            _write_json(self, 200, {"status": "ok", "mode": "service", "key": key, "value": value})

    return ThreadingHTTPServer((host, int(port)), InsightsRequestHandler)

