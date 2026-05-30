"""Command line entry point for esports-tycoon.

    python -m esports_tycoon inspect                # load the canned save, print a summary
    python -m esports_tycoon resolve <cite-id>      # resolve a cite ID to its memory entry
    python -m esports_tycoon validate-save <path>   # schema-check a save; print 'OK' or the first error
    python -m esports_tycoon roster show <save>     # print the current roster from a save
    python -m esports_tycoon roster export <save>   # emit the current roster as csv or json
    python -m esports_tycoon play                   # launch the local slice web app

``inspect``, ``resolve``, ``validate-save``, ``roster show``, and ``roster
export`` load a save through the typed loader, so they double as a smoke test
that the schema still matches a given save. ``validate-save`` is the read-only
"did I break it?" check authors of hand-edited saves reach for: on success it
prints ``OK`` and exits 0; on failure it prints a one-line ``<field_path>:
<message>`` (the first typed :class:`loader.SaveError`) and exits 1. The default
check covers YAML well-formedness, ``schema_version`` compatibility, and the
typed schema. ``--strict`` additionally runs the cross-entity
referential-integrity gate — every relationship, clash, opponent and chirper
reply must resolve to an entity defined in the same save. ``roster show`` is the
read-only roster printer: one row per starter on the managed team with id, role,
name, handle, age, signature operative, and traits — no sim advance, no
mutation. ``roster export`` is its machine-facing twin: the same starters in the
same order, emitted as ``csv`` (default) or ``json`` to ``--out`` or stdout, for
piping into a spreadsheet, a JSON-consuming tool, or a diff. ``play`` starts the
Flask slice app on ``127.0.0.1`` (the headless runner is ``python -m
esports_tycoon.runner``; the cast-lock gate is ``python -m
esports_tycoon.cast_lock``).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Sequence

import yaml
from pydantic import ValidationError

from esports_tycoon import __version__
from esports_tycoon.canned import loader
from esports_tycoon.schema import Player, WorldState

# Column order for ``roster export``. Pinned so the CSV header and the JSON
# record key order match the schema's natural read — id first (the stable
# handle a downstream tool joins on), then name/handle/role/age/signature
# operative, then traits last (the variable-length attributes list). Kept in
# one place so a future column addition lands in both formats together; the
# human-facing ``roster show`` deliberately uses its own column order
# (alignment first, then human-skim order), so the two surfaces can evolve
# independently.
_ROSTER_EXPORT_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "handle",
    "role",
    "age",
    "signature_operative",
    "traits",
)

# CSV joiner for the ``traits`` list. ``,`` is reserved for CSV cell
# separation, so a list-valued cell needs an unambiguous inner delimiter; ``|``
# is the conventional choice (no canned-save trait contains one) and survives
# a round-trip through ``str.split("|")`` cleanly. JSON keeps the list shape
# native, so this only affects CSV output.
_TRAITS_CSV_DELIM = "|"


def web_default_port() -> int:
    """The web app's default bind port — single source of truth in the web module.

    Imported lazily so this core CLI stays Flask-free for ``inspect``/``resolve``.
    """
    from esports_tycoon.web.__main__ import DEFAULT_PORT

    return DEFAULT_PORT


def _roster_record(player: Player) -> dict[str, object]:
    """Project one :class:`Player` to the export's flat record shape.

    Returns a dict keyed by :data:`_ROSTER_EXPORT_FIELDS` in order: native
    types throughout (``traits`` stays a list, ``role`` becomes the enum's
    string value), so the JSON writer can dump straight through and the CSV
    writer only flattens the list field. Centralised so both formats and the
    tests share one definition of "what a roster row contains" — adding a
    column is a one-line edit here plus a tuple bump above, not a per-format
    sync.
    """
    return {
        "id": player.id,
        "name": player.name,
        "handle": player.handle,
        "role": player.role.value,
        "age": player.age,
        "signature_operative": player.signature_operative,
        "traits": list(player.traits),
    }


def _format_roster_csv(roster: Sequence[Player]) -> str:
    """Render the roster as CSV with a header row.

    ``traits`` is joined on :data:`_TRAITS_CSV_DELIM` so the cell stays a
    single field even when the player has multiple traits. ``csv.writer``
    handles quoting for any value that contains the dialect's delimiter or a
    newline, so a name with a comma in it still round-trips through
    ``csv.reader``. ``lineterminator="\\n"`` keeps the output platform-stable
    (the same bytes on Linux, macOS, and Windows) so a golden-bytes test
    stays honest.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_ROSTER_EXPORT_FIELDS)
    for player in roster:
        record = _roster_record(player)
        traits_cell = _TRAITS_CSV_DELIM.join(record["traits"])  # type: ignore[arg-type]
        row = [
            traits_cell if field == "traits" else record[field]
            for field in _ROSTER_EXPORT_FIELDS
        ]
        writer.writerow(row)
    return buf.getvalue()


