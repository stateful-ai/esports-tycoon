"""Match-review synthesis: determinism, staff-tier gating, and edge cases."""

from __future__ import annotations

import pytest

from esports_sim.manager import advance_week, new_campaign
from esports_sim.manager.market import release_player
from esports_sim.manager.match_review import build_match_review, tactic_adjustment
from esports_sim.manager.state import GamePlan, GameState, StaffMember
from esports_sim.registry import GameData
from esports_sim.schemas import TeamTactics


def _play(gd: GameData, seed: int, weeks: int = 4) -> GameState:
    gs = new_campaign(gd, seed=seed)
    for _ in range(weeks):
        advance_week(gs, gd)
    return gs


def test_review_present_and_grounded(game_data: GameData) -> None:
    gs = _play(game_data, seed=123)
    rv = gs.last_review_by.get(gs.user_team_id)
    assert rv is not None and rv.contested
    assert rv.team_id == gs.user_team_id
    # A real series has a scoreline and at least one diagnosed signal.
    assert rv.your_rounds + rv.their_rounds > 0
    assert rv.working or rv.breaking
    # Every point is well-formed and tagged with an unlock tier.
    for p in rv.working + rv.breaking:
        assert p.tone in ("good", "bad")
        assert 0 <= p.min_tier <= 2
        assert p.den >= 0
    # Won flag agrees with the map score.
    assert rv.won == (rv.your_maps > rv.their_maps)


def test_review_deterministic(game_data: GameData) -> None:
    a = _play(game_data, seed=77)
    b = _play(game_data, seed=77)
    da = {t: rv.model_dump_json() for t, rv in sorted(a.last_review_by.items())}
    db = {t: rv.model_dump_json() for t, rv in sorted(b.last_review_by.items())}
    assert da == db and da  # identical AND non-empty


def test_min_tier_gating_is_monotonic(game_data: GameData) -> None:
    """Filtering points by a higher analyst tier only ever ADDS signals."""
    gs = _play(game_data, seed=77)
    rv = gs.last_review_by[gs.user_team_id]
    seen = rv.working + rv.breaking

    def visible(tier: int) -> set[str]:
        return {p.code for p in seen if p.min_tier <= tier}

    assert visible(0) <= visible(1) <= visible(2)
    # There is genuinely tiered content to gate (tier-0 is a strict subset).
    assert any(p.min_tier > 0 for p in seen)


def test_serializer_respects_tier(game_data: GameData) -> None:
    from esports_sim.web import server

    gs = _play(game_data, seed=77)
    uid = gs.user_team_id
    gs.set_acting(uid)

    # Bare org (no analyst) -> tier 0: only tier-0 signals surface, locked hint.
    gs.staff.pop("analyst", None)
    low = server._last_match_review(gs)
    assert low["tier"] == 0
    assert all(
        p["code"] in {"atk_side", "def_side", "pistol", "player_std", "player_under"}
        for p in low["working"] + low["breaking"]
    )

    # Elite analyst -> tier 3: deeper signals become visible, nothing locked.
    gs.staff["analyst"] = StaffMember(
        id="an", name="Ana", role="analyst", quality=98.0, salary=1, specialty="data"
    )
    hi = server._last_match_review(gs)
    assert hi["tier"] == 3
    assert not hi["locked"]
    assert len(hi["working"]) + len(hi["breaking"]) >= len(low["working"]) + len(low["breaking"])


