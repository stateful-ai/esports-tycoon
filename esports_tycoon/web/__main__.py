"""Launch the local slice web app.

    python -m esports_tycoon.web [options]

Serves the manager view + Chirper feed on ``127.0.0.1`` in one process and writes
``runs/<slice_id>/`` artifacts on completion. Templated (zero-API) mode by default.

    python -m esports_tycoon.web --port 8000 --opponent apex_foundry --seed 6
"""

from __future__ import annotations

import argparse
from typing import get_args

from esports_tycoon.runner.model import SliceConfig
from esports_tycoon.schema import TacticalStance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon.web", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
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
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
