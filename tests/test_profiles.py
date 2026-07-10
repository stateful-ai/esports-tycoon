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

# The web layer is an optional extra; without it these contract tests skip
# rather than break collection (CI installs ".[dev,web]" so they DO run there).
fastapi = pytest.importorskip("fastapi")
HTTPException = fastapi.HTTPException

import esports_sim.web.server as server_mod
from esports_sim.manager import advance_week, chronicle, new_campaign
from esports_sim.manager.state import (
    CareerStats,
    Fixture,
    GameState,
    MapResult,
    PlayerLineSnap,
    PlayerSeasonStats,
    TeamRecord,
)
from esports_sim.registry import GameData
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role

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
    "splits",
    "charts",
    "relationships",
    "career",
    "career_totals",
    "honours",
    "epithet",
    "memories",
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
    "transfer_ask",
    "followers",
    "confidence",
    "is_starter",
    "dev_focus",
    "training_intensity",
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
    "rating",
    "analytics_tier",
    "hs_pct",
    "first_deaths",
    "fk_fd",
    "clutch_1v1",
    "clutch_1v2",
    "clutch_1v3",
    "kast_pct",
    "trade_kills",
    "eco_kills",
    "save_kills",
    "pistol_kills",
    "multikills",
    "aces",
    "kills_by_weapon",
}
WEEKLY_ITEM = {"season", "week", "opponent", "result", "kills", "deaths", "acs"}
ATTR_ITEM = {"key", "label", "value", "band"}
AGENT_ITEM = {"agent_id", "name", "icon", "mastery"}
REL_ITEM = {"pid", "handle", "kind", "strength"}

TEAM_TOP = {
    "team", "record", "splits", "maps", "players", "form", "honors",
    "rivals", "knowledge",
}
TEAM_BLOCK = {"id", "name", "logo", "region", "league_tier", "is_user_team"}
RECORD = {"wins", "losses", "round_diff", "position", "streak"}
SPLITS = {"attack_round_rate", "defense_round_rate"}
MAP_ITEM = {"map", "played", "wins", "losses"}
TEAM_PLAYER_ITEM = {
    "pid", "handle", "role", "matches", "kd", "acs", "retirement_risk",
}
FORM_ITEM = {"season", "week", "opponent", "result", "score"}


def _build(game_data: GameData) -> GameState:
    gs = new_campaign(game_data, seed=SEED, user_team_id="team_nexus")
    for _ in range(WEEKS):
        advance_week(gs, game_data)
    return gs


def _bind(gs: GameState, gd: GameData) -> None:
    """Bind a one-off game + request context so the endpoint functions (which
    read the current game via the `S` proxy) can be called directly in-process,
    without spinning up the ASGI app."""
    game = server_mod._Game(gd, "TESTC", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))


def _player(gs: GameState, gd: GameData, pid: str) -> dict:
    _bind(gs, gd)
    return server_mod.player_profile(pid)


def _team(gs: GameState, gd: GameData, tid: str) -> dict:
    _bind(gs, gd)
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


# ---------------------------------------------------------------------------
# Pass-2 web helpers: POTM, recent form, epithet (pure reads over GameState)


def _line(pid, kills, rating):
    return PlayerLineSnap(player_id=pid, kills=kills, deaths=12, rating=rating)


def test_series_potm_prefers_the_winning_side():
    # vex (loser) has the highest rating, but POTM goes to the winner's top.
    r = MapResult(
        map_id="ascent", seed=0, score_a=13, score_b=9, winner_id="nxs",
        lines=[_line("apex", 20, 1.30), _line("vex", 25, 1.55)],
    )
    f = Fixture(id="s1w1m0", week=1, team_a="nxs", team_b="vgd", maps=["ascent"],
                played=True, winner_id="nxs", results=[r])
    gs = GameState(
        seed=1, season=1, week=1, user_team_id="nxs",
        teams={
            "nxs": Team(id="nxs", name="Nexus", tag="NXS", player_ids=["apex"]),
            "vgd": Team(id="vgd", name="Vanguard", tag="VGD", player_ids=["vex"]),
        },
        players={
            "apex": Player(id="apex", handle="Apex", age=24, role=Role.DUELIST,
                           playstyle=Playstyle.ENTRY, attributes={"aim_precision": 80}),
            "vex": Player(id="vex", handle="Vex", age=24, role=Role.DUELIST,
                          playstyle=Playstyle.ENTRY, attributes={"aim_precision": 80}),
        },
    )
    potm = server_mod._series_potm(f, gs)
    assert potm["player_id"] == "apex" and potm["on_winner"] is True
    assert potm["handle"] == "Apex"


def test_series_potm_falls_back_to_overall_top_when_roster_churned():
    r = MapResult(
        map_id="ascent", seed=0, score_a=13, score_b=5, winner_id="nxs",
        lines=[_line("ghost", 25, 1.60)],
    )
    f = Fixture(id="s1w1m0", week=1, team_a="nxs", team_b="vgd", maps=["ascent"],
                played=True, winner_id="nxs", results=[r])
    gs = GameState(
        seed=1, season=1, week=1, user_team_id="nxs",
        teams={"nxs": Team(id="nxs", name="Nexus", tag="NXS", player_ids=[])},
        players={"ghost": Player(id="ghost", handle="Ghost", age=24, role=Role.DUELIST,
                                 playstyle=Playstyle.ENTRY, attributes={"aim_precision": 80})},
    )
    potm = server_mod._series_potm(f, gs)
    assert potm["player_id"] == "ghost" and potm["on_winner"] is False