def _format_roster_json(roster: Sequence[Player]) -> str:
    """Render the roster as a pretty-printed JSON array of records.

    ``indent=2`` plus a trailing newline matches the house convention (the
    recap JSON artefacts use the same shape), so a downstream diff stays
    readable and the file ends in a newline the way well-mannered POSIX
    tools expect. ``traits`` stays a native list in JSON — the CSV-only
    ``|`` join would be a lossy choice here.
    """
    records = [_roster_record(player) for player in roster]
    return json.dumps(records, indent=2) + "\n"


def _print_roster(world: WorldState) -> None:
    """Print one row per starter on the managed team.

    Reads ``world.roster`` (the schema property that names the managed team's
    starters in save order — see :class:`esports_tycoon.schema.WorldState`),
    so this stays in lockstep with the resolver's "who is on the team" view
    rather than reaching for the bare ``players`` list. No sim advance, no
    mutation — purely a read of the loaded world.

    Header names the managed team and the roster size; each row carries the
    player id, role, name, handle, age, signature operative, and the
    comma-joined traits — the fields a manager actually wants when checking a
    save's current state. Column widths are computed from the roster so a
    longer/shorter cast still aligns; an empty traits list renders as ``-`` so
    the column is never blank without it being a load-time bug.
    """
    team = world.team
    roster = world.roster
    print(f"{team.name} ({team.tag}) — roster ({len(roster)}):")
    if not roster:
        return
    id_w = max(len(p.id) for p in roster)
    role_w = max(len(p.role.value) for p in roster)
    name_w = max(len(p.name) for p in roster)
    handle_w = max(len(p.handle) for p in roster)
    sig_w = max(len(p.signature_operative) for p in roster)
    for player in roster:
        traits = ", ".join(player.traits) if player.traits else "-"
        print(
            f"  {player.id:<{id_w}}  "
            f"{player.role.value:<{role_w}}  "
            f"{player.name:<{name_w}}  "
            f"{player.handle:<{handle_w}}  "
            f"age {player.age:>2}  "
            f"{player.signature_operative:<{sig_w}}  "
            f"traits: {traits}"
        )


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


