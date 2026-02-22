from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List
import pandas as pd


class DataValidationError(ValueError):
    pass


@dataclass
class ValidationIssue:
    table: str
    rule: str
    severity: str
    issue_count: int
    detail: str


REQUIRED_COLUMNS: Dict[str, list[str]] = {
    "marketing_spend": ["date", "channel", "campaign", "spend", "clicks", "impressions", "sales_cost"],
    "sessions": ["session_id", "session_ts", "customer_id", "utm_source", "utm_medium", "utm_campaign", "channel", "is_direct"],
    "customers": ["customer_id", "acquired_at", "acquisition_channel", "region"],
    "orders": ["order_id", "customer_id", "order_ts", "gross_revenue", "discount", "cogs", "status"],
    "refunds": ["refund_id", "order_id", "refund_amount", "refund_ts", "status"],
}

NUMERIC_NON_NEGATIVE: Dict[str, list[str]] = {
    "marketing_spend": ["spend", "clicks", "impressions", "sales_cost"],
    "orders": ["gross_revenue", "discount", "cogs"],
    "refunds": ["refund_amount"],
}

UNIQUE_KEYS: Dict[str, list[str]] = {
    "sessions": ["session_id"],
    "customers": ["customer_id"],
    "orders": ["order_id"],
    "refunds": ["refund_id"],
}

DATETIME_COLUMNS: Dict[str, list[str]] = {
    "marketing_spend": ["date"],
    "sessions": ["session_ts"],
    "customers": ["acquired_at"],
    "orders": ["order_ts"],
    "refunds": ["refund_ts"],
}

ID_LIKE_COLUMNS: Dict[str, list[str]] = {
    "sessions": ["session_id", "customer_id"],
    "customers": ["customer_id"],
    "orders": ["order_id", "customer_id"],
    "refunds": ["refund_id", "order_id"],
}

ALLOWED_STATUS = {
    "orders": {"completed", "cancelled", "refunded", "processing", "pending"},
    "refunds": {"processed", "pending", "failed"},
}


def _add_issue(issues: List[ValidationIssue], table: str, rule: str, severity: str, issue_count: int, detail: str) -> None:
    if issue_count > 0:
        issues.append(
            ValidationIssue(
                table=table,
                rule=rule,
                severity=severity,
                issue_count=int(issue_count),
                detail=detail,
            )
        )


def _blank_or_null_count(series: pd.Series) -> int:
    as_str = series.astype(str).str.strip()
    return int(series.isna().sum() + as_str.eq("").sum() + as_str.eq("nan").sum() + as_str.eq("None").sum())


