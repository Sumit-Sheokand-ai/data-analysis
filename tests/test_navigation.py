from app.ui.navigation import (
    PAGE_GROUP_ADMIN,
    PAGE_GROUP_CORE,
    PAGE_GROUP_OPERATIONS,
    build_available_pages,
    build_grouped_pages,
    required_feature_for_page,
)


def test_grouped_pages_hide_advanced_when_toggle_off() -> None:
    grouped = build_grouped_pages(show_advanced_pages=False, has_entitlement=lambda _: True)
    assert set(grouped.keys()) == {PAGE_GROUP_CORE}
    assert "No-Code Upload Center" in grouped[PAGE_GROUP_CORE]
    assert "Connectors & Sync" not in grouped[PAGE_GROUP_CORE]


def test_grouped_pages_filter_advanced_by_entitlement_when_enabled() -> None:
    enabled_features = {"connector_health", "security_center", "alert_actions"}
    grouped = build_grouped_pages(
        show_advanced_pages=True,
        has_entitlement=lambda feature: feature in enabled_features,
    )
    assert "Connectors & Sync" in grouped[PAGE_GROUP_OPERATIONS]
    assert "Security Center" in grouped[PAGE_GROUP_ADMIN]
    assert "What Changed" not in grouped[PAGE_GROUP_OPERATIONS]


def test_build_available_pages_flattens_in_group_order() -> None:
    pages = build_available_pages(show_advanced_pages=False, has_entitlement=lambda _: True)
    assert pages[0] == "No-Code Upload Center"
    assert "Anomaly Alerts" in pages
    assert "Security Center" not in pages


def test_required_feature_lookup_returns_expected_values() -> None:
    assert required_feature_for_page("Scheduled Reports") == "scheduled_reports"
    assert required_feature_for_page("Executive Overview") is None
    assert required_feature_for_page("Unknown Page") is None
