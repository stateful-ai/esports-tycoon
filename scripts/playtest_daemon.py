"""Start a synthetic-player session: the game, a browser, and a control port.

    python scripts/playtest_daemon.py --persona first-timer --port 8710

Leaves a live browser sitting on the game. Drive it with `scripts/play.py`,
which is what a synthetic-player agent uses:

    python scripts/play.py tab market
    python scripts/play.py advance

Everything the session does lands under `runs/synthetic-players/<persona>/`:
`screens/` (one PNG per step — the agent reads these to *see* the game),
`journal.jsonl` (every action + observation), `findings.jsonl` (the point).

The daemon writes `session.json` next to those, so the client can find the
port without being told.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from esports_sim.playtest.control import ControlState, serve  # noqa: E402
from esports_sim.playtest.personas import PERSONAS, persona as get_persona  # noqa: E402
from esports_sim.playtest.session import GameServer, PlaytestSession, free_port  # noqa: E402

DEFAULT_ROOT = REPO_ROOT / "runs" / "synthetic-players"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--persona", default="first-timer",
        choices=[p.id for p in PERSONAS] + ["freeform"],
        help="which synthetic player this session is for",
    )
    parser.add_argument("--port", type=int, default=0, help="control port (0 = pick a free one)")
    parser.add_argument("--game-port", type=int, default=0, help="game port (0 = pick a free one)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument(
        "--start-campaign", action="store_true",
        help="create the campaign before handing over, so the agent starts in-game",
    )
    parser.add_argument("--team-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=950)
    parser.add_argument(
        "--headed", action="store_true", help="show the browser (needs a display)"
    )
    args = parser.parse_args()

    run_dir = args.run_dir or (DEFAULT_ROOT / args.persona)
    run_dir.mkdir(parents=True, exist_ok=True)
    control_port = args.port or free_port()

    game = GameServer(args.game_port or None, saves_dir=run_dir / "saves")
    print(f"starting game server on port {game.port} ...", flush=True)
    game.start(log_path=run_dir / "server.log")
    print(f"game up at {game.url}", flush=True)

    session = PlaytestSession(
        run_dir=run_dir,
        base_url=game.url,
        headless=not args.headed,
        width=args.width,
        height=args.height,
    )
    session.start()
    print(f"browser attached (chromium: {session.chromium or 'playwright default'})", flush=True)

    state = ControlState(session, run_dir=run_dir, persona=args.persona, game=game)
    if args.start_campaign:
        observation = session.new_campaign(seed=args.seed, team_index=args.team_index)
        state.record(observation)
        print(
            f"campaign started (seed {args.seed}): "
            f"{'ok' if observation.ok else 'FAILED — ' + observation.message}",
            flush=True,
        )

    brief = "" if args.persona == "freeform" else get_persona(args.persona).brief()
    (run_dir / "session.json").write_text(
        json.dumps(
            {
                "persona": args.persona,
                "control_port": control_port,
                "game_url": game.url,
                "run_dir": str(run_dir),
                "seed": args.seed,
                "brief": brief,
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    print(f"control plane on http://127.0.0.1:{control_port} — run_dir {run_dir}", flush=True)
    print("ready", flush=True)
    try:
        serve(state, control_port)
    finally:
        session.close()
        game.stop()
        print("session closed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
