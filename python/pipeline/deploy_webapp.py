from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from python.analysis.pipeline import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "app" / "main.py"


def _run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _refresh_data(data_source: str, validation_mode: str) -> None:
    run_pipeline(
        data_source=data_source,
        raw_data_dir=PROJECT_ROOT / "data" / "raw",
        processed_data_dir=PROJECT_ROOT / "data" / "processed",
        validation_mode=validation_mode,
    )


def run_local(port: int, refresh_data: bool, data_source: str, validation_mode: str) -> None:
    if refresh_data:
        _refresh_data(data_source=data_source, validation_mode=validation_mode)
    _run_cmd(
        [
            "streamlit",
            "run",
            str(APP_PATH),
            f"--server.port={port}",
            "--server.address=0.0.0.0",
        ]
    )


def docker_build(image: str) -> None:
    _run_cmd(["docker", "build", "-t", image, str(PROJECT_ROOT)])


def docker_run(image: str, port: int) -> None:
    _run_cmd(["docker", "run", "--rm", "-p", f"{port}:8501", image])


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Deploy helper for D2C analytics web app.")
    parser.add_argument("--mode", choices=["local", "docker-build", "docker-run"], default="local")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--image", default="d2c-analytics-webapp:latest")
    parser.add_argument("--refresh-data", action="store_true", help="Run analytics pipeline before local app start.")
    parser.add_argument("--data-source", choices=["csv", "postgres"], default="csv")
    parser.add_argument("--validation-mode", choices=["strict", "warn"], default="warn")
    args = parser.parse_args()

    if args.mode == "local":
        run_local(
            port=args.port,
            refresh_data=args.refresh_data,
            data_source=args.data_source,
            validation_mode=args.validation_mode,
        )
    elif args.mode == "docker-build":
        docker_build(image=args.image)
    else:
        docker_run(image=args.image, port=args.port)


if __name__ == "__main__":
    main()
