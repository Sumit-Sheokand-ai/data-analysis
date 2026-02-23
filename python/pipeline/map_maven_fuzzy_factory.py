from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from python.analysis.validation import validate_table
from python.connectors.ad_spend import map_ad_spend_export


SOURCE_TO_CHANNEL = {
    "gsearch": "Google",
    "bsearch": "Bing",
    "socialbook": "Meta",
}

CHANNEL_IMPRESSIONS_FACTOR = {
    "Google": 5,
    "Bing": 4,
    "Meta": 6,
    "Referral": 2,
    "direct": 1,
}

CHANNEL_CPC = {
    "Google": 1.35,
    "Bing": 1.10,
    "Meta": 0.95,
    "Referral": 0.15,
    "direct": 0.00,
}


def _normalize_text(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.where(s.ne(""), pd.NA)


def _build_sessions(sessions_src: pd.DataFrame) -> pd.DataFrame:
    src = _normalize_text(sessions_src["utm_source"])
    campaign = _normalize_text(sessions_src["utm_campaign"])
    referer = _normalize_text(sessions_src["http_referer"])

    channel = src.str.lower().map(SOURCE_TO_CHANNEL)
    channel = channel.where(~(src.isna() & referer.isna()), "direct")
    channel = channel.where(~(src.isna() & referer.notna()), "Referral")
    channel = channel.fillna(src.fillna("unknown").str.title())

    utm_medium = pd.Series(index=sessions_src.index, dtype="string")
    utm_medium = utm_medium.where(~src.str.lower().isin({"gsearch", "bsearch"}), "cpc")
    utm_medium = utm_medium.where(~src.str.lower().eq("socialbook"), "paid_social")
    utm_medium = utm_medium.where(~channel.eq("Referral"), "referral")
    utm_medium = utm_medium.where(~channel.eq("direct"), "none")
    utm_medium = utm_medium.fillna("other")

    campaign_fallback = pd.Series(
        np.where(channel.eq("direct"), "(direct)", "(organic/referral)"),
        index=campaign.index,
    )
    utm_campaign = campaign.fillna(campaign_fallback)

    out = pd.DataFrame(
        {
            "session_id": sessions_src["website_session_id"].astype(str).str.strip(),
            "session_ts": pd.to_datetime(sessions_src["created_at"], utc=True, errors="coerce"),
            "customer_id": sessions_src["user_id"].astype(str).str.strip(),
            "utm_source": src.fillna(""),
            "utm_medium": utm_medium.astype(str),
            "utm_campaign": utm_campaign.astype(str),
            "channel": channel.astype(str),
        }
    )
    out["is_direct"] = out["channel"].str.lower().eq("direct")
    out = out[out["session_id"] != ""].drop_duplicates(subset=["session_id"], keep="last")
    return out


def _build_orders(orders_src: pd.DataFrame, refunds_src: pd.DataFrame) -> pd.DataFrame:
    refunded_order_ids = set(refunds_src["order_id"].astype(str).str.strip())
    order_id = orders_src["order_id"].astype(str).str.strip()

    out = pd.DataFrame(
        {
            "order_id": order_id,
            "customer_id": orders_src["user_id"].astype(str).str.strip(),
            "order_ts": pd.to_datetime(orders_src["created_at"], utc=True, errors="coerce"),
            "gross_revenue": pd.to_numeric(orders_src["price_usd"], errors="coerce").fillna(0.0).clip(lower=0),
            "discount": 0.0,
            "cogs": pd.to_numeric(orders_src["cogs_usd"], errors="coerce").fillna(0.0).clip(lower=0),
            "status": np.where(order_id.isin(refunded_order_ids), "refunded", "completed"),
        }
    )
    out = out[out["order_id"] != ""].drop_duplicates(subset=["order_id"], keep="last")
    return out


def _build_refunds(refunds_src: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "refund_id": refunds_src["order_item_refund_id"].astype(str).str.strip(),
            "order_id": refunds_src["order_id"].astype(str).str.strip(),
            "refund_amount": pd.to_numeric(refunds_src["refund_amount_usd"], errors="coerce").fillna(0.0).clip(lower=0),
            "refund_ts": pd.to_datetime(refunds_src["created_at"], utc=True, errors="coerce"),
            "status": "processed",
        }
    )
    out = out[(out["refund_id"] != "") & (out["order_id"] != "")].drop_duplicates(subset=["refund_id"], keep="last")
    return out


