from python.analysis.entitlements import (
    PLAN_CATALOG,
    PLAN_ORDER,
    get_plan,
    has_feature,
    next_plan_for_feature,
    normalize_plan_slug,
)


def test_plan_catalog_contains_expected_tiers() -> None:
    assert tuple(PLAN_CATALOG.keys()) == PLAN_ORDER
    assert get_plan("starter").display_name == "Starter"
    assert get_plan("enterprise").display_name == "Enterprise"


def test_normalize_plan_slug_defaults_for_unknown_values() -> None:
    assert normalize_plan_slug("growth") == "growth"
    assert normalize_plan_slug("GROWTH") == "growth"
    assert normalize_plan_slug("unknown-tier") == "starter"


def test_feature_flag_coverage_by_plan() -> None:
    assert has_feature("starter", "core_dashboards")
    assert not has_feature("starter", "scheduled_reports")
    assert has_feature("growth", "scheduled_reports")
    assert has_feature("pro", "slack_webhooks")


def test_next_plan_for_feature_returns_upgrade_target() -> None:
    upgrade_for_starter = next_plan_for_feature("starter", "scheduled_reports")
    assert upgrade_for_starter is not None
    assert upgrade_for_starter.slug == "growth"

    upgrade_for_pro = next_plan_for_feature("pro", "sso")
    assert upgrade_for_pro is not None
    assert upgrade_for_pro.slug == "enterprise"
