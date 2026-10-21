"""CLI: python -m ic_hub [--port N]. Serves the hub on 127.0.0.1 only."""

from __future__ import annotations

import argparse
from pathlib import Path

from .server import HOST, make_server
from .store import Store

DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ic_hub", description="Local Incident Commander hub.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="0 picks a free port")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="keep run history and a hash-chained audit log here (off by default)",
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    store = None
    if args.data_dir is not None:
        try:
            store = Store(args.data_dir)
        except OSError as exc:
            parser.error(f"cannot use --data-dir: {exc.strerror or exc}")
    server = make_server(args.port, store=store)
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
