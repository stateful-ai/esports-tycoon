"""Deterministic Week-11 setup from the Week-10 post-match review artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from esports_tycoon.runner.week10 import (
    WEEK10_POST_MATCH_REVIEW_FILENAME,
    WEEK10_POST_MATCH_REVIEW_OUTCOMES,
    Week10PostMatchReviewLock,
)

Week11SetupChoice = Literal["lean_into_carry", "stress_test_carry", "protect_room"]
Week11SetupOutcome = Literal[
    "edge_activated",
    "edge_overcalled",
    "test_defined",
    "test_scattered",
    "room_stabilized",
    "room_passive",
]
Week11PrepChoice = Literal["build_edge_lane", "scout_countermove", "stabilize_room"]
Week11PrepOutcome = Literal[
    "edge_lane_drilled",
    "edge_lane_forced",
    "countermove_ready",
    "countermove_noisy",
    "room_prepped",
    "room_tentative",
]
Week11ScrimChoice = Literal["repeat_edge", "show_countermove", "steady_first_contact"]
Week11MatchPlanChoice = Literal["trust_the_read", "attack_the_gap", "stabilize_defaults"]
Week11MatchResultTier = Literal["win", "loss"]
Week11ScrimOutcome = Literal[
    "edge_repeated_under_pressure",
    "edge_counter_scouted",
    "edge_tempo_dulled",
    "forced_edge_punished",
    "forced_edge_exposed",
    "forced_edge_depressurized",
    "counter_read_ignored",
    "countermove_confirmed",
    "counter_timing_delayed",
    "noise_hardened_into_call",
    "read_narrowed",
    "read_noise_depressurized",
    "stable_room_underused",
    "room_overloaded_by_scout",
    "first_contact_stabilized",
    "tentative_room_given_task",
    "tentative_room_overloaded",
    "room_stays_tentative",
]
Week11MatchOutcome = Literal[
    "read_trusted",
    "read_overtrusted",
    "gap_attacked",
    "gap_chased",
    "defaults_stabilized",
    "defaults_too_slow",
]

WEEK11_SETUP_FILENAME = "week11_setup.json"
WEEK11_PREP_FILENAME = "week11_prep.json"
WEEK11_SCRIM_FILENAME = "week11_scrim.json"
WEEK11_MATCH_PLAN_FILENAME = "week11_match_plan.json"
WEEK11_MATCH_RESULT_FILENAME = "week11_match_result.json"
WEEK11_SETUP_CHOICES: tuple[Week11SetupChoice, ...] = (
    "lean_into_carry",
    "stress_test_carry",
    "protect_room",
)
WEEK11_SETUP_OUTCOMES: tuple[Week11SetupOutcome, ...] = (
    "edge_activated",
    "edge_overcalled",
    "test_defined",
    "test_scattered",
    "room_stabilized",
    "room_passive",
)
WEEK11_PREP_CHOICES: tuple[Week11PrepChoice, ...] = (
    "build_edge_lane",
    "scout_countermove",
    "stabilize_room",
)
WEEK11_PREP_OUTCOMES: tuple[Week11PrepOutcome, ...] = (
    "edge_lane_drilled",
    "edge_lane_forced",
    "countermove_ready",
    "countermove_noisy",
    "room_prepped",
    "room_tentative",
)
WEEK11_SCRIM_CHOICES: tuple[Week11ScrimChoice, ...] = (
    "repeat_edge",
    "show_countermove",
    "steady_first_contact",
)
WEEK11_MATCH_PLAN_CHOICES: tuple[Week11MatchPlanChoice, ...] = (
    "trust_the_read",
    "attack_the_gap",
    "stabilize_defaults",
)
WEEK11_SCRIM_OUTCOMES: tuple[Week11ScrimOutcome, ...] = (
    "edge_repeated_under_pressure",
    "edge_counter_scouted",
    "edge_tempo_dulled",
    "forced_edge_punished",
    "forced_edge_exposed",
    "forced_edge_depressurized",
    "counter_read_ignored",
    "countermove_confirmed",
    "counter_timing_delayed",
    "noise_hardened_into_call",
    "read_narrowed",
    "read_noise_depressurized",
    "stable_room_underused",
    "room_overloaded_by_scout",
    "first_contact_stabilized",
    "tentative_room_given_task",
    "tentative_room_overloaded",
    "room_stays_tentative",
)
WEEK11_MATCH_OUTCOMES: tuple[Week11MatchOutcome, ...] = (
    "read_trusted",
    "read_overtrusted",
    "gap_attacked",
    "gap_chased",
    "defaults_stabilized",
    "defaults_too_slow",
)


@dataclass(frozen=True)
class Week11SetupOption:
    """One Week-11 opening posture."""

    value: Week11SetupChoice
    label: str
    posture: str
    payoff: str
    risk: str


@dataclass(frozen=True)
class Week11SetupEffect:
    """One visible consequence chip for the Week-11 setup lock."""

    value: str
    label: str
    polarity: str


@dataclass(frozen=True)
class Week11SetupPlan:
    """The read-only Week-11 setup prompt before the opening posture is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    review_outcome_id: str
    review_label: str
    lesson: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    setup_prompt: str
    recommended_setup: Week11SetupChoice
    options: tuple[Week11SetupOption, ...]


@dataclass(frozen=True)
class Week11SetupLock:
    """The deterministic artifact produced by locking the Week-11 setup."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    review_outcome_id: str
    review_label: str
    lesson: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    recommended_setup: Week11SetupChoice
    followed_recommendation: bool
    setup_outcome_id: Week11SetupOutcome
    setup_label: str
    setup_posture: str
    opening_priority: str
    week11_pressure: str
    visible_effects: tuple[Week11SetupEffect, ...]
    result_basis: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week11PrepOption:
    """One Week-11 prep allocation after setup."""

    value: Week11PrepChoice
    label: str
    lane: str
    payoff: str
    risk: str


@dataclass(frozen=True)
class Week11PrepPlan:
    """The read-only Week-11 prep prompt before the prep allocation is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    opening_priority: str
    week11_pressure: str
    visible_effects: tuple[Week11SetupEffect, ...]
    prep_prompt: str
    recommended_prep: Week11PrepChoice
    options: tuple[Week11PrepOption, ...]


@dataclass(frozen=True)
class Week11PrepLock:
    """The deterministic artifact produced by locking the Week-11 prep block."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    week11_pressure: str
    selected_prep: Week11PrepChoice
    recommended_prep: Week11PrepChoice
    followed_recommendation: bool
    prep_outcome_id: Week11PrepOutcome
    prep_label: str
    prep_lane: str
    prep_priority: str
    scrim_seed: str
    visible_effects: tuple[Week11SetupEffect, ...]
    result_basis: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week11ScrimOption:
    """One Week-11 scrim protocol after prep."""

    value: Week11ScrimChoice
    label: str
    lane: str
    payoff: str
    risk: str


@dataclass(frozen=True)
class Week11ScrimPlan:
    """The read-only Week-11 scrim prompt before the protocol is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    week11_pressure: str
    selected_prep: Week11PrepChoice
    recommended_prep: Week11PrepChoice
    prep_outcome_id: Week11PrepOutcome
    prep_label: str
    prep_lane: str
    prep_priority: str
    scrim_seed: str
    visible_effects: tuple[Week11SetupEffect, ...]
    scrim_prompt: str
    recommended_scrim: Week11ScrimChoice
    recommendation_reason: str
    options: tuple[Week11ScrimOption, ...]


@dataclass(frozen=True)
class Week11ScrimLock:
    """The deterministic artifact produced by locking the Week-11 scrim protocol."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    week11_pressure: str
    selected_prep: Week11PrepChoice
    recommended_prep: Week11PrepChoice
    prep_outcome_id: Week11PrepOutcome
    prep_label: str
    prep_lane: str
    prep_priority: str
    scrim_seed: str
    selected_scrim: Week11ScrimChoice
    recommended_scrim: Week11ScrimChoice
    followed_recommendation: bool
    scrim_outcome_id: Week11ScrimOutcome
    scrim_label: str
    scrim_lane: str
    scrim_protocol: str
    analyst_read_id: str
    recommendation_reason: str
    scrim_priority: str
    match_plan_seed: str
    visible_effects: tuple[Week11SetupEffect, ...]
    result_basis: tuple[str, ...]
    next_hook: str


@dataclass(frozen=True)
class Week11MatchPlanOption:
    """One Week-11 match plan available after the scrim protocol."""

    value: Week11MatchPlanChoice
    label: str
    payoff: str
    risk: str
    commitment: str
    result_constraint: str


@dataclass(frozen=True)
class Week11MatchPlanPreview:
    """The read-only Week-11 match-plan preview before the plan is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    week11_pressure: str
    selected_prep: Week11PrepChoice
    recommended_prep: Week11PrepChoice
    prep_outcome_id: Week11PrepOutcome
    prep_lane: str
    selected_scrim: Week11ScrimChoice
    recommended_scrim: Week11ScrimChoice
    scrim_outcome_id: Week11ScrimOutcome
    scrim_protocol: str
    analyst_read_id: str
    match_plan_seed: str
    outcome_class: str
    protocol_signal: str
    analyst_read_class: str
    seed_bucket: int
    seeded_emphasis: str
    scrim_priority: str
    visible_effects: tuple[Week11SetupEffect, ...]
    recommendation_basis: str
    recommended_plan: Week11MatchPlanChoice
    recommendation_reason: str
    match_risk: str
    options: tuple[Week11MatchPlanOption, ...]


@dataclass(frozen=True)
class Week11MatchPlanLock:
    """The deterministic artifact produced by locking the Week-11 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    week11_pressure: str
    selected_prep: Week11PrepChoice
    recommended_prep: Week11PrepChoice
    prep_outcome_id: Week11PrepOutcome
    prep_lane: str
    selected_scrim: Week11ScrimChoice
    recommended_scrim: Week11ScrimChoice
    scrim_outcome_id: Week11ScrimOutcome
    scrim_protocol: str
    analyst_read_id: str
    match_plan_seed: str
    outcome_class: str
    protocol_signal: str
    analyst_read_class: str
    seed_bucket: int
    seeded_emphasis: str
    scrim_priority: str
    visible_effects: tuple[Week11SetupEffect, ...]
    recommendation_basis: str
    recommended_plan: Week11MatchPlanChoice
    available_choices: tuple[Week11MatchPlanChoice, ...]
    selected_plan: Week11MatchPlanChoice
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
class Week11MatchResultLock:
    """The deterministic Week-11 result produced from the locked match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: str
    week10_outcome_id: str
    week10_result_tier: str
    week10_result_grade: str
    carry_forward_tag: str
    carry_forward_type: str
    carry_forward_polarity: str
    selected_setup: Week11SetupChoice
    setup_outcome_id: Week11SetupOutcome
    week11_pressure: str
    selected_prep: Week11PrepChoice
    recommended_prep: Week11PrepChoice
    prep_outcome_id: Week11PrepOutcome
    prep_lane: str
    selected_scrim: Week11ScrimChoice
    recommended_scrim: Week11ScrimChoice
    scrim_outcome_id: Week11ScrimOutcome
    scrim_protocol: str
    analyst_read_id: str
    match_plan_seed: str
    outcome_class: str
    protocol_signal: str
    analyst_read_class: str
    seeded_emphasis: str
    selected_plan: Week11MatchPlanChoice
    recommended_plan: Week11MatchPlanChoice
    matched_recommendation: bool
    commitment: str
    match_risk: str
    outcome_id: Week11MatchOutcome
    result_tier: Week11MatchResultTier
    team_maps: int
    opponent_maps: int
    scoreline: str
    result_score: int
    result_grade: str
    headline: str
    recap: str
    player_read: str
    visible_effects: tuple[Week11SetupEffect, ...]
    result_basis: tuple[str, ...]
    causal_chain: tuple[str, ...]
    next_hook: str


_WEEK11_SETUP_OPTIONS: tuple[Week11SetupOption, ...] = (
    Week11SetupOption(
        value="lean_into_carry",
        label="Lean into carry-forward",
        posture="commit the lesson",
        payoff="Build the first Week 11 block around the carry-forward tag.",
        risk="Can overcall a lesson before the next opponent tests it.",
    ),
    Week11SetupOption(
        value="stress_test_carry",
        label="Stress-test the carry-forward",
        posture="prove the lesson",
        payoff="Turn the carry-forward into the first Week 11 validation target.",
        risk="Can scatter the room if every lesson becomes a test.",
    ),
    Week11SetupOption(
        value="protect_room",
        label="Protect the room",
        posture="stabilize before pressure",
        payoff="Open Week 11 by controlling emotional load around the lesson.",
        risk="Can make the room passive if the lesson needed action.",
    ),
)

