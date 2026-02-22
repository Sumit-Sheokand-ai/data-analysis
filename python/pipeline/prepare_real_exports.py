from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from python.analysis.validation import validate_table
from python.connectors.ad_spend import map_ad_spend_export
from python.connectors.ga4 import map_ga4_sessions_export
from python.connectors.shopify import map_shopify_orders_export


def main() -> None:
    parser = argparse.ArgumentParser(description="Map real source exports to canonical raw CSV contract.")
    parser.add_argument("--shopify-orders", default="", help="Path to Shopify orders CSV export.")
    parser.add_argument("--ga4-sessions", default="", help="Path to GA4 sessions CSV export.")
    parser.add_argument("--marketing-spend", default="", help="Path to ad-platform marketing spend CSV export.")
    parser.add_argument("--output-dir", default="data/raw", help="Output directory for canonical raw CSV files.")
    parser.add_argument("--validation-mode", choices=["strict", "warn"], default="strict")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[pd.DataFrame] = []

    if args.shopify_orders:
        orders_df, customers_df = map_shopify_orders_export(
            input_csv=Path(args.shopify_orders),
            output_orders_csv=output_dir / "raw_orders.csv",
            output_customers_csv=output_dir / "raw_customers.csv",
        )
        reports.append(validate_table("orders", orders_df, mode=args.validation_mode))
        reports.append(validate_table("customers", customers_df, mode=args.validation_mode))
        print("Generated raw_orders.csv and raw_customers.csv from Shopify export.")

    if args.ga4_sessions:
        sessions_df = map_ga4_sessions_export(
            input_csv=Path(args.ga4_sessions),
            output_sessions_csv=output_dir / "raw_sessions.csv",
        )
        reports.append(validate_table("sessions", sessions_df, mode=args.validation_mode))
        print("Generated raw_sessions.csv from GA4 export.")
    if args.marketing_spend:
        marketing_spend_df = map_ad_spend_export(
            input_csv=Path(args.marketing_spend),
            output_marketing_spend_csv=output_dir / "raw_marketing_spend.csv",
        )
        reports.append(validate_table("marketing_spend", marketing_spend_df, mode=args.validation_mode))
        print("Generated raw_marketing_spend.csv from ad-platform export.")

    if not args.shopify_orders and not args.ga4_sessions and not args.marketing_spend:
        print("No inputs provided. Use --shopify-orders and/or --ga4-sessions and/or --marketing-spend.")
        print("No inputs provided. Use --shopify-orders and/or --ga4-sessions.")
        return

    combined_report = pd.concat(reports, ignore_index=True) if reports else pd.DataFrame(
        [{"table": "connectors", "rule": "validation_passed", "severity": "info", "issue_count": 0, "detail": "All connector validations passed."}]
    )
    combined_report.to_csv(output_dir / "connector_validation_report.csv", index=False)
    print(f"Connector validation report written to {output_dir / 'connector_validation_report.csv'}.")


if __name__ == "__main__":
    main()
