"""Deterministic Week-10 fallout from the Week-9 match result artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from esports_tycoon.runner.week9 import (
    WEEK10_FALLOUT_FILENAME,
    WEEK9_MATCH_OUTCOMES,
    Week9MatchOutcome,
    Week9MatchResultLock,
    Week9MatchResultTier,
)

Week10FalloutChoice = Literal["steady_room", "raise_standards", "adapt_system"]
Week10FalloutOutcome = Literal[
    "room_recentered",
    "room_overmanaged",
    "standards_locked",
    "standards_overfit",
    "system_adjusted",
    "system_blurred",
]
Week10PrepChoice = Literal["scout_counter", "staff_review", "roster_reps"]
Week10PrepOutcome = Literal[
    "counter_read_ready",
    "counter_read_overfit",
    "review_loop_locked",
    "review_loop_drift",
    "reps_translated",
    "reps_burned",
]
Week10ScrimChoice = Literal["validate_read", "stress_execution", "stabilize_comms"]
Week10ScrimOutcome = Literal[
    "read_validated",
    "read_exposed",
    "execution_translated",
    "execution_frayed",
    "comms_stabilized",
    "comms_turtled",
]
Week10MatchPlanChoice = Literal[
    "week10_plan_protect_pressure",
    "week10_plan_trade_map",
    "week10_plan_press_advantage",
]
Week10MatchOutcome = Literal[
    "pressure_held",
    "pressure_broke",
    "map_trade_paid",
    "map_trade_late",
    "advantage_converted",
    "advantage_punished",
]
Week10MatchResultTier = Literal["win", "loss"]

WEEK10_PREP_FILENAME = "week10_prep.json"
WEEK10_SCRIM_FILENAME = "week10_scrim.json"
WEEK10_MATCH_PLAN_FILENAME = "week10_match_plan.json"
WEEK10_MATCH_RESULT_FILENAME = "week10_match_result.json"
WEEK10_FALLOUT_CHOICES: tuple[Week10FalloutChoice, ...] = (
    "steady_room",
    "raise_standards",
    "adapt_system",
)
WEEK10_FALLOUT_OUTCOMES: tuple[Week10FalloutOutcome, ...] = (
    "room_recentered",
    "room_overmanaged",
    "standards_locked",
    "standards_overfit",
    "system_adjusted",
    "system_blurred",
)
WEEK10_PREP_CHOICES: tuple[Week10PrepChoice, ...] = (
    "scout_counter",
    "staff_review",
    "roster_reps",
)
WEEK10_PREP_OUTCOMES: tuple[Week10PrepOutcome, ...] = (
    "counter_read_ready",
    "counter_read_overfit",
    "review_loop_locked",
    "review_loop_drift",
    "reps_translated",
    "reps_burned",
)
WEEK10_SCRIM_CHOICES: tuple[Week10ScrimChoice, ...] = (
    "validate_read",
    "stress_execution",
    "stabilize_comms",
)
WEEK10_SCRIM_OUTCOMES: tuple[Week10ScrimOutcome, ...] = (
    "read_validated",
    "read_exposed",
    "execution_translated",
    "execution_frayed",
    "comms_stabilized",
    "comms_turtled",
)
WEEK10_MATCH_PLAN_CHOICES: tuple[Week10MatchPlanChoice, ...] = (
    "week10_plan_protect_pressure",
    "week10_plan_trade_map",
    "week10_plan_press_advantage",
)
WEEK10_MATCH_OUTCOMES: tuple[Week10MatchOutcome, ...] = (
    "pressure_held",
    "pressure_broke",
    "map_trade_paid",
    "map_trade_late",
    "advantage_converted",
    "advantage_punished",
)


@dataclass(frozen=True)
class Week10FalloutOption:
    """One response available after the Week-9 match result."""

    value: Week10FalloutChoice
    label: str
    payoff: str
    cost: str
    posture: str


@dataclass(frozen=True)
class Week10FalloutPlan:
    """The read-only Week-10 fallout prompt before the response is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    week9_headline: str
    week9_recap: str
    week9_player_read: str
    selected_week9_plan: str
    week9_problem_id: str
    pressure_prompt: str
    recommended_choice: Week10FalloutChoice
    options: tuple[Week10FalloutOption, ...]


@dataclass(frozen=True)
class Week10FalloutLock:
    """The deterministic artifact produced by locking the Week-10 fallout response."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    week9_headline: str
    week9_recap: str
    week9_player_read: str
    selected_week9_plan: str
    week9_problem_id: str
    pressure_prompt: str
    available_choices: tuple[Week10FalloutChoice, ...]
    recommended_choice: Week10FalloutChoice
    selected_choice: Week10FalloutChoice
    choice_label: str
    followed_recommendation: bool
    outcome_id: Week10FalloutOutcome
    fallout_headline: str
    consequence: str
    carry_forward_tag: str
    visible_constraints: tuple[str, ...]
    result_basis: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week10PrepOption:
    """One prep allocation available after the Week-10 fallout lock."""

    value: Week10PrepChoice
    label: str
    lane: str
    payoff: str
    cost: str


@dataclass(frozen=True)
class Week10AdvisorPacket:
    """Deterministic in-universe analyst recommendation."""

    advisor_id: str
    recommended_prep: Week10PrepChoice
    confidence: str
    summary: str
    source_facts: tuple[str, ...]
    risk_flags: tuple[str, ...]


@dataclass(frozen=True)
class Week10PrepPlan:
    """The read-only Week-10 analyst desk before prep is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    fallout_headline: str
    fallout_consequence: str
    carry_forward_tag: str
    visible_constraints: tuple[str, ...]
    advisor_packet: Week10AdvisorPacket
    pressure_meters: tuple[tuple[str, int, str], ...]
    options: tuple[Week10PrepOption, ...]


@dataclass(frozen=True)
class Week10PrepLock:
    """The deterministic artifact produced by locking the Week-10 prep block."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    fallout_headline: str
    fallout_consequence: str
    carry_forward_tag: str
    visible_constraints: tuple[str, ...]
    advisor_packet: Week10AdvisorPacket
    pressure_meters: tuple[tuple[str, int, str], ...]
    available_choices: tuple[Week10PrepChoice, ...]
    recommended_prep: Week10PrepChoice
    selected_choice: Week10PrepChoice
    choice_label: str
    followed_recommendation: bool
    prep_blocks_available: int
    prep_blocks_spent: int
    lane: str
    outcome_id: Week10PrepOutcome
    prep_headline: str
    consequence: str
    scout_clarity: int
    room_load: int
    execution_confidence: int
    result_basis: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week10ScrimProtocol:
    """One Week-10 scrim protocol available after the prep block."""

    value: Week10ScrimChoice
    label: str
    axis: str
    payoff: str
    risk: str


@dataclass(frozen=True)
class Week10ScrimPlan:
    """The read-only Week-10 scrim lab before the protocol is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    prep_outcome_id: Week10PrepOutcome
    selected_prep: Week10PrepChoice
    prep_lane: str
    prep_headline: str
    carry_forward_tag: str
    visible_constraints: tuple[str, ...]
    scout_clarity: int
    room_load: int
    execution_confidence: int
    recommended_scrim: Week10ScrimChoice
    recommendation_reason: str
    readiness_meters: tuple[tuple[str, int, str], ...]
    lane_states: tuple[tuple[str, int, str], ...]
    protocols: tuple[Week10ScrimProtocol, ...]


@dataclass(frozen=True)
class Week10ScrimLock:
    """The deterministic artifact produced by locking the Week-10 scrim lab."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    prep_outcome_id: Week10PrepOutcome
    selected_prep: Week10PrepChoice
    prep_lane: str
    prep_headline: str
    carry_forward_tag: str
    visible_constraints: tuple[str, ...]
    scout_clarity: int
    room_load: int
    execution_confidence: int
    readiness_meters: tuple[tuple[str, int, str], ...]
    lane_states: tuple[tuple[str, int, str], ...]
    available_choices: tuple[Week10ScrimChoice, ...]
    recommended_scrim: Week10ScrimChoice
    selected_scrim: Week10ScrimChoice
    choice_label: str
    followed_recommendation: bool
    outcome_id: Week10ScrimOutcome
    scrim_headline: str
    consequence: str
    match_plan_pressure: str
    synergy_delta: int
    stress_delta: int
    clarity_delta: int
    result_basis: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week10MatchPlanOption:
    """One Week-10 match plan available after the scrim protocol."""

    value: Week10MatchPlanChoice
    label: str
    payoff: str
    cost: str
    read_basis: str
    commitment: str
    result_constraint: str


@dataclass(frozen=True)
class Week10MatchPlanPreview:
    """The read-only Week-10 match-plan preview before the plan is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    prep_outcome_id: Week10PrepOutcome
    scrim_outcome_id: Week10ScrimOutcome
    selected_prep: Week10PrepChoice
    selected_scrim: Week10ScrimChoice
    prep_lane: str
    prep_headline: str
    scrim_headline: str
    match_plan_pressure: str
    scout_clarity: int
    room_load: int
    execution_confidence: int
    synergy_delta: int
    stress_delta: int
    clarity_delta: int
    lane_states: tuple[tuple[str, int, str], ...]
    recommendation_basis: str
    recommended_plan: Week10MatchPlanChoice
    recommendation_reason: str
    match_risk: str
    options: tuple[Week10MatchPlanOption, ...]


@dataclass(frozen=True)
class Week10MatchPlanLock:
    """The deterministic artifact produced by locking the Week-10 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    prep_outcome_id: Week10PrepOutcome
    scrim_outcome_id: Week10ScrimOutcome
    selected_prep: Week10PrepChoice
    selected_scrim: Week10ScrimChoice
    prep_lane: str
    prep_headline: str
    scrim_headline: str
    match_plan_pressure: str
    scout_clarity: int
    room_load: int
    execution_confidence: int
    synergy_delta: int
    stress_delta: int
    clarity_delta: int
    lane_states: tuple[tuple[str, int, str], ...]
    recommendation_basis: str
    recommended_plan: Week10MatchPlanChoice
    available_choices: tuple[Week10MatchPlanChoice, ...]
    selected_plan: Week10MatchPlanChoice
    plan_outcome_id: str
    plan_label: str
    followed_recommendation: bool
    commitment: str
    risk_taken: str
    thing_to_watch: str
    match_risk: str
    result_constraints: tuple[str, ...]
    recommendation_reason: str
    next_hook: str


@dataclass(frozen=True)
class Week10VisibleEffect:
    """One visible consequence chip rendered on the Week-10 result page."""

    value: str
    label: str
    polarity: str


@dataclass(frozen=True)
class Week10MatchResultLock:
    """The deterministic artifact produced by resolving the Week-10 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week9_outcome_id: Week9MatchOutcome
    week9_result_tier: Week9MatchResultTier
    week9_scoreline: str
    fallout_outcome_id: Week10FalloutOutcome
    prep_outcome_id: Week10PrepOutcome
    scrim_outcome_id: Week10ScrimOutcome
    selected_prep: Week10PrepChoice
    selected_scrim: Week10ScrimChoice
    selected_plan: Week10MatchPlanChoice
    recommended_plan: Week10MatchPlanChoice
    matched_recommendation: bool
    commitment: str
    match_risk: str
    match_plan_pressure: str
    outcome_id: Week10MatchOutcome
    result_tier: Week10MatchResultTier
    team_maps: int
    opponent_maps: int
    scoreline: str
    result_score: int
    result_grade: str
    headline: str
    recap: str
    player_read: str
    visible_effects: tuple[Week10VisibleEffect, ...]
    result_basis: tuple[str, ...]
    causal_chain: tuple[str, ...]
    next_hook: str


