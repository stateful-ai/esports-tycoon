"""Integrated club-depth rules: windows, registration, series cards, leverage."""

from __future__ import annotations

from esports_sim.manager import campaign, market, series_management
from esports_sim.manager.state import Fixture, GameState, SCHEMA_VERSION
from esports_sim.rng.tree import RngTree


def test_transfer_calendar_has_open_closed_and_locked_periods(game_data) -> None:
    gs = campaign.new_campaign(game_data, seed=404)
    assert market.market_window_status(gs)["kind"] == "opening"

    gs.week = 6
    assert market.market_window_status(gs)["kind"] == "closed"
    gs.week = 7
    assert market.market_window_status(gs)["kind"] == "mid_split"
    gs.phase = "playoffs"
    status = market.market_window_status(gs)
    assert status["kind"] == "roster_lock" and not status["open"]


def test_closed_window_allows_only_emergency_free_agent(game_data) -> None:
    gs = campaign.new_campaign(game_data, seed=405)
    tid = gs.user_team_id
    gs.week = 6
    pid = gs.free_agent_ids[0]
    ok, why = market.can_sign(gs, tid, pid)
    assert not ok and "closed" in why.lower()

    # A team that cannot field five is allowed a narrowly scoped emergency FA.
    gs.teams[tid].player_ids.pop()
    ok, why = market.can_sign(gs, tid, pid)
    assert ok, why


def test_closed_window_prevents_ai_poach_from_dropping_a_player(game_data) -> None:
    gs = campaign.new_campaign(game_data, seed=409)
    gs.week = 6
    before = {
        tid: tuple(team.player_ids) for tid, team in sorted(gs.teams.items())
    }

    class Eager:
        @staticmethod
        def random() -> float:
            return 0.0

        @staticmethod
        def integers(_low, _high=None) -> int:
            return 0

    market.ai_poach_free_agents(gs, game_data, Eager())
    assert {
        tid: tuple(team.player_ids) for tid, team in sorted(gs.teams.items())
    } == before


def test_tournament_six_and_between_map_substitution_are_real(game_data) -> None:
    gs = campaign.new_campaign(game_data, seed=406)
    tid = gs.user_team_id
    opponent = next(
        t.id for t in gs.teams.values() if t.id != tid and t.tier == 1
    )
    sixth = gs.free_agent_ids.pop(0)
    gs.teams[tid].player_ids.append(sixth)
    gs.players[sixth].contract_weeks_left = 40
    starters = campaign.default_five(gs, tid)
    out_pid = starters[-1]
    registered = starters + [sixth]
    ok, why = series_management.register_roster(gs, tid, registered)
    assert ok, why

    fixture = Fixture(
        id="test_series_card",
        week=gs.week,
        stage="semi",
        best_of=3,
        team_a=tid,
        team_b=opponent,
        maps=sorted(game_data.maps)[:3],
    )
    gs.fixtures.append(fixture)
    gs.phase = "playoffs"
    ok, why = series_management.set_directive(
        gs,
        tid,
        fixture.id,
        trigger="always",
        response="reset",
        substitute_in=sixth,
        substitute_out=out_pid,
    )
    assert ok, why

    campaign._sim_fixture(
        gs,
        campaign.runtime_gamedata(gs, game_data),
        RngTree(gs.seed),
        fixture,
    )
    assert fixture.played
    assert any("replaces" in note for note in fixture.series_notes)
    assert tid not in gs.series_directives_by
    assert len(fixture.results) >= 2
    second_map_ids = {line.player_id for line in fixture.results[1].lines}
    assert sixth in second_map_ids
    assert out_pid not in second_map_ids


def test_negotiation_snapshots_visible_causal_leverage(game_data) -> None:
    gs = campaign.new_campaign(game_data, seed=407)
    tid = gs.user_team_id
    gs.set_acting(tid)
    pid = gs.teams[tid].player_ids[0]
    p = gs.players[pid]
    p.form = 75
    p.contract_weeks_left = 4
    ok, why, neg = market.open_negotiation(gs, pid)
    assert ok, why
    assert 5 <= neg.leverage <= 95
    assert 5 <= neg.interest <= 95
    assert neg.deadline_week > gs.week
    assert "strong recent form" in neg.leverage_reasons
    assert "contract close to expiry" in neg.leverage_reasons


def test_v21_save_migrates_new_club_state(game_data, tmp_path) -> None:
    gs = campaign.new_campaign(game_data, seed=408)
    raw = gs.model_dump(mode="json")
    raw["schema_version"] = 21
    for field in (
        "academy_affiliates",
        "academy_levels",
        "academy_reports_by",
        "academy_player_rights",
        "preparation_plans_by",
        "preparation_reports_by",
        "leadership_groups",
        "culture_principles",
        "culture_last_action",
        "leadership_last_change",
        "tournament_rosters",
        "series_directives_by",
    ):
        raw.pop(field, None)
    path = tmp_path / "v21.json"
    import json

    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == SCHEMA_VERSION == 26
    assert loaded.academy_affiliates == {}
    assert loaded.preparation_plans_by == {}
    assert loaded.leadership_groups == {}
