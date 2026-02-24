from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from python.services.pipeline_service import trigger_pipeline_job


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run D2C analytics pipeline")
    parser.add_argument("--data-source", choices=["csv", "postgres"], default="csv")
    parser.add_argument("--raw-data-dir", default="data/raw")
    parser.add_argument("--processed-data-dir", default="data/processed")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--validation-mode", choices=["strict", "warn"], default="strict")
    parser.add_argument("--service-url", default="")
    parser.add_argument("--service-timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    response = trigger_pipeline_job(
        data_source=args.data_source,
        raw_data_dir=Path(args.raw_data_dir),
        processed_data_dir=Path(args.processed_data_dir),
        database_url=args.database_url or None,
        validation_mode=args.validation_mode,
        service_url=args.service_url,
        timeout_seconds=args.service_timeout_seconds,
    )
    mode = str(response.get("mode", "local")).strip().lower()
    if mode == "local":
        print(
            f"Pipeline completed locally. Generated {int(response.get('output_tables', 0))} "
            f"output tables in {args.processed_data_dir}."
        )
    else:
        print(f"Pipeline job submitted via service ({mode}). Status={response.get('status', 'accepted')}.")


if __name__ == "__main__":
    main()
