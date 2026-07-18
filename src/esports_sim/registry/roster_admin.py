"""Admin data-correction: edit a real player/team's compact `src/*.yaml`
sheet in a roster pack and rebuild the pack from it.

This is the disk-writing half of the web admin-edit toggle (see
`web/server.py`'s `/api/admin/*` routes). It never touches a live
`GameState` — the caller is responsible for copying the returned "fresh"
identity fields onto the matching live `Player`/`Team` if a campaign has one
loaded, while leaving campaign-managed fields (salary, contract, morale,
stamina, form, confidence, balance, reputation, fan_count, ...) alone: those
evolve through play and a data correction must not reset them.

Only entries that actually originate from a pack's `src/` sheets are
editable here — generated fill teams/players (topped up at new-game time)
have no sheet to correct and are reported as not editable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from esports_sim.registry.loader import DEFAULT_DATA_DIR, GameData
from esports_sim.registry.roster_pack_builder import build, expand_player, slugify
from esports_sim.schemas.common import Playstyle, Region, Role

PLAYER_EDITABLE_FIELDS = (
    "handle", "real_name", "age", "country", "languages",
    "role", "playstyle", "quality", "agents",
)
# Deliberately NOT editable here: `igl` (captaincy). Flipping it cascades to
# a SECOND player on the team (the old captain) plus the live team's
# captain_id, which this single-player edit endpoint has no clean way to
# sync — fix captaincy directly on the src sheet + rebuild instead.
TEAM_EDITABLE_FIELDS = ("name", "tag", "tier", "prestige")


class RosterEditError(ValueError):
    """A rejected edit — bad field, bad value, or a structural violation the
    rebuild would hit (e.g. two IGLs). Message is safe to show the admin."""


@dataclass
class _PlayerLoc:
    pack_dir: Path
    src_file: Path
    doc: dict           # the parsed src file (region sheet or free_agents.yaml)
    is_free_agent: bool
    team_spec: dict | None  # None for free agents
    player_spec: dict
    region: str
    team_slug: str | None  # None for free agents


@dataclass
class _TeamLoc:
    pack_dir: Path
    src_file: Path
    doc: dict
    team_spec: dict
    region: str


def _pack_dir(pack_id: str, data_dir: Path | None = None) -> Path:
    return (data_dir or DEFAULT_DATA_DIR) / "rosters" / pack_id


def _region_specs(pack_dir: Path) -> list[Path]:
    """Return only team-region source sheets, excluding market/prospect input."""
    non_region_sources = {
        "free_agents.yaml",
        "future_prospects.yaml",
        "future_archive_free_agents.yaml",
        "future_archive_prospects.yaml",
        "future_2026_backfill_free_agents.yaml",
        "future_2026_backfill_prospects.yaml",
        "career_profiles.yaml",
        "pack.yaml",
    }
    return sorted(
        f for f in (pack_dir / "src").glob("*.yaml")
        if f.name not in non_region_sources
    )


def find_player(
    pack_id: str, player_id: str, data_dir: Path | None = None
) -> _PlayerLoc | None:
    """Locate the src spec behind a pack player id, or None if this player
    isn't sheet-sourced (a generated fill/prospect)."""
    pack_dir = _pack_dir(pack_id, data_dir)
    for spec_file in _region_specs(pack_dir):
        doc = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        region = str(Region(doc["region"]))
        for tspec in doc.get("teams", []):
            slug = "team_" + slugify(str(tspec["name"]))
            for pspec in tspec.get("players", []):
                pid = f"{slug}_{slugify(str(pspec['handle']))}"
                if pid == player_id:
                    return _PlayerLoc(
                        pack_dir=pack_dir, src_file=spec_file, doc=doc,
                        is_free_agent=False, team_spec=tspec,
                        player_spec=pspec, region=region, team_slug=slug,
                    )
    for fa_file in sorted((pack_dir / "src").glob("*free_agents.yaml")):
        doc = yaml.safe_load(fa_file.read_text(encoding="utf-8")) or {}
        for pspec in doc.get("free_agents", []):
            region = str(Region(pspec["region"]))
            pid = "fa_" + slugify(str(pspec["handle"]))
            if pid == player_id:
                return _PlayerLoc(
                    pack_dir=pack_dir, src_file=fa_file, doc=doc,
                    is_free_agent=True, team_spec=None,
                    player_spec=pspec, region=region, team_slug=None,
                )
    return None