_FALLOUT_OPTIONS: tuple[Week10FalloutOption, ...] = (
    Week10FalloutOption(
        value="steady_room",
        label="Steady the room",
        payoff="Turn the Week 9 result into a calmer first meeting.",
        cost="The team may underuse a result that deserved sharper standards.",
        posture="room",
    ),
    Week10FalloutOption(
        value="raise_standards",
        label="Raise standards",
        payoff="Make the result the new bar before Week 10 prep starts.",
        cost="The staff can overfit one match and make the next block brittle.",
        posture="standards",
    ),
    Week10FalloutOption(
        value="adapt_system",
        label="Adapt the system",
        payoff="Change the process around the read the result exposed.",
        cost="The room may hear process churn instead of a clear Week 10 message.",
        posture="system",
    ),
)

_PREP_OPTIONS: tuple[Week10PrepOption, ...] = (
    Week10PrepOption(
        value="scout_counter",
        label="Scout the counter",
        lane="scout",
        payoff="Spend the block on opponent-read prep and counter-call clarity.",
        cost="The staff can overfit a read before the Week 10 opponent shows its real hand.",
    ),
    Week10PrepOption(
        value="staff_review",
        label="Run staff review",
        lane="staff",
        payoff="Align coaches and review language before the next prep cycle starts.",
        cost="The block can turn into process talk while player reps wait.",
    ),
    Week10PrepOption(
        value="roster_reps",
        label="Take roster reps",
        lane="roster",
        payoff="Turn the fallout lesson into player execution and repeatability.",
        cost="If the message is blurry, the room absorbs another load-bearing practice.",
    ),
)

_SCRIM_PROTOCOLS: tuple[Week10ScrimProtocol, ...] = (
    Week10ScrimProtocol(
        value="validate_read",
        label="Validate counter-read",
        axis="scout",
        payoff="Use the scrim block to test whether the counter-read survives real pressure.",
        risk="If the read is narrow, the block exposes it before match planning starts.",
    ),
    Week10ScrimProtocol(
        value="stress_execution",
        label="Pressure-test execution",
        axis="execution",
        payoff="Turn the prep effect into repeatable calls at scrim speed.",
        risk="If the room is carrying too much load, the test turns into forced errors.",
    ),
    Week10ScrimProtocol(
        value="stabilize_comms",
        label="Stabilize comms",
        axis="room",
        payoff="Spend the block on call discipline and shared language before the match plan.",
        risk="The team can leave safer, but with less new tactical signal.",
    ),
)

_MATCH_PLAN_OPTIONS: tuple[Week10MatchPlanOption, ...] = (
    Week10MatchPlanOption(
        value="week10_plan_protect_pressure",
        label="Protect pressure",
        payoff="Protect the lane, meter, or pressure point most exposed by scrim and readiness signals.",
        cost="Lower collapse risk can mean lower opening-map upside.",
        read_basis="match_plan_pressure",
        commitment="pressure_protection",
        result_constraint="protected_pressure_must_not_collapse",
    ),
    Week10MatchPlanOption(
        value="week10_plan_trade_map",
        label="Trade map",
        payoff="Avoid direct collision with the volatile point and win through rotations and map tradeoffs.",
        cost="The plan may decline the clearest early advantage in exchange for stability.",
        read_basis="lane_states",
        commitment="map_trade",
        result_constraint="map_trade_must_create_cross_pressure",
    ),
    Week10MatchPlanOption(
        value="week10_plan_press_advantage",
        label="Press advantage",
        payoff="Commit resources to the clearest advantage from readiness, lane state, prep, or scrim effect.",
        cost="Higher upside comes with a sharper punish window if the read is wrong.",
        read_basis="scrim_effect",
        commitment="advantage_press",
        result_constraint="pressed_advantage_must_land_before_punish",
    ),
)

_OUTCOME_COPY: dict[Week10FalloutOutcome, dict[str, object]] = {
    "room_recentered": {
        "headline": "The room gets a clearer first meeting.",
        "consequence": "The staff names the pressure without turning it into blame, so Week 10 starts with one shared read.",
        "tag": "room_recentered",
        "constraints": ("shared_language", "lower_noise", "watch_ceiling"),
    },
    "room_overmanaged": {
        "headline": "The room hears management before momentum.",
        "consequence": "The message is calm, but it turns a usable result into a meeting about feelings before the next opponent appears.",
        "tag": "room_overmanaged",
        "constraints": ("momentum_dulled", "meeting_fatigue", "prove_edge"),
    },
    "standards_locked": {
        "headline": "The result becomes the new bar.",
        "consequence": "The team leaves the review with a higher standard and a concrete repeatability demand.",
        "tag": "standards_locked",
        "constraints": ("higher_bar", "repeatability", "less_excuse_room"),
    },
    "standards_overfit": {
        "headline": "The staff overfits one result.",
        "consequence": "The new bar sounds decisive, but the room can tell it was built from a result that still needed interpretation.",
        "tag": "standards_overfit",
        "constraints": ("brittle_standard", "review_pressure", "simplify_prep"),
    },
    "system_adjusted": {
        "headline": "The process changes around the real read.",
        "consequence": "The staff adjusts the review loop around what Week 9 actually exposed instead of chasing the scoreboard.",
        "tag": "system_adjusted",
        "constraints": ("process_adjusted", "read_carried", "needs_buy_in"),
    },
    "system_blurred": {
        "headline": "The process message blurs the lesson.",
        "consequence": "The adjustment has logic, but it makes the Week 9 lesson sound more complicated than the room needs.",
        "tag": "system_blurred",
        "constraints": ("unclear_process", "message_blur", "room_check_needed"),
    },
}

_PREP_OUTCOME_COPY: dict[Week10PrepOutcome, dict[str, object]] = {
    "counter_read_ready": {
        "headline": "The analyst read becomes playable prep.",
        "consequence": "The scout block gives the staff a clearer counter without hiding the room's carry-forward pressure.",
        "effects": {"scout_clarity": 2, "room_load": 0, "execution_confidence": 1},
        "hook": "Week 10 scrim tests whether the opponent read is playable under pressure.",
    },
    "counter_read_overfit": {
        "headline": "The counter read gets too narrow.",
        "consequence": "The desk finds a pattern, but the room can feel the staff squeezing Week 9 into the next opponent.",
        "effects": {"scout_clarity": 1, "room_load": 2, "execution_confidence": -1},
        "hook": "Week 10 scrim must separate real signal from staff noise.",
    },
    "review_loop_locked": {
        "headline": "The staff review gives prep a shared language.",
        "consequence": "The block turns the fallout into short, usable terms the coaches can repeat without relitigating the result.",
        "effects": {"scout_clarity": 1, "room_load": -1, "execution_confidence": 1},
        "hook": "Week 10 scrim tests whether the shared language survives contact.",
    },
    "review_loop_drift": {
        "headline": "The review loop starts to drift.",
        "consequence": "The staff is aligned in theory, but the room hears too many terms before enough reps.",
        "effects": {"scout_clarity": 0, "room_load": 2, "execution_confidence": 0},
        "hook": "Week 10 scrim starts with too many review terms in the comms.",
    },
    "reps_translated": {
        "headline": "The roster reps translate the lesson.",
        "consequence": "The block turns the fallout message into visible execution work instead of another meeting.",
        "effects": {"scout_clarity": 0, "room_load": 1, "execution_confidence": 2},
        "hook": "Week 10 scrim checks whether execution turns into map pressure.",
    },
    "reps_burned": {
        "headline": "The reps cost more room energy than they return.",
        "consequence": "The players get reps, but the unresolved message makes the block feel heavier than it should.",
        "effects": {"scout_clarity": -1, "room_load": 2, "execution_confidence": 1},
        "hook": "Week 10 scrim opens with fatigue and lower trust.",
    },
}

_SCRIM_OUTCOME_COPY: dict[Week10ScrimOutcome, dict[str, object]] = {
    "read_validated": {
        "headline": "The counter-read survives contact.",
        "consequence": "The scrim gives the staff enough live signal to carry the opponent read into match planning.",
        "match_plan_pressure": "counter_read_primary",
        "effects": {"synergy": 2, "stress": 0, "clarity": 2},
        "hook": "Week 10 match planning can build the first map script around the validated read.",
    },
    "read_exposed": {
        "headline": "The counter-read looks too narrow.",
        "consequence": "The opponent pattern appears in spots, but the scrim punishes the staff for treating it as the whole plan.",
        "match_plan_pressure": "counter_read_secondary",
        "effects": {"synergy": -1, "stress": 2, "clarity": -1},
        "hook": "Week 10 match planning must keep the read as a check, not the spine of the plan.",
    },
    "execution_translated": {
        "headline": "The prep turns into repeatable calls.",
        "consequence": "The room plays the block at match speed without losing the Week 10 lesson.",
        "match_plan_pressure": "execution_primary",
        "effects": {"synergy": 2, "stress": 1, "clarity": 1},
        "hook": "Week 10 match planning can ask for a higher-tempo first half.",
    },
    "execution_frayed": {
        "headline": "The execution test frays at speed.",
        "consequence": "The idea is visible, but missed timings and overloaded comms make the plan feel fragile.",
        "match_plan_pressure": "execution_guardrail",
        "effects": {"synergy": -1, "stress": 2, "clarity": 0},
        "hook": "Week 10 match planning needs guardrails before it asks for tempo.",
    },
    "comms_stabilized": {
        "headline": "The room leaves with cleaner calls.",
        "consequence": "The scrim lowers the noise around the prep effect and gives the staff a clearer shared language.",
        "match_plan_pressure": "room_stability_primary",
        "effects": {"synergy": 1, "stress": -2, "clarity": 1},
        "hook": "Week 10 match planning can lean on stability even if the tactical edge stays modest.",
    },
    "comms_turtled": {
        "headline": "The room gets safer but less ambitious.",
        "consequence": "The comms are cleaner, but the block protects comfort instead of generating a sharper match read.",
        "match_plan_pressure": "room_stability_secondary",
        "effects": {"synergy": 0, "stress": -1, "clarity": -1},
        "hook": "Week 10 match planning must decide whether safety is enough.",
    },
}


def _pressure_prompt(result: Week9MatchResultLock) -> str:
    if result.outcome_id in {"room_held", "room_cracked"}:
        return "Week 10 opens with the room as the first constraint."
    if result.outcome_id in {"prep_converted", "prep_stalled"}:
        return "Week 10 opens with the staff process under review."
    return "Week 10 opens with the read and counter-call under public pressure."


def _recommended_choice(result: Week9MatchResultLock) -> Week10FalloutChoice:
    if result.outcome_id in {"room_held", "room_cracked"}:
        return "steady_room"
    if result.result_tier == "win":
        return "raise_standards"
    return "adapt_system"


def week10_fallout_plan(result: Week9MatchResultLock) -> Week10FalloutPlan:
    """Build the deterministic Week-10 fallout prompt from a Week-9 result."""
    return Week10FalloutPlan(
        source_branch=result.source_branch,
        setup_branch=result.setup_branch,
        chosen_focus=result.chosen_focus,
        week9_outcome_id=result.outcome_id,
        week9_result_tier=result.result_tier,
        week9_scoreline=result.scoreline,
        week9_headline=result.headline,
        week9_recap=result.recap,
        week9_player_read=result.player_read,
        selected_week9_plan=result.selected_plan,
        week9_problem_id=result.week9_problem_id,
        pressure_prompt=_pressure_prompt(result),
        recommended_choice=_recommended_choice(result),
        options=_FALLOUT_OPTIONS,
    )


