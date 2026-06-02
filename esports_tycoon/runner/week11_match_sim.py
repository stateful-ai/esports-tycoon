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
    states: tuple[Week11SimAgentState, ...]


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
        steps.append(
            Week11SimStep(
                tick=tick,
                round_id=round_id,
                agent_id=agent_id,
                observation=observation,
                action=action,
                reward=_reward(result, tick, reward),
                policy_id=agent.policy_id,
                reason=reason,
                trajectory_tag=trajectory_tag,
            )
        )
    return tuple(steps)


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
    frames = []
    step_by_tick = {step.tick: step for step in steps}
    for tick in range(12):
        step = step_by_tick[tick]
        round_ = round_lookup[step.round_id]
        local_tick = tick % 4
        states = tuple(_state_for_agent(agent, result, tick, round_.round_id) for agent in agents)
        pressure = 50 + sum(s.reward for s in steps[: tick + 1])
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
                states=states,
            )
        )
    return tuple(frames)


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
    sim_id = f"w11-{result.selected_plan}-{result.outcome_id}-{result.match_plan_seed}"
    viewer_summary = (
        f"{result.selected_plan} replay on {map_name}",
        f"{result.result_tier} {result.scoreline} with {result.result_grade} grade",
        f"policy trace uses {len(overcast_agents)} Overcast agents and {len(steps)} reward steps",
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
        "states": [_state_to_dict(state) for state in frame.states],
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
        "rl_contract": {
            "observation_space": list(WEEK11_SIM_OBSERVATION_SPACE),
            "action_space": list(WEEK11_SIM_ACTION_SPACE),
            "reward_fields": list(WEEK11_SIM_REWARD_FIELDS),
            "policy_hook": "agent.policy_id + scenario_archetype + skill_epoch_proxy",
            "epoch_proxy_field": "agents[].skill_epoch_proxy",
            "trajectory_unit": "steps[]",
        },
        "viewer_summary": list(sim.viewer_summary),
        "training_notes": list(sim.training_notes),
        "stops_before": "week11_post_match_review",
        "next_artifact": None,
    }


def render_week11_match_sim_json(sim: Week11MatchSimulation) -> str:
    """Canonical JSON export for the Week-11 tactical replay."""
    return json.dumps(
        {"week11_match_sim": week11_match_sim_to_dict(sim)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


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
    rl_contract = sim.get("rl_contract")
    if not isinstance(agents_raw, list) or not agents_raw:
        raise ValueError("week11_match_sim JSON must include agents")
    if not isinstance(rounds_raw, list) or not rounds_raw:
        raise ValueError("week11_match_sim JSON must include rounds")
    if not isinstance(frames_raw, list) or not frames_raw:
        raise ValueError("week11_match_sim JSON must include frames")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("week11_match_sim JSON must include steps")
    if not isinstance(rl_contract, dict):
        raise ValueError("week11_match_sim JSON must include rl_contract")
    if sim.get("next_artifact") is not None:
        raise ValueError("week11_match_sim next_artifact must be null")

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
        )
        for step in steps_raw
        if isinstance(step, dict)
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
        viewer_summary=tuple(str(item) for item in sim.get("viewer_summary", []) if isinstance(item, str)),
        training_notes=tuple(str(item) for item in sim.get("training_notes", []) if isinstance(item, str)),
    )
