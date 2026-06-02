"""Deterministic Week-11 tactical replay simulator.

The simulator is intentionally small and explicit. It produces a match-viewer
artifact today, and its agents/observations/actions/rewards are shaped so a
future learned policy can replace the deterministic policy step by step.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
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
    states: tuple[Week11SimAgentState, ...]
    zone_control: dict[str, int]
    events: tuple[Week11SimEvent, ...]
    threat_arcs: tuple[Week11SimThreatArc, ...]
    utility_zones: tuple[Week11SimUtilityZone, ...]


@dataclass(frozen=True)
class Week11SimStep:
    """One RL-style step in the deterministic policy trace."""

    tick: int
    round_id: int
    agent_id: str
    observation: tuple[str, ...]
    action: Week11SimAction
    reward: int
    policy_id: str
    reason: str
    trajectory_tag: str
    observation_features: dict[str, Any]
    action_context: dict[str, str]
    reward_components: dict[str, int]


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
class Week11TrainingSample:
    """One offline RL transition sample derived from the tactical replay."""

    sample_id: str
    agent_id: str
    tick: int
    round_id: int
    observation: tuple[str, ...]
    action: Week11SimAction
    reward: int
    next_observation: tuple[str, ...]
    done: bool
    telemetry: Week11SimTelemetry
    observation_features: dict[str, Any]
    reward_components: dict[str, int]
    target_policy_id: str
    source_drill_id: str


@dataclass(frozen=True)
class Week11TrainingDataset:
    """Model-ready offline RL dataset derived from replay + development targets."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
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
    elif local_tick == 0:
        stance = "set"
        intent = "default"
    elif local_tick == 1:
        stance = "contact"
        intent = "take space"
    elif local_tick == 2:
        stance = "trade"
        intent = "convert"
    else:
        stance = "resolve"
        intent = "close round"
    return Week11SimAgentState(
        agent_id=agent.agent_id,
        x=x,
        y=y,
        alive=alive,
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
        "a_site": (70, 34),
        "b_site": (39, 68),
        "mid": (53, 52),
        "spawn_lobby": (50, 77),
        "a_main": (58, 46),
        "b_main": (36, 58),
    }.get(zone_id, (50, 50))


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
        steps.append(
            Week11SimStep(
                tick=tick,
                round_id=round_id,
                agent_id=agent_id,
                observation=observation,
                action=action,
                reward=step_reward,
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
            )
        )
    return tuple(steps)


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
                states=states,
                zone_control=_zone_control(telemetry, round_),
                events=events,
                threat_arcs=threat_arcs,
                utility_zones=utility_zones,
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
    frames = _frames(result, agents, rounds, steps)
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
        "states": [_state_to_dict(state) for state in frame.states],
        "zone_control": dict(frame.zone_control),
        "events": [_event_to_dict(event) for event in frame.events],
        "threat_arcs": [_threat_arc_to_dict(arc) for arc in frame.threat_arcs],
        "utility_zones": [_utility_zone_to_dict(zone) for zone in frame.utility_zones],
    }


def _step_to_dict(step: Week11SimStep) -> dict[str, Any]:
    return {
        "tick": step.tick,
        "round_id": step.round_id,
        "agent_id": step.agent_id,
        "observation": list(step.observation),
        "action": step.action,
        "reward": step.reward,
        "policy_id": step.policy_id,
        "reason": step.reason,
        "trajectory_tag": step.trajectory_tag,
        "observation_features": dict(step.observation_features),
        "action_context": dict(step.action_context),
        "reward_components": dict(step.reward_components),
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
                "top_trait",
            ],
            "reward_component_fields": list(WEEK11_SIM_REWARD_FIELDS),
            "zone_control_fields": ["a_site", "b_site", "mid", "spawn_lobby"],
            "frame_event_unit": "frames[].events[]",
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


def _next_observation_for_step(
    steps: tuple[Week11SimStep, ...],
    *,
    step_index: int,
) -> tuple[tuple[str, ...], bool]:
    current = steps[step_index]
    if current.action == "round_end":
        return ("episode_done", f"round:{current.round_id}", f"agent:{current.agent_id}"), True
    for next_step in steps[step_index + 1 :]:
        if next_step.agent_id == current.agent_id:
            return next_step.observation, False
    return ("episode_done", f"round:{current.round_id}", f"agent:{current.agent_id}"), True


