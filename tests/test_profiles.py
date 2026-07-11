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
    DevSnap,
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
    "badges",
    "attributes",
    "agents",
    "season",
    "weekly",
    "splits",
    "charts",
    "relationships",
    "career",
    "career_totals",
    "career_arc",
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
    "tenure_weeks",
    "transfer_ask",
    "ask_breakdown",
    "followers",
    "stream_load",
    "stream_status",
    "stream_income",
    "stream_growth_mult",
    "can_rein_streaming",
    "confidence",
    "is_starter",
    "dev_focus",
    "training_intensity",
    "country",
    "languages",
}
OVERVIEW = {
    "ovr",
    "ovr_stars",
    "potential",
    "potential_stars",
    "potential_band",
    "skill_ceilings",
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
    "identity", "tendencies", "rivals", "knowledge", "chemistry",
    "dev_progress", "strength", "agent_pool",
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
    # Rostered at campaign start -> the loyalty clock is already running.
    assert prof["player"]["tenure_weeks"] >= 1
    # Streaming block is public: a label plus the org's weekly cut, and the
    # own-club-only "rein it in" affordance is a bool either way.
    assert prof["player"]["stream_status"] in (
        "heavy streamer", "balanced", "practice-focused"
    )
    assert isinstance(prof["player"]["can_rein_streaming"], bool)

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


# ---------------------------------------------------------------------------
# Pass-4 web helpers: tactical identity, condition trend, leaders, movers


def _p(pid, ca=75):
    return Player(id=pid, handle=pid.title(), age=24, role=Role.DUELIST,
                  playstyle=Playstyle.ENTRY, attributes={"aim_precision": ca})


def test_team_identity_label_picks_the_dominant_dial():
    t = Team(id="x", name="X", tag="X")
    assert server_mod._team_identity_label(t.tactics) == "Balanced"  # all neutral
    t.tactics.aggression = 80  # dev 30 -> Aggressive
    assert server_mod._team_identity_label(t.tactics) == "Aggressive"
    t.tactics.pace = 5  # dev 45 outweighs aggression's 30 -> Methodical
    assert server_mod._team_identity_label(t.tactics) == "Methodical"


def test_team_identity_label_balanced_inside_deadzone():
    t = Team(id="y", name="Y", tag="Y")
    t.tactics.aggression = 58  # dev 8 < 12 -> still Balanced
    assert server_mod._team_identity_label(t.tactics) == "Balanced"


def test_team_tendencies_read_the_poles():
    t = Team(id="x", name="X", tag="X")
    assert server_mod._team_tendencies(t.tactics) == []  # neutral -> nothing
    t.tactics.aggression = 70
    t.tactics.pace = 70
    tend = server_mod._team_tendencies(t.tactics)
    assert "swings angles aggressively" in tend and "hits sites fast" in tend


def test_condition_trend_reads_direction():
    gs = GameState(seed=1, season=1, week=3, user_team_id="nxs", teams={}, players={})
    assert server_mod._condition_trend(gs, "p") is None  # no history yet
    gs.dev_history["p"] = [
        DevSnap(season=1, week=1, ca=70, confidence=50, form=50, morale=50, followers=1000),
        DevSnap(season=1, week=2, ca=70, confidence=50, form=50, morale=50, followers=1000),
        DevSnap(season=1, week=3, ca=72, confidence=60, form=45, morale=50, followers=1000),
    ]
    tr = server_mod._condition_trend(gs, "p")  # last(w3) vs snaps[-3](w1)
    assert tr["ca"] == "up"          # +2 > 0.3
    assert tr["confidence"] == "up"  # +10 > 2.0
    assert tr["form"] == "down"      # -5 < -1.5


def test_league_leaders_top_by_rating_tier1_only():
    teams = {
        "nxs": Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["a", "b"]),
        "t2": Team(id="t2", name="T2", tag="T2", tier=2, player_ids=["c"]),
    }
    players = {pid: _p(pid) for pid in ("a", "b", "c")}
    stats = {
        "a": PlayerSeasonStats(maps=5, rating_sum=6.0, kills=100),   # 1.20
        "b": PlayerSeasonStats(maps=5, rating_sum=5.0, kills=90),    # 1.00
        "c": PlayerSeasonStats(maps=5, rating_sum=7.5, kills=120),   # 1.50 but tier-2
    }
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams=teams, players=players, player_stats=stats)
    ld = server_mod._league_leaders(gs, n=3)
    assert [x["pid"] for x in ld] == ["a", "b"]  # c excluded (tier 2)
    assert ld[0]["rating"] == 1.2
    # Each row links back to the player's club.
    assert all(x["team_id"] == "nxs" for x in ld)


