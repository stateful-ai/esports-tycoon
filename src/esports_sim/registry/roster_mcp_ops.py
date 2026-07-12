"""Draft-first operations exposed by the roster-pack MCP server.

MCP tools edit portable roster documents under ``data/rosters/.drafts``.
They never mutate an installed pack until ``install_draft`` is called, so an
agent can assemble an temporarily-invalid five one player at a time.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from esports_sim.registry.loader import DEFAULT_DATA_DIR
from esports_sim.registry.roster_pack_builder import slugify
from esports_sim.registry.roster_workbench import (
    DraftFreeAgent,
    DraftPlayer,
    example_document,
    install_document,
    list_documents,
    load_document,
    parse_document,
    schema_bundle,
    validate_document,
)

_PACK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LOCK = threading.RLock()


class RosterMcpError(ValueError):
    """A safe, actionable error for an MCP tool caller."""


def _draft_root() -> Path:
    override = os.environ.get("ESPORTS_ROSTER_DRAFT_DIR")
    return (
        Path(override).expanduser().resolve()
        if override
        else DEFAULT_DATA_DIR / "rosters" / ".drafts"
    )


def _draft_path(pack_id: str) -> Path:
    if not _PACK_ID_RE.fullmatch(pack_id):
        raise RosterMcpError(
            "pack_id must contain lowercase letters, digits, and single hyphens"
        )
    return _draft_root() / f"{pack_id}.roster-pack.yaml"


def _read(pack_id: str) -> dict[str, Any]:
    path = _draft_path(pack_id)
    if not path.is_file():
        raise RosterMcpError(
            f"no draft {pack_id!r}; call create_draft or open_installed_pack first"
        )
    return parse_document(path.read_text(encoding="utf-8"))


def _write(raw: dict[str, Any], *, overwrite: bool = True) -> Path:
    pack_id = str(raw.get("id", ""))
    path = _draft_path(pack_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise RosterMcpError(
            f"draft {pack_id!r} already exists; pass overwrite=true to replace it"
        )
    text = yaml.safe_dump(raw, sort_keys=False, width=100, allow_unicode=False)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="ascii")
    temp.replace(path)
    return path


def _view(raw: dict[str, Any], changed: dict[str, Any] | None = None) -> dict:
    validation = validate_document(raw)
    return {
        "draft_path": str(_draft_path(str(raw["id"]))),
        "changed": changed,
        "validation": validation,
    }


def _team(raw: dict[str, Any], team_name: str) -> dict[str, Any]:
    wanted = slugify(team_name)
    matches = [
        team for team in raw.get("teams", [])
        if slugify(str(team.get("name", ""))) == wanted
    ]
    if not matches:
        raise RosterMcpError(f"team {team_name!r} is not in draft {raw.get('id')!r}")
    if len(matches) > 1:
        raise RosterMcpError(f"team name {team_name!r} is ambiguous")
    return matches[0]


def _player(rows: list[dict[str, Any]], handle: str, where: str) -> tuple[int, dict]:
    wanted = slugify(handle)
    matches = [
        (index, player) for index, player in enumerate(rows)
        if slugify(str(player.get("handle", ""))) == wanted
    ]
    if not matches:
        raise RosterMcpError(f"player {handle!r} is not in {where}")
    if len(matches) > 1:
        raise RosterMcpError(f"player handle {handle!r} is ambiguous in {where}")
    return matches[0]


def _model_error(exc: ValidationError) -> RosterMcpError:
    first = exc.errors(include_url=False)[0]
    path = ".".join(str(part) for part in first["loc"])
    return RosterMcpError(f"{path or 'player'}: {first['msg']}")


def get_schema() -> dict:
    """Return the portable document schema and all legal game catalog ids."""
    return schema_bundle()


def list_installed_packs() -> dict:
    """List roster packs currently available in the game's Play lobby."""
    return {"packs": list_documents()}