def resolve_week11_training_dataset(
    sim: Week11MatchSimulation,
    development_plan: Week11DevelopmentPlan,
) -> Week11TrainingDataset:
    """Build a deterministic offline RL dataset from replay transitions and policy targets."""
    frame_by_tick = {frame.tick: frame for frame in sim.frames}
    drill_by_agent = {drill.agent_id: drill for drill in development_plan.drills}
    samples = []
    for index, step in enumerate(sim.steps):
        drill = drill_by_agent.get(step.agent_id)
        next_observation, done = _next_observation_for_step(sim.steps, step_index=index)
        frame = frame_by_tick[step.tick]
        samples.append(
            Week11TrainingSample(
                sample_id=f"{sim.sim_id}_t{step.tick}_{step.agent_id}",
                agent_id=step.agent_id,
                tick=step.tick,
                round_id=step.round_id,
                observation=step.observation,
                action=step.action,
                reward=step.reward,
                next_observation=next_observation,
                done=done or step.action == "round_end",
                telemetry=frame.telemetry,
                observation_features=step.observation_features,
                reward_components=step.reward_components,
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
        samples=tuple(samples),
        policy_targets=policy_targets,
        dataset_notes=(
            "Offline samples pair deterministic observations/actions/rewards with replay telemetry.",
            "target_policy_id maps each sample to the development plan's next player policy.",
            "Replace target_policy_id with Scenario model ids or learned policy ids when training exists.",
        ),
    )


def _training_sample_to_dict(sample: Week11TrainingSample) -> dict[str, Any]:
    return {
        "sample_id": sample.sample_id,
        "agent_id": sample.agent_id,
        "tick": sample.tick,
        "round_id": sample.round_id,
        "observation": list(sample.observation),
        "action": sample.action,
        "reward": sample.reward,
        "next_observation": list(sample.next_observation),
        "done": sample.done,
        "telemetry": _telemetry_to_dict(sample.telemetry),
        "observation_features": dict(sample.observation_features),
        "reward_components": dict(sample.reward_components),
        "target_policy_id": sample.target_policy_id,
        "source_drill_id": sample.source_drill_id,
    }


def week11_training_dataset_to_dict(dataset: Week11TrainingDataset) -> dict[str, Any]:
    """Dictionary form used by JSON export and the web training dataset board."""
    return {
        "artifact_type": "week11_training_dataset",
        "checkpoint": "week11_training_dataset",
        "schema_version": 1,
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
        "sample_count": len(dataset.samples),
        "samples": [_training_sample_to_dict(sample) for sample in dataset.samples],
        "policy_targets": list(dataset.policy_targets),
        "dataset_contract": {
            "format": "offline_rl_transition_v1",
            "observation_space": list(WEEK11_SIM_OBSERVATION_SPACE),
            "action_space": list(WEEK11_SIM_ACTION_SPACE),
            "reward_fields": list(WEEK11_SIM_REWARD_FIELDS),
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
            "transition_unit": "samples[]",
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
    samples = tuple(
        Week11TrainingSample(
            sample_id=str(sample.get("sample_id", "")),
            agent_id=str(sample.get("agent_id", "")),
            tick=int(sample.get("tick", 0)),
            round_id=int(sample.get("round_id", 0)),
            observation=tuple(str(item) for item in sample.get("observation", []) if isinstance(item, str)),
            action=sample.get("action") if sample.get("action") in WEEK11_SIM_ACTION_SPACE else "round_end",
            reward=int(sample.get("reward", 0)),
            next_observation=tuple(
                str(item) for item in sample.get("next_observation", []) if isinstance(item, str)
            ),
            done=bool(sample.get("done", False)),
            telemetry=_telemetry_from_dict(sample.get("telemetry"), team_pressure=0),
            observation_features=_observation_features_from_any(sample.get("observation_features")),
            reward_components=_int_dict_from_any(sample.get("reward_components")),
            target_policy_id=str(sample.get("target_policy_id", "")),
            source_drill_id=str(sample.get("source_drill_id", "")),
        )
        for sample in samples_raw
        if isinstance(sample, dict)
    )
    return Week11TrainingDataset(
        sim_id=str(dataset.get("sim_id", "")),
        selected_plan=str(dataset.get("selected_plan", "")),
        outcome_id=str(dataset.get("outcome_id", "")),
        result_tier=str(dataset.get("result_tier", "")),
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
            states=tuple(
                Week11SimAgentState(
                    agent_id=str(state.get("agent_id", "")),
                    x=int(state.get("x", 0)),
                    y=int(state.get("y", 0)),
                    alive=bool(state.get("alive", False)),
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
        )
        for frame in frames_raw
        if isinstance(frame, dict)
    )
    steps = tuple(
        Week11SimStep(
            tick=int(step.get("tick", 0)),
            round_id=int(step.get("round_id", 0)),
            agent_id=str(step.get("agent_id", "")),
            observation=tuple(str(item) for item in step.get("observation", []) if isinstance(item, str)),
            action=step.get("action") if step.get("action") in WEEK11_SIM_ACTION_SPACE else "round_end",
            reward=int(step.get("reward", 0)),
            policy_id=str(step.get("policy_id", "")),
            reason=str(step.get("reason", "")),
            trajectory_tag=str(step.get("trajectory_tag", "")),
            observation_features=_observation_features_from_any(step.get("observation_features")),
            action_context=_str_dict_from_any(step.get("action_context")),
            reward_components=_int_dict_from_any(step.get("reward_components")),
        )
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
