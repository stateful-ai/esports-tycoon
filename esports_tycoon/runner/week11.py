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

WEEK11_SETUP_FILENAME = "week11_setup.json"
WEEK11_PREP_FILENAME = "week11_prep.json"
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
    if prep.get("next_artifact") is not None:
        raise ValueError("week11_prep next_artifact must be null")
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
            "next_artifact": None,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
