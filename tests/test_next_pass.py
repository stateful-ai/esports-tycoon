"""Coaching-loop pass: game plans, in-match momentum + tilt spirals,
community sentiment feedback, one-match lineups, and meta patches."""

from __future__ import annotations

import pytest

from esports_sim.manager import development, meta, social
from esports_sim.manager.campaign import (
    WeekReport,
    advance_week,
    new_campaign,
    runtime_gamedata,
)
from esports_sim.manager.state import Fixture, GamePlan, GameState, PatchChange
from esports_sim.registry import load_all
from esports_sim.rng.tree import RngTree
from esports_sim.sim import simulate_match, simulate_match_result
from esports_sim.sim.engine import TeamMatchPlan


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=123)


def _events_blob(events) -> str:
    return "\n".join(e.model_dump_json() for e in events)


# ---------------------------------------------------------------------------
# Engine reach: game plans + momentum are exact no-ops at their defaults


def test_default_plan_is_a_noop(game_data) -> None:
    """An all-defaults TeamMatchPlan produces the byte-identical log the
    bare engine produces — the plan machinery itself is neutral."""
    base = simulate_match(game_data, "team_nexus", "team_vanguard", "haven", 7)
    planned = simulate_match_result(
        game_data, "team_nexus", "team_vanguard", "haven", 7,
        plans={"team_nexus": TeamMatchPlan(), "team_vanguard": TeamMatchPlan()},
    ).events
    assert _events_blob(base) == _events_blob(planned)


def test_prep_edge_reaches_the_attack_policy(game_data) -> None:
    """Preparation is now a policy input, not merely a hidden duel term.

    The old 30-map win-count assertion was an accidental calibration pin for
    the engine-owned IGL.  With site selection now made by a policy, assert
    the durable contract instead: a fully prepared side receives a scout read
    and selects a different deterministic opening route.  The exact duel-term
    test below still verifies that preparation affects combat outcomes too.
    """
    base = simulate_match_result(
        game_data, "team_nexus", "team_vanguard", "haven", 0
    )
    prepared = simulate_match_result(
        game_data,
        "team_nexus",
        "team_vanguard",
        "haven",
        0,
        plans={"team_nexus": TeamMatchPlan(prep_edge=1.5)},
    )

    def opening_routes(events):
        return [
            (event.player_id, event.to_callout)
            for event in events
            if event.type == "round.move"
            and event.from_callout == "attacker_spawn"
        ][:5]

    assert opening_routes(prepared.events) != opening_routes(base.events)


def _mk_sim(gd, plans=None):
    from esports_sim.sim.engine import _MatchSim

    return _MatchSim(gd, "team_nexus", "team_vanguard", "haven", 1, plans=plans)


def test_focus_and_prep_terms_are_exact_in_duel_score(game_data) -> None:
    """The plan terms are precise duel-score deltas: prep is flat, the
    focus target is +FOCUS_TARGET_EDGE against the hunted man and
    -FOCUS_OFF_MALUS against anyone else. Two sims with the same seed
    share day-form draws, so the difference isolates the plan exactly."""
    from esports_sim.sim import constants as C

    victim, other, *_ = sorted(game_data.teams["team_vanguard"].player_ids)
    att = sorted(game_data.teams["team_nexus"].player_ids)[0]
    plan = TeamMatchPlan(focus_target=victim, prep_edge=1.0, counter_edge=0.75)
    sim0 = _mk_sim(game_data)
    sim1 = _mk_sim(game_data, {"team_nexus": plan})

    args = (False, False, False, 0, 5, 5)  # holder/adv/same/tick/alive counts
    base_vs_victim = sim0._duel_score(att, *args, opp_pid=victim)
    base_vs_other = sim0._duel_score(att, *args, opp_pid=other)
    hunted = sim1._duel_score(att, *args, opp_pid=victim)
    off = sim1._duel_score(att, *args, opp_pid=other)
    assert hunted - base_vs_victim == pytest.approx(
        1.0 + 0.75 + C.FOCUS_TARGET_EDGE
    )
    assert off - base_vs_other == pytest.approx(
        1.0 + 0.75 - C.FOCUS_OFF_MALUS
    )
    # The engine clamp holds even if the campaign hands in nonsense.
    sim2 = _mk_sim(
        game_data, {"team_nexus": TeamMatchPlan(prep_edge=99.0)}
    )
    assert sim2._prep["team_nexus"] == pytest.approx(C.PREP_EDGE_CAP)
    sim3 = _mk_sim(
        game_data, {"team_nexus": TeamMatchPlan(counter_edge=-99.0)}
    )
    assert sim3._counter["team_nexus"] == pytest.approx(-C.COUNTER_STRAT_CAP)