def test_roster_movers_rank_by_absolute_swing():
    teams = {"nxs": Team(id="nxs", name="Nexus", tag="NXS", tier=1,
                         player_ids=["a", "b", "c"])}
    players = {pid: _p(pid) for pid in ("a", "b", "c")}
    gs = GameState(seed=1, season=1, week=2, user_team_id="nxs",
                   teams=teams, players=players)

    def hist(w1, w2):
        return [DevSnap(season=1, week=1, ca=w1, confidence=50, form=50, morale=50, followers=1000),
                DevSnap(season=1, week=2, ca=w2, confidence=50, form=50, morale=50, followers=1000)]

    gs.dev_history["a"] = hist(70, 72.5)   # +2.5
    gs.dev_history["b"] = hist(70, 69.0)   # -1.0
    gs.dev_history["c"] = hist(70, 70.1)   # +0.1 -> below the 0.3 threshold
    mv = server_mod._roster_movers(gs, "nxs")
    assert [m["pid"] for m in mv] == ["a", "b"]  # |2.5| > |1.0|; c dropped
    assert mv[0]["delta"] == 2.5 and mv[1]["delta"] == -1.0


# ---------------------------------------------------------------------------
# Pass-6 market decision aids (server helpers over a real campaign)


def test_squad_needs_covers_every_core_role(env):
    gs, gd, h = env
    needs = server_mod._squad_needs(gs, h.user_team)
    assert set(needs["role_counts"]) == {
        "duelist", "controller", "initiator", "sentinel", "flex"
    }
    # a full five-man starter roster has no empty CORE role
    assert all(isinstance(v, int) for v in needs["role_counts"].values())
    if needs["weakest_role"] is not None:
        assert needs["weakest_role"]["role"] in needs["role_counts"]


def test_target_suggestions_respect_the_priority_role(env):
    gs, gd, h = env
    needs = server_mod._squad_needs(gs, h.user_team)
    targets = server_mod._target_suggestions(gs, h.user_team, needs)
    assert isinstance(targets, list) and len(targets) <= 3
    want = set(needs["gaps"]) or (
        {needs["weakest_role"]["role"]} if needs["weakest_role"] else set()
    )
    if want and targets:
        assert all(t["role"] in want for t in targets)
    # ranked by quality (descending)
    q = [t["quality"] for t in targets]
    assert q == sorted(q, reverse=True)


def test_contract_watch_shape_and_thresholds(env):
    gs, gd, h = env
    cw = server_mod._contract_watch(gs, h.user_team, weeks=8)
    assert set(cw) == {"expiring_own", "market_watch"}
    assert all(0 < p["weeks_left"] <= 8 for p in cw["expiring_own"])
    assert all(0 < p["weeks_left"] <= 8 for p in cw["market_watch"])
    # own entries are your players; market entries are rivals (not your club)
    own_ids = {p.id for p in gs.roster(h.user_team)}
    assert all(p["id"] in own_ids for p in cw["expiring_own"])
    assert all(p["id"] not in own_ids for p in cw["market_watch"])
    # Market-watch rows link to the rival club holding the expiring deal.
    assert all(
        p["team_id"] in gs.teams and p["team_id"] != h.user_team
        for p in cw["market_watch"]
    )


