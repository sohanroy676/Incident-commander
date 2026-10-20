"""CLI: python -m ic_hub [--port N]. Serves the hub on 127.0.0.1 only."""

from __future__ import annotations

import argparse

from .server import HOST, make_server

DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ic_hub", description="Local Incident Commander hub.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="0 picks a free port")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    server = make_server(args.port)
    print(f"ic_hub: http://{HOST}:{server.port}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("ic_hub: stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
