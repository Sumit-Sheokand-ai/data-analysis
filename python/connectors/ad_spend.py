from __future__ import annotations

from pathlib import Path
import pandas as pd

from .common import pick_series


def _normalize_channel(raw: pd.Series) -> pd.Series:
    cleaned = raw.astype(str).str.strip()
    lowered = cleaned.str.lower()
    mapped = pd.Series(index=cleaned.index, dtype="string")
    mapped = mapped.where(~lowered.isin({"google", "google ads", "adwords", "gsearch"}), "Google")
    mapped = mapped.where(~lowered.isin({"bing", "bing ads", "bsearch", "microsoft ads"}), "Bing")
    mapped = mapped.where(~lowered.isin({"meta", "facebook", "facebook ads", "instagram", "socialbook"}), "Meta")
    mapped = mapped.where(~lowered.isin({"affiliate", "partner", "referral"}), "Affiliate")
    mapped = mapped.where(~lowered.isin({"email", "newsletter", "mail"}), "Email")
    mapped = mapped.fillna(cleaned.where(cleaned.ne(""), "unknown"))
    return mapped.astype(str)


def _parse_date(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    return parsed.dt.date


def map_ad_spend_export(input_csv: Path, output_marketing_spend_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(input_csv)

    date = _parse_date(
        pick_series(
            df,
            [
                "date",
                "Date",
                "day",
                "Day",
                "report_date",
                "Report Date",
                "start_date",
                "Start Date",
            ],
            None,
        )
    )
    channel_raw = pick_series(
        df,
        [
            "channel",
            "Channel",
            "platform",
            "Platform",
            "source",
            "Source",
            "network",
            "Network",
            "publisher",
            "Publisher",
            "account_name",
            "Account Name",
        ],
        "unknown",
    )
    campaign = (
        pick_series(
            df,
            [
                "campaign",
                "Campaign",
                "campaign_name",
                "Campaign Name",
                "campaignName",
                "adset_name",
                "Ad Set Name",
            ],
            "(unknown)",
        )
        .astype(str)
        .str.strip()
    )
    campaign = campaign.where(campaign.ne(""), "(unknown)")

    spend = pd.to_numeric(
        pick_series(
            df,
            [
                "spend",
                "Spend",
                "cost",
                "Cost",
                "amount_spent",
                "Amount Spent",
                "ad_spend",
                "Ad Spend",
            ],
            0,
        ),
        errors="coerce",
    ).fillna(0.0)
    clicks = pd.to_numeric(pick_series(df, ["clicks", "Clicks", "link_clicks", "Link Clicks"], 0), errors="coerce").fillna(0.0)
    impressions = pd.to_numeric(
        pick_series(df, ["impressions", "Impressions", "views", "Views", "ad_impressions"], 0),
        errors="coerce",
    ).fillna(0.0)
    sales_cost = pd.to_numeric(
        pick_series(
            df,
            ["sales_cost", "Sales Cost", "platform_fee", "Platform Fee", "fees", "Fees"],
            0,
        ),
        errors="coerce",
    ).fillna(0.0)

    out = pd.DataFrame(
        {
            "date": date,
            "channel": _normalize_channel(channel_raw),
            "campaign": campaign,
            "spend": spend.clip(lower=0),
            "clicks": clicks.clip(lower=0),
            "impressions": impressions.clip(lower=0),
            "sales_cost": sales_cost.clip(lower=0),
        }
    )

    out = out.dropna(subset=["date"]).copy()
    out["impressions"] = out[["impressions", "clicks"]].max(axis=1)
    out = (
        out.groupby(["date", "channel", "campaign"], as_index=False)[["spend", "clicks", "impressions", "sales_cost"]]
        .sum()
        .sort_values(["date", "channel", "campaign"])
        .reset_index(drop=True)
    )
    out["spend"] = out["spend"].round(2)
    out["sales_cost"] = out["sales_cost"].round(2)
    out["clicks"] = out["clicks"].round(0).astype(int)
    out["impressions"] = out["impressions"].round(0).astype(int)

    output_marketing_spend_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_marketing_spend_csv, index=False)
    return out