def test_round_summaries_from_event_log():
    events = [
        {"type": "round.start", "round_num": 1, "attacking_team_id": "a"},
        {"type": "round.spike_plant"},
        {"type": "round.end", "winner_id": "a"},
        {"type": "round.start", "round_num": 2, "attacking_team_id": "a"},
        {"type": "round.end", "winner_id": "b"},
    ]
    rs = server_mod._round_summaries(events, team_a="a")
    assert len(rs) == 2
    assert rs[0] == {"num": 1, "attacker": "a", "plant": True,
                     "winner_id": "a", "score_a": 1, "score_b": 0}
    assert rs[1] == {"num": 2, "attacker": "a", "plant": False,
                     "winner_id": "b", "score_a": 1, "score_b": 1}


def test_transfer_rumors_shape(env):
    gs, gd, h = env
    rumors = server_mod._transfer_rumors(gs, h.user_team)
    assert isinstance(rumors, list)
    assert all(set(r) == {"kind", "text"} for r in rumors)
    assert all(r["kind"] in ("interest", "link") for r in rumors)


def test_fixture_run_in_rates_upcoming(env):
    gs, gd, h = env
    run_in = server_mod._fixture_run_in(gs, h.user_team)
    assert isinstance(run_in, list) and len(run_in) <= 5
    assert all(
        set(r) == {"week", "opponent", "opponent_id", "opp_rank", "difficulty"}
        for r in run_in
    )
    assert all(r["difficulty"] in ("easy", "medium", "hard") for r in run_in)
    assert all(r["week"] >= gs.week for r in run_in)
    # The opponent id resolves to a real club (linkable in the UI).
    assert all(r["opponent_id"] in gs.teams for r in run_in)


def test_squad_chemistry_shape(env):
    gs, gd, h = env
    chem = server_mod._squad_chemistry(gs, h.user_team)
    assert set(chem) == {"cohesion", "bonds", "frictions"}
    assert chem["cohesion"] is None or isinstance(chem["cohesion"], float)
    for p in chem["bonds"] + chem["frictions"]:
        assert set(p) == {"a", "a_id", "b", "b_id", "strength"}


def test_wonderkid_watch_shape(env):
    gs, gd, h = env
    wk = server_mod._wonderkid_watch(gs)
    assert isinstance(wk, list) and len(wk) <= 6
    for w in wk:
        assert set(w) == {
            "id", "handle", "age", "role", "potential_stars", "team", "team_id",
        }
        assert w["age"] <= 20
        # Rostered prospects link to their club; free agents carry None.
        assert (w["team_id"] in gs.teams) or (
            w["team_id"] is None and w["team"] == "free agent"
        )
        assert 0 <= w["potential_stars"] <= 5
    # Sorted by potential star band descending, then id (deterministic).
    stars = [w["potential_stars"] for w in wk]
    assert stars == sorted(stars, reverse=True)


def test_challengers_standouts_shape(env):
    gs, gd, h = env
    chal = server_mod._challengers_standouts(gs, h.user_team)
    assert isinstance(chal, list) and len(chal) <= 5
    for c in chal:
        assert set(c) == {"id", "handle", "age", "role", "team", "team_id", "rating"}
        assert c["team_id"] in gs.teams and gs.teams[c["team_id"]].tier == 2
    ratings = [c["rating"] for c in chal]
    assert ratings == sorted(ratings, reverse=True)


def test_signing_headroom_shape(env):
    gs, gd, h = env
    head = server_mod._signing_headroom(gs, h.user_team)
    assert set(head) == {"weekly_net", "affordable_wage", "runway_weeks", "balance"}
    assert head["affordable_wage"] >= 0
    assert head["affordable_wage"] == max(0, head["weekly_net"])
    assert head["runway_weeks"] is None or head["runway_weeks"] >= 0


