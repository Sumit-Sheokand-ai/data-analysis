from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Literal


PlanSlug = Literal["starter", "growth", "pro", "enterprise"]


@dataclass(frozen=True)
class Plan:
    slug: PlanSlug
    display_name: str
    monthly_price_usd: int
    annual_price_usd: int
    feature_flags: frozenset[str]
    limits: dict[str, int]


PLAN_CATALOG: Dict[PlanSlug, Plan] = {
    "starter": Plan(
        slug="starter",
        display_name="Starter",
        monthly_price_usd=79,
        annual_price_usd=59,
        feature_flags=frozenset(
            {
                "core_dashboards",
                "manual_uploads",
                "strict_validation",
            }
        ),
        limits={
            "max_workspaces": 1,
            "max_stores": 1,
            "monthly_report_exports": 2,
            "alert_destinations": 0,
        },
    ),
    "growth": Plan(
        slug="growth",
        display_name="Growth",
        monthly_price_usd=199,
        annual_price_usd=149,
        feature_flags=frozenset(
            {
                "core_dashboards",
                "manual_uploads",
                "strict_validation",
                "advanced_analytics",
                "scenario_planner",
                "alert_actions",
                "scheduled_reports",
                "email_alerts",
                "connector_health",
                "connector_sync",
                "what_changed_diagnostics",
                "security_center",
                "growth_experiments",
            }
        ),
        limits={
            "max_workspaces": 3,
            "max_stores": 3,
            "monthly_report_exports": 20,
            "alert_destinations": 3,
            "max_workspace_members": 5,
            "partner_pipeline_opportunities": 0,
            "active_experiments": 10,
            "monthly_ai_insights": 0,
        },
    ),
    "pro": Plan(
        slug="pro",
        display_name="Pro / Agency",
        monthly_price_usd=399,
        annual_price_usd=319,
        feature_flags=frozenset(
            {
                "core_dashboards",
                "manual_uploads",
                "strict_validation",
                "advanced_analytics",
                "scenario_planner",
                "alert_actions",
                "scheduled_reports",
                "email_alerts",
                "connector_health",
                "connector_sync",
                "what_changed_diagnostics",
                "webhook_alerts",
                "attribution_depth",
                "scenario_optimizer",
                "slack_webhooks",
                "api_exports",
                "multi_store",
                "white_label",
                "white_label_controls",
                "security_center",
                "audit_logs",
                "partner_hub",
                "ai_growth_copilot",
                "growth_experiments",
            }
        ),
        limits={
            "max_workspaces": 10,
            "max_stores": 20,
            "monthly_report_exports": 200,
            "alert_destinations": 20,
            "max_workspace_members": 25,
            "partner_pipeline_opportunities": 200,
            "active_experiments": 100,
            "monthly_ai_insights": 300,
        },
    ),
    "enterprise": Plan(
        slug="enterprise",
        display_name="Enterprise",
        monthly_price_usd=0,
        annual_price_usd=0,
        feature_flags=frozenset(
            {
                "core_dashboards",
                "manual_uploads",
                "strict_validation",
                "advanced_analytics",
                "scenario_planner",
                "alert_actions",
                "scheduled_reports",
                "email_alerts",
                "connector_health",
                "connector_sync",
                "what_changed_diagnostics",
                "webhook_alerts",
                "attribution_depth",
                "scenario_optimizer",
                "slack_webhooks",
                "api_exports",
                "multi_store",
                "white_label",
                "white_label_controls",
                "security_center",
                "audit_logs",
                "partner_hub",
                "enterprise_controls",
                "rbac",
                "ip_allowlist",
                "scim_provisioning",
                "ai_growth_copilot",
                "growth_experiments",
                "sso",
                "custom_sla",
            }
        ),
        limits={
            "max_workspaces": 9999,
            "max_stores": 9999,
            "monthly_report_exports": 999999,
            "alert_destinations": 9999,
            "max_workspace_members": 9999,
            "partner_pipeline_opportunities": 999999,
            "active_experiments": 999999,
            "monthly_ai_insights": 999999,
        },
    ),
}

PLAN_ORDER: tuple[PlanSlug, ...] = ("starter", "growth", "pro", "enterprise")


def normalize_plan_slug(value: str | None, default: PlanSlug = "starter") -> PlanSlug:
    if value is None:
        return default
    candidate = str(value).strip().lower()
    if candidate in PLAN_CATALOG:
        return candidate  # type: ignore[return-value]
    return default


def get_plan(slug: str | PlanSlug) -> Plan:
    return PLAN_CATALOG[normalize_plan_slug(str(slug))]


def has_feature(slug: str | PlanSlug, feature: str) -> bool:
    plan = get_plan(slug)
    return feature in plan.feature_flags


def list_plan_slugs() -> Iterable[PlanSlug]:
    return PLAN_ORDER


def next_plan_for_feature(current_slug: str | PlanSlug, feature: str) -> Plan | None:
    current = normalize_plan_slug(str(current_slug))
    try:
        start_idx = PLAN_ORDER.index(current)
    except ValueError:
        start_idx = 0
    for slug in PLAN_ORDER[start_idx + 1 :]:
        plan = PLAN_CATALOG[slug]
        if feature in plan.feature_flags:
            return plan
    return None
