"""Actionable analyst mail, critical talks, and AI GM archetypes."""

from __future__ import annotations

import json

import numpy as np

from esports_sim.manager import gm_personalities, inbox, market, new_campaign, talk
from esports_sim.manager.match_review import _walk_map
from esports_sim.manager.state import (
    SCHEMA_VERSION,
    GameState,
    MatchReview,
    ReviewPoint,
    StaffMember,
)
from esports_sim.schemas import RoundEndEvent, RoundStartEvent, SpikePlantEvent


def test_site_retake_counts_feed_an_actionable_analyst_digest(game_data) -> None:
    gs = new_campaign(game_data, seed=910)
    tid = gs.user_team_id
    gs.set_acting(tid)
    gs.staff["analyst"] = StaffMember(
        id="analyst", name="Mara", role="analyst", quality=80, salary=1,
    )
    gs.staff["coach"] = StaffMember(
        id="coach", name="Ivo", role="coach", quality=75, salary=1,
    )
    gs.teams[tid].tactics.util_discipline = 30

    counters = {
        key: 0 for key in (
            "atk_rounds", "atk_won", "def_rounds", "def_won",
            "pistol_played", "pistol_won", "plants", "plants_won",
            "opp_plants", "retakes_won", "eco_rounds", "eco_won",
        )
    }
    sites: dict[str, list[int]] = {}
    opponent = next(x for x in sorted(gs.teams) if x != tid)
    team_of = {"enemy": opponent}
    events = []
    for round_num in range(3, 7):
        events.extend([
            RoundStartEvent(
                round_num=round_num, attacking_team_id=opponent,
                defending_team_id=tid,
            ),
            SpikePlantEvent(player_id="enemy", callout_id="a_site"),
            RoundEndEvent(
                round_num=round_num,
                winner_id=tid if round_num == 3 else opponent,
                reason="spike_defused" if round_num == 3 else "spike_detonation",
            ),
        ])
    _walk_map(None, events, team_of, tid, opponent, {}, counters, sites)
    assert sites == {"A": [1, 4]}

    gs.last_review_by[tid] = MatchReview(
        fixture_id="fx-retakes", season=1, week=1, team_id=tid,
        opp_id=opponent,
        breaking=[ReviewPoint(
            code="retake_site", category="retake", tone="bad", min_tier=2,
            value=0.25, num=1, den=4, weight=1.0,
            lever_code="retake_site", site="A",
        )],
    )
    items = inbox._analytics_items(gs, 1, 1)
    assert len(items) == 1
    _priority, item = items[0]
    assert item.category == "analytics"
    assert "lost 3/4 (75%) of A-site retakes" in item.body
    assert "Utility discipline is 30; move it toward" in item.body
    assert item.tab == "tactics"


def test_crisis_mistake_creates_a_real_transfer_request(game_data, tmp_path) -> None:
    gs = new_campaign(game_data, seed=911)
    tid = gs.user_team_id
    gs.set_acting(tid)
    pid = gs.teams[tid].player_ids[0]
    player = gs.players[pid]
    player.morale = 10
    before = int(market.org_player_valuation(gs, tid, pid, "sell")["value"])

    assert talk.topic_for(gs, pid).id == "crisis"
    ok, message, effects = talk.resolve(gs, pid, "bench_ultimatum")
    assert ok and "leave" in message
    assert effects["transfer_request"] == 1.0
    assert pid in gs.transfer_requests_by
    assert market.transfer_ask(gs, pid) < before
    assert any(
        row["label"] == "active transfer request" and row["delta"] < 0
        for row in market.transfer_ask_breakdown(gs, pid)
    )
    renewed, why = market.renew_contract(gs, tid, pid)
    assert not renewed and "transfer request" in why

    path = tmp_path / "critical-talk.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert loaded.transfer_requests_by[pid].reason == "manager issued a bench ultimatum"
    assert loaded.schema_version == SCHEMA_VERSION


def test_ai_gm_archetypes_are_stable_and_scapegoater_changes_course(game_data) -> None:
    gs = new_campaign(game_data, seed=912)
    ai_tier1 = [
        tid for tid in sorted(gs.teams)
        if gs.teams[tid].tier == 1 and not gs.is_human(tid)
    ]
    profiles = {tid: gm_personalities.profile(gs, tid) for tid in ai_tier1}
    assert profiles == {tid: gm_personalities.profile(gs, tid) for tid in ai_tier1}
    ids = {row["id"] for row in profiles.values()}
    assert {"spender", "scapegoater"} <= ids
    assert gm_personalities.transfer_appetite("spender", quiet=False) > (
        gm_personalities.transfer_appetite("loyalist", quiet=False)
    )
    assert gm_personalities.free_agent_salary_multiplier("spender") > 1.0

    scapegoater = next(tid for tid, row in profiles.items() if row["id"] == "scapegoater")
    losses = [f for f in gs.fixtures if scapegoater in (f.team_a, f.team_b)][:2]
    for fixture in losses:
        opponent = fixture.team_b if fixture.team_a == scapegoater else fixture.team_a
        fixture.played = True
        fixture.winner_id = opponent
    before = gs.teams[scapegoater].tactics.model_dump()
    old_coach = gs.staff_by[scapegoater]["coach"]
    gm_personalities.weekly_tick(gs, np.random.default_rng(12))
    assert gs.ai_gm_coach_changes_by[scapegoater] == 1
    assert gs.teams[scapegoater].tactics.model_dump() != before
    new_coach = gs.staff_by[scapegoater]["coach"]
    assert new_coach.id != old_coach.id
    assert old_coach in gs.staff_pool
    assert new_coach not in gs.staff_pool
    assert any(old_coach.name in line and new_coach.name in line for line in gs.news)
    gm_personalities.weekly_tick(gs, np.random.default_rng(12))
    assert gs.ai_gm_coach_changes_by[scapegoater] == 1


def test_v26_save_migrates_new_management_state(game_data, tmp_path) -> None:
    gs = new_campaign(game_data, seed=913)
    raw = json.loads(gs.model_dump_json())
    raw["schema_version"] = 26
    raw.pop("transfer_requests_by")
    raw.pop("ai_gm_coach_changes_by")
    raw.pop("ai_gm_last_action_week_by")
    path = tmp_path / "v26.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == SCHEMA_VERSION
    assert loaded.transfer_requests_by == {}
    assert loaded.ai_gm_coach_changes_by == {}
