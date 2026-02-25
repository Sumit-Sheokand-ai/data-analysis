from __future__ import annotations

import argparse

from python.webapp.server import create_webapp_http_server, load_webapp_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Syntellia browser-native web server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()

    config = load_webapp_config()
    server = create_webapp_http_server(host=args.host, port=args.port, config=config)
    print(f"Syntellia web server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

