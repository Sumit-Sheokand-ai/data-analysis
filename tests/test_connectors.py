from pathlib import Path

import pandas as pd

from python.connectors.ad_spend import map_ad_spend_export


def test_map_ad_spend_export_normalizes_common_columns(tmp_path: Path) -> None:
    src = pd.DataFrame(
        {
            "Date": ["2025-09-01", "2025-09-01", "2025-09-02"],
            "Platform": ["Google Ads", "Meta", "bing"],
            "Campaign Name": ["Brand", "Prospecting", "Search NB"],
            "Amount Spent": [100.5, 80.0, 120.0],
            "Clicks": [50, 30, 40],
            "Impressions": [5000, 1200, 4000],
            "Platform Fee": [10.0, 4.0, 12.0],
        }
    )
    input_csv = tmp_path / "ad_export.csv"
    output_csv = tmp_path / "raw_marketing_spend.csv"
    src.to_csv(input_csv, index=False)

    out = map_ad_spend_export(input_csv, output_csv)

    assert output_csv.exists()
    assert list(out.columns) == ["date", "channel", "campaign", "spend", "clicks", "impressions", "sales_cost"]
    assert set(out["channel"]) == {"Google", "Meta", "Bing"}
    assert (out["impressions"] >= out["clicks"]).all()
    assert (out["spend"] >= 0).all()
    assert (out["sales_cost"] >= 0).all()
