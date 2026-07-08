"""Management-layer invariants: schedule shape, season lifecycle, market
rules, save/load, and campaign determinism."""

from __future__ import annotations

from collections import Counter

import pytest

from esports_sim.manager import advance_week, new_campaign
from esports_sim.manager.market import release_player, sign_player
from esports_sim.manager.schedule import regular_season_weeks, veto_bo3
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=123)


def test_schedule_shape(campaign: GameState) -> None:
    from esports_sim.manager.campaign import (
        LEAGUE_REGIONS,
        TEAMS_PER_REGION,
        TIER2_PER_REGION,
    )

    tier1 = [t for t in campaign.teams.values() if t.tier == 1]
    tier2 = [t for t in campaign.teams.values() if t.tier == 2]
    assert len(tier1) == len(LEAGUE_REGIONS) * TEAMS_PER_REGION
    assert len(tier2) == len(LEAGUE_REGIONS) * TIER2_PER_REGION
    # Parallel leagues: every tier-1 team plays exactly once every week
    # of the franchised calendar (Challengers wraps earlier — 6 teams).
    n_weeks = regular_season_weeks(TEAMS_PER_REGION)
    for week in range(1, n_weeks + 1):
        seen: set[str] = set()
        for f in campaign.fixtures_for_week(week):
            assert f.team_a not in seen and f.team_b not in seen
            seen.update((f.team_a, f.team_b))
        assert {t.id for t in tier1} <= seen or week > n_weeks
    # Each intra-league pair meets exactly twice; regular play never
    # crosses regions or tiers.
    pairs = Counter(
        frozenset((f.team_a, f.team_b))
        for f in campaign.fixtures
        if f.stage == "regular"
    )
    assert all(count == 2 for count in pairs.values())
    for f in campaign.fixtures:
        if f.stage == "regular":
            assert (
                campaign.teams[f.team_a].region == campaign.teams[f.team_b].region
            )
            assert campaign.teams[f.team_a].tier == campaign.teams[f.team_b].tier
            assert f.tier == campaign.teams[f.team_a].tier


def test_full_season_lifecycle(campaign: GameState, game_data: GameData) -> None:
    from esports_sim.manager.campaign import TEAMS_PER_REGION

    n_weeks = regular_season_weeks(TEAMS_PER_REGION)
    for _ in range(n_weeks):
        advance_week(campaign, game_data)
    assert campaign.phase == "playoffs"
    # Regional semis, regional finals, Masters QF/SF/Final = 5 weeks,
    # then Champions QF/SF/Final = 3 more.
    for _ in range(5):
        advance_week(campaign, game_data)
    assert campaign.phase == "playoffs"  # Masters done, Champions drawn
    assert len(campaign.champions_seeds) == 8
    for _ in range(3):
        advance_week(campaign, game_data)
    assert campaign.phase == "offseason"
    assert len(campaign.champions) == 1
    # Both internationals actually happened, cross-region.
    masters = [f for f in campaign.fixtures if f.bracket == "masters"]
    assert len(masters) == 5  # 2 QF + 2 SF + 1 final
    assert all(f.played for f in masters)
    champs = [f for f in campaign.fixtures if f.bracket == "champions"]
    assert len(champs) == 7  # 4 QF + 2 SF + 1 final
    assert all(f.played for f in champs)
    cf = next(f for f in champs if f.stage == "champ_final")
    assert campaign.champions[-1].team_id == cf.winner_id
    # Challengers ran silently underneath: tier-2 fixtures simmed with
    # box scores feeding development, and every t2 player has stats.
    t2 = [f for f in campaign.fixtures if f.tier == 2]
    assert t2 and all(f.played for f in t2 if f.stage == "regular")
    some_t2_team = next(t for t in campaign.teams.values() if t.tier == 2)
    assert any(
        pid in campaign.player_stats for pid in some_t2_team.player_ids
    )
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


def test_veto_bo3_deterministic_and_valid() -> None:
    maps = ["ascent", "bind", "haven", "lotus", "split"]
    ma = {"ascent": 80.0, "bind": 40.0, "haven": 60.0, "lotus": 55.0, "split": 50.0}
    mb = {"ascent": 45.0, "bind": 70.0, "haven": 50.0, "lotus": 65.0, "split": 55.0}
    order1, log1 = veto_bo3(maps, ma, mb, "AAA", "BBB")
    order2, log2 = veto_bo3(maps, ma, mb, "AAA", "BBB")
    assert (order1, log1) == (order2, log2)
    assert len(order1) == 3 and len(set(order1)) == 3
    assert all(m in maps for m in order1)
    # A dumps its worst map, B dumps its worst matchup, picks follow strength.
    assert log1[0] == "AAA ban bind"
    assert log1[1] == "BBB ban ascent"
    assert order1 == ["haven", "lotus", "split"]


def test_talk_once_per_week_and_deterministic(campaign: GameState) -> None:
    from esports_sim.manager import talk

    pid = campaign.teams[campaign.user_team_id].player_ids[0]
    ok, _ = talk.can_talk(campaign, pid)
    assert ok
    topic = talk.topic_for(campaign, pid)
    assert len(topic.options) == 3

    before = campaign.players[pid].morale
    ok, msg, effects = talk.resolve(campaign, pid, topic.options[0].id)
    assert ok and msg
    assert campaign.players[pid].morale == round(
        min(100.0, max(0.0, before + effects["morale"])), 1
    )
    # Second talk the same week is refused.
    ok, why = talk.can_talk(campaign, pid)
    assert not ok and "already" in why


def test_sponsor_deal_lifecycle(campaign: GameState) -> None:
    from esports_sim.manager import sponsors
    from esports_sim.manager.state import SponsorDeal

    team = campaign.teams[campaign.user_team_id]
    campaign.sponsor_offer = SponsorDeal(
        name="Testcorp", kind="performance",
        signing_bonus=100_000, weekly=5_000, per_win=8_000, weeks_left=2,
    )
    before = team.balance
    ok, _ = sponsors.accept_offer(campaign)
    assert ok
    assert team.balance == before + 100_000
    assert campaign.sponsor is not None and campaign.sponsor_offer is None

    # Winning week pays weekly + per-win; deal counts down and expires.
    before = team.balance
    got = sponsors.weekly_tick(campaign, user_won_this_week=True)
    assert got == 13_000 and team.balance == before + 13_000
    got = sponsors.weekly_tick(campaign, user_won_this_week=False)
    assert got == 5_000
    assert campaign.sponsor is None  # 2 weeks elapsed -> expired


def test_staff_hire_and_effects(campaign: GameState) -> None:
    from esports_sim.manager import staff

    assert campaign.staff_candidates, "candidate market seeded at campaign start"
    coach = campaign.staff_candidates["coach"][0]
    ok, _ = staff.hire(campaign, coach.id)
    assert ok
    assert campaign.staff["coach"].id == coach.id
    assert staff.coach_multiplier(campaign) > 1.0
    assert staff.weekly_cost(campaign) == coach.salary
    # Hiring a replacement returns the old coach to the market.
    other = campaign.staff_candidates["coach"][0]
    ok, _ = staff.hire(campaign, other.id)
    assert ok
    assert campaign.staff["coach"].id == other.id
    assert any(c.id == coach.id for c in campaign.staff_candidates["coach"])
    ok, _ = staff.release(campaign, "coach")
    assert ok and "coach" not in campaign.staff
