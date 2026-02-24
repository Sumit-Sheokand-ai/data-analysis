from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from python.services.insights_api import create_insights_http_server


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run insights automation state HTTP service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--state-file", default="data/processed/insights_state.json")
    args = parser.parse_args()

    server = create_insights_http_server(
        host=args.host,
        port=args.port,
        state_file=Path(args.state_file),
    )
    print(f"Insights automation service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