def _build_customers(sessions: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    session_first = (
        sessions.sort_values(["customer_id", "session_ts"])
        .groupby("customer_id", as_index=False)
        .first()[["customer_id", "session_ts", "channel"]]
        .rename(columns={"session_ts": "first_session_ts", "channel": "acquisition_channel"})
    )
    order_first = (
        orders.sort_values(["customer_id", "order_ts"])
        .groupby("customer_id", as_index=False)
        .first()[["customer_id", "order_ts"]]
        .rename(columns={"order_ts": "first_order_ts"})
    )
    all_customers = (
        pd.concat(
            [
                sessions[["customer_id"]].copy(),
                orders[["customer_id"]].copy(),
            ],
            ignore_index=True,
        )
        .dropna()
        .drop_duplicates()
    )
    out = all_customers.merge(session_first, on="customer_id", how="left").merge(order_first, on="customer_id", how="left")
    out["acquired_at"] = pd.concat([out["first_session_ts"], out["first_order_ts"]], axis=1).min(axis=1)
    out["acquisition_channel"] = out["acquisition_channel"].fillna("unknown")
    out["region"] = "unknown"
    out = out[["customer_id", "acquired_at", "acquisition_channel", "region"]]
    out = out.drop_duplicates(subset=["customer_id"], keep="first")
    return out


def _build_marketing_spend(sessions: pd.DataFrame) -> pd.DataFrame:
    spend = sessions.copy()
    spend["date"] = pd.to_datetime(spend["session_ts"], utc=True, errors="coerce").dt.date
    spend["campaign"] = _normalize_text(spend["utm_campaign"]).fillna("(unknown)")

    grouped = (
        spend.groupby(["date", "channel", "campaign"], as_index=False)["session_id"]
        .nunique()
        .rename(columns={"session_id": "clicks"})
    )
    grouped["impressions_factor"] = grouped["channel"].map(CHANNEL_IMPRESSIONS_FACTOR).fillna(2).astype(int)
    grouped["impressions"] = grouped["clicks"] * grouped["impressions_factor"]
    grouped["cpc"] = grouped["channel"].map(CHANNEL_CPC).fillna(0.10)
    grouped["spend"] = grouped["clicks"] * grouped["cpc"]

    variable_rate = np.where(grouped["channel"].isin(["Google", "Bing", "Meta"]), 0.12, np.where(grouped["channel"].eq("Referral"), 0.05, 0.0))
    grouped["sales_cost"] = grouped["spend"] * variable_rate

    out = grouped[["date", "channel", "campaign", "spend", "clicks", "impressions", "sales_cost"]].copy()
    out["spend"] = out["spend"].round(2)
    out["sales_cost"] = out["sales_cost"].round(2)
    out = out.sort_values(["date", "channel", "campaign"]).reset_index(drop=True)
    return out


def map_maven_fuzzy_factory(
    input_dir: Path,
    output_dir: Path,
    validation_mode: str,
    marketing_spend_input_csv: Path | None = None,
    allow_proxy_marketing_spend: bool = False,
) -> Dict[str, pd.DataFrame]:
    sessions_src = pd.read_csv(input_dir / "website_sessions.csv")
    orders_src = pd.read_csv(input_dir / "orders.csv")
    refunds_src = pd.read_csv(input_dir / "order_item_refunds.csv")

    sessions = _build_sessions(sessions_src)
    orders = _build_orders(orders_src, refunds_src)
    refunds = _build_refunds(refunds_src)
    customers = _build_customers(sessions, orders)
    if marketing_spend_input_csv is not None:
        marketing_spend = map_ad_spend_export(marketing_spend_input_csv, output_dir / "raw_marketing_spend.csv")
    elif allow_proxy_marketing_spend:
        marketing_spend = _build_marketing_spend(sessions)
    else:
        raise ValueError(
            "Real marketing spend CSV is required. Provide --marketing-spend-csv, "
            "or pass --allow-proxy-marketing-spend to generate proxy spend."
        )

    tables = {
        "sessions": sessions,
        "customers": customers,
        "orders": orders,
        "refunds": refunds,
        "marketing_spend": marketing_spend,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    tables["sessions"].to_csv(output_dir / "raw_sessions.csv", index=False)
    tables["customers"].to_csv(output_dir / "raw_customers.csv", index=False)
    tables["orders"].to_csv(output_dir / "raw_orders.csv", index=False)
    tables["refunds"].to_csv(output_dir / "raw_refunds.csv", index=False)
    if marketing_spend_input_csv is None:
        tables["marketing_spend"].to_csv(output_dir / "raw_marketing_spend.csv", index=False)

    reports = [
        validate_table("sessions", tables["sessions"], mode=validation_mode),
        validate_table("customers", tables["customers"], mode=validation_mode),
        validate_table("orders", tables["orders"], mode=validation_mode),
        validate_table("refunds", tables["refunds"], mode=validation_mode),
        validate_table("marketing_spend", tables["marketing_spend"], mode=validation_mode),
    ]
    pd.concat(reports, ignore_index=True).to_csv(output_dir / "maven_mapping_validation_report.csv", index=False)
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Map Maven Fuzzy Factory exports to canonical raw CSV contract.")
    parser.add_argument(
        "--input-dir",
        default="data/raw/external/maven_fuzzy_factory",
        help="Directory containing Maven Fuzzy Factory CSV exports.",
    )
    parser.add_argument("--output-dir", default="data/raw", help="Output directory for canonical raw CSV files.")
    parser.add_argument(
        "--marketing-spend-csv",
        default="",
        help="Ad-platform spend export CSV used to create raw_marketing_spend.csv.",
    )
    parser.add_argument(
        "--allow-proxy-marketing-spend",
        action="store_true",
        help="Allow proxy marketing spend generation from sessions when real spend file is not provided.",
    )
    parser.add_argument("--validation-mode", choices=["strict", "warn"], default="strict")
    args = parser.parse_args()
    marketing_spend_input = Path(args.marketing_spend_csv) if args.marketing_spend_csv else None
    tables = map_maven_fuzzy_factory(
        Path(args.input_dir),
        Path(args.output_dir),
        validation_mode=args.validation_mode,
        marketing_spend_input_csv=marketing_spend_input,
        allow_proxy_marketing_spend=args.allow_proxy_marketing_spend,
    )
    print(
        "Generated canonical raw files from Maven Fuzzy Factory dataset: "
        f"sessions={len(tables['sessions'])}, customers={len(tables['customers'])}, "
        f"orders={len(tables['orders'])}, refunds={len(tables['refunds'])}, "
        f"marketing_spend={len(tables['marketing_spend'])}."
    )


if __name__ == "__main__":
    main()
