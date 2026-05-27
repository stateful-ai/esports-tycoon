"""Command line entry point for esports-tycoon.

    python -m esports_tycoon inspect              # load the canned save, print a summary
    python -m esports_tycoon resolve <cite-id>    # resolve a cite ID to its memory entry
    python -m esports_tycoon validate-save <path> # schema-check a save; print 'OK' or the first error
    python -m esports_tycoon play                 # launch the local slice web app

``inspect``, ``resolve``, and ``validate-save`` load a save through the typed
loader, so they double as a smoke test that the schema still matches a given
save. ``validate-save`` is the read-only "did I break it?" check authors of
hand-edited saves reach for: it surfaces the first :class:`loader.SaveError`
as a one-line ``<field_path>: <message>`` and exits non-zero, or prints ``OK``
and exits zero. ``play`` starts the Flask slice app on ``127.0.0.1`` (the
headless runner is ``python -m esports_tycoon.runner``; the cast-lock gate is
``python -m esports_tycoon.cast_lock``).
"""

from __future__ import annotations

import argparse

from esports_tycoon import __version__
from esports_tycoon.canned import loader
from esports_tycoon.schema import WorldState


def web_default_port() -> int:
    """The web app's default bind port — single source of truth in the web module.

    Imported lazily so this core CLI stays Flask-free for ``inspect``/``resolve``.
    """
    from esports_tycoon.web.__main__ import DEFAULT_PORT

    return DEFAULT_PORT


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
    validate = sub.add_parser(
        "validate-save",
        help="schema-check a save file; print 'OK' or '<field_path>: <message>' and exit non-zero",
    )
    validate.add_argument(
        "save_path",
        nargs="?",
        default=None,
        help="path to the save YAML (default: --save / the packaged canned save)",
    )
    play = sub.add_parser("play", help="launch the local slice web app on 127.0.0.1")
    play.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    play.add_argument(
        "--port", type=int, default=web_default_port(),
        help=f"bind port (default: {web_default_port()})",
    )

    args = parser.parse_args(argv)

    if args.command == "play":
        # Lazy import: the web app pulls in Flask (an opt-in extra), so the core
        # CLI stays importable without it.
        from esports_tycoon.web.__main__ import main as web_main

        return web_main(["--host", args.host, "--port", str(args.port)])

    if args.command == "validate-save":
        # The positional argument wins over the shared ``--save`` flag so
        # ``python -m esports_tycoon validate-save my.yaml`` reads naturally;
        # falling back to ``--save`` keeps the flag useful (and the default
        # path — the packaged canned save — exercised) for callers that already
        # drive the CLI that way. The loader is the single source of schema
        # truth; every typed ``SaveError`` carries a ``field_path`` plus a
        # single message, which is exactly the one-line shape promised above.
        target = args.save_path if args.save_path is not None else args.save
        try:
            loader.load(target)
        except loader.SaveError as exc:
            print(f"{exc.field_path}: {exc}")
            return 1
        except FileNotFoundError as exc:
            # A typo'd path is the most common author mistake. The loader
            # itself doesn't catch this (the file is read before the YAML
            # parser sees a thing), so surface a clean one-liner with the same
            # exit code as any other validation failure.
            print(f"<path>: {exc}")
            return 1
        print("OK")
        return 0

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
