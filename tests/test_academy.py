"""Academy affiliates: deterministic pairing, movement, intake and growth."""

from __future__ import annotations

import pytest

from esports_sim.manager import academy, new_campaign
from esports_sim.manager.state import GameState, MapResult, PlayerLineSnap
from esports_sim.registry import GameData


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    gs = new_campaign(game_data, seed=123)
    academy.seed_affiliates(gs)
    return gs


def test_affiliates_are_same_region_balanced_and_deterministic(
    game_data: GameData,
) -> None:
    first = new_campaign(game_data, seed=123)
    second = new_campaign(game_data, seed=123)
    mapping = academy.seed_affiliates(first)
    assert mapping == academy.seed_affiliates(second)

    tier1 = sorted(team.id for team in first.teams.values() if team.tier == 1)
    assert sorted(mapping) == tier1
    for parent_tid, affiliate_tid in mapping.items():
        assert first.teams[parent_tid].region == first.teams[affiliate_tid].region
        assert first.teams[affiliate_tid].tier == 2

    for region in first.regions():
        parents = sorted(
            tid for tid in tier1 if str(first.teams[tid].region) == region
        )
        affiliates = sorted(
            team.id
            for team in first.teams.values()
            if team.tier == 2 and str(team.region) == region
        )
        assigned = [mapping[tid] for tid in parents]
        assert len(set(assigned[: len(affiliates)])) == len(affiliates)
        counts = [assigned.count(tid) for tid in affiliates]
        assert max(counts) - min(counts) <= 1


def test_promote_and_send_down_obey_roster_and_age_rules(campaign: GameState) -> None:
    parent_tid = sorted(campaign.academy_affiliates)[0]
    affiliate_tid = academy.affiliate_for(campaign, parent_tid)
    assert affiliate_tid is not None
    affiliate = campaign.teams[affiliate_tid]

    player_id = next(
        pid
        for pid in sorted(campaign.free_agent_ids)
        if campaign.players[pid].age <= academy.ACADEMY_MAX_AGE
    )
    campaign.free_agent_ids.remove(player_id)
    affiliate.player_ids.append(player_id)
    campaign.academy_player_rights[player_id] = parent_tid
    campaign.players[player_id].roster_role = "academy"

    assert academy.can_move(campaign, parent_tid, player_id, "promote") == (True, "")
    ok, _ = academy.move_player(campaign, parent_tid, player_id, "promote")
    assert ok
    assert player_id in campaign.teams[parent_tid].player_ids
    assert player_id not in affiliate.player_ids
    assert campaign.players[player_id].roster_role == "bench"

    blocked = lambda _gs, _tid: (False, "registration window closed")
    assert academy.can_move(
        campaign, parent_tid, player_id, "send_down", window_check=blocked
    ) == (False, "registration window closed")

    ok, _ = academy.move_player(campaign, parent_tid, player_id, "send_down")
    assert ok
    assert player_id in affiliate.player_ids
    assert campaign.players[player_id].roster_role == "academy"

    veteran_id = next(
        pid
        for pid in sorted(campaign.teams[parent_tid].player_ids)
        if campaign.players[pid].age > academy.ACADEMY_MAX_AGE
    )
    ok, why = academy.can_move(campaign, parent_tid, veteran_id, "send_down")
    assert not ok and "23 or younger" in why


def test_offseason_intake_is_deterministic_and_idempotent(
    game_data: GameData,
) -> None:
    first = new_campaign(game_data, seed=987)
    second = new_campaign(game_data, seed=987)
    academy.seed_affiliates(first)
    academy.seed_affiliates(second)
    for gs in (first, second):
        # Exercise every investment tier without privileging the human org.
        for index, parent_tid in enumerate(sorted(gs.academy_levels)):
            gs.academy_levels[parent_tid] = 1 + index % 3

    free_before = set(first.free_agent_ids)
    reports = academy.offseason_intake(first)
    academy.offseason_intake(second)
    assigned_first = {
        tid: tuple(report["player_ids"])
        for tid, rows in first.academy_reports_by.items()
        for report in rows
        if report["kind"] == "intake"
    }
    assigned_second = {
        tid: tuple(report["player_ids"])
        for tid, rows in second.academy_reports_by.items()
        for report in rows
        if report["kind"] == "intake"
    }
    assert reports
    assert assigned_first == assigned_second
    moved = {pid for ids in assigned_first.values() for pid in ids}
    assert moved
    assert moved <= free_before
    assert all(first.players[pid].age <= academy.ACADEMY_MAX_AGE for pid in moved)
    assert all(first.players[pid].roster_role == "academy" for pid in moved)

    state_after = first.model_dump_json()
    assert academy.offseason_intake(first) == []
    assert first.model_dump_json() == state_after


