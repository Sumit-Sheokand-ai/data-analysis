import hashlib
import hmac

from python.analysis.security import (
    build_webhook_signature,
    mask_destination_target,
    parse_webhook_allowed_hosts,
    validate_webhook_target_url,
)


def test_parse_webhook_allowed_hosts_normalizes_values() -> None:
    hosts = parse_webhook_allowed_hosts("hooks.example.com, https://api.partner.io/webhook, localhost:9000")
    assert hosts == {"hooks.example.com", "api.partner.io", "localhost"}


def test_validate_webhook_target_url_rejects_non_https_when_enforced() -> None:
    ok, message = validate_webhook_target_url(
        target="http://hooks.example.com/alerts",
        allowed_hosts={"hooks.example.com"},
        enforce_https=True,
    )
    assert not ok
    assert "HTTPS" in message


def test_validate_webhook_target_url_rejects_hosts_outside_allowlist() -> None:
    ok, message = validate_webhook_target_url(
        target="https://untrusted.example.net/alerts",
        allowed_hosts={"hooks.example.com"},
        enforce_https=True,
    )
    assert not ok
    assert "APP_WEBHOOK_ALLOWED_HOSTS" in message


def test_validate_webhook_target_url_accepts_https_allowlisted_host() -> None:
    ok, message = validate_webhook_target_url(
        target="https://hooks.example.com/alerts",
        allowed_hosts={"hooks.example.com"},
        enforce_https=True,
    )
    assert ok
    assert message == ""


def test_build_webhook_signature_uses_hmac_sha256() -> None:
    payload = b'{"event":"test"}'
    secret = "super-secret"
    signature = build_webhook_signature(payload, secret)
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert signature == f"sha256={expected}"


def test_mask_destination_target_masks_email_and_webhook() -> None:
    assert mask_destination_target("email", "founder@company.com") == "fo***@company.com"
    assert mask_destination_target("webhook", "https://hooks.example.com/path") == "hooks.example.com"