def list_drafts() -> dict:
    """List MCP draft ids without reading their full documents."""
    root = _draft_root()
    ids = []
    if root.is_dir():
        suffix = ".roster-pack.yaml"
        ids = sorted(
            path.name.removesuffix(suffix)
            for path in root.glob(f"*{suffix}")
        )
    return {"draft_root": str(root), "draft_ids": ids}


def create_draft(
    pack_id: str,
    name: str,
    description: str = "",
    league_regions: list[str] | None = None,
    teams_per_region: int = 8,
    tier2_per_region: int = 4,
    template: str = "empty",
    overwrite: bool = False,
) -> dict:
    """Create an empty or example-based portable roster draft."""
    regions = league_regions or ["americas", "emea", "pacific"]
    if template not in {"empty", "example"}:
        raise RosterMcpError("template must be 'empty' or 'example'")
    if template == "example":
        raw = example_document()
        raw.update({"id": pack_id, "name": name, "description": description})
        raw["world"].update({
            "league_regions": regions,
            "teams_per_region": teams_per_region,
            "tier2_per_region": tier2_per_region,
        })
        # Keep the example team inside the caller's first region.
        raw["teams"][0]["region"] = regions[0] if regions else "americas"
    else:
        raw = {
            "schema_version": 1,
            "id": pack_id,
            "name": name,
            "description": description,
            "world": {
                "league_regions": regions,
                "teams_per_region": teams_per_region,
                "tier2_per_region": tier2_per_region,
            },
            "teams": [],
            "free_agents": [],
        }
    with _LOCK:
        _write(raw, overwrite=overwrite)
    return {"document": raw, **_view(raw)}


def open_installed_pack(pack_id: str, overwrite: bool = False) -> dict:
    """Copy an installed pack into an editable MCP draft."""
    raw = load_document(pack_id).model_dump(mode="json")
    with _LOCK:
        _write(raw, overwrite=overwrite)
    return {"document": raw, **_view(raw)}


def get_draft(pack_id: str) -> dict:
    """Return a complete portable roster draft and current validation."""
    with _LOCK:
        raw = _read(pack_id)
    return {"document": raw, **_view(raw)}


def validate_draft(pack_id: str) -> dict:
    """Validate a draft without installing or changing game data."""
    with _LOCK:
        raw = _read(pack_id)
    return _view(raw)


def update_pack_metadata(pack_id: str, changes: dict[str, Any]) -> dict:
    """Update draft name, description, or world settings."""
    allowed = {"name", "description", "league_regions", "teams_per_region", "tier2_per_region"}
    unknown = sorted(set(changes) - allowed)
    if unknown:
        raise RosterMcpError(f"metadata fields are not editable: {unknown}")
    with _LOCK:
        raw = _read(pack_id)
        for key in ("name", "description"):
            if key in changes:
                raw[key] = changes[key]
        for key in ("league_regions", "teams_per_region", "tier2_per_region"):
            if key in changes:
                raw["world"][key] = changes[key]
        _write(raw)
    return _view(raw, {"metadata": changes})


def add_team(
    pack_id: str,
    name: str,
    tag: str,
    region: str,
    tier: int = 1,
    prestige: float = 50,
    partial: bool = False,
) -> dict:
    """Add an empty team to a draft; add its players with add_team_player."""
    with _LOCK:
        raw = _read(pack_id)
        if any(slugify(str(t.get("name", ""))) == slugify(name) for t in raw.get("teams", [])):
            raise RosterMcpError(f"team {name!r} already exists")
        team = {
            "name": name,
            "tag": tag,
            "region": region,
            "tier": tier,
            "prestige": prestige,
            "partial": partial,
            "players": [],
        }
        raw.setdefault("teams", []).append(team)
        _write(raw)
    return _view(raw, {"team": team})


def edit_team(pack_id: str, team_name: str, changes: dict[str, Any]) -> dict:
    """Edit team identity or league placement in a draft."""
    allowed = {"name", "tag", "region", "tier", "prestige", "partial"}
    unknown = sorted(set(changes) - allowed)
    if unknown:
        raise RosterMcpError(f"team fields are not editable: {unknown}")
    with _LOCK:
        raw = _read(pack_id)
        team = _team(raw, team_name)
        team.update(changes)
        _write(raw)
    return _view(raw, {"team": team})


