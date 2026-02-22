from __future__ import annotations

from pathlib import Path
import pandas as pd

from .common import pick_series


def map_ga4_sessions_export(input_csv: Path, output_sessions_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(input_csv)

    out = pd.DataFrame(
        {
            "session_id": pick_series(df, ["session_id", "ga_session_id", "Session ID"], ""),
            "session_ts": pick_series(
                df,
                ["session_ts", "event_timestamp", "Event Timestamp", "date", "Date"],
                None,
            ),
            "customer_id": pick_series(df, ["customer_id", "user_id", "User ID", "user_pseudo_id"], "unknown_customer"),
            "utm_source": pick_series(df, ["utm_source", "session_source", "source", "Source"], ""),
            "utm_medium": pick_series(df, ["utm_medium", "session_medium", "medium", "Medium"], ""),
            "utm_campaign": pick_series(df, ["utm_campaign", "session_campaign", "campaign", "Campaign"], ""),
            "channel": pick_series(df, ["channel", "default_channel_group", "Default Channel Group"], "direct"),
        }
    )

    out["session_id"] = out["session_id"].astype(str).str.strip()
    out["customer_id"] = out["customer_id"].astype(str).str.strip()
    out["session_ts"] = pd.to_datetime(out["session_ts"], utc=True, errors="coerce")
    out["is_direct"] = out["channel"].astype(str).str.lower().eq("direct")
    out = out[out["session_id"] != ""].copy()
    out = out.drop_duplicates(subset=["session_id"], keep="last")

    output_sessions_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_sessions_csv, index=False)
    return out