_WEEK11_SETUP_COPY: dict[Week11SetupOutcome, dict[str, str]] = {
    "edge_activated": {
        "opening_priority": "Make the carry-forward tag the first Week 11 practice lane.",
        "week11_pressure": "edge_lane",
        "effect_id": "edge_lane_activated",
        "effect_label": "Edge lane activated",
        "polarity": "positive",
        "next_hook": "Week 11 prep can start from an activated edge lane.",
    },
    "edge_overcalled": {
        "opening_priority": "Treat the carry-forward as a hypothesis, not an identity.",
        "week11_pressure": "overcalled_edge",
        "effect_id": "edge_overcall_watch",
        "effect_label": "Edge overcall watch",
        "polarity": "watch",
        "next_hook": "Week 11 prep should test whether the edge survives contact.",
    },
    "test_defined": {
        "opening_priority": "Define one validation test for the carry-forward before adding new work.",
        "week11_pressure": "validation_lane",
        "effect_id": "validation_lane_defined",
        "effect_label": "Validation lane defined",
        "polarity": "positive",
        "next_hook": "Week 11 prep can start from a single validation lane.",
    },
    "test_scattered": {
        "opening_priority": "Reduce the setup to one test before the room splits its attention.",
        "week11_pressure": "scattered_validation",
        "effect_id": "validation_scatter_watch",
        "effect_label": "Validation scatter watch",
        "polarity": "watch",
        "next_hook": "Week 11 prep should narrow the validation work before scrims.",
    },
    "room_stabilized": {
        "opening_priority": "Protect the room around the carry-forward and make the next demand explicit.",
        "week11_pressure": "stable_room",
        "effect_id": "room_stabilized",
        "effect_label": "Room stabilized",
        "polarity": "positive",
        "next_hook": "Week 11 prep can start from a stabilized room constraint.",
    },
    "room_passive": {
        "opening_priority": "Reintroduce action before the room turns stability into avoidance.",
        "week11_pressure": "passive_room",
        "effect_id": "room_passivity_watch",
        "effect_label": "Room passivity watch",
        "polarity": "watch",
        "next_hook": "Week 11 prep should turn stability back into a concrete task.",
    },
}


def _week11_setup_prompt(review: Week10PostMatchReviewLock) -> str:
    if review.carry_forward_type == "advantage":
        return "Week 11 starts by deciding how hard to trust the advantage."
    if review.carry_forward_type == "constraint":
        return "Week 11 starts by deciding how much room load the constraint can carry."
    return "Week 11 starts by deciding how to test the watch item before it becomes identity."


def _recommended_week11_setup(review: Week10PostMatchReviewLock) -> Week11SetupChoice:
    if review.carry_forward_type == "advantage" and review.carry_forward_polarity == "positive":
        return "lean_into_carry"
    if review.carry_forward_type == "watch":
        return "stress_test_carry"
    return "protect_room"


def week11_setup_plan(review: Week10PostMatchReviewLock) -> Week11SetupPlan:
    """Build the read-only Week-11 setup prompt from the Week-10 review."""
    return Week11SetupPlan(
        source_branch=review.source_branch,
        setup_branch=review.setup_branch,
        chosen_focus=review.chosen_focus,
        week10_outcome_id=review.week10_outcome_id,
        week10_result_tier=review.result_tier,
        week10_result_grade=review.result_grade,
        review_outcome_id=review.review_outcome_id,
        review_label=review.review_label,
        lesson=review.lesson,
        carry_forward_tag=review.carry_forward_tag,
        carry_forward_type=review.carry_forward_type,
        carry_forward_polarity=review.carry_forward_polarity,
        setup_prompt=_week11_setup_prompt(review),
        recommended_setup=_recommended_week11_setup(review),
        options=_WEEK11_SETUP_OPTIONS,
    )


def _week11_setup_outcome(
    plan: Week11SetupPlan,
    selected_setup: Week11SetupChoice,
) -> Week11SetupOutcome:
    if selected_setup == "lean_into_carry":
        if plan.carry_forward_type == "advantage" and plan.carry_forward_polarity == "positive":
            return "edge_activated"
        return "edge_overcalled"
    if selected_setup == "stress_test_carry":
        if plan.carry_forward_type in {"watch", "constraint"}:
            return "test_defined"
        return "test_scattered"
    if plan.carry_forward_type == "constraint" or plan.carry_forward_polarity == "negative":
        return "room_stabilized"
    return "room_passive"


def _week11_setup_option(selected_setup: Week11SetupChoice) -> Week11SetupOption:
    return next(option for option in _WEEK11_SETUP_OPTIONS if option.value == selected_setup)


def resolve_week11_setup(plan: Week11SetupPlan, selected_setup: str) -> Week11SetupLock:
    """Resolve the selected Week-11 opening posture into a setup artifact."""
    if selected_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("selected_setup must list a Week-11 setup choice")
    selected = selected_setup
    outcome_id = _week11_setup_outcome(plan, selected)
    option = _week11_setup_option(selected)
    copy = _WEEK11_SETUP_COPY[outcome_id]
    carry_effect = Week11SetupEffect(
        value=plan.carry_forward_tag,
        label=plan.carry_forward_tag.replace("_", " ").title(),
        polarity=plan.carry_forward_polarity,
    )
    setup_effect = Week11SetupEffect(
        value=copy["effect_id"],
        label=copy["effect_label"],
        polarity=copy["polarity"],
    )
    return Week11SetupLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week10_outcome_id=plan.week10_outcome_id,
        week10_result_tier=plan.week10_result_tier,
        week10_result_grade=plan.week10_result_grade,
        review_outcome_id=plan.review_outcome_id,
        review_label=plan.review_label,
        lesson=plan.lesson,
        carry_forward_tag=plan.carry_forward_tag,
        carry_forward_type=plan.carry_forward_type,
        carry_forward_polarity=plan.carry_forward_polarity,
        selected_setup=selected,
        recommended_setup=plan.recommended_setup,
        followed_recommendation=selected == plan.recommended_setup,
        setup_outcome_id=outcome_id,
        setup_label=option.label,
        setup_posture=option.posture,
        opening_priority=copy["opening_priority"],
        week11_pressure=copy["week11_pressure"],
        visible_effects=(setup_effect, carry_effect),
        result_basis=(
            f"carry_forward:{plan.carry_forward_tag}",
            f"type:{plan.carry_forward_type}",
            f"polarity:{plan.carry_forward_polarity}",
            f"selected_setup:{selected}",
            f"recommended_setup:{plan.recommended_setup}",
            f"setup_outcome:{outcome_id}",
        ),
        next_hook=copy["next_hook"],
    )


