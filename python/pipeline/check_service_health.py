from __future__ import annotations

import argparse
import os

from python.services.service_health import assert_services_healthy


def main() -> None:
    parser = argparse.ArgumentParser(description="Check health endpoints for configured services")
    parser.add_argument("--pipeline-url", default="")
    parser.add_argument("--insights-url", default="")
    parser.add_argument("--policy-url", default="")
    parser.add_argument("--timeout-seconds", type=int, default=5)
    args = parser.parse_args()

    services = {
        "pipeline": args.pipeline_url,
        "insights": args.insights_url,
        "policy": args.policy_url,
    }
    service_token = os.getenv("SERVICE_API_AUTH_TOKEN", "").strip() or os.getenv("APP_SERVICE_AUTH_TOKEN", "").strip()
    results = assert_services_healthy(
        services,
        timeout_seconds=args.timeout_seconds,
        service_token=service_token,
    )
    for name, result in results.items():
        print(f"{name}: ok ({result.get('url')})")


if __name__ == "__main__":
    main()