def test_dev_progress_shape(env):
    gs, gd, h = env
    dev = server_mod._dev_progress(gs, h.user_team)
    assert isinstance(dev, list)
    for d in dev:
        assert set(d) == {
            "id", "handle", "age", "ca", "potential", "potential_band",
            "progress_pct", "trajectory", "maxed", "mentor_skill",
        }
        assert 0 <= d["progress_pct"] <= 100
        assert d["potential_band"][0] <= d["potential_band"][1]
        assert 0 <= d["mentor_skill"] <= 99
        assert d["trajectory"] in ("climbing", "declining", "steady")
        assert d["ca"] <= d["potential"] + 1  # CA never exceeds ceiling
    # Sorted by potential descending, then handle.
    pots = [d["potential"] for d in dev]
    assert pots == sorted(pots, reverse=True)


def test_map_pool_board_shape(env):
    gs, gd, h = env
    _bind(gs, gd)
    mp = server_mod._map_pool_board(gs, h.user_team)
    assert set(mp) == {"maps", "veto"}
    for m in mp["maps"]:
        assert set(m) == {"map", "map_id", "played", "wins", "win_rate"}
        assert m["wins"] <= m["played"]
    # Win-rate descending (None sinks to the bottom).
    wrs = [m["win_rate"] if m["win_rate"] is not None else -1 for m in mp["maps"]]
    assert wrs == sorted(wrs, reverse=True)
    assert mp["veto"] is None  # no opponent -> no veto suggestion
    mp2 = server_mod._map_pool_board(gs, h.user_team, h.rival_team)
    assert set(mp2["veto"]) == {"opponent", "ban", "pick"}


def test_team_of_week_shape(env):
    gs, gd, h = env
    totw = server_mod._team_of_week(gs)
    assert set(totw) == {"week", "players"}
    assert totw["week"] is None or totw["week"] >= 1
    assert len(totw["players"]) <= 5
    for p in totw["players"]:
        assert set(p) == {
            "id", "handle", "role", "team", "team_id", "rating", "kd", "maps",
        }
        assert p["team_id"] is None or p["team_id"] in gs.teams
    ratings = [p["rating"] for p in totw["players"]]
    assert ratings == sorted(ratings, reverse=True)


def test_roster_chemistry_pair_ids_mirror_handles(env):
    gs, gd, h = env
    _bind(gs, gd)
    ro = server_mod.roster(h.user_team)
    pairs, pair_ids = ro["chemistry_pairs"], ro["chemistry_pair_ids"]
    assert set(pairs) == set(pair_ids) == {"duos", "feuds"}
    for kind in ("duos", "feuds"):
        # Same pairs in the same order: ids resolve to exactly the handles.
        assert [
            [gs.players[a].handle, gs.players[b].handle]
            for a, b in pair_ids[kind]
        ] == pairs[kind]
    # Per-player streaming chip flag: a bool that just restates the label.
    for v in ro["players"]:
        assert v["stream_heavy"] == (v["stream_status"] == "heavy streamer")
    # A rival roster exposes no locker-room pairs, id or handle form alike.
    rv = server_mod.roster(h.rival_team)
    assert rv["chemistry_pairs"] == {"duos": [], "feuds": []}
    assert rv["chemistry_pair_ids"] == {"duos": [], "feuds": []}


def test_tactics_fit_chips_carry_player_ids(env):
    gs, gd, h = env
    _bind(gs, gd)
    fit = server_mod._tactics_fit(gs, gs.teams[h.user_team])
    roster_ids = set(gs.teams[h.user_team].player_ids)
    for dial in fit["dials"]:
        for chip in dial["players"]:
            assert set(chip) == {"id", "handle", "playstyle", "score"}
            assert chip["id"] in roster_ids


def test_market_rows_carry_languages(env):
    gs, gd, h = env
    _bind(gs, gd)
    mv = server_mod.market_view()
    assert mv["free_agents"], "campaign should have free agents to shop"
    for row in mv["free_agents"]:
        assert isinstance(row["languages"], list)
        for l in row["languages"]:
            assert set(l) == {"lang", "level"}
    # Search rows carry the same public language read.
    fa = gs.players[sorted(gs.free_agent_ids)[0]]
    res = server_mod.market_search(q=fa.handle)["results"]
    assert res and all(isinstance(r["languages"], list) for r in res)


