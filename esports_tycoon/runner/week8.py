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
Week8ScrimChoice = Literal["play_to_prep", "cover_the_crack"]

WEEK8_PREP_FILENAME = "week8_prep.json"
WEEK8_SCRIM_FILENAME = "week8_scrim.json"
WEEK8_PREP_CHOICES: tuple[Week8PrepChoice, ...] = (
    "patch_exposed_break",
    "double_down_identity",
)
WEEK8_SCRIM_CHOICES: tuple[Week8ScrimChoice, ...] = (
    "play_to_prep",
    "cover_the_crack",
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


@dataclass(frozen=True)
class Week8ScrimOption:
    """One tactical call available in the Week-8 scrim setup."""

    value: Week8ScrimChoice
    label: str
    payoff: str
    cost: str


@dataclass(frozen=True)
class Week8ScrimPlan:
    """The read-only scrim setup caused by the Week-8 prep response."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    prep_choice: Week8PrepChoice
    prep_modifier: str
    exposed_problem: str
    spotlight_player: str
    opponent_read: str
    scrim_modifier: str
    scrim_opening_state: str
    setup_headline: str
    setup_body: str
    reaction: str
    options: tuple[Week8ScrimOption, ...]


@dataclass(frozen=True)
class Week8ScrimLock:
    """The deterministic artifact produced by locking the Week-8 scrim call."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    prep_choice: Week8PrepChoice
    prep_modifier: str
    exposed_problem: str
    spotlight_player: str
    opponent_read: str
    scrim_modifier: str
    scrim_opening_state: str
    setup_headline: str
    available_choices: tuple[Week8ScrimChoice, ...]
    selected_call: Week8ScrimChoice
    call_label: str
    readiness_delta: int
    tempo_delta: int
    tilt_risk_delta: int
    visible_consequence: str
    next_match_hook: str


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


def _scrim_reaction(spotlight_player: str, exposed_problem: str) -> str:
    if spotlight_player == "vex_pixie":
        return "Rook keeps the review short; Vex and Pixie both know the first miss will get clipped."
    if spotlight_player == "pixie":
        return "Pixie wants the fallback named before the server starts."
    if exposed_problem == "low_ceiling_after_reset":
        return "Vex buys the calmer block, but wants proof it can still win opening duels."
    return "The room likes the clarity; nobody wants it to become passive tape."


def week8_scrim_plan(
    setup: Week7SetupPayload,
    focus: Week7FocusPayload,
    pressure: Week7PressurePayload,
    prep: Week8PrepLock,
) -> Week8ScrimPlan:
    """Build the deterministic Week-8 scrim setup from prior receipts."""
    if setup.hook_id != focus.hook_id or setup.hook_id != pressure.setup_branch:
        raise ValueError("week8 scrim artifacts do not agree on setup branch")
    if prep.setup_branch != setup.hook_id:
        raise ValueError("week8 scrim prep does not match setup branch")
    if focus.chosen_focus != pressure.chosen_focus or prep.chosen_focus != focus.chosen_focus:
        raise ValueError("week8 scrim artifacts do not agree on chosen focus")
    if prep.source_pressure_outcome != pressure.outcome_id:
        raise ValueError("week8 scrim prep does not match pressure outcome")

    if prep.selected_choice == "patch_exposed_break":
        scrim_modifier = "trust_buffer"
        opening_state = "controlled_reset"
        headline = "Scrim block: patch under pressure"
        body = (
            f"The first map starts around {prep.exposed_problem}: tighter comms, "
            "shorter review loops, and less room for solo correction."
        )
        opponent_read = (
            f"{pressure.headline}: opponents will test whether the patch slows the first hit."
        )
        options = (
            Week8ScrimOption(
                value="play_to_prep",
                label="Run the patched protocol",
                payoff="Protect the repair through first contact.",
                cost="Lower tempo if the opponent sits deep.",
            ),
            Week8ScrimOption(
                value="cover_the_crack",
                label="Pressure with a leash",
                payoff="Stress-test the patch before the match week.",
                cost="More risk of reopening the exposed problem.",
            ),
        )
    else:
        scrim_modifier = "tempo_spike"
        opening_state = "volatile_opener"
        headline = "Scrim block: identity at speed"
        body = (
            f"The first map starts by pressing through {prep.exposed_problem}: "
            "faster calls, louder proof, and less patience for hesitation."
        )
        opponent_read = (
            f"{pressure.headline}: opponents will bait the identity and wait for the room to overheat."
        )
        options = (
            Week8ScrimOption(
                value="play_to_prep",
                label="Force the identity",
                payoff="Put the chosen Week-8 posture under immediate tempo.",
                cost="Tilt risk rises if the opener misses.",
            ),
            Week8ScrimOption(
                value="cover_the_crack",
                label="Split the opening reps",
                payoff="Keep the identity sharp without overloading the same fault line.",
                cost="The scrim loses some of the edge the prep bought.",
            ),
        )

    return Week8ScrimPlan(
        source_branch=setup.source_branch,
        setup_branch=setup.hook_id,
        chosen_focus=focus.chosen_focus,
        source_pressure_outcome=pressure.outcome_id,
        pressure_headline=pressure.headline,
        prep_choice=prep.selected_choice,
        prep_modifier=prep.week8_modifier,
        exposed_problem=prep.exposed_problem,
        spotlight_player=prep.spotlight_player,
        opponent_read=opponent_read,
        scrim_modifier=scrim_modifier,
        scrim_opening_state=opening_state,
        setup_headline=headline,
        setup_body=body,
        reaction=_scrim_reaction(prep.spotlight_player, prep.exposed_problem),
        options=options,
    )


def resolve_week8_scrim(plan: Week8ScrimPlan, selected_call: str) -> Week8ScrimLock:
    """Resolve one Week-8 scrim setup call into a deterministic artifact."""
    if selected_call not in WEEK8_SCRIM_CHOICES:
        raise ValueError("selected_call must be play_to_prep or cover_the_crack")
    call: Week8ScrimChoice = selected_call  # type: ignore[assignment]
    selected = next(option for option in plan.options if option.value == call)

    if plan.prep_choice == "patch_exposed_break" and call == "play_to_prep":
        readiness, tempo, tilt = 2, -1, -2
        consequence = "patched_protocol_held"
        hook = "Week 8 match setup inherits a calmer first-contact script."
    elif plan.prep_choice == "patch_exposed_break":
        readiness, tempo, tilt = 1, 1, -1
        consequence = "patch_tested_early"
        hook = "Week 8 match setup inherits a controlled pressure check."
    elif call == "play_to_prep":
        readiness, tempo, tilt = 0, 2, 2
        consequence = "identity_forced"
        hook = "Week 8 match setup inherits a faster opener with less patience."
    else:
        readiness, tempo, tilt = 1, 1, 0
        consequence = "identity_split_reps"
        hook = "Week 8 match setup inherits a split-rep opener that protects the room."

    return Week8ScrimLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        source_pressure_outcome=plan.source_pressure_outcome,
        pressure_headline=plan.pressure_headline,
        prep_choice=plan.prep_choice,
        prep_modifier=plan.prep_modifier,
        exposed_problem=plan.exposed_problem,
        spotlight_player=plan.spotlight_player,
        opponent_read=plan.opponent_read,
        scrim_modifier=plan.scrim_modifier,
        scrim_opening_state=plan.scrim_opening_state,
        setup_headline=plan.setup_headline,
        available_choices=WEEK8_SCRIM_CHOICES,
        selected_call=call,
        call_label=selected.label,
        readiness_delta=readiness,
        tempo_delta=tempo,
        tilt_risk_delta=tilt,
        visible_consequence=consequence,
        next_match_hook=hook,
    )


