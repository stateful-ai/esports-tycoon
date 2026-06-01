"""Deterministic Week-8 prep fork from Week-7 pressure artifacts.

This module consumes the run-local Week-7 setup/focus/pressure receipts and
produces one next manager-facing decision. It does not simulate Week 8.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from esports_tycoon.runner.week7 import (
    WEEK7_FOCI,
    Week7Focus,
    Week7FocusPayload,
    Week7SetupPayload,
)

Week8PrepChoice = Literal["patch_exposed_break", "double_down_identity"]

WEEK8_PREP_FILENAME = "week8_prep.json"
WEEK8_PREP_CHOICES: tuple[Week8PrepChoice, ...] = (
    "patch_exposed_break",
    "double_down_identity",
)


@dataclass(frozen=True)
class Week7PressurePayload:
    """The subset of ``week7_pressure.json`` consumed by Week-8 prep."""

    source_branch: str
    setup_branch: str
    hook_title: str
    chosen_focus: Week7Focus
    recommended_focus: Week7Focus
    matched_recommendation: bool
    outcome_id: str
    headline: str
    visible_consequence: str


@dataclass(frozen=True)
class Week8PrepOption:
    """One deterministic response to the Week-7 exposed problem."""

    value: Week8PrepChoice
    label: str
    payoff: str
    cost: str


@dataclass(frozen=True)
class Week8PrepPlan:
    """The read-only Week-8 agenda before a manager response is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    exposed_problem: str
    manager_problem: str
    spotlight_player: str
    options: tuple[Week8PrepOption, ...]


@dataclass(frozen=True)
class Week8PrepLock:
    """The deterministic artifact produced by locking Week-8 prep."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    exposed_problem: str
    manager_problem: str
    available_choices: tuple[Week8PrepChoice, ...]
    selected_choice: Week8PrepChoice
    choice_label: str
    spotlight_player: str
    review_room_trust_delta: int
    competitive_edge_delta: int
    volatility_delta: int
    week8_modifier: str
    gains: tuple[str, ...]
    costs: tuple[str, ...]
    next_hook: str


def pressure_payload_from_json(text: str) -> Week7PressurePayload:
    """Parse a ``week7_pressure.json`` export into the Week-8 prep contract."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week7_pressure JSON is malformed") from exc
    pressure = data.get("week7_pressure") if isinstance(data, dict) else None
    if not isinstance(pressure, dict):
        raise ValueError("week7_pressure JSON must contain a week7_pressure object")
    chosen = pressure.get("chosen_focus")
    recommended = pressure.get("recommended_focus")
    if chosen not in WEEK7_FOCI:
        raise ValueError("week7_pressure chosen_focus must be contain_fallout or prove_ceiling")
    if recommended not in WEEK7_FOCI:
        raise ValueError("week7_pressure recommended_focus must be contain_fallout or prove_ceiling")
    return Week7PressurePayload(
        source_branch=str(pressure.get("source_branch", "")),
        setup_branch=str(pressure.get("setup_branch", "")),
        hook_title=str(pressure.get("hook_title", "")),
        chosen_focus=chosen,
        recommended_focus=recommended,
        matched_recommendation=bool(pressure.get("matched_recommendation", chosen == recommended)),
        outcome_id=str(pressure.get("outcome_id", "")),
        headline=str(pressure.get("headline", "")),
        visible_consequence=str(pressure.get("visible_consequence", "")),
    )


