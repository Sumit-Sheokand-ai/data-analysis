from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd
import pytest

from python.analysis.data_loader import load_from_csv


@pytest.fixture()
def sample_raw_dir(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    sessions = pd.DataFrame(
        [
            {
                "session_id": "s1",
                "session_ts": "2025-01-01T08:00:00Z",
                "customer_id": "c1",
                "utm_source": "facebook",
                "utm_medium": "paid_social",
                "utm_campaign": "meta_q1",
                "channel": "Meta",
                "is_direct": False,
            },
            {
                "session_id": "s2",
                "session_ts": "2025-01-01T08:30:00Z",
                "customer_id": "c2",
                "utm_source": "google",
                "utm_medium": "cpc",
                "utm_campaign": "search_brand",
                "channel": "Google",
                "is_direct": False,
            },
            {
                "session_id": "s3",
                "session_ts": "2025-01-02T09:00:00Z",
                "customer_id": "c3",
                "utm_source": "newsletter",
                "utm_medium": "email",
                "utm_campaign": "email_q1",
                "channel": "Email",
                "is_direct": False,
            },
            {
                "session_id": "s4",
                "session_ts": "2025-02-01T10:00:00Z",
                "customer_id": "c1",
                "utm_source": "",
                "utm_medium": "none",
                "utm_campaign": "",
                "channel": "direct",
                "is_direct": True,
            },
        ]
    )
    sessions.to_csv(raw_dir / "raw_sessions.csv", index=False)

    customers = pd.DataFrame(
        [
            {"customer_id": "c1", "acquired_at": "2025-01-01T08:00:00Z", "acquisition_channel": "Meta", "region": "IN-DL"},
            {"customer_id": "c2", "acquired_at": "2025-01-01T08:30:00Z", "acquisition_channel": "Google", "region": "IN-MH"},
            {"customer_id": "c3", "acquired_at": "2025-01-02T09:00:00Z", "acquisition_channel": "Email", "region": "IN-KA"},
        ]
    )
    customers.to_csv(raw_dir / "raw_customers.csv", index=False)

    orders = pd.DataFrame(
        [
            {"order_id": "o1", "customer_id": "c1", "order_ts": "2025-01-01T10:00:00Z", "gross_revenue": 100.0, "discount": 10.0, "cogs": 40.0, "status": "completed"},
            {"order_id": "o2", "customer_id": "c2", "order_ts": "2025-01-01T11:00:00Z", "gross_revenue": 90.0, "discount": 5.0, "cogs": 30.0, "status": "completed"},
            {"order_id": "o3", "customer_id": "c1", "order_ts": "2025-02-01T12:00:00Z", "gross_revenue": 110.0, "discount": 10.0, "cogs": 45.0, "status": "completed"},
            {"order_id": "o4", "customer_id": "c3", "order_ts": "2025-01-03T09:30:00Z", "gross_revenue": 80.0, "discount": 0.0, "cogs": 35.0, "status": "completed"},
        ]
    )
    orders.to_csv(raw_dir / "raw_orders.csv", index=False)

    refunds = pd.DataFrame(
        [
            {"refund_id": "r1", "order_id": "o2", "refund_amount": 10.0, "refund_ts": "2025-01-02T15:00:00Z", "status": "processed"},
        ]
    )
    refunds.to_csv(raw_dir / "raw_refunds.csv", index=False)

    marketing_spend = pd.DataFrame(
        [
            {"date": "2025-01-01", "channel": "Meta", "campaign": "meta_q1", "spend": 100.0, "clicks": 50, "impressions": 1000, "sales_cost": 10.0},
            {"date": "2025-01-01", "channel": "Google", "campaign": "search_brand", "spend": 120.0, "clicks": 60, "impressions": 1200, "sales_cost": 12.0},
            {"date": "2025-01-02", "channel": "Email", "campaign": "email_q1", "spend": 30.0, "clicks": 20, "impressions": 500, "sales_cost": 3.0},
        ]
    )
    marketing_spend.to_csv(raw_dir / "raw_marketing_spend.csv", index=False)

    return raw_dir


@pytest.fixture()
def sample_frames(sample_raw_dir: Path) -> Dict[str, pd.DataFrame]:
    return load_from_csv(sample_raw_dir)
