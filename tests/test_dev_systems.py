"""Player-development overhaul: stats derivation depth, confidence,
dev events, social layer, lineups/bench, staff pool, save migration."""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import development, market, social, staff, training
from esports_sim.manager.campaign import advance_week, new_campaign, runtime_gamedata
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import (
    BuyEvent,
    KillEvent,
    MatchEndEvent,
    MatchStartEvent,
    RoundEndEvent,
    RoundStartEvent,
)
from esports_sim.sim import simulate_match
from esports_sim.sim.stats import PlayerLine, compute_match_stats


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=123)


# ---------------------------------------------------------------------------
# Box-score derivation: the synthetic-log unit tests


P = [f"p{i}" for i in range(5)]  # team t1
Q = [f"q{i}" for i in range(5)]  # team t2
TEAM_OF = {**{p: "t1" for p in P}, **{q: "t2" for q in Q}}
WCLASS = {"classic": "pistol", "vandal": "rifle", "operator": "sniper"}


def _round(num, atk, events, winner, reason="elim"):
    return [
        RoundStartEvent(round_num=num, attacking_team_id=atk, defending_team_id="t2" if atk == "t1" else "t1"),
        *events,
        RoundEndEvent(round_num=num, winner_id=winner, reason=reason),
    ]


def _buys(weapon_by_pid, armor_by_pid=None):
    armor_by_pid = armor_by_pid or {}
    return [
        BuyEvent(player_id=pid, weapon_id=weapon_by_pid.get(pid, "classic"),
                 armor=armor_by_pid.get(pid, 50), spent=0)
        for pid in [*P, *Q]
    ]


def _kill(killer, victim, weapon="vandal", **kw):
    return KillEvent(killer_id=killer, victim_id=victim, weapon_id=weapon, **kw)


def test_stats_depth_from_synthetic_log() -> None:
    events = [
        MatchStartEvent(
            match_id="m", map_id="haven", team_a_id="t1", team_b_id="t2", seed=1,
            agents={pid: "jett" for pid in [*P, *Q]},
        )
    ]
    # R1 (pistol): p0 kills q0 with the classic -> pistol kill, headshot.
    events += _round(
        1, "t1",
        [*_buys({}), _kill("p0", "q0", weapon="classic", headshot=True),
         *[_kill("p0", q) for q in Q[1:]]],
        "t1",
    )
    # R2 (gun round): t1 rifles up (bar p1, who saves on the classic with
    # no armor), t2 stays on pistols (under-gunned). q0 kills a rifler ->
    # eco kill. p1 converts on the save -> save kill. p2 flash-assists
    # p0's kill. p3 dies but p4 trades instantly -> p3 died traded.
    rifles = {p: "vandal" for p in P if p != "p1"}
    events += _round(
        2, "t1",
        [
            *_buys(rifles, armor_by_pid={"p1": 0}),
            _kill("q0", "p0"),
            _kill("p1", "q4", weapon="classic"),
            _kill("p0", "q0", assist_id="p2"),
            _kill("q1", "p3"),
            _kill("p4", "q1", is_trade=True),
        ],
        "t1",
    )
    # R3+: both sides rifled up (no more eco reads). q0 mows down four ->
    # t1 isolated at 1v5; p4 clears the server (5 kills = ace) and wins ->
    # a 1vX clutch.
    all_rifles = {pid: "vandal" for pid in [*P, *Q]}
    events += _round(
        3, "t1",
        [*_buys(all_rifles),
         *[_kill("q0", p) for p in P[:4]],
         *[_kill("p4", q) for q in Q]],
        "t1",
    )
    # R4: engineered 1v1 for p4 (p3 chips in a kill so it isn't an ace).
    events += _round(
        4, "t1",
        [
            *_buys(all_rifles),
            *[_kill("q0", p) for p in P[:3]],
            _kill("p3", "q0"),
            *[_kill("p4", q) for q in Q[1:4]],
            _kill("q4", "p3"),
            _kill("p4", "q4"),
        ],
        "t1",
    )
    events.append(MatchEndEvent(match_id="m", winner_id="t1", score_a=4, score_b=0))

    st = compute_match_stats(events, TEAM_OF, WCLASS)
    p0, p1, p2, p3, p4, q0 = (st.lines[k] for k in ("p0", "p1", "p2", "p3", "p4", "q0"))

    assert p0.pistol_kills == 5 and p0.headshots == 1
    assert q0.eco_kills == 1  # own side on pistols, victims rifled up
    assert p1.save_kills == 1  # classic + no armor on a gun round
    assert p2.assists == 1
    assert p3.traded_deaths == 1 and p4.trade_kills == 1
    assert p4.aces == 1 and p4.clutch_1v3 == 1 and p4.clutch_1v1 == 1
    assert p4.clutches == 1  # legacy counter: 1v2-or-worse only
    assert p0.kills_by_weapon == {"classic": 1, "vandal": 5}
    assert p0.agent_id == "jett"
    # KAST: p2's only contribution in R2 was the assist; it still counts.
    assert p2.kast_rounds >= 1
    # Survivors count toward KAST; p4 survived every round.
    assert p4.kast_rounds == 4 and p4.survived == 4
    assert p4.combat_score > 0
    assert st.lines["q1"].first_deaths == 0  # sanity: q4 died first in R2


