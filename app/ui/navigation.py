from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


PAGE_GROUP_CORE = "Core"
PAGE_GROUP_OPERATIONS = "Operations"
PAGE_GROUP_ADMIN = "Admin"
PAGE_GROUP_ORDER: tuple[str, ...] = (
    PAGE_GROUP_CORE,
    PAGE_GROUP_OPERATIONS,
    PAGE_GROUP_ADMIN,
)


@dataclass(frozen=True)
class PageDefinition:
    name: str
    group: str
    advanced: bool = False
    required_feature: str | None = None


PAGE_REGISTRY: tuple[PageDefinition, ...] = (
    PageDefinition("No-Code Upload Center", PAGE_GROUP_CORE, advanced=False),
    PageDefinition("Executive Overview", PAGE_GROUP_CORE, advanced=False),
    PageDefinition("Channel Performance", PAGE_GROUP_CORE, advanced=False),
    PageDefinition("Anomaly Alerts", PAGE_GROUP_CORE, advanced=False, required_feature="alert_actions"),
    PageDefinition("Data Quality", PAGE_GROUP_CORE, advanced=False),
    PageDefinition("Billing & Plan", PAGE_GROUP_CORE, advanced=False),
    PageDefinition("Connectors & Sync", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="connector_health"),
    PageDefinition("What Changed", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="what_changed_diagnostics"),
    PageDefinition("Growth Copilot", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="ai_growth_copilot"),
    PageDefinition("Experiment Studio", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="growth_experiments"),
    PageDefinition("Playbook Automation", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="playbook_automation"),
    PageDefinition("ROI Forecast", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="roi_forecasting"),
    PageDefinition("Goal Tracker", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="goal_tracker"),
    PageDefinition("Autopilot Queue", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="autopilot_queue"),
    PageDefinition("Attribution Deep Dive", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="attribution_depth"),
    PageDefinition("Scenario Optimizer", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="scenario_optimizer"),
    PageDefinition("Cohort Retention & LTV", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="advanced_analytics"),
    PageDefinition("Customer Profitability", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="advanced_analytics"),
    PageDefinition("Budget Planner", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="scenario_planner"),
    PageDefinition("Scheduled Reports", PAGE_GROUP_OPERATIONS, advanced=True, required_feature="scheduled_reports"),
    PageDefinition("Security Center", PAGE_GROUP_ADMIN, advanced=True, required_feature="security_center"),
    PageDefinition("Partner Hub", PAGE_GROUP_ADMIN, advanced=True, required_feature="partner_hub"),
    PageDefinition("White Label Studio", PAGE_GROUP_ADMIN, advanced=True, required_feature="white_label_controls"),
)


def required_feature_for_page(page_name: str) -> str | None:
    for page in PAGE_REGISTRY:
        if page.name == page_name:
            return page.required_feature
    return None


def group_for_page(page_name: str) -> str:
    for page in PAGE_REGISTRY:
        if page.name == page_name:
            return page.group
    return PAGE_GROUP_CORE


def build_grouped_pages(
    show_advanced_pages: bool,
    has_entitlement: Callable[[str], bool],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {group: [] for group in PAGE_GROUP_ORDER}
    for page in PAGE_REGISTRY:
        if page.advanced:
            if not show_advanced_pages:
                continue
            if page.required_feature and not has_entitlement(page.required_feature):
                continue
        grouped.setdefault(page.group, []).append(page.name)
    return {group: pages for group, pages in grouped.items() if pages}


def build_available_pages(
    show_advanced_pages: bool,
    has_entitlement: Callable[[str], bool],
) -> list[str]:
    grouped = build_grouped_pages(show_advanced_pages=show_advanced_pages, has_entitlement=has_entitlement)
    pages: list[str] = []
    for group in PAGE_GROUP_ORDER:
        pages.extend(grouped.get(group, []))
    return pages