def week8_scrim_from_json(text: str) -> Week8ScrimLock:
    """Parse a written ``week8_scrim.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week8_scrim JSON is malformed") from exc
    scrim = data.get("week8_scrim") if isinstance(data, dict) else None
    if not isinstance(scrim, dict):
        raise ValueError("week8_scrim JSON must contain a week8_scrim object")
    call = scrim.get("selected_call")
    if call not in WEEK8_SCRIM_CHOICES:
        raise ValueError("week8_scrim selected_call must be play_to_prep or cover_the_crack")
    prep_choice = scrim.get("prep_choice")
    if prep_choice not in WEEK8_PREP_CHOICES:
        raise ValueError("week8_scrim prep_choice must be patch_exposed_break or double_down_identity")
    available = scrim.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK8_SCRIM_CHOICES for choice in available):
        raise ValueError("week8_scrim available_choices must list Week-8 scrim calls")
    focus = scrim.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week8_scrim chosen_focus must be contain_fallout or prove_ceiling")
    modifiers = scrim.get("modifiers")
    if not isinstance(modifiers, dict):
        raise ValueError("week8_scrim JSON must include modifiers")
    return Week8ScrimLock(
        source_branch=str(scrim.get("source_branch", "")),
        setup_branch=str(scrim.get("setup_branch", "")),
        chosen_focus=focus,
        source_pressure_outcome=str(scrim.get("source_pressure_outcome", "")),
        pressure_headline=str(scrim.get("pressure_headline", "")),
        prep_choice=prep_choice,
        prep_modifier=str(scrim.get("prep_modifier", "")),
        exposed_problem=str(scrim.get("exposed_problem", "")),
        spotlight_player=str(scrim.get("spotlight_player", "")),
        opponent_read=str(scrim.get("opponent_read", "")),
        scrim_modifier=str(scrim.get("scrim_modifier", "")),
        scrim_opening_state=str(scrim.get("scrim_opening_state", "")),
        setup_headline=str(scrim.get("setup_headline", "")),
        available_choices=tuple(available),  # type: ignore[arg-type]
        selected_call=call,
        call_label=str(scrim.get("call_label", "")),
        readiness_delta=int(modifiers.get("readiness", 0)),
        tempo_delta=int(modifiers.get("tempo", 0)),
        tilt_risk_delta=int(modifiers.get("tilt_risk", 0)),
        visible_consequence=str(scrim.get("visible_consequence", "")),
        next_match_hook=str(scrim.get("next_match_hook", "")),
    )


def render_week8_scrim_json(lock: Week8ScrimLock) -> str:
    """Canonical JSON export for a locked Week-8 scrim setup."""
    payload = {
        "week8_scrim": {
            "artifact_type": "week8_scrim",
            "schema_version": 1,
            "source_artifacts": {
                "week7_setup": "week7_setup.json",
                "week7_focus": "week7_focus.json",
                "week7_pressure": "week7_pressure.json",
                "week8_prep": "week8_prep.json",
            },
            "week": 8,
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "source_pressure_outcome": lock.source_pressure_outcome,
            "pressure_headline": lock.pressure_headline,
            "prep_choice": lock.prep_choice,
            "prep_modifier": lock.prep_modifier,
            "exposed_problem": lock.exposed_problem,
            "spotlight_player": lock.spotlight_player,
            "opponent_read": lock.opponent_read,
            "scrim_modifier": lock.scrim_modifier,
            "scrim_opening_state": lock.scrim_opening_state,
            "setup_headline": lock.setup_headline,
            "available_choices": list(lock.available_choices),
            "selected_call": lock.selected_call,
            "call_label": lock.call_label,
            "modifiers": {
                "readiness": lock.readiness_delta,
                "tempo": lock.tempo_delta,
                "tilt_risk": lock.tilt_risk_delta,
            },
            "visible_consequence": lock.visible_consequence,
            "next_match_hook": lock.next_match_hook,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