def _validate_table_internal(table: str, df: pd.DataFrame, issues: List[ValidationIssue]) -> None:
    required = REQUIRED_COLUMNS.get(table, [])
    missing = [c for c in required if c not in df.columns]
    _add_issue(
        issues,
        table,
        "required_columns",
        "error",
        len(missing),
        f"Missing required columns: {missing}" if missing else "",
    )
    if missing:
        return

    for col in DATETIME_COLUMNS.get(table, []):
        invalid = pd.to_datetime(df[col], utc=True, errors="coerce").isna().sum()
        _add_issue(
            issues,
            table,
            f"datetime_parse:{col}",
            "error",
            int(invalid),
            f"Invalid/empty datetime values in `{col}`",
        )

    for col in NUMERIC_NON_NEGATIVE.get(table, []):
        numeric = pd.to_numeric(df[col], errors="coerce")
        invalid_num = numeric.isna().sum()
        negative = (numeric < 0).sum()
        _add_issue(
            issues,
            table,
            f"numeric_parse:{col}",
            "error",
            int(invalid_num),
            f"Non-numeric values in `{col}`",
        )
        _add_issue(
            issues,
            table,
            f"non_negative:{col}",
            "error",
            int(negative),
            f"Negative values in `{col}`",
        )

    for col in ID_LIKE_COLUMNS.get(table, []):
        blank = _blank_or_null_count(df[col])
        _add_issue(
            issues,
            table,
            f"id_not_blank:{col}",
            "error",
            int(blank),
            f"Blank/null identifiers in `{col}`",
        )

    key = UNIQUE_KEYS.get(table)
    if key:
        duplicate_rows = int(df.duplicated(subset=key, keep=False).sum())
        _add_issue(
            issues,
            table,
            f"unique_key:{'+'.join(key)}",
            "error",
            duplicate_rows,
            f"Duplicate key rows for {key}",
        )

    if table in ALLOWED_STATUS and "status" in df.columns:
        statuses = df["status"].astype(str).str.strip().str.lower()
        invalid_status = (~statuses.isin(ALLOWED_STATUS[table])).sum()
        _add_issue(
            issues,
            table,
            "status_domain",
            "error",
            int(invalid_status),
            f"Values outside allowed status set for `{table}`",
        )

    if table == "sessions":
        channel = df["channel"].astype(str).str.strip().str.lower()
        blank_channel = _blank_or_null_count(df["channel"])
        _add_issue(
            issues,
            table,
            "channel_not_blank",
            "error",
            int(blank_channel),
            "Blank/null channel values in sessions",
        )
        direct = df["is_direct"].astype(str).str.strip().str.lower().isin({"true", "1", "t", "yes"})
        direct_channel_mismatch = ((direct & (channel != "direct")) | (~direct & (channel == "direct"))).sum()
        _add_issue(
            issues,
            table,
            "direct_channel_consistency",
            "warn",
            int(direct_channel_mismatch),
            "Mismatch between `is_direct` flag and `channel` value.",
        )

    if table == "marketing_spend":
        duplicate_grain = int(df.duplicated(subset=["date", "channel", "campaign"], keep=False).sum())
        _add_issue(
            issues,
            table,
            "grain_uniqueness:date+channel+campaign",
            "warn",
            duplicate_grain,
            "Duplicate records at marketing spend grain; consider pre-aggregation",
        )
        clicks = pd.to_numeric(df["clicks"], errors="coerce")
        impressions = pd.to_numeric(df["impressions"], errors="coerce")
        spend = pd.to_numeric(df["spend"], errors="coerce")
        clicks_gt_impressions = (clicks > impressions).sum()
        _add_issue(
            issues,
            table,
            "clicks_le_impressions",
            "error",
            int(clicks_gt_impressions),
            "Clicks cannot exceed impressions.",
        )
        spend_with_zero_clicks = ((spend > 0) & (clicks == 0)).sum()
        _add_issue(
            issues,
            table,
            "spend_with_zero_clicks",
            "warn",
            int(spend_with_zero_clicks),
            "Spend exists with zero clicks; verify tracking/attribution windows.",
        )

    if table == "orders":
        gross = pd.to_numeric(df["gross_revenue"], errors="coerce")
        discount = pd.to_numeric(df["discount"], errors="coerce")
        discount_gt_gross = (discount > gross).sum()
        _add_issue(
            issues,
            table,
            "discount_le_gross_revenue",
            "error",
            int(discount_gt_gross),
            "Discount cannot exceed gross revenue.",
        )
        high_discount_ratio = ((gross > 0) & ((discount / gross) > 0.8)).sum()
        _add_issue(
            issues,
            table,
            "high_discount_ratio",
            "warn",
            int(high_discount_ratio),
            "Discount ratio > 80% detected; verify promo logic or source mapping.",
        )


