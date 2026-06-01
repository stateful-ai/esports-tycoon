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

WEEK10_PREP_FILENAME = "week10_prep.json"
WEEK10_SCRIM_FILENAME = "week10_scrim.json"
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
