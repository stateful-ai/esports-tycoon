"""Deterministic Week-11 tactical replay simulator.

The simulator is intentionally small and explicit. It produces a match-viewer
artifact today, and its agents/observations/actions/rewards are shaped so a
future learned policy can replace the deterministic policy step by step.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from esports_tycoon.runner.week11 import (
    WEEK11_MATCH_OUTCOMES,
    WEEK11_MATCH_PLAN_CHOICES,
    WEEK11_MATCH_RESULT_FILENAME,
    WEEK11_MATCH_SIM_FILENAME,
    Week11MatchResultLock,
)
from esports_tycoon.schema import Player

WEEK11_DEVELOPMENT_PLAN_FILENAME = "week11_development_plan.json"
WEEK11_TRAINING_DATASET_FILENAME = "week11_training_dataset.json"
WEEK12_MODEL_PREP_FILENAME = "week12_model_prep.json"

Week11SimSide = Literal["overcast", "opponent"]
Week11SimAction = Literal[
    "call_default",
    "scan_lane",
    "entry_peek",
    "lurk_contact",
    "rotate_call",
    "anchor_trade",
    "objective_execute",
    "reset_shape",
    "round_end",
]
Week11DatasetSplit = Literal["train", "eval"]

WEEK11_SIM_ACTION_SPACE: tuple[Week11SimAction, ...] = (
    "call_default",
    "scan_lane",
    "entry_peek",
    "lurk_contact",
    "rotate_call",
    "anchor_trade",
    "objective_execute",
    "reset_shape",
    "round_end",
)
WEEK11_SIM_OBSERVATION_SPACE: tuple[str, ...] = (
    "self_role",
    "trait_profile",
    "alive_teammates",
    "visible_contact_lane",
    "utility_window",
    "economy_pressure",
    "objective_pressure",
    "protocol_signal",
    "analyst_read_class",
    "match_plan_commitment",
)
WEEK11_SIM_REWARD_FIELDS: tuple[str, ...] = (
    "round_win",
    "trade_quality",
    "utility_timing",
    "space_gained",
    "overpeek_penalty",
    "default_integrity",
)
WEEK11_RETURN_DISCOUNT_X100 = 90


@dataclass(frozen=True)
class Week11SimTraitProfile:
    """Numeric policy priors derived from saved player role + traits."""

    aim: int
    discipline: int
    tempo: int
    utility: int
    clutch: int
    comms: int
    risk: int


@dataclass(frozen=True)
class Week11SimAgent:
    """One controllable or opponent-side agent in the tactical replay."""

    agent_id: str
    side: Week11SimSide
    name: str
    role: str
    signature_operative: str
    portrait_asset: str
    traits: tuple[str, ...]
    trait_profile: Week11SimTraitProfile
    policy_id: str
    scenario_archetype: str
    skill_epoch_proxy: int


@dataclass(frozen=True)
class Week11SimRound:
    """One tactical training episode inside the match simulation."""

    round_id: int
    side_phase: str
    objective_lane: str
    opening_plan: str
    pressure_test: str
    terminal_condition: str
    winner: Week11SimSide
    reward_total: int
    frame_ticks: tuple[int, ...]


@dataclass(frozen=True)
class Week11SimAgentState:
    """One agent's rendered state at a replay tick."""

    agent_id: str
    x: int
    y: int
    alive: bool
    health: int
    stance: str
    intent: str


@dataclass(frozen=True)
class Week11SimTelemetry:
    """Frame-level numeric tactical signals for viewer HUDs and model training."""

    space_control: int
    utility_pressure: int
    trade_window: int
    risk_index: int
    objective_pressure: int


@dataclass(frozen=True)
class Week11SimObjectiveState:
    """Frame-level objective progress for plant, retake, or site-control logic."""

    site_id: str
    status: str
    progress: int
    carrier_agent_id: str
    contested: bool
    defender_pressure: int
    post_plant_seconds: int
    label: str


@dataclass(frozen=True)
class Week11SimLoadoutState:
    """Frame-level economy and equipment state for tactical replay policies."""

    buy_class: str
    weapon_tier: str
    armor_level: int
    utility_remaining: int
    team_credits: int
    opponent_credits: int
    economy_pressure: int
    advantage: str
    label: str


@dataclass(frozen=True)
class Week11SimScoreState:
    """Frame-level score, casualty, and win-probability state for broadcast/RL."""

    overcast_rounds: int
    opponent_rounds: int
    alive_overcast: int
    alive_opponent: int
    man_advantage: int
    win_probability: int
    momentum: str
    swing_reason: str


@dataclass(frozen=True)
class Week11SimLastKnownPosition:
    """One partial-observation position estimate for policy vision."""

    agent_id: str
    x: int
    y: int
    tick: int
    confidence: int


@dataclass(frozen=True)
class Week11SimSightline:
    """One visible, inferred, or blocked policy-vision ray."""

    source_agent_id: str
    target_agent_id: str
    blocked_by_cover_id: str
    blocked_by_utility_zone_id: str
    confidence: int
    visibility: str
    label: str


@dataclass(frozen=True)
class Week11SimInformationState:
    """Frame-level partial-observation state for policy vision and RL."""

    observer_agent_id: str
    visible_agent_ids: tuple[str, ...]
    occluded_agent_ids: tuple[str, ...]
    last_known_positions: tuple[Week11SimLastKnownPosition, ...]
    visible_zone_ids: tuple[str, ...]
    occluded_zone_ids: tuple[str, ...]
    sightlines: tuple[Week11SimSightline, ...]
    contact_confidence: int
    fog_pressure: int
    information_advantage: str


@dataclass(frozen=True)
class Week11SimEvent:
    """One tactical overlay event rendered on top of the replay map."""

    event_type: str
    agent_id: str
    zone_id: str
    x: int
    y: int
    radius: int
    label: str
    polarity: str


@dataclass(frozen=True)
class Week11SimThreatArc:
    """One line-of-sight or trade-cover lane visible in the match viewer."""

    arc_type: str
    source_agent_id: str
    target_agent_id: str
    lane_id: str
    x1: int
    y1: int
    x2: int
    y2: int
    threat_level: int
    advantage: str
    label: str
    polarity: str


@dataclass(frozen=True)
class Week11SimUtilityZone:
    """One deployable utility area emitted for replay rendering and RL state."""

    utility_type: str
    agent_id: str
    zone_id: str
    x: int
    y: int
    radius: int
    duration_ticks: int
    effect_strength: int
    blocks_sight: bool
    label: str
    polarity: str


@dataclass(frozen=True)
class Week11SimCombatEvent:
    """One damage, elimination, or trade event for replay and model state."""

    event_type: str
    source_agent_id: str
    target_agent_id: str
    damage: int
    target_health: int
    eliminated: bool
    trade_window: int
    trait_signal: str
    x: int
    y: int
    label: str
    polarity: str


@dataclass(frozen=True)
class Week11SimMapRegion:
    """One named tactical region in the replay map."""

    region_id: str
    label: str
    x: int
    y: int
    width: int
    height: int
    tactical_role: str
    priority: int


@dataclass(frozen=True)
class Week11SimMapCover:
    """One piece of map cover or blocking geometry."""

    cover_id: str
    zone_id: str
    x: int
    y: int
    width: int
    height: int
    rotation: int
    cover_type: str
    blocks_sight: bool


@dataclass(frozen=True)
class Week11SimMapLane:
    """One traversable lane polyline for replay and future navigation policies."""

    lane_id: str
    from_zone: str
    to_zone: str
    points: tuple[tuple[int, int], ...]
    tempo_bias: int
    trait_bias: str


@dataclass(frozen=True)
class Week11SimMapLayout:
    """The deterministic tactical map layout shared by viewer and RL contract."""

    map_id: str
    theme: str
    regions: tuple[Week11SimMapRegion, ...]
    covers: tuple[Week11SimMapCover, ...]
    lanes: tuple[Week11SimMapLane, ...]


@dataclass(frozen=True)
class Week11SimFrame:
    """One replay frame for the match viewer."""

    tick: int
    round_id: int
    clock: str
    phase: str
    focus_agent: str
    event_title: str
    event_detail: str
    reward_delta: int
    team_pressure: int
    telemetry: Week11SimTelemetry
    objective_state: Week11SimObjectiveState
    loadout_state: Week11SimLoadoutState
    score_state: Week11SimScoreState
    information_state: Week11SimInformationState
    states: tuple[Week11SimAgentState, ...]
    zone_control: dict[str, int]
    events: tuple[Week11SimEvent, ...]
    threat_arcs: tuple[Week11SimThreatArc, ...]
    utility_zones: tuple[Week11SimUtilityZone, ...]
    combat_events: tuple[Week11SimCombatEvent, ...]


@dataclass(frozen=True)
class Week11SimActionCandidate:
    """One legal or masked action candidate aligned to the replay action space."""

    action: Week11SimAction
    legal: bool
    score: int
    reason: str
    mask_reason: str
    target_zone: str
    target_x: int
    target_y: int
    expected_delta: int
    risk_delta: int
    utility_delta: int
    lane_id: str
    counterfactual_tag: str


@dataclass(frozen=True)
class Week11SimActionPrior:
    """One policy prior for a candidate action before the deterministic action is chosen."""

    action: Week11SimAction
    probability: int
    legal: bool
    score: int
    trait_fit: int


@dataclass(frozen=True)
class Week11SimPolicyEvaluation:
    """Trait-aware policy readout for future learned player models."""

    policy_id: str
    chosen_action: Week11SimAction
    confidence: int
    entropy: int
    exploration_temperature: int
    playstyle_label: str
    trait_alignment: int
    pressure_response: str
    top_priors: tuple[Week11SimActionPrior, ...]


@dataclass(frozen=True)
class Week11SimStep:
    """One RL-style step in the deterministic policy trace."""

    tick: int
    round_id: int
    agent_id: str
    observation: tuple[str, ...]
    action: Week11SimAction
    reward: int
    return_to_go_x100: int
    policy_id: str
    reason: str
    trajectory_tag: str
    observation_features: dict[str, Any]
    action_context: dict[str, str]
    reward_components: dict[str, int]
    action_mask: tuple[int, ...]
    candidate_actions: tuple[Week11SimActionCandidate, ...]
    policy_evaluation: Week11SimPolicyEvaluation


@dataclass(frozen=True)
class Week11TrainingSignal:
    """One player-development signal derived from the replay trajectory."""

    agent_id: str
    category: str
    priority: str
    label: str
    evidence: str
    source_rounds: tuple[int, ...]
    reward_total: int
    epoch_delta: int
    current_policy_id: str
    next_policy_id: str


@dataclass(frozen=True)
class Week11DevelopmentDrill:
    """One actionable training block derived from replay training signals."""

    drill_id: str
    agent_id: str
    category: str
    focus: str
    priority: str
    source_signal: str
    source_rounds: tuple[int, ...]
    training_minutes: int
    epoch_delta: int
    current_policy_id: str
    target_policy_id: str
    success_metric: str


@dataclass(frozen=True)
class Week11DevelopmentPlan:
    """Post-match development artifact produced from the tactical replay."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    training_budget_minutes: int
    drills: tuple[Week11DevelopmentDrill, ...]
    coaching_summary: tuple[str, ...]
    rl_notes: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week11TrainingEpisode:
    """One replay round packaged as an offline RL episode."""

    episode_id: str
    round_id: int
    split: Week11DatasetSplit
    sample_ids: tuple[str, ...]
    terminal_sample_id: str
    step_count: int
    reward_total: int
    start_tick: int
    end_tick: int
    agent_ids: tuple[str, ...]


@dataclass(frozen=True)
class Week11TrainingSample:
    """One offline RL transition sample derived from the tactical replay."""

    sample_id: str
    episode_id: str
    episode_step: int
    next_sample_id: str | None
    split: Week11DatasetSplit
    agent_id: str
    tick: int
    round_id: int
    observation: tuple[str, ...]
    action: Week11SimAction
    reward: int
    return_to_go_x100: int
    next_observation: tuple[str, ...]
    done: bool
    telemetry: Week11SimTelemetry
    observation_features: dict[str, Any]
    reward_components: dict[str, int]
    action_mask: tuple[int, ...]
    candidate_actions: tuple[Week11SimActionCandidate, ...]
    target_policy_id: str
    source_drill_id: str


@dataclass(frozen=True)
class Week11TrainingDataset:
    """Model-ready offline RL dataset derived from replay + development targets."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    episodes: tuple[Week11TrainingEpisode, ...]
    samples: tuple[Week11TrainingSample, ...]
    policy_targets: tuple[dict[str, Any], ...]
    dataset_notes: tuple[str, ...]


@dataclass(frozen=True)
class Week11MatchSimulation:
    """A deterministic tactical replay artifact for Week 11."""

    sim_id: str
    source_branch: str
    setup_branch: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    scoreline: str
    result_grade: str
    seed: str
    map_name: str
    map_layout: Week11SimMapLayout
    opponent_name: str
    sim_mode: str
    agents: tuple[Week11SimAgent, ...]
    rounds: tuple[Week11SimRound, ...]
    frames: tuple[Week11SimFrame, ...]
    steps: tuple[Week11SimStep, ...]
    training_signals: tuple[Week11TrainingSignal, ...]
    viewer_summary: tuple[str, ...]
    training_notes: tuple[str, ...]


def _clamp(value: int, low: int = 35, high: int = 98) -> int:
    return max(low, min(high, value))


def _display_name(player: Player) -> str:
    if '"' in player.name:
        return player.name.split('"')[1]
    return player.name.split()[0] if player.name.split() else player.id


def _base_profile(role: str) -> Week11SimTraitProfile:
    role_profiles: dict[str, Week11SimTraitProfile] = {
        "IGL": Week11SimTraitProfile(aim=58, discipline=84, tempo=56, utility=72, clutch=64, comms=86, risk=42),
        "DUELIST": Week11SimTraitProfile(aim=84, discipline=54, tempo=86, utility=48, clutch=72, comms=58, risk=82),
        "SENTINEL": Week11SimTraitProfile(aim=68, discipline=82, tempo=48, utility=68, clutch=82, comms=48, risk=34),
        "INITIATOR": Week11SimTraitProfile(aim=62, discipline=64, tempo=68, utility=86, clutch=62, comms=88, risk=56),
        "CONTROLLER": Week11SimTraitProfile(aim=64, discipline=78, tempo=58, utility=84, clutch=68, comms=52, risk=44),
    }
    return role_profiles.get(role, Week11SimTraitProfile(64, 64, 64, 64, 64, 64, 50))


def _profile_for_player(player: Player) -> Week11SimTraitProfile:
    profile = _base_profile(str(player.role.value if hasattr(player.role, "value") else player.role))
    aim = profile.aim
    discipline = profile.discipline
    tempo = profile.tempo
    utility = profile.utility
    clutch = profile.clutch
    comms = profile.comms
    risk = profile.risk

    for trait in player.traits:
        if trait == "mechanically-gifted":
            aim += 12
            clutch += 4
        elif trait == "impulsive":
            discipline -= 12
            tempo += 10
            risk += 10
        elif trait == "hotshot":
            aim += 4
            risk += 8
        elif trait == "structure-first":
            discipline += 12
            comms += 8
            risk -= 6
        elif trait == "veteran":
            discipline += 8
            clutch += 6
        elif trait == "control-freak":
            comms += 6
            risk -= 4
        elif trait == "anchor":
            discipline += 8
            clutch += 8
            tempo -= 6
        elif trait == "reliable":
            discipline += 8
            clutch += 4
        elif trait == "info-savant":
            utility += 12
            comms += 8
        elif trait == "motormouth":
            comms += 10
            discipline -= 4
        elif trait == "optimist":
            clutch += 4
        elif trait == "patient":
            discipline += 10
            tempo -= 4
            risk -= 6
        elif trait == "lurker":
            tempo += 4
            utility += 4
            risk += 3
        elif trait == "cynical":
            discipline += 3
            comms -= 4

    return Week11SimTraitProfile(
        aim=_clamp(aim),
        discipline=_clamp(discipline),
        tempo=_clamp(tempo),
        utility=_clamp(utility),
        clutch=_clamp(clutch),
        comms=_clamp(comms),
        risk=_clamp(risk, 20, 98),
    )


def _policy_for_player(player: Player) -> tuple[str, str]:
    policies = {
        "rook": ("structured_default_caller", "scenario_style_rook_structure_igl"),
        "vex": ("entry_pressure_sprinter", "scenario_style_vex_high_tempo_entry"),
        "sable": ("anchor_trade_minimizer", "scenario_style_sable_low_variance_anchor"),
        "pixie": ("info_utility_overcaller", "scenario_style_pixie_info_initiator"),
        "coyote": ("patient_lurk_controller", "scenario_style_coyote_lurk_controller"),
    }
    return policies.get(player.id, ("role_default_policy", "scenario_style_role_baseline"))


def _epoch_proxy(profile: Week11SimTraitProfile, result: Week11MatchResultLock) -> int:
    base = profile.aim + profile.discipline + profile.utility + profile.clutch
    grade_bonus = {"clean": 80, "earned": 50, "thin": 20, "punished": 0}.get(result.result_grade, 20)
    result_bonus = 40 if result.result_tier == "win" else 0
    return int((base * 3) + grade_bonus + result_bonus)


def _agent_for_player(player: Player, result: Week11MatchResultLock) -> Week11SimAgent:
    profile = _profile_for_player(player)
    policy_id, scenario_archetype = _policy_for_player(player)
    role = str(player.role.value if hasattr(player.role, "value") else player.role)
    portrait_asset = f"art/portraits/{player.id}.webp" if player.id in {"rook", "vex", "sable", "pixie", "coyote"} else ""
    return Week11SimAgent(
        agent_id=player.id,
        side="overcast",
        name=_display_name(player),
        role=role,
        signature_operative=player.signature_operative,
        portrait_asset=portrait_asset,
        traits=tuple(player.traits),
        trait_profile=profile,
        policy_id=policy_id,
        scenario_archetype=scenario_archetype,
        skill_epoch_proxy=_epoch_proxy(profile, result),
    )