def week8_prep_plan(
    setup: Week7SetupPayload,
    focus: Week7FocusPayload,
    pressure: Week7PressurePayload,
) -> Week8PrepPlan:
    """Build the deterministic Week-8 prep agenda from Week-7 artifacts."""
    if setup.hook_id != focus.hook_id or setup.hook_id != pressure.setup_branch:
        raise ValueError("week8 prep artifacts do not agree on setup branch")
    if focus.chosen_focus != pressure.chosen_focus:
        raise ValueError("week8 prep artifacts do not agree on chosen focus")

    if pressure.outcome_id == "heat_contained_scrappy_win":
        exposed = "low_ceiling_after_reset"
        manager_problem = (
            "The room cooled down, but the next opponent can test whether calmer still has teeth."
        )
        spotlight = "team"
        patch = Week8PrepOption(
            value="patch_exposed_break",
            label="Patch the low ceiling",
            payoff="Formalize the Vex/Pixie review protocol before Week 8 prep speeds up.",
            cost="Less time for the carry edge that wins loud maps.",
        )
        double = Week8PrepOption(
            value="double_down_identity",
            label="Double down on the steadier identity",
            payoff="Keep the room calm and make the clean structure the team brand.",
            cost="Week 8 may start without a signature punish look.",
        )
    elif pressure.outcome_id == "heat_ignored_highlight_loss":
        exposed = "vex_pixie_trust_fracture"
        manager_problem = (
            "The highlight proved ceiling, but Vex and Pixie now read every review as blame."
        )
        spotlight = "vex_pixie"
        patch = Week8PrepOption(
            value="patch_exposed_break",
            label="Patch the trust fracture",
            payoff="Lower Vex's load and rebuild the retake protocol around shared timing.",
            cost="The viral carry look gets fewer reps before Week 8.",
        )
        double = Week8PrepOption(
            value="double_down_identity",
            label="Double down on the Vex ceiling",
            payoff="Keep investing in the one look that scared the room.",
            cost="Pixie enters Week 8 with the same exposed fault line.",
        )
    elif pressure.outcome_id == "stability_unlocked_clean_2_0":
        exposed = "identity_needs_second_layer"
        manager_problem = (
            "The clean win proved the repair, but Week 8 needs a second layer before teams copy the tape."
        )
        spotlight = "pixie"
        patch = Week8PrepOption(
            value="patch_exposed_break",
            label="Patch the second layer",
            payoff="Give Pixie's repaired timing a fallback call before opponents crowd the default.",
            cost="The team spends less time pressing its new confidence.",
        )
        double = Week8PrepOption(
            value="double_down_identity",
            label="Double down on the clean ceiling",
            payoff="Keep pressure on the exact look that finally produced clip value.",
            cost="The plan may become predictable if Week 8 opens slow.",
        )
    elif pressure.outcome_id == "stability_overmanaged_flat_win":
        exposed = "overmanaged_low_threat"
        manager_problem = (
            "The room stayed calm, but the tape gives opponents permission to crowd the default."
        )
        spotlight = "team"
        patch = Week8PrepOption(
            value="patch_exposed_break",
            label="Patch the low-threat default",
            payoff="Add one explicit punish call so calm reps do not become passive reps.",
            cost="Less review time goes to preserving the repaired room.",
        )
        double = Week8PrepOption(
            value="double_down_identity",
            label="Double down on stability",
            payoff="Protect the repaired structure for one more block.",
            cost="Week 8 inherits the same low-clip-value question.",
        )
    else:
        raise ValueError(f"unsupported week7 pressure outcome: {pressure.outcome_id!r}")

    return Week8PrepPlan(
        source_branch=setup.source_branch,
        setup_branch=setup.hook_id,
        chosen_focus=focus.chosen_focus,
        source_pressure_outcome=pressure.outcome_id,
        pressure_headline=pressure.headline,
        exposed_problem=exposed,
        manager_problem=manager_problem,
        spotlight_player=spotlight,
        options=(patch, double),
    )


def resolve_week8_prep(plan: Week8PrepPlan, selected_choice: str) -> Week8PrepLock:
    """Resolve one Week-8 prep choice into a deterministic artifact."""
    if selected_choice not in WEEK8_PREP_CHOICES:
        raise ValueError("selected_choice must be patch_exposed_break or double_down_identity")
    choice: Week8PrepChoice = selected_choice  # type: ignore[assignment]
    selected = next(option for option in plan.options if option.value == choice)

    if choice == "patch_exposed_break":
        return Week8PrepLock(
            source_branch=plan.source_branch,
            setup_branch=plan.setup_branch,
            chosen_focus=plan.chosen_focus,
            source_pressure_outcome=plan.source_pressure_outcome,
            pressure_headline=plan.pressure_headline,
            exposed_problem=plan.exposed_problem,
            manager_problem=plan.manager_problem,
            available_choices=WEEK8_PREP_CHOICES,
            selected_choice=choice,
            choice_label=selected.label,
            spotlight_player=plan.spotlight_player,
            review_room_trust_delta=1,
            competitive_edge_delta=-1,
            volatility_delta=-1,
            week8_modifier="lower_volatility",
            gains=("role clarity", "repeat-failure protection"),
            costs=("slower ceiling growth",),
            next_hook=f"Week 8 opens by patching {plan.exposed_problem}.",
        )
    return Week8PrepLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        source_pressure_outcome=plan.source_pressure_outcome,
        pressure_headline=plan.pressure_headline,
        exposed_problem=plan.exposed_problem,
        manager_problem=plan.manager_problem,
        available_choices=WEEK8_PREP_CHOICES,
        selected_choice=choice,
        choice_label=selected.label,
        spotlight_player=plan.spotlight_player,
        review_room_trust_delta=-1,
        competitive_edge_delta=1,
        volatility_delta=1,
        week8_modifier="higher_ceiling_higher_tilt",
        gains=("competitive edge", "identity speed"),
        costs=("review-room patience",),
        next_hook=f"Week 8 opens by doubling down through {plan.exposed_problem}.",
    )


