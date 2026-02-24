from __future__ import annotations

import json
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from python.services.service_auth import build_service_headers


def health_url_for_service(base_url: str) -> str:
    cleaned = str(base_url).strip().rstrip("/")
    if not cleaned:
        raise ValueError("Service URL is required for healthcheck.")
    if cleaned.endswith("/health"):
        return cleaned
    return f"{cleaned}/health"


def check_service_health(
    base_url: str,
    timeout_seconds: int = 5,
    service_token: str = "",
) -> dict[str, Any]:
    url = health_url_for_service(base_url)
    request = urllib_request.Request(
        url=url,
        headers=build_service_headers(service_token=service_token),
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=max(int(timeout_seconds), 1)) as response:
            status_code = int(getattr(response, "status", 200))
            body = response.read().decode("utf-8", errors="ignore").strip()
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore").strip() if hasattr(exc, "read") else ""
        message = f"HTTP {exc.code}" + (f": {detail}" if detail else "")
        return {"ok": False, "url": url, "status_code": int(exc.code), "message": message, "payload": {}}
    except urllib_error.URLError as exc:
        return {"ok": False, "url": url, "status_code": 0, "message": f"Connection error: {exc}", "payload": {}}
    except Exception as exc:
        return {"ok": False, "url": url, "status_code": 0, "message": f"Unexpected error: {exc}", "payload": {}}

    payload: dict[str, Any] = {}
    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    ok = 200 <= status_code < 300
    if payload:
        declared_status = str(payload.get("status", "")).strip().lower()
        if declared_status in {"error", "failed", "unhealthy"}:
            ok = False
    return {
        "ok": ok,
        "url": url,
        "status_code": status_code,
        "message": "ok" if ok else "health endpoint reported failure",
        "payload": payload,
    }


def assert_services_healthy(
    service_urls: dict[str, str],
    timeout_seconds: int = 5,
    service_token: str = "",
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for name, url in service_urls.items():
        cleaned = str(url).strip()
        if not cleaned:
            continue
        result = check_service_health(
            cleaned,
            timeout_seconds=timeout_seconds,
            service_token=service_token,
        )
        results[name] = result
        if not bool(result.get("ok", False)):
            failures.append(f"{name}: {result.get('message', 'unhealthy')}")
    if failures:
        raise RuntimeError("Service healthcheck failed: " + "; ".join(failures))
    return results

