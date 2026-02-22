from __future__ import annotations

from pathlib import Path
from typing import Tuple
import pandas as pd

from .common import pick_series


def map_shopify_orders_export(input_csv: Path, output_orders_csv: Path, output_customers_csv: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(input_csv)

    out = pd.DataFrame(
        {
            "order_id": pick_series(df, ["order_id", "Order ID", "name", "Name", "Order Name"], ""),
            "customer_id": pick_series(df, ["customer_id", "Customer ID", "email", "Email"], "unknown_customer"),
            "order_ts": pick_series(
                df,
                ["order_ts", "Created at", "Created At", "created_at", "Processed at", "processed_at"],
                None,
            ),
            "gross_revenue": pd.to_numeric(
                pick_series(df, ["gross_revenue", "Total", "total_price", "Current Total Price"], 0),
                errors="coerce",
            ).fillna(0),
            "discount": pd.to_numeric(
                pick_series(df, ["discount", "Discount Amount", "total_discounts", "Total Discounts"], 0),
                errors="coerce",
            ).fillna(0),
            "cogs": pd.to_numeric(pick_series(df, ["cogs", "COGS"], 0), errors="coerce").fillna(0),
            "status": pick_series(df, ["status", "Financial Status", "financial_status"], "completed"),
        }
    )

    out["order_id"] = out["order_id"].astype(str).str.strip()
    out["customer_id"] = out["customer_id"].astype(str).str.strip()
    out["status"] = out["status"].astype(str).str.strip().str.lower()
    out["order_ts"] = pd.to_datetime(out["order_ts"], utc=True, errors="coerce")
    out = out[out["order_id"] != ""].copy()
    out = out.drop_duplicates(subset=["order_id"], keep="last")

    output_orders_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_orders_csv, index=False)

    customers = (
        out.sort_values(["customer_id", "order_ts"])
        .groupby("customer_id", as_index=False)
        .first()[["customer_id", "order_ts"]]
        .rename(columns={"order_ts": "acquired_at"})
    )
    customers["acquisition_channel"] = "unknown"
    customers["region"] = "unknown"
    customers.to_csv(output_customers_csv, index=False)
    return out, customers
