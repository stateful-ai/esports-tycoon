from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from esports_sim.policy.base import Action
from esports_sim.policy.heuristic import HeuristicPolicy
from esports_sim.policy.learned import (
    LearnedPlayerModel,
    RecordingPlayerPolicy,
    conditioned_features,
    imitation_metrics,
)
from esports_sim.registry import load_all
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import (
    ClaimKind,
    ClaimValue,
    CommunicationAction,
    PlayerObservation,
    TeamClaim,
)
from esports_sim.sim.comms import TeamWhiteboard
from esports_sim.sim.engine import MatchPolicies, simulate_match_result


def _policies(game_data, policy, *, comms: bool = True) -> MatchPolicies:
    by_id = {player_id: policy for player_id in game_data.players}
    return MatchPolicies(
        player_by_id=by_id,
        communication_by_id=by_id if comms else {},
    )


def _claim() -> CommunicationAction:
    return CommunicationAction(
        speak=True,
        kind=ClaimKind.ENEMY_LOCATION,
        value=ClaimValue.PRESENT,
        callout_id="a_site",
        enemy_id="enemy",
        expressed_confidence=0.9,
    )


def test_communication_action_is_strict_and_structured() -> None:
    with pytest.raises(ValidationError):
        CommunicationAction(speak=True)
    with pytest.raises(ValidationError):
        CommunicationAction(speak=False, kind=ClaimKind.ENEMY_LOCATION)
    with pytest.raises(ValidationError):
        CommunicationAction.model_validate({"speak": False, "was_wrong": True})


def test_contract_versions_reject_silent_mismatch() -> None:
    with pytest.raises(ValidationError):
        TeamClaim(
            schema_version=2,
            claim_id="r1-c0",
            team_id="team_nexus",
            sender_id="apex",
            kind=ClaimKind.ENEMY_LOCATION,
            value=ClaimValue.PRESENT,
            observed_tick=1,
            delivered_tick=1,
            expressed_confidence=0.8,
        )


def test_whiteboard_is_deterministic_receiver_specific_and_decays() -> None:
    gd = load_all()
    team = gd.teams["team_nexus"]
    sender, receiver = team.player_ids[:2]

    a = TeamWhiteboard(RngTree(17), "test-match", gd.maps["haven"], gd.players)
    b = TeamWhiteboard(RngTree(17), "test-match", gd.maps["haven"], gd.players)
    claim_a = a.publish(team.id, sender, _claim(), tick=10, round_num=1)
    claim_b = b.publish(team.id, sender, _claim(), tick=10, round_num=1)
    assert claim_a == claim_b
    assert claim_a is not None

    at_delivery_a = a.view(team.id, receiver, claim_a.delivered_tick)
    at_delivery_b = b.view(team.id, receiver, claim_a.delivered_tick)
    assert at_delivery_a == at_delivery_b
    assert len(at_delivery_a) == 1
    assert "was_wrong" not in type(at_delivery_a[0]).model_fields

    later = a.view(team.id, receiver, claim_a.delivered_tick + 30)
    assert later
    assert later[0].confidence < at_delivery_a[0].confidence
    assert a.view(team.id, sender, claim_a.delivered_tick) == []


class _RecordingPolicy:
    def __init__(self, delegate: HeuristicPolicy):
        self.delegate = delegate
        self.decisions = 0
        self.comms = 0
        self.conditions = 0
        self.buy_phase_enemy_leaks = 0
        self.defender_target_leaks = 0

    def decide(
        self,
        obs: PlayerObservation,
        legal: list[Action],
        rng: np.random.Generator,
    ) -> Action:
        self.decisions += 1
        self.conditions += int(obs.player_condition is not None)
        if obs.tick == 0 and obs.enemies:
            self.buy_phase_enemy_leaks += 1
        if not obs.is_attacking and obs.team_target is not None:
            self.defender_target_leaks += 1
        return self.delegate.decide(obs, legal, rng)

    def communicate(
        self,
        obs: PlayerObservation,
        legal: list[CommunicationAction],
        rng: np.random.Generator,
    ) -> CommunicationAction:
        self.comms += 1
        return self.delegate.communicate(obs, legal, rng)


def test_match_accepts_injected_policy_with_parallel_comms_head() -> None:
    gd = load_all()
    policy = _RecordingPolicy(HeuristicPolicy(gd, gd.maps["haven"]))
    result = simulate_match_result(
        gd,
        "team_nexus",
        "team_vanguard",
        "haven",
        seed=23,
        policies=_policies(gd, policy),
    )
    assert result.winner_id in ("team_nexus", "team_vanguard")
    assert policy.decisions > 0
    assert policy.conditions == policy.decisions
    assert policy.comms > 0
    assert policy.buy_phase_enemy_leaks == 0
    assert policy.defender_target_leaks == 0


def test_learned_player_model_trains_checkpoints_and_replays(tmp_path) -> None:
    gd = load_all()
    recorder = RecordingPlayerPolicy(HeuristicPolicy(gd, gd.maps["haven"]))
    simulate_match_result(
        gd,
        "team_nexus",
        "team_vanguard",
        "haven",
        seed=29,
        policies=_policies(gd, recorder),
    )
    traces = recorder.traces[:180]
    comms = recorder.communication_traces
    model = LearnedPlayerModel.train(traces, comms)
    metrics = imitation_metrics(model, traces)
    assert metrics["legal_rate"] == 1.0
    assert metrics["action_accuracy"] >= 0.45
    assert model.communication_examples == len(comms)

    path = tmp_path / "player-policy.json"
    model.save(path)
    loaded = LearnedPlayerModel.load(path)
    example = traces[-1]
    before = model.make_policy().action_probabilities(
        example.observation, list(example.legal_actions)
    )
    after = loaded.make_policy().action_probabilities(
        example.observation, list(example.legal_actions)
    )
    assert before == after
    assert path.read_text(encoding="utf-8").endswith("\n")

    # The live model is a legal deterministic match policy, not only an
    # offline classifier.
    events_a = simulate_match_result(
        gd, "team_nexus", "team_vanguard", "haven", 31,
        policies=_policies(gd, model.make_policy()),
    ).events
    events_b = simulate_match_result(
        load_all(), "team_nexus", "team_vanguard", "haven", 31,
        policies=_policies(load_all(), loaded.make_policy()),
    ).events
    assert [event.model_dump_json() for event in events_a] == [
        event.model_dump_json() for event in events_b
    ]


def test_conditioned_encoder_changes_with_player_identity() -> None:
    gd = load_all()
    recorder = RecordingPlayerPolicy(HeuristicPolicy(gd, gd.maps["haven"]))
    simulate_match_result(
        gd, "team_nexus", "team_vanguard", "haven", 37,
        policies=_policies(gd, recorder, comms=False),
    )
    by_player = {}
    for trace in recorder.traces:
        by_player.setdefault(trace.observation.self_state.player_id, trace.observation)
    observations = list(by_player.values())
    assert len(observations) >= 2
    left = observations[0]
    right = left.model_copy(update={"player_condition": observations[1].player_condition})
    assert not np.array_equal(conditioned_features(left), conditioned_features(right))