def _cross_table_checks(frames: Dict[str, pd.DataFrame], issues: List[ValidationIssue]) -> None:
    if {"orders", "customers"}.issubset(frames.keys()):
        orders = frames["orders"].copy()
        customers = frames["customers"].copy()
        missing_customers = (~orders["customer_id"].astype(str).isin(customers["customer_id"].astype(str))).sum()
        _add_issue(
            issues,
            "orders/customers",
            "fk_orders_customer_id",
            "error",
            int(missing_customers),
            "orders.customer_id missing in customers.customer_id",
        )
        merged = orders.merge(customers[["customer_id", "acquired_at"]], on="customer_id", how="left")
        order_ts = pd.to_datetime(merged["order_ts"], utc=True, errors="coerce")
        acquired_at = pd.to_datetime(merged["acquired_at"], utc=True, errors="coerce")
        order_before_acquisition = (order_ts < acquired_at).sum()
        _add_issue(
            issues,
            "orders/customers",
            "order_ts_ge_acquired_at",
            "error",
            int(order_before_acquisition),
            "Order timestamp occurs before customer acquisition timestamp.",
        )

    if {"refunds", "orders"}.issubset(frames.keys()):
        refunds = frames["refunds"].copy()
        orders = frames["orders"].copy()
        missing_orders = (~refunds["order_id"].astype(str).isin(orders["order_id"].astype(str))).sum()
        _add_issue(
            issues,
            "refunds/orders",
            "fk_refunds_order_id",
            "error",
            int(missing_orders),
            "refunds.order_id missing in orders.order_id",
        )
        merged = refunds.merge(
            orders[["order_id", "gross_revenue", "order_ts"]],
            on="order_id",
            how="left",
        )
        refund_amount = pd.to_numeric(merged["refund_amount"], errors="coerce")
        gross_revenue = pd.to_numeric(merged["gross_revenue"], errors="coerce")
        refund_exceeds_gross = (refund_amount > gross_revenue).sum()
        _add_issue(
            issues,
            "refunds/orders",
            "refund_amount_le_order_gross",
            "error",
            int(refund_exceeds_gross),
            "Refund amount cannot exceed referenced order gross revenue.",
        )
        refund_ts = pd.to_datetime(merged["refund_ts"], utc=True, errors="coerce")
        order_ts = pd.to_datetime(merged["order_ts"], utc=True, errors="coerce")
        refund_before_order = (refund_ts < order_ts).sum()
        _add_issue(
            issues,
            "refunds/orders",
            "refund_ts_ge_order_ts",
            "error",
            int(refund_before_order),
            "Refund timestamp occurs before order timestamp.",
        )


def _raise_if_needed(report: pd.DataFrame, mode: str) -> None:
    if mode != "strict":
        return
    errors = report[report["severity"] == "error"] if not report.empty else report
    if errors.empty:
        return
    top = errors.head(10)
    lines = [
        f"{r.table} | {r.rule} | count={int(r.issue_count)} | {r.detail}"
        for r in top.itertuples(index=False)
    ]
    raise DataValidationError("Validation failed:\n" + "\n".join(lines))


def validate_table(table: str, df: pd.DataFrame, mode: str = "strict") -> pd.DataFrame:
    mode = mode.strip().lower()
    if mode not in {"strict", "warn"}:
        raise ValueError("validation mode must be one of: strict, warn")

    issues: List[ValidationIssue] = []
    _validate_table_internal(table, df, issues)
    report = pd.DataFrame([asdict(i) for i in issues], columns=["table", "rule", "severity", "issue_count", "detail"])
    _raise_if_needed(report, mode)

    if report.empty:
        report = pd.DataFrame(
            [
                {
                    "table": table,
                    "rule": "validation_passed",
                    "severity": "info",
                    "issue_count": 0,
                    "detail": "All table-level validation checks passed.",
                }
            ]
        )
    return report


def validate_frames(frames: Dict[str, pd.DataFrame], mode: str = "strict") -> pd.DataFrame:
    mode = mode.strip().lower()
    if mode not in {"strict", "warn"}:
        raise ValueError("validation mode must be one of: strict, warn")

    issues: List[ValidationIssue] = []
    for table, df in frames.items():
        _validate_table_internal(table, df, issues)
    _cross_table_checks(frames, issues)

    report = pd.DataFrame([asdict(i) for i in issues], columns=["table", "rule", "severity", "issue_count", "detail"])
    _raise_if_needed(report, mode)

    if report.empty:
        report = pd.DataFrame(
            [
                {
                    "table": "all",
                    "rule": "validation_passed",
                    "severity": "info",
                    "issue_count": 0,
                    "detail": "All validation checks passed.",
                }
            ]
        )
    return report
