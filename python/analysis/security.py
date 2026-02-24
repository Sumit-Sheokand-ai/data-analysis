from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlparse


_LOCAL_WEBHOOK_HOSTS = {"localhost", "127.0.0.1"}


def _normalize_host(value: str) -> str:
    candidate = str(value).strip().lower()
    if not candidate:
        return ""
    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.hostname or ""
    candidate = candidate.split("/", 1)[0].split(":", 1)[0].strip().lower()
    return candidate


def parse_webhook_allowed_hosts(value: str | None) -> set[str]:
    if value is None:
        return set()
    allowed_hosts: set[str] = set()
    for raw in str(value).split(","):
        host = _normalize_host(raw)
        if host:
            allowed_hosts.add(host)
    return allowed_hosts


def validate_webhook_target_url(
    target: str,
    allowed_hosts: set[str] | None = None,
    enforce_https: bool = True,
) -> tuple[bool, str]:
    candidate = str(target).strip()
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").strip().lower()
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        return False, "Webhook target must start with http:// or https://"
    if not host:
        return False, "Webhook target host is missing."
    if enforce_https and scheme != "https" and host not in _LOCAL_WEBHOOK_HOSTS:
        return False, "Webhook target must use HTTPS in secure mode."
    if allowed_hosts:
        normalized_allowlist = {_normalize_host(item) for item in allowed_hosts if _normalize_host(item)}
        if host not in normalized_allowlist and host not in _LOCAL_WEBHOOK_HOSTS:
            return False, f"Webhook host `{host}` is not in APP_WEBHOOK_ALLOWED_HOSTS."
    return True, ""


def build_webhook_signature(payload: bytes, secret: str) -> str:
    secret_value = str(secret)
    digest = hmac.new(secret_value.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def mask_destination_target(destination_type: str, target: str) -> str:
    d_type = str(destination_type).strip().lower()
    raw_target = str(target).strip()
    if not raw_target:
        return ""
    if d_type == "email" and "@" in raw_target:
        local_part, domain = raw_target.split("@", 1)
        if len(local_part) <= 2:
            local_masked = "***"
        else:
            local_masked = f"{local_part[:2]}***"
        return f"{local_masked}@{domain}"
    parsed = urlparse(raw_target)
    host = (parsed.hostname or "").strip()
    if host:
        return host
    return "***"