def test_momentum_is_invisible_at_default_confidence(game_data) -> None:
    """Momentum accumulates in every match but only amplifies a confidence
    DEVIATION — at the default 50 the log is byte-identical (this is the
    golden gate's guarantee, pinned here as a unit)."""
    a = simulate_match(game_data, "team_nexus", "team_vanguard", "ascent", 3)
    b = simulate_match(game_data, "team_nexus", "team_vanguard", "ascent", 3)
    assert _events_blob(a) == _events_blob(b)


def test_conf_dev_amplifies_deviation_never_creates_one(game_data) -> None:
    """The momentum contract, checked to the decimal: eff = dev + m*SPAN*|dev|
    — zero at confidence 50 for ANY momentum (the golden guarantee), lifted
    on a heater and dimmed on a cold streak off-neutral, in BOTH directions."""
    from esports_sim.sim import constants as C

    gd = game_data
    sim = _mk_sim(gd)
    pid = sorted(gd.teams["team_nexus"].player_ids)[0]
    old = gd.players[pid].confidence
    try:
        # Neutral confidence: momentum multiplies zero.
        gd.players[pid].confidence = 50.0
        sim.momentum[pid] = 1.0
        assert sim._conf_dev(pid) == 0.0
        sim.momentum[pid] = -1.0
        assert sim._conf_dev(pid) == 0.0
        # High confidence: a heater amplifies, a spiral dims.
        gd.players[pid].confidence = 70.0
        sim.momentum[pid] = 0.0
        assert sim._conf_dev(pid) == pytest.approx(20.0)
        sim.momentum[pid] = 1.0
        assert sim._conf_dev(pid) == pytest.approx(20.0 * (1 + C.MOMENTUM_SPAN))
        sim.momentum[pid] = -1.0
        assert sim._conf_dev(pid) == pytest.approx(20.0 * (1 - C.MOMENTUM_SPAN))
        # Low confidence: a heater pulls a shaky player back toward level.
        gd.players[pid].confidence = 30.0
        sim.momentum[pid] = 1.0
        assert sim._conf_dev(pid) == pytest.approx(-20.0 * (1 - C.MOMENTUM_SPAN))
    finally:
        gd.players[pid].confidence = old


def test_kills_and_clutches_move_momentum(game_data) -> None:
    """A full sim leaves real momentum tracks: after a match somebody is
    off zero, everything is clamped, and the golden gate (byte-identical
    logs) already proved none of it leaked at neutral confidence."""
    from esports_sim.sim import constants as C
    from esports_sim.sim.engine import _MatchSim

    sim = _MatchSim(game_data, "team_nexus", "team_vanguard", "haven", 42)
    sim.run()
    assert any(m != 0.0 for m in sim.momentum.values())
    assert all(-C.MOMENTUM_CAP <= m <= C.MOMENTUM_CAP for m in sim.momentum.values())


# ---------------------------------------------------------------------------
# Campaign: plans apply, consume, and keep the campaign deterministic