def find_team(
    pack_id: str, team_id: str, data_dir: Path | None = None
) -> _TeamLoc | None:
    pack_dir = _pack_dir(pack_id, data_dir)
    for spec_file in _region_specs(pack_dir):
        doc = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        region = str(Region(doc["region"]))
        for tspec in doc.get("teams", []):
            slug = "team_" + slugify(str(tspec["name"]))
            if slug == team_id:
                return _TeamLoc(
                    pack_dir=pack_dir, src_file=spec_file, doc=doc,
                    team_spec=tspec, region=region,
                )
    return None


def _validate_player_edits(gd: GameData, edits: dict) -> None:
    unknown = set(edits) - set(PLAYER_EDITABLE_FIELDS)
    if unknown:
        raise RosterEditError(f"not editable: {sorted(unknown)}")
    if "role" in edits:
        try:
            Role(edits["role"])
        except ValueError:
            raise RosterEditError(f"unknown role {edits['role']!r}") from None
    if "playstyle" in edits:
        try:
            Playstyle(edits["playstyle"])
        except ValueError:
            raise RosterEditError(
                f"unknown playstyle {edits['playstyle']!r}"
            ) from None
    if "age" in edits and not (14 <= int(edits["age"]) <= 45):
        raise RosterEditError("age must be between 14 and 45")
    if "quality" in edits and not (1 <= float(edits["quality"]) <= 99):
        raise RosterEditError("quality must be between 1 and 99")
    if "agents" in edits:
        agents = edits["agents"]
        if not isinstance(agents, list) or len(agents) > 3:
            raise RosterEditError("agents must be a list of at most 3 ids")
        for a in agents:
            if str(a) not in gd.agents:
                raise RosterEditError(f"unknown agent id {a!r}")
    if "languages" in edits:
        langs = edits["languages"]
        if not isinstance(langs, list) or len(langs) > 3:
            raise RosterEditError("languages must be a list of at most 3")
        for entry in langs:
            if "lang" not in entry:
                raise RosterEditError("each language needs a 'lang' code")
    for text_field in ("handle", "real_name", "country"):
        if text_field in edits:
            try:
                str(edits[text_field]).encode("ascii")
            except UnicodeEncodeError:
                raise RosterEditError(
                    f"{text_field} must be ASCII"
                ) from None


def _validate_team_edits(edits: dict) -> None:
    unknown = set(edits) - set(TEAM_EDITABLE_FIELDS)
    if unknown:
        raise RosterEditError(f"not editable: {sorted(unknown)}")
    if "tier" in edits and int(edits["tier"]) not in (1, 2):
        raise RosterEditError("tier must be 1 or 2")
    if "prestige" in edits and not (1 <= float(edits["prestige"]) <= 99):
        raise RosterEditError("prestige must be between 1 and 99")
    if "name" in edits:
        try:
            str(edits["name"]).encode("ascii")
        except UnicodeEncodeError:
            raise RosterEditError("name must be ASCII") from None
    if "tag" in edits:
        try:
            str(edits["tag"]).encode("ascii")
        except UnicodeEncodeError:
            raise RosterEditError("tag must be ASCII") from None


def _is_flat(x: object) -> bool:
    """A dict with only scalar values, or a non-collection — the kind of
    value the src sheets author inline (`agents: [jett, raze]`,
    `languages: [{lang: en, level: 90}]`)."""
    if isinstance(x, dict):
        return all(not isinstance(v, (list, dict)) for v in x.values())
    return not isinstance(x, (list, dict))