def test_levers_gated_by_coach(game_data: GameData) -> None:
    from esports_sim.web import server

    # Seed 124: produces slider-type levers on the traced maps (seed 123
    # yields only mechanical/team levers there — probed 123-128, 5/6
    # seeds carry sliders, so this pins a representative one).
    gs = _play(game_data, seed=124)
    uid = gs.user_team_id
    gs.set_acting(uid)
    gs.staff["analyst"] = StaffMember(
        id="an", name="Ana", role="analyst", quality=98.0, salary=1, specialty="data"
    )

    # No coach -> no levers.
    gs.staff.pop("coach", None)
    assert server._last_match_review(gs)["levers"] == []

    # A strong tactical coach -> up to 3 levers, tactical ones lead.
    gs.staff["coach"] = StaffMember(
        id="co", name="K", role="coach", quality=85.0, salary=1, specialty="tactical"
    )
    levers = server._last_match_review(gs)["levers"]
    assert 1 <= len(levers) <= 3
    if any(lv["specialty"] == "tactical" for lv in levers):
        assert levers[0]["specialty"] == "tactical"  # specialty floats to top
    slider_levers = [lv for lv in levers if lv["adjustment"] is not None]
    assert slider_levers
    assert all(lv["tab"] == "tactics" for lv in slider_levers)
    assert all(
        lv["text"].startswith(("Set ", "Keep ")) for lv in slider_levers
    )


def test_tactic_adjustment_uses_staff_skill_and_current_slider() -> None:
    tactics = TeamTactics(pace=51, map_control=50)

    # A developing coach makes a conservative call and a basic analyst rounds
    # it to a broad ten-point target.
    basic = tactic_adjustment(tactics, "atk_tempo", 35.0, 0)
    assert basic == {
        "dial": "pace",
        "label": "Pace",
        "current": 51,
        "target": 60,
        "at_limit": False,
        "reason": "Speed up the attack timing and commit to earlier executes.",
        "coach_step": 10,
        "analyst_precision": 10,
    }

    # An elite coach makes a bolder adjustment; a deep analyst preserves the
    # calibrated point target instead of rounding it away.
    elite = tactic_adjustment(tactics, "atk_tempo", 85.0, 2)
    assert elite["target"] == 71
    assert elite["coach_step"] == 20
    assert elite["analyst_precision"] == 1


def test_tactic_adjustment_calls_out_when_slider_is_already_at_limit() -> None:
    rec = tactic_adjustment(
        TeamTactics(map_control=18), "def_setups", 85.0, 3
    )
    assert rec["target"] == 18
    assert rec["at_limit"] is True
    coarse = tactic_adjustment(
        TeamTactics(map_control=18), "def_setups", 35.0, 0
    )
    assert coarse["target"] == 18  # "keep" never disguises a rounded move
    assert tactic_adjustment(TeamTactics(), "aim_training", 85.0, 3) is None


def _plan_and_play(gd: GameData, seed: int = 99) -> tuple[GameState, str, str]:
    """Set a full game plan for the user's next fixture, sim the week, and
    return (state, user team id, planned focus-target pid)."""
    gs = new_campaign(gd, seed=seed)
    uid = gs.user_team_id
    fx = gs.team_fixture(uid)
    assert fx is not None, "expected a week-1 fixture"
    opp = fx.team_b if fx.team_a == uid else fx.team_a
    target = sorted(gs.teams[opp].player_ids)[0]
    gs.game_plans_by[uid] = GamePlan(
        fixture_id=fx.id,
        aggression=72.0,
        site_focus="a",
        focus_target=target,
        team_talk="fire_up",
    )
    advance_week(gs, gd)
    return gs, uid, target


def test_your_calls_captured_with_plan(game_data: GameData) -> None:
    """The consumed game plan's facts survive in review.calls — dial override
    vs the season identity, validated target, talk with its applied nudge,
    and the resolved prep edge — even though the plan itself is deleted."""
    gs, uid, target = _plan_and_play(game_data)
    rv = gs.last_review_by[uid]
    c = rv.calls
    assert c is not None and c.plan_set
    assert c.dials == {"aggression": 72.0}
    assert set(c.base_dials) == {"aggression"}
    assert c.site_focus == "a"
    assert c.focus_target == target
    assert c.team_talk == "fire_up"
    assert c.talk_avg_delta > 0.0  # fire_up lifts a mid-confidence room
    assert c.prep_edge > 0.0  # a set plan always carries the base edge
    # The plan was consumed at sim time; only the review kept its facts.
    assert uid not in gs.game_plans_by


