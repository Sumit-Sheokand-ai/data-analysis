from __future__ import annotations

import argparse

from dotenv import load_dotenv

from python.services.pipeline_api import create_pipeline_http_server


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run analytics pipeline HTTP service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    server = create_pipeline_http_server(host=args.host, port=args.port)
    print(f"Pipeline service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

