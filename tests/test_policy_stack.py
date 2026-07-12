"""Regression coverage for policy-owned tactical decisions.

The point of these tests is architectural as much as behavioral: the match
referee must keep querying all ten player policies, team policies must own the
round plan, and coaches must enter a live map only through timeout advice.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.campaign import _fixture_plans, new_campaign
from esports_sim.manager.state import StaffMember
from esports_sim.policy.base import (
    Action,
    ActionType,
    AttackRoundRequest,
    CoachObservation,
    CoachProfile,
    TimeoutDirective,
)
from esports_sim.policy.heuristic import HeuristicCoachPolicy, HeuristicTeamPolicy
from esports_sim.registry import GameData
from esports_sim.sim import MatchPolicies, simulate_match_result
from esports_sim.sim import constants as C


class _HoldProbe:
    """Policy used to prove the engine queries every player every live tick."""

    def __init__(self) -> None:
        self.live_calls: dict[str, int] = {}

    def decide(self, obs, legal, rng):
        pid = obs.self_state.player_id
        if obs.tick > 0:
            self.live_calls[pid] = self.live_calls.get(pid, 0) + 1
        if any(action.type == ActionType.BUY for action in legal):
            return Action(type=ActionType.BUY, weapon_id="classic")
        return Action(type=ActionType.HOLD)


class _ImmediateTimeout:
    """Test coach: calls exactly one timeout when the referee offers it."""

    def call_timeout(self, observation, rng):
        return TimeoutDirective(kind="pressure", clarity=0.9)


def test_all_ten_player_policies_decide_each_live_tick(game_data: GameData) -> None:
    probe = _HoldProbe()
    player_ids = [
        *game_data.teams["team_nexus"].player_ids,
        *game_data.teams["team_vanguard"].player_ids,
    ]
    result = simulate_match_result(
        game_data,
        "team_nexus",
        "team_vanguard",
        "haven",
        17,
        policies=MatchPolicies(player_by_id={pid: probe for pid in player_ids}),
    )

    # Both teams hold their spawns, so every round reaches the 100-second
    # timer and no player becomes busy or dies.  The only non-live tick is
    # 201, where the referee checks time before asking a policy.
    # Sides alternate through overtime too, so a pure time-win fixture stays
    # tied until the match's finite overtime cap resolves it by seeded coin.
    rounds = result.score_a + result.score_b
    assert rounds == C.MAX_ROUNDS
    assert probe.live_calls == {pid: C.ROUND_TICKS * rounds for pid in player_ids}


def test_timeout_is_the_only_live_coach_event(game_data: GameData) -> None:
    result = simulate_match_result(
        game_data,
        "team_nexus",
        "team_vanguard",
        "haven",
        19,
        policies=MatchPolicies(coach_by_team={"team_nexus": _ImmediateTimeout()}),
    )
    timeouts = [event for event in result.events if event.type == "round.timeout"]
    assert len(timeouts) == 1
    timeout = timeouts[0]
    assert timeout.team_id == "team_nexus"
    assert timeout.tick == 0
    assert timeout.directive == "pressure"


def test_player_stats_choose_the_attack_roles(game_data: GameData) -> None:
    gd = game_data.model_copy(deep=True)
    players = [gd.players[pid] for pid in sorted(gd.teams["team_nexus"].player_ids)]
    entry, carrier = players[0], players[1]
    entry.attributes["aim_reactivity"] = 99.0
    entry.attributes["movement"] = 99.0
    entry.attributes["game_sense"] = 1.0
    carrier.attributes["game_sense"] = 99.0
    carrier.attributes["composure"] = 99.0

    policy = HeuristicTeamPolicy(gd, gd.maps["haven"])
    plan = policy.plan_attack(
        AttackRoundRequest(
            team_id="team_nexus",
            opponent_id="team_vanguard",
            players=tuple(players),
            captain_id=gd.teams["team_nexus"].captain_id,
            round_num=2,
            sites=tuple(str(site) for site in gd.maps["haven"].sites if str(site) != "mid"),
            site_wins={},
            tactics=gd.teams["team_nexus"].tactics,
            under_gunned=False,
        ),
        np.random.default_rng(3),
    )
    assert plan.spike_carrier_id == carrier.id
    assert plan.roles[entry.id] == "entry"


def test_coach_quality_controls_timeout_decision() -> None:
    policy = HeuristicCoachPolicy()
    common = dict(
        team_id="team_nexus",
        round_num=8,
        score_for=2,
        score_against=5,
        loss_streak=4,
        is_attacking=True,
    )
    low = policy.call_timeout(
        CoachObservation(profile=CoachProfile(id="low", quality=25.0), **common),
        np.random.default_rng(1),
    )
    high = policy.call_timeout(
        CoachObservation(
            profile=CoachProfile(id="high", quality=90.0, specialty="tactical"),
            **common,
        ),
        np.random.default_rng(1),
    )
    assert low is None
    assert high is not None and high.kind == "pressure"


def test_campaign_staff_projects_into_match_coach_profile(game_data: GameData) -> None:
    campaign = new_campaign(game_data, seed=55)
    team_id = campaign.user_team_id
    campaign.staff_by[team_id] = {
        "coach": StaffMember(
            id="coach_policy_test",
            name="Policy Test",
            role="coach",
            quality=88.0,
            salary=1,
            specialty="tactical",
            traits=["innovator"],
        )
    }
    fixture = campaign.team_fixture(team_id)
    assert fixture is not None
    plans, _ = _fixture_plans(campaign, fixture)
    coach = plans[team_id].coach
    assert coach is not None
    assert (coach.id, coach.quality, coach.specialty, coach.traits) == (
        "coach_policy_test", 88.0, "tactical", ("innovator",)
    )
