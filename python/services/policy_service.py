from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from python.analysis.entitlements import get_plan, has_feature, normalize_plan_slug
from python.services.service_auth import DEFAULT_WORKSPACE_ID, build_service_headers


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

def _workspace_usage_payload(state: dict[str, Any], workspace_id: str) -> dict[str, int]:
    workspaces = state.get("workspaces", {})
    if isinstance(workspaces, dict):
        workspace_payload = workspaces.get(workspace_id, {})
        if isinstance(workspace_payload, dict):
            usage_counters = workspace_payload.get("usage_counters", {})
            if isinstance(usage_counters, dict):
                return {str(key): int(value) for key, value in usage_counters.items()}
    if workspace_id == DEFAULT_WORKSPACE_ID:
        usage_counters = state.get("usage_counters", {})
        if isinstance(usage_counters, dict):
            return {str(key): int(value) for key, value in usage_counters.items()}
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
        raise RuntimeError(f"Policy service returned HTTP {exc.code}{suffix}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Could not reach policy service: {exc}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Policy service response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Policy service response must be a JSON object")
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
        raise RuntimeError(f"Policy service returned HTTP {exc.code}{suffix}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Could not reach policy service: {exc}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Policy service response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Policy service response must be a JSON object")
    return parsed


def _usage_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/usage"


def _plan_endpoint(base_url: str, plan_slug: str) -> str:
    return f"{base_url.rstrip('/')}/plans/{urllib_parse.quote(plan_slug.strip().lower())}"


def _entitlement_endpoint(base_url: str, plan_slug: str, feature: str) -> str:
    return (
        f"{base_url.rstrip('/')}/entitlements/"
        f"{urllib_parse.quote(plan_slug.strip().lower())}/{urllib_parse.quote(feature.strip().lower())}"
    )


def get_plan_metadata(
    *,
    plan_slug: str,
    service_url: str = "",
    timeout_seconds: int = 10,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    user_id: str = "",
    user_role: str = "",
    service_token: str = "",
) -> dict[str, Any]:
    normalized_slug = normalize_plan_slug(plan_slug)
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_get_json(
                _plan_endpoint(cleaned_service_url, normalized_slug),
                timeout_seconds=timeout_seconds,
                headers=build_service_headers(
                    service_token=service_token,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    user_role=user_role,
                ),
            )
            if isinstance(response.get("plan"), dict):
                return response["plan"]
        except Exception:
            pass
    plan = get_plan(normalized_slug)
    return {
        "slug": plan.slug,
        "display_name": plan.display_name,
        "monthly_price_usd": int(plan.monthly_price_usd),
        "annual_price_usd": int(plan.annual_price_usd),
        "limits": {key: int(value) for key, value in plan.limits.items()},
        "feature_flags": sorted(list(plan.feature_flags)),
    }


def has_feature_for_plan(
    *,
    plan_slug: str,
    feature: str,
    service_url: str = "",
    timeout_seconds: int = 10,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    user_id: str = "",
    user_role: str = "",
    service_token: str = "",
) -> bool:
    normalized_slug = normalize_plan_slug(plan_slug)
    normalized_feature = str(feature).strip().lower()
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_get_json(
                _entitlement_endpoint(cleaned_service_url, normalized_slug, normalized_feature),
                timeout_seconds=timeout_seconds,
                headers=build_service_headers(
                    service_token=service_token,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    user_role=user_role,
                ),
            )
            return bool(response.get("allowed", False))
        except Exception:
            pass
    return has_feature(normalized_slug, normalized_feature)


def get_usage_counters(
    *,
    default_counters: dict[str, int],
    state_file: Path,
    service_url: str = "",
    timeout_seconds: int = 10,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    user_id: str = "",
    user_role: str = "",
    service_token: str = "",
) -> dict[str, int]:
    normalized_defaults = {key: int(value) for key, value in default_counters.items()}
    normalized_workspace = _normalize_workspace_id(workspace_id)
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_get_json(
                _usage_endpoint(cleaned_service_url),
                timeout_seconds=timeout_seconds,
                headers=build_service_headers(
                    service_token=service_token,
                    workspace_id=normalized_workspace,
                    user_id=user_id,
                    user_role=user_role,
                ),
            )
            usage = response.get("usage_counters", {})
            if isinstance(usage, dict):
                return {key: int(usage.get(key, default_value)) for key, default_value in normalized_defaults.items()}
        except Exception:
            pass
    payload = _read_state_file(state_file)
    usage_local = _workspace_usage_payload(payload, normalized_workspace)
    return {key: int(usage_local.get(key, default_value)) for key, default_value in normalized_defaults.items()}


def set_usage_counters(
    *,
    counters: dict[str, int],
    state_file: Path,
    service_url: str = "",
    timeout_seconds: int = 10,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    user_id: str = "",
    user_role: str = "",
    service_token: str = "",
) -> dict[str, Any]:
    normalized = {key: int(value) for key, value in counters.items()}
    normalized_workspace = _normalize_workspace_id(workspace_id)
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_put_json(
                _usage_endpoint(cleaned_service_url),
                {"usage_counters": normalized},
                timeout_seconds=timeout_seconds,
                headers=build_service_headers(
                    service_token=service_token,
                    workspace_id=normalized_workspace,
                    user_id=user_id,
                    user_role=user_role,
                ),
            )
            return response
        except Exception:
            pass
    payload = _read_state_file(state_file)
    next_payload = _set_workspace_usage_payload(payload, normalized_workspace, normalized)
    _write_state_file(state_file, next_payload)
    return {"status": "ok", "mode": "local", "usage_counters": normalized, "workspace_id": normalized_workspace}