def _opponent_agents(opponent_name: str, result: Week11MatchResultLock) -> tuple[Week11SimAgent, ...]:
    pressure = 10 if result.result_tier == "loss" else 0
    specs = (
        ("opp_igl", "IGL", "caller", 62, 78, 55, 70, 60, 76, 45),
        ("opp_entry", "DUELIST", "entry", 82, 58, 82, 46, 70, 54, 78),
        ("opp_anchor", "SENTINEL", "anchor", 70, 78, 48, 66, 74, 46, 36),
        ("opp_info", "INITIATOR", "info", 64, 66, 66, 82, 60, 78, 55),
        ("opp_smoke", "CONTROLLER", "smoke", 66, 74, 54, 80, 64, 52, 42),
    )
    agents = []
    for agent_id, role, label, aim, discipline, tempo, utility, clutch, comms, risk in specs:
        profile = Week11SimTraitProfile(
            aim=_clamp(aim + pressure // 2),
            discipline=_clamp(discipline + pressure // 2),
            tempo=_clamp(tempo + pressure // 3),
            utility=_clamp(utility + pressure // 3),
            clutch=_clamp(clutch + pressure // 2),
            comms=_clamp(comms),
            risk=_clamp(risk + pressure // 2, 20, 98),
        )
        agents.append(
            Week11SimAgent(
                agent_id=agent_id,
                side="opponent",
                name=f"{opponent_name} {label}",
                role=role,
                signature_operative="rival-kit",
                portrait_asset="",
                traits=("rival", label),
                trait_profile=profile,
                policy_id=f"rival_{label}_baseline",
                scenario_archetype=f"scenario_style_rival_{label}",
                skill_epoch_proxy=_epoch_proxy(profile, result) - (20 if result.result_tier == "win" else 0),
            )
        )
    return tuple(agents)


_PATHS: dict[str, dict[str, tuple[tuple[int, int], ...]]] = {
    "trust_the_read": {
        "rook": ((23, 72), (31, 66), (40, 59), (48, 54), (56, 50), (61, 46), (67, 43), (72, 40)),
        "vex": ((19, 76), (30, 68), (43, 58), (55, 50), (64, 43), (71, 39), (75, 36), (78, 34)),
        "sable": ((26, 82), (34, 78), (42, 73), (49, 68), (55, 63), (61, 57), (67, 52), (72, 47)),
        "pixie": ((17, 67), (30, 61), (43, 54), (53, 49), (60, 45), (66, 41), (72, 38), (76, 36)),
        "coyote": ((35, 79), (42, 73), (50, 66), (59, 60), (68, 55), (75, 50), (80, 45), (83, 40)),
    },
    "attack_the_gap": {
        "rook": ((24, 72), (35, 68), (44, 64), (51, 58), (60, 54), (67, 50), (73, 45), (77, 42)),
        "vex": ((19, 76), (32, 70), (45, 64), (56, 57), (68, 49), (78, 43), (84, 38), (86, 35)),
        "sable": ((25, 82), (32, 80), (39, 77), (47, 74), (54, 69), (62, 63), (69, 58), (73, 52)),
        "pixie": ((18, 67), (30, 63), (40, 59), (51, 54), (63, 49), (72, 45), (79, 41), (83, 38)),
        "coyote": ((35, 79), (42, 72), (51, 64), (61, 56), (73, 50), (83, 45), (88, 40), (89, 36)),
    },
    "stabilize_defaults": {
        "rook": ((23, 72), (30, 70), (37, 67), (44, 63), (51, 59), (58, 55), (64, 50), (70, 47)),
        "vex": ((19, 76), (28, 72), (37, 66), (46, 60), (55, 54), (64, 49), (70, 45), (75, 42)),
        "sable": ((26, 82), (31, 80), (36, 77), (42, 73), (49, 69), (57, 64), (64, 59), (71, 54)),
        "pixie": ((17, 67), (27, 65), (36, 62), (45, 58), (53, 54), (61, 50), (68, 46), (74, 43)),
        "coyote": ((35, 79), (40, 76), (46, 72), (53, 67), (61, 62), (69, 57), (77, 52), (82, 47)),
    },
}

_OPPONENT_PATHS: dict[str, tuple[tuple[int, int], ...]] = {
    "opp_igl": ((76, 25), (72, 29), (68, 34), (64, 40), (61, 45), (58, 49), (55, 53), (52, 57)),
    "opp_entry": ((83, 29), (78, 34), (73, 40), (67, 46), (60, 50), (55, 54), (51, 58), (48, 62)),
    "opp_anchor": ((73, 18), (70, 24), (68, 31), (66, 38), (65, 45), (64, 52), (63, 58), (61, 64)),
    "opp_info": ((87, 22), (81, 28), (75, 35), (70, 42), (65, 48), (60, 53), (56, 58), (53, 62)),
    "opp_smoke": ((69, 29), (67, 35), (64, 42), (61, 48), (58, 54), (55, 59), (52, 63), (49, 66)),
}


def _state_for_agent(
    agent: Week11SimAgent,
    result: Week11MatchResultLock,
    tick: int,
    round_id: int,
) -> Week11SimAgentState:
    local_tick = tick % 4
    path_tick = min((round_id - 1) * 2 + local_tick, 7)
    if agent.side == "overcast":
        path = _PATHS[result.selected_plan].get(agent.agent_id, _PATHS[result.selected_plan]["rook"])
        if result.result_tier == "loss":
            death_tick = {"vex": 3, "pixie": 6, "rook": 9}.get(agent.agent_id, 99)
        else:
            death_tick = {"vex": 10 if result.result_grade == "thin" else 99}.get(agent.agent_id, 99)
        alive = tick < death_tick
    else:
        path = _OPPONENT_PATHS.get(agent.agent_id, _OPPONENT_PATHS["opp_igl"])
        if result.result_tier == "win":
            death_tick = {"opp_entry": 3, "opp_info": 7, "opp_igl": 10, "opp_anchor": 11}.get(agent.agent_id, 99)
        else:
            death_tick = {"opp_entry": 11}.get(agent.agent_id, 99)
        alive = tick < death_tick

    x, y = path[path_tick]
    if not alive:
        stance = "down"
        intent = "out"
        health = 0
    elif local_tick == 0:
        stance = "set"
        intent = "default"
        health = max(1, min(100, 100 - (round_id - 1) * 3))
    elif local_tick == 1:
        stance = "contact"
        intent = "take space"
        health = max(1, min(100, 88 - (round_id - 1) * 4))
    elif local_tick == 2:
        stance = "trade"
        intent = "convert"
        health = max(1, min(100, 74 - (round_id - 1) * 5))
    else:
        stance = "resolve"
        intent = "close round"
        health = max(1, min(100, 62 - (round_id - 1) * 6))
    return Week11SimAgentState(
        agent_id=agent.agent_id,
        x=x,
        y=y,
        alive=alive,
        health=health,
        stance=stance,
        intent=intent,
    )


def _reward(result: Week11MatchResultLock, tick: int, default: int) -> int:
    if result.result_tier == "win":
        return default
    return -default if default > 0 and tick >= 2 else default


def _round_winner(result: Week11MatchResultLock, round_id: int) -> Week11SimSide:
    if result.result_tier == "win":
        if result.scoreline == "2-1" and round_id == 2:
            return "opponent"
        return "overcast"
    if result.scoreline == "1-2" and round_id == 1:
        return "overcast"
    return "opponent"


def _rounds(result: Week11MatchResultLock) -> tuple[Week11SimRound, ...]:
    if result.selected_plan == "trust_the_read":
        objectives = (
            ("attack", "A main", "prove the read before second layer", "read timing"),
            ("defense", "mid pinch", "hold the confirmed rotate call", "counter timing"),
            ("attack", "B split", "convert the analyst read into objective pressure", "late fight setup"),
        )
    elif result.selected_plan == "attack_the_gap":
        objectives = (
            ("attack", "mid gap", "hit the exposed branch early", "branch punish"),
            ("attack", "A elbow", "stay narrow after first contact", "over-chase check"),
            ("defense", "B retake", "deny the hidden counter branch", "trade discipline"),
        )
    else:
        objectives = (
            ("defense", "B default", "keep the first-contact shell intact", "default integrity"),
            ("attack", "mid default", "turn stability into proactive pressure", "tempo ceiling"),
            ("defense", "A retake", "stabilize without giving away the map", "late action trigger"),
        )

    rounds = []
    for index, (side_phase, lane, opening, pressure) in enumerate(objectives, start=1):
        winner = _round_winner(result, index)
        reward_total = 8 if winner == "overcast" else -5
        terminal = "objective secured" if winner == "overcast" else "pressure window lost"
        if index == 2 and result.result_grade in {"thin", "punished"}:
            terminal = "trade window contested"
        rounds.append(
            Week11SimRound(
                round_id=index,
                side_phase=side_phase,
                objective_lane=lane,
                opening_plan=opening,
                pressure_test=pressure,
                terminal_condition=terminal,
                winner=winner,
                reward_total=reward_total,
                frame_ticks=tuple(range((index - 1) * 4, index * 4)),
            )
        )
    return tuple(rounds)


def _zone_id(x: int, y: int) -> str:
    if y >= 70:
        return "spawn_lobby"
    if x >= 62 and y <= 48:
        return "a_site"
    if x <= 46 and y >= 58:
        return "b_site"
    if 45 <= x <= 62 and 42 <= y <= 62:
        return "mid"
    if x < 45:
        return "b_main"
    return "a_main"


def _target_zone(round_id: int, action: Week11SimAction) -> str:
    if action in {"objective_execute", "round_end"}:
        return "a_site" if round_id in (1, 3) else "mid"
    if action in {"scan_lane", "entry_peek"}:
        return "a_main"
    if action == "lurk_contact":
        return "b_main"
    if action == "anchor_trade":
        return "mid"
    return "spawn_lobby"


def _zone_anchor(zone_id: str) -> tuple[int, int]:
    return {
        "a_site": (83, 43),
        "b_site": (16, 45),
        "mid": (53, 48),
        "spawn_lobby": (36, 76),
        "a_main": (67, 45),
        "b_main": (28, 52),
    }.get(zone_id, (50, 50))


def _map_id(map_name: str) -> str:
    slug = "_".join(part.lower() for part in map_name.split() if part)
    return slug or "helix"


def _map_layout(map_name: str) -> Week11SimMapLayout:
    """Return a stable tactical layout for the current simulated map."""
    regions = (
        Week11SimMapRegion("spawn_lobby", "Spawn lobby", 17, 66, 31, 24, "reset shell", 36),
        Week11SimMapRegion("b_main", "B main", 18, 45, 28, 25, "late lurk lane", 54),
        Week11SimMapRegion("mid", "Mid hinge", 41, 32, 25, 31, "rotate and trade hinge", 72),
        Week11SimMapRegion("a_main", "A main", 58, 31, 24, 27, "entry contact lane", 68),
        Week11SimMapRegion("a_site", "A site", 74, 29, 22, 29, "execute target", 82),
        Week11SimMapRegion("b_site", "B site", 5, 34, 25, 28, "split target", 74),
    )
    covers = (
        Week11SimMapCover("a_heaven_pillar", "a_site", 81, 33, 9, 5, 0, "hard", True),
        Week11SimMapCover("a_elbow_box", "a_main", 66, 45, 9, 5, 12, "soft", True),
        Week11SimMapCover("mid_arch", "mid", 49, 48, 12, 6, -8, "hard", True),
        Week11SimMapCover("b_stack", "b_site", 12, 43, 8, 9, 0, "hard", True),
        Week11SimMapCover("b_lurk_crate", "b_main", 28, 52, 8, 7, 18, "soft", True),
        Week11SimMapCover("spawn_call_wall", "spawn_lobby", 38, 75, 14, 5, 0, "soft", False),
    )
    lanes = (
        Week11SimMapLane(
            "a_main_execute",
            "spawn_lobby",
            "a_site",
            ((23, 72), (40, 60), (58, 48), (79, 42)),
            70,
            "tempo",
        ),
        Week11SimMapLane(
            "mid_rotate",
            "spawn_lobby",
            "mid",
            ((31, 70), (41, 61), (50, 53), (54, 43)),
            58,
            "comms",
        ),
        Week11SimMapLane(
            "b_split_lurk",
            "spawn_lobby",
            "b_site",
            ((34, 78), (29, 65), (24, 54), (16, 45)),
            50,
            "discipline",
        ),
        Week11SimMapLane(
            "a_b_crossfire",
            "mid",
            "b_site",
            ((55, 52), (43, 51), (29, 49), (16, 45)),
            62,
            "trade_window",
        ),
    )
    return Week11SimMapLayout(
        map_id=_map_id(map_name),
        theme="two-site tactical board with mid hinge and late lurk lane",
        regions=regions,
        covers=covers,
        lanes=lanes,
    )


def _toward_zone(
    state: Week11SimAgentState,
    zone_id: str,
    *,
    weight: int,
) -> tuple[int, int]:
    anchor_x, anchor_y = _zone_anchor(zone_id)
    inverse = 100 - weight
    return (
        _clamp((state.x * inverse + anchor_x * weight) // 100, 0, 100),
        _clamp((state.y * inverse + anchor_y * weight) // 100, 0, 100),
    )


def _top_trait(agent: Week11SimAgent) -> str:
    profile = _profile_to_dict(agent.trait_profile)
    return max(profile, key=lambda name: profile[name])


def _trade_partner(agent_id: str) -> str:
    return {
        "rook": "pixie",
        "vex": "sable",
        "sable": "vex",
        "pixie": "rook",
        "coyote": "rook",
    }.get(agent_id, "team")


def _utility_kind(action: Week11SimAction) -> str:
    return {
        "call_default": "default_shell",
        "scan_lane": "reveal",
        "rotate_call": "rotate_ping",
        "reset_shape": "smoke",
        "anchor_trade": "crossfire",
        "objective_execute": "execute",
        "entry_peek": "flash",
        "lurk_contact": "silent_contact",
        "round_end": "terminal_zone",
    }[action]


def _counterfactual(action: Week11SimAction) -> str:
    return {
        "call_default": "force_fast_hit",
        "scan_lane": "hold_utility",
        "entry_peek": "reset_shape",
        "lurk_contact": "group_contact",
        "rotate_call": "stay_default",
        "anchor_trade": "late_retrade",
        "objective_execute": "delay_execute",
        "reset_shape": "keep_pressure",
        "round_end": "earlier_trade",
    }[action]


def _reward_components(
    *,
    action: Week11SimAction,
    reward: int,
    trajectory_tag: str,
    risk: int,
) -> dict[str, int]:
    components = {field: 0 for field in WEEK11_SIM_REWARD_FIELDS}
    if trajectory_tag in components:
        components[trajectory_tag] = reward
    if action in {"entry_peek", "lurk_contact"} and risk >= 78:
        components["overpeek_penalty"] -= 1
    if action in {"call_default", "rotate_call", "reset_shape"} and reward >= 0:
        components["default_integrity"] += 1
    if action == "objective_execute" and reward > 0:
        components["round_win"] += 1
    return components


def _candidate_score(
    *,
    action: Week11SimAction,
    selected_action: Week11SimAction,
    observation_features: dict[str, Any],
    reward: int,
    legal: bool,
) -> int:
    if not legal:
        return 0
    score = 42
    if action == selected_action:
        score += 28 + max(0, reward) * 5
    if action in {"scan_lane", "reset_shape", "rotate_call"}:
        score += int(observation_features.get("utility_pressure", 0)) // 4
    if action in {"entry_peek", "lurk_contact"}:
        score += int(observation_features.get("space_control", 0)) // 5
    if action == "anchor_trade":
        score += int(observation_features.get("trade_window", 0)) // 3
    if action == "objective_execute":
        score += int(observation_features.get("objective_pressure", 0)) // 3
    economy_pressure = int(observation_features.get("economy_pressure", 0))
    if economy_pressure >= 68 and action in {"scan_lane", "reset_shape", "rotate_call"}:
        score += 8
    if economy_pressure >= 70 and action in {"entry_peek", "lurk_contact"}:
        score -= 12
    if economy_pressure >= 76 and action == "objective_execute":
        score -= 6
    if int(observation_features.get("risk_index", 0)) >= 76 and action in {"entry_peek", "lurk_contact"}:
        score -= 14
    if action == "round_end":
        score += 18 if selected_action == "round_end" else -10
    return _clamp(score, 0, 100)


def _legal_action_set(
    *,
    agent: Week11SimAgent,
    selected_action: Week11SimAction,
    observation_features: dict[str, Any],
    tick: int,
) -> set[Week11SimAction]:
    local_tick = tick % 4
    own_zone = str(observation_features.get("own_zone", ""))
    target_zone = str(observation_features.get("target_zone", ""))
    risk = int(observation_features.get("risk_index", 0))
    objective_pressure = int(observation_features.get("objective_pressure", 0))
    legal: set[Week11SimAction] = {selected_action, "reset_shape"}

    if local_tick == 0 or own_zone == "spawn_lobby":
        legal.update({"call_default", "scan_lane", "rotate_call"})
    if target_zone in {"a_main", "b_main", "mid"}:
        legal.update({"scan_lane", "entry_peek", "lurk_contact", "anchor_trade"})
    if agent.role in {"IGL", "CONTROLLER", "INITIATOR"}:
        legal.update({"call_default", "scan_lane", "rotate_call"})
    if agent.role in {"DUELIST", "CONTROLLER"}:
        legal.update({"entry_peek", "lurk_contact"})
    if risk >= 70:
        legal.update({"anchor_trade", "reset_shape"})
    if objective_pressure >= 58 or selected_action == "objective_execute":
        legal.add("objective_execute")
    if local_tick == 3 or selected_action == "round_end":
        legal.add("round_end")
    return legal


def _mask_reason(action: Week11SimAction, *, legal: bool, selected_action: Week11SimAction) -> str:
    if legal and action == selected_action:
        return "selected_by_policy"
    if legal:
        return "available_in_state"
    if action == "objective_execute":
        return "objective_pressure_gate"
    if action == "round_end":
        return "terminal_phase_only"
    if action in {"entry_peek", "lurk_contact"}:
        return "contact_or_role_gate"
    return "masked_by_phase"


def _candidate_reason(action: Week11SimAction, *, legal: bool, selected_action: Week11SimAction) -> str:
    if action == selected_action:
        return "Deterministic policy selected this branch for the saved trajectory."
    if legal:
        return "Legal alternative for counterfactual rollout or behavior cloning negatives."
    return "Masked action kept in the contract so future policies share a stable action index."


def _bounded_delta(value: int, *, low: int = -100, high: int = 100) -> int:
    return max(low, min(high, value))


def _candidate_lane_id(source_zone: str, target_zone: str, action: Week11SimAction) -> str:
    if action == "round_end":
        return "terminal"
    if target_zone in {"a_main", "a_site"}:
        return "a_main_execute"
    if target_zone in {"b_main", "b_site"}:
        return "b_split_lurk"
    if target_zone == "mid":
        return "mid_rotate" if source_zone != "mid" else "a_b_crossfire"
    return f"{source_zone}->{target_zone}"


def _risk_delta(action: Week11SimAction, observation_features: dict[str, Any]) -> int:
    baseline = int(observation_features.get("risk_index", 50))
    bias = {
        "call_default": -10,
        "scan_lane": -8,
        "entry_peek": 18,
        "lurk_contact": 14,
        "rotate_call": -6,
        "anchor_trade": 4,
        "objective_execute": 10,
        "reset_shape": -14,
        "round_end": 0,
    }[action]
    if baseline >= 74 and action in {"entry_peek", "lurk_contact", "objective_execute"}:
        bias += 6
    return _bounded_delta(bias, low=-50, high=50)


def _utility_delta(action: Week11SimAction, observation_features: dict[str, Any]) -> int:
    utility_pressure = int(observation_features.get("utility_pressure", 50))
    bias = {
        "call_default": 4,
        "scan_lane": 16,
        "entry_peek": -8,
        "lurk_contact": -6,
        "rotate_call": 8,
        "anchor_trade": 2,
        "objective_execute": -18,
        "reset_shape": 10,
        "round_end": 0,
    }[action]
    if utility_pressure >= 66 and action in {"scan_lane", "reset_shape", "rotate_call"}:
        bias += 5
    return _bounded_delta(bias, low=-50, high=50)


def _candidate_actions(
    *,
    agent: Week11SimAgent,
    selected_action: Week11SimAction,
    observation_features: dict[str, Any],
    round_id: int,
    tick: int,
    reward: int,
) -> tuple[Week11SimActionCandidate, ...]:
    legal_actions = _legal_action_set(
        agent=agent,
        selected_action=selected_action,
        observation_features=observation_features,
        tick=tick,
    )
    source_zone = str(observation_features.get("own_zone", "spawn_lobby"))
    selected_score = _candidate_score(
        action=selected_action,
        selected_action=selected_action,
        observation_features=observation_features,
        reward=reward,
        legal=True,
    )
    candidates = []
    for action in WEEK11_SIM_ACTION_SPACE:
        legal = action in legal_actions
        score = _candidate_score(
            action=action,
            selected_action=selected_action,
            observation_features=observation_features,
            reward=reward,
            legal=legal,
        )
        target_zone = _target_zone(round_id, action)
        target_x, target_y = _zone_anchor(target_zone)
        candidates.append(
            Week11SimActionCandidate(
                action=action,
                legal=legal,
                score=score,
                reason=_candidate_reason(
                    action,
                    legal=legal,
                    selected_action=selected_action,
                ),
                mask_reason=_mask_reason(
                    action,
                    legal=legal,
                    selected_action=selected_action,
                ),
                target_zone=target_zone,
                target_x=target_x,
                target_y=target_y,
                expected_delta=_bounded_delta(score - selected_score),
                risk_delta=_risk_delta(action, observation_features),
                utility_delta=_utility_delta(action, observation_features),
                lane_id=_candidate_lane_id(source_zone, target_zone, action),
                counterfactual_tag="selected_policy_path"
                if action == selected_action
                else _counterfactual(action),
            )
        )
    return tuple(candidates)


def _action_mask(candidates: tuple[Week11SimActionCandidate, ...]) -> tuple[int, ...]:
    return tuple(1 if candidate.legal else 0 for candidate in candidates)


def _action_trait_fit(agent: Week11SimAgent, action: Week11SimAction) -> int:
    profile = agent.trait_profile
    fits = {
        "call_default": (profile.comms + profile.discipline + profile.utility) // 3,
        "scan_lane": (profile.utility + profile.comms + profile.discipline) // 3,
        "entry_peek": (profile.aim + profile.tempo + profile.risk) // 3,
        "lurk_contact": (profile.discipline + profile.risk + profile.clutch) // 3,
        "rotate_call": (profile.comms + profile.discipline + profile.tempo) // 3,
        "anchor_trade": (profile.discipline + profile.clutch + profile.aim) // 3,
        "objective_execute": (profile.tempo + profile.utility + profile.clutch) // 3,
        "reset_shape": (profile.discipline + profile.comms + profile.utility) // 3,
        "round_end": (profile.clutch + profile.discipline + profile.comms) // 3,
    }
    return _clamp(fits[action], 0, 100)


def _pressure_response(action: Week11SimAction, observation_features: dict[str, Any]) -> str:
    risk = int(observation_features.get("risk_index", 50))
    objective = int(observation_features.get("objective_pressure", 50))
    if action in {"scan_lane", "rotate_call"}:
        return "information_reset" if risk >= 56 else "information_gain"
    if action in {"call_default", "reset_shape"}:
        return "stabilize_default"
    if action in {"entry_peek", "lurk_contact"}:
        return "pressure_contact" if objective >= 62 else "space_probe"
    if action == "anchor_trade":
        return "trade_hold"
    if action == "objective_execute":
        return "objective_commit"
    return "terminal_reward"


def _playstyle_label(agent: Week11SimAgent, action: Week11SimAction) -> str:
    if action in {"entry_peek", "objective_execute"} and agent.trait_profile.tempo >= 68:
        return "high_tempo_space"
    if action in {"scan_lane", "rotate_call"} and agent.trait_profile.utility >= 64:
        return "info_utility"
    if action in {"call_default", "reset_shape"} and agent.trait_profile.comms >= 64:
        return "structured_default"
    if action in {"lurk_contact"}:
        return "patient_lurk" if agent.trait_profile.discipline >= 62 else "risk_probe"
    if action == "anchor_trade":
        return "trade_anchor"
    return f"{agent.role}_policy"


def _policy_evaluation(
    *,
    agent: Week11SimAgent,
    selected_action: Week11SimAction,
    observation_features: dict[str, Any],
    candidate_actions: tuple[Week11SimActionCandidate, ...],
) -> Week11SimPolicyEvaluation:
    legal_priors: list[tuple[Week11SimActionCandidate, int, int]] = []
    for candidate in candidate_actions:
        trait_fit = _action_trait_fit(agent, candidate.action)
        if candidate.legal:
            pressure_bonus = max(0, int(observation_features.get("objective_pressure", 50)) - 55) // 3
            risk_penalty = max(0, int(observation_features.get("risk_index", 50)) - 66) // 2
            weight = max(1, candidate.score + trait_fit // 3 + pressure_bonus - risk_penalty)
        else:
            weight = 0
        legal_priors.append((candidate, trait_fit, weight))

    total_weight = sum(weight for _, _, weight in legal_priors) or 1
    priors = tuple(
        Week11SimActionPrior(
            action=candidate.action,
            probability=(weight * 100 + total_weight // 2) // total_weight if candidate.legal else 0,
            legal=candidate.legal,
            score=candidate.score,
            trait_fit=trait_fit,
        )
        for candidate, trait_fit, weight in legal_priors
    )
    selected_prior = next((prior for prior in priors if prior.action == selected_action), priors[0])
    top_priors = tuple(
        sorted(
            priors,
            key=lambda prior: (prior.probability, prior.legal, prior.score),
            reverse=True,
        )[:4]
    )
    legal_count = len([prior for prior in priors if prior.legal])
    top_probability = top_priors[0].probability if top_priors else 0
    entropy = _clamp(100 - top_probability + legal_count * 4, 0, 100)
    exploration_temperature = _clamp(
        30
        + int(observation_features.get("risk_index", 50)) // 4
        + max(0, 70 - agent.trait_profile.discipline) // 3
        - selected_prior.probability // 6,
        0,
        100,
    )
    trait_alignment = _clamp((selected_prior.trait_fit + selected_prior.score) // 2, 0, 100)
    return Week11SimPolicyEvaluation(
        policy_id=agent.policy_id,
        chosen_action=selected_action,
        confidence=selected_prior.probability,
        entropy=entropy,
        exploration_temperature=exploration_temperature,
        playstyle_label=_playstyle_label(agent, selected_action),
        trait_alignment=trait_alignment,
        pressure_response=_pressure_response(selected_action, observation_features),
        top_priors=top_priors,
    )


def _observation_features(
    *,
    result: Week11MatchResultLock,
    agent: Week11SimAgent,
    tick: int,
    round_id: int,
    action: Week11SimAction,
    reward: int,
) -> dict[str, Any]:
    path = _PATHS[result.selected_plan].get(agent.agent_id, _PATHS[result.selected_plan]["rook"])
    x, y = path[min((round_id - 1) * 2 + tick % 4, 7)]
    risk_index = _clamp(agent.trait_profile.risk + (8 if action in {"entry_peek", "lurk_contact"} else -4), 0, 100)
    objective_pressure = _clamp(48 + round_id * 7 + max(0, reward) * 5, 0, 100)
    combat_window = _clamp(
        (risk_index + objective_pressure) // 2
        + (12 if action in _combat_actions() else -8),
        0,
        100,
    )
    economy_pressure = _clamp(
        34
        + (tick % 4) * 9
        + (round_id - 1) * 4
        + (12 if action in {"entry_peek", "lurk_contact", "objective_execute"} else -4)
        + max(0, risk_index - 62) // 2
        - max(0, reward) * 3,
        0,
        100,
    )
    return {
        "alive_overcast": 5,
        "alive_opponent": 5,
        "own_zone": _zone_id(x, y),
        "target_zone": _target_zone(round_id, action),
        "team_pressure": _clamp(50 + tick + reward * 3, 0, 100),
        "space_control": _clamp(45 + tick * 2 + max(0, reward) * 4, 0, 100),
        "utility_pressure": _clamp(42 + (12 if action == "scan_lane" else 0) + tick, 0, 100),
        "trade_window": _clamp(40 + (12 if action == "anchor_trade" else 0) + reward * 3, 0, 100),
        "risk_index": risk_index,
        "objective_pressure": objective_pressure,
        "combat_window": combat_window,
        "economy_pressure": economy_pressure,
        "top_trait": _top_trait(agent),
    }


def _action_context(
    *,
    agent: Week11SimAgent,
    action: Week11SimAction,
    round_id: int,
    reason: str,
) -> dict[str, str]:
    top_trait = _top_trait(agent)
    return {
        "target_zone": _target_zone(round_id, action),
        "trade_partner": _trade_partner(agent.agent_id),
        "utility_kind": _utility_kind(action),
        "policy_reason": f"{top_trait} trait bias: {reason}",
        "counterfactual": _counterfactual(action),
    }


def _discounted_return_x100(value_x100: int) -> int:
    scaled = value_x100 * WEEK11_RETURN_DISCOUNT_X100
    if scaled >= 0:
        return (scaled + 50) // 100
    return -((-scaled + 50) // 100)


def _return_to_go_by_tick(steps: tuple[Week11SimStep, ...]) -> dict[int, int]:
    """Discount future rewards inside each round without leaking into observations."""
    returns_by_tick: dict[int, int] = {}
    for round_id in sorted({step.round_id for step in steps}):
        running_return_x100 = 0
        round_steps = tuple(step for step in steps if step.round_id == round_id)
        for step in reversed(round_steps):
            running_return_x100 = (
                step.reward * 100 + _discounted_return_x100(running_return_x100)
            )
            returns_by_tick[step.tick] = running_return_x100
    return returns_by_tick


def _steps(result: Week11MatchResultLock, agent_lookup: dict[str, Week11SimAgent]) -> tuple[Week11SimStep, ...]:
    action_script: tuple[tuple[int, int, str, Week11SimAction, int, str, str], ...] = (
        (0, 1, "rook", "call_default", 0, "Rook opens the first episode from the selected match commitment.", "default_integrity"),
        (1, 1, "pixie", "scan_lane", 1, "Pixie spends utility to reveal the first contact lane.", "utility_timing"),
        (2, 1, "vex", "entry_peek", 2, "Vex turns the read into pressure before the second layer arrives.", "space_gained"),
        (3, 1, "sable", "round_end", 4, "Sable holds the terminal trade for the first episode.", "round_win"),
        (4, 2, "coyote", "lurk_contact", 1, "Coyote checks whether the branch is real or bait.", "trade_quality"),
        (5, 2, "rook", "rotate_call", 1, "The IGL chooses between staying narrow and resetting shape.", "default_integrity"),
        (6, 2, "pixie", "scan_lane", 1, "Pixie refreshes information before the opponent counter arrives.", "utility_timing"),
        (7, 2, "sable", "anchor_trade", 2, "Sable holds the trade window while the room commits.", "trade_quality"),
        (8, 3, "rook", "reset_shape", 1, "Rook compresses the call sheet for the final episode.", "default_integrity"),
        (9, 3, "coyote", "lurk_contact", 2, "Coyote finds the late contact that decides whether the plan scales.", "space_gained"),
        (
            10,
            3,
            "vex" if result.selected_plan != "stabilize_defaults" else "sable",
            "objective_execute" if result.result_tier == "win" else "reset_shape",
            3,
            "The final site action follows the plan's reward condition.",
            "round_win",
        ),
        (11, 3, "rook", "round_end", 4, "Terminal reward records the simulated match outcome.", "round_win"),
    )
    steps = []
    for tick, round_id, agent_id, action, reward, reason, trajectory_tag in action_script:
        agent = agent_lookup[agent_id]
        observation = (
            f"round:{round_id}",
            f"role:{agent.role}",
            f"protocol_signal:{result.protocol_signal}",
            f"analyst_read_class:{result.analyst_read_class}",
            f"commitment:{result.commitment}",
            f"outcome:{result.outcome_id}",
        )
        step_reward = _reward(result, tick, reward)
        observation_features = _observation_features(
            result=result,
            agent=agent,
            tick=tick,
            round_id=round_id,
            action=action,
            reward=step_reward,
        )
        candidate_actions = _candidate_actions(
            agent=agent,
            selected_action=action,
            observation_features=observation_features,
            round_id=round_id,
            tick=tick,
            reward=step_reward,
        )
        steps.append(
            Week11SimStep(
                tick=tick,
                round_id=round_id,
                agent_id=agent_id,
                observation=observation,
                action=action,
                reward=step_reward,
                return_to_go_x100=step_reward * 100,
                policy_id=agent.policy_id,
                reason=reason,
                trajectory_tag=trajectory_tag,
                observation_features=observation_features,
                action_context=_action_context(
                    agent=agent,
                    action=action,
                    round_id=round_id,
                    reason=reason,
                ),
                reward_components=_reward_components(
                    action=action,
                    reward=step_reward,
                    trajectory_tag=trajectory_tag,
                    risk=int(observation_features["risk_index"]),
                ),
                action_mask=_action_mask(candidate_actions),
                candidate_actions=candidate_actions,
                policy_evaluation=_policy_evaluation(
                    agent=agent,
                    selected_action=action,
                    observation_features=observation_features,
                    candidate_actions=candidate_actions,
                ),
            )
        )
    steps_with_default_returns = tuple(steps)
    return_by_tick = _return_to_go_by_tick(steps_with_default_returns)
    return tuple(
        replace(step, return_to_go_x100=return_by_tick.get(step.tick, step.reward * 100))
        for step in steps_with_default_returns
    )


def _telemetry_for_step(
    step: Week11SimStep,
    round_: Week11SimRound,
    *,
    pressure: int,
    local_tick: int,
) -> Week11SimTelemetry:
    """Translate deterministic replay state into numeric model-friendly telemetry."""
    action_modifiers: dict[Week11SimAction, tuple[int, int, int, int, int]] = {
        "call_default": (4, 2, 5, -6, 4),
        "scan_lane": (3, 14, 6, -4, 5),
        "entry_peek": (16, 4, 10, 18, 12),
        "lurk_contact": (10, 2, 8, 12, 8),
        "rotate_call": (6, 7, 12, -2, 10),
        "anchor_trade": (8, 4, 20, 2, 9),
        "objective_execute": (18, 8, 14, 8, 22),
        "reset_shape": (-2, 4, 7, -12, -3),
        "round_end": (0, 0, 0, 0, 0),
    }
    space_delta, utility_delta, trade_delta, risk_delta, objective_delta = action_modifiers[step.action]
    reward_push = step.reward * 4
    round_push = round_.reward_total * 2
    phase_push = local_tick * 3
    return Week11SimTelemetry(
        space_control=_clamp(46 + space_delta + reward_push + round_push, 0, 100),
        utility_pressure=_clamp(42 + utility_delta + phase_push + max(step.reward, 0) * 3, 0, 100),
        trade_window=_clamp(38 + trade_delta + reward_push + (8 if round_.winner == "overcast" else -4), 0, 100),
        risk_index=_clamp(44 + risk_delta - reward_push + (8 if step.reward < 0 else 0), 0, 100),
        objective_pressure=_clamp(pressure + objective_delta + phase_push, 0, 100),
    )


def _zone_control(telemetry: Week11SimTelemetry, round_: Week11SimRound) -> dict[str, int]:
    a_bias = 10 if round_.objective_lane.lower().startswith("a") else 0
    b_bias = 10 if round_.objective_lane.lower().startswith("b") else 0
    mid_bias = 10 if "mid" in round_.objective_lane.lower() else 0
    return {
        "a_site": _clamp(telemetry.objective_pressure + a_bias - 8, 0, 100),
        "b_site": _clamp(telemetry.space_control + b_bias - 10, 0, 100),
        "mid": _clamp(telemetry.trade_window + mid_bias, 0, 100),
        "spawn_lobby": _clamp(100 - telemetry.risk_index + 22, 0, 100),
    }


def _objective_site(round_: Week11SimRound) -> str:
    lane = round_.objective_lane.lower()
    if lane.startswith("a") or " a " in f" {lane} ":
        return "a_site"
    if lane.startswith("b") or " b " in f" {lane} ":
        return "b_site"
    if "mid" in lane:
        return "mid"
    return "a_site" if round_.round_id in (1, 3) else "b_site"


def _objective_carrier(step: Week11SimStep, round_: Week11SimRound) -> str:
    if step.action in {"objective_execute", "round_end"}:
        return step.agent_id
    if round_.side_phase == "attack":
        return "vex" if round_.round_id == 1 else "coyote"
    return "sable" if "retake" in round_.objective_lane.lower() else "rook"


def _objective_status(
    *,
    step: Week11SimStep,
    round_: Week11SimRound,
    local_tick: int,
) -> str:
    if local_tick == 0:
        return "setup"
    if step.action in {"entry_peek", "lurk_contact", "anchor_trade"}:
        return "contested"
    if step.action == "objective_execute":
        return "planting" if round_.side_phase == "attack" else "retaking"
    if step.action == "round_end":
        return "secured" if round_.winner == "overcast" else "lost"
    return "pressure"


def _objective_state(
    *,
    step: Week11SimStep,
    round_: Week11SimRound,
    telemetry: Week11SimTelemetry,
    local_tick: int,
) -> Week11SimObjectiveState:
    status = _objective_status(step=step, round_=round_, local_tick=local_tick)
    progress_push = max(0, step.reward) * 7
    if status == "secured":
        progress = 100
    elif status == "lost":
        progress = _clamp(telemetry.objective_pressure - 24, 0, 100)
    elif status in {"planting", "retaking"}:
        progress = _clamp(64 + progress_push, 0, 100)
    else:
        progress = _clamp(18 + local_tick * 18 + progress_push, 0, 100)
    defender_pressure = _clamp(
        100 - telemetry.objective_pressure + (14 if round_.winner == "opponent" else 0),
        0,
        100,
    )
    contested = status in {"contested", "planting", "retaking"} or telemetry.risk_index >= 66
    post_plant_seconds = 35 if status == "secured" and round_.side_phase == "attack" else 0
    site_id = _objective_site(round_)
    return Week11SimObjectiveState(
        site_id=site_id,
        status=status,
        progress=progress,
        carrier_agent_id=_objective_carrier(step, round_),
        contested=contested,
        defender_pressure=defender_pressure,
        post_plant_seconds=post_plant_seconds,
        label=f"{site_id.replace('_', ' ')} {status}",
    )


def _buy_class(team_credits: int, armor_level: int, utility_remaining: int) -> str:
    if team_credits >= 5200 and armor_level >= 70 and utility_remaining >= 45:
        return "full_buy"
    if team_credits >= 4200 and armor_level >= 55:
        return "balanced_buy"
    if team_credits >= 3000:
        return "force_buy"
    return "eco"


def _weapon_tier(buy_class: str, *, step: Week11SimStep, round_: Week11SimRound) -> str:
    if step.agent_id == "coyote" and step.action == "lurk_contact" and buy_class in {"full_buy", "balanced_buy"}:
        return "operator"
    if buy_class in {"full_buy", "balanced_buy"}:
        return "rifle"
    if buy_class == "force_buy":
        return "smg"
    if round_.side_phase == "defense":
        return "sidearm"
    return "light"


def _loadout_state(
    *,
    step: Week11SimStep,
    round_: Week11SimRound,
    telemetry: Week11SimTelemetry,
    local_tick: int,
) -> Week11SimLoadoutState:
    action_spend = {
        "call_default": 120,
        "scan_lane": 340,
        "entry_peek": 520,
        "lurk_contact": 430,
        "rotate_call": 180,
        "anchor_trade": 360,
        "objective_execute": 680,
        "reset_shape": 410,
        "round_end": 0,
    }[step.action]
    result_bonus = 560 if round_.winner == "overcast" else -460
    team_credits = _clamp(
        4800
        + round_.round_id * 360
        + max(step.reward, 0) * 260
        + result_bonus
        - local_tick * 320
        - action_spend,
        1400,
        9000,
    )
    opponent_credits = _clamp(
        4650
        + round_.round_id * 280
        + (520 if round_.winner == "opponent" else 0)
        + telemetry.risk_index * 4
        - max(step.reward, 0) * 160,
        1400,
        9000,
    )
    armor_level = _clamp(
        74 + round_.round_id * 4 + step.reward * 4 - local_tick * 5 - max(0, telemetry.risk_index - 66) // 2,
        0,
        100,
    )
    utility_remaining = _clamp(
        72
        - local_tick * 14
        + (12 if step.action in {"call_default", "scan_lane", "rotate_call", "reset_shape"} else 0)
        - (18 if step.action == "objective_execute" else 0)
        + step.reward * 3,
        0,
        100,
    )
    economy_pressure = _clamp(
        int(step.observation_features.get("economy_pressure", 0)),
        0,
        100,
    )
    buy_class = _buy_class(team_credits, armor_level, utility_remaining)
    weapon_tier = _weapon_tier(buy_class, step=step, round_=round_)
    if team_credits >= opponent_credits + 500 and economy_pressure < 62:
        advantage = "overcast"
    elif opponent_credits >= team_credits + 500 or economy_pressure >= 68:
        advantage = "opponent"
    else:
        advantage = "even"
    return Week11SimLoadoutState(
        buy_class=buy_class,
        weapon_tier=weapon_tier,
        armor_level=armor_level,
        utility_remaining=utility_remaining,
        team_credits=team_credits,
        opponent_credits=opponent_credits,
        economy_pressure=economy_pressure,
        advantage=advantage,
        label=f"{buy_class.replace('_', ' ')} - {weapon_tier}",
    )


def _score_state(
    *,
    rounds: tuple[Week11SimRound, ...],
    round_: Week11SimRound,
    local_tick: int,
    states: tuple[Week11SimAgentState, ...],
    telemetry: Week11SimTelemetry,
) -> Week11SimScoreState:
    overcast_rounds = 0
    opponent_rounds = 0
    for candidate in rounds:
        if candidate.round_id < round_.round_id or (
            candidate.round_id == round_.round_id and local_tick == 3
        ):
            if candidate.winner == "overcast":
                overcast_rounds += 1
            else:
                opponent_rounds += 1
    overcast_ids = {"rook", "vex", "sable", "pixie", "coyote"}
    alive_overcast = sum(1 for state in states if state.agent_id in overcast_ids and state.alive)
    alive_opponent = sum(1 for state in states if state.agent_id.startswith("opp_") and state.alive)
    man_advantage = alive_overcast - alive_opponent
    score_edge = overcast_rounds - opponent_rounds
    win_probability = _clamp(
        50
        + score_edge * 11
        + man_advantage * 7
        + (telemetry.space_control - 50) // 3
        + (telemetry.objective_pressure - 50) // 4
        - (telemetry.risk_index - 50) // 5,
        5,
        95,
    )
    if win_probability >= 60:
        momentum = "overcast"
    elif win_probability <= 40:
        momentum = "opponent"
    else:
        momentum = "even"
    if man_advantage > 0:
        body_read = f"man +{man_advantage}"
    elif man_advantage < 0:
        body_read = f"man {man_advantage}"
    else:
        body_read = "man even"
    swing_reason = (
        f"{body_read} | score {overcast_rounds}-{opponent_rounds} | "
        f"objective {telemetry.objective_pressure} | risk {telemetry.risk_index}"
    )
    return Week11SimScoreState(
        overcast_rounds=overcast_rounds,
        opponent_rounds=opponent_rounds,
        alive_overcast=alive_overcast,
        alive_opponent=alive_opponent,
        man_advantage=man_advantage,
        win_probability=win_probability,
        momentum=momentum,
        swing_reason=swing_reason,
    )


def _event_type(action: Week11SimAction) -> str:
    return {
        "call_default": "call",
        "scan_lane": "utility",
        "entry_peek": "risk",
        "lurk_contact": "contact",
        "rotate_call": "call",
        "anchor_trade": "trade",
        "objective_execute": "objective",
        "reset_shape": "reset",
        "round_end": "terminal",
    }[action]


def _agent_state(
    states: tuple[Week11SimAgentState, ...],
    agent_id: str,
) -> Week11SimAgentState | None:
    return next((state for state in states if state.agent_id == agent_id), None)


def _distance_score(left: Week11SimAgentState, right: Week11SimAgentState) -> int:
    return abs(left.x - right.x) + abs(left.y - right.y)


def _nearest_opponent_state(
    *,
    focus_state: Week11SimAgentState,
    states: tuple[Week11SimAgentState, ...],
    agent_lookup: dict[str, Week11SimAgent],
) -> Week11SimAgentState | None:
    focus_agent = agent_lookup.get(focus_state.agent_id)
    if focus_agent is None:
        return None
    candidates = [
        state
        for state in states
        if state.alive
        and agent_lookup.get(state.agent_id) is not None
        and agent_lookup[state.agent_id].side != focus_agent.side
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda state: _distance_score(focus_state, state))


def _line_samples(
    source: Week11SimAgentState,
    target: Week11SimAgentState,
    *,
    steps: int = 12,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            source.x + (target.x - source.x) * index / steps,
            source.y + (target.y - source.y) * index / steps,
        )
        for index in range(1, steps)
    )


def _line_blocking_cover(
    source: Week11SimAgentState,
    target: Week11SimAgentState,
    covers: tuple[Week11SimMapCover, ...],
) -> str:
    for cover in covers:
        if not cover.blocks_sight:
            continue
        left = cover.x
        right = cover.x + cover.width
        top = cover.y
        bottom = cover.y + cover.height
        for sample_x, sample_y in _line_samples(source, target):
            if left <= sample_x <= right and top <= sample_y <= bottom:
                return cover.cover_id
    return ""


def _line_blocking_utility(
    source: Week11SimAgentState,
    target: Week11SimAgentState,
    utility_zones: tuple[Week11SimUtilityZone, ...],
) -> str:
    for zone in utility_zones:
        if not zone.blocks_sight:
            continue
        radius_sq = zone.radius * zone.radius
        for sample_x, sample_y in _line_samples(source, target):
            dx = sample_x - zone.x
            dy = sample_y - zone.y
            if dx * dx + dy * dy <= radius_sq:
                return zone.zone_id
    return ""


def _sightline_confidence(
    *,
    step: Week11SimStep,
    telemetry: Week11SimTelemetry,
    distance: int,
    blocked_by_cover_id: str,
    blocked_by_utility_zone_id: str,
) -> int:
    confidence = (
        95
        - distance
        + telemetry.utility_pressure // 4
        + (16 if step.action == "scan_lane" else 0)
        + (8 if step.action in {"entry_peek", "lurk_contact"} else 0)
    )
    if blocked_by_cover_id:
        confidence -= 24
    if blocked_by_utility_zone_id:
        confidence -= 34
    return _clamp(confidence, 0, 100)


def _information_state(
    *,
    step: Week11SimStep,
    states: tuple[Week11SimAgentState, ...],
    telemetry: Week11SimTelemetry,
    utility_zones: tuple[Week11SimUtilityZone, ...],
    map_layout: Week11SimMapLayout,
    agent_lookup: dict[str, Week11SimAgent],
) -> Week11SimInformationState:
    observer_state = _agent_state(states, step.agent_id)
    observer_agent = agent_lookup.get(step.agent_id)
    if observer_state is None or observer_agent is None or not observer_state.alive:
        return Week11SimInformationState(
            observer_agent_id=step.agent_id,
            visible_agent_ids=(),
            occluded_agent_ids=(),
            last_known_positions=(),
            visible_zone_ids=(),
            occluded_zone_ids=(),
            sightlines=(),
            contact_confidence=0,
            fog_pressure=100,
            information_advantage="opponent",
        )

    visible_ids: list[str] = []
    occluded_ids: list[str] = []
    last_known_positions: list[Week11SimLastKnownPosition] = []
    sightlines: list[Week11SimSightline] = []
    visible_zones = {
        _zone_id(observer_state.x, observer_state.y),
        step.action_context.get("target_zone", _target_zone(step.round_id, step.action)),
    }
    occluded_zones: set[str] = set()

    enemy_states = [
        state
        for state in states
        if state.alive
        and agent_lookup.get(state.agent_id) is not None
        and agent_lookup[state.agent_id].side != observer_agent.side
    ]
    for enemy_state in enemy_states:
        blocked_by_cover_id = _line_blocking_cover(observer_state, enemy_state, map_layout.covers)
        blocked_by_utility_zone_id = _line_blocking_utility(observer_state, enemy_state, utility_zones)
        distance = _distance_score(observer_state, enemy_state)
        confidence = _sightline_confidence(
            step=step,
            telemetry=telemetry,
            distance=distance,
            blocked_by_cover_id=blocked_by_cover_id,
            blocked_by_utility_zone_id=blocked_by_utility_zone_id,
        )
        if confidence >= 60 and not blocked_by_utility_zone_id:
            visibility = "visible"
            visible_ids.append(enemy_state.agent_id)
            visible_zones.add(_zone_id(enemy_state.x, enemy_state.y))
        elif confidence >= 35:
            visibility = "inferred"
            occluded_ids.append(enemy_state.agent_id)
            occluded_zones.add(_zone_id(enemy_state.x, enemy_state.y))
        else:
            visibility = "hidden"
            occluded_ids.append(enemy_state.agent_id)
            occluded_zones.add(_zone_id(enemy_state.x, enemy_state.y))

        last_known_positions.append(
            Week11SimLastKnownPosition(
                agent_id=enemy_state.agent_id,
                x=enemy_state.x,
                y=enemy_state.y,
                tick=step.tick,
                confidence=confidence,
            )
        )
        blockers = []
        if blocked_by_cover_id:
            blockers.append(blocked_by_cover_id)
        if blocked_by_utility_zone_id:
            blockers.append(blocked_by_utility_zone_id)
        block_label = ", ".join(blockers) if blockers else "clear"
        sightlines.append(
            Week11SimSightline(
                source_agent_id=observer_state.agent_id,
                target_agent_id=enemy_state.agent_id,
                blocked_by_cover_id=blocked_by_cover_id,
                blocked_by_utility_zone_id=blocked_by_utility_zone_id,
                confidence=confidence,
                visibility=visibility,
                label=f"{visibility} contact via {block_label}",
            )
        )

    contact_confidence = max((line.confidence for line in sightlines), default=0)
    fog_pressure = _clamp(100 - contact_confidence + len(occluded_ids) * 5, 0, 100)
    if len(visible_ids) >= 2 or contact_confidence >= 68:
        information_advantage = "overcast"
    elif fog_pressure >= 68:
        information_advantage = "opponent"
    else:
        information_advantage = "even"

    return Week11SimInformationState(
        observer_agent_id=observer_state.agent_id,
        visible_agent_ids=tuple(visible_ids),
        occluded_agent_ids=tuple(occluded_ids),
        last_known_positions=tuple(last_known_positions),
        visible_zone_ids=tuple(sorted(zone for zone in visible_zones if zone)),
        occluded_zone_ids=tuple(sorted(zone for zone in occluded_zones if zone)),
        sightlines=tuple(sightlines),
        contact_confidence=contact_confidence,
        fog_pressure=fog_pressure,
        information_advantage=information_advantage,
    )


def _arc_advantage(*, step: Week11SimStep, telemetry: Week11SimTelemetry) -> str:
    if step.reward > 0 and telemetry.risk_index < 58:
        return "overcast"
    if step.reward < 0 or telemetry.risk_index >= 72:
        return "opponent"
    return "contested"


def _arc_polarity(advantage: str) -> str:
    if advantage == "overcast":
        return "positive"
    if advantage == "opponent":
        return "negative"
    return "watch"


def _duel_threat_level(step: Week11SimStep, telemetry: Week11SimTelemetry) -> int:
    reward_modifier = -10 if step.reward > 0 else 10 if step.reward < 0 else 0
    return _clamp(
        (telemetry.risk_index * 2 + max(0, 100 - telemetry.trade_window) + reward_modifier) // 3,
        0,
        100,
    )


def _threat_arc(
    *,
    arc_type: str,
    source: Week11SimAgentState,
    target: Week11SimAgentState,
    threat_level: int,
    advantage: str,
    label: str,
) -> Week11SimThreatArc:
    lane_id = f"{_zone_id(source.x, source.y)}->{_zone_id(target.x, target.y)}"
    return Week11SimThreatArc(
        arc_type=arc_type,
        source_agent_id=source.agent_id,
        target_agent_id=target.agent_id,
        lane_id=lane_id,
        x1=source.x,
        y1=source.y,
        x2=target.x,
        y2=target.y,
        threat_level=threat_level,
        advantage=advantage,
        label=label,
        polarity=_arc_polarity(advantage),
    )


def _frame_threat_arcs(
    *,
    step: Week11SimStep,
    states: tuple[Week11SimAgentState, ...],
    telemetry: Week11SimTelemetry,
    agent_lookup: dict[str, Week11SimAgent],
) -> tuple[Week11SimThreatArc, ...]:
    focus_state = _agent_state(states, step.agent_id)
    if focus_state is None or not focus_state.alive:
        return ()
    arcs: list[Week11SimThreatArc] = []
    opponent_state = _nearest_opponent_state(
        focus_state=focus_state,
        states=states,
        agent_lookup=agent_lookup,
    )
    if opponent_state is not None:
        advantage = _arc_advantage(step=step, telemetry=telemetry)
        arcs.append(
            _threat_arc(
                arc_type="duel_pressure",
                source=focus_state,
                target=opponent_state,
                threat_level=_duel_threat_level(step, telemetry),
                advantage=advantage,
                label=f"{step.action.replace('_', ' ')} sightline",
            )
        )
    trade_partner_id = step.action_context.get("trade_partner", "")
    trade_state = _agent_state(states, trade_partner_id)
    if (
        trade_state is not None
        and trade_state.alive
        and trade_state.agent_id != focus_state.agent_id
    ):
        arcs.append(
            _threat_arc(
                arc_type="trade_cover",
                source=trade_state,
                target=focus_state,
                threat_level=_clamp(telemetry.trade_window, 0, 100),
                advantage="overcast" if telemetry.trade_window >= 54 else "contested",
                label=f"{trade_partner_id} cover window",
            )
        )
    return tuple(arcs)


def _utility_zone(
    *,
    utility_type: str,
    agent_id: str,
    x: int,
    y: int,
    radius: int,
    duration_ticks: int,
    effect_strength: int,
    blocks_sight: bool,
    label: str,
    polarity: str,
) -> Week11SimUtilityZone:
    return Week11SimUtilityZone(
        utility_type=utility_type,
        agent_id=agent_id,
        zone_id=_zone_id(x, y),
        x=_clamp(x, 0, 100),
        y=_clamp(y, 0, 100),
        radius=_clamp(radius, 6, 24),
        duration_ticks=_clamp(duration_ticks, 1, 4),
        effect_strength=_clamp(effect_strength, 0, 100),
        blocks_sight=blocks_sight,
        label=label,
        polarity=polarity,
    )


def _utility_polarity(*, step: Week11SimStep, telemetry: Week11SimTelemetry) -> str:
    if step.reward > 0 and telemetry.utility_pressure >= 50:
        return "positive"
    if step.reward < 0 or telemetry.risk_index >= 78:
        return "negative"
    return "watch"


def _frame_utility_zones(
    *,
    step: Week11SimStep,
    states: tuple[Week11SimAgentState, ...],
    telemetry: Week11SimTelemetry,
) -> tuple[Week11SimUtilityZone, ...]:
    focus_state = _agent_state(states, step.agent_id)
    if focus_state is None or not focus_state.alive:
        return ()
    utility_kind = step.action_context.get("utility_kind", _utility_kind(step.action))
    target_zone = step.action_context.get("target_zone", _target_zone(step.round_id, step.action))
    target_x, target_y = _zone_anchor(target_zone)
    strength = _clamp(
        telemetry.utility_pressure + max(step.reward, 0) * 6 - max(0, telemetry.risk_index - 72) // 2,
        0,
        100,
    )
    polarity = _utility_polarity(step=step, telemetry=telemetry)

    if utility_kind == "default_shell":
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=focus_state.x,
                y=focus_state.y,
                radius=13,
                duration_ticks=3,
                effect_strength=_clamp(44 + telemetry.trade_window // 2, 0, 100),
                blocks_sight=False,
                label="default shell",
                polarity="watch",
            ),
        )
    if utility_kind == "reveal":
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=target_x,
                y=target_y,
                radius=15,
                duration_ticks=2,
                effect_strength=strength,
                blocks_sight=False,
                label="reveal sweep",
                polarity=polarity,
            ),
        )
    if utility_kind == "flash":
        x, y = _toward_zone(focus_state, target_zone, weight=62)
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=x,
                y=y,
                radius=10,
                duration_ticks=1,
                effect_strength=_clamp(strength + 8, 0, 100),
                blocks_sight=False,
                label="entry flash",
                polarity=polarity,
            ),
        )
    if utility_kind == "silent_contact":
        x, y = _toward_zone(focus_state, target_zone, weight=38)
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=x,
                y=y,
                radius=8,
                duration_ticks=2,
                effect_strength=_clamp(telemetry.risk_index + telemetry.space_control // 4, 0, 100),
                blocks_sight=False,
                label="silent contact",
                polarity=polarity,
            ),
        )
    if utility_kind == "rotate_ping":
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=target_x,
                y=target_y,
                radius=11,
                duration_ticks=2,
                effect_strength=_clamp(strength + telemetry.objective_pressure // 5, 0, 100),
                blocks_sight=False,
                label="rotate ping",
                polarity="positive" if step.reward >= 0 else "watch",
            ),
        )
    if utility_kind == "crossfire":
        trade_state = _agent_state(states, step.action_context.get("trade_partner", ""))
        zones = [
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=focus_state.x,
                y=focus_state.y,
                radius=12,
                duration_ticks=2,
                effect_strength=_clamp(telemetry.trade_window + 18, 0, 100),
                blocks_sight=False,
                label="crossfire hold",
                polarity=polarity,
            )
        ]
        if trade_state is not None and trade_state.alive:
            zones.append(
                _utility_zone(
                    utility_type="trade_anchor",
                    agent_id=trade_state.agent_id,
                    x=trade_state.x,
                    y=trade_state.y,
                    radius=10,
                    duration_ticks=2,
                    effect_strength=_clamp(telemetry.trade_window + 10, 0, 100),
                    blocks_sight=False,
                    label="trade anchor",
                    polarity="positive" if telemetry.trade_window >= 54 else "watch",
                )
            )
        return tuple(zones)
    if utility_kind == "smoke":
        x, y = _toward_zone(focus_state, target_zone, weight=52)
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=x,
                y=y,
                radius=17,
                duration_ticks=3,
                effect_strength=_clamp(strength + 4, 0, 100),
                blocks_sight=True,
                label="reset smoke",
                polarity=polarity,
            ),
        )
    if utility_kind == "execute":
        return (
            _utility_zone(
                utility_type=utility_kind,
                agent_id=step.agent_id,
                x=target_x,
                y=target_y,
                radius=20,
                duration_ticks=3,
                effect_strength=_clamp(strength + telemetry.objective_pressure // 4, 0, 100),
                blocks_sight=True,
                label="execute package",
                polarity=polarity,
            ),
            _utility_zone(
                utility_type="post_plant_anchor",
                agent_id=step.agent_id,
                x=focus_state.x,
                y=focus_state.y,
                radius=9,
                duration_ticks=2,
                effect_strength=_clamp(telemetry.trade_window + 8, 0, 100),
                blocks_sight=False,
                label="post plant anchor",
                polarity="positive",
            ),
        )
    return (
        _utility_zone(
            utility_type=utility_kind,
            agent_id=step.agent_id,
            x=target_x,
            y=target_y,
            radius=14,
            duration_ticks=2,
            effect_strength=_clamp(strength + 6, 0, 100),
            blocks_sight=False,
            label="terminal zone",
            polarity="positive" if step.reward >= 0 else "negative",
        ),
    )


def _combat_actions() -> set[Week11SimAction]:
    return {
        "entry_peek",
        "lurk_contact",
        "anchor_trade",
        "objective_execute",
        "round_end",
    }


def _combat_damage(
    *,
    step: Week11SimStep,
    source: Week11SimAgent,
    telemetry: Week11SimTelemetry,
) -> int:
    action_bonus = {
        "entry_peek": 16,
        "lurk_contact": 10,
        "anchor_trade": 12,
        "objective_execute": 22,
        "round_end": 8,
    }.get(step.action, 0)
    trait_push = source.trait_profile.aim // 8 + source.trait_profile.clutch // 12
    reward_push = max(step.reward, 0) * 8
    risk_drag = max(0, telemetry.risk_index - 68) // 3
    return _clamp(18 + action_bonus + trait_push + reward_push - risk_drag, 0, 100)


def _combat_polarity(*, source: Week11SimAgent, target: Week11SimAgent, eliminated: bool) -> str:
    if source.side == "overcast" and eliminated:
        return "positive"
    if target.side == "overcast" and eliminated:
        return "negative"
    if source.side == "overcast":
        return "positive"
    if target.side == "overcast":
        return "negative"
    return "watch"


def _combat_event(
    *,
    step: Week11SimStep,
    source_state: Week11SimAgentState,
    target_state: Week11SimAgentState,
    source_agent: Week11SimAgent,
    target_agent: Week11SimAgent,
    telemetry: Week11SimTelemetry,
) -> Week11SimCombatEvent:
    damage = _combat_damage(step=step, source=source_agent, telemetry=telemetry)
    target_health = max(0, target_state.health - damage)
    eliminated = (not target_state.alive) or target_health <= 0 or step.action == "round_end"
    event_type = "elimination" if eliminated else "damage"
    if step.action == "anchor_trade":
        event_type = "trade" if not eliminated else "trade_elimination"
    x = (source_state.x + target_state.x) // 2
    y = (source_state.y + target_state.y) // 2
    trait_signal = _top_trait(source_agent)
    return Week11SimCombatEvent(
        event_type=event_type,
        source_agent_id=source_state.agent_id,
        target_agent_id=target_state.agent_id,
        damage=damage,
        target_health=target_health,
        eliminated=eliminated,
        trade_window=_clamp(telemetry.trade_window, 0, 100),
        trait_signal=trait_signal,
        x=_clamp(x, 0, 100),
        y=_clamp(y, 0, 100),
        label=f"{source_agent.name} {event_type.replace('_', ' ')} via {trait_signal}",
        polarity=_combat_polarity(
            source=source_agent,
            target=target_agent,
            eliminated=eliminated,
        ),
    )


def _frame_combat_events(
    *,
    step: Week11SimStep,
    states: tuple[Week11SimAgentState, ...],
    telemetry: Week11SimTelemetry,
    agent_lookup: dict[str, Week11SimAgent],
) -> tuple[Week11SimCombatEvent, ...]:
    if step.action not in _combat_actions():
        return ()
    focus_state = _agent_state(states, step.agent_id)
    if focus_state is None or not focus_state.alive:
        return ()
    focus_agent = agent_lookup.get(focus_state.agent_id)
    if focus_agent is None:
        return ()
    target_state = _nearest_opponent_state(
        focus_state=focus_state,
        states=states,
        agent_lookup=agent_lookup,
    )
    if target_state is None:
        return ()
    target_agent = agent_lookup.get(target_state.agent_id)
    if target_agent is None:
        return ()

    primary = _combat_event(
        step=step,
        source_state=focus_state,
        target_state=target_state,
        source_agent=focus_agent,
        target_agent=target_agent,
        telemetry=telemetry,
    )
    events = [primary]
    if step.action == "anchor_trade" and telemetry.trade_window >= 58:
        trade_state = _agent_state(states, step.action_context.get("trade_partner", ""))
        trade_agent = agent_lookup.get(trade_state.agent_id) if trade_state is not None else None
        if trade_state is not None and trade_state.alive and trade_agent is not None:
            events.append(
                _combat_event(
                    step=step,
                    source_state=trade_state,
                    target_state=target_state,
                    source_agent=trade_agent,
                    target_agent=target_agent,
                    telemetry=telemetry,
                )
            )
    return tuple(events)


def _frame_events(
    *,
    step: Week11SimStep,
    states: tuple[Week11SimAgentState, ...],
    telemetry: Week11SimTelemetry,
) -> tuple[Week11SimEvent, ...]:
    state = next((item for item in states if item.agent_id == step.agent_id), None)
    if state is None:
        return ()
    return (
        Week11SimEvent(
            event_type=_event_type(step.action),
            agent_id=step.agent_id,
            zone_id=_zone_id(state.x, state.y),
            x=state.x,
            y=state.y,
            radius=_clamp(8 + telemetry.utility_pressure // 12, 8, 18),
            label=step.action.replace("_", " "),
            polarity="negative" if step.reward < 0 else "positive",
        ),
    )


def _frames(
    result: Week11MatchResultLock,
    agents: tuple[Week11SimAgent, ...],
    rounds: tuple[Week11SimRound, ...],
    steps: tuple[Week11SimStep, ...],
    map_layout: Week11SimMapLayout,
) -> tuple[Week11SimFrame, ...]:
    details = {
        "trust_the_read": (
            "Read Contact",
            "The replay emphasizes whether the scrim read appears before the opponent's second answer.",
        ),
        "attack_the_gap": (
            "Gap Punish",
            "The replay checks whether the visible branch is punished without chasing the hidden branch.",
        ),
        "stabilize_defaults": (
            "Default Hold",
            "The replay checks whether a safer shape stays proactive enough to win contact.",
        ),
    }
    title_prefix, plan_detail = details[result.selected_plan]
    phase_names = (
        "round setup",
        "first utility",
        "contact",
        "terminal",
    )
    clocks = ("1:40", "1:18", "0:44", "0:00")
    round_lookup = {round_.round_id: round_ for round_ in rounds}
    agent_lookup = {agent.agent_id: agent for agent in agents}
    frames = []
    step_by_tick = {step.tick: step for step in steps}
    for tick in range(12):
        step = step_by_tick[tick]
        round_ = round_lookup[step.round_id]
        local_tick = tick % 4
        states = tuple(_state_for_agent(agent, result, tick, round_.round_id) for agent in agents)
        pressure = 50 + sum(s.reward for s in steps[: tick + 1])
        telemetry = _telemetry_for_step(step, round_, pressure=pressure, local_tick=local_tick)
        objective_state = _objective_state(
            step=step,
            round_=round_,
            telemetry=telemetry,
            local_tick=local_tick,
        )
        loadout_state = _loadout_state(
            step=step,
            round_=round_,
            telemetry=telemetry,
            local_tick=local_tick,
        )
        score_state = _score_state(
            rounds=rounds,
            round_=round_,
            local_tick=local_tick,
            states=states,
            telemetry=telemetry,
        )
        events = _frame_events(step=step, states=states, telemetry=telemetry)
        threat_arcs = _frame_threat_arcs(
            step=step,
            states=states,
            telemetry=telemetry,
            agent_lookup=agent_lookup,
        )
        utility_zones = _frame_utility_zones(
            step=step,
            states=states,
            telemetry=telemetry,
        )
        information_state = _information_state(
            step=step,
            states=states,
            telemetry=telemetry,
            utility_zones=utility_zones,
            map_layout=map_layout,
            agent_lookup=agent_lookup,
        )
        combat_events = _frame_combat_events(
            step=step,
            states=states,
            telemetry=telemetry,
            agent_lookup=agent_lookup,
        )
        frames.append(
            Week11SimFrame(
                tick=tick,
                round_id=round_.round_id,
                clock=clocks[local_tick],
                phase=phase_names[local_tick],
                focus_agent=step.agent_id,
                event_title=f"R{round_.round_id} {title_prefix}: {step.action.replace('_', ' ')}",
                event_detail=f"{round_.objective_lane} - {plan_detail} {step.reason}",
                reward_delta=step.reward,
                team_pressure=_clamp(pressure, 0, 100),
                telemetry=telemetry,
                objective_state=objective_state,
                loadout_state=loadout_state,
                score_state=score_state,
                information_state=information_state,
                states=states,
                zone_control=_zone_control(telemetry, round_),
                events=events,
                threat_arcs=threat_arcs,
                utility_zones=utility_zones,
                combat_events=combat_events,
            )
        )
    return tuple(frames)


def _signal_template(agent: Week11SimAgent) -> tuple[str, str]:
    templates = {
        "rook": ("calling", "compress the call tree before terminal pressure"),
        "vex": ("entry discipline", "convert space without extending past trade cover"),
        "sable": ("trade discipline", "anchor the terminal trade window with lower variance"),
        "pixie": ("utility timing", "refresh information without flooding the comm channel"),
        "coyote": ("lurk timing", "delay contact until the branch is confirmed"),
    }
    return templates.get(agent.agent_id, ("role execution", "stabilize role baseline under match pressure"))


def _training_signals(
    result: Week11MatchResultLock,
    agents: tuple[Week11SimAgent, ...],
    steps: tuple[Week11SimStep, ...],
) -> tuple[Week11TrainingSignal, ...]:
    overcast_agents = [agent for agent in agents if agent.side == "overcast"]
    signals = []
    for agent in overcast_agents:
        agent_steps = [step for step in steps if step.agent_id == agent.agent_id]
        reward_total = sum(step.reward for step in agent_steps)
        source_rounds = tuple(sorted({step.round_id for step in agent_steps}))
        category, label = _signal_template(agent)
        if reward_total <= 0 or result.result_grade == "punished":
            priority = "high"
            epoch_delta = 18
        elif reward_total <= 2 or result.result_grade == "thin":
            priority = "medium"
            epoch_delta = 28
        else:
            priority = "low"
            epoch_delta = 40
        if agent.agent_id == "vex" and agent.trait_profile.risk >= 85:
            priority = "high" if result.result_grade in {"thin", "punished"} else "medium"
            label = "turn entry speed into traded pressure, not isolated pressure"
        elif agent.agent_id == "pixie" and agent.trait_profile.comms >= 90:
            label = "convert info volume into two clean timing calls"
        elif agent.agent_id == "rook" and result.selected_plan == "stabilize_defaults":
            label = "make the stable default proactive before the first rotate"

        evidence = (
            f"{len(agent_steps)} steps, reward {reward_total}, "
            f"rounds {','.join(str(round_id) for round_id in source_rounds) or 'none'}"
        )
        signals.append(
            Week11TrainingSignal(
                agent_id=agent.agent_id,
                category=category,
                priority=priority,
                label=label,
                evidence=evidence,
                source_rounds=source_rounds,
                reward_total=reward_total,
                epoch_delta=epoch_delta,
                current_policy_id=agent.policy_id,
                next_policy_id=f"{agent.policy_id}_epoch_{agent.skill_epoch_proxy + epoch_delta}",
            )
        )
    return tuple(signals)


def resolve_week11_match_simulation(
    result: Week11MatchResultLock,
    players: Sequence[Player],
    *,
    opponent_name: str,
    map_name: str,
) -> Week11MatchSimulation:
    """Resolve a Week-11 result into a deterministic tactical replay artifact."""
    overcast_agents = tuple(_agent_for_player(player, result) for player in players)
    agents = overcast_agents + _opponent_agents(opponent_name, result)
    agent_lookup = {agent.agent_id: agent for agent in agents}
    rounds = _rounds(result)
    steps = _steps(result, agent_lookup)
    map_layout = _map_layout(map_name)
    frames = _frames(result, agents, rounds, steps, map_layout)
    training_signals = _training_signals(result, agents, steps)
    sim_id = f"w11-{result.selected_plan}-{result.outcome_id}-{result.match_plan_seed}"
    viewer_summary = (
        f"{result.selected_plan} replay on {map_name}",
        f"{result.result_tier} {result.scoreline} with {result.result_grade} grade",
        f"policy trace uses {len(overcast_agents)} Overcast agents, {len(rounds)} rounds, and {len(training_signals)} training signals",
    )
    training_notes = (
        "Replace policy_id dispatch with learned model inference when RL policies exist.",
        "Use skill_epoch_proxy as the first proxy for scenario-trained policy maturity.",
        "Keep reward fields stable so saved trajectories remain comparable across model families.",
    )
    return Week11MatchSimulation(
        sim_id=sim_id,
        source_branch=result.source_branch,
        setup_branch=result.setup_branch,
        selected_plan=result.selected_plan,
        outcome_id=result.outcome_id,
        result_tier=result.result_tier,
        scoreline=result.scoreline,
        result_grade=result.result_grade,
        seed=result.match_plan_seed,
        map_name=map_name,
        map_layout=map_layout,
        opponent_name=opponent_name,
        sim_mode="deterministic_policy_trace_v1",
        agents=agents,
        rounds=rounds,
        frames=frames,
        steps=steps,
        training_signals=training_signals,
        viewer_summary=viewer_summary,
        training_notes=training_notes,
    )


def _profile_to_dict(profile: Week11SimTraitProfile) -> dict[str, int]:
    return {
        "aim": profile.aim,
        "discipline": profile.discipline,
        "tempo": profile.tempo,
        "utility": profile.utility,
        "clutch": profile.clutch,
        "comms": profile.comms,
        "risk": profile.risk,
    }


def _agent_to_dict(agent: Week11SimAgent) -> dict[str, Any]:
    return {
        "agent_id": agent.agent_id,
        "side": agent.side,
        "name": agent.name,
        "role": agent.role,
        "signature_operative": agent.signature_operative,
        "portrait_asset": agent.portrait_asset,
        "traits": list(agent.traits),
        "trait_profile": _profile_to_dict(agent.trait_profile),
        "policy_id": agent.policy_id,
        "scenario_archetype": agent.scenario_archetype,
        "skill_epoch_proxy": agent.skill_epoch_proxy,
    }


def _round_to_dict(round_: Week11SimRound) -> dict[str, Any]:
    return {
        "round_id": round_.round_id,
        "side_phase": round_.side_phase,
        "objective_lane": round_.objective_lane,
        "opening_plan": round_.opening_plan,
        "pressure_test": round_.pressure_test,
        "terminal_condition": round_.terminal_condition,
        "winner": round_.winner,
        "reward_total": round_.reward_total,
        "frame_ticks": list(round_.frame_ticks),
    }


def _state_to_dict(state: Week11SimAgentState) -> dict[str, Any]:
    return {
        "agent_id": state.agent_id,
        "x": state.x,
        "y": state.y,
        "alive": state.alive,
        "health": state.health,
        "stance": state.stance,
        "intent": state.intent,
    }


def _telemetry_to_dict(telemetry: Week11SimTelemetry) -> dict[str, int]:
    return {
        "space_control": telemetry.space_control,
        "utility_pressure": telemetry.utility_pressure,
        "trade_window": telemetry.trade_window,
        "risk_index": telemetry.risk_index,
        "objective_pressure": telemetry.objective_pressure,
    }


def _objective_state_to_dict(objective: Week11SimObjectiveState) -> dict[str, Any]:
    return {
        "site_id": objective.site_id,
        "status": objective.status,
        "progress": objective.progress,
        "carrier_agent_id": objective.carrier_agent_id,
        "contested": objective.contested,
        "defender_pressure": objective.defender_pressure,
        "post_plant_seconds": objective.post_plant_seconds,
        "label": objective.label,
    }


def _loadout_state_to_dict(loadout: Week11SimLoadoutState) -> dict[str, Any]:
    return {
        "buy_class": loadout.buy_class,
        "weapon_tier": loadout.weapon_tier,
        "armor_level": loadout.armor_level,
        "utility_remaining": loadout.utility_remaining,
        "team_credits": loadout.team_credits,
        "opponent_credits": loadout.opponent_credits,
        "economy_pressure": loadout.economy_pressure,
        "advantage": loadout.advantage,
        "label": loadout.label,
    }


def _score_state_to_dict(score: Week11SimScoreState) -> dict[str, Any]:
    return {
        "overcast_rounds": score.overcast_rounds,
        "opponent_rounds": score.opponent_rounds,
        "alive_overcast": score.alive_overcast,
        "alive_opponent": score.alive_opponent,
        "man_advantage": score.man_advantage,
        "win_probability": score.win_probability,
        "momentum": score.momentum,
        "swing_reason": score.swing_reason,
    }


def _last_known_position_to_dict(position: Week11SimLastKnownPosition) -> dict[str, Any]:
    return {
        "agent_id": position.agent_id,
        "x": position.x,
        "y": position.y,
        "tick": position.tick,
        "confidence": position.confidence,
    }


def _sightline_to_dict(sightline: Week11SimSightline) -> dict[str, Any]:
    return {
        "source_agent_id": sightline.source_agent_id,
        "target_agent_id": sightline.target_agent_id,
        "blocked_by_cover_id": sightline.blocked_by_cover_id,
        "blocked_by_utility_zone_id": sightline.blocked_by_utility_zone_id,
        "confidence": sightline.confidence,
        "visibility": sightline.visibility,
        "label": sightline.label,
    }


def _information_state_to_dict(info: Week11SimInformationState) -> dict[str, Any]:
    return {
        "observer_agent_id": info.observer_agent_id,
        "visible_agent_ids": list(info.visible_agent_ids),
        "occluded_agent_ids": list(info.occluded_agent_ids),
        "last_known_positions": [
            _last_known_position_to_dict(position) for position in info.last_known_positions
        ],
        "visible_zone_ids": list(info.visible_zone_ids),
        "occluded_zone_ids": list(info.occluded_zone_ids),
        "sightlines": [_sightline_to_dict(sightline) for sightline in info.sightlines],
        "contact_confidence": info.contact_confidence,
        "fog_pressure": info.fog_pressure,
        "information_advantage": info.information_advantage,
    }


def _event_to_dict(event: Week11SimEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "agent_id": event.agent_id,
        "zone_id": event.zone_id,
        "x": event.x,
        "y": event.y,
        "radius": event.radius,
        "label": event.label,
        "polarity": event.polarity,
    }


def _threat_arc_to_dict(arc: Week11SimThreatArc) -> dict[str, Any]:
    return {
        "arc_type": arc.arc_type,
        "source_agent_id": arc.source_agent_id,
        "target_agent_id": arc.target_agent_id,
        "lane_id": arc.lane_id,
        "x1": arc.x1,
        "y1": arc.y1,
        "x2": arc.x2,
        "y2": arc.y2,
        "threat_level": arc.threat_level,
        "advantage": arc.advantage,
        "label": arc.label,
        "polarity": arc.polarity,
    }


def _utility_zone_to_dict(zone: Week11SimUtilityZone) -> dict[str, Any]:
    return {
        "utility_type": zone.utility_type,
        "agent_id": zone.agent_id,
        "zone_id": zone.zone_id,
        "x": zone.x,
        "y": zone.y,
        "radius": zone.radius,
        "duration_ticks": zone.duration_ticks,
        "effect_strength": zone.effect_strength,
        "blocks_sight": zone.blocks_sight,
        "label": zone.label,
        "polarity": zone.polarity,
    }


def _combat_event_to_dict(event: Week11SimCombatEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "source_agent_id": event.source_agent_id,
        "target_agent_id": event.target_agent_id,
        "damage": event.damage,
        "target_health": event.target_health,
        "eliminated": event.eliminated,
        "trade_window": event.trade_window,
        "trait_signal": event.trait_signal,
        "x": event.x,
        "y": event.y,
        "label": event.label,
        "polarity": event.polarity,
    }


def _map_region_to_dict(region: Week11SimMapRegion) -> dict[str, Any]:
    return {
        "region_id": region.region_id,
        "label": region.label,
        "x": region.x,
        "y": region.y,
        "width": region.width,
        "height": region.height,
        "tactical_role": region.tactical_role,
        "priority": region.priority,
    }


def _map_cover_to_dict(cover: Week11SimMapCover) -> dict[str, Any]:
    return {
        "cover_id": cover.cover_id,
        "zone_id": cover.zone_id,
        "x": cover.x,
        "y": cover.y,
        "width": cover.width,
        "height": cover.height,
        "rotation": cover.rotation,
        "cover_type": cover.cover_type,
        "blocks_sight": cover.blocks_sight,
    }


def _map_lane_to_dict(lane: Week11SimMapLane) -> dict[str, Any]:
    return {
        "lane_id": lane.lane_id,
        "from_zone": lane.from_zone,
        "to_zone": lane.to_zone,
        "points": [[x, y] for x, y in lane.points],
        "tempo_bias": lane.tempo_bias,
        "trait_bias": lane.trait_bias,
    }


def _map_layout_to_dict(layout: Week11SimMapLayout) -> dict[str, Any]:
    return {
        "map_id": layout.map_id,
        "theme": layout.theme,
        "regions": [_map_region_to_dict(region) for region in layout.regions],
        "covers": [_map_cover_to_dict(cover) for cover in layout.covers],
        "lanes": [_map_lane_to_dict(lane) for lane in layout.lanes],
    }


def _frame_to_dict(frame: Week11SimFrame) -> dict[str, Any]:
    return {
        "tick": frame.tick,
        "round_id": frame.round_id,
        "clock": frame.clock,
        "phase": frame.phase,
        "focus_agent": frame.focus_agent,
        "event_title": frame.event_title,
        "event_detail": frame.event_detail,
        "reward_delta": frame.reward_delta,
        "team_pressure": frame.team_pressure,
        "telemetry": _telemetry_to_dict(frame.telemetry),
        "objective_state": _objective_state_to_dict(frame.objective_state),
        "loadout_state": _loadout_state_to_dict(frame.loadout_state),
        "score_state": _score_state_to_dict(frame.score_state),
        "information_state": _information_state_to_dict(frame.information_state),
        "states": [_state_to_dict(state) for state in frame.states],
        "zone_control": dict(frame.zone_control),
        "events": [_event_to_dict(event) for event in frame.events],
        "threat_arcs": [_threat_arc_to_dict(arc) for arc in frame.threat_arcs],
        "utility_zones": [_utility_zone_to_dict(zone) for zone in frame.utility_zones],
        "combat_events": [_combat_event_to_dict(event) for event in frame.combat_events],
    }


def _action_candidate_to_dict(candidate: Week11SimActionCandidate) -> dict[str, Any]:
    return {
        "action": candidate.action,
        "legal": candidate.legal,
        "score": candidate.score,
        "reason": candidate.reason,
        "mask_reason": candidate.mask_reason,
        "target_zone": candidate.target_zone,
        "target_x": candidate.target_x,
        "target_y": candidate.target_y,
        "expected_delta": candidate.expected_delta,
        "risk_delta": candidate.risk_delta,
        "utility_delta": candidate.utility_delta,
        "lane_id": candidate.lane_id,
        "counterfactual_tag": candidate.counterfactual_tag,
    }


def _action_prior_to_dict(prior: Week11SimActionPrior) -> dict[str, Any]:
    return {
        "action": prior.action,
        "probability": prior.probability,
        "legal": prior.legal,
        "score": prior.score,
        "trait_fit": prior.trait_fit,
    }


def _policy_evaluation_to_dict(evaluation: Week11SimPolicyEvaluation) -> dict[str, Any]:
    return {
        "policy_id": evaluation.policy_id,
        "chosen_action": evaluation.chosen_action,
        "confidence": evaluation.confidence,
        "entropy": evaluation.entropy,
        "exploration_temperature": evaluation.exploration_temperature,
        "playstyle_label": evaluation.playstyle_label,
        "trait_alignment": evaluation.trait_alignment,
        "pressure_response": evaluation.pressure_response,
        "top_priors": [_action_prior_to_dict(prior) for prior in evaluation.top_priors],
    }


def _step_to_dict(step: Week11SimStep) -> dict[str, Any]:
    return {
        "tick": step.tick,
        "round_id": step.round_id,
        "agent_id": step.agent_id,
        "observation": list(step.observation),
        "action": step.action,
        "reward": step.reward,
        "return_to_go_x100": step.return_to_go_x100,
        "policy_id": step.policy_id,
        "reason": step.reason,
        "trajectory_tag": step.trajectory_tag,
        "observation_features": dict(step.observation_features),
        "action_context": dict(step.action_context),
        "reward_components": dict(step.reward_components),
        "action_mask": list(step.action_mask),
        "candidate_actions": [
            _action_candidate_to_dict(candidate) for candidate in step.candidate_actions
        ],
        "policy_evaluation": _policy_evaluation_to_dict(step.policy_evaluation),
    }


def _training_signal_to_dict(signal: Week11TrainingSignal) -> dict[str, Any]:
    return {
        "agent_id": signal.agent_id,
        "category": signal.category,
        "priority": signal.priority,
        "label": signal.label,
        "evidence": signal.evidence,
        "source_rounds": list(signal.source_rounds),
        "reward_total": signal.reward_total,
        "epoch_delta": signal.epoch_delta,
        "current_policy_id": signal.current_policy_id,
        "next_policy_id": signal.next_policy_id,
    }


def week11_match_sim_to_dict(sim: Week11MatchSimulation) -> dict[str, Any]:
    """Dictionary form used by JSON export and the web viewer."""
    return {
        "artifact_type": "week11_match_sim",
        "checkpoint": "week11_match_sim",
        "schema_version": 1,
        "source_artifact": WEEK11_MATCH_RESULT_FILENAME,
        "source_artifacts": {
            "week11_match_result": WEEK11_MATCH_RESULT_FILENAME,
        },
        "week": 11,
        "route": "/week11/match/viewer",
        "sim_id": sim.sim_id,
        "source_branch": sim.source_branch,
        "setup_branch": sim.setup_branch,
        "selected_plan": sim.selected_plan,
        "outcome_id": sim.outcome_id,
        "result_tier": sim.result_tier,
        "scoreline": sim.scoreline,
        "result_grade": sim.result_grade,
        "seed": sim.seed,
        "map_name": sim.map_name,
        "map_layout": _map_layout_to_dict(sim.map_layout),
        "opponent_name": sim.opponent_name,
        "sim_mode": sim.sim_mode,
        "agents": [_agent_to_dict(agent) for agent in sim.agents],
        "rounds": [_round_to_dict(round_) for round_ in sim.rounds],
        "frames": [_frame_to_dict(frame) for frame in sim.frames],
        "steps": [_step_to_dict(step) for step in sim.steps],
        "training_signals": [_training_signal_to_dict(signal) for signal in sim.training_signals],
        "rl_contract": {
            "observation_space": list(WEEK11_SIM_OBSERVATION_SPACE),
            "action_space": list(WEEK11_SIM_ACTION_SPACE),
            "reward_fields": list(WEEK11_SIM_REWARD_FIELDS),
            "value_target_field": "steps[].return_to_go_x100",
            "discount_factor_x100": WEEK11_RETURN_DISCOUNT_X100,
            "telemetry_fields": [
                "space_control",
                "utility_pressure",
                "trade_window",
                "risk_index",
                "objective_pressure",
            ],
            "observation_feature_fields": [
                "alive_overcast",
                "alive_opponent",
                "own_zone",
                "target_zone",
                "team_pressure",
                "space_control",
                "utility_pressure",
                "trade_window",
                "risk_index",
                "objective_pressure",
                "combat_window",
                "economy_pressure",
                "top_trait",
            ],
            "reward_component_fields": list(WEEK11_SIM_REWARD_FIELDS),
            "action_mask_unit": "steps[].action_mask",
            "action_mask_alignment": "WEEK11_SIM_ACTION_SPACE order",
            "candidate_action_unit": "steps[].candidate_actions[]",
            "candidate_action_fields": [
                "action",
                "legal",
                "score",
                "mask_reason",
                "target_zone",
                "target_x",
                "target_y",
                "expected_delta",
                "risk_delta",
                "utility_delta",
                "lane_id",
                "counterfactual_tag",
            ],
            "policy_evaluation_unit": "steps[].policy_evaluation",
            "policy_evaluation_fields": [
                "policy_id",
                "chosen_action",
                "confidence",
                "entropy",
                "exploration_temperature",
                "playstyle_label",
                "trait_alignment",
                "pressure_response",
                "top_priors",
            ],
            "action_prior_unit": "steps[].policy_evaluation.top_priors[]",
            "action_prior_fields": [
                "action",
                "probability",
                "legal",
                "score",
                "trait_fit",
            ],
            "zone_control_fields": ["a_site", "b_site", "mid", "spawn_lobby"],
            "objective_state_unit": "frames[].objective_state",
            "objective_state_fields": [
                "site_id",
                "status",
                "progress",
                "carrier_agent_id",
                "contested",
                "defender_pressure",
                "post_plant_seconds",
            ],
            "loadout_state_unit": "frames[].loadout_state",
            "loadout_state_fields": [
                "buy_class",
                "weapon_tier",
                "armor_level",
                "utility_remaining",
                "team_credits",
                "opponent_credits",
                "economy_pressure",
                "advantage",
            ],
            "score_state_unit": "frames[].score_state",
            "score_state_fields": [
                "overcast_rounds",
                "opponent_rounds",
                "alive_overcast",
                "alive_opponent",
                "man_advantage",
                "win_probability",
                "momentum",
                "swing_reason",
            ],
            "information_state_unit": "frames[].information_state",
            "information_state_fields": [
                "observer_agent_id",
                "visible_agent_ids",
                "occluded_agent_ids",
                "last_known_positions",
                "visible_zone_ids",
                "occluded_zone_ids",
                "sightlines",
                "contact_confidence",
                "fog_pressure",
                "information_advantage",
            ],
            "agent_state_unit": "frames[].states[]",
            "agent_state_fields": [
                "agent_id",
                "x",
                "y",
                "alive",
                "health",
                "stance",
                "intent",
            ],
            "map_layout_unit": "map_layout",
            "map_region_unit": "map_layout.regions[]",
            "map_region_fields": [
                "region_id",
                "x",
                "y",
                "width",
                "height",
                "tactical_role",
                "priority",
            ],
            "map_cover_unit": "map_layout.covers[]",
            "map_cover_fields": [
                "cover_id",
                "zone_id",
                "x",
                "y",
                "width",
                "height",
                "blocks_sight",
            ],
            "map_lane_unit": "map_layout.lanes[]",
            "map_lane_fields": [
                "lane_id",
                "from_zone",
                "to_zone",
                "points",
                "tempo_bias",
                "trait_bias",
            ],
            "frame_event_unit": "frames[].events[]",
            "combat_event_unit": "frames[].combat_events[]",
            "combat_event_fields": [
                "event_type",
                "source_agent_id",
                "target_agent_id",
                "damage",
                "target_health",
                "eliminated",
                "trade_window",
                "trait_signal",
                "polarity",
            ],
            "threat_arc_unit": "frames[].threat_arcs[]",
            "threat_arc_fields": [
                "arc_type",
                "source_agent_id",
                "target_agent_id",
                "lane_id",
                "threat_level",
                "advantage",
                "polarity",
            ],
            "utility_zone_unit": "frames[].utility_zones[]",
            "utility_zone_fields": [
                "utility_type",
                "agent_id",
                "zone_id",
                "radius",
                "duration_ticks",
                "effect_strength",
                "blocks_sight",
                "polarity",
            ],
            "policy_hook": "agent.policy_id + scenario_archetype + skill_epoch_proxy",
            "epoch_proxy_field": "agents[].skill_epoch_proxy",
            "telemetry_unit": "frames[].telemetry",
            "training_signal_unit": "training_signals[]",
            "trajectory_unit": "steps[]",
        },
        "viewer_summary": list(sim.viewer_summary),
        "training_notes": list(sim.training_notes),
        "stops_before": "week11_development_plan",
        "next_artifact": WEEK11_DEVELOPMENT_PLAN_FILENAME,
    }


def render_week11_match_sim_json(sim: Week11MatchSimulation) -> str:
    """Canonical JSON export for the Week-11 tactical replay."""
    return json.dumps(
        {"week11_match_sim": week11_match_sim_to_dict(sim)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


_DEVELOPMENT_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _development_minutes(signal: Week11TrainingSignal) -> int:
    if signal.priority == "high":
        return 45
    if signal.priority == "medium":
        return 35
    return 25


def _development_success_metric(signal: Week11TrainingSignal) -> str:
    metrics = {
        "rook": "two clean rotate calls before first terminal contact",
        "vex": "entry contact produces trade cover within one replay tick",
        "sable": "anchor trade keeps default_integrity positive in two source rounds",
        "pixie": "info utility creates a timing call without comm overload",
        "coyote": "lurk contact starts after the confirmed branch call",
    }
    return metrics.get(signal.agent_id, "role action improves reward total in source rounds")


def _development_focus(signal: Week11TrainingSignal) -> str:
    focus = {
        "calling": "compress match calls into one default branch and one punish branch",
        "entry discipline": "run entry reps that require visible trade cover before the second peek",
        "trade discipline": "pair anchor timing with immediate refrag windows",
        "utility timing": "sequence recon and stall utility around caller-confirmed timing",
        "lurk timing": "hold late contact until rotate evidence appears in the observation",
    }
    return focus.get(signal.category, signal.label)


def _development_drill(signal: Week11TrainingSignal) -> Week11DevelopmentDrill:
    return Week11DevelopmentDrill(
        drill_id=f"w11_dev_{signal.agent_id}_{signal.category.replace(' ', '_')}",
        agent_id=signal.agent_id,
        category=signal.category,
        focus=_development_focus(signal),
        priority=signal.priority,
        source_signal=signal.label,
        source_rounds=signal.source_rounds,
        training_minutes=_development_minutes(signal),
        epoch_delta=signal.epoch_delta,
        current_policy_id=signal.current_policy_id,
        target_policy_id=signal.next_policy_id,
        success_metric=_development_success_metric(signal),
    )


def resolve_week11_development_plan(sim: Week11MatchSimulation) -> Week11DevelopmentPlan:
    """Turn replay training signals into a deterministic player-development plan."""
    drills = tuple(
        sorted(
            (_development_drill(signal) for signal in sim.training_signals),
            key=lambda drill: (
                _DEVELOPMENT_PRIORITY_ORDER.get(drill.priority, 3),
                drill.agent_id,
                drill.drill_id,
            ),
        )
    )
    training_budget = sum(drill.training_minutes for drill in drills)
    high_count = sum(1 for drill in drills if drill.priority == "high")
    coaching_summary = (
        f"{len(drills)} player drills from {len(sim.training_signals)} replay signals",
        f"{training_budget} minutes allocated with {high_count} high-priority intervention(s)",
        f"{sim.result_tier} {sim.scoreline} on {sim.map_name} stays tied to policy replay {sim.sim_id}",
    )
    rl_notes = (
        "Each drill maps one training_signal to a policy target without changing the saved replay.",
        "epoch_delta is still a proxy; future Scenario or RL models can replace target_policy_id with a trained model id.",
        "source_rounds preserve the replay windows needed for offline imitation and reward regression checks.",
    )
    return Week11DevelopmentPlan(
        sim_id=sim.sim_id,
        selected_plan=sim.selected_plan,
        outcome_id=sim.outcome_id,
        result_tier=sim.result_tier,
        training_budget_minutes=training_budget,
        drills=drills,
        coaching_summary=coaching_summary,
        rl_notes=rl_notes,
        next_hook="Feed development outputs into Week 12 prep and future learned policy selection.",
    )


def _development_drill_to_dict(drill: Week11DevelopmentDrill) -> dict[str, Any]:
    return {
        "drill_id": drill.drill_id,
        "agent_id": drill.agent_id,
        "category": drill.category,
        "focus": drill.focus,
        "priority": drill.priority,
        "source_signal": drill.source_signal,
        "source_rounds": list(drill.source_rounds),
        "training_minutes": drill.training_minutes,
        "epoch_delta": drill.epoch_delta,
        "current_policy_id": drill.current_policy_id,
        "target_policy_id": drill.target_policy_id,
        "success_metric": drill.success_metric,
    }


def week11_development_plan_to_dict(plan: Week11DevelopmentPlan) -> dict[str, Any]:
    """Dictionary form used by JSON export and the web development board."""
    drills = [_development_drill_to_dict(drill) for drill in plan.drills]
    return {
        "artifact_type": "week11_development_plan",
        "checkpoint": "week11_development_plan",
        "schema_version": 1,
        "source_artifact": WEEK11_MATCH_SIM_FILENAME,
        "source_artifacts": {
            "week11_match_sim": WEEK11_MATCH_SIM_FILENAME,
        },
        "week": 11,
        "route": "/week11/match/development",
        "sim_id": plan.sim_id,
        "selected_plan": plan.selected_plan,
        "outcome_id": plan.outcome_id,
        "result_tier": plan.result_tier,
        "training_budget_minutes": plan.training_budget_minutes,
        "drills": drills,
        "policy_targets": [
            {
                "agent_id": drill["agent_id"],
                "from_policy_id": drill["current_policy_id"],
                "to_policy_id": drill["target_policy_id"],
                "epoch_delta": drill["epoch_delta"],
                "training_minutes": drill["training_minutes"],
                "source_rounds": drill["source_rounds"],
            }
            for drill in drills
        ],
        "development_contract": {
            "input_unit": "week11_match_sim.training_signals[]",
            "output_unit": "drills[] + policy_targets[]",
            "policy_target_field": "policy_targets[].to_policy_id",
            "epoch_proxy_field": "policy_targets[].epoch_delta",
            "rl_source_window": "drills[].source_rounds",
        },
        "coaching_summary": list(plan.coaching_summary),
        "rl_notes": list(plan.rl_notes),
        "next_hook": plan.next_hook,
        "stops_before": "week11_training_dataset",
        "next_artifact": WEEK11_TRAINING_DATASET_FILENAME,
    }


def render_week11_development_plan_json(plan: Week11DevelopmentPlan) -> str:
    """Canonical JSON export for the Week-11 replay-derived development plan."""
    return json.dumps(
        {"week11_development_plan": week11_development_plan_to_dict(plan)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def week11_development_plan_from_json(text: str) -> Week11DevelopmentPlan:
    """Parse a written ``week11_development_plan.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_development_plan JSON is malformed") from exc
    plan = data.get("week11_development_plan") if isinstance(data, dict) else None
    if not isinstance(plan, dict):
        raise ValueError("week11_development_plan JSON must contain a week11_development_plan object")
    if plan.get("source_artifact") != WEEK11_MATCH_SIM_FILENAME:
        raise ValueError("week11_development_plan source_artifact must be week11_match_sim.json")
    if plan.get("selected_plan") not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_development_plan selected_plan must list a Week-11 match plan")
    if plan.get("outcome_id") not in WEEK11_MATCH_OUTCOMES:
        raise ValueError("week11_development_plan outcome_id must list a Week-11 match outcome")
    drills_raw = plan.get("drills")
    policy_targets = plan.get("policy_targets")
    if not isinstance(drills_raw, list) or not drills_raw:
        raise ValueError("week11_development_plan JSON must include drills")
    if not isinstance(policy_targets, list) or not policy_targets:
        raise ValueError("week11_development_plan JSON must include policy_targets")
    if plan.get("next_artifact") not in (None, WEEK11_TRAINING_DATASET_FILENAME):
        raise ValueError("week11_development_plan next_artifact must be null or week11_training_dataset.json")

    drills = tuple(
        Week11DevelopmentDrill(
            drill_id=str(drill.get("drill_id", "")),
            agent_id=str(drill.get("agent_id", "")),
            category=str(drill.get("category", "")),
            focus=str(drill.get("focus", "")),
            priority=str(drill.get("priority", "")),
            source_signal=str(drill.get("source_signal", "")),
            source_rounds=tuple(
                int(item) for item in drill.get("source_rounds", []) if isinstance(item, int)
            ),
            training_minutes=int(drill.get("training_minutes", 0)),
            epoch_delta=int(drill.get("epoch_delta", 0)),
            current_policy_id=str(drill.get("current_policy_id", "")),
            target_policy_id=str(drill.get("target_policy_id", "")),
            success_metric=str(drill.get("success_metric", "")),
        )
        for drill in drills_raw
        if isinstance(drill, dict)
    )
    return Week11DevelopmentPlan(
        sim_id=str(plan.get("sim_id", "")),
        selected_plan=str(plan.get("selected_plan", "")),
        outcome_id=str(plan.get("outcome_id", "")),
        result_tier=str(plan.get("result_tier", "")),
        training_budget_minutes=int(plan.get("training_budget_minutes", 0)),
        drills=drills,
        coaching_summary=tuple(str(item) for item in plan.get("coaching_summary", []) if isinstance(item, str)),
        rl_notes=tuple(str(item) for item in plan.get("rl_notes", []) if isinstance(item, str)),
        next_hook=str(plan.get("next_hook", "")),
    )


def _episode_id_for_round(sim_id: str, round_id: int) -> str:
    return f"{sim_id}_episode_r{round_id}"


def _sample_id_for_step(sim_id: str, step: Week11SimStep) -> str:
    return f"{sim_id}_t{step.tick}_{step.agent_id}"


def _split_for_round(round_id: int, *, eval_round_id: int) -> Week11DatasetSplit:
    return "eval" if round_id == eval_round_id else "train"


def _done_observation(step: Week11SimStep) -> tuple[str, ...]:
    return ("episode_done", f"round:{step.round_id}", f"agent:{step.agent_id}")


def _next_transition_for_step(
    steps: tuple[Week11SimStep, ...],
    *,
    step_index: int,
    sample_id_by_index: dict[int, str],
) -> tuple[tuple[str, ...], bool, str | None]:
    current = steps[step_index]
    if current.action == "round_end":
        return _done_observation(current), True, None
    for next_index, next_step in enumerate(steps[step_index + 1 :], start=step_index + 1):
        if next_step.round_id != current.round_id:
            if next_step.round_id > current.round_id:
                break
            continue
        if next_step.agent_id == current.agent_id:
            return next_step.observation, False, sample_id_by_index[next_index]
    return _done_observation(current), True, None


def _episodes_from_samples(
    samples: tuple[Week11TrainingSample, ...],
    *,
    sim_id: str,
) -> tuple[Week11TrainingEpisode, ...]:
    samples_by_round: dict[int, list[Week11TrainingSample]] = {}
    for sample in samples:
        samples_by_round.setdefault(sample.round_id, []).append(sample)

    episodes: list[Week11TrainingEpisode] = []
    for round_id in sorted(samples_by_round):
        round_samples = tuple(sorted(samples_by_round[round_id], key=lambda item: item.tick))
        if not round_samples:
            continue
        terminal_sample = next(
            (sample for sample in reversed(round_samples) if sample.done),
            round_samples[-1],
        )
        episodes.append(
            Week11TrainingEpisode(
                episode_id=round_samples[0].episode_id or _episode_id_for_round(sim_id, round_id),
                round_id=round_id,
                split=round_samples[0].split,
                sample_ids=tuple(sample.sample_id for sample in round_samples),
                terminal_sample_id=terminal_sample.sample_id,
                step_count=len(round_samples),
                reward_total=sum(sample.reward for sample in round_samples),
                start_tick=round_samples[0].tick,
                end_tick=round_samples[-1].tick,
                agent_ids=tuple(sorted({sample.agent_id for sample in round_samples})),
            )
        )
    return tuple(episodes)


def resolve_week11_training_dataset(
    sim: Week11MatchSimulation,
    development_plan: Week11DevelopmentPlan,
) -> Week11TrainingDataset:
    """Build a deterministic offline RL dataset from replay transitions and policy targets."""
    frame_by_tick = {frame.tick: frame for frame in sim.frames}
    drill_by_agent = {drill.agent_id: drill for drill in development_plan.drills}
    round_ids = tuple(sorted({step.round_id for step in sim.steps}))
    eval_round_id = round_ids[-1] if round_ids else 0
    sample_id_by_index = {
        index: _sample_id_for_step(sim.sim_id, step) for index, step in enumerate(sim.steps)
    }
    episode_steps_by_round: dict[int, int] = {}
    samples = []
    for index, step in enumerate(sim.steps):
        drill = drill_by_agent.get(step.agent_id)
        episode_step = episode_steps_by_round.get(step.round_id, 0)
        episode_steps_by_round[step.round_id] = episode_step + 1
        split = _split_for_round(step.round_id, eval_round_id=eval_round_id)
        next_observation, done, next_sample_id = _next_transition_for_step(
            sim.steps,
            step_index=index,
            sample_id_by_index=sample_id_by_index,
        )
        frame = frame_by_tick[step.tick]
        samples.append(
            Week11TrainingSample(
                sample_id=sample_id_by_index[index],
                episode_id=_episode_id_for_round(sim.sim_id, step.round_id),
                episode_step=episode_step,
                next_sample_id=next_sample_id,
                split=split,
                agent_id=step.agent_id,
                tick=step.tick,
                round_id=step.round_id,
                observation=step.observation,
                action=step.action,
                reward=step.reward,
                return_to_go_x100=step.return_to_go_x100,
                next_observation=next_observation,
                done=done or step.action == "round_end",
                telemetry=frame.telemetry,
                observation_features=step.observation_features,
                reward_components=step.reward_components,
                action_mask=step.action_mask,
                candidate_actions=step.candidate_actions,
                target_policy_id=drill.target_policy_id if drill else step.policy_id,
                source_drill_id=drill.drill_id if drill else "none",
            )
        )
    policy_targets = tuple(
        {
            "agent_id": drill.agent_id,
            "from_policy_id": drill.current_policy_id,
            "to_policy_id": drill.target_policy_id,
            "epoch_delta": drill.epoch_delta,
            "source_drill_id": drill.drill_id,
        }
        for drill in development_plan.drills
    )
    return Week11TrainingDataset(
        sim_id=sim.sim_id,
        selected_plan=sim.selected_plan,
        outcome_id=sim.outcome_id,
        result_tier=sim.result_tier,
        episodes=_episodes_from_samples(tuple(samples), sim_id=sim.sim_id),
        samples=tuple(samples),
        policy_targets=policy_targets,
        dataset_notes=(
            "Offline samples pair deterministic observations/actions/rewards with replay telemetry.",
            "Episodes are round-bounded and split into train/eval for future policy learning.",
            "target_policy_id maps each sample to the development plan's next player policy.",
            "Replace target_policy_id with Scenario model ids or learned policy ids when training exists.",
        ),
    )


def _training_episode_to_dict(episode: Week11TrainingEpisode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "round_id": episode.round_id,
        "split": episode.split,
        "sample_ids": list(episode.sample_ids),
        "terminal_sample_id": episode.terminal_sample_id,
        "step_count": episode.step_count,
        "reward_total": episode.reward_total,
        "start_tick": episode.start_tick,
        "end_tick": episode.end_tick,
        "agent_ids": list(episode.agent_ids),
    }


def _training_sample_to_dict(sample: Week11TrainingSample) -> dict[str, Any]:
    return {
        "sample_id": sample.sample_id,
        "episode_id": sample.episode_id,
        "episode_step": sample.episode_step,
        "next_sample_id": sample.next_sample_id,
        "split": sample.split,
        "agent_id": sample.agent_id,
        "tick": sample.tick,
        "round_id": sample.round_id,
        "observation": list(sample.observation),
        "action": sample.action,
        "reward": sample.reward,
        "return_to_go_x100": sample.return_to_go_x100,
        "next_observation": list(sample.next_observation),
        "done": sample.done,
        "telemetry": _telemetry_to_dict(sample.telemetry),
        "observation_features": dict(sample.observation_features),
        "reward_components": dict(sample.reward_components),
        "action_mask": list(sample.action_mask),
        "candidate_actions": [
            _action_candidate_to_dict(candidate) for candidate in sample.candidate_actions
        ],
        "target_policy_id": sample.target_policy_id,
        "source_drill_id": sample.source_drill_id,
    }


def week11_training_dataset_to_dict(dataset: Week11TrainingDataset) -> dict[str, Any]:
    """Dictionary form used by JSON export and the web training dataset board."""
    split_counts = {
        "train": len([sample for sample in dataset.samples if sample.split == "train"]),
        "eval": len([sample for sample in dataset.samples if sample.split == "eval"]),
    }
    return {
        "artifact_type": "week11_training_dataset",
        "checkpoint": "week11_training_dataset",
        "schema_version": 2,
        "source_artifact": WEEK11_DEVELOPMENT_PLAN_FILENAME,
        "source_artifacts": {
            "week11_match_sim": WEEK11_MATCH_SIM_FILENAME,
            "week11_development_plan": WEEK11_DEVELOPMENT_PLAN_FILENAME,
        },
        "week": 11,
        "route": "/week11/match/training-dataset",
        "sim_id": dataset.sim_id,
        "selected_plan": dataset.selected_plan,
        "outcome_id": dataset.outcome_id,
        "result_tier": dataset.result_tier,
        "episode_count": len(dataset.episodes),
        "sample_count": len(dataset.samples),
        "split_counts": split_counts,
        "episodes": [_training_episode_to_dict(episode) for episode in dataset.episodes],
        "samples": [_training_sample_to_dict(sample) for sample in dataset.samples],
        "policy_targets": list(dataset.policy_targets),
        "dataset_contract": {
            "format": "offline_rl_transition_v1",
            "episode_format": "round_bounded_episode_v1",
            "observation_space": list(WEEK11_SIM_OBSERVATION_SPACE),
            "action_space": list(WEEK11_SIM_ACTION_SPACE),
            "reward_fields": list(WEEK11_SIM_REWARD_FIELDS),
            "value_target_field": "samples[].return_to_go_x100",
            "discount_factor_x100": WEEK11_RETURN_DISCOUNT_X100,
            "telemetry_fields": [
                "space_control",
                "utility_pressure",
                "trade_window",
                "risk_index",
                "objective_pressure",
            ],
            "observation_feature_fields": [
                "samples[].observation_features",
            ],
            "reward_component_fields": [
                "samples[].reward_components",
            ],
            "action_mask_unit": "samples[].action_mask",
            "action_mask_alignment": "WEEK11_SIM_ACTION_SPACE order",
            "candidate_action_unit": "samples[].candidate_actions[]",
            "transition_unit": "samples[]",
            "episode_unit": "episodes[]",
            "episode_id_field": "samples[].episode_id",
            "episode_step_field": "samples[].episode_step",
            "next_sample_id_field": "samples[].next_sample_id",
            "split_field": "samples[].split",
            "split_values": ["train", "eval"],
            "training_split": "train",
            "held_out_split": "eval",
            "policy_target_field": "samples[].target_policy_id",
        },
        "dataset_notes": list(dataset.dataset_notes),
        "stops_before": "week12_model_prep",
        "next_artifact": WEEK12_MODEL_PREP_FILENAME,
    }


def render_week11_training_dataset_json(dataset: Week11TrainingDataset) -> str:
    """Canonical JSON export for the Week-11 offline RL dataset."""
    return json.dumps(
        {"week11_training_dataset": week11_training_dataset_to_dict(dataset)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def _dataset_split_from_any(value: Any) -> Week11DatasetSplit:
    return value if value in ("train", "eval") else "train"


def _training_episode_from_dict(episode: dict[str, Any], *, sim_id: str) -> Week11TrainingEpisode:
    round_id = int(episode.get("round_id", 0))
    sample_ids = tuple(
        str(item) for item in episode.get("sample_ids", []) if isinstance(item, str)
    )
    return Week11TrainingEpisode(
        episode_id=str(episode.get("episode_id") or _episode_id_for_round(sim_id, round_id)),
        round_id=round_id,
        split=_dataset_split_from_any(episode.get("split")),
        sample_ids=sample_ids,
        terminal_sample_id=str(episode.get("terminal_sample_id", sample_ids[-1] if sample_ids else "")),
        step_count=int(episode.get("step_count", len(sample_ids))),
        reward_total=int(episode.get("reward_total", 0)),
        start_tick=int(episode.get("start_tick", 0)),
        end_tick=int(episode.get("end_tick", 0)),
        agent_ids=tuple(str(item) for item in episode.get("agent_ids", []) if isinstance(item, str)),
    )


def _training_sample_from_dict(sample: dict[str, Any], *, sim_id: str) -> Week11TrainingSample:
    round_id = int(sample.get("round_id", 0))
    parsed_sample_action = (
        sample.get("action") if sample.get("action") in WEEK11_SIM_ACTION_SPACE else "round_end"
    )
    reward = int(sample.get("reward", 0))
    raw_next_sample_id = sample.get("next_sample_id")
    return Week11TrainingSample(
        sample_id=str(sample.get("sample_id", "")),
        episode_id=str(sample.get("episode_id") or _episode_id_for_round(sim_id, round_id)),
        episode_step=int(sample.get("episode_step", 0)),
        next_sample_id=str(raw_next_sample_id) if isinstance(raw_next_sample_id, str) else None,
        split=_dataset_split_from_any(sample.get("split")),
        agent_id=str(sample.get("agent_id", "")),
        tick=int(sample.get("tick", 0)),
        round_id=round_id,
        observation=tuple(str(item) for item in sample.get("observation", []) if isinstance(item, str)),
        action=parsed_sample_action,
        reward=reward,
        return_to_go_x100=int(sample.get("return_to_go_x100", reward * 100)),
        next_observation=tuple(
            str(item) for item in sample.get("next_observation", []) if isinstance(item, str)
        ),
        done=bool(sample.get("done", False)),
        telemetry=_telemetry_from_dict(sample.get("telemetry"), team_pressure=0),
        observation_features=_observation_features_from_any(sample.get("observation_features")),
        reward_components=_int_dict_from_any(sample.get("reward_components")),
        action_mask=_action_mask_from_any(
            sample.get("action_mask"),
            selected_action=parsed_sample_action,
        ),
        candidate_actions=_candidate_actions_from_any(
            sample.get("candidate_actions"),
            selected_action=parsed_sample_action,
        ),
        target_policy_id=str(sample.get("target_policy_id", "")),
        source_drill_id=str(sample.get("source_drill_id", "")),
    )


def week11_training_dataset_from_json(text: str) -> Week11TrainingDataset:
    """Parse a written ``week11_training_dataset.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_training_dataset JSON is malformed") from exc
    dataset = data.get("week11_training_dataset") if isinstance(data, dict) else None
    if not isinstance(dataset, dict):
        raise ValueError("week11_training_dataset JSON must contain a week11_training_dataset object")
    if dataset.get("source_artifact") != WEEK11_DEVELOPMENT_PLAN_FILENAME:
        raise ValueError("week11_training_dataset source_artifact must be week11_development_plan.json")
    if dataset.get("selected_plan") not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_training_dataset selected_plan must list a Week-11 match plan")
    if dataset.get("outcome_id") not in WEEK11_MATCH_OUTCOMES:
        raise ValueError("week11_training_dataset outcome_id must list a Week-11 match outcome")
    samples_raw = dataset.get("samples")
    policy_targets_raw = dataset.get("policy_targets")
    if not isinstance(samples_raw, list) or not samples_raw:
        raise ValueError("week11_training_dataset JSON must include samples")
    if not isinstance(policy_targets_raw, list) or not policy_targets_raw:
        raise ValueError("week11_training_dataset JSON must include policy_targets")
    if dataset.get("next_artifact") not in (None, WEEK12_MODEL_PREP_FILENAME):
        raise ValueError("week11_training_dataset next_artifact must be null or week12_model_prep.json")
    sim_id = str(dataset.get("sim_id", ""))
    samples = tuple(
        _training_sample_from_dict(sample, sim_id=sim_id)
        for sample in samples_raw
        if isinstance(sample, dict)
    )
    episodes_raw = dataset.get("episodes", [])
    episodes = tuple(
        _training_episode_from_dict(episode, sim_id=sim_id)
        for episode in episodes_raw
        if isinstance(episode, dict)
    )
    if not episodes:
        episodes = _episodes_from_samples(samples, sim_id=sim_id)
    return Week11TrainingDataset(
        sim_id=sim_id,
        selected_plan=str(dataset.get("selected_plan", "")),
        outcome_id=str(dataset.get("outcome_id", "")),
        result_tier=str(dataset.get("result_tier", "")),
        episodes=episodes,
        samples=samples,
        policy_targets=tuple(dict(item) for item in policy_targets_raw if isinstance(item, dict)),
        dataset_notes=tuple(str(item) for item in dataset.get("dataset_notes", []) if isinstance(item, str)),
    )


def _profile_from_dict(data: dict[str, Any]) -> Week11SimTraitProfile:
    return Week11SimTraitProfile(
        aim=int(data.get("aim", 0)),
        discipline=int(data.get("discipline", 0)),
        tempo=int(data.get("tempo", 0)),
        utility=int(data.get("utility", 0)),
        clutch=int(data.get("clutch", 0)),
        comms=int(data.get("comms", 0)),
        risk=int(data.get("risk", 0)),
    )


def _telemetry_from_dict(data: Any, *, team_pressure: int) -> Week11SimTelemetry:
    if not isinstance(data, dict):
        return Week11SimTelemetry(
            space_control=team_pressure,
            utility_pressure=team_pressure,
            trade_window=team_pressure,
            risk_index=_clamp(100 - team_pressure, 0, 100),
            objective_pressure=team_pressure,
        )
    return Week11SimTelemetry(
        space_control=int(data.get("space_control", team_pressure)),
        utility_pressure=int(data.get("utility_pressure", team_pressure)),
        trade_window=int(data.get("trade_window", team_pressure)),
        risk_index=int(data.get("risk_index", _clamp(100 - team_pressure, 0, 100))),
        objective_pressure=int(data.get("objective_pressure", team_pressure)),
    )


def _objective_state_from_any(data: Any, *, round_id: int, team_pressure: int) -> Week11SimObjectiveState:
    if isinstance(data, dict):
        return Week11SimObjectiveState(
            site_id=str(data.get("site_id", "")),
            status=str(data.get("status", "")),
            progress=int(data.get("progress", 0)),
            carrier_agent_id=str(data.get("carrier_agent_id", "")),
            contested=bool(data.get("contested", False)),
            defender_pressure=int(data.get("defender_pressure", 0)),
            post_plant_seconds=int(data.get("post_plant_seconds", 0)),
            label=str(data.get("label", "")),
        )
    site_id = "a_site" if round_id in (1, 3) else "b_site"
    return Week11SimObjectiveState(
        site_id=site_id,
        status="legacy",
        progress=_clamp(team_pressure, 0, 100),
        carrier_agent_id="rook",
        contested=False,
        defender_pressure=_clamp(100 - team_pressure, 0, 100),
        post_plant_seconds=0,
        label=f"{site_id.replace('_', ' ')} legacy",
    )


def _loadout_state_from_any(data: Any, *, team_pressure: int) -> Week11SimLoadoutState:
    if isinstance(data, dict):
        return Week11SimLoadoutState(
            buy_class=str(data.get("buy_class", "")),
            weapon_tier=str(data.get("weapon_tier", "")),
            armor_level=int(data.get("armor_level", 0)),
            utility_remaining=int(data.get("utility_remaining", 0)),
            team_credits=int(data.get("team_credits", 0)),
            opponent_credits=int(data.get("opponent_credits", 0)),
            economy_pressure=int(data.get("economy_pressure", 0)),
            advantage=str(data.get("advantage", "")),
            label=str(data.get("label", "")),
        )
    pressure = _clamp(100 - team_pressure, 0, 100)
    return Week11SimLoadoutState(
        buy_class="legacy",
        weapon_tier="unknown",
        armor_level=team_pressure,
        utility_remaining=team_pressure,
        team_credits=4000,
        opponent_credits=4000,
        economy_pressure=pressure,
        advantage="even",
        label="legacy loadout",
    )


def _score_state_from_any(data: Any, *, team_pressure: int) -> Week11SimScoreState:
    if isinstance(data, dict):
        return Week11SimScoreState(
            overcast_rounds=int(data.get("overcast_rounds", 0)),
            opponent_rounds=int(data.get("opponent_rounds", 0)),
            alive_overcast=int(data.get("alive_overcast", 5)),
            alive_opponent=int(data.get("alive_opponent", 5)),
            man_advantage=int(data.get("man_advantage", 0)),
            win_probability=int(data.get("win_probability", team_pressure)),
            momentum=str(data.get("momentum", "even")),
            swing_reason=str(data.get("swing_reason", "")),
        )
    win_probability = _clamp(team_pressure, 5, 95)
    if win_probability >= 60:
        momentum = "overcast"
    elif win_probability <= 40:
        momentum = "opponent"
    else:
        momentum = "even"
    return Week11SimScoreState(
        overcast_rounds=0,
        opponent_rounds=0,
        alive_overcast=5,
        alive_opponent=5,
        man_advantage=0,
        win_probability=win_probability,
        momentum=momentum,
        swing_reason="legacy score state",
    )


def _last_known_positions_from_any(data: Any) -> tuple[Week11SimLastKnownPosition, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimLastKnownPosition(
            agent_id=str(position.get("agent_id", "")),
            x=int(position.get("x", 0)),
            y=int(position.get("y", 0)),
            tick=int(position.get("tick", 0)),
            confidence=int(position.get("confidence", 0)),
        )
        for position in data
        if isinstance(position, dict)
    )


def _sightlines_from_any(data: Any) -> tuple[Week11SimSightline, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimSightline(
            source_agent_id=str(sightline.get("source_agent_id", "")),
            target_agent_id=str(sightline.get("target_agent_id", "")),
            blocked_by_cover_id=str(sightline.get("blocked_by_cover_id", "")),
            blocked_by_utility_zone_id=str(sightline.get("blocked_by_utility_zone_id", "")),
            confidence=int(sightline.get("confidence", 0)),
            visibility=str(sightline.get("visibility", "hidden")),
            label=str(sightline.get("label", "")),
        )
        for sightline in data
        if isinstance(sightline, dict)
    )


def _information_state_from_any(
    data: Any,
    *,
    focus_agent: str,
    team_pressure: int,
) -> Week11SimInformationState:
    if isinstance(data, dict):
        return Week11SimInformationState(
            observer_agent_id=str(data.get("observer_agent_id", focus_agent)),
            visible_agent_ids=tuple(
                str(agent_id)
                for agent_id in data.get("visible_agent_ids", [])
                if isinstance(agent_id, str)
            ),
            occluded_agent_ids=tuple(
                str(agent_id)
                for agent_id in data.get("occluded_agent_ids", [])
                if isinstance(agent_id, str)
            ),
            last_known_positions=_last_known_positions_from_any(data.get("last_known_positions")),
            visible_zone_ids=tuple(
                str(zone_id)
                for zone_id in data.get("visible_zone_ids", [])
                if isinstance(zone_id, str)
            ),
            occluded_zone_ids=tuple(
                str(zone_id)
                for zone_id in data.get("occluded_zone_ids", [])
                if isinstance(zone_id, str)
            ),
            sightlines=_sightlines_from_any(data.get("sightlines")),
            contact_confidence=int(data.get("contact_confidence", team_pressure)),
            fog_pressure=int(data.get("fog_pressure", _clamp(100 - team_pressure, 0, 100))),
            information_advantage=str(data.get("information_advantage", "even")),
        )
    contact_confidence = _clamp(team_pressure, 0, 100)
    return Week11SimInformationState(
        observer_agent_id=focus_agent,
        visible_agent_ids=(),
        occluded_agent_ids=(),
        last_known_positions=(),
        visible_zone_ids=(),
        occluded_zone_ids=(),
        sightlines=(),
        contact_confidence=contact_confidence,
        fog_pressure=_clamp(100 - contact_confidence, 0, 100),
        information_advantage="even",
    )


def _int_dict_from_any(data: Any) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    values: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            values[str(key)] = value
    return values


def _str_dict_from_any(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def _observation_features_from_any(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    values: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            values[str(key)] = value
    return values


def _action_mask_from_any(data: Any, *, selected_action: Week11SimAction) -> tuple[int, ...]:
    if isinstance(data, list) and len(data) == len(WEEK11_SIM_ACTION_SPACE):
        return tuple(1 if item else 0 for item in data)
    return tuple(1 if action == selected_action else 0 for action in WEEK11_SIM_ACTION_SPACE)


def _candidate_actions_from_any(
    data: Any,
    *,
    selected_action: Week11SimAction,
) -> tuple[Week11SimActionCandidate, ...]:
    candidates_by_action: dict[str, Week11SimActionCandidate] = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            action = item.get("action")
            if action not in WEEK11_SIM_ACTION_SPACE:
                continue
            target_zone = str(item.get("target_zone", _target_zone(1, action)))
            target_x, target_y = _zone_anchor(target_zone)
            candidates_by_action[str(action)] = Week11SimActionCandidate(
                action=action,
                legal=bool(item.get("legal", action == selected_action)),
                score=int(item.get("score", 0)),
                reason=str(item.get("reason", "")),
                mask_reason=str(item.get("mask_reason", "")),
                target_zone=target_zone,
                target_x=int(item.get("target_x", target_x)),
                target_y=int(item.get("target_y", target_y)),
                expected_delta=int(item.get("expected_delta", 0)),
                risk_delta=int(item.get("risk_delta", 0)),
                utility_delta=int(item.get("utility_delta", 0)),
                lane_id=str(item.get("lane_id", _candidate_lane_id("spawn_lobby", target_zone, action))),
                counterfactual_tag=str(item.get("counterfactual_tag", _counterfactual(action))),
            )
    return tuple(
        candidates_by_action.get(
            action,
            Week11SimActionCandidate(
                action=action,
                legal=action == selected_action,
                score=100 if action == selected_action else 0,
                reason="Legacy artifact fallback candidate.",
                mask_reason="selected_by_policy" if action == selected_action else "legacy_masked",
                target_zone=_target_zone(1, action),
                target_x=_zone_anchor(_target_zone(1, action))[0],
                target_y=_zone_anchor(_target_zone(1, action))[1],
                expected_delta=0,
                risk_delta=0,
                utility_delta=0,
                lane_id=_candidate_lane_id("spawn_lobby", _target_zone(1, action), action),
                counterfactual_tag="selected_policy_path" if action == selected_action else _counterfactual(action),
            ),
        )
        for action in WEEK11_SIM_ACTION_SPACE
    )


def _action_priors_from_any(
    data: Any,
    *,
    candidates: tuple[Week11SimActionCandidate, ...],
    selected_action: Week11SimAction,
) -> tuple[Week11SimActionPrior, ...]:
    priors: list[Week11SimActionPrior] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            action = item.get("action")
            if action not in WEEK11_SIM_ACTION_SPACE:
                continue
            priors.append(
                Week11SimActionPrior(
                    action=action,
                    probability=_clamp(int(item.get("probability", 0)), 0, 100),
                    legal=bool(item.get("legal", action == selected_action)),
                    score=int(item.get("score", 0)),
                    trait_fit=_clamp(int(item.get("trait_fit", 0)), 0, 100),
                )
            )
    if priors:
        return tuple(priors)
    legal_candidates = [candidate for candidate in candidates if candidate.legal]
    total_score = sum(max(1, candidate.score) for candidate in legal_candidates) or 1
    return tuple(
        Week11SimActionPrior(
            action=candidate.action,
            probability=(
                (max(1, candidate.score) * 100 + total_score // 2) // total_score
                if candidate.legal
                else 0
            ),
            legal=candidate.legal,
            score=candidate.score,
            trait_fit=candidate.score if candidate.legal else 0,
        )
        for candidate in sorted(
            candidates,
            key=lambda item: (item.legal, item.score, item.action == selected_action),
            reverse=True,
        )[:4]
    )


def _policy_evaluation_from_any(
    data: Any,
    *,
    policy_id: str,
    selected_action: Week11SimAction,
    candidates: tuple[Week11SimActionCandidate, ...],
    observation_features: dict[str, Any],
) -> Week11SimPolicyEvaluation:
    evaluation = data if isinstance(data, dict) else {}
    top_priors = _action_priors_from_any(
        evaluation.get("top_priors"),
        candidates=candidates,
        selected_action=selected_action,
    )
    selected_prior = next(
        (prior for prior in top_priors if prior.action == selected_action),
        top_priors[0],
    )
    top_probability = top_priors[0].probability if top_priors else selected_prior.probability
    entropy = _clamp(int(evaluation.get("entropy", 100 - top_probability)), 0, 100)
    return Week11SimPolicyEvaluation(
        policy_id=str(evaluation.get("policy_id", policy_id)),
        chosen_action=(
            evaluation.get("chosen_action")
            if evaluation.get("chosen_action") in WEEK11_SIM_ACTION_SPACE
            else selected_action
        ),
        confidence=_clamp(int(evaluation.get("confidence", selected_prior.probability)), 0, 100),
        entropy=entropy,
        exploration_temperature=_clamp(
            int(evaluation.get("exploration_temperature", entropy // 2)),
            0,
            100,
        ),
        playstyle_label=str(evaluation.get("playstyle_label", "legacy_policy")),
        trait_alignment=_clamp(int(evaluation.get("trait_alignment", selected_prior.trait_fit)), 0, 100),
        pressure_response=str(
            evaluation.get("pressure_response", _pressure_response(selected_action, observation_features))
        ),
        top_priors=top_priors,
    )


def _step_from_dict(step: dict[str, Any]) -> Week11SimStep:
    parsed_action: Week11SimAction = (
        step.get("action") if step.get("action") in WEEK11_SIM_ACTION_SPACE else "round_end"
    )
    reward = int(step.get("reward", 0))
    observation_features = _observation_features_from_any(step.get("observation_features"))
    candidate_actions = _candidate_actions_from_any(
        step.get("candidate_actions"),
        selected_action=parsed_action,
    )
    policy_id = str(step.get("policy_id", ""))
    return Week11SimStep(
        tick=int(step.get("tick", 0)),
        round_id=int(step.get("round_id", 0)),
        agent_id=str(step.get("agent_id", "")),
        observation=tuple(str(item) for item in step.get("observation", []) if isinstance(item, str)),
        action=parsed_action,
        reward=reward,
        return_to_go_x100=int(step.get("return_to_go_x100", reward * 100)),
        policy_id=policy_id,
        reason=str(step.get("reason", "")),
        trajectory_tag=str(step.get("trajectory_tag", "")),
        observation_features=observation_features,
        action_context=_str_dict_from_any(step.get("action_context")),
        reward_components=_int_dict_from_any(step.get("reward_components")),
        action_mask=_action_mask_from_any(step.get("action_mask"), selected_action=parsed_action),
        candidate_actions=candidate_actions,
        policy_evaluation=_policy_evaluation_from_any(
            step.get("policy_evaluation"),
            policy_id=policy_id,
            selected_action=parsed_action,
            candidates=candidate_actions,
            observation_features=observation_features,
        ),
    )


def _events_from_any(data: Any) -> tuple[Week11SimEvent, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimEvent(
            event_type=str(event.get("event_type", "")),
            agent_id=str(event.get("agent_id", "")),
            zone_id=str(event.get("zone_id", "")),
            x=int(event.get("x", 0)),
            y=int(event.get("y", 0)),
            radius=int(event.get("radius", 0)),
            label=str(event.get("label", "")),
            polarity=str(event.get("polarity", "")),
        )
        for event in data
        if isinstance(event, dict)
    )


def _threat_arcs_from_any(data: Any) -> tuple[Week11SimThreatArc, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimThreatArc(
            arc_type=str(arc.get("arc_type", "")),
            source_agent_id=str(arc.get("source_agent_id", "")),
            target_agent_id=str(arc.get("target_agent_id", "")),
            lane_id=str(arc.get("lane_id", "")),
            x1=int(arc.get("x1", 0)),
            y1=int(arc.get("y1", 0)),
            x2=int(arc.get("x2", 0)),
            y2=int(arc.get("y2", 0)),
            threat_level=int(arc.get("threat_level", 0)),
            advantage=str(arc.get("advantage", "")),
            label=str(arc.get("label", "")),
            polarity=str(arc.get("polarity", "")),
        )
        for arc in data
        if isinstance(arc, dict)
    )


def _utility_zones_from_any(data: Any) -> tuple[Week11SimUtilityZone, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimUtilityZone(
            utility_type=str(zone.get("utility_type", "")),
            agent_id=str(zone.get("agent_id", "")),
            zone_id=str(zone.get("zone_id", "")),
            x=int(zone.get("x", 0)),
            y=int(zone.get("y", 0)),
            radius=int(zone.get("radius", 0)),
            duration_ticks=int(zone.get("duration_ticks", 0)),
            effect_strength=int(zone.get("effect_strength", 0)),
            blocks_sight=bool(zone.get("blocks_sight", False)),
            label=str(zone.get("label", "")),
            polarity=str(zone.get("polarity", "")),
        )
        for zone in data
        if isinstance(zone, dict)
    )


def _combat_events_from_any(data: Any) -> tuple[Week11SimCombatEvent, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimCombatEvent(
            event_type=str(event.get("event_type", "")),
            source_agent_id=str(event.get("source_agent_id", "")),
            target_agent_id=str(event.get("target_agent_id", "")),
            damage=int(event.get("damage", 0)),
            target_health=int(event.get("target_health", 0)),
            eliminated=bool(event.get("eliminated", False)),
            trade_window=int(event.get("trade_window", 0)),
            trait_signal=str(event.get("trait_signal", "")),
            x=int(event.get("x", 0)),
            y=int(event.get("y", 0)),
            label=str(event.get("label", "")),
            polarity=str(event.get("polarity", "")),
        )
        for event in data
        if isinstance(event, dict)
    )


def _map_regions_from_any(data: Any) -> tuple[Week11SimMapRegion, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimMapRegion(
            region_id=str(region.get("region_id", "")),
            label=str(region.get("label", "")),
            x=int(region.get("x", 0)),
            y=int(region.get("y", 0)),
            width=int(region.get("width", 0)),
            height=int(region.get("height", 0)),
            tactical_role=str(region.get("tactical_role", "")),
            priority=int(region.get("priority", 0)),
        )
        for region in data
        if isinstance(region, dict)
    )


def _map_covers_from_any(data: Any) -> tuple[Week11SimMapCover, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimMapCover(
            cover_id=str(cover.get("cover_id", "")),
            zone_id=str(cover.get("zone_id", "")),
            x=int(cover.get("x", 0)),
            y=int(cover.get("y", 0)),
            width=int(cover.get("width", 0)),
            height=int(cover.get("height", 0)),
            rotation=int(cover.get("rotation", 0)),
            cover_type=str(cover.get("cover_type", "")),
            blocks_sight=bool(cover.get("blocks_sight", False)),
        )
        for cover in data
        if isinstance(cover, dict)
    )


def _map_lane_points_from_any(data: Any) -> tuple[tuple[int, int], ...]:
    if not isinstance(data, list):
        return ()
    points: list[tuple[int, int]] = []
    for point in data:
        if (
            isinstance(point, list)
            and len(point) == 2
            and isinstance(point[0], int)
            and isinstance(point[1], int)
        ):
            points.append((point[0], point[1]))
    return tuple(points)


def _map_lanes_from_any(data: Any) -> tuple[Week11SimMapLane, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(
        Week11SimMapLane(
            lane_id=str(lane.get("lane_id", "")),
            from_zone=str(lane.get("from_zone", "")),
            to_zone=str(lane.get("to_zone", "")),
            points=_map_lane_points_from_any(lane.get("points")),
            tempo_bias=int(lane.get("tempo_bias", 0)),
            trait_bias=str(lane.get("trait_bias", "")),
        )
        for lane in data
        if isinstance(lane, dict)
    )


def _map_layout_from_any(data: Any, *, map_name: str) -> Week11SimMapLayout:
    fallback = _map_layout(map_name)
    if not isinstance(data, dict):
        return fallback
    regions = _map_regions_from_any(data.get("regions"))
    covers = _map_covers_from_any(data.get("covers"))
    lanes = _map_lanes_from_any(data.get("lanes"))
    if not regions or not covers or not lanes:
        return fallback
    return Week11SimMapLayout(
        map_id=str(data.get("map_id", fallback.map_id)),
        theme=str(data.get("theme", fallback.theme)),
        regions=regions,
        covers=covers,
        lanes=lanes,
    )


def week11_match_sim_from_json(text: str) -> Week11MatchSimulation:
    """Parse a written ``week11_match_sim.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_match_sim JSON is malformed") from exc
    sim = data.get("week11_match_sim") if isinstance(data, dict) else None
    if not isinstance(sim, dict):
        raise ValueError("week11_match_sim JSON must contain a week11_match_sim object")
    if sim.get("source_artifact") != WEEK11_MATCH_RESULT_FILENAME:
        raise ValueError("week11_match_sim source_artifact must be week11_match_result.json")
    if sim.get("selected_plan") not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_match_sim selected_plan must list a Week-11 match plan")
    if sim.get("outcome_id") not in WEEK11_MATCH_OUTCOMES:
        raise ValueError("week11_match_sim outcome_id must list a Week-11 match outcome")
    agents_raw = sim.get("agents")
    rounds_raw = sim.get("rounds")
    frames_raw = sim.get("frames")
    steps_raw = sim.get("steps")
    training_signals_raw = sim.get("training_signals")
    rl_contract = sim.get("rl_contract")
    if not isinstance(agents_raw, list) or not agents_raw:
        raise ValueError("week11_match_sim JSON must include agents")
    if not isinstance(rounds_raw, list) or not rounds_raw:
        raise ValueError("week11_match_sim JSON must include rounds")
    if not isinstance(frames_raw, list) or not frames_raw:
        raise ValueError("week11_match_sim JSON must include frames")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("week11_match_sim JSON must include steps")
    if not isinstance(training_signals_raw, list) or not training_signals_raw:
        raise ValueError("week11_match_sim JSON must include training_signals")
    if not isinstance(rl_contract, dict):
        raise ValueError("week11_match_sim JSON must include rl_contract")
    if sim.get("next_artifact") not in (None, WEEK11_DEVELOPMENT_PLAN_FILENAME):
        raise ValueError("week11_match_sim next_artifact must be null or week11_development_plan.json")

    agents = tuple(
        Week11SimAgent(
            agent_id=str(agent.get("agent_id", "")),
            side="opponent" if agent.get("side") == "opponent" else "overcast",
            name=str(agent.get("name", "")),
            role=str(agent.get("role", "")),
            signature_operative=str(agent.get("signature_operative", "")),
            portrait_asset=str(agent.get("portrait_asset", "")),
            traits=tuple(str(item) for item in agent.get("traits", []) if isinstance(item, str)),
            trait_profile=_profile_from_dict(agent.get("trait_profile", {})),
            policy_id=str(agent.get("policy_id", "")),
            scenario_archetype=str(agent.get("scenario_archetype", "")),
            skill_epoch_proxy=int(agent.get("skill_epoch_proxy", 0)),
        )
        for agent in agents_raw
        if isinstance(agent, dict)
    )
    rounds = tuple(
        Week11SimRound(
            round_id=int(round_.get("round_id", 0)),
            side_phase=str(round_.get("side_phase", "")),
            objective_lane=str(round_.get("objective_lane", "")),
            opening_plan=str(round_.get("opening_plan", "")),
            pressure_test=str(round_.get("pressure_test", "")),
            terminal_condition=str(round_.get("terminal_condition", "")),
            winner="opponent" if round_.get("winner") == "opponent" else "overcast",
            reward_total=int(round_.get("reward_total", 0)),
            frame_ticks=tuple(int(item) for item in round_.get("frame_ticks", []) if isinstance(item, int)),
        )
        for round_ in rounds_raw
        if isinstance(round_, dict)
    )
    frames = tuple(
        Week11SimFrame(
            tick=int(frame.get("tick", 0)),
            round_id=int(frame.get("round_id", 0)),
            clock=str(frame.get("clock", "")),
            phase=str(frame.get("phase", "")),
            focus_agent=str(frame.get("focus_agent", "")),
            event_title=str(frame.get("event_title", "")),
            event_detail=str(frame.get("event_detail", "")),
            reward_delta=int(frame.get("reward_delta", 0)),
            team_pressure=int(frame.get("team_pressure", 0)),
            telemetry=_telemetry_from_dict(
                frame.get("telemetry"),
                team_pressure=int(frame.get("team_pressure", 0)),
            ),
            objective_state=_objective_state_from_any(
                frame.get("objective_state"),
                round_id=int(frame.get("round_id", 0)),
                team_pressure=int(frame.get("team_pressure", 0)),
            ),
            loadout_state=_loadout_state_from_any(
                frame.get("loadout_state"),
                team_pressure=int(frame.get("team_pressure", 0)),
            ),
            score_state=_score_state_from_any(
                frame.get("score_state"),
                team_pressure=int(frame.get("team_pressure", 0)),
            ),
            information_state=_information_state_from_any(
                frame.get("information_state"),
                focus_agent=str(frame.get("focus_agent", "")),
                team_pressure=int(frame.get("team_pressure", 0)),
            ),
            states=tuple(
                Week11SimAgentState(
                    agent_id=str(state.get("agent_id", "")),
                    x=int(state.get("x", 0)),
                    y=int(state.get("y", 0)),
                    alive=bool(state.get("alive", False)),
                    health=int(
                        state.get(
                            "health",
                            100 if bool(state.get("alive", False)) else 0,
                        )
                    ),
                    stance=str(state.get("stance", "")),
                    intent=str(state.get("intent", "")),
                )
                for state in frame.get("states", [])
                if isinstance(state, dict)
            ),
            zone_control=_int_dict_from_any(frame.get("zone_control")),
            events=_events_from_any(frame.get("events")),
            threat_arcs=_threat_arcs_from_any(frame.get("threat_arcs")),
            utility_zones=_utility_zones_from_any(frame.get("utility_zones")),
            combat_events=_combat_events_from_any(frame.get("combat_events")),
        )
        for frame in frames_raw
        if isinstance(frame, dict)
    )
    steps = tuple(
        _step_from_dict(step)
        for step in steps_raw
        if isinstance(step, dict)
    )
    training_signals = tuple(
        Week11TrainingSignal(
            agent_id=str(signal.get("agent_id", "")),
            category=str(signal.get("category", "")),
            priority=str(signal.get("priority", "")),
            label=str(signal.get("label", "")),
            evidence=str(signal.get("evidence", "")),
            source_rounds=tuple(
                int(item) for item in signal.get("source_rounds", []) if isinstance(item, int)
            ),
            reward_total=int(signal.get("reward_total", 0)),
            epoch_delta=int(signal.get("epoch_delta", 0)),
            current_policy_id=str(signal.get("current_policy_id", "")),
            next_policy_id=str(signal.get("next_policy_id", "")),
        )
        for signal in training_signals_raw
        if isinstance(signal, dict)
    )
    return Week11MatchSimulation(
        sim_id=str(sim.get("sim_id", "")),
        source_branch=str(sim.get("source_branch", "")),
        setup_branch=str(sim.get("setup_branch", "")),
        selected_plan=str(sim.get("selected_plan", "")),
        outcome_id=str(sim.get("outcome_id", "")),
        result_tier=str(sim.get("result_tier", "")),
        scoreline=str(sim.get("scoreline", "")),
        result_grade=str(sim.get("result_grade", "")),
        seed=str(sim.get("seed", "")),
        map_name=str(sim.get("map_name", "")),
        map_layout=_map_layout_from_any(
            sim.get("map_layout"),
            map_name=str(sim.get("map_name", "")),
        ),
        opponent_name=str(sim.get("opponent_name", "")),
        sim_mode=str(sim.get("sim_mode", "")),
        agents=agents,
        rounds=rounds,
        frames=frames,
        steps=steps,
        training_signals=training_signals,
        viewer_summary=tuple(str(item) for item in sim.get("viewer_summary", []) if isinstance(item, str)),
        training_notes=tuple(str(item) for item in sim.get("training_notes", []) if isinstance(item, str)),
    )
