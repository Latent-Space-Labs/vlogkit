"""`python -m vlogkit.server` — Electron sidecar entrypoint."""
from __future__ import annotations

import argparse
from pathlib import Path

from vlogkit.server.app import run_desktop_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m vlogkit.server")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path.home() / ".vlogkit" / "projects.json",
    )
    parser.add_argument("--bind", type=str, default="127.0.0.1")
    args = parser.parse_args()

    run_desktop_server(
        registry_path=args.registry,
        token=args.token,
        host=args.bind,
        port=args.port,
    )


if __name__ == "__main__":
    main()
