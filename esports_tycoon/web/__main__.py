"""Launch the local slice web app.

    python -m esports_tycoon.web [options]

Serves the manager view + Chirper feed on ``127.0.0.1`` in one process and writes
``runs/<slice_id>/`` artifacts on completion. Templated (zero-API) mode by default.

    python -m esports_tycoon.web --port 8765 --opponent apex_foundry --seed 6
"""

from __future__ import annotations

import argparse
import errno
from typing import get_args

from esports_tycoon.runner.model import SliceConfig
from esports_tycoon.schema import TacticalStance

#: Default bind port. Deliberately *not* 8000/8001/7860 — those are commonly
#: taken by a local LLM server, an LLM router, and a Stable Diffusion UI on a
#: dev box, so the slice app would fail to bind. 8765 is an unlikely collision.
DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon.web", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"bind port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--seed", type=int, default=6, help="match seed (default: 6)")
    parser.add_argument("--opponent", default="apex_foundry", help="rival org id for the week-6 fixture")
    parser.add_argument("--map", default="Helix", help="map being played (default: Helix)")
    parser.add_argument(
        "--stance", choices=list(get_args(TacticalStance)), default="default", help="the captain's tactical stance"
    )
    parser.add_argument("--runs-dir", default="runs", help="where to write runs/<slice_id>/ (default: runs)")
    parser.add_argument("--debug", action="store_true", help="run Flask in debug mode")
    args = parser.parse_args(argv)

    try:
        from esports_tycoon.web import create_app
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        if exc.name == "flask":
            parser.error("Flask is not installed. Install the web extra: pip install -e '.[web]'")
        raise

    config = SliceConfig(opponent=args.opponent, map=args.map, seed=args.seed, tactical_stance=args.stance)
    app = create_app(config=config, output_root=args.runs_dir)
    print(f"esports-tycoon slice → http://{args.host}:{args.port}  (templated mode, runs in {args.runs_dir}/)")
    try:
        app.run(host=args.host, port=args.port, debug=args.debug)
    except OSError as exc:
        # Only the address-in-use case is a port collision; other bind failures
        # (bad host, permission denied) need a different fix, so don't send the
        # user to change --port for those.
        if exc.errno == errno.EADDRINUSE:
            parser.error(
                f"port {args.port} on {args.host} is already in use — re-run with "
                f"a free one, e.g. --port {args.port + 1}."
            )
        parser.error(f"could not bind {args.host}:{args.port}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