def test_your_calls_thin_without_plan(game_data: GameData) -> None:
    """Hands-off week: the review still records the (empty) attribution —
    no plan facts, no talk, zero prep edge ('no plan, no payoff')."""
    gs = _play(game_data, seed=123)
    c = gs.last_review_by[gs.user_team_id].calls
    assert c is not None
    assert not c.plan_set and not c.dials and not c.base_dials
    assert c.team_talk == "" and c.talk_avg_delta == 0.0
    assert c.prep_edge == 0.0
    assert not c.prepped_maps_played and not c.prepped_maps_missed
    assert not c.lineup_override


def test_your_calls_serializer_tier_gating(game_data: GameData) -> None:
    """Facts are tier-0; the computed attribution numbers (tactics_fit impact
    delta, applied prep edge) unlock with an analyst — same convention as the
    rest of the card."""
    from esports_sim.web import server

    gs, uid, target = _plan_and_play(game_data)
    gs.set_acting(uid)

    gs.staff.pop("analyst", None)
    low = server._last_match_review(gs)["your_calls"]
    assert low is not None and low["plan_set"]
    assert low["dials"][0]["key"] == "aggression"
    assert low["dials"][0]["impact_delta"] is None  # numbers locked at tier 0
    assert low["prep"]["edge"] is None
    assert low["team_talk"]["approach"] == "fire_up"
    assert low["focus_target"]["player_id"] == target

    gs.staff["analyst"] = StaffMember(
        id="an", name="Ana", role="analyst", quality=98.0, salary=1, specialty="data"
    )
    hi = server._last_match_review(gs)["your_calls"]
    d = hi["dials"][0]
    assert d["planned"] == 72
    assert d["base"] == round(gs.last_review_by[uid].calls.base_dials["aggression"])
    assert isinstance(d["impact_delta"], float)  # tactics_fit-computed, server-side
    assert isinstance(hi["prep"]["edge"], float) and hi["prep"]["edge"] > 0.0
    assert hi["team_talk"]["avg_delta"] == gs.last_review_by[uid].calls.talk_avg_delta


def test_forfeit_is_thin_review(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=123)
    tid = gs.user_team_id
    for pid in list(gs.teams[tid].player_ids):
        release_player(gs, tid, pid)
    advance_week(gs, game_data)
    rv = gs.last_review_by.get(tid)
    assert rv is not None
    assert rv.contested is False
    assert not rv.working and not rv.breaking


def test_build_empty_bundles() -> None:
    rv = build_match_review(1, 2, "fx", "A", "B", 1, [], {})
    assert rv.contested is False
    assert rv.fixture_id == "fx" and rv.season == 1 and rv.week == 2
    assert not rv.working and not rv.breaking


def test_momentum_trace_reconstructs_kills_decay_and_clutch() -> None:
    from esports_sim.schemas import KillEvent, RoundEndEvent, RoundStartEvent
    from esports_sim.sim import constants as C
    from esports_sim.sim.momentum import momentum_trace

    team_of = {"a": "A", "b": "A", "x": "B", "y": "B"}
    events = [
        RoundStartEvent(round_num=1, attacking_team_id="A", defending_team_id="B"),
        KillEvent(killer_id="a", victim_id="x", weapon_id="vandal"),
        KillEvent(killer_id="y", victim_id="b", weapon_id="vandal"),
        RoundEndEvent(round_num=1, winner_id="A", reason="elim"),
    ]
    row = momentum_trace(events, team_of)[0]
    assert row.values["a"] == round(C.MOMENTUM_KILL * C.MOMENTUM_DECAY + C.MOMENTUM_CLUTCH, 4)
    assert row.values["b"] == round(-C.MOMENTUM_DEATH * C.MOMENTUM_DECAY, 4)