def week8_prep_from_json(text: str) -> Week8PrepLock:
    """Parse a written ``week8_prep.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week8_prep JSON is malformed") from exc
    prep = data.get("week8_prep") if isinstance(data, dict) else None
    if not isinstance(prep, dict):
        raise ValueError("week8_prep JSON must contain a week8_prep object")
    selected = prep.get("selected_choice")
    if selected not in WEEK8_PREP_CHOICES:
        raise ValueError("week8_prep selected_choice must be patch_exposed_break or double_down_identity")
    deltas = prep.get("deltas")
    if not isinstance(deltas, dict):
        raise ValueError("week8_prep JSON must include deltas")
    tradeoff = prep.get("tradeoff")
    if not isinstance(tradeoff, dict):
        raise ValueError("week8_prep JSON must include tradeoff")
    available = prep.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK8_PREP_CHOICES for choice in available):
        raise ValueError("week8_prep available_choices must list Week-8 prep choices")
    focus = prep.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week8_prep chosen_focus must be contain_fallout or prove_ceiling")
    return Week8PrepLock(
        source_branch=str(prep.get("source_branch", "")),
        setup_branch=str(prep.get("setup_branch", "")),
        chosen_focus=focus,
        source_pressure_outcome=str(prep.get("source_pressure_outcome", "")),
        pressure_headline=str(prep.get("pressure_headline", "")),
        exposed_problem=str(prep.get("exposed_problem", "")),
        manager_problem=str(prep.get("manager_problem", "")),
        available_choices=tuple(available),  # type: ignore[arg-type]
        selected_choice=selected,
        choice_label=str(prep.get("choice_label", "")),
        spotlight_player=str(prep.get("spotlight_player", "")),
        review_room_trust_delta=int(deltas.get("review_room_trust", 0)),
        competitive_edge_delta=int(deltas.get("competitive_edge", 0)),
        volatility_delta=int(deltas.get("volatility", 0)),
        week8_modifier=str(prep.get("week8_modifier", "")),
        gains=tuple(str(item) for item in tradeoff.get("gains", ())),
        costs=tuple(str(item) for item in tradeoff.get("costs", ())),
        next_hook=str(prep.get("next_hook", "")),
    )


def render_week8_prep_json(lock: Week8PrepLock) -> str:
    """Canonical JSON export for a locked Week-8 prep response."""
    payload = {
        "week8_prep": {
            "artifact_type": "week8_prep",
            "schema_version": 1,
            "source_artifacts": {
                "week7_setup": "week7_setup.json",
                "week7_focus": "week7_focus.json",
                "week7_pressure": "week7_pressure.json",
            },
            "week": 8,
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "source_pressure_outcome": lock.source_pressure_outcome,
            "pressure_headline": lock.pressure_headline,
            "exposed_problem": lock.exposed_problem,
            "manager_problem": lock.manager_problem,
            "available_choices": list(lock.available_choices),
            "selected_choice": lock.selected_choice,
            "choice_label": lock.choice_label,
            "spotlight_player": lock.spotlight_player,
            "deltas": {
                "review_room_trust": lock.review_room_trust_delta,
                "competitive_edge": lock.competitive_edge_delta,
                "volatility": lock.volatility_delta,
            },
            "week8_modifier": lock.week8_modifier,
            "tradeoff": {
                "gains": list(lock.gains),
                "costs": list(lock.costs),
            },
            "next_hook": lock.next_hook,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