def _fallout_outcome(result: Week9MatchResultLock, choice: Week10FalloutChoice) -> Week10FalloutOutcome:
    if choice == "steady_room":
        if result.outcome_id in {"room_held", "room_cracked"} or result.result_tier == "loss":
            return "room_recentered"
        return "room_overmanaged"
    if choice == "raise_standards":
        if result.result_tier == "win":
            return "standards_locked"
        return "standards_overfit"
    if result.outcome_id in {"prep_converted", "prep_stalled", "read_punished", "counter_overreached"}:
        return "system_adjusted"
    return "system_blurred"


def resolve_week10_fallout(
    result: Week9MatchResultLock,
    plan: Week10FalloutPlan,
    selected_choice: str,
) -> Week10FalloutLock:
    """Resolve one Week-10 fallout response into a deterministic artifact."""
    if selected_choice not in WEEK10_FALLOUT_CHOICES:
        raise ValueError("selected_choice must be steady_room, raise_standards, or adapt_system")
    if result.outcome_id != plan.week9_outcome_id:
        raise ValueError("week10 fallout plan does not match Week-9 result outcome")
    choice: Week10FalloutChoice = selected_choice  # type: ignore[assignment]
    selected = next(option for option in plan.options if option.value == choice)
    outcome = _fallout_outcome(result, choice)
    copy = _OUTCOME_COPY[outcome]
    return Week10FalloutLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week9_outcome_id=plan.week9_outcome_id,
        week9_result_tier=plan.week9_result_tier,
        week9_scoreline=plan.week9_scoreline,
        week9_headline=plan.week9_headline,
        week9_recap=plan.week9_recap,
        week9_player_read=plan.week9_player_read,
        selected_week9_plan=plan.selected_week9_plan,
        week9_problem_id=plan.week9_problem_id,
        pressure_prompt=plan.pressure_prompt,
        available_choices=WEEK10_FALLOUT_CHOICES,
        recommended_choice=plan.recommended_choice,
        selected_choice=choice,
        choice_label=selected.label,
        followed_recommendation=choice == plan.recommended_choice,
        outcome_id=outcome,
        fallout_headline=str(copy["headline"]),
        consequence=str(copy["consequence"]),
        carry_forward_tag=str(copy["tag"]),
        visible_constraints=tuple(str(item) for item in copy["constraints"]),  # type: ignore[index]
        result_basis=(
            f"week9:{plan.week9_outcome_id}",
            f"tier:{plan.week9_result_tier}",
            f"choice:{choice}",
            f"recommended:{plan.recommended_choice}",
        ),
        next_hook=f"Week 10 prep can start from {outcome}.",
    )


