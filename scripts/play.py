"""Play the game one command at a time. This is the synthetic player's hands.

Point it at a session started by `scripts/playtest_daemon.py`. Each command
acts on the live browser and prints what the screen looks like afterwards,
including the path to a fresh screenshot — open that image to actually *see*
the game rather than trusting the text.

    python scripts/play.py look
    python scripts/play.py tab club
    python scripts/play.py subtab Squad
    python scripts/play.py click "Advance Week"
    python scripts/play.py advance --weeks 2
    python scripts/play.py profile team_nexus_p0
    python scripts/play.py note blocker club "Squad screen is empty" \\
        --detail "After selling two players the squad table renders no rows." \\
        --repro "Club > Squad, release two players, reopen the tab."
    python scripts/play.py findings

The session is discovered from `runs/synthetic-players/<persona>/session.json`
(`--persona`, or `--port` to address one directly).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from esports_sim.playtest.findings import AREAS, SEVERITIES  # noqa: E402

DEFAULT_ROOT = REPO_ROOT / "runs" / "synthetic-players"


def _discover_port(persona: str | None, run_dir: Path | None) -> int:
    candidates: list[Path] = []
    if run_dir is not None:
        candidates.append(run_dir / "session.json")
    if persona:
        candidates.append(DEFAULT_ROOT / persona / "session.json")
    if not candidates and DEFAULT_ROOT.exists():
        candidates = sorted(
            DEFAULT_ROOT.glob("*/session.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    for path in candidates:
        if path.exists():
            return int(json.loads(path.read_text(encoding="utf-8"))["control_port"])
    raise SystemExit(
        "no live session found — start one with scripts/playtest_daemon.py, "
        "or pass --port"
    )


def _post(port: int, command: str, params: dict[str, object], timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(  # noqa: S310 - localhost only
        f"http://127.0.0.1:{port}/{command}",
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach the session on port {port}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--persona", default=None, help="which session to talk to")
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=0, help="control port, if you know it")
    parser.add_argument("--timeout", type=float, default=300.0)

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("look", help="re-observe the current screen")
    sub.add_parser("close", help="dismiss the topmost overlay")
    sub.add_parser("findings", help="show the findings filed so far")
    sub.add_parser("errors", help="show every console/network error this run")
    sub.add_parser("stop", help="shut the session down")

    new = sub.add_parser("new", help="start a campaign from the lobby")
    new.add_argument("--seed", type=int, default=2026)
    new.add_argument("--team-index", type=int, default=0)

    tab = sub.add_parser("tab", help="open a top-level tab")
    tab.add_argument("tab")

    subtab = sub.add_parser("subtab", help="open a sub-tab by visible label")
    subtab.add_argument("label")

    click = sub.add_parser("click", help="click a control by label or id")
    click.add_argument("label")
    click.add_argument("--nth", type=int, default=0, help="which match, when several fit")

    setter = sub.add_parser("set", help="set an input or select")
    setter.add_argument("selector", help="CSS selector, e.g. #ng-seed")
    setter.add_argument("value")

    profile = sub.add_parser("profile", help="open a player/team/staff profile overlay")
    profile.add_argument("ref", help="the data-pid / data-tid / data-sid value")

    advance = sub.add_parser("advance", help="advance the campaign a week")
    advance.add_argument("--weeks", type=int, default=1)

    api = sub.add_parser("api", help="read a JSON endpoint (for cross-checking only)")
    api.add_argument("path")
    api.add_argument("--limit", type=int, default=4000)

    note = sub.add_parser("note", help="file a finding")
    note.add_argument("severity", choices=SEVERITIES)
    note.add_argument("area", choices=AREAS)
    note.add_argument("title")
    note.add_argument("--detail", required=True, help="what happened and why it matters")
    note.add_argument("--repro", default="", help="the clicks that get a maintainer there")
    note.add_argument("--screenshot", default="", help="defaults to the last screen you saw")
    note.add_argument("--tags", default="", help="comma-separated")

    args = parser.parse_args()
    port = args.port or _discover_port(args.persona, args.run_dir)

    params: dict[str, object] = {}
    if args.command == "new":
        params = {"seed": args.seed, "team_index": args.team_index}
    elif args.command == "tab":
        params = {"tab": args.tab}
    elif args.command == "subtab":
        params = {"label": args.label}
    elif args.command == "click":
        params = {"label": args.label, "nth": args.nth}
    elif args.command == "set":
        params = {"selector": args.selector, "value": args.value}
    elif args.command == "profile":
        params = {"ref": args.ref}
    elif args.command == "advance":
        params = {"weeks": args.weeks}
    elif args.command == "api":
        params = {"path": args.path, "limit": args.limit}
    elif args.command == "note":
        params = {
            "severity": args.severity,
            "area": args.area,
            "title": args.title,
            "detail": args.detail,
            "repro": args.repro,
            "screenshot": args.screenshot,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
        }

    status, body = _post(port, args.command, params, args.timeout)
    print(body)
    return 0 if status < 400 else 1


if __name__ == "__main__":
    sys.exit(main())