# ---------------------------------------------------------------------------
# Development: plans, match XP, events, confidence


def test_individual_focus_overrides_team_week(campaign, game_data) -> None:
    tid = campaign.user_team_id
    team = campaign.teams[tid]
    roster = campaign.roster(tid)
    pinned = roster[0]
    pinned.dev_focus = "mechanical"
    baseline = {a: pinned.attr(a) for a in ("aim_precision", "aim_reactivity", "movement")}
    rng = RngTree(1).derive("t")
    training.apply_training(team, roster, "mental", rng)
    grew = sum(pinned.attr(a) - baseline[a] for a in baseline)
    assert grew > 0, "a pinned mechanical focus trains mechanics on a mental week"


def test_intensity_trades_growth_for_stamina(campaign) -> None:
    tid = campaign.user_team_id
    team = campaign.teams[tid]
    roster = campaign.roster(tid)
    light, intense = roster[0], roster[1]
    light.training_intensity = "light"
    intense.training_intensity = "intense"
    s_light, s_intense = light.stamina, intense.stamina
    training.apply_training(team, roster, "tactical", RngTree(2).derive("t"))
    assert s_light - light.stamina < s_intense - intense.stamina


def test_match_experience_scales_with_youth_and_line() -> None:
    gd = load_all()
    gs = new_campaign(gd, seed=99)
    young = min(gs.players.values(), key=lambda p: (p.age, p.id))
    line = PlayerLine(player_id=young.id, kills=20, first_kills=4, headshots=8,
                      assists=3, clutch_1v2=1, survived=15, first_deaths=3)
    before = dict(young.attributes)
    training.apply_match_experience(young, line, n_rounds=24)
    gained = sum(young.attributes[a] - before[a] for a in before)
    assert gained > 0
    # An empty line teaches nothing.
    idle = gs.players[sorted(gs.players)[0]]
    before = dict(idle.attributes)
    training.apply_match_experience(idle, PlayerLine(player_id=idle.id), 24)
    assert dict(idle.attributes) == before


def test_dev_events_deterministic_and_applied(campaign) -> None:
    snap = campaign.model_dump_json()
    rng = RngTree(campaign.seed).derive("devevents", 1)
    events = development.weekly_dev_events(campaign, rng)
    # Same state + same stream -> same events.
    gs2 = GameState.model_validate_json(snap)
    rng2 = RngTree(gs2.seed).derive("devevents", 1)
    events2 = development.weekly_dev_events(gs2, rng2)
    assert [(e["player_id"], e["kind"]) for e in events] == [
        (e["player_id"], e["kind"]) for e in events2
    ]
    # And the two worlds end up byte-identical.
    assert campaign.model_dump_json() == gs2.model_dump_json()