def week10_fallout_from_json(text: str) -> Week10FalloutLock:
    """Parse a written ``week10_fallout.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week10_fallout JSON is malformed") from exc
    fallout = data.get("week10_fallout") if isinstance(data, dict) else None
    if not isinstance(fallout, dict):
        raise ValueError("week10_fallout JSON must contain a week10_fallout object")
    week9_outcome = fallout.get("week9_outcome_id")
    if week9_outcome not in WEEK9_MATCH_OUTCOMES:
        raise ValueError("week10_fallout week9_outcome_id must list a Week-9 outcome")
    result_tier = fallout.get("week9_result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week10_fallout week9_result_tier must be win or loss")
    selected = fallout.get("selected_choice")
    if selected not in WEEK10_FALLOUT_CHOICES:
        raise ValueError("week10_fallout selected_choice must list a Week-10 fallout choice")
    recommended = fallout.get("recommended_choice")
    if recommended not in WEEK10_FALLOUT_CHOICES:
        raise ValueError("week10_fallout recommended_choice must list a Week-10 fallout choice")
    outcome = fallout.get("outcome_id")
    if outcome not in WEEK10_FALLOUT_OUTCOMES:
        raise ValueError("week10_fallout outcome_id must list a Week-10 fallout outcome")
    available = fallout.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK10_FALLOUT_CHOICES for choice in available):
        raise ValueError("week10_fallout available_choices must list Week-10 fallout choices")
    constraints = fallout.get("visible_constraints")
    if not isinstance(constraints, list):
        raise ValueError("week10_fallout JSON must include visible_constraints")
    basis = fallout.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week10_fallout JSON must include result_basis")
    if fallout.get("next_artifact") != WEEK10_PREP_FILENAME:
        raise ValueError("week10_fallout next_artifact must be week10_prep.json")
    return Week10FalloutLock(
        source_branch=str(fallout.get("source_branch", "")),
        setup_branch=str(fallout.get("setup_branch", "")),
        chosen_focus=str(fallout.get("chosen_focus", "")),
        week9_outcome_id=week9_outcome,
        week9_result_tier=result_tier,
        week9_scoreline=str(fallout.get("week9_scoreline", "")),
        week9_headline=str(fallout.get("week9_headline", "")),
        week9_recap=str(fallout.get("week9_recap", "")),
        week9_player_read=str(fallout.get("week9_player_read", "")),
        selected_week9_plan=str(fallout.get("selected_week9_plan", "")),
        week9_problem_id=str(fallout.get("week9_problem_id", "")),
        pressure_prompt=str(fallout.get("pressure_prompt", "")),
        available_choices=tuple(available),  # type: ignore[arg-type]
        recommended_choice=recommended,
        selected_choice=selected,
        choice_label=str(fallout.get("choice_label", "")),
        followed_recommendation=bool(fallout.get("followed_recommendation", selected == recommended)),
        outcome_id=outcome,
        fallout_headline=str(fallout.get("fallout_headline", "")),
        consequence=str(fallout.get("consequence", "")),
        carry_forward_tag=str(fallout.get("carry_forward_tag", "")),
        visible_constraints=tuple(str(item) for item in constraints),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(fallout.get("next_hook", "")),
    )


def render_week10_fallout_json(lock: Week10FalloutLock) -> str:
    """Canonical JSON export for a locked Week-10 fallout response."""
    payload = {
        "week10_fallout": {
            "artifact_type": "week10_fallout",
            "schema_version": 1,
            "source_artifacts": {
                "week9_match_result": "week9_match_result.json",
            },
            "week": 10,
            "route": "/week10/fallout",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week9_outcome_id": lock.week9_outcome_id,
            "week9_result_tier": lock.week9_result_tier,
            "week9_scoreline": lock.week9_scoreline,
            "week9_headline": lock.week9_headline,
            "week9_recap": lock.week9_recap,
            "week9_player_read": lock.week9_player_read,
            "selected_week9_plan": lock.selected_week9_plan,
            "week9_problem_id": lock.week9_problem_id,
            "pressure_prompt": lock.pressure_prompt,
            "available_choices": list(lock.available_choices),
            "recommended_choice": lock.recommended_choice,
            "selected_choice": lock.selected_choice,
            "choice_label": lock.choice_label,
            "followed_recommendation": lock.followed_recommendation,
            "outcome_id": lock.outcome_id,
            "fallout_headline": lock.fallout_headline,
            "consequence": lock.consequence,
            "carry_forward_tag": lock.carry_forward_tag,
            "visible_constraints": list(lock.visible_constraints),
            "result_basis": list(lock.result_basis),
            "next_hook": lock.next_hook,
            "stops_before": "week10_prep",
            "next_artifact": WEEK10_PREP_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _recommended_prep(fallout: Week10FalloutLock) -> Week10PrepChoice:
    if fallout.outcome_id == "system_adjusted":
        return "scout_counter"
    if fallout.outcome_id in {"room_overmanaged", "standards_overfit", "system_blurred"}:
        return "staff_review"
    return "roster_reps"


def _advisor_confidence(fallout: Week10FalloutLock, recommendation: Week10PrepChoice) -> str:
    if fallout.followed_recommendation and recommendation in {"scout_counter", "roster_reps"}:
        return "high"
    if fallout.outcome_id in {"room_overmanaged", "standards_overfit", "system_blurred"}:
        return "medium"
    return "medium"


def _advisor_summary(fallout: Week10FalloutLock, recommendation: Week10PrepChoice) -> str:
    if recommendation == "scout_counter":
        return "The desk sees a real read to carry, but only if the next block keeps it testable."
    if recommendation == "staff_review":
        return "The desk wants one shared language pass before more pressure turns into noise."
    if fallout.outcome_id == "standards_locked":
        return "The desk thinks the raised standard is ready for player reps."
    return "The desk reads the room as stable enough to convert fallout into execution."


def _risk_flags(fallout: Week10FalloutLock) -> tuple[str, ...]:
    flags: list[str] = []
    if fallout.outcome_id in {"room_overmanaged", "standards_overfit", "system_blurred"}:
        flags.extend(["process_noise", "message_watch"])
    if fallout.outcome_id in {"standards_locked", "standards_overfit"}:
        flags.append("overfit_watch")
    if fallout.outcome_id in {"room_recentered", "room_overmanaged"}:
        flags.append("room_energy")
    if fallout.outcome_id == "system_adjusted" or "read_carried" in fallout.visible_constraints:
        flags.append("counter_signal")
    return tuple(dict.fromkeys(flags or ["baseline_watch"]))


def _pressure_meters(fallout: Week10FalloutLock) -> tuple[tuple[str, int, str], ...]:
    room_load = 62
    if fallout.outcome_id in {"room_overmanaged", "standards_overfit", "system_blurred"}:
        room_load = 78
    elif fallout.outcome_id in {"room_recentered", "system_adjusted"}:
        room_load = 48

    prep_clarity = 52
    if fallout.outcome_id in {"standards_locked", "system_adjusted"}:
        prep_clarity = 76
    elif fallout.outcome_id in {"room_overmanaged", "system_blurred"}:
        prep_clarity = 44

    sponsor_noise = 55
    if fallout.week9_result_tier == "loss":
        sponsor_noise = 74
    elif fallout.outcome_id == "standards_locked":
        sponsor_noise = 38

    return (
        ("room_load", room_load, "watch" if room_load >= 70 else "stable"),
        ("prep_clarity", prep_clarity, "stable" if prep_clarity >= 60 else "watch"),
        ("sponsor_noise", sponsor_noise, "danger" if sponsor_noise >= 70 else "watch"),
    )


def _advisor_packet(fallout: Week10FalloutLock) -> Week10AdvisorPacket:
    recommendation = _recommended_prep(fallout)
    source_facts = (
        f"fallout:{fallout.outcome_id}",
        f"tag:{fallout.carry_forward_tag}",
        *(f"constraint:{constraint}" for constraint in fallout.visible_constraints[:2]),
    )
    return Week10AdvisorPacket(
        advisor_id="analyst_desk_v1",
        recommended_prep=recommendation,
        confidence=_advisor_confidence(fallout, recommendation),
        summary=_advisor_summary(fallout, recommendation),
        source_facts=source_facts,
        risk_flags=_risk_flags(fallout),
    )


def week10_prep_plan(fallout: Week10FalloutLock) -> Week10PrepPlan:
    """Build the deterministic Week-10 analyst desk from a fallout artifact."""
    return Week10PrepPlan(
        source_branch=fallout.source_branch,
        setup_branch=fallout.setup_branch,
        chosen_focus=fallout.chosen_focus,
        week9_outcome_id=fallout.week9_outcome_id,
        week9_result_tier=fallout.week9_result_tier,
        week9_scoreline=fallout.week9_scoreline,
        fallout_outcome_id=fallout.outcome_id,
        fallout_headline=fallout.fallout_headline,
        fallout_consequence=fallout.consequence,
        carry_forward_tag=fallout.carry_forward_tag,
        visible_constraints=fallout.visible_constraints,
        advisor_packet=_advisor_packet(fallout),
        pressure_meters=_pressure_meters(fallout),
        options=_PREP_OPTIONS,
    )


def _prep_outcome(fallout: Week10FalloutLock, selected_choice: Week10PrepChoice) -> Week10PrepOutcome:
    if selected_choice == "scout_counter":
        if fallout.outcome_id == "system_adjusted" or "read_carried" in fallout.visible_constraints:
            return "counter_read_ready"
        return "counter_read_overfit"
    if selected_choice == "staff_review":
        if fallout.outcome_id in {"room_overmanaged", "standards_overfit", "system_blurred", "room_recentered"}:
            return "review_loop_locked"
        return "review_loop_drift"
    if fallout.outcome_id in {"room_recentered", "standards_locked"} or "repeatability" in fallout.visible_constraints:
        return "reps_translated"
    return "reps_burned"


def resolve_week10_prep(
    fallout: Week10FalloutLock,
    plan: Week10PrepPlan,
    selected_choice: str,
) -> Week10PrepLock:
    """Resolve one analyst-desk prep allocation into a deterministic artifact."""
    if selected_choice not in WEEK10_PREP_CHOICES:
        raise ValueError("selected_choice must be scout_counter, staff_review, or roster_reps")
    if fallout.outcome_id != plan.fallout_outcome_id:
        raise ValueError("week10 prep plan does not match Week-10 fallout outcome")
    choice: Week10PrepChoice = selected_choice  # type: ignore[assignment]
    selected = next(option for option in plan.options if option.value == choice)
    outcome = _prep_outcome(fallout, choice)
    copy = _PREP_OUTCOME_COPY[outcome]
    effects = copy["effects"]
    if not isinstance(effects, dict):
        raise ValueError("week10 prep outcome effects are malformed")
    return Week10PrepLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week9_outcome_id=plan.week9_outcome_id,
        week9_result_tier=plan.week9_result_tier,
        week9_scoreline=plan.week9_scoreline,
        fallout_outcome_id=plan.fallout_outcome_id,
        fallout_headline=plan.fallout_headline,
        fallout_consequence=plan.fallout_consequence,
        carry_forward_tag=plan.carry_forward_tag,
        visible_constraints=plan.visible_constraints,
        advisor_packet=plan.advisor_packet,
        pressure_meters=plan.pressure_meters,
        available_choices=WEEK10_PREP_CHOICES,
        recommended_prep=plan.advisor_packet.recommended_prep,
        selected_choice=choice,
        choice_label=selected.label,
        followed_recommendation=choice == plan.advisor_packet.recommended_prep,
        prep_blocks_available=1,
        prep_blocks_spent=1,
        lane=selected.lane,
        outcome_id=outcome,
        prep_headline=str(copy["headline"]),
        consequence=str(copy["consequence"]),
        scout_clarity=int(effects["scout_clarity"]),
        room_load=int(effects["room_load"]),
        execution_confidence=int(effects["execution_confidence"]),
        result_basis=(
            f"fallout:{plan.fallout_outcome_id}",
            f"choice:{choice}",
            f"recommended:{plan.advisor_packet.recommended_prep}",
            f"tag:{plan.carry_forward_tag}",
        ),
        next_hook=str(copy["hook"]),
    )


def week10_prep_from_json(text: str) -> Week10PrepLock:
    """Parse a written ``week10_prep.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week10_prep JSON is malformed") from exc
    prep = data.get("week10_prep") if isinstance(data, dict) else None
    if not isinstance(prep, dict):
        raise ValueError("week10_prep JSON must contain a week10_prep object")
    week9_outcome = prep.get("week9_outcome_id")
    if week9_outcome not in WEEK9_MATCH_OUTCOMES:
        raise ValueError("week10_prep week9_outcome_id must list a Week-9 outcome")
    result_tier = prep.get("week9_result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week10_prep week9_result_tier must be win or loss")
    fallout_outcome = prep.get("fallout_outcome_id")
    if fallout_outcome not in WEEK10_FALLOUT_OUTCOMES:
        raise ValueError("week10_prep fallout_outcome_id must list a Week-10 fallout outcome")
    selected = prep.get("selected_choice")
    if selected not in WEEK10_PREP_CHOICES:
        raise ValueError("week10_prep selected_choice must list a Week-10 prep choice")
    recommended = prep.get("recommended_prep")
    if recommended not in WEEK10_PREP_CHOICES:
        raise ValueError("week10_prep recommended_prep must list a Week-10 prep choice")
    outcome = prep.get("outcome_id")
    if outcome not in WEEK10_PREP_OUTCOMES:
        raise ValueError("week10_prep outcome_id must list a Week-10 prep outcome")
    available = prep.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK10_PREP_CHOICES for choice in available):
        raise ValueError("week10_prep available_choices must list Week-10 prep choices")
    constraints = prep.get("visible_constraints")
    if not isinstance(constraints, list):
        raise ValueError("week10_prep JSON must include visible_constraints")
    advisor = prep.get("advisor_packet")
    if not isinstance(advisor, dict):
        raise ValueError("week10_prep JSON must include advisor_packet")
    source_facts = advisor.get("source_facts")
    risk_flags = advisor.get("risk_flags")
    if not isinstance(source_facts, list) or not isinstance(risk_flags, list):
        raise ValueError("week10_prep advisor_packet must include source_facts and risk_flags")
    meters = prep.get("pressure_meters")
    if not isinstance(meters, list):
        raise ValueError("week10_prep JSON must include pressure_meters")
    resource = prep.get("resource")
    if not isinstance(resource, dict):
        raise ValueError("week10_prep JSON must include resource")
    effects = prep.get("prep_effect")
    if not isinstance(effects, dict):
        raise ValueError("week10_prep JSON must include prep_effect")
    basis = prep.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week10_prep JSON must include result_basis")
    if prep.get("next_artifact") != WEEK10_SCRIM_FILENAME:
        raise ValueError("week10_prep next_artifact must be week10_scrim.json")
    return Week10PrepLock(
        source_branch=str(prep.get("source_branch", "")),
        setup_branch=str(prep.get("setup_branch", "")),
        chosen_focus=str(prep.get("chosen_focus", "")),
        week9_outcome_id=week9_outcome,
        week9_result_tier=result_tier,
        week9_scoreline=str(prep.get("week9_scoreline", "")),
        fallout_outcome_id=fallout_outcome,
        fallout_headline=str(prep.get("fallout_headline", "")),
        fallout_consequence=str(prep.get("fallout_consequence", "")),
        carry_forward_tag=str(prep.get("carry_forward_tag", "")),
        visible_constraints=tuple(str(item) for item in constraints),
        advisor_packet=Week10AdvisorPacket(
            advisor_id=str(advisor.get("advisor_id", "")),
            recommended_prep=recommended,
            confidence=str(advisor.get("confidence", "")),
            summary=str(advisor.get("summary", "")),
            source_facts=tuple(str(item) for item in source_facts),
            risk_flags=tuple(str(item) for item in risk_flags),
        ),
        pressure_meters=tuple(
            (str(item.get("id", "")), int(item.get("value", 0)), str(item.get("tone", "")))
            for item in meters
            if isinstance(item, dict)
        ),
        available_choices=tuple(available),  # type: ignore[arg-type]
        recommended_prep=recommended,
        selected_choice=selected,
        choice_label=str(prep.get("choice_label", "")),
        followed_recommendation=bool(prep.get("followed_recommendation", selected == recommended)),
        prep_blocks_available=int(resource.get("prep_blocks_available", 0)),
        prep_blocks_spent=int(resource.get("prep_blocks_spent", 0)),
        lane=str(resource.get("lane", "")),
        outcome_id=outcome,
        prep_headline=str(prep.get("prep_headline", "")),
        consequence=str(prep.get("consequence", "")),
        scout_clarity=int(effects.get("scout_clarity", 0)),
        room_load=int(effects.get("room_load", 0)),
        execution_confidence=int(effects.get("execution_confidence", 0)),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(prep.get("next_hook", "")),
    )