class _SrcDumper(yaml.SafeDumper):
    """Matches the src sheets' hand-authored style: block sequences indent
    under their parent key (PyYAML's default doesn't)."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _represent_list(dumper: yaml.SafeDumper, data: list):
    # Flat lists (scalars, or dicts of scalars — `agents`, `languages`)
    # inline as flow style; nested team/player structures stay block, same
    # split the hand-authored sheets already use.
    flow = all(_is_flat(x) for x in data) if data else True
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_SrcDumper.add_representer(list, _represent_list)


def _dump(path: Path, doc: dict) -> None:
    # yaml round-tripping through safe_load/safe_dump always drops comments —
    # preserve the sheet's leading `# ...` header (sourcing notes) verbatim.
    header = ""
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            if line.startswith("#"):
                header += line
            else:
                break
    body = yaml.dump(doc, Dumper=_SrcDumper, sort_keys=False, width=88)
    path.write_text(header + body, encoding="ascii")


def edit_player(
    gd: GameData, pack_id: str, player_id: str, edits: dict,
    data_dir: Path | None = None,
) -> dict:
    """Apply `edits` (a subset of PLAYER_EDITABLE_FIELDS) to the player's src
    sheet, rebuild the pack, and return the freshly-expanded player dict
    (attributes/agent_pool/map_pool/potential/...) keyed by the SAME player
    id — for the caller to copy identity fields onto a live save. Raises
    RosterEditError on a bad edit (nothing is written)."""
    loc = find_player(pack_id, player_id, data_dir)
    if loc is None:
        raise RosterEditError(
            f"{player_id!r} has no roster-pack sheet entry (generated fill "
            "player, or not from this pack) — not editable"
        )
    _validate_player_edits(gd, edits)

    spec = loc.player_spec
    original = loc.src_file.read_text(encoding="utf-8")
    try:
        for k, v in edits.items():
            spec[k] = v
        _dump(loc.src_file, loc.doc)
        build(pack_id, data_dir)
    except (Exception, SystemExit) as e:  # build() raises SystemExit on a bad sheet
        loc.src_file.write_text(original, encoding="ascii")
        raise RosterEditError(f"rebuild failed, edit rolled back: {e}") from e
    # Regenerate this one player's full sheet under its OWN id (unaffected by
    # any id a rebuilt-from-scratch campaign would assign a renamed handle),
    # so a live save keyed by the old id can be patched consistently.
    merged_spec = dict(spec)
    return expand_player(
        pack_id, player_id, merged_spec, loc.region, gd,
        loc.team_slug or "fa",
    )


def edit_team(
    pack_id: str, team_id: str, edits: dict, data_dir: Path | None = None
) -> None:
    """Apply `edits` (a subset of TEAM_EDITABLE_FIELDS) to a team's src entry
    and rebuild the pack. Renaming a team changes the SLUG (and therefore the
    id/player-ids) a future new campaign built from this pack will assign;
    the current live save's ids are untouched — only `.name`/`.tag` on the
    live Team should be patched by the caller."""
    loc = find_team(pack_id, team_id, data_dir)
    if loc is None:
        raise RosterEditError(
            f"{team_id!r} has no roster-pack sheet entry (generated fill "
            "team, or not from this pack) — not editable"
        )
    _validate_team_edits(edits)
    original = loc.src_file.read_text(encoding="utf-8")
    try:
        for k, v in edits.items():
            loc.team_spec[k] = v
        _dump(loc.src_file, loc.doc)
        build(pack_id, data_dir)
    except (Exception, SystemExit) as e:  # build() raises SystemExit on a bad sheet
        loc.src_file.write_text(original, encoding="ascii")
        raise RosterEditError(f"rebuild failed, edit rolled back: {e}") from e
