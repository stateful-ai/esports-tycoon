"""Management-layer invariants: schedule shape, season lifecycle, market
rules, save/load, and campaign determinism."""

from __future__ import annotations

from collections import Counter

import pytest

from esports_sim.manager import advance_week, new_campaign
from esports_sim.manager.market import release_player, sign_player
from esports_sim.manager.schedule import regular_season_weeks
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=123)


def test_schedule_shape(campaign: GameState) -> None:
    n_teams = len(campaign.teams)
    n_weeks = regular_season_weeks(n_teams)
    # One match per team per week.
    for week in range(1, n_weeks + 1):
        seen: set[str] = set()
        for f in campaign.fixtures_for_week(week):
            assert f.team_a not in seen and f.team_b not in seen
            seen.update((f.team_a, f.team_b))
        assert len(seen) == n_teams
    # Each pair meets exactly twice.
    pairs = Counter(
        frozenset((f.team_a, f.team_b))
        for f in campaign.fixtures
        if f.stage == "regular"
    )
    assert all(count == 2 for count in pairs.values())


def test_full_season_lifecycle(campaign: GameState, game_data: GameData) -> None:
    n_weeks = regular_season_weeks(len(campaign.teams))
    for _ in range(n_weeks):
        advance_week(campaign, game_data)
    assert campaign.phase == "playoffs"
    for _ in range(2):
        advance_week(campaign, game_data)
    assert campaign.phase == "offseason"
    assert len(campaign.champions) == 1
    advance_week(campaign, game_data)  # offseason tick
    assert campaign.phase == "regular"
    assert campaign.season == 2
    assert campaign.week == 1
    # Every regular fixture is fresh for the new season.
    assert all(not f.played for f in campaign.fixtures)
    # AI rosters stayed legal all season.
    for tid, team in campaign.teams.items():
        if tid != campaign.user_team_id:
            assert len(team.player_ids) == 5, f"{tid} has {len(team.player_ids)}"


def test_campaign_determinism(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=99)
    b = new_campaign(game_data, seed=99)
    for _ in range(6):
        advance_week(a, game_data)
        advance_week(b, game_data)
    assert a.model_dump_json() == b.model_dump_json()


def test_save_load_roundtrip(
    campaign: GameState, game_data: GameData, tmp_path
) -> None:
    for _ in range(2):
        advance_week(campaign, game_data)
    path = tmp_path / "save.json"
    campaign.save(path)
    loaded = GameState.load(path)
    assert loaded.model_dump_json() == campaign.model_dump_json()
    # A loaded save must continue exactly like the original.
    advance_week(campaign, game_data)
    advance_week(loaded, game_data)
    assert loaded.model_dump_json() == campaign.model_dump_json()


def test_market_sign_and_release(campaign: GameState) -> None:
    tid = campaign.user_team_id
    team = campaign.teams[tid]
    # Roster full: signing must be refused.
    fa = campaign.free_agent_ids[0]
    ok, why = sign_player(campaign, tid, fa)
    assert not ok and "full" in why

    victim = team.player_ids[0]
    balance_before = campaign.teams[tid].balance
    salary = campaign.players[victim].salary
    ok, _ = release_player(campaign, tid, victim)
    assert ok
    assert len(team.player_ids) == 4
    assert victim in campaign.free_agent_ids
    assert campaign.teams[tid].balance == balance_before - salary * 6

    ok, _ = sign_player(campaign, tid, fa)
    assert ok
    assert len(team.player_ids) == 5
    assert fa not in campaign.free_agent_ids
    assert campaign.players[fa].contract_weeks_left > 0


def test_forfeit_when_roster_empty(campaign: GameState, game_data: GameData) -> None:
    tid = campaign.user_team_id
    for pid in list(campaign.teams[tid].player_ids):
        release_player(campaign, tid, pid)
    report = advance_week(campaign, game_data)
    mine = next(f for f in report.fixtures if tid in (f.team_a, f.team_b))
    assert mine.played
    assert mine.winner_id != tid