def render_week10_prep_json(lock: Week10PrepLock) -> str:
    """Canonical JSON export for a locked Week-10 analyst desk prep block."""
    payload = {
        "week10_prep": {
            "artifact_type": "week10_prep",
            "schema_version": 1,
            "source_artifacts": {
                "week10_fallout": WEEK10_FALLOUT_FILENAME,
            },
            "week": 10,
            "route": "/week10/prep",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week9_outcome_id": lock.week9_outcome_id,
            "week9_result_tier": lock.week9_result_tier,
            "week9_scoreline": lock.week9_scoreline,
            "fallout_outcome_id": lock.fallout_outcome_id,
            "fallout_headline": lock.fallout_headline,
            "fallout_consequence": lock.fallout_consequence,
            "carry_forward_tag": lock.carry_forward_tag,
            "visible_constraints": list(lock.visible_constraints),
            "advisor_packet": {
                "advisor_id": lock.advisor_packet.advisor_id,
                "recommended_prep": lock.advisor_packet.recommended_prep,
                "confidence": lock.advisor_packet.confidence,
                "summary": lock.advisor_packet.summary,
                "source_facts": list(lock.advisor_packet.source_facts),
                "risk_flags": list(lock.advisor_packet.risk_flags),
            },
            "pressure_meters": [
                {"id": meter_id, "value": value, "tone": tone}
                for meter_id, value, tone in lock.pressure_meters
            ],
            "available_choices": list(lock.available_choices),
            "recommended_prep": lock.recommended_prep,
            "selected_choice": lock.selected_choice,
            "choice_label": lock.choice_label,
            "followed_recommendation": lock.followed_recommendation,
            "resource": {
                "prep_blocks_available": lock.prep_blocks_available,
                "prep_blocks_spent": lock.prep_blocks_spent,
                "lane": lock.lane,
            },
            "outcome_id": lock.outcome_id,
            "prep_headline": lock.prep_headline,
            "consequence": lock.consequence,
            "prep_effect": {
                "scout_clarity": lock.scout_clarity,
                "room_load": lock.room_load,
                "execution_confidence": lock.execution_confidence,
            },
            "result_basis": list(lock.result_basis),
            "next_hook": lock.next_hook,
            "stops_before": "week10_scrim",
            "next_artifact": WEEK10_SCRIM_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _clamp_meter(value: int) -> int:
    return max(5, min(95, value))


def _signal_tone(value: int) -> str:
    if value >= 68:
        return "stable"
    if value <= 38:
        return "danger"
    return "watch"


def _load_tone(value: int) -> str:
    if value >= 72:
        return "danger"
    if value >= 56:
        return "watch"
    return "stable"


def _scrim_readiness_meters(prep: Week10PrepLock) -> tuple[tuple[str, int, str], ...]:
    scout = _clamp_meter(50 + prep.scout_clarity * 15)
    load = _clamp_meter(45 + prep.room_load * 14)
    execution = _clamp_meter(50 + prep.execution_confidence * 15)
    return (
        ("scout_clarity", scout, _signal_tone(scout)),
        ("room_load", load, _load_tone(load)),
        ("execution_confidence", execution, _signal_tone(execution)),
    )


def _scrim_lane_states(prep: Week10PrepLock) -> tuple[tuple[str, int, str], ...]:
    top = _clamp_meter(48 + prep.scout_clarity * 13 - prep.room_load * 4)
    mid = _clamp_meter(50 + prep.execution_confidence * 12 - prep.room_load * 5)
    bot = _clamp_meter(52 + prep.scout_clarity * 6 + prep.execution_confidence * 6 - prep.room_load * 6)
    return (
        ("top", top, _signal_tone(top)),
        ("mid", mid, _signal_tone(mid)),
        ("bot", bot, _signal_tone(bot)),
    )


def _recommended_scrim(prep: Week10PrepLock) -> Week10ScrimChoice:
    if prep.room_load >= 2 or prep.outcome_id in {"counter_read_overfit", "reps_burned"}:
        return "stabilize_comms"
    if prep.scout_clarity >= 2 or prep.outcome_id == "counter_read_ready":
        return "validate_read"
    if prep.execution_confidence >= 2 or prep.outcome_id == "reps_translated":
        return "stress_execution"
    return "stabilize_comms"


def _scrim_recommendation_reason(prep: Week10PrepLock, recommendation: Week10ScrimChoice) -> str:
    if recommendation == "validate_read":
        return "Scout clarity is the strongest signal, so the scrim should prove the counter-read is not overfit."
    if recommendation == "stress_execution":
        return "Execution confidence is the strongest signal, so the scrim should test whether reps hold at speed."
    if prep.room_load >= 2:
        return "Room load is the loudest risk, so the scrim should lower comm noise before match planning."
    return "The prep created language before a hard edge, so the scrim should stabilize the shared call sheet."


def week10_scrim_plan(prep: Week10PrepLock) -> Week10ScrimPlan:
    """Build the deterministic Week-10 scrim lab from a prep artifact."""
    recommendation = _recommended_scrim(prep)
    return Week10ScrimPlan(
        source_branch=prep.source_branch,
        setup_branch=prep.setup_branch,
        chosen_focus=prep.chosen_focus,
        week9_outcome_id=prep.week9_outcome_id,
        week9_result_tier=prep.week9_result_tier,
        week9_scoreline=prep.week9_scoreline,
        fallout_outcome_id=prep.fallout_outcome_id,
        prep_outcome_id=prep.outcome_id,
        selected_prep=prep.selected_choice,
        prep_lane=prep.lane,
        prep_headline=prep.prep_headline,
        carry_forward_tag=prep.carry_forward_tag,
        visible_constraints=prep.visible_constraints,
        scout_clarity=prep.scout_clarity,
        room_load=prep.room_load,
        execution_confidence=prep.execution_confidence,
        recommended_scrim=recommendation,
        recommendation_reason=_scrim_recommendation_reason(prep, recommendation),
        readiness_meters=_scrim_readiness_meters(prep),
        lane_states=_scrim_lane_states(prep),
        protocols=_SCRIM_PROTOCOLS,
    )


def _scrim_outcome(prep: Week10PrepLock, selected_scrim: Week10ScrimChoice) -> Week10ScrimOutcome:
    if selected_scrim == "validate_read":
        if prep.scout_clarity >= 2 or (prep.scout_clarity >= 1 and prep.room_load <= 0):
            return "read_validated"
        return "read_exposed"
    if selected_scrim == "stress_execution":
        if prep.execution_confidence >= 2 and prep.room_load <= 1:
            return "execution_translated"
        return "execution_frayed"
    if prep.room_load >= 1 or prep.outcome_id in {"review_loop_locked", "review_loop_drift"}:
        return "comms_stabilized"
    return "comms_turtled"


def resolve_week10_scrim(
    prep: Week10PrepLock,
    plan: Week10ScrimPlan,
    selected_scrim: str,
) -> Week10ScrimLock:
    """Resolve one scrim protocol into a deterministic Week-10 scrim artifact."""
    if selected_scrim not in WEEK10_SCRIM_CHOICES:
        raise ValueError("selected_scrim must be validate_read, stress_execution, or stabilize_comms")
    if prep.outcome_id != plan.prep_outcome_id:
        raise ValueError("week10 scrim plan does not match Week-10 prep outcome")
    choice: Week10ScrimChoice = selected_scrim  # type: ignore[assignment]
    selected = next(protocol for protocol in plan.protocols if protocol.value == choice)
    outcome = _scrim_outcome(prep, choice)
    copy = _SCRIM_OUTCOME_COPY[outcome]
    effects = copy["effects"]
    if not isinstance(effects, dict):
        raise ValueError("week10 scrim outcome effects are malformed")
    return Week10ScrimLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week9_outcome_id=plan.week9_outcome_id,
        week9_result_tier=plan.week9_result_tier,
        week9_scoreline=plan.week9_scoreline,
        fallout_outcome_id=plan.fallout_outcome_id,
        prep_outcome_id=plan.prep_outcome_id,
        selected_prep=plan.selected_prep,
        prep_lane=plan.prep_lane,
        prep_headline=plan.prep_headline,
        carry_forward_tag=plan.carry_forward_tag,
        visible_constraints=plan.visible_constraints,
        scout_clarity=plan.scout_clarity,
        room_load=plan.room_load,
        execution_confidence=plan.execution_confidence,
        readiness_meters=plan.readiness_meters,
        lane_states=plan.lane_states,
        available_choices=WEEK10_SCRIM_CHOICES,
        recommended_scrim=plan.recommended_scrim,
        selected_scrim=choice,
        choice_label=selected.label,
        followed_recommendation=choice == plan.recommended_scrim,
        outcome_id=outcome,
        scrim_headline=str(copy["headline"]),
        consequence=str(copy["consequence"]),
        match_plan_pressure=str(copy["match_plan_pressure"]),
        synergy_delta=int(effects["synergy"]),
        stress_delta=int(effects["stress"]),
        clarity_delta=int(effects["clarity"]),
        result_basis=(
            f"prep:{plan.prep_outcome_id}",
            f"protocol:{choice}",
            f"recommended:{plan.recommended_scrim}",
            f"effects:scout={plan.scout_clarity},room={plan.room_load},execution={plan.execution_confidence}",
        ),
        next_hook=str(copy["hook"]),
    )


def week10_scrim_from_json(text: str) -> Week10ScrimLock:
    """Parse a written ``week10_scrim.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week10_scrim JSON is malformed") from exc
    scrim = data.get("week10_scrim") if isinstance(data, dict) else None
    if not isinstance(scrim, dict):
        raise ValueError("week10_scrim JSON must contain a week10_scrim object")
    week9_outcome = scrim.get("week9_outcome_id")
    if week9_outcome not in WEEK9_MATCH_OUTCOMES:
        raise ValueError("week10_scrim week9_outcome_id must list a Week-9 outcome")
    result_tier = scrim.get("week9_result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week10_scrim week9_result_tier must be win or loss")
    fallout_outcome = scrim.get("fallout_outcome_id")
    if fallout_outcome not in WEEK10_FALLOUT_OUTCOMES:
        raise ValueError("week10_scrim fallout_outcome_id must list a Week-10 fallout outcome")
    prep_outcome = scrim.get("prep_outcome_id")
    if prep_outcome not in WEEK10_PREP_OUTCOMES:
        raise ValueError("week10_scrim prep_outcome_id must list a Week-10 prep outcome")
    selected_prep = scrim.get("selected_prep")
    if selected_prep not in WEEK10_PREP_CHOICES:
        raise ValueError("week10_scrim selected_prep must list a Week-10 prep choice")
    selected = scrim.get("selected_scrim")
    if selected not in WEEK10_SCRIM_CHOICES:
        raise ValueError("week10_scrim selected_scrim must list a Week-10 scrim choice")
    recommended = scrim.get("recommended_scrim")
    if recommended not in WEEK10_SCRIM_CHOICES:
        raise ValueError("week10_scrim recommended_scrim must list a Week-10 scrim choice")
    outcome = scrim.get("outcome_id")
    if outcome not in WEEK10_SCRIM_OUTCOMES:
        raise ValueError("week10_scrim outcome_id must list a Week-10 scrim outcome")
    available = scrim.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK10_SCRIM_CHOICES for choice in available):
        raise ValueError("week10_scrim available_choices must list Week-10 scrim choices")
    constraints = scrim.get("visible_constraints")
    if not isinstance(constraints, list):
        raise ValueError("week10_scrim JSON must include visible_constraints")
    prep_effect = scrim.get("prep_effect")
    if not isinstance(prep_effect, dict):
        raise ValueError("week10_scrim JSON must include prep_effect")
    meters = scrim.get("readiness_meters")
    if not isinstance(meters, list):
        raise ValueError("week10_scrim JSON must include readiness_meters")
    lanes = scrim.get("lane_states")
    if not isinstance(lanes, list):
        raise ValueError("week10_scrim JSON must include lane_states")
    scrim_effect = scrim.get("scrim_effect")
    if not isinstance(scrim_effect, dict):
        raise ValueError("week10_scrim JSON must include scrim_effect")
    basis = scrim.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week10_scrim JSON must include result_basis")
    if scrim.get("next_artifact") != WEEK10_MATCH_PLAN_FILENAME:
        raise ValueError("week10_scrim next_artifact must be week10_match_plan.json")
    return Week10ScrimLock(
        source_branch=str(scrim.get("source_branch", "")),
        setup_branch=str(scrim.get("setup_branch", "")),
        chosen_focus=str(scrim.get("chosen_focus", "")),
        week9_outcome_id=week9_outcome,
        week9_result_tier=result_tier,
        week9_scoreline=str(scrim.get("week9_scoreline", "")),
        fallout_outcome_id=fallout_outcome,
        prep_outcome_id=prep_outcome,
        selected_prep=selected_prep,
        prep_lane=str(scrim.get("prep_lane", "")),
        prep_headline=str(scrim.get("prep_headline", "")),
        carry_forward_tag=str(scrim.get("carry_forward_tag", "")),
        visible_constraints=tuple(str(item) for item in constraints),
        scout_clarity=int(prep_effect.get("scout_clarity", 0)),
        room_load=int(prep_effect.get("room_load", 0)),
        execution_confidence=int(prep_effect.get("execution_confidence", 0)),
        readiness_meters=tuple(
            (str(item.get("id", "")), int(item.get("value", 0)), str(item.get("tone", "")))
            for item in meters
            if isinstance(item, dict)
        ),
        lane_states=tuple(
            (str(item.get("id", "")), int(item.get("pressure", 0)), str(item.get("tone", "")))
            for item in lanes
            if isinstance(item, dict)
        ),
        available_choices=tuple(available),  # type: ignore[arg-type]
        recommended_scrim=recommended,
        selected_scrim=selected,
        choice_label=str(scrim.get("choice_label", "")),
        followed_recommendation=bool(scrim.get("followed_recommendation", selected == recommended)),
        outcome_id=outcome,
        scrim_headline=str(scrim.get("scrim_headline", "")),
        consequence=str(scrim.get("consequence", "")),
        match_plan_pressure=str(scrim.get("match_plan_pressure", "")),
        synergy_delta=int(scrim_effect.get("synergy", 0)),
        stress_delta=int(scrim_effect.get("stress", 0)),
        clarity_delta=int(scrim_effect.get("clarity", 0)),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(scrim.get("next_hook", "")),
    )


def render_week10_scrim_json(lock: Week10ScrimLock) -> str:
    """Canonical JSON export for a locked Week-10 scrim protocol."""
    payload = {
        "week10_scrim": {
            "artifact_type": "week10_scrim",
            "schema_version": 1,
            "source_artifacts": {
                "week10_prep": WEEK10_PREP_FILENAME,
            },
            "week": 10,
            "route": "/week10/scrim",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week9_outcome_id": lock.week9_outcome_id,
            "week9_result_tier": lock.week9_result_tier,
            "week9_scoreline": lock.week9_scoreline,
            "fallout_outcome_id": lock.fallout_outcome_id,
            "prep_outcome_id": lock.prep_outcome_id,
            "selected_prep": lock.selected_prep,
            "prep_lane": lock.prep_lane,
            "prep_headline": lock.prep_headline,
            "carry_forward_tag": lock.carry_forward_tag,
            "visible_constraints": list(lock.visible_constraints),
            "prep_effect": {
                "scout_clarity": lock.scout_clarity,
                "room_load": lock.room_load,
                "execution_confidence": lock.execution_confidence,
            },
            "readiness_meters": [
                {"id": meter_id, "value": value, "tone": tone}
                for meter_id, value, tone in lock.readiness_meters
            ],
            "lane_states": [
                {"id": lane_id, "pressure": pressure, "tone": tone}
                for lane_id, pressure, tone in lock.lane_states
            ],
            "available_choices": list(lock.available_choices),
            "recommended_scrim": lock.recommended_scrim,
            "selected_scrim": lock.selected_scrim,
            "choice_label": lock.choice_label,
            "followed_recommendation": lock.followed_recommendation,
            "outcome_id": lock.outcome_id,
            "scrim_headline": lock.scrim_headline,
            "consequence": lock.consequence,
            "match_plan_pressure": lock.match_plan_pressure,
            "scrim_effect": {
                "synergy": lock.synergy_delta,
                "stress": lock.stress_delta,
                "clarity": lock.clarity_delta,
            },
            "result_basis": list(lock.result_basis),
            "next_hook": lock.next_hook,
            "stops_before": "week10_match_plan",
            "next_artifact": WEEK10_MATCH_PLAN_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _recommended_match_plan(scrim: Week10ScrimLock) -> tuple[Week10MatchPlanChoice, str, str]:
    if scrim.stress_delta >= 2:
        return (
            "week10_plan_protect_pressure",
            "stress_pressure",
            "The scrim exposes enough stress that the plan must protect the loudest pressure point.",
        )
    if scrim.match_plan_pressure in {"counter_read_primary", "execution_primary"}:
        return (
            "week10_plan_press_advantage",
            "primary_advantage",
            "The scrim creates a primary advantage that can be pressed before the opponent resets.",
        )
    if scrim.match_plan_pressure.endswith("_secondary") or scrim.match_plan_pressure.endswith("_guardrail"):
        return (
            "week10_plan_trade_map",
            "mixed_pressure",
            "The scrim leaves a useful but unstable read, so the plan should trade map instead of colliding.",
        )
    if scrim.match_plan_pressure.startswith("room_stability"):
        return (
            "week10_plan_protect_pressure",
            "room_stability",
            "The scrim says the match plan should make the room's stability the protected pressure point.",
        )
    return (
        "week10_plan_protect_pressure",
        "conservative_tiebreak",
        "No sharp edge dominates, so the conservative tie-break protects pressure first.",
    )


def _week10_match_risk(scrim: Week10ScrimLock, recommended_plan: Week10MatchPlanChoice) -> str:
    if scrim.stress_delta >= 2:
        return "high"
    if recommended_plan == "week10_plan_protect_pressure" and scrim.stress_delta <= -1:
        return "low"
    if scrim.room_load >= 2 and recommended_plan != "week10_plan_protect_pressure":
        return "high"
    return "medium"


def week10_match_plan_preview(scrim: Week10ScrimLock) -> Week10MatchPlanPreview:
    """Build the deterministic Week-10 match-plan preview from the scrim artifact."""
    recommended, basis, reason = _recommended_match_plan(scrim)
    return Week10MatchPlanPreview(
        source_branch=scrim.source_branch,
        setup_branch=scrim.setup_branch,
        chosen_focus=scrim.chosen_focus,
        week9_outcome_id=scrim.week9_outcome_id,
        week9_result_tier=scrim.week9_result_tier,
        week9_scoreline=scrim.week9_scoreline,
        fallout_outcome_id=scrim.fallout_outcome_id,
        prep_outcome_id=scrim.prep_outcome_id,
        scrim_outcome_id=scrim.outcome_id,
        selected_prep=scrim.selected_prep,
        selected_scrim=scrim.selected_scrim,
        prep_lane=scrim.prep_lane,
        prep_headline=scrim.prep_headline,
        scrim_headline=scrim.scrim_headline,
        match_plan_pressure=scrim.match_plan_pressure,
        scout_clarity=scrim.scout_clarity,
        room_load=scrim.room_load,
        execution_confidence=scrim.execution_confidence,
        synergy_delta=scrim.synergy_delta,
        stress_delta=scrim.stress_delta,
        clarity_delta=scrim.clarity_delta,
        lane_states=scrim.lane_states,
        recommendation_basis=basis,
        recommended_plan=recommended,
        recommendation_reason=reason,
        match_risk=_week10_match_risk(scrim, recommended),
        options=_MATCH_PLAN_OPTIONS,
    )


def resolve_week10_match_plan(
    preview: Week10MatchPlanPreview,
    selected_plan: str,
) -> Week10MatchPlanLock:
    """Resolve one Week-10 match plan into a deterministic artifact."""
    if selected_plan not in WEEK10_MATCH_PLAN_CHOICES:
        raise ValueError(
            "selected_plan must be week10_plan_protect_pressure, "
            "week10_plan_trade_map, or week10_plan_press_advantage"
        )
    plan: Week10MatchPlanChoice = selected_plan  # type: ignore[assignment]
    selected = next(option for option in preview.options if option.value == plan)

    if plan == "week10_plan_protect_pressure":
        risk_taken = "the plan may lower its ceiling to keep the exposed point from collapsing"
        thing_to_watch = "whether the protected pressure point stays proactive after first contact"
        extra_constraints = ("protect_exposed_pressure", "do_not_turtle_after_contact")
    elif plan == "week10_plan_trade_map":
        risk_taken = "trading map can concede the direct advantage if rotations arrive late"
        thing_to_watch = "whether the first rotation creates cross-pressure instead of avoidance"
        extra_constraints = ("trade_volatile_point", "create_cross_pressure")
    else:
        risk_taken = "pressing the advantage can be punished if the scrim read was too optimistic"
        thing_to_watch = "whether the advantage lands before the opponent's first punish window"
        extra_constraints = ("press_clearest_advantage", "avoid_second_layer_overreach")

    constraints = (
        selected.result_constraint,
        f"prep:{preview.prep_outcome_id}",
        f"scrim:{preview.scrim_outcome_id}",
        f"pressure:{preview.match_plan_pressure}",
        *extra_constraints,
    )
    return Week10MatchPlanLock(
        source_branch=preview.source_branch,
        setup_branch=preview.setup_branch,
        chosen_focus=preview.chosen_focus,
        week9_outcome_id=preview.week9_outcome_id,
        week9_result_tier=preview.week9_result_tier,
        week9_scoreline=preview.week9_scoreline,
        fallout_outcome_id=preview.fallout_outcome_id,
        prep_outcome_id=preview.prep_outcome_id,
        scrim_outcome_id=preview.scrim_outcome_id,
        selected_prep=preview.selected_prep,
        selected_scrim=preview.selected_scrim,
        prep_lane=preview.prep_lane,
        prep_headline=preview.prep_headline,
        scrim_headline=preview.scrim_headline,
        match_plan_pressure=preview.match_plan_pressure,
        scout_clarity=preview.scout_clarity,
        room_load=preview.room_load,
        execution_confidence=preview.execution_confidence,
        synergy_delta=preview.synergy_delta,
        stress_delta=preview.stress_delta,
        clarity_delta=preview.clarity_delta,
        lane_states=preview.lane_states,
        recommendation_basis=preview.recommendation_basis,
        recommended_plan=preview.recommended_plan,
        available_choices=WEEK10_MATCH_PLAN_CHOICES,
        selected_plan=plan,
        plan_outcome_id=f"week10_match_plan_{plan.removeprefix('week10_plan_')}",
        plan_label=selected.label,
        followed_recommendation=plan == preview.recommended_plan,
        commitment=selected.commitment,
        risk_taken=risk_taken,
        thing_to_watch=thing_to_watch,
        match_risk=preview.match_risk,
        result_constraints=constraints,
        recommendation_reason=preview.recommendation_reason,
        next_hook=(
            f"Week 10 result can test {selected.commitment} against "
            f"{preview.match_plan_pressure}."
        ),
    )


def week10_match_plan_from_json(text: str) -> Week10MatchPlanLock:
    """Parse a written ``week10_match_plan.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week10_match_plan JSON is malformed") from exc
    match_plan = data.get("week10_match_plan") if isinstance(data, dict) else None
    if not isinstance(match_plan, dict):
        raise ValueError("week10_match_plan JSON must contain a week10_match_plan object")
    week9_outcome = match_plan.get("week9_outcome_id")
    if week9_outcome not in WEEK9_MATCH_OUTCOMES:
        raise ValueError("week10_match_plan week9_outcome_id must list a Week-9 outcome")
    result_tier = match_plan.get("week9_result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week10_match_plan week9_result_tier must be win or loss")
    fallout_outcome = match_plan.get("fallout_outcome_id")
    if fallout_outcome not in WEEK10_FALLOUT_OUTCOMES:
        raise ValueError("week10_match_plan fallout_outcome_id must list a Week-10 fallout outcome")
    prep_outcome = match_plan.get("prep_outcome_id")
    if prep_outcome not in WEEK10_PREP_OUTCOMES:
        raise ValueError("week10_match_plan prep_outcome_id must list a Week-10 prep outcome")
    scrim_outcome = match_plan.get("scrim_outcome_id")
    if scrim_outcome not in WEEK10_SCRIM_OUTCOMES:
        raise ValueError("week10_match_plan scrim_outcome_id must list a Week-10 scrim outcome")
    selected_prep = match_plan.get("selected_prep")
    if selected_prep not in WEEK10_PREP_CHOICES:
        raise ValueError("week10_match_plan selected_prep must list a Week-10 prep choice")
    selected_scrim = match_plan.get("selected_scrim")
    if selected_scrim not in WEEK10_SCRIM_CHOICES:
        raise ValueError("week10_match_plan selected_scrim must list a Week-10 scrim choice")
    selected = match_plan.get("selected_plan")
    if selected not in WEEK10_MATCH_PLAN_CHOICES:
        raise ValueError("week10_match_plan selected_plan must list a Week-10 match plan")
    recommended = match_plan.get("recommended_plan")
    if recommended not in WEEK10_MATCH_PLAN_CHOICES:
        raise ValueError("week10_match_plan recommended_plan must list a Week-10 match plan")
    available = match_plan.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK10_MATCH_PLAN_CHOICES for choice in available):
        raise ValueError("week10_match_plan available_choices must list Week-10 match plans")
    prep_effect = match_plan.get("prep_effect")
    if not isinstance(prep_effect, dict):
        raise ValueError("week10_match_plan JSON must include prep_effect")
    scrim_effect = match_plan.get("scrim_effect")
    if not isinstance(scrim_effect, dict):
        raise ValueError("week10_match_plan JSON must include scrim_effect")
    lanes = match_plan.get("lane_states")
    if not isinstance(lanes, list):
        raise ValueError("week10_match_plan JSON must include lane_states")
    constraints = match_plan.get("result_constraints")
    if not isinstance(constraints, list):
        raise ValueError("week10_match_plan JSON must include result_constraints")
    if match_plan.get("next_artifact") != WEEK10_MATCH_RESULT_FILENAME:
        raise ValueError("week10_match_plan next_artifact must be week10_match_result.json")
    plan_lock = match_plan.get("plan_lock")
    result_lock = match_plan.get("result_lock")
    if not isinstance(plan_lock, dict):
        raise ValueError("week10_match_plan JSON must include plan_lock")
    if not isinstance(result_lock, dict):
        raise ValueError("week10_match_plan JSON must include result_lock")
    return Week10MatchPlanLock(
        source_branch=str(match_plan.get("source_branch", "")),
        setup_branch=str(match_plan.get("setup_branch", "")),
        chosen_focus=str(match_plan.get("chosen_focus", "")),
        week9_outcome_id=week9_outcome,
        week9_result_tier=result_tier,
        week9_scoreline=str(match_plan.get("week9_scoreline", "")),
        fallout_outcome_id=fallout_outcome,
        prep_outcome_id=prep_outcome,
        scrim_outcome_id=scrim_outcome,
        selected_prep=selected_prep,
        selected_scrim=selected_scrim,
        prep_lane=str(match_plan.get("prep_lane", "")),
        prep_headline=str(match_plan.get("prep_headline", "")),
        scrim_headline=str(match_plan.get("scrim_headline", "")),
        match_plan_pressure=str(match_plan.get("match_plan_pressure", "")),
        scout_clarity=int(prep_effect.get("scout_clarity", 0)),
        room_load=int(prep_effect.get("room_load", 0)),
        execution_confidence=int(prep_effect.get("execution_confidence", 0)),
        synergy_delta=int(scrim_effect.get("synergy", 0)),
        stress_delta=int(scrim_effect.get("stress", 0)),
        clarity_delta=int(scrim_effect.get("clarity", 0)),
        lane_states=tuple(
            (str(item.get("id", "")), int(item.get("pressure", 0)), str(item.get("tone", "")))
            for item in lanes
            if isinstance(item, dict)
        ),
        recommendation_basis=str(match_plan.get("recommendation_basis", "")),
        recommended_plan=recommended,
        available_choices=tuple(available),  # type: ignore[arg-type]
        selected_plan=selected,
        plan_outcome_id=str(match_plan.get("plan_outcome_id", "")),
        plan_label=str(match_plan.get("plan_label", "")),
        followed_recommendation=bool(match_plan.get("followed_recommendation", selected == recommended)),
        commitment=str(match_plan.get("commitment", "")),
        risk_taken=str(match_plan.get("risk_taken", "")),
        thing_to_watch=str(match_plan.get("thing_to_watch", "")),
        match_risk=str(match_plan.get("match_risk", "")),
        result_constraints=tuple(str(item) for item in constraints),
        recommendation_reason=str(match_plan.get("recommendation_reason", "")),
        next_hook=str(match_plan.get("next_hook", "")),
    )