def remove_team(pack_id: str, team_name: str) -> dict:
    """Remove a team and all of its players from a draft."""
    with _LOCK:
        raw = _read(pack_id)
        team = _team(raw, team_name)
        raw["teams"].remove(team)
        _write(raw)
    return _view(raw, {"removed_team": team_name})


def add_team_player(pack_id: str, team_name: str, player: DraftPlayer) -> dict:
    """Add one schema-validated player to a draft team."""
    row = player.model_dump(mode="json")
    with _LOCK:
        raw = _read(pack_id)
        team = _team(raw, team_name)
        players = team.setdefault("players", [])
        if any(slugify(str(p.get("handle", ""))) == slugify(player.handle) for p in players):
            raise RosterMcpError(f"player {player.handle!r} already exists on {team_name}")
        if len(players) >= 5:
            raise RosterMcpError(f"team {team_name!r} already has five players")
        players.append(row)
        _write(raw)
    return _view(raw, {"team": team_name, "player": row})


def edit_team_player(
    pack_id: str, team_name: str, handle: str, changes: dict[str, Any]
) -> dict:
    """Patch one player on a draft team and revalidate the player schema."""
    with _LOCK:
        raw = _read(pack_id)
        team = _team(raw, team_name)
        index, current = _player(team.setdefault("players", []), handle, team_name)
        try:
            updated = DraftPlayer.model_validate({**current, **changes})
        except ValidationError as exc:
            raise _model_error(exc) from exc
        row = updated.model_dump(mode="json")
        team["players"][index] = row
        _write(raw)
    return _view(raw, {"team": team_name, "player": row})


def remove_team_player(pack_id: str, team_name: str, handle: str) -> dict:
    """Remove one player from a draft team."""
    with _LOCK:
        raw = _read(pack_id)
        team = _team(raw, team_name)
        index, current = _player(team.setdefault("players", []), handle, team_name)
        team["players"].pop(index)
        _write(raw)
    return _view(raw, {"team": team_name, "removed_player": current})


def add_free_agent(pack_id: str, player: DraftFreeAgent) -> dict:
    """Add one schema-validated free agent to a draft."""
    row = player.model_dump(mode="json")
    with _LOCK:
        raw = _read(pack_id)
        players = raw.setdefault("free_agents", [])
        if any(slugify(str(p.get("handle", ""))) == slugify(player.handle) for p in players):
            raise RosterMcpError(f"free agent {player.handle!r} already exists")
        players.append(row)
        _write(raw)
    return _view(raw, {"free_agent": row})


def edit_free_agent(pack_id: str, handle: str, changes: dict[str, Any]) -> dict:
    """Patch one draft free agent and revalidate the player schema."""
    with _LOCK:
        raw = _read(pack_id)
        players = raw.setdefault("free_agents", [])
        index, current = _player(players, handle, "free agents")
        try:
            updated = DraftFreeAgent.model_validate({**current, **changes})
        except ValidationError as exc:
            raise _model_error(exc) from exc
        row = updated.model_dump(mode="json")
        players[index] = row
        _write(raw)
    return _view(raw, {"free_agent": row})


def remove_free_agent(pack_id: str, handle: str) -> dict:
    """Remove one free agent from a draft."""
    with _LOCK:
        raw = _read(pack_id)
        players = raw.setdefault("free_agents", [])
        index, current = _player(players, handle, "free agents")
        players.pop(index)
        _write(raw)
    return _view(raw, {"removed_free_agent": current})


def install_draft(pack_id: str) -> dict:
    """Compile a valid draft and atomically install it into the Play lobby."""
    with _LOCK:
        raw = _read(pack_id)
        validation = validate_document(raw)
        if not validation["valid"]:
            details = "; ".join(
                f"{error['path']}: {error['message']}"
                for error in validation["errors"][:5]
            )
            raise RosterMcpError(f"draft is not installable: {details}")
        result = install_document(raw)
    return {"pack_id": pack_id, "installed": True, **result}
