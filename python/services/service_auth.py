from __future__ import annotations

import os
from secrets import compare_digest
from typing import Mapping


DEFAULT_WORKSPACE_ID = "default"
DEFAULT_USER_ID = "service-client"
DEFAULT_USER_ROLE = "system"


def parse_env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def configured_service_auth_token() -> str:
    return os.getenv("SERVICE_API_AUTH_TOKEN", "").strip()


def should_require_health_auth() -> bool:
    return parse_env_flag("SERVICE_HEALTH_REQUIRE_AUTH", default=False)


def _normalize_workspace_id(value: str) -> str:
    cleaned = str(value).strip().lower()
    return cleaned or DEFAULT_WORKSPACE_ID


def _normalize_user_id(value: str) -> str:
    cleaned = str(value).strip().lower()
    return cleaned or DEFAULT_USER_ID


def _normalize_user_role(value: str) -> str:
    cleaned = str(value).strip().lower()
    return cleaned or DEFAULT_USER_ROLE


def build_service_headers(
    *,
    service_token: str = "",
    workspace_id: str = "",
    user_id: str = "",
    user_role: str = "",
) -> dict[str, str]:
    headers = {
        "X-Workspace-Id": _normalize_workspace_id(workspace_id),
        "X-User-Id": _normalize_user_id(user_id),
        "X-User-Role": _normalize_user_role(user_role),
    }
    token = str(service_token).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _header_value(headers: Mapping[str, str], key: str) -> str:
    value = headers.get(key)
    if value is None:
        value = headers.get(key.lower())
    return str(value or "").strip()


def extract_presented_service_token(headers: Mapping[str, str]) -> str:
    authorization = _header_value(headers, "Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", maxsplit=1)[1].strip()
    return _header_value(headers, "X-Service-Token")


def is_request_authorized(headers: Mapping[str, str]) -> bool:
    required_token = configured_service_auth_token()
    if not required_token:
        return True
    presented_token = extract_presented_service_token(headers)
    if not presented_token:
        return False
    return compare_digest(required_token, presented_token)


def workspace_id_from_headers(headers: Mapping[str, str], default: str = DEFAULT_WORKSPACE_ID) -> str:
    return _normalize_workspace_id(_header_value(headers, "X-Workspace-Id") or default)


def user_id_from_headers(headers: Mapping[str, str], default: str = DEFAULT_USER_ID) -> str:
    return _normalize_user_id(_header_value(headers, "X-User-Id") or default)


def user_role_from_headers(headers: Mapping[str, str], default: str = DEFAULT_USER_ROLE) -> str:
    return _normalize_user_role(_header_value(headers, "X-User-Role") or default)


def actor_from_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        "workspace_id": workspace_id_from_headers(headers),
        "user_id": user_id_from_headers(headers),
        "user_role": user_role_from_headers(headers),
    }
