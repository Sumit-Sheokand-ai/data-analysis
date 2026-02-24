from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from python.services.service_auth import DEFAULT_WORKSPACE_ID, build_service_headers


ALLOWED_STATE_KEYS = frozenset(
    {
        "alert_destinations",
        "sync_jobs",
        "growth_experiments",
        "activation_playbooks",
        "goal_targets",
        "autopilot_queue",
    }
)


def _service_state_endpoint(base_url: str, state_key: str) -> str:
    return f"{base_url.rstrip('/')}/state/{state_key}"

def _normalize_workspace_id(workspace_id: str) -> str:
    cleaned = str(workspace_id).strip().lower()
    return cleaned or DEFAULT_WORKSPACE_ID


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


def _http_get_json(
    url: str,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib_request.Request(url=url, headers=headers or {}, method="GET")
    try:
        with urllib_request.urlopen(request, timeout=max(int(timeout_seconds), 1)) as response:
            body = response.read().decode("utf-8").strip()
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore").strip() if hasattr(exc, "read") else ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Insights service returned HTTP {exc.code}{suffix}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Could not reach insights service: {exc}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Insights service response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Insights service response must be a JSON object")
    return parsed


def _http_put_json(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="PUT",
    )
    try:
        with urllib_request.urlopen(request, timeout=max(int(timeout_seconds), 1)) as response:
            body = response.read().decode("utf-8").strip()
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore").strip() if hasattr(exc, "read") else ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Insights service returned HTTP {exc.code}{suffix}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Could not reach insights service: {exc}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Insights service response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Insights service response must be a JSON object")
    return parsed


def get_state_value(
    *,
    state_key: str,
    default_value: Any,
    state_file: Path,
    service_url: str = "",
    timeout_seconds: int = 10,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    user_id: str = "",
    user_role: str = "",
    service_token: str = "",
) -> Any:
    if state_key not in ALLOWED_STATE_KEYS:
        raise ValueError(f"Unsupported insights state key: {state_key}")
    normalized_workspace = _normalize_workspace_id(workspace_id)
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        response = _http_get_json(
            _service_state_endpoint(cleaned_service_url, state_key),
            timeout_seconds=timeout_seconds,
            headers=build_service_headers(
                service_token=service_token,
                workspace_id=normalized_workspace,
                user_id=user_id,
                user_role=user_role,
            ),
        )
        return response.get("value", default_value)
    state = _read_state_file(state_file)
    workspace_payload = _workspace_payload(state, normalized_workspace)
    return workspace_payload.get(state_key, default_value)


def set_state_value(
    *,
    state_key: str,
    value: Any,
    state_file: Path,
    service_url: str = "",
    timeout_seconds: int = 10,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    user_id: str = "",
    user_role: str = "",
    service_token: str = "",
) -> dict[str, Any]:
    if state_key not in ALLOWED_STATE_KEYS:
        raise ValueError(f"Unsupported insights state key: {state_key}")
    normalized_workspace = _normalize_workspace_id(workspace_id)
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        response = _http_put_json(
            _service_state_endpoint(cleaned_service_url, state_key),
            {"value": value},
            timeout_seconds=timeout_seconds,
            headers=build_service_headers(
                service_token=service_token,
                workspace_id=normalized_workspace,
                user_id=user_id,
                user_role=user_role,
            ),
        )
        return response
    state = _read_state_file(state_file)
    workspace_payload = _workspace_payload(state, normalized_workspace)
    workspace_payload[state_key] = value
    next_state = _set_workspace_payload(state, normalized_workspace, workspace_payload)
    _write_state_file(state_file, next_state)
    return {"status": "ok", "mode": "local", "key": state_key, "workspace_id": normalized_workspace}

