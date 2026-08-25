"""Set up synthetic-player sessions and print the brief each agent plays under.

    python scripts/run_synthetic_players.py --list
    python scripts/run_synthetic_players.py --persona first-timer --brief
    python scripts/run_synthetic_players.py --persona first-timer --start

`--start` launches a daemon for that persona in the background and waits until
it is ready, then prints the exact commands the agent should run. It does not
play the game: the *player* is a language model, and this only builds it a body
and hands it a character sheet.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from esports_sim.playtest.findings import AREAS, SEVERITIES  # noqa: E402
from esports_sim.playtest.personas import PERSONAS, persona as get_persona  # noqa: E402

DEFAULT_ROOT = REPO_ROOT / "runs" / "synthetic-players"

HOW_TO_PLAY = """\
HOW TO PLAY

You drive a real browser showing the real game. Every command prints a text
digest of the screen AND writes a screenshot. Read the screenshot — look at it,
do not just trust the digest. Half of what you are here to judge (layout,
hierarchy, whether a number is legible, whether a screen feels dead) is only
visible in the picture.

  python scripts/play.py --persona {persona} look
  python scripts/play.py --persona {persona} tab club
  python scripts/play.py --persona {persona} subtab "Development"
  python scripts/play.py --persona {persona} click "Advance Week"
  python scripts/play.py --persona {persona} profile <player-id>
  python scripts/play.py --persona {persona} close
  python scripts/play.py --persona {persona} advance --weeks 1
  python scripts/play.py --persona {persona} api /api/state      # cross-check only
  python scripts/play.py --persona {persona} errors              # console/network errors
  python scripts/play.py --persona {persona} stop                # when you are done

File what you notice, as you notice it:

  python scripts/play.py --persona {persona} note <severity> <area> "<short title>" \\
      --detail "what happened, and why it matters to a player" \\
      --repro "the clicks that get a maintainer to the same place"

  severity: {severities}
  area:     {areas}

RULES
  1. Play in character. Your brief is above; do not drift into being a QA bot
     if you are the first-timer, or into being charitable if you are the
     stress-tester.
  2. Look at the screenshots. A finding you could have made without looking is
     a finding the existing test suite already covers.
  3. Only report what you actually saw. No speculation, no "presumably".
     Every finding needs a repro someone else can follow.
  4. A finding is about the player's experience. "This field is unlabelled" is
     a finding; "this function is badly named" is not — you cannot see the code.
  5. `praise` is a real severity. What works is as useful to know as what does not.
  6. If something blocks you, file it as a blocker and route around it. Do not
     stop playing.
"""


def _brief_for(persona_id: str) -> str:
    subject = get_persona(persona_id)
    return (
        subject.brief()
        + "\n\n"
        + HOW_TO_PLAY.format(
            persona=persona_id,
            severities="|".join(SEVERITIES),
            areas="|".join(AREAS),
        )
    )


def _start(persona_id: str, seed: int, timeout: float) -> dict:
    run_dir = DEFAULT_ROOT / persona_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "daemon.log"
    with log.open("wb") as handle:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable, str(REPO_ROOT / "scripts/playtest_daemon.py"),
                "--persona", persona_id, "--seed", str(seed), "--start-campaign",
            ],
            cwd=str(REPO_ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists() and "ready" in log.read_text(encoding="utf-8", errors="replace"):
            return json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
        time.sleep(1.0)
    raise SystemExit(
        f"session for {persona_id} did not become ready within {timeout:.0f}s; see {log}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--persona", default=None, choices=[p.id for p in PERSONAS])
    parser.add_argument("--list", action="store_true", help="list the personas and stop")
    parser.add_argument("--brief", action="store_true", help="print the agent brief and stop")
    parser.add_argument("--start", action="store_true", help="launch the session for --persona")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    if args.list or not (args.persona or args.brief or args.start):
        width = max(len(p.id) for p in PERSONAS)
        print("synthetic players:")
        for subject in PERSONAS:
            print(f"  {subject.id.ljust(width)}  {subject.name} — {subject.weeks} weeks")
        print("\n--brief <id> prints the instructions; --start <id> launches its session.")
        return 0

    if args.persona is None:
        parser.error("--brief and --start need --persona")

    if args.start:
        info = _start(args.persona, args.seed, args.timeout)
        print(f"session ready for {args.persona}: control port {info['control_port']}, "
              f"game {info['game_url']}, run_dir {info['run_dir']}")
        print()
    print(_brief_for(args.persona))
    return 0


if __name__ == "__main__":
    sys.exit(main())