def _user_fixture(gs: GameState) -> Fixture:
    fx = gs.team_fixture(gs.user_team_id)
    assert fx is not None
    return fx


def test_game_plan_lineup_applies_and_restores(campaign, game_data) -> None:
    gs = campaign
    uid = gs.user_team_id
    team = gs.teams[uid]
    # Give the user a 6th man (properly contracted, so the week's
    # contract tick doesn't release him mid-test).
    fa = gs.free_agent_ids[0]
    gs.free_agent_ids.remove(fa)
    team.player_ids.append(fa)
    gs.players[fa].contract_weeks_left = 20
    gs.players[fa].salary = 2_000
    standing = list(team.player_ids[:5])
    team.lineup_ids = list(standing)

    fx = _user_fixture(gs)
    bench_in = [fa] + standing[:4]  # the 6th man starts, one starter sits
    gs.game_plans_by[uid] = GamePlan(
        fixture_id=fx.id, starter_ids=bench_in, aggression=80.0
    )
    advance_week(gs, game_data)

    played = {ln.player_id for r in fx.results for ln in r.lines}
    assert fa in played, "the one-match lineup actually played"
    assert standing[4] not in played, "the rested starter sat out"
    # The plan was consumed; the default five is untouched, and the plan's
    # single-use map_lineups entries were swept with the played fixture.
    assert uid not in gs.game_plans_by
    assert gs.teams[uid].lineup_ids == standing
    assert not any(k.startswith(f"{uid}|{fx.id}|") for k in gs.map_lineups)


def test_stale_game_plan_expires(campaign, game_data) -> None:
    gs = campaign
    gs.game_plans_by[gs.user_team_id] = GamePlan(fixture_id="nonexistent")
    advance_week(gs, game_data)
    assert gs.user_team_id not in gs.game_plans_by


def test_campaign_with_plan_is_deterministic(game_data) -> None:
    def run() -> str:
        gs = new_campaign(game_data, seed=77)
        fx = gs.team_fixture(gs.user_team_id)
        gs.game_plans_by[gs.user_team_id] = GamePlan(
            fixture_id=fx.id, pace=75.0,
            focus_target=sorted(
                gs.teams[
                    fx.team_b if fx.team_a == gs.user_team_id else fx.team_a
                ].player_ids
            )[0],
        )
        for _ in range(3):
            advance_week(gs, game_data)
        return gs.model_dump_json()

    assert run() == run()


# ---------------------------------------------------------------------------
# Tilt spirals / heaters


def test_tilt_spiral_fires_and_deepens(campaign) -> None:
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    p.confidence, p.form = 20.0, 35.0
    p.attributes["tilt_resistance"] = 10.0
    fired = False
    for i in range(30):
        before = p.confidence
        events = development.weekly_mental_events(gs, RngTree(i).derive("t"))
        mine = [e for e in events if e["player_id"] == p.id]
        if mine:
            fired = True
            assert mine[0]["kind"] == "tilt_spiral"
            assert p.confidence < before
            break
    assert fired, "a fragile 20-confidence player spirals within 30 rolls"


def test_heater_fires_for_hot_player(campaign) -> None:
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    p.confidence, p.form = 80.0, 70.0
    fired = False
    for i in range(30):
        events = development.weekly_mental_events(gs, RngTree(i).derive("t"))
        mine = [e for e in events if e["player_id"] == p.id]
        if mine:
            fired = True
            assert mine[0]["kind"] == "heater"
            break
    assert fired


def test_mental_events_draw_once_per_player(campaign) -> None:
    """Fixed draw budget: rosters in any mental state consume the same
    stream length, so the label stays stable as careers rise and fall."""
    gs = campaign
    events_a = development.weekly_mental_events(gs, RngTree(1).derive("t"))
    for p in gs.roster(gs.user_team_id):
        p.confidence = 15.0
        p.form = 30.0
    events_b = development.weekly_mental_events(gs, RngTree(1).derive("t"))
    # Same stream, same non-user rolls: every non-user event is identical.
    a_rest = [e for e in events_a if e["team_id"] != gs.user_team_id]
    b_rest = [e for e in events_b if e["team_id"] != gs.user_team_id]
    assert a_rest == b_rest