def test_confidence_moves_and_regresses(campaign, game_data) -> None:
    before = {
        pid: campaign.players[pid].confidence for pid in sorted(campaign.players)
    }
    advance_week(campaign, game_data)
    after = {pid: campaign.players[pid].confidence for pid in sorted(campaign.players)}
    moved = [pid for pid in before if pid in after and before[pid] != after[pid]]
    assert moved, "match results move confidence"
    assert all(5.0 <= v <= 95.0 for v in after.values())


# ---------------------------------------------------------------------------
# Social layer


def test_social_seeding_and_feed(campaign, game_data) -> None:
    fols = [p.followers for p in campaign.players.values()]
    assert all(f >= 500 for f in fols)
    assert max(fols) > 50 * min(fols), "stars are famous, journeymen are not"
    # Seeding is idempotent: a second pass never touches a seeded count.
    snap = {pid: p.followers for pid, p in campaign.players.items()}
    social.seed_followers(campaign)
    assert snap == {pid: p.followers for pid, p in campaign.players.items()}
    advance_week(campaign, game_data)
    assert campaign.social_feed, "a played week writes the feed"
    kinds = {p.kind for p in campaign.social_feed}
    assert "result" in kinds or "hype" in kinds
    assert len(campaign.social_feed) <= social.FEED_CAP


# ---------------------------------------------------------------------------
# Lineups / bench


def test_engine_fields_only_the_dressed_five(campaign, game_data) -> None:
    from esports_sim.manager.campaign import _dressed_gamedata, default_five

    tid = campaign.user_team_id
    team = campaign.teams[tid]
    team.balance += 10_000_000
    while len(team.player_ids) < 7 and campaign.free_agent_ids:
        fa = campaign.free_agent_ids[0]
        ok, why = market.sign_player(campaign, tid, fa)
        assert ok, why
    team.lineup_ids = sorted(team.player_ids)[:5]  # an explicit five
    starters = default_five(campaign, tid)
    assert sorted(starters) == team.lineup_ids
    bench = [pid for pid in team.player_ids if pid not in starters]
    assert len(bench) == 2
    rt = runtime_gamedata(campaign, game_data)
    opp = next(t for t in campaign.teams.values() if t.id != tid and t.tier == 1)
    map_gd = _dressed_gamedata(
        campaign, rt, {tid: starters, opp.id: default_five(campaign, opp.id)}
    )
    events = simulate_match(map_gd, tid, opp.id, sorted(game_data.maps)[0], 7)
    seen = {e.player_id for e in events if e.type == "round.buy"}
    assert set(starters) <= seen
    assert not (set(bench) & seen), "bench players never appear in a match"


def test_bench_treatment_follows_actual_minutes(campaign) -> None:
    """A player rotated in via a per-map override is NOT benched, and a
    default-five player who sat every map IS — bench life keys off who
    actually dressed, not the default lineup (PR review fix)."""
    from esports_sim.manager.campaign import _apply_bench_week

    tid = campaign.user_team_id
    team = campaign.teams[tid]
    team.balance += 10_000_000
    while len(team.player_ids) < 7 and campaign.free_agent_ids:
        ok, why = market.sign_player(campaign, tid, campaign.free_agent_ids[0])
        assert ok, why
    rotated_in = team.player_ids[5]  # outside the default five
    sat_out = team.player_ids[0]  # in the default five, but sat this week
    dressed = set(team.player_ids[1:5]) | {rotated_in}
    st_in = campaign.players[rotated_in].stamina = 50.0
    st_out = campaign.players[sat_out].stamina = 50.0
    mor_out = campaign.players[sat_out].morale

    _apply_bench_week(campaign, {tid: dressed})
    assert campaign.players[rotated_in].stamina == st_in, "played -> no refund"
    assert campaign.players[sat_out].stamina == st_out + 6.0, "sat -> refunded"
    assert campaign.players[sat_out].morale < mor_out, "sat -> wants minutes"

    # A bye week applies no bench treatment at all.
    before = campaign.players[sat_out].stamina
    _apply_bench_week(campaign, {})
    assert campaign.players[sat_out].stamina == before


