from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from python.analysis.entitlements import get_plan, has_feature, normalize_plan_slug
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


def _workspace_usage_payload(state: dict[str, Any], workspace_id: str) -> dict[str, Any]:
    workspaces = state.get("workspaces", {})
    if isinstance(workspaces, dict):
        workspace_payload = workspaces.get(workspace_id, {})
        if isinstance(workspace_payload, dict):
            usage = workspace_payload.get("usage_counters", {})
            if isinstance(usage, dict):
                return usage
    if workspace_id == DEFAULT_WORKSPACE_ID:
        usage = state.get("usage_counters", {})
        if isinstance(usage, dict):
            return usage
    return {}


def _set_workspace_usage_payload(state: dict[str, Any], workspace_id: str, usage_payload: dict[str, int]) -> dict[str, Any]:
    next_state = dict(state)
    workspaces = next_state.get("workspaces", {})
    if not isinstance(workspaces, dict):
        workspaces = {}

    legacy_usage = next_state.pop("usage_counters", None)
    if isinstance(legacy_usage, dict):
        default_workspace_payload = workspaces.get(DEFAULT_WORKSPACE_ID, {})
        if not isinstance(default_workspace_payload, dict):
            default_workspace_payload = {}
        default_workspace_payload = dict(default_workspace_payload)
        default_workspace_payload["usage_counters"] = {str(key): int(value) for key, value in legacy_usage.items()}
        workspaces[DEFAULT_WORKSPACE_ID] = default_workspace_payload

    workspace_payload = workspaces.get(workspace_id, {})
    if not isinstance(workspace_payload, dict):
        workspace_payload = {}
    workspace_payload = dict(workspace_payload)
    workspace_payload["usage_counters"] = {str(key): int(value) for key, value in usage_payload.items()}
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


def create_policy_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8093,
    state_file: Path = Path("data/processed/policy_state.json"),
) -> ThreadingHTTPServer:
    class PolicyRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path == "/health":
                if not _authorize_request(self, health_endpoint=True):
                    return
                _write_json(self, 200, {"status": "ok", "service": "entitlements-usage-service"})
                return
            if not _authorize_request(self):
                return
            if path == "/usage":
                workspace_id = _workspace_id_for_request(self, parsed_url)
                state = _read_state_file(state_file)
                usage = _workspace_usage_payload(state, workspace_id)
                _write_json(
                    self,
                    200,
                    {"status": "ok", "mode": "service", "usage_counters": usage, "workspace_id": workspace_id},
                )
                return
            if path.startswith("/plans/"):
                slug = normalize_plan_slug(unquote(path.removeprefix("/plans/")).strip())
                plan = get_plan(slug)
                _write_json(
                    self,
                    200,
                    {
                        "status": "ok",
                        "plan": {
                            "slug": plan.slug,
                            "display_name": plan.display_name,
                            "monthly_price_usd": int(plan.monthly_price_usd),
                            "annual_price_usd": int(plan.annual_price_usd),
                            "limits": {key: int(value) for key, value in plan.limits.items()},
                            "feature_flags": sorted(list(plan.feature_flags)),
                        },
                    },
                )
                return
            if path.startswith("/entitlements/"):
                raw = path.removeprefix("/entitlements/").split("/", maxsplit=1)
                if len(raw) != 2:
                    _write_json(self, 400, {"status": "error", "message": "Expected /entitlements/{plan}/{feature}"})
                    return
                plan_slug = normalize_plan_slug(unquote(raw[0]).strip())
                feature = unquote(raw[1]).strip().lower()
                _write_json(
                    self,
                    200,
                    {"status": "ok", "plan_slug": plan_slug, "feature": feature, "allowed": bool(has_feature(plan_slug, feature))},
                )
                return
            _write_json(self, 404, {"status": "error", "message": "Not found"})

        def do_PUT(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path != "/usage":
                _write_json(self, 404, {"status": "error", "message": "Not found"})
                return
            if not _authorize_request(self):
                return
            try:
                request_body = _parse_json_body(self)
            except ValueError as exc:
                _write_json(self, 400, {"status": "error", "message": str(exc)})
                return
            usage = request_body.get("usage_counters", {})
            if not isinstance(usage, dict):
                _write_json(self, 400, {"status": "error", "message": "`usage_counters` must be an object"})
                return
            normalized = {str(key): int(value) for key, value in usage.items()}
            workspace_id = _workspace_id_for_request(self, parsed_url)
            payload = _read_state_file(state_file)
            next_payload = _set_workspace_usage_payload(payload, workspace_id, normalized)
            _write_state_file(state_file, next_payload)
            _write_json(
                self,
                200,
                {"status": "ok", "mode": "service", "usage_counters": normalized, "workspace_id": workspace_id},
            )

    return ThreadingHTTPServer((host, int(port)), PolicyRequestHandler)

