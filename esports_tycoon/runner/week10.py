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

WEEK10_PREP_FILENAME = "week10_prep.json"
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