def test_completed_match_scout_returns_grounded_report(env):
    gs, gd, h = env
    _bind(gs, gd)
    fixture = next(f for f in gs.fixtures if f.played and f.results)
    gs.scout_progress[f"match:{fixture.id}"] = 0.5
    view = server_mod.scouting_view()
    report = view["match_report"]
    assert report["fixture_id"] == fixture.id
    assert set(report) == {
        "fixture_id", "week", "team_a_id", "team_a_name", "team_b_id",
        "team_b_name", "winner_id", "score", "team_a_tendencies",
        "team_b_tendencies", "danger_man", "veto_lean",
    }
    assert report["danger_man"] is None or set(report["danger_man"]) == {
        "player_id", "handle", "rating",
    }


def test_rival_prices_carry_reconciled_breakdowns(env):
    gs, gd, h = env
    _bind(gs, gd)
    rv = server_mod.roster(h.rival_team)
    for row in rv["players"]:
        quoted = row["buyout"] if row["buyout"] is not None else row["transfer_ask"]
        assert sum(part["delta"] for part in row["ask_breakdown"]) == quoted
        assert all(set(part) == {"label", "delta"} for part in row["ask_breakdown"])


def test_league_endpoint_shape(env):
    gs, gd, h = env
    _bind(gs, gd)
    lg = server_mod.league()
    assert set(lg) == {
        "team_of_week", "bracket", "projection", "in_regular_season",
        "h2h_matrix", "results",
    }
    for r in lg["projection"]:
        assert set(r) == {
            "team_id", "name", "wins", "losses", "remaining", "proj_wins", "proj_pos",
        }
        assert r["proj_wins"] >= r["wins"]
    assert [r["proj_pos"] for r in lg["projection"]] == list(
        range(1, len(lg["projection"]) + 1)
    )
    for rnd in lg["bracket"]:
        assert set(rnd) == {"stage", "label", "matches"}
        for m in rnd["matches"]:
            assert set(m) == {
                "team_a", "team_a_id", "team_b", "team_b_id",
                "score_a", "score_b", "played", "winner_id",
            }


def test_meta_endpoint_shape(env):
    gs, gd, h = env
    _bind(gs, gd)
    mv = server_mod.meta_view()
    assert set(mv) == {"latest_patch", "patched_agents", "tier_list", "map_trends"}
    for a in mv["tier_list"]:
        assert set(a) == {"agent_id", "name", "maps", "pick_rate"}
        assert a["maps"] > 0
    picks = [a["maps"] for a in mv["tier_list"]]
    assert picks == sorted(picks, reverse=True)
    for a in mv["patched_agents"]:
        assert set(a) == {"agent_id", "name", "direction"}
        assert a["direction"] in ("buff", "nerf", "even")
    assert mv["map_trends"]
    for trend in mv["map_trends"]:
        assert set(trend) == {"map_id", "team_maps", "agents", "tactics", "site_focus"}
        assert trend["team_maps"] > 0
        assert {t["key"] for t in trend["tactics"]} == {
            "aggression", "pace", "util_discipline", "eco_greed", "map_control",
        }


def test_meta_report_direction_and_latest_patch(game_data):
    # Direction logic on injected patches (fresh gs — never touch the shared env).
    from esports_sim.manager import meta
    from esports_sim.manager.state import PatchChange, PatchNote

    gs = new_campaign(game_data, seed=7, user_team_id="team_nexus")
    aids = sorted(game_data.agents)
    gs.agent_patches = [
        PatchChange(agent_id=aids[0], ability_id="x", field="cost", delta=-50),  # cheaper = buff
        PatchChange(agent_id=aids[1], ability_id="y", field="cost", delta=120),  # dearer = nerf
        PatchChange(agent_id=aids[2], ability_id="z", field="ult_points", delta=-1),  # cheaper ult = buff
        PatchChange(agent_id=aids[3], ability_id="w", field="charges", delta=-1),  # fewer charges = nerf
    ]
    gs.patch_history = [PatchNote(season=1, week=3, version="1.03", lines=["tweak"])]
    rep = meta.meta_report(gs, game_data.agents)
    dirs = {a["agent_id"]: a["direction"] for a in rep["patched_agents"]}
    assert dirs[aids[0]] == "buff"
    assert dirs[aids[1]] == "nerf"
    # Codex review: an ult_points CUT is a buff (cheaper ult); a charges cut is
    # a nerf. Only cost + ult_points flip sign; charges is straight power.
    assert dirs[aids[2]] == "buff"
    assert dirs[aids[3]] == "nerf"
    assert rep["latest_patch"]["version"] == "1.03"