def render_week10_match_plan_json(lock: Week10MatchPlanLock) -> str:
    """Canonical JSON export for a locked Week-10 match plan."""
    payload = {
        "week10_match_plan": {
            "artifact_type": "week10_match_plan",
            "schema_version": 1,
            "source_artifacts": {
                "week10_scrim": WEEK10_SCRIM_FILENAME,
            },
            "week": 10,
            "route": "/week10/match",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week9_outcome_id": lock.week9_outcome_id,
            "week9_result_tier": lock.week9_result_tier,
            "week9_scoreline": lock.week9_scoreline,
            "fallout_outcome_id": lock.fallout_outcome_id,
            "prep_outcome_id": lock.prep_outcome_id,
            "scrim_outcome_id": lock.scrim_outcome_id,
            "selected_prep": lock.selected_prep,
            "selected_scrim": lock.selected_scrim,
            "prep_lane": lock.prep_lane,
            "prep_headline": lock.prep_headline,
            "scrim_headline": lock.scrim_headline,
            "match_plan_pressure": lock.match_plan_pressure,
            "prep_effect": {
                "scout_clarity": lock.scout_clarity,
                "room_load": lock.room_load,
                "execution_confidence": lock.execution_confidence,
            },
            "scrim_effect": {
                "synergy": lock.synergy_delta,
                "stress": lock.stress_delta,
                "clarity": lock.clarity_delta,
            },
            "lane_states": [
                {"id": lane_id, "pressure": pressure, "tone": tone}
                for lane_id, pressure, tone in lock.lane_states
            ],
            "recommendation_basis": lock.recommendation_basis,
            "recommended_plan": lock.recommended_plan,
            "recommended_plan_id": lock.recommended_plan,
            "available_choices": list(lock.available_choices),
            "choice_order": list(lock.available_choices),
            "selected_plan": lock.selected_plan,
            "selected_plan_id": lock.selected_plan,
            "plan_outcome_id": lock.plan_outcome_id,
            "plan_label": lock.plan_label,
            "followed_recommendation": lock.followed_recommendation,
            "commitment": lock.commitment,
            "risk_taken": lock.risk_taken,
            "thing_to_watch": lock.thing_to_watch,
            "match_risk": lock.match_risk,
            "result_constraints": list(lock.result_constraints),
            "recommendation_reason": lock.recommendation_reason,
            "plan_lock": {
                "status": "locked",
                "selected_at_route": "/week10/match",
                "cannot_change_after_write": True,
            },
            "result_lock": {
                "status": "not_resolved",
                "reason": "week10_match_plan_only",
                "next_artifact": WEEK10_MATCH_RESULT_FILENAME,
            },
            "match_plan_commitment": {
                "commitment": lock.commitment,
                "risk_taken": lock.risk_taken,
                "thing_to_watch": lock.thing_to_watch,
            },
            "next_hook": lock.next_hook,
            "stops_before": "week10_match_result",
            "next_artifact": WEEK10_MATCH_RESULT_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_WEEK10_RESULT_COPY: dict[Week10MatchOutcome, dict[str, str]] = {
    "pressure_held": {
        "headline": "The protected pressure point holds.",
        "recap": (
            "The match never became clean, but the first pressure point stayed live. "
            "The team lost less tempo than the opponent expected and closed through steadier second contact."
        ),
        "player_read": "Protecting pressure worked because the plan turned stress into a boundary instead of a panic button.",
    },
    "pressure_broke": {
        "headline": "The protected point becomes a bunker.",
        "recap": (
            "The plan protected the right danger, but the team stopped contesting around it. "
            "By the time the second adjustment arrived, the map had already narrowed."
        ),
        "player_read": "The protection call was understandable, but it made the room play not to lose the pressure point.",
    },
    "map_trade_paid": {
        "headline": "The map trade creates the winning cross-pressure.",
        "recap": (
            "The team conceded the noisy contact and kept the rotation timing clean. "
            "The opponent won space, but Overcast bought the map back on its own terms."
        ),
        "player_read": "Trading map worked because the lane-state read created pressure somewhere else before the opponent reset.",
    },
    "map_trade_late": {
        "headline": "The trade arrives one beat late.",
        "recap": (
            "The idea was correct on paper, but the first rotation landed after the opponent had already cashed the open lane. "
            "The late map trade gave the team decisions without leverage."
        ),
        "player_read": "The trade plan needed cleaner timing than the prep and scrim chain had proved.",
    },
    "advantage_converted": {
        "headline": "The first-half advantage becomes the match.",
        "recap": (
            "The team pressed the clearest edge before the opponent could add a second layer. "
            "The result looked earned rather than lucky because the same prep signal kept reappearing."
        ),
        "player_read": "Pressing the advantage worked because execution, synergy, and the scrim read all pointed in the same direction.",
    },
    "advantage_punished": {
        "headline": "The advantage gets punished before it compounds.",
        "recap": (
            "The opening call found the right door, but the second layer was slower than the opponent's punish. "
            "The plan asked for a sharper conversion than the current room could support."
        ),
        "player_read": "The team had an edge, but the commitment spent it before the room could stabilize the follow-up.",
    },
}

_WEEK10_VISIBLE_EFFECTS: dict[Week10MatchOutcome, tuple[Week10VisibleEffect, ...]] = {
    "pressure_held": (
        Week10VisibleEffect("pressure_boundary_held", "Pressure boundary held", "positive"),
        Week10VisibleEffect("tempo_ceiling_watch", "Tempo ceiling watch", "watch"),
        Week10VisibleEffect("room_trust_bank", "Room trust banked", "positive"),
    ),
    "pressure_broke": (
        Week10VisibleEffect("pressure_became_bunker", "Pressure became bunker", "negative"),
        Week10VisibleEffect("proactivity_lost", "Proactivity lost", "negative"),
        Week10VisibleEffect("review_simplify", "Simplify review", "watch"),
    ),
    "map_trade_paid": (
        Week10VisibleEffect("cross_pressure_created", "Cross-pressure created", "positive"),
        Week10VisibleEffect("rotation_timing_validated", "Rotation timing validated", "positive"),
        Week10VisibleEffect("direct_edge_declined", "Direct edge declined", "watch"),
    ),
    "map_trade_late": (
        Week10VisibleEffect("rotation_late", "Rotation late", "negative"),
        Week10VisibleEffect("lane_leverage_lost", "Lane leverage lost", "negative"),
        Week10VisibleEffect("map_trade_reteach", "Map trade reteach", "watch"),
    ),
    "advantage_converted": (
        Week10VisibleEffect("advantage_landed", "Advantage landed", "positive"),
        Week10VisibleEffect("prep_signal_validated", "Prep signal validated", "positive"),
        Week10VisibleEffect("punish_window_closed", "Punish window closed", "positive"),
    ),
    "advantage_punished": (
        Week10VisibleEffect("punish_window_open", "Punish window open", "negative"),
        Week10VisibleEffect("second_layer_slow", "Second layer slow", "negative"),
        Week10VisibleEffect("edge_not_repeatable", "Edge not repeatable", "watch"),
    ),
}


def _week10_lane_spread(plan: Week10MatchPlanLock) -> int:
    pressures = [pressure for _lane_id, pressure, _tone in plan.lane_states]
    if not pressures:
        return 0
    return max(pressures) - min(pressures)


def _week10_result_score(plan: Week10MatchPlanLock) -> int:
    score = 2 if plan.followed_recommendation else -1
    score += plan.scout_clarity + plan.execution_confidence + plan.synergy_delta + plan.clarity_delta
    score -= max(plan.room_load, 0) + max(plan.stress_delta, 0)

    if plan.match_risk == "low":
        score += 1
    elif plan.match_risk == "high":
        score -= 1

    if plan.selected_plan == "week10_plan_protect_pressure":
        if plan.stress_delta >= 1:
            score += 1
        if plan.match_risk != "high":
            score += 1
        if plan.match_plan_pressure.startswith("room_stability"):
            score += 1
    elif plan.selected_plan == "week10_plan_trade_map":
        score += 1 if _week10_lane_spread(plan) >= 18 else -1
        score += plan.clarity_delta
        if plan.match_risk == "high":
            score -= 1
    else:
        if plan.match_plan_pressure in {"counter_read_primary", "execution_primary"}:
            score += 1
        score += plan.execution_confidence + plan.synergy_delta
        if plan.stress_delta >= 2:
            score -= 2
    return score


def _week10_match_succeeded(plan: Week10MatchPlanLock, score: int) -> bool:
    if plan.selected_plan == "week10_plan_protect_pressure":
        return score >= 3 and not (plan.match_risk == "high" and plan.stress_delta >= 2)
    if plan.selected_plan == "week10_plan_trade_map":
        return score >= 4 and _week10_lane_spread(plan) >= 12
    return score >= 5 and plan.stress_delta < 2


def _week10_outcome_id(plan: Week10MatchPlanLock, score: int) -> Week10MatchOutcome:
    succeeded = _week10_match_succeeded(plan, score)
    if plan.selected_plan == "week10_plan_protect_pressure":
        return "pressure_held" if succeeded else "pressure_broke"
    if plan.selected_plan == "week10_plan_trade_map":
        return "map_trade_paid" if succeeded else "map_trade_late"
    return "advantage_converted" if succeeded else "advantage_punished"


def _week10_scoreline(outcome_id: Week10MatchOutcome, score: int) -> tuple[Week10MatchResultTier, int, int]:
    if outcome_id in {"pressure_held", "map_trade_paid", "advantage_converted"}:
        if outcome_id == "advantage_converted" and score >= 8:
            return "win", 2, 0
        return "win", 2, 1
    if score <= 0 or outcome_id == "advantage_punished":
        return "loss", 0, 2
    return "loss", 1, 2


def _week10_result_grade(score: int) -> str:
    if score >= 8:
        return "clean"
    if score >= 4:
        return "earned"
    if score >= 2:
        return "thin"
    return "punished"


def _week10_result_basis(plan: Week10MatchPlanLock, score: int) -> tuple[str, ...]:
    return (
        f"plan:{plan.selected_plan}",
        f"recommended:{plan.recommended_plan}",
        f"matched:{plan.followed_recommendation}",
        f"prep:{plan.prep_outcome_id}",
        f"scrim:{plan.scrim_outcome_id}",
        f"risk:{plan.match_risk}",
        f"pressure:{plan.match_plan_pressure}",
        f"lane_spread:{_week10_lane_spread(plan)}",
        f"score:{score}",
    )


def resolve_week10_match_result(plan: Week10MatchPlanLock) -> Week10MatchResultLock:
    """Resolve a locked Week-10 match plan into a deterministic result artifact."""
    score = _week10_result_score(plan)
    outcome_id = _week10_outcome_id(plan, score)
    result_tier, team_maps, opponent_maps = _week10_scoreline(outcome_id, score)
    copy = _WEEK10_RESULT_COPY[outcome_id]
    causal_chain = (
        f"Week 9 fallout left the room with {plan.fallout_outcome_id.replace('_', ' ')}.",
        f"Prep signal: {plan.prep_headline}",
        f"Scrim signal: {plan.scrim_headline}",
        f"Match commitment: {plan.commitment.replace('_', ' ')}.",
        f"Watch point: {plan.thing_to_watch}",
    )
    return Week10MatchResultLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week9_outcome_id=plan.week9_outcome_id,
        week9_result_tier=plan.week9_result_tier,
        week9_scoreline=plan.week9_scoreline,
        fallout_outcome_id=plan.fallout_outcome_id,
        prep_outcome_id=plan.prep_outcome_id,
        scrim_outcome_id=plan.scrim_outcome_id,
        selected_prep=plan.selected_prep,
        selected_scrim=plan.selected_scrim,
        selected_plan=plan.selected_plan,
        recommended_plan=plan.recommended_plan,
        matched_recommendation=plan.followed_recommendation,
        commitment=plan.commitment,
        match_risk=plan.match_risk,
        match_plan_pressure=plan.match_plan_pressure,
        outcome_id=outcome_id,
        result_tier=result_tier,
        team_maps=team_maps,
        opponent_maps=opponent_maps,
        scoreline=f"{team_maps}-{opponent_maps}",
        result_score=score,
        result_grade=_week10_result_grade(score),
        headline=copy["headline"],
        recap=copy["recap"],
        player_read=copy["player_read"],
        visible_effects=_WEEK10_VISIBLE_EFFECTS[outcome_id],
        result_basis=_week10_result_basis(plan, score),
        causal_chain=causal_chain,
        next_hook=f"Week 10 post-match review can start from {outcome_id}.",
    )


def week10_match_result_from_json(text: str) -> Week10MatchResultLock:
    """Parse a written ``week10_match_result.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week10_match_result JSON is malformed") from exc
    result = data.get("week10_match_result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise ValueError("week10_match_result JSON must contain a week10_match_result object")
    week9_outcome = result.get("week9_outcome_id")
    if week9_outcome not in WEEK9_MATCH_OUTCOMES:
        raise ValueError("week10_match_result week9_outcome_id must list a Week-9 outcome")
    week9_tier = result.get("week9_result_tier")
    if week9_tier not in ("win", "loss"):
        raise ValueError("week10_match_result week9_result_tier must be win or loss")
    fallout_outcome = result.get("fallout_outcome_id")
    if fallout_outcome not in WEEK10_FALLOUT_OUTCOMES:
        raise ValueError("week10_match_result fallout_outcome_id must list a Week-10 fallout outcome")
    prep_outcome = result.get("prep_outcome_id")
    if prep_outcome not in WEEK10_PREP_OUTCOMES:
        raise ValueError("week10_match_result prep_outcome_id must list a Week-10 prep outcome")
    scrim_outcome = result.get("scrim_outcome_id")
    if scrim_outcome not in WEEK10_SCRIM_OUTCOMES:
        raise ValueError("week10_match_result scrim_outcome_id must list a Week-10 scrim outcome")
    selected_prep = result.get("selected_prep")
    if selected_prep not in WEEK10_PREP_CHOICES:
        raise ValueError("week10_match_result selected_prep must list a Week-10 prep choice")
    selected_scrim = result.get("selected_scrim")
    if selected_scrim not in WEEK10_SCRIM_CHOICES:
        raise ValueError("week10_match_result selected_scrim must list a Week-10 scrim choice")
    selected_plan = result.get("selected_plan")
    if selected_plan not in WEEK10_MATCH_PLAN_CHOICES:
        raise ValueError("week10_match_result selected_plan must list a Week-10 match plan")
    recommended_plan = result.get("recommended_plan")
    if recommended_plan not in WEEK10_MATCH_PLAN_CHOICES:
        raise ValueError("week10_match_result recommended_plan must list a Week-10 match plan")
    outcome_id = result.get("outcome_id")
    if outcome_id not in WEEK10_MATCH_OUTCOMES:
        raise ValueError("week10_match_result outcome_id must list a Week-10 outcome")
    result_tier = result.get("result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week10_match_result result_tier must be win or loss")
    scoreline = result.get("scoreline")
    if not isinstance(scoreline, dict):
        raise ValueError("week10_match_result JSON must include scoreline")
    effects = result.get("visible_effects")
    if not isinstance(effects, list):
        raise ValueError("week10_match_result JSON must include visible_effects")
    basis = result.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week10_match_result JSON must include result_basis")
    causal_chain = result.get("causal_chain")
    if not isinstance(causal_chain, list):
        raise ValueError("week10_match_result JSON must include causal_chain")
    if result.get("next_artifact") is not None:
        raise ValueError("week10_match_result next_artifact must be null")
    return Week10MatchResultLock(
        source_branch=str(result.get("source_branch", "")),
        setup_branch=str(result.get("setup_branch", "")),
        chosen_focus=str(result.get("chosen_focus", "")),
        week9_outcome_id=week9_outcome,
        week9_result_tier=week9_tier,
        week9_scoreline=str(result.get("week9_scoreline", "")),
        fallout_outcome_id=fallout_outcome,
        prep_outcome_id=prep_outcome,
        scrim_outcome_id=scrim_outcome,
        selected_prep=selected_prep,
        selected_scrim=selected_scrim,
        selected_plan=selected_plan,
        recommended_plan=recommended_plan,
        matched_recommendation=bool(result.get("matched_recommendation", selected_plan == recommended_plan)),
        commitment=str(result.get("commitment", "")),
        match_risk=str(result.get("match_risk", "")),
        match_plan_pressure=str(result.get("match_plan_pressure", "")),
        outcome_id=outcome_id,
        result_tier=result_tier,
        team_maps=int(scoreline.get("team_maps", 0)),
        opponent_maps=int(scoreline.get("opponent_maps", 0)),
        scoreline=str(scoreline.get("display", "")),
        result_score=int(result.get("result_score", 0)),
        result_grade=str(result.get("result_grade", "")),
        headline=str(result.get("headline", "")),
        recap=str(result.get("recap", "")),
        player_read=str(result.get("player_read", "")),
        visible_effects=tuple(
            Week10VisibleEffect(
                value=str(effect.get("id", "")),
                label=str(effect.get("label", "")),
                polarity=str(effect.get("polarity", "")),
            )
            for effect in effects
            if isinstance(effect, dict)
        ),
        result_basis=tuple(str(item) for item in basis),
        causal_chain=tuple(str(item) for item in causal_chain),
        next_hook=str(result.get("next_hook", "")),
    )


def render_week10_match_result_json(lock: Week10MatchResultLock) -> str:
    """Canonical JSON export for a resolved Week-10 match result."""
    payload = {
        "week10_match_result": {
            "artifact_type": "week10_match_result",
            "schema_version": 1,
            "source_artifacts": {
                "week10_match_plan": WEEK10_MATCH_PLAN_FILENAME,
            },
            "week": 10,
            "route": "/week10/match/result",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week9_outcome_id": lock.week9_outcome_id,
            "week9_result_tier": lock.week9_result_tier,
            "week9_scoreline": lock.week9_scoreline,
            "fallout_outcome_id": lock.fallout_outcome_id,
            "prep_outcome_id": lock.prep_outcome_id,
            "scrim_outcome_id": lock.scrim_outcome_id,
            "selected_prep": lock.selected_prep,
            "selected_scrim": lock.selected_scrim,
            "selected_plan": lock.selected_plan,
            "recommended_plan": lock.recommended_plan,
            "matched_recommendation": lock.matched_recommendation,
            "commitment": lock.commitment,
            "match_risk": lock.match_risk,
            "match_plan_pressure": lock.match_plan_pressure,
            "outcome_id": lock.outcome_id,
            "result_tier": lock.result_tier,
            "scoreline": {
                "team_maps": lock.team_maps,
                "opponent_maps": lock.opponent_maps,
                "display": lock.scoreline,
            },
            "result_score": lock.result_score,
            "result_grade": lock.result_grade,
            "headline": lock.headline,
            "recap": lock.recap,
            "player_read": lock.player_read,
            "visible_effects": [
                {
                    "id": effect.value,
                    "label": effect.label,
                    "polarity": effect.polarity,
                }
                for effect in lock.visible_effects
            ],
            "result_basis": list(lock.result_basis),
            "causal_chain": list(lock.causal_chain),
            "next_hook": lock.next_hook,
            "stops_before": "week10_post_match_review",
            "next_artifact": None,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
