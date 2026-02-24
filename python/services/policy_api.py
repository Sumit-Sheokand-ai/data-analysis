from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from python.analysis.entitlements import get_plan, has_feature, normalize_plan_slug


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
            path = urlparse(self.path).path
            if path == "/health":
                _write_json(self, 200, {"status": "ok", "service": "entitlements-usage-service"})
                return
            if path == "/usage":
                state = _read_state_file(state_file)
                usage = state.get("usage_counters", {})
                if not isinstance(usage, dict):
                    usage = {}
                _write_json(self, 200, {"status": "ok", "mode": "service", "usage_counters": usage})
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
            path = urlparse(self.path).path
            if path != "/usage":
                _write_json(self, 404, {"status": "error", "message": "Not found"})
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
            payload = _read_state_file(state_file)
            payload["usage_counters"] = normalized
            _write_state_file(state_file, payload)
            _write_json(self, 200, {"status": "ok", "mode": "service", "usage_counters": normalized})

    return ThreadingHTTPServer((host, int(port)), PolicyRequestHandler)