# ---------------------------------------------------------------------------
# Sentiment


def test_sentiment_follows_results_and_feeds_back(campaign, game_data) -> None:
    gs = campaign
    advance_week(gs, game_data)
    played = [f for f in gs.fixtures if f.played and f.winner_id]
    assert played
    f = played[0]
    loser = f.team_b if f.winner_id == f.team_a else f.team_a
    assert gs.sentiment(f.winner_id) > 50.0
    assert gs.sentiment(loser) < 50.0


def test_sentiment_extremes_touch_confidence(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.team_sentiment[tid] = 90.0
    before = [p.confidence for p in gs.roster(tid)]
    report = WeekReport(season=gs.season, week=gs.week, phase="regular")
    social._sentiment_tick(gs, report, [], [], RngTree(0).derive("s"))
    after = [p.confidence for p in gs.roster(tid)]
    assert all(b2 > b1 for b1, b2 in zip(before, after))


# ---------------------------------------------------------------------------
# Meta patches


def test_roll_patch_changes_runtime_agents_only(campaign, game_data) -> None:
    gs = campaign
    note = meta.roll_patch(gs, game_data, RngTree(5).derive("p"), version="1.99")
    assert note is not None and note.lines
    assert gs.agent_patches, "active modifier set is populated"
    rt = runtime_gamedata(gs, game_data)
    changed = False
    for ch in gs.agent_patches:
        base_ab = next(
            a for a in game_data.agents[ch.agent_id].abilities if a.id == ch.ability_id
        )
        rt_ab = next(
            a for a in rt.agents[ch.agent_id].abilities if a.id == ch.ability_id
        )
        if base_ab != rt_ab:
            changed = True
    assert changed, "runtime agents reflect the patch"
    # The shared registry is untouched (the gates' guarantee).
    assert all(
        game_data.agents[a].abilities == load_all().agents[a].abilities
        for a in ("jett", "raze")
    )


def test_patch_clamps_hold(game_data, campaign) -> None:
    gs = campaign
    # Pile absurd deltas on and confirm the applied kit stays in range.
    gs.agent_patches = [
        PatchChange(agent_id="jett", ability_id="jett_cloudburst", field="cost", delta=-9999),
        PatchChange(agent_id="jett", ability_id="jett_cloudburst", field="charges", delta=99),
        PatchChange(agent_id="jett", ability_id="jett_bladestorm", field="ult_points", delta=-99),
    ]
    rt = runtime_gamedata(gs, game_data)
    cloud = next(a for a in rt.agents["jett"].abilities if a.id == "jett_cloudburst")
    blade = next(a for a in rt.agents["jett"].abilities if a.id == "jett_bladestorm")
    assert cloud.cost >= 0 and 1 <= cloud.charges <= 3
    assert blade.ult_points is not None and 4 <= blade.ult_points <= 9


def test_patched_campaign_saves_and_reloads(campaign, game_data, tmp_path) -> None:
    gs = campaign
    meta.roll_patch(gs, game_data, RngTree(5).derive("p"), version="1.99")
    fx = gs.team_fixture(gs.user_team_id)
    gs.game_plans_by[gs.user_team_id] = GamePlan(fixture_id=fx.id, map_control=70.0)
    gs.team_sentiment[gs.user_team_id] = 61.0
    path = tmp_path / "save.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert loaded.model_dump_json() == gs.model_dump_json()


# ---------------------------------------------------------------------------
# Plan re-validation at sim time (stored plans are never trusted)


def test_fixture_plans_revalidate_against_live_state(campaign) -> None:
    from esports_sim.manager.campaign import (
        PREP_EDGE_BASE,
        PREP_EDGE_SPAN,
        _fixture_plans,
    )

    gs = campaign
    uid = gs.user_team_id
    fx = gs.team_fixture(uid)
    opp_id = fx.team_b if fx.team_a == uid else fx.team_a
    opp = gs.teams[opp_id]

    # A target on the opponent's roster but BENCHED keeps the plan's
    # target (the tax-without-edge counterplay); one who LEFT the roster
    # is nulled; a lineup with a departed player is discarded whole.
    target = sorted(opp.player_ids)[0]
    gone = "player_who_left"
    gs.game_plans_by[uid] = GamePlan(
        fixture_id=fx.id, focus_target=target, pace=0.0,
        starter_ids=[gone] + sorted(gs.teams[uid].player_ids)[:4],
    )
    gs.teams[opp_id].tactics.pace = 100.0
    gs.scout_progress_by.setdefault(uid, {})[opp_id] = 0.5
    plans, lineups = _fixture_plans(gs, fx)
    assert plans[uid].focus_target == target
    assert uid not in lineups, "a lineup with a departed player is discarded"
    assert plans[uid].prep_edge == pytest.approx(PREP_EDGE_BASE + PREP_EDGE_SPAN * 0.5)
    assert plans[uid].counter_edge == pytest.approx(1.875)

    # Same plan after the target leaves the roster entirely: nulled.
    opp.player_ids.remove(target)
    plans, _ = _fixture_plans(gs, fx)
    assert plans[uid].focus_target is None
    opp.player_ids.insert(0, target)

    # Prep edge scales with scouting: unscouted opponent = the baseline.
    gs.scout_progress_by[uid][opp_id] = 0.0
    plans, _ = _fixture_plans(gs, fx)
    assert plans[uid].prep_edge == pytest.approx(PREP_EDGE_BASE)


# ---------------------------------------------------------------------------
# Offseason contracts: patch-before-reset, sentiment cooling, plan sweep


def test_offseason_patch_is_usage_driven_and_state_resets(game_data) -> None:
    gs = new_campaign(game_data, seed=42)
    gd = game_data
    # Run a full season into the offseason tick.
    guard = 0
    while gs.phase != "offseason" and guard < 60:
        advance_week(gs, gd)
        guard += 1
    assert gs.phase == "offseason"
    usage_before = set()
    for by_agent in gs.player_agent_stats.values():
        usage_before.update(k for k, v in by_agent.items() if v.maps > 0)
    assert usage_before, "a played season has per-agent usage"
    gs.game_plans_by[gs.user_team_id] = GamePlan(fixture_id="whatever")
    gs.team_sentiment[gs.user_team_id] = 80.0

    advance_week(gs, gd)  # the offseason tick

    # The offseason patch shipped, stamped with the NEW season's version,
    # and its nerfs read the season's real pick rates — which only works
    # if roll_patch ran BEFORE the per-agent splits were reset.
    note = gs.patch_history[-1]
    assert note.version == f"{gs.season}.00"
    nerfed = [
        ch.agent_id
        for ch in gs.agent_patches
        if any(f"({'nerf'})" in ln and gd.agents[ch.agent_id].display_name in ln
               for ln in note.lines)
    ]
    assert any(a in usage_before for a in nerfed), (
        "offseason nerfs target agents that were actually played"
    )
    assert gs.player_agent_stats == {}, "splits reset after the patch read them"
    # The break sweeps plans and cools sentiment halfway to neutral.
    assert gs.game_plans_by == {}
    assert gs.team_sentiment[gs.user_team_id] == pytest.approx(65.0)

    # The new season's first social tick posts the break patch — under
    # this save's own balance-watch outlet (media voices are per-save).
    advance_week(gs, gd)
    patch_voice = social.media_voices(gs)["patch"]
    assert any(
        p.author == patch_voice and note.version in p.text
        for p in gs.social_feed
    ), "offseason patch gets its balance-watch post in the new season's week 1"


def test_heater_growth_can_fire_milestones(campaign) -> None:
    """A heater's follower bump lands BEFORE the milestone check, so a
    boundary it crosses still produces the milestone post + confidence.
    Only landmarks >= MILESTONE_POST_FLOOR post (smaller crossings just
    nudge confidence — the feed stays out of "thanks for 25K" territory)."""
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    p.followers = 99_990  # ambient drift + heater growth crosses 100K
    conf_before = p.confidence
    report = WeekReport(season=gs.season, week=gs.week, phase="regular")
    mental = [{"team_id": gs.user_team_id, "player_id": p.id,
               "kind": "heater", "headline": "x"}]
    social.weekly_tick(gs, report, [], RngTree(3).derive("s"), mental_events=mental)
    assert p.followers >= 100_000
    assert any(
        po.kind == "milestone" and po.author_id == p.id for po in gs.social_feed
    ), "the 100K milestone post fired on heater-driven growth"

    # A small landmark still boosts confidence but does NOT post.
    q = gs.roster(gs.user_team_id)[1]
    q.followers = 9_990
    conf_before = q.confidence
    report2 = WeekReport(season=gs.season, week=gs.week + 1, phase="regular")
    social.weekly_tick(gs, report2, [], RngTree(4).derive("s"))
    assert q.followers >= 10_000
    assert q.confidence > conf_before, "small landmark still nudges belief"
    assert not any(
        po.kind == "milestone" and po.author_id == q.id for po in gs.social_feed
    ), "sub-100K landmarks stay off the feed"


# ---------------------------------------------------------------------------
# Web endpoints (thin-serializer checks)


def test_gameplan_endpoints(campaign, game_data) -> None:
    import esports_sim.web.server as server_mod

    gs = campaign
    game = server_mod._Game(game_data, "TESTB", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))

    out = server_mod.gameplan_view()
    assert out["fixture"] is not None
    assert out["plan"] is None
    assert out["prep_edge"] >= 0.3
    assert out["counter"]["opponent_edge"] is None
    assert out["counter"]["max_edge"] > 0.0
    assert len([r for r in out["opponent_roster"] if r["is_starter"]]) == 5

    opp = out["fixture"]["opponent"]["id"]
    target = sorted(gs.teams[opp].player_ids)[0]
    body = server_mod.GamePlanBody(pace=75.0, focus_target=target)
    r = server_mod.set_gameplan(body)
    assert r["ok"]
    out = server_mod.gameplan_view()
    assert out["plan"] is not None and out["plan"]["pace"] == 75.0
    assert "meta_edge" in out["counter"]
    assert out["counter"]["opponent_edge"] is None
    gs.scout_progress[opp] = 0.5
    revealed = server_mod.gameplan_view()["counter"]
    assert revealed["opponent_revealed"] is True
    assert revealed["opponent_edge"] is not None

    r = server_mod.set_gameplan(server_mod.GamePlanBody(clear=True))
    assert r["ok"]
    assert server_mod.gameplan_view()["plan"] is None


def test_gameplan_rejects_bad_input(campaign, game_data) -> None:
    import esports_sim.web.server as server_mod
    from fastapi import HTTPException

    gs = campaign
    game = server_mod._Game(game_data, "TESTC", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))

    with pytest.raises(HTTPException):
        server_mod.set_gameplan(server_mod.GamePlanBody(focus_target="nobody"))
    with pytest.raises(HTTPException):
        server_mod.set_gameplan(server_mod.GamePlanBody(starter_ids=["a", "b"]))
    with pytest.raises(HTTPException):
        server_mod.set_gameplan(server_mod.GamePlanBody(site_focus="z"))
    with pytest.raises(HTTPException):
        server_mod.set_gameplan(server_mod.GamePlanBody(pace=float("nan")))
