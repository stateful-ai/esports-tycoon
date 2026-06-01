"""Headless slice runner CLI: play a week and write the recap artifact.

    python -m esports_tycoon.runner [options]

Runs practice → match → fallout against the canned save in templated mode and
writes ``runs/<slice_id>/recap.md`` + ``feed.snapshot.html``. This is the
no-browser path — handy for scripting, CI, and proving the determinism contract
(re-run with the same seed and the artifacts are byte-identical).

    python -m esports_tycoon.runner --seed 6 --practice defaults \\
        --team-talk "no heroes. run the default." \\
        --fallout "week 6: held the line. on to week 7."
"""

from __future__ import annotations

import argparse
from typing import get_args

from esports_tycoon.canned import loader
from esports_tycoon.runner.engine import run_slice
from esports_tycoon.runner.model import TRAINING_DRILLS, SliceConfig, SliceDecisions, training_decision_for_drill
from esports_tycoon.runner.recap import write_artifacts
from esports_tycoon.schema import PracticeFocus, TacticalStance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon.runner", description=__doc__)
    parser.add_argument("--save", default=str(loader.DEFAULT_SAVE_PATH), help="path to the canned save YAML")
    parser.add_argument("--seed", type=int, default=6, help="match seed (default: 6)")
    parser.add_argument("--opponent", default="apex_foundry", help="rival org id for the week-6 fixture")
    parser.add_argument("--map", default="Helix", help="map being played (default: Helix)")
    parser.add_argument(
        "--stance", choices=list(get_args(TacticalStance)), default="default", help="the captain's tactical stance"
    )
    parser.add_argument(
        "--practice",
        choices=list(get_args(PracticeFocus)),
        default="defaults",
        help="the MC decision: what the practice block drills",
    )
    parser.add_argument(
        "--training-drill",
        choices=[drill.value for drill in TRAINING_DRILLS],
        default="none",
        help="optional focused training drill to spend this week's training points",
    )
    parser.add_argument("--team-talk", default="", help="open-text #1: private pre-match line (<=120 chars)")
    parser.add_argument("--fallout", default="", help="open-text #2: public post-match Chirper post (<=120 chars)")
    parser.add_argument("--runs-dir", default="runs", help="where to write runs/<slice_id>/ (default: runs)")
    args = parser.parse_args(argv)

    world = loader.load(args.save)
    config = SliceConfig(opponent=args.opponent, map=args.map, seed=args.seed, tactical_stance=args.stance)
    training_points, decision_effects = training_decision_for_drill(args.training_drill)
    try:
        decisions = SliceDecisions(
            practice_focus=args.practice,
            team_talk=args.team_talk,
            fallout_post=args.fallout,
            training_points=training_points,
            decision_effects=decision_effects,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    result = run_slice(world, config, decisions)
    recap_path, feed_path, events_path = write_artifacts(result, world, args.runs_dir)

    ovc, opp = result.scoreline
    opponent = next((r.name for r in world.rivals if r.id == config.opponent), config.opponent)
    verdict = "won" if result.won else "lost"
    print(f"slice {result.slice_id}: {world.save.team.name} {verdict} {ovc}–{opp} vs {opponent} on {config.map}")
    print(f"  events: {events_path}")
    print(f"  recap : {recap_path}")
    print(f"  feed  : {feed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
