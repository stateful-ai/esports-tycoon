"""Player/team profile endpoints — contract shape, scouting fog, and
determinism.

These are pure read-only aggregations over GameState. The endpoints are
plain functions on the web server module (FastAPI runs them in a
threadpool), so we drive them directly through the module-global session
`S` — no HTTP client needed. 404s surface as HTTPException, which is what
FastAPI serializes into {"detail": ...}.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

import esports_sim.web.server as server_mod
from esports_sim.manager import advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData

SEED = 2026
WEEKS = 3  # enough to populate stats, fixtures, and relationships


# Frozen contract key sets — the frontend renders these exactly.
PLAYER_TOP = {
    "player",
    "overview",
    "traits",
    "attributes",
    "agents",
    "season",
    "weekly",
    "relationships",
    "career",
}
PLAYER_BLOCK = {
    "id",
    "handle",
    "age",
    "role",
    "team_id",
    "team_name",
    "team_logo",
    "portrait",
    "is_user_team",
    "is_free_agent",
}
OVERVIEW = {
    "ovr",
    "potential",
    "form",
    "morale",
    "condition",
    "market_value",
    "salary",
    "contract_weeks",
    "playstyle",
    "fogged",
}
SEASON = {
    "matches",
    "kills",
    "deaths",
    "assists",
    "kd",
    "acs",
    "first_kills",
    "clutches",
}
WEEKLY_ITEM = {"season", "week", "opponent", "result", "kills", "deaths", "acs"}
ATTR_ITEM = {"key", "label", "value", "band"}
AGENT_ITEM = {"agent_id", "name", "icon", "mastery"}
REL_ITEM = {"pid", "handle", "kind", "strength"}

TEAM_TOP = {"team", "record", "splits", "maps", "players", "form", "honors"}
TEAM_BLOCK = {"id", "name", "logo", "region", "league_tier", "is_user_team"}
RECORD = {"wins", "losses", "round_diff", "position", "streak"}
SPLITS = {"attack_round_rate", "defense_round_rate"}
MAP_ITEM = {"map", "played", "wins", "losses"}
TEAM_PLAYER_ITEM = {"pid", "handle", "role", "matches", "kd", "acs"}
FORM_ITEM = {"season", "week", "opponent", "result", "score"}


def _build(game_data: GameData) -> GameState:
    gs = new_campaign(game_data, seed=SEED, user_team_id="team_nexus")
    for _ in range(WEEKS):
        advance_week(gs, game_data)
    return gs


def _player(gs: GameState, gd: GameData, pid: str) -> dict:
    server_mod.S.gs = gs
    server_mod.S.gd = gd
    return server_mod.player_profile(pid)


def _team(gs: GameState, gd: GameData, tid: str) -> dict:
    server_mod.S.gs = gs
    server_mod.S.gd = gd
    return server_mod.team_profile(tid)


class Handles:
    """Deterministic pick of one player/team per category to profile."""

    def __init__(self, gs: GameState) -> None:
        self.user_team = gs.user_team_id
        self.user_pid = gs.teams[self.user_team].player_ids[0]
        self.rival_team = next(
            t
            for t in sorted(gs.teams.values(), key=lambda t: t.id)
            if t.tier == 1 and t.id != self.user_team
        ).id
        self.rival_pid = gs.teams[self.rival_team].player_ids[0]
        self.tier2_team = next(
            t for t in sorted(gs.teams.values(), key=lambda t: t.id) if t.tier == 2
        ).id
        self.tier2_pid = gs.teams[self.tier2_team].player_ids[0]
        self.fa_pid = sorted(gs.free_agent_ids)[0]


@pytest.fixture(scope="module")
def env(game_data: GameData):
    gs = _build(game_data)
    return gs, game_data, Handles(gs)


# ---------------------------------------------------------------------------
# Player profile


def _assert_player_contract(prof: dict) -> None:
    assert set(prof) == PLAYER_TOP
    assert set(prof["player"]) == PLAYER_BLOCK
    assert set(prof["overview"]) == OVERVIEW
    assert set(prof["season"]) == SEASON
    for item in prof["attributes"]:
        assert set(item) == ATTR_ITEM
    for item in prof["agents"]:
        assert set(item) == AGENT_ITEM
    for item in prof["weekly"]:
        assert set(item) == WEEKLY_ITEM
    for item in prof["relationships"]:
        assert set(item) == REL_ITEM
    for tr in prof["traits"]:
        assert set(tr) == {"name", "desc", "revealed"}


def test_user_player_profile(env) -> None:
    gs, gd, h = env
    prof = _player(gs, gd, h.user_pid)
    _assert_player_contract(prof)

    assert prof["player"]["is_user_team"] is True
    assert prof["player"]["is_free_agent"] is False
    assert prof["player"]["team_id"] == h.user_team

    ov = prof["overview"]
    assert ov["fogged"] is False
    assert isinstance(ov["ovr"], int)  # exact for own club
    assert ov["form"] is not None and ov["morale"] is not None
    assert isinstance(ov["market_value"], int)

    # Own club: every attribute carries an EXACT value plus a band.
    assert prof["attributes"], "user player should expose attributes"
    assert all(a["value"] is not None for a in prof["attributes"])
    assert all(a["band"] for a in prof["attributes"])

    # Weekly is chronological (oldest first) and drawn from played fixtures.
    weeks = [w["week"] for w in prof["weekly"]]
    assert weeks == sorted(weeks)
    assert len(prof["weekly"]) >= 1

    # ACS / assists / clutches are not persisted anywhere -> null.
    assert prof["season"]["acs"] is None
    assert prof["season"]["assists"] is None
    assert prof["season"]["clutches"] is None
    assert prof["career"] == []  # no per-season archive exists


def test_rival_player_profile_fog(env) -> None:
    gs, gd, h = env
    prof = _player(gs, gd, h.rival_pid)
    _assert_player_contract(prof)

    ov = prof["overview"]
    assert ov["fogged"] is True
    assert ov["ovr"] is None  # no exact ability for an unscouted rival
    assert ov["form"] is None and ov["morale"] is None and ov["condition"] is None
    assert isinstance(ov["potential"], str)  # banded ceiling text still shown

    # Scout-banded attributes: a qualitative band, but the exact number is
    # hidden.
    assert prof["attributes"], "rival should still list banded attributes"
    assert all(a["value"] is None for a in prof["attributes"])
    assert all(a["band"] for a in prof["attributes"])

    # Rival locker-room graph stays private, like the roster page.
    assert prof["relationships"] == []
    # Season box scores are public broadcast data — not fogged.
    assert prof["season"]["matches"] >= 1


def test_free_agent_profile(env) -> None:
    gs, gd, h = env
    prof = _player(gs, gd, h.fa_pid)
    _assert_player_contract(prof)

    pl = prof["player"]
    assert pl["is_free_agent"] is True
    assert pl["is_user_team"] is False
    assert pl["team_id"] is None
    assert pl["team_name"] is None
    assert pl["team_logo"] is None

    # No current club -> nothing to attribute weekly/relationship-wise.
    assert prof["weekly"] == []
    assert prof["relationships"] == []
    assert prof["career"] == []
    assert isinstance(prof["overview"]["market_value"], int)


def test_tier2_player_profile(env) -> None:
    gs, gd, h = env
    prof = _player(gs, gd, h.tier2_pid)
    _assert_player_contract(prof)

    # Tier 2 is fully simmed: the player accrues real season stats and a
    # derivable weekly series even though it is never broadcast.
    assert prof["player"]["is_free_agent"] is False
    assert prof["season"]["matches"] >= 1
    assert isinstance(prof["weekly"], list)
    # A tier-2 player is a rival -> fogged, banded attributes.
    assert prof["overview"]["fogged"] is True
    assert all(a["value"] is None for a in prof["attributes"])


# ---------------------------------------------------------------------------
# Team profile


def _assert_team_contract(prof: dict) -> None:
    assert set(prof) == TEAM_TOP
    assert set(prof["team"]) == TEAM_BLOCK
    assert set(prof["record"]) == RECORD
    assert set(prof["splits"]) == SPLITS
    for m in prof["maps"]:
        assert set(m) == MAP_ITEM
    for p in prof["players"]:
        assert set(p) == TEAM_PLAYER_ITEM
    for f in prof["form"]:
        assert set(f) == FORM_ITEM
    assert isinstance(prof["honors"], list)
    assert all(isinstance(x, str) for x in prof["honors"])


def test_user_team_profile(env) -> None:
    gs, gd, h = env
    prof = _team(gs, gd, h.user_team)
    _assert_team_contract(prof)

    assert prof["team"]["is_user_team"] is True
    assert prof["team"]["league_tier"] == 1
    rec = prof["record"]
    assert rec["wins"] + rec["losses"] >= 1
    assert isinstance(rec["position"], int)
    assert isinstance(rec["streak"], str)
    # Form is chronological and capped at the last 20.
    assert len(prof["form"]) <= 20
    assert [f["week"] for f in prof["form"]] == sorted(f["week"] for f in prof["form"])
    # Players are ordered best-first (acs is untracked -> rating fallback).
    assert prof["players"], "user team should list its roster"


def test_rival_team_profile(env) -> None:
    gs, gd, h = env
    prof = _team(gs, gd, h.rival_team)
    _assert_team_contract(prof)
    assert prof["team"]["is_user_team"] is False
    assert prof["team"]["league_tier"] == 1
    # Team-level box scores stay public even for a rival.
    assert prof["record"]["wins"] + prof["record"]["losses"] >= 1


def test_tier2_team_profile(env) -> None:
    gs, gd, h = env
    prof = _team(gs, gd, h.tier2_team)
    _assert_team_contract(prof)
    assert prof["team"]["league_tier"] == 2
    assert prof["team"]["is_user_team"] is False
    assert prof["record"]["wins"] + prof["record"]["losses"] >= 1
    assert prof["maps"], "tier-2 team is simmed and should have map records"


# ---------------------------------------------------------------------------
# 404s


def test_unknown_player_404(env) -> None:
    gs, gd, _ = env
    with pytest.raises(HTTPException) as ei:
        _player(gs, gd, "no_such_player")
    assert ei.value.status_code == 404
    assert ei.value.detail


def test_unknown_team_404(env) -> None:
    gs, gd, _ = env
    with pytest.raises(HTTPException) as ei:
        _team(gs, gd, "no_such_team")
    assert ei.value.status_code == 404
    assert ei.value.detail


# ---------------------------------------------------------------------------
# Determinism: same seed + same advances -> byte-identical payloads.


def test_profile_determinism(game_data: GameData) -> None:
    gs_a = _build(game_data)
    gs_b = _build(game_data)
    h = Handles(gs_a)

    def dump_player(gs: GameState, pid: str) -> str:
        return json.dumps(_player(gs, game_data, pid), sort_keys=True)

    def dump_team(gs: GameState, tid: str) -> str:
        return json.dumps(_team(gs, game_data, tid), sort_keys=True)

    for pid in (h.user_pid, h.rival_pid, h.tier2_pid, h.fa_pid):
        assert dump_player(gs_a, pid) == dump_player(gs_b, pid)
    for tid in (h.user_team, h.rival_team, h.tier2_team):
        assert dump_team(gs_a, tid) == dump_team(gs_b, tid)