def _validate_save_path(path, *, strict: bool) -> WorldState:
    """Run the same load-time contracts ``loader.load`` runs, gated by ``strict``.

    Mirrors :func:`esports_tycoon.canned.loader.load` (YAML parse -> version
    gate -> typed-schema validate) but only runs the cross-entity referential
    integrity gate when ``strict`` is true, so the non-strict CLI mode is
    strictly shape-only. Every failure still surfaces as the same typed
    :class:`loader.SaveError` subclass the loader raises, so callers — and
    the ``validate-save`` handler below — read one contract for both modes.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise loader.SaveYamlError(
            f"{path}: save is not a valid YAML document: {exc}",
            field_path="<yaml>",
            source=path,
        ) from exc
    if not isinstance(data, dict):
        raise loader.SaveSchemaError(
            f"{path}: expected a mapping at the top level, got {type(data).__name__}",
            field_path="<root>",
            source=path,
        )
    data = loader._ensure_loadable_version(data, path)
    try:
        world = WorldState.model_validate(data)
    except ValidationError as exc:
        raise loader.SaveSchemaError(
            f"{path}: save does not match the typed schema: {exc}",
            field_path=loader._field_path_from_validation_error(exc),
            source=path,
            original=exc,
        ) from exc
    if strict:
        loader.check_referential_integrity(world, source=path)
    return world


def main(argv=None) -> int:
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
    validate.add_argument(
        "--strict",
        action="store_true",
        help=(
            "additionally enforce referential integrity: every relationship, "
            "clash, opponent and chirper reply must resolve to an entity "
            "defined in the same save"
        ),
    )
    roster = sub.add_parser(
        "roster",
        help="read-only roster queries against a save (no sim advance, no mutation)",
    )
    roster_sub = roster.add_subparsers(dest="roster_command")
    roster_show = roster_sub.add_parser(
        "show",
        help="print the managed team's current roster (one row per starter)",
    )
    roster_show.add_argument(
        "save_path",
        nargs="?",
        default=None,
        help="path to the save YAML (default: --save / the packaged canned save)",
    )
    roster_export = roster_sub.add_parser(
        "export",
        help="emit the managed team's roster as csv (default) or json to --out or stdout",
    )
    roster_export.add_argument(
        "save_path",
        nargs="?",
        default=None,
        help="path to the save YAML (default: --save / the packaged canned save)",
    )
    roster_export.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="output format (default: csv)",
    )
    roster_export.add_argument(
        "--out",
        default=None,
        help="write to FILE instead of stdout",
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
        # falling back to ``--save`` keeps the flag useful (and the packaged
        # canned save — the default — exercised) for callers that already
        # drive the CLI that way.
        target = args.save_path if args.save_path is not None else args.save
        try:
            _validate_save_path(target, strict=args.strict)
        except FileNotFoundError as exc:
            # A typo'd path is the most common author mistake. Surface a
            # clean one-liner with the same exit code as any other
            # validation failure; the loader doesn't catch this itself (the
            # file is read before the YAML parser sees a thing).
            print(f"<path>: {exc}")
            return 1
        except loader.SaveError as exc:
            print(f"{exc.field_path}: {exc}")
            return 1
        print("OK")
        return 0

    if args.command == "roster":
        # The subcommand only makes sense with a verb attached; ``roster``
        # alone is an authoring mistake, not a default action — print help
        # and exit non-zero rather than silently doing nothing or running
        # the default ``inspect`` against a misread args namespace.
        if args.roster_command is None:
            roster.print_help()
            return 2
        if args.roster_command == "show":
            # The positional path wins over the shared ``--save`` flag so
            # ``roster show my.yaml`` reads naturally; falling back to
            # ``--save`` keeps the flag useful (and the packaged canned save
            # — the default — exercised) for callers that already drive the
            # CLI that way.
            target = args.save_path if args.save_path is not None else args.save
            world = loader.load(target)
            _print_roster(world)
            return 0
        if args.roster_command == "export":
            # Same positional-wins-over-flag shape as ``roster show`` — the
            # two verbs need to be interchangeable on the same save path or
            # one will silently read a different file than the other. The
            # format/out handling is what's new here: ``--format`` selects
            # csv (default) or json; ``--out`` writes to a file rather than
            # stdout, but the bytes are the same either way (see the
            # ``newline=""`` note below for why).
            target = args.save_path if args.save_path is not None else args.save
            world = loader.load(target)
            if args.format == "json":
                output = _format_roster_json(world.roster)
            else:
                output = _format_roster_csv(world.roster)
            if args.out is None:
                # Stdout: the formatter already terminates with a single
                # newline, so ``end=""`` keeps a piped ``> file`` writing
                # the same bytes ``--out`` would.
                print(output, end="")
            else:
                # ``newline=""`` so the CSV writer's own
                # ``lineterminator="\n"`` is what hits disk — otherwise
                # Python's universal-newlines translation would write
                # ``\r\n`` on Windows and the file would drift from the
                # stdout form. JSON is plain text either way.
                Path(args.out).write_text(output, encoding="utf-8", newline="")
            return 0
        parser.error(f"unknown roster subcommand {args.roster_command!r}")
        return 2

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