def test_default_five_filters_stale_and_tops_up(campaign) -> None:
    from esports_sim.manager.campaign import default_five

    tid = campaign.user_team_id
    team = campaign.teams[tid]
    team.balance += 10_000_000
    while len(team.player_ids) < 6 and campaign.free_agent_ids:
        ok, why = market.sign_player(campaign, tid, campaign.free_agent_ids[0])
        assert ok, why
    team.lineup_ids = ["gone_player", team.player_ids[0]]
    five = default_five(campaign, tid)
    assert len(five) == 5 and "gone_player" not in five
    assert team.player_ids[0] in five


# ---------------------------------------------------------------------------
# Save migration: v2 -> v3


def test_v2_save_loads_and_migrates(campaign, tmp_path) -> None:
    data = json.loads(campaign.model_dump_json())
    data["schema_version"] = 2
    # Old per-manager candidate market replaces the pool; old members lack
    # the v3 identity fields.
    pool = data.pop("staff_pool")
    old_members = []
    for m in pool[:3]:
        old_members.append(
            {k: m[k] for k in ("id", "name", "role", "quality", "salary")}
        )
    data["staff_candidates_by"] = {campaign.user_team_id: {"coach": old_members}}
    # Strip every v3-only field a real v2 save wouldn't have.
    for k in (
        "player_map_stats", "player_agent_stats", "team_map_stats",
        "stat_history", "dev_history", "social_feed",
    ):
        data.pop(k)
    for p in data["players"].values():
        for k in ("confidence", "followers", "dev_focus", "training_intensity"):
            p.pop(k)
    path = tmp_path / "v2.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = GameState.load(path)
    assert loaded.schema_version == 3
    migrated_ids = {m["id"] for m in old_members}
    assert migrated_ids <= {m.id for m in loaded.staff_pool}
    assert all(p.confidence == 50.0 for p in loaded.players.values())
    assert all(p.dev_focus == "auto" for p in loaded.players.values())
    from esports_sim.manager.campaign import default_five

    assert all(
        len(default_five(loaded, tid)) <= 5 for tid in sorted(loaded.teams)
    )


# ---------------------------------------------------------------------------
# Analytics gating (server-side)


def test_stats_gating_follows_analytics_tier(campaign, game_data) -> None:
    import esports_sim.web.server as server_mod

    advance_week(campaign, game_data)
    game = server_mod._Game(game_data, "TESTA", gs=campaign)
    server_mod._ctx.set(server_mod._ReqCtx(game, campaign.user_team_id))

    out = server_mod.stats_view()
    assert out["analytics"]["tier"] == 0
    row = out["players"][0]
    assert "acs" not in row and "kast_pct" not in row

    # An elite analyst + a maxed suite unlock everything.
    analyst = max(
        (m for m in campaign.staff_pool if m.role == "analyst"),
        key=lambda m: m.quality,
    )
    campaign.teams[campaign.user_team_id].balance += analyst.salary * 8
    ok, why = staff.hire(campaign, analyst.id)
    assert ok, why
    campaign.facilities["analytics_suite"] = 3
    assert staff.analytics_tier(campaign) == 3

    out = server_mod.stats_view()
    row = out["players"][0]
    assert "acs" in row and "kast_pct" in row and "kills_by_weapon" in row
    assert out["split_keys"] is not None
    map_id = out["split_keys"]["maps"][0]
    split = server_mod.stats_view(split="map", key=map_id)
    assert split["players"], "per-map split has rows at tier 3"
