from __future__ import annotations

import argparse
from pathlib import Path
from dotenv import load_dotenv

from python.analysis.pipeline import run_pipeline


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run D2C analytics pipeline")
    parser.add_argument("--data-source", choices=["csv", "postgres"], default="csv")
    parser.add_argument("--raw-data-dir", default="data/raw")
    parser.add_argument("--processed-data-dir", default="data/processed")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--validation-mode", choices=["strict", "warn"], default="strict")
    args = parser.parse_args()

    outputs = run_pipeline(
        data_source=args.data_source,
        raw_data_dir=Path(args.raw_data_dir),
        processed_data_dir=Path(args.processed_data_dir),
        database_url=args.database_url or None,
        validation_mode=args.validation_mode,
    )
    print(f"Pipeline completed. Generated {len(outputs)} output tables in {args.processed_data_dir}.")


if __name__ == "__main__":
    main()
