"""Sandbox scenario starts (manager/scenarios.py): each preset applies to
the user's org only, campaign determinism holds (same seed + scenario ->
byte-identical GameState), the choice is chronicled, and the web layer
validates the pick."""

from __future__ import annotations

import pytest

from esports_sim.manager import economy, new_campaign, scenarios, staff, telemetry
from esports_sim.manager.campaign import advance_week
from esports_sim.manager.market import player_quality
from esports_sim.registry import GameData

UID = "team_nexus"
SEED = 7


@pytest.fixture(scope="module")
def baseline(game_data: GameData):
    """The classic (no-scenario) world at SEED — read-only in every test."""
    return new_campaign(game_data, seed=SEED, user_team_id=UID)


def _world(game_data: GameData, scenario: str):
    return new_campaign(game_data, seed=SEED, user_team_id=UID, scenario=scenario)


# -- registry / validation ------------------------------------------------------


def test_options_shape() -> None:
    opts = scenarios.options()
    assert len(opts) == 4
    assert [o["id"] for o in opts] == list(scenarios.SCENARIOS)
    for o in opts:
        assert set(o) == {"id", "name", "blurb"}
        assert o["name"] and o["blurb"]
        # CLI prints these lines; keep them cp1252-console-safe.
        (o["name"] + o["blurb"]).encode("ascii")


def test_unknown_scenario_and_legacy_mode_are_rejected(game_data: GameData) -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        new_campaign(game_data, seed=SEED, user_team_id=UID, scenario="nope")
    with pytest.raises(ValueError, match="sandbox"):
        new_campaign(
            game_data, seed=SEED, user_team_id=UID,
            mode="legacy", scenario="crisis_club",
        )


# -- each preset applies ---------------------------------------------------------


def test_insolvent_giant_applies(game_data: GameData, baseline) -> None:
    gs = _world(game_data, "insolvent_giant")
    team = gs.teams[UID]
    assert team.reputation >= scenarios.GIANT_REPUTATION
    assert team.fan_count >= scenarios.GIANT_FAN_COUNT
    assert team.balance < 0  # deep in the red, above the insolvency floor
    assert team.balance > economy.INSOLVENCY_FLOOR
    payroll = sum(p.salary for p in gs.roster(UID))
    base_payroll = sum(p.salary for p in baseline.roster(UID))
    assert payroll >= 2 * base_payroll  # bloated wage bill
    # ~20 weeks of cash at the current burn (acting defaults to the user).
    weeks = economy.weeks_until_insolvent(gs, staff.weekly_cost(gs))
    assert weeks is not None
    assert 10 <= weeks <= scenarios.RUNWAY_WEEKS


def test_youth_project_applies(game_data: GameData) -> None:
    gs = _world(game_data, "youth_project")
    roster = gs.roster(UID)
    assert all(p.age <= 20 for p in roster)
    # Real upside: potential clears current quality by a margin on average.
    edges = [p.potential - player_quality(p) for p in roster]
    assert sum(edges) / len(edges) >= 6.0
    assert all(e >= 0.0 for e in edges)
    assert gs.teams[UID].balance <= scenarios.YOUTH_MAX_BUDGET
    fac = gs.facilities_by.get(UID, {})
    assert fac.get("training_center", 0) >= scenarios.YOUTH_FACILITY_LEVEL
    assert gs.academy_levels.get(UID, 0) >= scenarios.YOUTH_ACADEMY_LEVEL


def test_crisis_club_applies(game_data: GameData) -> None:
    gs = _world(game_data, "crisis_club")
    team = gs.teams[UID]
    assert team.chemistry <= scenarios.CRISIS_CHEMISTRY
    assert team.reputation <= scenarios.CRISIS_REPUTATION
    assert team.balance <= scenarios.CRISIS_MAX_BUDGET
    assert gs.sentiment(UID) == scenarios.CRISIS_SENTIMENT
    for p in gs.roster(UID):
        assert p.morale <= scenarios.CRISIS_MORALE_BASE[1]
        assert p.confidence <= scenarios.CRISIS_CONFIDENCE_BASE[1]


def test_superteam_headache_applies(game_data: GameData, baseline) -> None:
    gs = _world(game_data, "superteam_headache")
    roster = gs.roster(UID)
    qualities = [player_quality(p) for p in roster]
    assert sum(qualities) / len(qualities) >= scenarios.SUPER_TARGET_QUALITY[0] - 2
    assert all(
        any(t in p.personality_tags for t in scenarios.SUPER_CLASH_TAGS)
        for p in roster
    )
    payroll = sum(p.salary for p in roster)
    base_payroll = sum(p.salary for p in baseline.roster(UID))
    assert payroll >= 2.5 * base_payroll
    assert gs.teams[UID].chemistry <= scenarios.SUPER_CHEMISTRY


# -- scope, determinism, records -------------------------------------------------


def test_scenario_touches_only_the_user_org(game_data: GameData, baseline) -> None:
    gs = _world(game_data, "superteam_headache")
    user_pids = set(baseline.teams[UID].player_ids)
    for tid in baseline.teams:
        if tid == UID:
            continue
        assert gs.teams[tid] == baseline.teams[tid]
    for pid in baseline.players:
        if pid not in user_pids:
            assert gs.players[pid] == baseline.players[pid]


def test_same_seed_same_scenario_is_byte_identical(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=11, user_team_id=UID, scenario="crisis_club")
    b = new_campaign(game_data, seed=11, user_team_id=UID, scenario="crisis_club")
    assert a.model_dump_json() == b.model_dump_json()
    plain = new_campaign(game_data, seed=11, user_team_id=UID)
    assert a.model_dump_json() != plain.model_dump_json()


def test_scenario_is_chronicled_and_action_kind_registered(
    game_data: GameData,
) -> None:
    gs = _world(game_data, "youth_project")
    notes = [e for e in gs.chronicle if e.kind == "scenario"]
    assert len(notes) == 1
    assert notes[0].team_id == UID
    assert notes[0].data.get("scenario") == "youth_project"
    assert "Youth project" in notes[0].text
    # The web/CLI layer records the pick with this kind — it must exist.
    telemetry.record_action(
        gs, "scenario_start", {"scenario": "youth_project"},
        team_id=UID, source="cli",
    )
    rec = gs.action_log[-1]
    assert rec.kind == "scenario_start"
    assert rec.params == {"scenario": "youth_project"}


def test_scenario_world_ticks(game_data: GameData) -> None:
    """A scenario campaign advances through a normal week without issue."""
    gs = new_campaign(game_data, seed=3, user_team_id=UID, scenario="insolvent_giant")
    advance_week(gs, game_data)
    assert gs.week == 2
    assert gs.teams[UID].balance < 0  # still digging out


def test_new_game_endpoint_validates_scenario() -> None:
    fastapi = pytest.importorskip("fastapi")
    import esports_sim.web.server as server_mod

    with pytest.raises(fastapi.HTTPException) as exc:
        server_mod.new_game(server_mod.NewGameBody(scenario="nope"))
    assert exc.value.status_code == 422
    with pytest.raises(fastapi.HTTPException) as exc:
        server_mod.new_game(
            server_mod.NewGameBody(scenario="crisis_club", game_mode="legacy")
        )
    assert exc.value.status_code == 422
