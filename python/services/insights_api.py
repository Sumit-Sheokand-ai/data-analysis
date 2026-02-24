from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from python.services.insights_state_service import ALLOWED_STATE_KEYS
from python.services.service_auth import (
    DEFAULT_WORKSPACE_ID,
    is_request_authorized,
    should_require_health_auth,
    workspace_id_from_headers,
)


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


def _normalize_workspace_id(workspace_id: str) -> str:
    cleaned = str(workspace_id).strip().lower()
    return cleaned or DEFAULT_WORKSPACE_ID


def _workspace_payload(state: dict[str, Any], workspace_id: str) -> dict[str, Any]:
    workspaces = state.get("workspaces", {})
    if isinstance(workspaces, dict):
        workspace_payload = workspaces.get(workspace_id, {})
        if isinstance(workspace_payload, dict):
            return workspace_payload
    if workspace_id == DEFAULT_WORKSPACE_ID:
        return {key: value for key, value in state.items() if key in ALLOWED_STATE_KEYS}
    return {}


def _set_workspace_payload(state: dict[str, Any], workspace_id: str, workspace_payload: dict[str, Any]) -> dict[str, Any]:
    next_state = dict(state)
    workspaces = next_state.get("workspaces", {})
    if not isinstance(workspaces, dict):
        workspaces = {}

    legacy_payload = {key: next_state.pop(key) for key in list(next_state.keys()) if key in ALLOWED_STATE_KEYS}
    if legacy_payload:
        default_workspace_payload = workspaces.get(DEFAULT_WORKSPACE_ID, {})
        if not isinstance(default_workspace_payload, dict):
            default_workspace_payload = {}
        default_workspace_payload = {**legacy_payload, **default_workspace_payload}
        workspaces[DEFAULT_WORKSPACE_ID] = default_workspace_payload

    workspaces[workspace_id] = workspace_payload
    next_state["workspaces"] = workspaces
    return next_state


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


def _workspace_id_for_request(handler: BaseHTTPRequestHandler, parsed_url) -> str:
    query = parse_qs(parsed_url.query)
    query_workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
    if query_workspace_id:
        return _normalize_workspace_id(query_workspace_id)
    return _normalize_workspace_id(workspace_id_from_headers(handler.headers))


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
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path == "/health":
                if not _authorize_request(self, health_endpoint=True):
                    return
                _write_json(self, 200, {"status": "ok", "service": "insights-automation-service"})
                return
            if path.startswith("/state/"):
                if not _authorize_request(self):
                    return
                key = path.removeprefix("/state/").strip()
                if key not in ALLOWED_STATE_KEYS:
                    _write_json(self, 400, {"status": "error", "message": f"Unsupported key: {key}"})
                    return
                workspace_id = _workspace_id_for_request(self, parsed_url)
                payload = _read_state_file(state_file)
                workspace_payload = _workspace_payload(payload, workspace_id)
                _write_json(
                    self,
                    200,
                    {
                        "status": "ok",
                        "mode": "service",
                        "key": key,
                        "value": workspace_payload.get(key),
                        "workspace_id": workspace_id,
                    },
                )
                return
            _write_json(self, 404, {"status": "error", "message": "Not found"})

        def do_PUT(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if not path.startswith("/state/"):
                _write_json(self, 404, {"status": "error", "message": "Not found"})
                return
            if not _authorize_request(self):
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
            workspace_id = _workspace_id_for_request(self, parsed_url)
            state = _read_state_file(state_file)
            workspace_payload = _workspace_payload(state, workspace_id)
            workspace_payload[key] = value
            next_state = _set_workspace_payload(state, workspace_id, workspace_payload)
            _write_state_file(state_file, next_state)
            _write_json(
                self,
                200,
                {"status": "ok", "mode": "service", "key": key, "value": value, "workspace_id": workspace_id},
            )

    return ThreadingHTTPServer((host, int(port)), InsightsRequestHandler)

