from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

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


def _http_get_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib_request.Request(url=url, method="GET")
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


def _http_put_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
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
) -> dict[str, Any]:
    normalized_slug = normalize_plan_slug(plan_slug)
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_get_json(_plan_endpoint(cleaned_service_url, normalized_slug), timeout_seconds=timeout_seconds)
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
) -> bool:
    normalized_slug = normalize_plan_slug(plan_slug)
    normalized_feature = str(feature).strip().lower()
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_get_json(
                _entitlement_endpoint(cleaned_service_url, normalized_slug, normalized_feature),
                timeout_seconds=timeout_seconds,
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
) -> dict[str, int]:
    normalized_defaults = {key: int(value) for key, value in default_counters.items()}
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_get_json(_usage_endpoint(cleaned_service_url), timeout_seconds=timeout_seconds)
            usage = response.get("usage_counters", {})
            if isinstance(usage, dict):
                return {key: int(usage.get(key, default_value)) for key, default_value in normalized_defaults.items()}
        except Exception:
            pass
    payload = _read_state_file(state_file)
    usage_local = payload.get("usage_counters", {})
    if not isinstance(usage_local, dict):
        usage_local = {}
    return {key: int(usage_local.get(key, default_value)) for key, default_value in normalized_defaults.items()}


def set_usage_counters(
    *,
    counters: dict[str, int],
    state_file: Path,
    service_url: str = "",
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    normalized = {key: int(value) for key, value in counters.items()}
    cleaned_service_url = str(service_url).strip()
    if cleaned_service_url:
        try:
            response = _http_put_json(
                _usage_endpoint(cleaned_service_url),
                {"usage_counters": normalized},
                timeout_seconds=timeout_seconds,
            )
            return response
        except Exception:
            pass
    payload = _read_state_file(state_file)
    payload["usage_counters"] = normalized
    _write_state_file(state_file, payload)
    return {"status": "ok", "mode": "local", "usage_counters": normalized}