def test_team_strength_own_vs_fogged(env):
    gs, gd, h = env
    _bind(gs, gd)
    own = server_mod._team_strength(gs, h.user_team, fogged=False)
    assert [a["axis"] for a in own] == ["mechanical", "tactical", "mental", "team"]
    for a in own:
        assert set(a) == {"axis", "label", "value", "band"}
        assert isinstance(a["value"], float) and a["band"]
    fog = server_mod._team_strength(gs, h.rival_team, fogged=True)
    assert all(a["value"] is None and a["band"] for a in fog)


def test_agent_pool_coverage_shape(env):
    gs, gd, h = env
    _bind(gs, gd)
    pool = server_mod._agent_pool_coverage(gs, h.user_team)
    assert set(pool) == {"covered", "meta_gaps"}
    for a in pool["covered"]:
        assert set(a) == {"agent_id", "name", "players", "mastery"}
        assert a["players"] >= 1
    # covered sorted by best mastery descending
    masteries = [a["mastery"] for a in pool["covered"]]
    assert masteries == sorted(masteries, reverse=True)
    for g in pool["meta_gaps"]:
        assert set(g) == {"agent_id", "name"}


def test_suggested_lineup_none_at_five_and_shape_when_deeper(env):
    gs, gd, h = env
    _bind(gs, gd)
    # A five-man roster has nothing to pick.
    if len(gs.teams[h.user_team].player_ids) <= 5:
        assert server_mod._suggested_lineup(gs, h.user_team) is None
    # Deep-roster path on an isolated copy (never mutate the shared env):
    # pad to a guaranteed 7-man roster so there's a real selection to make.
    gs2 = gs.model_copy(deep=True)
    existing = list(gs2.teams[h.user_team].player_ids)
    fas = [pid for pid in sorted(gs2.free_agent_ids) if pid not in existing]
    gs2.teams[h.user_team].player_ids = (existing + fas)[:7]
    assert len(gs2.teams[h.user_team].player_ids) > 5
    sug = server_mod._suggested_lineup(gs2, h.user_team)
    assert sug is not None
    assert set(sug) == {"players", "changed"}
    assert len(sug["players"]) == 5
    for p in sug["players"]:
        assert set(p) == {"id", "handle", "quality", "dressed"}


def test_board_standing_none_in_sandbox_or_shaped(env):
    gs, gd, h = env
    _bind(gs, gd)
    board = server_mod._board_standing(gs)
    assert board is None or set(board) == {
        "goal", "patience", "band", "seasons_left", "goal_state", "goal_detail",
    }


def test_marketability_breakdown_sums_to_score(env):
    gs, gd, h = env
    _bind(gs, gd)
    from esports_sim.manager import sponsors
    mb = sponsors.marketability_breakdown(gs)
    assert set(mb) == {"score", "facility_mult", "reach", "drivers"}
    for d in mb["drivers"]:
        assert set(d) == {"key", "label", "contrib"}
    # drivers are contribution-descending
    contribs = [d["contrib"] for d in mb["drivers"]]
    assert contribs == sorted(contribs, reverse=True)
    # pre-facility sum, clamped at 0.4, times the facility mult == the score
    raw = sum(d["contrib"] for d in mb["drivers"])  # rounded terms
    expected = max(0.4, raw) * mb["facility_mult"]
    # Per-driver 2dp rounding (7 terms) x facility mult loosens the tie.
    assert abs(expected - mb["score"]) <= 0.06