def test_weekly_growth_uses_played_affiliate_lines_and_is_bounded(
    campaign: GameState,
) -> None:
    parent_tid = sorted(campaign.academy_affiliates)[0]
    affiliate_tid = campaign.academy_affiliates[parent_tid]
    campaign.academy_levels[parent_tid] = 3
    player_id = next(
        pid
        for pid in sorted(campaign.teams[affiliate_tid].player_ids)
        if campaign.academy_player_rights.get(pid) == parent_tid
    )
    player = campaign.players[player_id]
    for attr_id in player.attributes:
        player.attributes[attr_id] = 50.0
    player.potential = 99.0

    fixture = next(
        f
        for f in campaign.fixtures
        if f.week == campaign.week
        and f.tier == 2
        and affiliate_tid in (f.team_a, f.team_b)
    )
    fixture.played = True
    fixture.winner_id = affiliate_tid
    fixture.results = [
        MapResult(
            map_id=fixture.maps[0],
            seed=1,
            score_a=13,
            score_b=8,
            winner_id=affiliate_tid,
            lines=[PlayerLineSnap(player_id=player_id, kills=22, deaths=12, rating=1.3)],
        )
    ]

    before = dict(player.attributes)
    reports = academy.weekly_tick(campaign)
    changed = [
        player.attributes[attr] - value
        for attr, value in before.items()
        if player.attributes[attr] > value
    ]
    assert reports
    assert len(changed) == 2
    assert all(0 < gain <= academy.WEEKLY_GAIN_CAP for gain in changed)

    after = dict(player.attributes)
    assert academy.weekly_tick(campaign) == []
    assert player.attributes == after


def test_academy_view_is_a_pure_owned_roster_projection(campaign: GameState) -> None:
    parent_tid = campaign.user_team_id
    view = academy.academy_view(campaign, parent_tid)
    affiliate_tid = campaign.academy_affiliates[parent_tid]
    assert view["affiliate_id"] == affiliate_tid
    assert {row["id"] for row in view["roster"]} == set(
        campaign.teams[affiliate_tid].player_ids
    )
    assert all(isinstance(row, dict) for row in view["roster"])
    assert view == academy.academy_view(campaign, parent_tid)


def test_shared_affiliate_preserves_each_parents_player_rights(
    campaign: GameState,
) -> None:
    by_affiliate: dict[str, list[str]] = {}
    for parent_tid, affiliate_tid in campaign.academy_affiliates.items():
        by_affiliate.setdefault(affiliate_tid, []).append(parent_tid)
    affiliate_tid, parents = next(
        (affiliate_tid, sorted(parents))
        for affiliate_tid, parents in sorted(by_affiliate.items())
        if len(parents) > 1
    )
    owner, other = parents[:2]
    player_id = next(
        pid
        for pid in sorted(campaign.free_agent_ids)
        if campaign.players[pid].age <= academy.ACADEMY_MAX_AGE
    )
    campaign.free_agent_ids.remove(player_id)
    campaign.teams[affiliate_tid].player_ids.append(player_id)
    campaign.academy_player_rights[player_id] = owner
    campaign.players[player_id].roster_role = "academy"

    ok, why = academy.can_move(campaign, other, player_id, "promote")
    assert not ok
    assert "rights" in why
    assert academy.can_move(campaign, owner, player_id, "promote") == (True, "")