def test_series_potm_none_for_unplayed_fixture():
    f = Fixture(id="x", week=1, team_a="nxs", team_b="vgd", maps=["ascent"], played=False)
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs", teams={}, players={})
    assert server_mod._series_potm(f, gs) is None


def _bo1(week, winner):
    sa, sb = (13, 7) if winner == "nxs" else (7, 13)
    return Fixture(
        id=f"s1w{week}m0", week=week, team_a="nxs", team_b="vgd", maps=["ascent"],
        played=True, winner_id=winner,
        results=[MapResult(map_id="ascent", seed=0, score_a=sa, score_b=sb,
                           winner_id=winner)],
    )


def test_team_recent_form_returns_last_five_oldest_first():
    teams = {
        "nxs": Team(id="nxs", name="Nexus", tag="NXS"),
        "vgd": Team(id="vgd", name="Vanguard", tag="VGD"),
    }
    # weeks 1..6: nxs wins odd weeks, loses even weeks.
    fixtures = [_bo1(w, "nxs" if w % 2 else "vgd") for w in range(1, 7)]
    gs = GameState(seed=1, season=1, week=7, user_team_id="nxs",
                   teams=teams, fixtures=fixtures)
    form = server_mod._team_recent_form(gs, "nxs", n=5)
    assert [g["week"] for g in form] == [2, 3, 4, 5, 6]  # week 1 dropped, oldest-first
    assert [g["result"] for g in form] == ["L", "W", "L", "W", "L"]
    assert form[-1]["opponent"] == "Vanguard"


def test_player_epithet_priority_and_grounding():
    gs = GameState(seed=1, season=3, week=1, user_team_id="nxs", teams={}, players={})
    assert server_mod._player_epithet(gs, "p") is None  # nothing won yet
    chronicle.record(gs, "award", "P wins Top Fragger.", player_id="p",
                     data={"award": "Top Fragger"})
    assert server_mod._player_epithet(gs, "p") == "Star fragger"
    chronicle.record(gs, "award", "P wins Season MVP.", player_id="p",
                     data={"award": "Season MVP"})
    assert server_mod._player_epithet(gs, "p") == "League MVP"  # MVP outranks
    # An award without a mapped epithet still earns the generic label.
    gs2 = GameState(seed=1, season=1, week=1, user_team_id="nxs", teams={}, players={})
    chronicle.record(gs2, "award", "Q wins Best Defensive Team.", player_id="q",
                     data={"award": "Best Defensive Team"})
    assert server_mod._player_epithet(gs2, "q") == "Decorated pro"


# ---------------------------------------------------------------------------
# Pass-3 web helpers: playoff elimination + career totals (pure reads)


def test_eliminated_teams_flags_the_hopeless():
    def mk(tid, wins):
        return Team(id=tid, name=tid.title(), tag=tid.upper()[:3], tier=1), \
            TeamRecord(wins=wins, losses=0)

    teams, standings = {}, {}
    for tid, w in [("a", 6), ("b", 6), ("c", 5), ("d", 5), ("e", 2)]:
        t, rec = mk(tid, w)
        teams[tid], standings[tid] = t, rec
    region = str(teams["a"].region)
    # 'e' has one regular game left (ceiling 3); a..d already have >3 wins,
    # so four rivals finish certainly above -> 'e' can't reach the top-4.
    fx = [Fixture(id="s1w9", week=9, stage="regular", tier=1,
                  team_a="e", team_b="a", maps=["ascent"], played=False)]
    gs = GameState(seed=1, season=1, week=9, user_team_id="a", phase="regular",
                   teams=teams, standings=standings, fixtures=fx)
    assert server_mod._eliminated_teams(gs, region) == {"e"}


def test_eliminated_teams_empty_outside_regular_season():
    t = Team(id="a", name="A", tag="A", tier=1)
    gs = GameState(seed=1, season=1, week=1, user_team_id="a", phase="playoffs",
                   teams={"a": t}, standings={"a": TeamRecord()})
    assert server_mod._eliminated_teams(gs, str(t.region)) == set()


def test_profile_career_totals_combines_history_and_live_season():
    gs = GameState(seed=1, season=3, week=5, user_team_id="nxs", teams={}, players={})
    gs.career_stats["p"] = CareerStats(
        maps=40, kills=500, deaths=420, first_kills=60, clutches=20, seasons=3
    )
    gs.player_stats["p"] = PlayerSeasonStats(maps=6, kills=90, deaths=70)
    chronicle.record(gs, "award", "P wins Season MVP.", player_id="p",
                     data={"award": "Season MVP"})
    ct = server_mod._profile_career_totals(gs, "p")
    assert ct["maps"] == 46 and ct["kills"] == 590
    assert ct["seasons"] == 4  # 3 completed + the live one
    assert ct["kd"] == round(590 / 490, 2)
    assert ct["honours"] == 1 and ct["mvps"] == 1


def test_profile_career_totals_none_for_a_mapless_debutant():
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs", teams={}, players={})
    assert server_mod._profile_career_totals(gs, "rookie") is None