def test_h2h_matrix_shape(env):
    gs, gd, h = env
    _bind(gs, gd)
    region = str(gs.teams[h.user_team].region)
    mx = server_mod._h2h_matrix(gs, region)
    assert set(mx) == {"teams", "rows"}
    n = len(mx["teams"])
    assert len(mx["rows"]) == n
    for i, row in enumerate(mx["rows"]):
        assert len(row["cells"]) == n
        assert row["cells"][i] is None  # diagonal (self) is blank
        for cell in row["cells"]:
            if cell is not None:
                assert set(cell) == {"w", "l", "played"}


def test_results_archive_newest_first(env):
    gs, gd, h = env
    _bind(gs, gd)
    region = str(gs.teams[h.user_team].region)
    res = server_mod._results_archive(gs, region, n=10)
    assert isinstance(res, list) and len(res) <= 10
    for r in res:
        assert set(r) == {
            "week", "stage", "team_a", "team_a_id", "team_b", "team_b_id",
            "score_a", "score_b", "winner_id",
        }
    weeks = [r["week"] for r in res]
    assert weeks == sorted(weeks, reverse=True)  # newest first


def test_squad_profile_shape(env):
    gs, gd, h = env
    sp = server_mod._squad_profile(gs, h.user_team)
    assert set(sp) == {"avg_age", "buckets", "expiries"}
    assert set(sp["buckets"]) == {"youth", "prime", "veteran"}
    assert sum(sp["buckets"].values()) == len(sp["expiries"])
    wl = [e["weeks_left"] for e in sp["expiries"]]
    assert wl == sorted(wl)  # soonest-expiring first


def test_form_trend_is_monotone(env):
    gs, gd, h = env
    trend = server_mod._form_trend(gs, h.user_team)
    wins = [p["wins"] for p in trend]
    assert wins == sorted(wins)  # cumulative wins never decrease
    for i, p in enumerate(trend, start=1):
        assert p["n"] == i


def test_impact_leaders_shape_and_order(env):
    gs, gd, h = env
    _bind(gs, gd)
    imp = server_mod._impact_leaders(gs)
    assert set(imp) == {"clutches", "multikills", "aces", "first_kills"}
    for cat in imp.values():
        assert set(cat) == {"label", "leaders"}
        for l in cat["leaders"]:
            assert set(l) == {"player_id", "value", "handle", "team"}
            assert l["value"] > 0
        vals = [l["value"] for l in cat["leaders"]]
        assert vals == sorted(vals, reverse=True)


def test_staff_effect_lines_department_roles():
    # Codex review: the fallback labelled every non-coach/analyst role as
    # stamina recovery, but psychologist drives confidence and performance
    # coach drives form. Each department role must read its own axis.
    import types
    eff = server_mod._staff_effect_lines
    psy = eff(types.SimpleNamespace(role="psychologist", quality=60.0, specialty=""))
    pc = eff(types.SimpleNamespace(role="performance_coach", quality=70.0, specialty=""))
    phys = eff(types.SimpleNamespace(role="physio", quality=54.0, specialty=""))
    assert "confidence" in psy[0].lower() and "stamina" not in psy[0].lower()
    assert "form" in pc[0].lower() and "stamina" not in pc[0].lower()
    assert "stamina" in phys[0].lower()


def test_objectives_hub_and_rotation_shape(env):
    gs, gd, h = env
    hub = server_mod._objectives_hub(gs, h.user_team)
    assert isinstance(hub, list)
    assert all(set(o) >= {"kind", "label", "state"} for o in hub)
    assert all(o["kind"] in ("board", "sponsor", "award") for o in hub)
    rot = server_mod._rotation_usage(gs, h.user_team)
    assert all(set(r) == {"id", "handle", "maps", "starter", "stamina", "burnout"} for r in rot)
    assert rot == sorted(rot, key=lambda r: (-r["maps"], r["handle"]))
