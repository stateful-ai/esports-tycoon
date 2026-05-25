"""Command line entry point for esports-tycoon.

    python -m esports_tycoon inspect            # load the canned save, print a summary
    python -m esports_tycoon resolve <cite-id>  # resolve a cite ID to its memory entry

Both commands load the packaged canned save through the typed loader, so they
double as a smoke test that the schema still matches the canned save. The
cast-lock gate has its own CLI (``python -m esports_tycoon.cast_lock``).
"""

from __future__ import annotations

import argparse

from esports_tycoon import __version__
from esports_tycoon.canned import loader
from esports_tycoon.schema import WorldState


def _print_summary(world: WorldState) -> None:
    save = world.save
    standing = save.team.standing
    print(f"{save.title}  [{save.game}, {save.tone}]")
    print(
        f"  {save.team.name} ({save.team.tag}): {standing.wins}-{standing.losses}, "
        f"{standing.place} of {standing.of}; "
        f"week {save.season.current_week} of {save.season.total_weeks}"
    )
    print(f"  starters ({len(world.players)}):")
    for player in world.players:
        print(f"    - {player.name:<26} {player.role.value:<11} ({len(player.memory_log)} memories)")
    print(f"  clash pairs    : {len(world.clash_pairs)}")
    print(f"  rival orgs     : {len(world.rivals)}")
    print(f"  memory entries : {len(world.memory_ids)} (all cite IDs unique and resolvable)")
    lw = world.last_week
    print(
        f"  last week      : wk{lw.week} vs {lw.opponent} "
        f"{lw.scoreline.overcast}-{lw.scoreline.opponent} ({lw.result}); "
        f"{len(lw.chirper_feed)} Chirper posts"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon", description=__doc__)
    parser.add_argument("--version", action="version", version=f"esports-tycoon {__version__}")
    parser.add_argument("--save", default=str(loader.DEFAULT_SAVE_PATH), help="path to the canned save YAML")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("inspect", help="load the canned save into a typed WorldState and print a summary")
    resolve = sub.add_parser("resolve", help="resolve a cite ID (mem:<player>:<event>) to its memory entry")
    resolve.add_argument("cite", help="the memory ID to resolve")

    args = parser.parse_args(argv)
    world = loader.load(args.save)

    command = args.command or "inspect"
    if command == "inspect":
        _print_summary(world)
        return 0
    if command == "resolve":
        entry = world.resolve_cite(args.cite)
        if entry is None:
            print(f"unresolved cite: {args.cite!r} is not in the memory log")
            return 1
        print(f"{entry.id}")
        print(f"  week {entry.week} day {entry.day}  [{entry.kind}, {entry.sentiment}]")
        print(f"  actors: {', '.join(entry.actors)}")
        print(f"  {entry.summary}")
        if entry.tags:
            print(f"  tags: {', '.join(entry.tags)}")
        return 0

    parser.error(f"unknown command {command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