def week11_setup_from_json(text: str) -> Week11SetupLock:
    """Parse a written ``week11_setup.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_setup JSON is malformed") from exc
    setup = data.get("week11_setup") if isinstance(data, dict) else None
    if not isinstance(setup, dict):
        raise ValueError("week11_setup JSON must contain a week11_setup object")
    review_outcome = setup.get("review_outcome_id")
    if review_outcome not in WEEK10_POST_MATCH_REVIEW_OUTCOMES:
        raise ValueError("week11_setup review_outcome_id must list a Week-10 review outcome")
    selected_setup = setup.get("selected_setup")
    if selected_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("week11_setup selected_setup must list a Week-11 setup choice")
    recommended_setup = setup.get("recommended_setup")
    if recommended_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("week11_setup recommended_setup must list a Week-11 setup choice")
    setup_outcome = setup.get("setup_outcome_id")
    if setup_outcome not in WEEK11_SETUP_OUTCOMES:
        raise ValueError("week11_setup setup_outcome_id must list a Week-11 setup outcome")
    effects = setup.get("visible_effects")
    if not isinstance(effects, list):
        raise ValueError("week11_setup JSON must include visible_effects")
    basis = setup.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week11_setup JSON must include result_basis")
    if setup.get("next_artifact") not in (None, WEEK11_PREP_FILENAME):
        raise ValueError("week11_setup next_artifact must be null or week11_prep.json")
    return Week11SetupLock(
        source_branch=str(setup.get("source_branch", "")),
        setup_branch=str(setup.get("setup_branch", "")),
        chosen_focus=str(setup.get("chosen_focus", "")),
        week10_outcome_id=str(setup.get("week10_outcome_id", "")),
        week10_result_tier=str(setup.get("week10_result_tier", "")),
        week10_result_grade=str(setup.get("week10_result_grade", "")),
        review_outcome_id=review_outcome,
        review_label=str(setup.get("review_label", "")),
        lesson=str(setup.get("lesson", "")),
        carry_forward_tag=str(setup.get("carry_forward_tag", "")),
        carry_forward_type=str(setup.get("carry_forward_type", "")),
        carry_forward_polarity=str(setup.get("carry_forward_polarity", "")),
        selected_setup=selected_setup,
        recommended_setup=recommended_setup,
        followed_recommendation=bool(setup.get("followed_recommendation", selected_setup == recommended_setup)),
        setup_outcome_id=setup_outcome,
        setup_label=str(setup.get("setup_label", "")),
        setup_posture=str(setup.get("setup_posture", "")),
        opening_priority=str(setup.get("opening_priority", "")),
        week11_pressure=str(setup.get("week11_pressure", "")),
        visible_effects=tuple(
            Week11SetupEffect(
                value=str(effect.get("id", "")),
                label=str(effect.get("label", "")),
                polarity=str(effect.get("polarity", "")),
            )
            for effect in effects
            if isinstance(effect, dict)
        ),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(setup.get("next_hook", "")),
    )


def render_week11_setup_json(lock: Week11SetupLock) -> str:
    """Canonical JSON export for a locked Week-11 setup."""
    payload = {
        "week11_setup": {
            "artifact_type": "week11_setup",
            "schema_version": 1,
            "source_artifacts": {
                "week10_post_match_review": WEEK10_POST_MATCH_REVIEW_FILENAME,
            },
            "week": 11,
            "route": "/week11/setup",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week10_outcome_id": lock.week10_outcome_id,
            "week10_result_tier": lock.week10_result_tier,
            "week10_result_grade": lock.week10_result_grade,
            "review_outcome_id": lock.review_outcome_id,
            "review_label": lock.review_label,
            "lesson": lock.lesson,
            "carry_forward_tag": lock.carry_forward_tag,
            "carry_forward_type": lock.carry_forward_type,
            "carry_forward_polarity": lock.carry_forward_polarity,
            "selected_setup": lock.selected_setup,
            "recommended_setup": lock.recommended_setup,
            "followed_recommendation": lock.followed_recommendation,
            "setup_outcome_id": lock.setup_outcome_id,
            "setup_label": lock.setup_label,
            "setup_posture": lock.setup_posture,
            "opening_priority": lock.opening_priority,
            "week11_pressure": lock.week11_pressure,
            "visible_effects": [
                {
                    "id": effect.value,
                    "label": effect.label,
                    "polarity": effect.polarity,
                }
                for effect in lock.visible_effects
            ],
            "result_basis": list(lock.result_basis),
            "next_hook": lock.next_hook,
            "stops_before": "week11_prep",
            "next_artifact": WEEK11_PREP_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_WEEK11_PREP_OPTIONS: tuple[Week11PrepOption, ...] = (
    Week11PrepOption(
        value="build_edge_lane",
        label="Build edge lane",
        lane="edge work",
        payoff="Spend prep time turning the setup pressure into a repeatable first call.",
        risk="Can force the carry-forward if the opponent changes the shape.",
    ),
    Week11PrepOption(
        value="scout_countermove",
        label="Scout countermove",
        lane="opponent read",
        payoff="Look for the opponent's first answer before committing scrim reps.",
        risk="Can make the room read instead of execute if the scout work sprawls.",
    ),
    Week11PrepOption(
        value="stabilize_room",
        label="Stabilize room",
        lane="room load",
        payoff="Lower emotional load before the carry-forward becomes practice pressure.",
        risk="Can underuse a live edge if stability becomes the whole block.",
    ),
)

_WEEK11_SCRIM_OPTIONS: tuple[Week11ScrimOption, ...] = (
    Week11ScrimOption(
        value="repeat_edge",
        label="Repeat the edge",
        lane="identity pressure",
        payoff="Run the scrim around the prep lane's first call until contact shows whether it holds.",
        risk="Can punish the room if the prep lane was already forced or tentative.",
    ),
    Week11ScrimOption(
        value="show_countermove",
        label="Show the countermove",
        lane="opponent answer",
        payoff="Have the scout side reveal the likely punish and test whether the prep adapts.",
        risk="Can overload the room if the read is noisy or the team needed a concrete task.",
    ),
    Week11ScrimOption(
        value="steady_first_contact",
        label="Steady first contact",
        lane="room protocol",
        payoff="Drill first-contact comms and reset protocol before the call tree widens.",
        risk="Can dull tempo if the edge needed pressure instead of protection.",
    ),
)

_WEEK11_PREP_COPY: dict[Week11PrepOutcome, dict[str, str]] = {
    "edge_lane_drilled": {
        "prep_priority": "The first prep block drills the edge lane until the call is repeatable.",
        "scrim_seed": "edge_lane_reps",
        "effect_id": "edge_lane_repped",
        "effect_label": "Edge lane repped",
        "polarity": "positive",
        "next_hook": "Week 11 scrim can start by checking whether the edge lane repeats under pressure.",
    },
    "edge_lane_forced": {
        "prep_priority": "The block forces an edge before the room has proved it still exists.",
        "scrim_seed": "forced_edge_watch",
        "effect_id": "forced_edge_watch",
        "effect_label": "Forced edge watch",
        "polarity": "watch",
        "next_hook": "Week 11 scrim should punish-test the forced edge before the team leans on it.",
    },
    "countermove_ready": {
        "prep_priority": "The scout block names the likely countermove and keeps the response narrow.",
        "scrim_seed": "countermove_check",
        "effect_id": "countermove_ready",
        "effect_label": "Countermove ready",
        "polarity": "positive",
        "next_hook": "Week 11 scrim can start by checking the countermove read.",
    },
    "countermove_noisy": {
        "prep_priority": "The scout block finds too many possible answers and muddies the first call.",
        "scrim_seed": "noisy_read_watch",
        "effect_id": "countermove_noise",
        "effect_label": "Countermove noise",
        "polarity": "watch",
        "next_hook": "Week 11 scrim should narrow the read before layering more calls.",
    },
    "room_prepped": {
        "prep_priority": "The room load is lowered enough for the carry-forward to survive first contact.",
        "scrim_seed": "stable_room_check",
        "effect_id": "room_load_prepped",
        "effect_label": "Room load prepped",
        "polarity": "positive",
        "next_hook": "Week 11 scrim can start from a stable-room check.",
    },
    "room_tentative": {
        "prep_priority": "The room gets calmer, but the block leaves too little action for the first scrim.",
        "scrim_seed": "tentative_room_watch",
        "effect_id": "tentative_room_watch",
        "effect_label": "Tentative room watch",
        "polarity": "watch",
        "next_hook": "Week 11 scrim should turn the calmer room into a concrete task quickly.",
    },
}


def _week11_prep_prompt(setup: Week11SetupLock) -> str:
    if setup.week11_pressure == "edge_lane":
        return "The first Week 11 prep block needs to make the edge repeatable."
    if setup.week11_pressure in {"validation_lane", "overcalled_edge", "scattered_validation"}:
        return "The first Week 11 prep block needs to prove the carry-forward before scrims."
    return "The first Week 11 prep block needs to control room load before pressure returns."


def _recommended_week11_prep(setup: Week11SetupLock) -> Week11PrepChoice:
    if setup.week11_pressure == "edge_lane":
        return "build_edge_lane"
    if setup.week11_pressure in {"validation_lane", "overcalled_edge", "scattered_validation"}:
        return "scout_countermove"
    return "stabilize_room"


def week11_prep_plan(setup: Week11SetupLock) -> Week11PrepPlan:
    """Build the read-only Week-11 prep prompt from the setup artifact."""
    return Week11PrepPlan(
        source_branch=setup.source_branch,
        setup_branch=setup.setup_branch,
        chosen_focus=setup.chosen_focus,
        week10_outcome_id=setup.week10_outcome_id,
        week10_result_tier=setup.week10_result_tier,
        week10_result_grade=setup.week10_result_grade,
        carry_forward_tag=setup.carry_forward_tag,
        carry_forward_type=setup.carry_forward_type,
        carry_forward_polarity=setup.carry_forward_polarity,
        selected_setup=setup.selected_setup,
        setup_outcome_id=setup.setup_outcome_id,
        opening_priority=setup.opening_priority,
        week11_pressure=setup.week11_pressure,
        visible_effects=setup.visible_effects,
        prep_prompt=_week11_prep_prompt(setup),
        recommended_prep=_recommended_week11_prep(setup),
        options=_WEEK11_PREP_OPTIONS,
    )


def _week11_prep_outcome(plan: Week11PrepPlan, selected_prep: Week11PrepChoice) -> Week11PrepOutcome:
    if selected_prep == "build_edge_lane":
        if plan.week11_pressure == "edge_lane" or plan.carry_forward_type == "advantage":
            return "edge_lane_drilled"
        return "edge_lane_forced"
    if selected_prep == "scout_countermove":
        if plan.week11_pressure in {"validation_lane", "overcalled_edge", "scattered_validation"}:
            return "countermove_ready"
        return "countermove_noisy"
    if plan.week11_pressure in {"stable_room", "passive_room"} or plan.carry_forward_type == "constraint":
        return "room_prepped"
    return "room_tentative"


def _week11_prep_option(selected_prep: Week11PrepChoice) -> Week11PrepOption:
    return next(option for option in _WEEK11_PREP_OPTIONS if option.value == selected_prep)


def resolve_week11_prep(plan: Week11PrepPlan, selected_prep: str) -> Week11PrepLock:
    """Resolve the selected Week-11 prep allocation into a prep artifact."""
    if selected_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("selected_prep must list a Week-11 prep choice")
    selected = selected_prep
    outcome_id = _week11_prep_outcome(plan, selected)
    option = _week11_prep_option(selected)
    copy = _WEEK11_PREP_COPY[outcome_id]
    prep_effect = Week11SetupEffect(
        value=copy["effect_id"],
        label=copy["effect_label"],
        polarity=copy["polarity"],
    )
    return Week11PrepLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week10_outcome_id=plan.week10_outcome_id,
        week10_result_tier=plan.week10_result_tier,
        week10_result_grade=plan.week10_result_grade,
        carry_forward_tag=plan.carry_forward_tag,
        carry_forward_type=plan.carry_forward_type,
        carry_forward_polarity=plan.carry_forward_polarity,
        selected_setup=plan.selected_setup,
        setup_outcome_id=plan.setup_outcome_id,
        week11_pressure=plan.week11_pressure,
        selected_prep=selected,
        recommended_prep=plan.recommended_prep,
        followed_recommendation=selected == plan.recommended_prep,
        prep_outcome_id=outcome_id,
        prep_label=option.label,
        prep_lane=option.lane,
        prep_priority=copy["prep_priority"],
        scrim_seed=copy["scrim_seed"],
        visible_effects=(prep_effect, *plan.visible_effects),
        result_basis=(
            f"setup_outcome:{plan.setup_outcome_id}",
            f"pressure:{plan.week11_pressure}",
            f"selected_prep:{selected}",
            f"recommended_prep:{plan.recommended_prep}",
            f"prep_outcome:{outcome_id}",
        ),
        next_hook=copy["next_hook"],
    )


def week11_prep_from_json(text: str) -> Week11PrepLock:
    """Parse a written ``week11_prep.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_prep JSON is malformed") from exc
    prep = data.get("week11_prep") if isinstance(data, dict) else None
    if not isinstance(prep, dict):
        raise ValueError("week11_prep JSON must contain a week11_prep object")
    selected_setup = prep.get("selected_setup")
    if selected_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("week11_prep selected_setup must list a Week-11 setup choice")
    setup_outcome = prep.get("setup_outcome_id")
    if setup_outcome not in WEEK11_SETUP_OUTCOMES:
        raise ValueError("week11_prep setup_outcome_id must list a Week-11 setup outcome")
    selected_prep = prep.get("selected_prep")
    if selected_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_prep selected_prep must list a Week-11 prep choice")
    recommended_prep = prep.get("recommended_prep")
    if recommended_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_prep recommended_prep must list a Week-11 prep choice")
    prep_outcome = prep.get("prep_outcome_id")
    if prep_outcome not in WEEK11_PREP_OUTCOMES:
        raise ValueError("week11_prep prep_outcome_id must list a Week-11 prep outcome")
    effects = prep.get("visible_effects")
    if not isinstance(effects, list):
        raise ValueError("week11_prep JSON must include visible_effects")
    basis = prep.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week11_prep JSON must include result_basis")
    if prep.get("next_artifact") not in (None, WEEK11_SCRIM_FILENAME):
        raise ValueError("week11_prep next_artifact must be null or week11_scrim.json")
    return Week11PrepLock(
        source_branch=str(prep.get("source_branch", "")),
        setup_branch=str(prep.get("setup_branch", "")),
        chosen_focus=str(prep.get("chosen_focus", "")),
        week10_outcome_id=str(prep.get("week10_outcome_id", "")),
        week10_result_tier=str(prep.get("week10_result_tier", "")),
        week10_result_grade=str(prep.get("week10_result_grade", "")),
        carry_forward_tag=str(prep.get("carry_forward_tag", "")),
        carry_forward_type=str(prep.get("carry_forward_type", "")),
        carry_forward_polarity=str(prep.get("carry_forward_polarity", "")),
        selected_setup=selected_setup,
        setup_outcome_id=setup_outcome,
        week11_pressure=str(prep.get("week11_pressure", "")),
        selected_prep=selected_prep,
        recommended_prep=recommended_prep,
        followed_recommendation=bool(prep.get("followed_recommendation", selected_prep == recommended_prep)),
        prep_outcome_id=prep_outcome,
        prep_label=str(prep.get("prep_label", "")),
        prep_lane=str(prep.get("prep_lane", "")),
        prep_priority=str(prep.get("prep_priority", "")),
        scrim_seed=str(prep.get("scrim_seed", "")),
        visible_effects=tuple(
            Week11SetupEffect(
                value=str(effect.get("id", "")),
                label=str(effect.get("label", "")),
                polarity=str(effect.get("polarity", "")),
            )
            for effect in effects
            if isinstance(effect, dict)
        ),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(prep.get("next_hook", "")),
    )


