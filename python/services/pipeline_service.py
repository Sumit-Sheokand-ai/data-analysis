from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from python.analysis.pipeline import run_pipeline


def _service_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/jobs/run"


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=max(int(timeout_seconds), 1)) as response:
            body = response.read().decode("utf-8").strip()
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore").strip() if hasattr(exc, "read") else ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Pipeline service returned HTTP {exc.code}{suffix}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Could not reach pipeline service: {exc}") from exc

    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Pipeline service response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Pipeline service response must be a JSON object")
    return parsed


def trigger_pipeline_job(
    data_source: str,
    raw_data_dir: Path,
    processed_data_dir: Path,
    validation_mode: str,
    database_url: str | None = None,
    service_url: str = "",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    cleaned_service_url = str(service_url).strip()
    if not cleaned_service_url:
        outputs = run_pipeline(
            data_source=data_source,
            raw_data_dir=raw_data_dir,
            processed_data_dir=processed_data_dir,
            database_url=database_url,
            validation_mode=validation_mode,
        )
        return {
            "mode": "local",
            "status": "completed",
            "output_tables": len(outputs),
        }

    payload = {
        "data_source": str(data_source).strip().lower(),
        "raw_data_dir": str(raw_data_dir),
        "processed_data_dir": str(processed_data_dir),
        "validation_mode": str(validation_mode).strip().lower(),
        "database_url": database_url or "",
    }
    response = _post_json(_service_endpoint(cleaned_service_url), payload, timeout_seconds=timeout_seconds)
    status = str(response.get("status", "accepted")).strip().lower()
    if status in {"failed", "error"}:
        detail = str(response.get("message", "pipeline service reported failure")).strip()
        raise RuntimeError(detail)
    response.setdefault("mode", "service")
    return response
