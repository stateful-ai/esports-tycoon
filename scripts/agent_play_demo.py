"""Scripted multi-agent shared world, end to end (docs/agent-play.md).

Usage:
    python scripts/agent_play_demo.py [--seed 42] [--agents 3] [--weeks 4] [--pack vct-2026]

Runs N scripted agents in one shared sandbox world through the in-process
AgentWorld surface: each week every seat makes a couple of legal decisions
picked straight off its legal_actions contract, then votes advance; the week
resolves on the last vote and each seat's digest is printed. Ends with the
league tables and each seat's championship objective. ASCII-only output.

This is executable documentation for harness authors: the same observe/act
loop over HTTP is one `X-Esports-Sid` header away (see docs/agent-play.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from esports_sim.manager.agent_play import AgentWorld, InvalidManagerAction
from esports_sim.registry import load_all


def scripted_turn(world: AgentWorld, team_id: str, week_index: int) -> list[str]:
    """A tiny deterministic policy: read legal_actions, take up to two
    grounded decisions, resolve any pending event, then vote advance."""
    lines: list[str] = []
    obs = world.observe(team_id)
    legal = obs["legal_actions"]

    focus_options = legal["set_training"]["options"]
    focus = focus_options[week_index % len(focus_options)]
    r = world.act(team_id, {"kind": "set_training", "params": {"focus": focus}})
    lines.append(f"  {team_id}: set_training({focus}) -> {r['message']}")

    if legal["set_scout"]["enabled"]:
        targets = legal["set_scout"]["targets"]
        target = targets[week_index % len(targets)]
        r = world.act(team_id, {"kind": "set_scout", "params": {"target": target}})
        lines.append(f"  {team_id}: set_scout -> {r['message']}")

    # Event choices come only from a fresh manager observation. A prior
    # decision may change the next event, so refresh before each action.
    for kind, label in (("resolve_flavor", "flavor event"), ("resolve_media", "media decision")):
        event = world.observe(team_id)["legal_actions"][kind]
        if event["enabled"]:
            world.act(team_id, {
                "kind": kind,
                "params": {"event_id": event["event_id"], "choice_id": event["choice_ids"][0]},
            })
            lines.append(f"  {team_id}: resolved {label} {event['event_id']}")

    vote = world.act(team_id, {"kind": "advance", "params": {}})
    if vote["advanced"]:
        lines.append(f"  {team_id}: advance -> WEEK RESOLVED")
    else:
        lines.append(
            f"  {team_id}: advance -> waiting on {', '.join(vote['waiting_on'])}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="scripted multi-agent world demo")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agents", type=int, default=3)
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--pack", default=None, help="roster pack id (e.g. vct-2026)")
    args = parser.parse_args()

    gd = load_all()
    world = AgentWorld.create(
        gd, seed=args.seed, n_teams=args.agents, pack_id=args.pack
    )
    print(f"world: seed {args.seed}, seats: {', '.join(world.team_ids)}")

    for week_index in range(args.weeks):
        week = world.gs.week
        print(f"week {week} (season {world.gs.season}):")
        for team_id in world.team_ids:
            try:
                for line in scripted_turn(world, team_id, week_index):
                    print(line)
            except InvalidManagerAction as exc:
                print(f"  {team_id}: action rejected -> {exc}")
        for team_id in world.team_ids:
            digest = world.last_tick.get(team_id)
            if digest is None:
                continue
            for row in digest["results"]:
                score = "-".join(str(s) for s in row["score"])
                outcome = "W" if row["won"] else "L"
                print(
                    f"    {team_id} {outcome} {score} vs {row['opponent_name']}"
                    f" ({row['stage']})"
                )
            pos = digest["position"]
            print(
                f"    {team_id}: {pos['region']} P{pos['position']}/{pos['teams']}"
                f", reward {digest['reward']:+.3f}"
            )

    print("league:")
    league = world.league()
    for region, rows in sorted(league["regions"].items()):
        print(f"  {region}:")
        for row in rows:
            seat = " *" if row["human"] else ""
            print(
                f"    {row['position']:>2}. {row['team_name']}"
                f" {row['wins']}-{row['losses']} ({row['round_diff']:+d}){seat}"
            )
    print("objectives:")
    for team_id in world.team_ids:
        objective = world.objective(team_id)
        titles = objective["titles"]
        print(
            f"  {team_id}: titles {titles['total']}"
            f" (champions {titles['champions']}, masters {titles['masters']},"
            f" regional {titles['regional']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