def render_week11_prep_json(lock: Week11PrepLock) -> str:
    """Canonical JSON export for a locked Week-11 prep block."""
    payload = {
        "week11_prep": {
            "artifact_type": "week11_prep",
            "schema_version": 1,
            "source_artifacts": {
                "week11_setup": WEEK11_SETUP_FILENAME,
            },
            "week": 11,
            "route": "/week11/prep",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week10_outcome_id": lock.week10_outcome_id,
            "week10_result_tier": lock.week10_result_tier,
            "week10_result_grade": lock.week10_result_grade,
            "carry_forward_tag": lock.carry_forward_tag,
            "carry_forward_type": lock.carry_forward_type,
            "carry_forward_polarity": lock.carry_forward_polarity,
            "selected_setup": lock.selected_setup,
            "setup_outcome_id": lock.setup_outcome_id,
            "week11_pressure": lock.week11_pressure,
            "selected_prep": lock.selected_prep,
            "recommended_prep": lock.recommended_prep,
            "followed_recommendation": lock.followed_recommendation,
            "prep_outcome_id": lock.prep_outcome_id,
            "prep_label": lock.prep_label,
            "prep_lane": lock.prep_lane,
            "prep_priority": lock.prep_priority,
            "scrim_seed": lock.scrim_seed,
            "visible_effects": [
                {
                    "id": effect.value,
                    "label": effect.label,
                    "polarity": effect.polarity,
                }
                for effect in lock.visible_effects
            ],
            "result_basis": list(lock.result_basis),
            "next_hook": lock.next_hook,
            "stops_before": "week11_scrim",
            "next_artifact": WEEK11_SCRIM_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_WEEK11_SCRIM_COPY: dict[Week11ScrimOutcome, dict[str, str]] = {
    "edge_repeated_under_pressure": {
        "scrim_label": "Edge repeated under pressure",
        "scrim_priority": "The edge lane survives first contact and can anchor a match-planning lane.",
        "match_plan_seed": "edge_pressure_plan",
        "effect_id": "edge_repeated_under_pressure",
        "effect_label": "Edge repeated under pressure",
        "polarity": "positive",
        "scrim_protocol": "repeat_edge_pressure_reps",
        "analyst_read_id": "edge_lane_survives_contact",
        "next_hook": "Week 11 match planning can start from a repeated edge lane.",
    },
    "edge_counter_scouted": {
        "scrim_label": "Edge counter scouted",
        "scrim_priority": "The expected counter appears without collapsing the original edge.",
        "match_plan_seed": "edge_counter_plan",
        "effect_id": "edge_counter_scouted",
        "effect_label": "Edge counter scouted",
        "polarity": "positive",
        "scrim_protocol": "counter_reveal_on_edge",
        "analyst_read_id": "edge_counter_named",
        "next_hook": "Week 11 match planning can carry both the edge lane and its first answer.",
    },
    "edge_tempo_dulled": {
        "scrim_label": "Edge tempo dulled",
        "scrim_priority": "The reset work protects the room but takes urgency out of the edge call.",
        "match_plan_seed": "edge_tempo_watch",
        "effect_id": "edge_tempo_dulled",
        "effect_label": "Edge tempo dulled",
        "polarity": "watch",
        "scrim_protocol": "first_contact_reset_on_edge",
        "analyst_read_id": "edge_loses_tempo",
        "next_hook": "Week 11 match planning should restore one pressure trigger to the edge lane.",
    },
    "forced_edge_punished": {
        "scrim_label": "Forced edge punished",
        "scrim_priority": "Repeating the forced edge gives the scout side a clean punish window.",
        "match_plan_seed": "forced_edge_repair_plan",
        "effect_id": "forced_edge_punished",
        "effect_label": "Forced edge punished",
        "polarity": "watch",
        "scrim_protocol": "repeat_forced_edge",
        "analyst_read_id": "forced_edge_breaks",
        "next_hook": "Week 11 match planning should repair the edge before building around it.",
    },
    "forced_edge_exposed": {
        "scrim_label": "Forced edge exposed",
        "scrim_priority": "The countermove makes the weak point obvious before the match plan commits.",
        "match_plan_seed": "forced_edge_counter_plan",
        "effect_id": "forced_edge_exposed",
        "effect_label": "Forced edge exposed",
        "polarity": "watch",
        "scrim_protocol": "counter_reveal_on_forced_edge",
        "analyst_read_id": "forced_edge_counter_visible",
        "next_hook": "Week 11 match planning can protect the forced edge from its named answer.",
    },
    "forced_edge_depressurized": {
        "scrim_label": "Forced edge depressurized",
        "scrim_priority": "First-contact protocol lowers pressure enough to keep the forced edge usable.",
        "match_plan_seed": "depressurized_edge_plan",
        "effect_id": "forced_edge_depressurized",
        "effect_label": "Forced edge depressurized",
        "polarity": "positive",
        "scrim_protocol": "first_contact_reset_for_forced_edge",
        "analyst_read_id": "forced_edge_needs_guardrails",
        "next_hook": "Week 11 match planning can use the edge only with first-contact guardrails.",
    },
    "counter_read_ignored": {
        "scrim_label": "Counter read ignored",
        "scrim_priority": "The room repeats its own edge and leaves the prepared countermove untested.",
        "match_plan_seed": "counter_read_repair_plan",
        "effect_id": "counter_read_ignored",
        "effect_label": "Counter read ignored",
        "polarity": "watch",
        "scrim_protocol": "repeat_edge_over_counter_read",
        "analyst_read_id": "prepared_counter_unproven",
        "next_hook": "Week 11 match planning should not trust the countermove until it is shown.",
    },
    "countermove_confirmed": {
        "scrim_label": "Countermove confirmed",
        "scrim_priority": "The scout side shows the expected answer and the room keeps the response narrow.",
        "match_plan_seed": "countermove_response_plan",
        "effect_id": "countermove_confirmed",
        "effect_label": "Countermove confirmed",
        "polarity": "positive",
        "scrim_protocol": "confirm_countermove",
        "analyst_read_id": "countermove_response_ready",
        "next_hook": "Week 11 match planning can carry a named countermove response.",
    },
    "counter_timing_delayed": {
        "scrim_label": "Counter timing delayed",
        "scrim_priority": "The room stays calm but delays seeing whether the countermove lands on time.",
        "match_plan_seed": "counter_timing_watch",
        "effect_id": "counter_timing_delayed",
        "effect_label": "Counter timing delayed",
        "polarity": "watch",
        "scrim_protocol": "first_contact_reset_before_counter",
        "analyst_read_id": "counter_timing_unproven",
        "next_hook": "Week 11 match planning should time-box the countermove check.",
    },
    "noise_hardened_into_call": {
        "scrim_label": "Noise hardened into call",
        "scrim_priority": "Repeating the edge turns the noisy read into one concrete call.",
        "match_plan_seed": "hardened_read_plan",
        "effect_id": "noise_hardened_into_call",
        "effect_label": "Noise hardened into call",
        "polarity": "positive",
        "scrim_protocol": "repeat_edge_to_reduce_noise",
        "analyst_read_id": "noise_becomes_call",
        "next_hook": "Week 11 match planning can start from the narrowed call instead of the full tree.",
    },
    "read_narrowed": {
        "scrim_label": "Read narrowed",
        "scrim_priority": "The countermove reveal trims the noisy scout packet down to one answer.",
        "match_plan_seed": "narrow_read_plan",
        "effect_id": "read_narrowed",
        "effect_label": "Read narrowed",
        "polarity": "positive",
        "scrim_protocol": "counter_reveal_to_narrow_noise",
        "analyst_read_id": "noisy_read_narrowed",
        "next_hook": "Week 11 match planning can carry one answer instead of a sprawling read.",
    },
    "read_noise_depressurized": {
        "scrim_label": "Read noise depressurized",
        "scrim_priority": "First-contact work calms the noise but leaves the actual answer soft.",
        "match_plan_seed": "depressurized_read_watch",
        "effect_id": "read_noise_depressurized",
        "effect_label": "Read noise depressurized",
        "polarity": "watch",
        "scrim_protocol": "first_contact_reset_on_noisy_read",
        "analyst_read_id": "noise_calmed_not_solved",
        "next_hook": "Week 11 match planning should pair the calmer room with one named answer.",
    },
    "stable_room_underused": {
        "scrim_label": "Stable room underused",
        "scrim_priority": "The room is stable, but repeating the edge fails to use that stability fully.",
        "match_plan_seed": "underused_room_watch",
        "effect_id": "stable_room_underused",
        "effect_label": "Stable room underused",
        "polarity": "watch",
        "scrim_protocol": "repeat_edge_from_stable_room",
        "analyst_read_id": "stable_room_needs_task",
        "next_hook": "Week 11 match planning should turn stability into one explicit demand.",
    },
    "room_overloaded_by_scout": {
        "scrim_label": "Room overloaded by scout",
        "scrim_priority": "The scout reveal adds more information than the stabilized room can absorb.",
        "match_plan_seed": "scout_overload_watch",
        "effect_id": "room_overloaded_by_scout",
        "effect_label": "Room overloaded by scout",
        "polarity": "watch",
        "scrim_protocol": "counter_reveal_to_stable_room",
        "analyst_read_id": "stable_room_overloaded",
        "next_hook": "Week 11 match planning should keep the room stable by cutting the read count.",
    },
    "first_contact_stabilized": {
        "scrim_label": "First contact stabilized",
        "scrim_priority": "The room converts the prep into a clear first-contact reset protocol.",
        "match_plan_seed": "first_contact_plan",
        "effect_id": "first_contact_stabilized",
        "effect_label": "First contact stabilized",
        "polarity": "positive",
        "scrim_protocol": "stabilize_first_contact",
        "analyst_read_id": "first_contact_protocol_ready",
        "next_hook": "Week 11 match planning can start from a stable first-contact call sheet.",
    },
    "tentative_room_given_task": {
        "scrim_label": "Tentative room given task",
        "scrim_priority": "Repeating the edge gives the tentative room a concrete job without adding noise.",
        "match_plan_seed": "tasked_room_plan",
        "effect_id": "tentative_room_given_task",
        "effect_label": "Tentative room given task",
        "polarity": "positive",
        "scrim_protocol": "repeat_edge_for_tentative_room",
        "analyst_read_id": "tentative_room_has_task",
        "next_hook": "Week 11 match planning can use the assigned task as the room's first anchor.",
    },
    "tentative_room_overloaded": {
        "scrim_label": "Tentative room overloaded",
        "scrim_priority": "The countermove reveal adds load before the tentative room has a task.",
        "match_plan_seed": "tentative_overload_watch",
        "effect_id": "tentative_room_overloaded",
        "effect_label": "Tentative room overloaded",
        "polarity": "watch",
        "scrim_protocol": "counter_reveal_to_tentative_room",
        "analyst_read_id": "tentative_room_overloaded",
        "next_hook": "Week 11 match planning should strip the read back to one safe first call.",
    },
    "room_stays_tentative": {
        "scrim_label": "Room stays tentative",
        "scrim_priority": "The room remains calm but does not gain a concrete match-planning action.",
        "match_plan_seed": "tentative_room_watch",
        "effect_id": "room_stays_tentative",
        "effect_label": "Room stays tentative",
        "polarity": "watch",
        "scrim_protocol": "first_contact_reset_for_tentative_room",
        "analyst_read_id": "tentative_room_still_passive",
        "next_hook": "Week 11 match planning should add one action trigger before the room drifts.",
    },
}

_WEEK11_SCRIM_OUTCOME_MATRIX: dict[Week11PrepOutcome, dict[Week11ScrimChoice, Week11ScrimOutcome]] = {
    "edge_lane_drilled": {
        "repeat_edge": "edge_repeated_under_pressure",
        "show_countermove": "edge_counter_scouted",
        "steady_first_contact": "edge_tempo_dulled",
    },
    "edge_lane_forced": {
        "repeat_edge": "forced_edge_punished",
        "show_countermove": "forced_edge_exposed",
        "steady_first_contact": "forced_edge_depressurized",
    },
    "countermove_ready": {
        "repeat_edge": "counter_read_ignored",
        "show_countermove": "countermove_confirmed",
        "steady_first_contact": "counter_timing_delayed",
    },
    "countermove_noisy": {
        "repeat_edge": "noise_hardened_into_call",
        "show_countermove": "read_narrowed",
        "steady_first_contact": "read_noise_depressurized",
    },
    "room_prepped": {
        "repeat_edge": "stable_room_underused",
        "show_countermove": "room_overloaded_by_scout",
        "steady_first_contact": "first_contact_stabilized",
    },
    "room_tentative": {
        "repeat_edge": "tentative_room_given_task",
        "show_countermove": "tentative_room_overloaded",
        "steady_first_contact": "room_stays_tentative",
    },
}

_WEEK11_SCRIM_RECOMMENDATIONS: dict[Week11PrepOutcome, tuple[Week11ScrimChoice, str]] = {
    "edge_lane_drilled": (
        "repeat_edge",
        "The edge lane already repeated in prep, so the scrim should test it under contact.",
    ),
    "edge_lane_forced": (
        "show_countermove",
        "The edge was forced in prep, so the scout side should expose the punish before match planning.",
    ),
    "countermove_ready": (
        "show_countermove",
        "The countermove read is ready, so the scrim should confirm it against a live answer.",
    ),
    "countermove_noisy": (
        "show_countermove",
        "The read is noisy, so revealing the likely answer is the fastest way to narrow the tree.",
    ),
    "room_prepped": (
        "steady_first_contact",
        "The room is prepared, so first-contact protocol should turn stability into something repeatable.",
    ),
    "room_tentative": (
        "repeat_edge",
        "The room is tentative, so it needs one concrete task before adding more information.",
    ),
}


def _week11_scrim_prompt(prep: Week11PrepLock) -> str:
    if prep.scrim_seed in {"edge_lane_reps", "forced_edge_watch"}:
        return "The first Week 11 scrim needs to prove whether the edge lane survives contact."
    if prep.scrim_seed in {"countermove_check", "noisy_read_watch"}:
        return "The first Week 11 scrim needs to check the opponent answer without sprawling."
    return "The first Week 11 scrim needs to turn room stability into a repeatable protocol."


def _recommended_week11_scrim(prep: Week11PrepLock) -> Week11ScrimChoice:
    return _WEEK11_SCRIM_RECOMMENDATIONS[prep.prep_outcome_id][0]


def _week11_scrim_recommendation_reason(prep: Week11PrepLock) -> str:
    return _WEEK11_SCRIM_RECOMMENDATIONS[prep.prep_outcome_id][1]


def week11_scrim_plan(prep: Week11PrepLock) -> Week11ScrimPlan:
    """Build the read-only Week-11 scrim prompt from the prep artifact."""
    return Week11ScrimPlan(
        source_branch=prep.source_branch,
        setup_branch=prep.setup_branch,
        chosen_focus=prep.chosen_focus,
        week10_outcome_id=prep.week10_outcome_id,
        week10_result_tier=prep.week10_result_tier,
        week10_result_grade=prep.week10_result_grade,
        carry_forward_tag=prep.carry_forward_tag,
        carry_forward_type=prep.carry_forward_type,
        carry_forward_polarity=prep.carry_forward_polarity,
        selected_setup=prep.selected_setup,
        setup_outcome_id=prep.setup_outcome_id,
        week11_pressure=prep.week11_pressure,
        selected_prep=prep.selected_prep,
        recommended_prep=prep.recommended_prep,
        prep_outcome_id=prep.prep_outcome_id,
        prep_label=prep.prep_label,
        prep_lane=prep.prep_lane,
        prep_priority=prep.prep_priority,
        scrim_seed=prep.scrim_seed,
        visible_effects=prep.visible_effects,
        scrim_prompt=_week11_scrim_prompt(prep),
        recommended_scrim=_recommended_week11_scrim(prep),
        recommendation_reason=_week11_scrim_recommendation_reason(prep),
        options=_WEEK11_SCRIM_OPTIONS,
    )


def _week11_scrim_outcome(plan: Week11ScrimPlan, selected_scrim: Week11ScrimChoice) -> Week11ScrimOutcome:
    return _WEEK11_SCRIM_OUTCOME_MATRIX[plan.prep_outcome_id][selected_scrim]


def _week11_scrim_option(selected_scrim: Week11ScrimChoice) -> Week11ScrimOption:
    return next(option for option in _WEEK11_SCRIM_OPTIONS if option.value == selected_scrim)


def resolve_week11_scrim(plan: Week11ScrimPlan, selected_scrim: str) -> Week11ScrimLock:
    """Resolve the selected Week-11 scrim protocol into a scrim artifact."""
    if selected_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("selected_scrim must list a Week-11 scrim choice")
    selected = selected_scrim
    outcome_id = _week11_scrim_outcome(plan, selected)
    option = _week11_scrim_option(selected)
    copy = _WEEK11_SCRIM_COPY[outcome_id]
    scrim_effect = Week11SetupEffect(
        value=copy["effect_id"],
        label=copy["effect_label"],
        polarity=copy["polarity"],
    )
    return Week11ScrimLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week10_outcome_id=plan.week10_outcome_id,
        week10_result_tier=plan.week10_result_tier,
        week10_result_grade=plan.week10_result_grade,
        carry_forward_tag=plan.carry_forward_tag,
        carry_forward_type=plan.carry_forward_type,
        carry_forward_polarity=plan.carry_forward_polarity,
        selected_setup=plan.selected_setup,
        setup_outcome_id=plan.setup_outcome_id,
        week11_pressure=plan.week11_pressure,
        selected_prep=plan.selected_prep,
        recommended_prep=plan.recommended_prep,
        prep_outcome_id=plan.prep_outcome_id,
        prep_label=plan.prep_label,
        prep_lane=plan.prep_lane,
        prep_priority=plan.prep_priority,
        scrim_seed=plan.scrim_seed,
        selected_scrim=selected,
        recommended_scrim=plan.recommended_scrim,
        followed_recommendation=selected == plan.recommended_scrim,
        scrim_outcome_id=outcome_id,
        scrim_label=copy["scrim_label"],
        scrim_lane=option.lane,
        scrim_protocol=copy["scrim_protocol"],
        analyst_read_id=copy["analyst_read_id"],
        recommendation_reason=plan.recommendation_reason,
        scrim_priority=copy["scrim_priority"],
        match_plan_seed=copy["match_plan_seed"],
        visible_effects=(scrim_effect, *plan.visible_effects),
        result_basis=(
            f"prep_outcome:{plan.prep_outcome_id}",
            f"scrim_seed:{plan.scrim_seed}",
            f"selected_scrim:{selected}",
            f"recommended_scrim:{plan.recommended_scrim}",
            f"protocol:{copy['scrim_protocol']}",
            f"analyst_read:{copy['analyst_read_id']}",
            f"scrim_outcome:{outcome_id}",
        ),
        next_hook=copy["next_hook"],
    )


def week11_scrim_from_json(text: str) -> Week11ScrimLock:
    """Parse a written ``week11_scrim.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_scrim JSON is malformed") from exc
    scrim = data.get("week11_scrim") if isinstance(data, dict) else None
    if not isinstance(scrim, dict):
        raise ValueError("week11_scrim JSON must contain a week11_scrim object")
    selected_setup = scrim.get("selected_setup")
    if selected_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("week11_scrim selected_setup must list a Week-11 setup choice")
    setup_outcome = scrim.get("setup_outcome_id")
    if setup_outcome not in WEEK11_SETUP_OUTCOMES:
        raise ValueError("week11_scrim setup_outcome_id must list a Week-11 setup outcome")
    selected_prep = scrim.get("selected_prep")
    if selected_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_scrim selected_prep must list a Week-11 prep choice")
    recommended_prep = scrim.get("recommended_prep")
    if recommended_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_scrim recommended_prep must list a Week-11 prep choice")
    prep_outcome = scrim.get("prep_outcome_id")
    if prep_outcome not in WEEK11_PREP_OUTCOMES:
        raise ValueError("week11_scrim prep_outcome_id must list a Week-11 prep outcome")
    selected_scrim = scrim.get("selected_scrim")
    if selected_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("week11_scrim selected_scrim must list a Week-11 scrim choice")
    recommended_scrim = scrim.get("recommended_scrim")
    if recommended_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("week11_scrim recommended_scrim must list a Week-11 scrim choice")
    scrim_outcome = scrim.get("scrim_outcome_id")
    if scrim_outcome not in WEEK11_SCRIM_OUTCOMES:
        raise ValueError("week11_scrim scrim_outcome_id must list a Week-11 scrim outcome")
    effects = scrim.get("visible_effects")
    if not isinstance(effects, list):
        raise ValueError("week11_scrim JSON must include visible_effects")
    basis = scrim.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week11_scrim JSON must include result_basis")
    if scrim.get("next_artifact") not in (None, WEEK11_MATCH_PLAN_FILENAME):
        raise ValueError("week11_scrim next_artifact must be null or week11_match_plan.json")
    return Week11ScrimLock(
        source_branch=str(scrim.get("source_branch", "")),
        setup_branch=str(scrim.get("setup_branch", "")),
        chosen_focus=str(scrim.get("chosen_focus", "")),
        week10_outcome_id=str(scrim.get("week10_outcome_id", "")),
        week10_result_tier=str(scrim.get("week10_result_tier", "")),
        week10_result_grade=str(scrim.get("week10_result_grade", "")),
        carry_forward_tag=str(scrim.get("carry_forward_tag", "")),
        carry_forward_type=str(scrim.get("carry_forward_type", "")),
        carry_forward_polarity=str(scrim.get("carry_forward_polarity", "")),
        selected_setup=selected_setup,
        setup_outcome_id=setup_outcome,
        week11_pressure=str(scrim.get("week11_pressure", "")),
        selected_prep=selected_prep,
        recommended_prep=recommended_prep,
        prep_outcome_id=prep_outcome,
        prep_label=str(scrim.get("prep_label", "")),
        prep_lane=str(scrim.get("prep_lane", "")),
        prep_priority=str(scrim.get("prep_priority", "")),
        scrim_seed=str(scrim.get("scrim_seed", "")),
        selected_scrim=selected_scrim,
        recommended_scrim=recommended_scrim,
        followed_recommendation=bool(scrim.get("followed_recommendation", selected_scrim == recommended_scrim)),
        scrim_outcome_id=scrim_outcome,
        scrim_label=str(scrim.get("scrim_label", "")),
        scrim_lane=str(scrim.get("scrim_lane", "")),
        scrim_protocol=str(scrim.get("scrim_protocol", "")),
        analyst_read_id=str(scrim.get("analyst_read_id", "")),
        recommendation_reason=str(scrim.get("recommendation_reason", "")),
        scrim_priority=str(scrim.get("scrim_priority", "")),
        match_plan_seed=str(scrim.get("match_plan_seed", "")),
        visible_effects=tuple(
            Week11SetupEffect(
                value=str(effect.get("id", "")),
                label=str(effect.get("label", "")),
                polarity=str(effect.get("polarity", "")),
            )
            for effect in effects
            if isinstance(effect, dict)
        ),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(scrim.get("next_hook", "")),
    )


def render_week11_scrim_json(lock: Week11ScrimLock) -> str:
    """Canonical JSON export for a locked Week-11 scrim protocol."""
    payload = {
        "week11_scrim": {
            "artifact_type": "week11_scrim",
            "checkpoint": "week11_scrim",
            "schema_version": 1,
            "source_artifact": WEEK11_PREP_FILENAME,
            "source_artifacts": {
                "week11_prep": WEEK11_PREP_FILENAME,
            },
            "week": 11,
            "route": "/week11/scrim",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week10_outcome_id": lock.week10_outcome_id,
            "week10_result_tier": lock.week10_result_tier,
            "week10_result_grade": lock.week10_result_grade,
            "carry_forward_tag": lock.carry_forward_tag,
            "carry_forward_type": lock.carry_forward_type,
            "carry_forward_polarity": lock.carry_forward_polarity,
            "selected_setup": lock.selected_setup,
            "setup_outcome_id": lock.setup_outcome_id,
            "week11_pressure": lock.week11_pressure,
            "selected_prep": lock.selected_prep,
            "recommended_prep": lock.recommended_prep,
            "prep_outcome_id": lock.prep_outcome_id,
            "prep_label": lock.prep_label,
            "prep_lane": lock.prep_lane,
            "prep_priority": lock.prep_priority,
            "scrim_seed": lock.scrim_seed,
            "selected_scrim": lock.selected_scrim,
            "recommended_scrim": lock.recommended_scrim,
            "followed_recommendation": lock.followed_recommendation,
            "scrim_outcome_id": lock.scrim_outcome_id,
            "scrim_label": lock.scrim_label,
            "scrim_lane": lock.scrim_lane,
            "scrim_protocol": lock.scrim_protocol,
            "analyst_read_id": lock.analyst_read_id,
            "recommendation_reason": lock.recommendation_reason,
            "scrim_priority": lock.scrim_priority,
            "match_plan_seed": lock.match_plan_seed,
            "visible_effects": [
                {
                    "id": effect.value,
                    "label": effect.label,
                    "polarity": effect.polarity,
                }
                for effect in lock.visible_effects
            ],
            "result_basis": list(lock.result_basis),
            "next_hook": lock.next_hook,
            "stops_before": "week11_match_plan",
            "next_artifact": WEEK11_MATCH_PLAN_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_WEEK11_MATCH_PLAN_OPTIONS: tuple[Week11MatchPlanOption, ...] = (
    Week11MatchPlanOption(
        value="trust_the_read",
        label="Trust the read",
        payoff="Convert the analyst and scrim confirmation into the match plan.",
        risk="Can overtrust the read if the opponent hides the first answer.",
        commitment="read_trust",
        result_constraint="trusted_read_must_show_before_second_layer",
    ),
    Week11MatchPlanOption(
        value="attack_the_gap",
        label="Attack the gap",
        payoff="Adapt around the weakness or timing window exposed by the scrim.",
        risk="Can chase the exposed branch if the match starts from a different shape.",
        commitment="gap_attack",
        result_constraint="gap_attack_must_not_chase_hidden_branches",
    ),
    Week11MatchPlanOption(
        value="stabilize_defaults",
        label="Stabilize defaults",
        payoff="Reduce variance and cover the weakness exposed by the scrim.",
        risk="Can give away tempo if stability becomes the whole plan.",
        commitment="default_stability",
        result_constraint="defaults_must_stay_proactive",
    ),
)

_WEEK11_MATCH_OUTCOME_CLASSES: dict[Week11ScrimOutcome, str] = {
    "edge_repeated_under_pressure": "confirming",
    "edge_counter_scouted": "exposing",
    "edge_tempo_dulled": "failing",
    "forced_edge_punished": "failing",
    "forced_edge_exposed": "exposing",
    "forced_edge_depressurized": "failing",
    "counter_read_ignored": "exposing",
    "countermove_confirmed": "confirming",
    "counter_timing_delayed": "failing",
    "noise_hardened_into_call": "confirming",
    "read_narrowed": "exposing",
    "read_noise_depressurized": "failing",
    "stable_room_underused": "exposing",
    "room_overloaded_by_scout": "failing",
    "first_contact_stabilized": "confirming",
    "tentative_room_given_task": "confirming",
    "tentative_room_overloaded": "failing",
    "room_stays_tentative": "failing",
}

_WEEK11_MATCH_PROTOCOL_SIGNALS: dict[str, str] = {
    "repeat_edge_pressure_reps": "high_signal",
    "counter_reveal_on_edge": "high_signal",
    "first_contact_reset_on_edge": "low_signal",
    "repeat_forced_edge": "low_signal",
    "counter_reveal_on_forced_edge": "medium_signal",
    "first_contact_reset_for_forced_edge": "low_signal",
    "repeat_edge_over_counter_read": "medium_signal",
    "confirm_countermove": "high_signal",
    "first_contact_reset_before_counter": "low_signal",
    "repeat_edge_to_reduce_noise": "high_signal",
    "counter_reveal_to_narrow_noise": "high_signal",
    "first_contact_reset_on_noisy_read": "low_signal",
    "repeat_edge_from_stable_room": "medium_signal",
    "counter_reveal_to_stable_room": "low_signal",
    "stabilize_first_contact": "high_signal",
    "repeat_edge_for_tentative_room": "high_signal",
    "counter_reveal_to_tentative_room": "low_signal",
    "first_contact_reset_for_tentative_room": "low_signal",
}

_WEEK11_MATCH_ANALYST_READ_CLASSES: dict[str, str] = {
    "edge_lane_survives_contact": "trust_read",
    "edge_counter_named": "exploit_gap",
    "edge_loses_tempo": "stabilize_execution",
    "forced_edge_breaks": "stabilize_execution",
    "forced_edge_counter_visible": "exploit_gap",
    "forced_edge_needs_guardrails": "stabilize_execution",
    "prepared_counter_unproven": "exploit_gap",
    "countermove_response_ready": "exploit_gap",
    "counter_timing_unproven": "stabilize_execution",
    "noise_becomes_call": "trust_read",
    "noisy_read_narrowed": "exploit_gap",
    "noise_calmed_not_solved": "stabilize_execution",
    "stable_room_needs_task": "exploit_gap",
    "stable_room_overloaded": "stabilize_execution",
    "first_contact_protocol_ready": "trust_read",
    "tentative_room_has_task": "trust_read",
    "tentative_room_overloaded": "stabilize_execution",
    "tentative_room_still_passive": "stabilize_execution",
}

_WEEK11_MATCH_SEEDED_EMPHASES = ("early_objective", "midgame_trade", "late_fight_setup")


def _week11_seed_context(match_plan_seed: str) -> tuple[int, str]:
    bucket = sum(ord(char) for char in match_plan_seed) % len(_WEEK11_MATCH_SEEDED_EMPHASES)
    return bucket, _WEEK11_MATCH_SEEDED_EMPHASES[bucket]


def _week11_match_recommendation(
    scrim: Week11ScrimLock,
    outcome_class: str,
    protocol_signal: str,
    analyst_read_class: str,
) -> tuple[Week11MatchPlanChoice, str, str]:
    if (
        outcome_class == "failing"
        or protocol_signal == "low_signal"
        or analyst_read_class == "stabilize_execution"
    ):
        return (
            "stabilize_defaults",
            "stability_required",
            "The scrim evidence flags execution risk, so the match plan should stabilize defaults before adding layers.",
        )
    if (
        scrim.selected_scrim == scrim.recommended_scrim
        and outcome_class == "confirming"
        and analyst_read_class == "trust_read"
    ):
        return (
            "trust_the_read",
            "confirming_trust_read",
            "The selected scrim matched the recommended block and confirmed the analyst read, so the match plan can trust it.",
        )
    return (
        "attack_the_gap",
        "gap_visible",
        "The scrim exposes a usable opponent branch or timing window, so the match plan should attack that gap.",
    )


def _week11_match_risk(scrim: Week11ScrimLock, recommended_plan: Week11MatchPlanChoice) -> str:
    if any(effect.polarity == "negative" for effect in scrim.visible_effects):
        return "high"
    if any(effect.polarity == "watch" for effect in scrim.visible_effects[:2]):
        return "high" if recommended_plan != "stabilize_defaults" else "medium"
    if recommended_plan == "trust_the_read" and scrim.followed_recommendation:
        return "low"
    return "medium"


def week11_match_plan_preview(scrim: Week11ScrimLock) -> Week11MatchPlanPreview:
    """Build the deterministic Week-11 match-plan preview from the scrim artifact."""
    outcome_class = _WEEK11_MATCH_OUTCOME_CLASSES[scrim.scrim_outcome_id]
    protocol_signal = _WEEK11_MATCH_PROTOCOL_SIGNALS[scrim.scrim_protocol]
    analyst_read_class = _WEEK11_MATCH_ANALYST_READ_CLASSES[scrim.analyst_read_id]
    seed_bucket, seeded_emphasis = _week11_seed_context(scrim.match_plan_seed)
    recommended, basis, reason = _week11_match_recommendation(
        scrim,
        outcome_class,
        protocol_signal,
        analyst_read_class,
    )
    return Week11MatchPlanPreview(
        source_branch=scrim.source_branch,
        setup_branch=scrim.setup_branch,
        chosen_focus=scrim.chosen_focus,
        week10_outcome_id=scrim.week10_outcome_id,
        week10_result_tier=scrim.week10_result_tier,
        week10_result_grade=scrim.week10_result_grade,
        carry_forward_tag=scrim.carry_forward_tag,
        carry_forward_type=scrim.carry_forward_type,
        carry_forward_polarity=scrim.carry_forward_polarity,
        selected_setup=scrim.selected_setup,
        setup_outcome_id=scrim.setup_outcome_id,
        week11_pressure=scrim.week11_pressure,
        selected_prep=scrim.selected_prep,
        recommended_prep=scrim.recommended_prep,
        prep_outcome_id=scrim.prep_outcome_id,
        prep_lane=scrim.prep_lane,
        selected_scrim=scrim.selected_scrim,
        recommended_scrim=scrim.recommended_scrim,
        scrim_outcome_id=scrim.scrim_outcome_id,
        scrim_protocol=scrim.scrim_protocol,
        analyst_read_id=scrim.analyst_read_id,
        match_plan_seed=scrim.match_plan_seed,
        outcome_class=outcome_class,
        protocol_signal=protocol_signal,
        analyst_read_class=analyst_read_class,
        seed_bucket=seed_bucket,
        seeded_emphasis=seeded_emphasis,
        scrim_priority=scrim.scrim_priority,
        visible_effects=scrim.visible_effects,
        recommendation_basis=basis,
        recommended_plan=recommended,
        recommendation_reason=reason,
        match_risk=_week11_match_risk(scrim, recommended),
        options=_WEEK11_MATCH_PLAN_OPTIONS,
    )


def resolve_week11_match_plan(
    preview: Week11MatchPlanPreview,
    selected_plan: str,
) -> Week11MatchPlanLock:
    """Resolve one Week-11 match plan into a deterministic artifact."""
    if selected_plan not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("selected_plan must list a Week-11 match plan")
    plan: Week11MatchPlanChoice = selected_plan  # type: ignore[assignment]
    selected = next(option for option in preview.options if option.value == plan)

    if plan == "trust_the_read":
        risk_taken = "trusting the read can be punished if the opponent hides the first answer"
        thing_to_watch = "whether the read appears before the second layer is called"
        extra_constraints = ("trust_analyst_read", "avoid_second_layer_overreach")
    elif plan == "attack_the_gap":
        risk_taken = "attacking the gap can become reactive if the opponent refuses the branch"
        thing_to_watch = "whether the exposed gap appears on the first timing window"
        extra_constraints = ("attack_visible_gap", "do_not_chase_hidden_branches")
    else:
        risk_taken = "stabilizing defaults can give away tempo if the read was already live"
        thing_to_watch = "whether the default stays proactive after first contact"
        extra_constraints = ("protect_default_shape", "keep_default_proactive")

    constraints = (
        selected.result_constraint,
        f"scrim_outcome:{preview.scrim_outcome_id}",
        f"protocol:{preview.scrim_protocol}",
        f"analyst_read:{preview.analyst_read_id}",
        f"match_seed:{preview.match_plan_seed}",
        f"seeded_emphasis:{preview.seeded_emphasis}",
        *extra_constraints,
    )
    return Week11MatchPlanLock(
        source_branch=preview.source_branch,
        setup_branch=preview.setup_branch,
        chosen_focus=preview.chosen_focus,
        week10_outcome_id=preview.week10_outcome_id,
        week10_result_tier=preview.week10_result_tier,
        week10_result_grade=preview.week10_result_grade,
        carry_forward_tag=preview.carry_forward_tag,
        carry_forward_type=preview.carry_forward_type,
        carry_forward_polarity=preview.carry_forward_polarity,
        selected_setup=preview.selected_setup,
        setup_outcome_id=preview.setup_outcome_id,
        week11_pressure=preview.week11_pressure,
        selected_prep=preview.selected_prep,
        recommended_prep=preview.recommended_prep,
        prep_outcome_id=preview.prep_outcome_id,
        prep_lane=preview.prep_lane,
        selected_scrim=preview.selected_scrim,
        recommended_scrim=preview.recommended_scrim,
        scrim_outcome_id=preview.scrim_outcome_id,
        scrim_protocol=preview.scrim_protocol,
        analyst_read_id=preview.analyst_read_id,
        match_plan_seed=preview.match_plan_seed,
        outcome_class=preview.outcome_class,
        protocol_signal=preview.protocol_signal,
        analyst_read_class=preview.analyst_read_class,
        seed_bucket=preview.seed_bucket,
        seeded_emphasis=preview.seeded_emphasis,
        scrim_priority=preview.scrim_priority,
        visible_effects=preview.visible_effects,
        recommendation_basis=preview.recommendation_basis,
        recommended_plan=preview.recommended_plan,
        available_choices=WEEK11_MATCH_PLAN_CHOICES,
        selected_plan=plan,
        plan_outcome_id=f"week11_match_plan_{plan}",
        plan_label=selected.label,
        followed_recommendation=plan == preview.recommended_plan,
        commitment=selected.commitment,
        risk_taken=risk_taken,
        thing_to_watch=thing_to_watch,
        match_risk=preview.match_risk,
        result_constraints=constraints,
        recommendation_reason=preview.recommendation_reason,
        next_hook=(
            f"Week 11 result can test {selected.commitment} against "
            f"{preview.match_plan_seed}."
        ),
    )


def week11_match_plan_from_json(text: str) -> Week11MatchPlanLock:
    """Parse a written ``week11_match_plan.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_match_plan JSON is malformed") from exc
    match_plan = data.get("week11_match_plan") if isinstance(data, dict) else None
    if not isinstance(match_plan, dict):
        raise ValueError("week11_match_plan JSON must contain a week11_match_plan object")
    selected_setup = match_plan.get("selected_setup")
    if selected_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("week11_match_plan selected_setup must list a Week-11 setup choice")
    setup_outcome = match_plan.get("setup_outcome_id")
    if setup_outcome not in WEEK11_SETUP_OUTCOMES:
        raise ValueError("week11_match_plan setup_outcome_id must list a Week-11 setup outcome")
    selected_prep = match_plan.get("selected_prep")
    if selected_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_match_plan selected_prep must list a Week-11 prep choice")
    recommended_prep = match_plan.get("recommended_prep")
    if recommended_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_match_plan recommended_prep must list a Week-11 prep choice")
    prep_outcome = match_plan.get("prep_outcome_id")
    if prep_outcome not in WEEK11_PREP_OUTCOMES:
        raise ValueError("week11_match_plan prep_outcome_id must list a Week-11 prep outcome")
    selected_scrim = match_plan.get("selected_scrim")
    if selected_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("week11_match_plan selected_scrim must list a Week-11 scrim choice")
    recommended_scrim = match_plan.get("recommended_scrim")
    if recommended_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("week11_match_plan recommended_scrim must list a Week-11 scrim choice")
    scrim_outcome = match_plan.get("scrim_outcome_id")
    if scrim_outcome not in WEEK11_SCRIM_OUTCOMES:
        raise ValueError("week11_match_plan scrim_outcome_id must list a Week-11 scrim outcome")
    selected = match_plan.get("selected_plan")
    if selected not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_match_plan selected_plan must list a Week-11 match plan")
    recommended = match_plan.get("recommended_plan")
    if recommended not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_match_plan recommended_plan must list a Week-11 match plan")
    available = match_plan.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK11_MATCH_PLAN_CHOICES for choice in available):
        raise ValueError("week11_match_plan available_choices must list Week-11 match plans")
    effects = match_plan.get("visible_effects")
    if not isinstance(effects, list):
        raise ValueError("week11_match_plan JSON must include visible_effects")
    constraints = match_plan.get("result_constraints")
    if not isinstance(constraints, list):
        raise ValueError("week11_match_plan JSON must include result_constraints")
    if match_plan.get("next_artifact") not in (None, WEEK11_MATCH_RESULT_FILENAME):
        raise ValueError("week11_match_plan next_artifact must be null or week11_match_result.json")
    plan_lock = match_plan.get("plan_lock")
    result_lock = match_plan.get("result_lock")
    if not isinstance(plan_lock, dict):
        raise ValueError("week11_match_plan JSON must include plan_lock")
    if not isinstance(result_lock, dict):
        raise ValueError("week11_match_plan JSON must include result_lock")
    recommendation_context = match_plan.get("recommendation_context")
    if not isinstance(recommendation_context, dict):
        raise ValueError("week11_match_plan JSON must include recommendation_context")
    seed_bucket = recommendation_context.get("seed_bucket")
    if not isinstance(seed_bucket, int):
        raise ValueError("week11_match_plan recommendation_context must include seed_bucket")
    return Week11MatchPlanLock(
        source_branch=str(match_plan.get("source_branch", "")),
        setup_branch=str(match_plan.get("setup_branch", "")),
        chosen_focus=str(match_plan.get("chosen_focus", "")),
        week10_outcome_id=str(match_plan.get("week10_outcome_id", "")),
        week10_result_tier=str(match_plan.get("week10_result_tier", "")),
        week10_result_grade=str(match_plan.get("week10_result_grade", "")),
        carry_forward_tag=str(match_plan.get("carry_forward_tag", "")),
        carry_forward_type=str(match_plan.get("carry_forward_type", "")),
        carry_forward_polarity=str(match_plan.get("carry_forward_polarity", "")),
        selected_setup=selected_setup,
        setup_outcome_id=setup_outcome,
        week11_pressure=str(match_plan.get("week11_pressure", "")),
        selected_prep=selected_prep,
        recommended_prep=recommended_prep,
        prep_outcome_id=prep_outcome,
        prep_lane=str(match_plan.get("prep_lane", "")),
        selected_scrim=selected_scrim,
        recommended_scrim=recommended_scrim,
        scrim_outcome_id=scrim_outcome,
        scrim_protocol=str(match_plan.get("scrim_protocol", "")),
        analyst_read_id=str(match_plan.get("analyst_read_id", "")),
        match_plan_seed=str(match_plan.get("match_plan_seed", "")),
        outcome_class=str(recommendation_context.get("outcome_class", "")),
        protocol_signal=str(recommendation_context.get("protocol_signal", "")),
        analyst_read_class=str(recommendation_context.get("analyst_read_class", "")),
        seed_bucket=seed_bucket,
        seeded_emphasis=str(recommendation_context.get("seeded_emphasis", "")),
        scrim_priority=str(match_plan.get("scrim_priority", "")),
        visible_effects=tuple(
            Week11SetupEffect(
                value=str(effect.get("id", "")),
                label=str(effect.get("label", "")),
                polarity=str(effect.get("polarity", "")),
            )
            for effect in effects
            if isinstance(effect, dict)
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


def render_week11_match_plan_json(lock: Week11MatchPlanLock) -> str:
    """Canonical JSON export for a locked Week-11 match plan."""
    payload = {
        "week11_match_plan": {
            "artifact_type": "week11_match_plan",
            "checkpoint": "week11_match_plan",
            "schema_version": 1,
            "source_artifact": WEEK11_SCRIM_FILENAME,
            "source_artifacts": {
                "week11_scrim": WEEK11_SCRIM_FILENAME,
            },
            "week": 11,
            "route": "/week11/match",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week10_outcome_id": lock.week10_outcome_id,
            "week10_result_tier": lock.week10_result_tier,
            "week10_result_grade": lock.week10_result_grade,
            "carry_forward_tag": lock.carry_forward_tag,
            "carry_forward_type": lock.carry_forward_type,
            "carry_forward_polarity": lock.carry_forward_polarity,
            "selected_setup": lock.selected_setup,
            "setup_outcome_id": lock.setup_outcome_id,
            "week11_pressure": lock.week11_pressure,
            "selected_prep": lock.selected_prep,
            "recommended_prep": lock.recommended_prep,
            "prep_outcome_id": lock.prep_outcome_id,
            "prep_lane": lock.prep_lane,
            "selected_scrim": lock.selected_scrim,
            "recommended_scrim": lock.recommended_scrim,
            "scrim_outcome_id": lock.scrim_outcome_id,
            "scrim_protocol": lock.scrim_protocol,
            "analyst_read_id": lock.analyst_read_id,
            "match_plan_seed": lock.match_plan_seed,
            "outcome_class": lock.outcome_class,
            "protocol_signal": lock.protocol_signal,
            "analyst_read_class": lock.analyst_read_class,
            "seed_bucket": lock.seed_bucket,
            "seeded_emphasis": lock.seeded_emphasis,
            "scrim_priority": lock.scrim_priority,
            "visible_effects": [
                {
                    "id": effect.value,
                    "label": effect.label,
                    "polarity": effect.polarity,
                }
                for effect in lock.visible_effects
            ],
            "recommendation_inputs": {
                "selected_scrim_id": lock.selected_scrim,
                "recommended_scrim_id": lock.recommended_scrim,
                "scrim_outcome_id": lock.scrim_outcome_id,
                "scrim_protocol": lock.scrim_protocol,
                "analyst_read_id": lock.analyst_read_id,
                "match_plan_seed": lock.match_plan_seed,
            },
            "recommendation_context": {
                "outcome_class": lock.outcome_class,
                "protocol_signal": lock.protocol_signal,
                "analyst_read_class": lock.analyst_read_class,
                "seed_bucket": lock.seed_bucket,
                "seeded_emphasis": lock.seeded_emphasis,
            },
            "recommendation_basis": lock.recommendation_basis,
            "recommendation_reason_id": lock.recommendation_basis,
            "recommended_plan": lock.recommended_plan,
            "recommended_plan_id": lock.recommended_plan,
            "recommended_match_plan_id": lock.recommended_plan,
            "available_choices": list(lock.available_choices),
            "available_match_plan_ids": list(lock.available_choices),
            "choice_order": list(lock.available_choices),
            "selected_plan": lock.selected_plan,
            "selected_plan_id": lock.selected_plan,
            "selected_match_plan_id": lock.selected_plan,
            "plan_outcome_id": lock.plan_outcome_id,
            "plan_label": lock.plan_label,
            "followed_recommendation": lock.followed_recommendation,
            "selected_is_recommended": lock.followed_recommendation,
            "commitment": lock.commitment,
            "risk_taken": lock.risk_taken,
            "thing_to_watch": lock.thing_to_watch,
            "match_risk": lock.match_risk,
            "result_constraints": list(lock.result_constraints),
            "recommendation_reason": lock.recommendation_reason,
            "plan_lock": {
                "status": "locked",
                "selected_at_route": "/week11/match",
                "cannot_change_after_write": True,
            },
            "result_lock": {
                "status": "not_resolved",
                "reason": "week11_match_plan_only",
                "next_artifact": WEEK11_MATCH_RESULT_FILENAME,
            },
            "match_plan_commitment": {
                "commitment": lock.commitment,
                "risk_taken": lock.risk_taken,
                "thing_to_watch": lock.thing_to_watch,
            },
            "next_hook": lock.next_hook,
            "stops_before": "week11_match_result",
            "next_artifact": WEEK11_MATCH_RESULT_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_WEEK11_RESULT_COPY: dict[Week11MatchOutcome, dict[str, str]] = {
    "read_trusted": {
        "headline": "The read becomes the match.",
        "recap": (
            "Overcast opened from the same signal the scrim confirmed. The opponent found contact, "
            "but the first answer arrived too late to move the team off its plan."
        ),
        "player_read": "Trusting the read worked because the analyst signal, scrim outcome, and match commitment all pointed at one lane.",
    },
    "read_overtrusted": {
        "headline": "The read gets one layer too comfortable.",
        "recap": (
            "The opening call found value, then stalled when the opponent changed the first answer. "
            "The plan trusted the scrim longer than the match state justified."
        ),
        "player_read": "The read was real, but the team treated it as a script instead of a live condition.",
    },
    "gap_attacked": {
        "headline": "The exposed gap gets punished.",
        "recap": (
            "The match plan turned the scrim's exposed branch into a clean timing window. "
            "Overcast did not need the whole tree; the first gap created enough leverage."
        ),
        "player_read": "Attacking the gap worked because the plan stayed narrow and did not chase every possible counter.",
    },
    "gap_chased": {
        "headline": "The gap turns into a chase.",
        "recap": (
            "The plan saw the right branch, but the room kept adding answers after first contact. "
            "By the second adjustment, the opponent had made the exposed gap expensive."
        ),
        "player_read": "The match plan needed one punish window; chasing the rest of the branch spent the advantage.",
    },
    "defaults_stabilized": {
        "headline": "The defaults hold the room together.",
        "recap": (
            "The match stayed tense, but the team refused to let first contact widen the call sheet. "
            "The stabilized defaults bought enough time for the second half to become playable."
        ),
        "player_read": "Stabilizing defaults worked because the scrim evidence had already warned that more layers would overload the room.",
    },
    "defaults_too_slow": {
        "headline": "The defaults arrive a beat slow.",
        "recap": (
            "The plan prevented a collapse, but it also left the first pressure window uncontested. "
            "The opponent won the map before Overcast's stable shape could turn into pressure."
        ),
        "player_read": "The defaults protected the room, but the match needed action sooner than the plan allowed.",
    },
}

_WEEK11_RESULT_VISIBLE_EFFECTS: dict[Week11MatchOutcome, tuple[Week11SetupEffect, ...]] = {
    "read_trusted": (
        Week11SetupEffect("read_converted", "Read converted", "positive"),
        Week11SetupEffect("counter_window_closed", "Counter window closed", "positive"),
        Week11SetupEffect("review_confirm_read", "Confirm read in review", "watch"),
    ),
    "read_overtrusted": (
        Week11SetupEffect("read_overheld", "Read overheld", "negative"),
        Week11SetupEffect("second_answer_late", "Second answer late", "negative"),
        Week11SetupEffect("review_live_condition", "Review live condition", "watch"),
    ),
    "gap_attacked": (
        Week11SetupEffect("gap_punished", "Gap punished", "positive"),
        Week11SetupEffect("branch_kept_narrow", "Branch kept narrow", "positive"),
        Week11SetupEffect("next_counter_scout", "Next counter scout", "watch"),
    ),
    "gap_chased": (
        Week11SetupEffect("branch_chased", "Branch chased", "negative"),
        Week11SetupEffect("punish_window_expired", "Punish window expired", "negative"),
        Week11SetupEffect("simplify_answer_tree", "Simplify answer tree", "watch"),
    ),
    "defaults_stabilized": (
        Week11SetupEffect("defaults_held", "Defaults held", "positive"),
        Week11SetupEffect("first_contact_narrow", "First contact narrow", "positive"),
        Week11SetupEffect("tempo_ceiling_watch", "Tempo ceiling watch", "watch"),
    ),
    "defaults_too_slow": (
        Week11SetupEffect("tempo_given", "Tempo given", "negative"),
        Week11SetupEffect("pressure_window_missed", "Pressure window missed", "negative"),
        Week11SetupEffect("review_action_trigger", "Review action trigger", "watch"),
    ),
}


def _week11_result_score(plan: Week11MatchPlanLock) -> int:
    score = 2 if plan.followed_recommendation else -1
    score += {"confirming": 2, "exposing": 1, "failing": -1}[plan.outcome_class]
    score += {"high_signal": 1, "medium_signal": 0, "low_signal": -1}[plan.protocol_signal]
    score += 1 if plan.match_risk == "low" else -1 if plan.match_risk == "high" else 0

    if plan.selected_plan == "trust_the_read":
        score += 2 if plan.analyst_read_class == "trust_read" else -1
        score += 1 if plan.protocol_signal == "high_signal" else -1
        score += 1 if plan.outcome_class == "confirming" else -1
    elif plan.selected_plan == "attack_the_gap":
        score += 2 if plan.analyst_read_class == "exploit_gap" else -1
        score += 1 if plan.outcome_class == "exposing" else 0
        score -= 1 if plan.protocol_signal == "low_signal" else 0
    else:
        score += 2 if plan.analyst_read_class == "stabilize_execution" else 0
        score += 1 if plan.protocol_signal == "low_signal" else 0
        score += 1 if plan.outcome_class == "failing" else -1
        score += 1 if plan.match_risk == "high" else 0
    return score


def _week11_match_succeeded(plan: Week11MatchPlanLock, score: int) -> bool:
    if plan.selected_plan == "trust_the_read":
        return score >= 5 and plan.protocol_signal != "low_signal"
    if plan.selected_plan == "attack_the_gap":
        return score >= 4 and plan.analyst_read_class == "exploit_gap"
    return score >= 3 and plan.match_risk != "low"


def _week11_outcome_id(plan: Week11MatchPlanLock, score: int) -> Week11MatchOutcome:
    succeeded = _week11_match_succeeded(plan, score)
    if plan.selected_plan == "trust_the_read":
        return "read_trusted" if succeeded else "read_overtrusted"
    if plan.selected_plan == "attack_the_gap":
        return "gap_attacked" if succeeded else "gap_chased"
    return "defaults_stabilized" if succeeded else "defaults_too_slow"


def _week11_scoreline(outcome_id: Week11MatchOutcome, score: int) -> tuple[Week11MatchResultTier, int, int]:
    if outcome_id in {"read_trusted", "gap_attacked", "defaults_stabilized"}:
        return ("win", 2, 0) if score >= 7 else ("win", 2, 1)
    return ("loss", 1, 2) if score >= 2 else ("loss", 0, 2)


def _week11_result_grade(score: int) -> str:
    if score >= 7:
        return "clean"
    if score >= 4:
        return "earned"
    if score >= 2:
        return "thin"
    return "punished"


def _week11_result_basis(plan: Week11MatchPlanLock, score: int) -> tuple[str, ...]:
    return (
        f"plan:{plan.selected_plan}",
        f"recommended:{plan.recommended_plan}",
        f"matched:{plan.followed_recommendation}",
        f"scrim:{plan.scrim_outcome_id}",
        f"outcome_class:{plan.outcome_class}",
        f"protocol_signal:{plan.protocol_signal}",
        f"analyst_read_class:{plan.analyst_read_class}",
        f"emphasis:{plan.seeded_emphasis}",
        f"risk:{plan.match_risk}",
        f"score:{score}",
    )


def resolve_week11_match_result(plan: Week11MatchPlanLock) -> Week11MatchResultLock:
    """Resolve a locked Week-11 match plan into a deterministic result artifact."""
    score = _week11_result_score(plan)
    outcome_id = _week11_outcome_id(plan, score)
    result_tier, team_maps, opponent_maps = _week11_scoreline(outcome_id, score)
    copy = _WEEK11_RESULT_COPY[outcome_id]
    causal_chain = (
        f"Week 11 pressure started as {plan.week11_pressure.replace('_', ' ')}.",
        f"Prep signal: {plan.prep_outcome_id.replace('_', ' ')}.",
        f"Scrim signal: {plan.scrim_outcome_id.replace('_', ' ')}.",
        f"Match commitment: {plan.commitment.replace('_', ' ')}.",
        f"Seeded emphasis: {plan.seeded_emphasis.replace('_', ' ')}.",
    )
    return Week11MatchResultLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week10_outcome_id=plan.week10_outcome_id,
        week10_result_tier=plan.week10_result_tier,
        week10_result_grade=plan.week10_result_grade,
        carry_forward_tag=plan.carry_forward_tag,
        carry_forward_type=plan.carry_forward_type,
        carry_forward_polarity=plan.carry_forward_polarity,
        selected_setup=plan.selected_setup,
        setup_outcome_id=plan.setup_outcome_id,
        week11_pressure=plan.week11_pressure,
        selected_prep=plan.selected_prep,
        recommended_prep=plan.recommended_prep,
        prep_outcome_id=plan.prep_outcome_id,
        prep_lane=plan.prep_lane,
        selected_scrim=plan.selected_scrim,
        recommended_scrim=plan.recommended_scrim,
        scrim_outcome_id=plan.scrim_outcome_id,
        scrim_protocol=plan.scrim_protocol,
        analyst_read_id=plan.analyst_read_id,
        match_plan_seed=plan.match_plan_seed,
        outcome_class=plan.outcome_class,
        protocol_signal=plan.protocol_signal,
        analyst_read_class=plan.analyst_read_class,
        seeded_emphasis=plan.seeded_emphasis,
        selected_plan=plan.selected_plan,
        recommended_plan=plan.recommended_plan,
        matched_recommendation=plan.followed_recommendation,
        commitment=plan.commitment,
        match_risk=plan.match_risk,
        outcome_id=outcome_id,
        result_tier=result_tier,
        team_maps=team_maps,
        opponent_maps=opponent_maps,
        scoreline=f"{team_maps}-{opponent_maps}",
        result_score=score,
        result_grade=_week11_result_grade(score),
        headline=copy["headline"],
        recap=copy["recap"],
        player_read=copy["player_read"],
        visible_effects=_WEEK11_RESULT_VISIBLE_EFFECTS[outcome_id],
        result_basis=_week11_result_basis(plan, score),
        causal_chain=causal_chain,
        next_hook="Week 11 post-match review can turn this result into the next carry-forward constraint.",
    )


def week11_match_result_from_json(text: str) -> Week11MatchResultLock:
    """Parse a written ``week11_match_result.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week11_match_result JSON is malformed") from exc
    result = data.get("week11_match_result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise ValueError("week11_match_result JSON must contain a week11_match_result object")
    selected_setup = result.get("selected_setup")
    if selected_setup not in WEEK11_SETUP_CHOICES:
        raise ValueError("week11_match_result selected_setup must list a Week-11 setup choice")
    setup_outcome = result.get("setup_outcome_id")
    if setup_outcome not in WEEK11_SETUP_OUTCOMES:
        raise ValueError("week11_match_result setup_outcome_id must list a Week-11 setup outcome")
    selected_prep = result.get("selected_prep")
    if selected_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_match_result selected_prep must list a Week-11 prep choice")
    recommended_prep = result.get("recommended_prep")
    if recommended_prep not in WEEK11_PREP_CHOICES:
        raise ValueError("week11_match_result recommended_prep must list a Week-11 prep choice")
    prep_outcome = result.get("prep_outcome_id")
    if prep_outcome not in WEEK11_PREP_OUTCOMES:
        raise ValueError("week11_match_result prep_outcome_id must list a Week-11 prep outcome")
    selected_scrim = result.get("selected_scrim")
    if selected_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("week11_match_result selected_scrim must list a Week-11 scrim choice")
    recommended_scrim = result.get("recommended_scrim")
    if recommended_scrim not in WEEK11_SCRIM_CHOICES:
        raise ValueError("week11_match_result recommended_scrim must list a Week-11 scrim choice")
    scrim_outcome = result.get("scrim_outcome_id")
    if scrim_outcome not in WEEK11_SCRIM_OUTCOMES:
        raise ValueError("week11_match_result scrim_outcome_id must list a Week-11 scrim outcome")
    selected_plan = result.get("selected_plan")
    if selected_plan not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_match_result selected_plan must list a Week-11 match plan")
    recommended_plan = result.get("recommended_plan")
    if recommended_plan not in WEEK11_MATCH_PLAN_CHOICES:
        raise ValueError("week11_match_result recommended_plan must list a Week-11 match plan")
    outcome_id = result.get("outcome_id")
    if outcome_id not in WEEK11_MATCH_OUTCOMES:
        raise ValueError("week11_match_result outcome_id must list a Week-11 match outcome")
    result_tier = result.get("result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week11_match_result result_tier must be win or loss")
    effects = result.get("visible_effects")
    basis = result.get("result_basis")
    causal_chain = result.get("causal_chain")
    if not isinstance(effects, list):
        raise ValueError("week11_match_result JSON must include visible_effects")
    if not isinstance(basis, list):
        raise ValueError("week11_match_result JSON must include result_basis")
    if not isinstance(causal_chain, list):
        raise ValueError("week11_match_result JSON must include causal_chain")
    if result.get("next_artifact") is not None:
        raise ValueError("week11_match_result next_artifact must be null")
    return Week11MatchResultLock(
        source_branch=str(result.get("source_branch", "")),
        setup_branch=str(result.get("setup_branch", "")),
        chosen_focus=str(result.get("chosen_focus", "")),
        week10_outcome_id=str(result.get("week10_outcome_id", "")),
        week10_result_tier=str(result.get("week10_result_tier", "")),
        week10_result_grade=str(result.get("week10_result_grade", "")),
        carry_forward_tag=str(result.get("carry_forward_tag", "")),
        carry_forward_type=str(result.get("carry_forward_type", "")),
        carry_forward_polarity=str(result.get("carry_forward_polarity", "")),
        selected_setup=selected_setup,
        setup_outcome_id=setup_outcome,
        week11_pressure=str(result.get("week11_pressure", "")),
        selected_prep=selected_prep,
        recommended_prep=recommended_prep,
        prep_outcome_id=prep_outcome,
        prep_lane=str(result.get("prep_lane", "")),
        selected_scrim=selected_scrim,
        recommended_scrim=recommended_scrim,
        scrim_outcome_id=scrim_outcome,
        scrim_protocol=str(result.get("scrim_protocol", "")),
        analyst_read_id=str(result.get("analyst_read_id", "")),
        match_plan_seed=str(result.get("match_plan_seed", "")),
        outcome_class=str(result.get("outcome_class", "")),
        protocol_signal=str(result.get("protocol_signal", "")),
        analyst_read_class=str(result.get("analyst_read_class", "")),
        seeded_emphasis=str(result.get("seeded_emphasis", "")),
        selected_plan=selected_plan,
        recommended_plan=recommended_plan,
        matched_recommendation=bool(result.get("matched_recommendation", selected_plan == recommended_plan)),
        commitment=str(result.get("commitment", "")),
        match_risk=str(result.get("match_risk", "")),
        outcome_id=outcome_id,
        result_tier=result_tier,  # type: ignore[arg-type]
        team_maps=int(result.get("team_maps", 0)),
        opponent_maps=int(result.get("opponent_maps", 0)),
        scoreline=str(result.get("scoreline", "")),
        result_score=int(result.get("result_score", 0)),
        result_grade=str(result.get("result_grade", "")),
        headline=str(result.get("headline", "")),
        recap=str(result.get("recap", "")),
        player_read=str(result.get("player_read", "")),
        visible_effects=tuple(
            Week11SetupEffect(
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


def render_week11_match_result_json(lock: Week11MatchResultLock) -> str:
    """Canonical JSON export for a resolved Week-11 match result."""
    payload = {
        "week11_match_result": {
            "artifact_type": "week11_match_result",
            "checkpoint": "week11_match_result",
            "schema_version": 1,
            "source_artifact": WEEK11_MATCH_PLAN_FILENAME,
            "source_artifacts": {
                "week11_match_plan": WEEK11_MATCH_PLAN_FILENAME,
            },
            "week": 11,
            "route": "/week11/match/result",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week10_outcome_id": lock.week10_outcome_id,
            "week10_result_tier": lock.week10_result_tier,
            "week10_result_grade": lock.week10_result_grade,
            "carry_forward_tag": lock.carry_forward_tag,
            "carry_forward_type": lock.carry_forward_type,
            "carry_forward_polarity": lock.carry_forward_polarity,
            "selected_setup": lock.selected_setup,
            "setup_outcome_id": lock.setup_outcome_id,
            "week11_pressure": lock.week11_pressure,
            "selected_prep": lock.selected_prep,
            "recommended_prep": lock.recommended_prep,
            "prep_outcome_id": lock.prep_outcome_id,
            "prep_lane": lock.prep_lane,
            "selected_scrim": lock.selected_scrim,
            "recommended_scrim": lock.recommended_scrim,
            "scrim_outcome_id": lock.scrim_outcome_id,
            "scrim_protocol": lock.scrim_protocol,
            "analyst_read_id": lock.analyst_read_id,
            "match_plan_seed": lock.match_plan_seed,
            "outcome_class": lock.outcome_class,
            "protocol_signal": lock.protocol_signal,
            "analyst_read_class": lock.analyst_read_class,
            "seeded_emphasis": lock.seeded_emphasis,
            "selected_plan": lock.selected_plan,
            "recommended_plan": lock.recommended_plan,
            "matched_recommendation": lock.matched_recommendation,
            "commitment": lock.commitment,
            "match_risk": lock.match_risk,
            "outcome_id": lock.outcome_id,
            "result_tier": lock.result_tier,
            "team_maps": lock.team_maps,
            "opponent_maps": lock.opponent_maps,
            "scoreline": lock.scoreline,
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
            "stops_before": "week11_post_match_review",
            "next_artifact": None,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
