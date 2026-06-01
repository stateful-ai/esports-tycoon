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
Week8MatchPlanChoice = Literal["patch_weakness", "lean_into_edge"]
Week8MatchOutcome = Literal["clean_win", "messy_win", "loss_with_signal"]
Week8MatchResult = Literal["win", "loss"]

WEEK8_PREP_FILENAME = "week8_prep.json"
WEEK8_SCRIM_FILENAME = "week8_scrim.json"
WEEK8_MATCH_PLAN_FILENAME = "week8_match_plan.json"
WEEK8_MATCH_RESULT_FILENAME = "week8_match_result.json"
WEEK8_PREP_CHOICES: tuple[Week8PrepChoice, ...] = (
    "patch_exposed_break",
    "double_down_identity",
)
WEEK8_SCRIM_CHOICES: tuple[Week8ScrimChoice, ...] = (
    "play_to_prep",
    "cover_the_crack",
)
WEEK8_MATCH_PLAN_CHOICES: tuple[Week8MatchPlanChoice, ...] = (
    "patch_weakness",
    "lean_into_edge",
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


@dataclass(frozen=True)
class Week8MatchOption:
    """One match-week plan available after the Week-8 scrim setup."""

    value: Week8MatchPlanChoice
    label: str
    payoff: str
    cost: str


@dataclass(frozen=True)
class Week8MatchPreview:
    """The read-only Week-8 match preview caused by the scrim artifact."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    prep_choice: Week8PrepChoice
    scrim_call: Week8ScrimChoice
    exposed_problem: str
    spotlight_player: str
    scrim_signal: str
    opponent_attack: str
    opponent_read: str
    team_edge: str
    match_risk: str
    recommended_plan: Week8MatchPlanChoice
    recommendation_reason: str
    options: tuple[Week8MatchOption, ...]


@dataclass(frozen=True)
class Week8MatchPlanLock:
    """The deterministic artifact produced by locking the Week-8 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    prep_choice: Week8PrepChoice
    scrim_call: Week8ScrimChoice
    exposed_problem: str
    spotlight_player: str
    scrim_signal: str
    opponent_attack: str
    team_edge: str
    match_risk: str
    recommended_plan: Week8MatchPlanChoice
    available_choices: tuple[Week8MatchPlanChoice, ...]
    selected_plan: Week8MatchPlanChoice
    plan_label: str
    readiness_delta: int
    edge_delta: int
    risk_delta: int
    match_pressure: str
    next_problem: str
    next_hook: str


@dataclass(frozen=True)
class Week8MatchResultLock:
    """The deterministic artifact produced by resolving the Week-8 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    source_pressure_outcome: str
    pressure_headline: str
    prep_choice: Week8PrepChoice
    scrim_call: Week8ScrimChoice
    selected_plan: Week8MatchPlanChoice
    recommended_plan: Week8MatchPlanChoice
    matched_recommendation: bool
    match_risk: str
    opponent_attack: str
    team_edge: str
    match_pressure: str
    source_next_problem: str
    outcome_id: Week8MatchOutcome
    match_result: Week8MatchResult
    scoreline: str
    plan_effect: str
    public_read: str
    pressure: str
    consequence_axis: str
    consequence_delta: int
    week9_hook: str


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


_OPPONENT_ATTACKS = {
    "vex_pixie_trust_fracture": (
        "retake_blame_pressure",
        "Apex Foundry will force the first retake and make Vex/Pixie assign blame in public.",
    ),
    "low_ceiling_after_reset": (
        "slow_opener_challenge",
        "Apex Foundry can sit deep early and ask whether the calmer opener has a punish.",
    ),
    "identity_needs_second_layer": (
        "default_crowd",
        "Apex Foundry can crowd the repaired default and test whether the second call exists.",
    ),
    "overmanaged_low_threat": (
        "passive_default_trap",
        "Apex Foundry can give space, wait out the default, and make calm reps look harmless.",
    ),
}

_TEAM_EDGES = {
    "trust_buffer": "cleaner_first_contact",
    "tempo_spike": "explosive_opening_tempo",
}


def week8_match_preview(
    setup: Week7SetupPayload,
    focus: Week7FocusPayload,
    pressure: Week7PressurePayload,
    prep: Week8PrepLock,
    scrim: Week8ScrimLock,
) -> Week8MatchPreview:
    """Build the deterministic Week-8 match preview from prior receipts."""
    if setup.hook_id != focus.hook_id or setup.hook_id != pressure.setup_branch:
        raise ValueError("week8 match artifacts do not agree on setup branch")
    if prep.setup_branch != setup.hook_id or scrim.setup_branch != setup.hook_id:
        raise ValueError("week8 match artifacts do not agree on setup branch")
    if focus.chosen_focus != pressure.chosen_focus or prep.chosen_focus != focus.chosen_focus:
        raise ValueError("week8 match artifacts do not agree on chosen focus")
    if scrim.chosen_focus != focus.chosen_focus:
        raise ValueError("week8 match scrim does not match chosen focus")
    if prep.source_pressure_outcome != pressure.outcome_id:
        raise ValueError("week8 match prep does not match pressure outcome")
    if scrim.source_pressure_outcome != pressure.outcome_id:
        raise ValueError("week8 match scrim does not match pressure outcome")
    if scrim.prep_choice != prep.selected_choice:
        raise ValueError("week8 match scrim does not match prep choice")

    opponent_attack, opponent_read = _OPPONENT_ATTACKS.get(
        scrim.exposed_problem,
        (
            "unknown_attack",
            f"Apex Foundry will test the unresolved {scrim.exposed_problem} problem first.",
        ),
    )
    team_edge = _TEAM_EDGES.get(scrim.scrim_modifier, "unclear_match_edge")

    if scrim.tilt_risk_delta >= 2:
        match_risk = "high"
    elif scrim.tilt_risk_delta <= -1 and scrim.readiness_delta >= 2:
        match_risk = "low"
    else:
        match_risk = "medium"

    if match_risk == "high" or scrim.visible_consequence in {
        "patch_tested_early",
        "identity_forced",
    }:
        recommended: Week8MatchPlanChoice = "patch_weakness"
        recommendation_reason = "The scrim exposed the same problem the opponent can attack first."
    else:
        recommended = "lean_into_edge"
        recommendation_reason = "The scrim left enough control to preserve the strongest match edge."

    options = (
        Week8MatchOption(
            value="patch_weakness",
            label="Patch the weakness",
            payoff=f"Protect {scrim.exposed_problem} against {opponent_attack}.",
            cost=f"Spend less time sharpening {team_edge}.",
        ),
        Week8MatchOption(
            value="lean_into_edge",
            label="Lean into the edge",
            payoff=f"Center match prep on {team_edge}.",
            cost=f"Carry {scrim.exposed_problem} into the opponent's first test.",
        ),
    )

    return Week8MatchPreview(
        source_branch=setup.source_branch,
        setup_branch=setup.hook_id,
        chosen_focus=focus.chosen_focus,
        source_pressure_outcome=pressure.outcome_id,
        pressure_headline=pressure.headline,
        prep_choice=prep.selected_choice,
        scrim_call=scrim.selected_call,
        exposed_problem=scrim.exposed_problem,
        spotlight_player=scrim.spotlight_player,
        scrim_signal=scrim.visible_consequence,
        opponent_attack=opponent_attack,
        opponent_read=opponent_read,
        team_edge=team_edge,
        match_risk=match_risk,
        recommended_plan=recommended,
        recommendation_reason=recommendation_reason,
        options=options,
    )


def resolve_week8_match_plan(
    preview: Week8MatchPreview,
    selected_plan: str,
) -> Week8MatchPlanLock:
    """Resolve one Week-8 match plan into a deterministic artifact."""
    if selected_plan not in WEEK8_MATCH_PLAN_CHOICES:
        raise ValueError("selected_plan must be patch_weakness or lean_into_edge")
    plan: Week8MatchPlanChoice = selected_plan  # type: ignore[assignment]
    selected = next(option for option in preview.options if option.value == plan)

    if plan == "patch_weakness":
        readiness_delta, edge_delta, risk_delta = 1, -1, -1
        match_pressure = "protected_opener"
        next_problem = f"{preview.exposed_problem}_managed_but_edge_dulled"
        next_hook = "Week 8 match can now test whether the protected opener still wins first contact."
    else:
        readiness_delta, edge_delta, risk_delta = 0, 1, 1
        match_pressure = "edge_first_opener"
        next_problem = f"{preview.exposed_problem}_carried_into_match"
        next_hook = "Week 8 match can now test whether the edge outruns the opponent's first attack."

    return Week8MatchPlanLock(
        source_branch=preview.source_branch,
        setup_branch=preview.setup_branch,
        chosen_focus=preview.chosen_focus,
        source_pressure_outcome=preview.source_pressure_outcome,
        pressure_headline=preview.pressure_headline,
        prep_choice=preview.prep_choice,
        scrim_call=preview.scrim_call,
        exposed_problem=preview.exposed_problem,
        spotlight_player=preview.spotlight_player,
        scrim_signal=preview.scrim_signal,
        opponent_attack=preview.opponent_attack,
        team_edge=preview.team_edge,
        match_risk=preview.match_risk,
        recommended_plan=preview.recommended_plan,
        available_choices=WEEK8_MATCH_PLAN_CHOICES,
        selected_plan=plan,
        plan_label=selected.label,
        readiness_delta=readiness_delta,
        edge_delta=edge_delta,
        risk_delta=risk_delta,
        match_pressure=match_pressure,
        next_problem=next_problem,
        next_hook=next_hook,
    )


def week8_match_plan_from_json(text: str) -> Week8MatchPlanLock:
    """Parse a written ``week8_match_plan.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week8_match_plan JSON is malformed") from exc
    match_plan = data.get("week8_match_plan") if isinstance(data, dict) else None
    if not isinstance(match_plan, dict):
        raise ValueError("week8_match_plan JSON must contain a week8_match_plan object")
    selected = match_plan.get("selected_plan")
    if selected not in WEEK8_MATCH_PLAN_CHOICES:
        raise ValueError("week8_match_plan selected_plan must be patch_weakness or lean_into_edge")
    recommended = match_plan.get("recommended_plan")
    if recommended not in WEEK8_MATCH_PLAN_CHOICES:
        raise ValueError("week8_match_plan recommended_plan must be patch_weakness or lean_into_edge")
    prep_choice = match_plan.get("prep_choice")
    if prep_choice not in WEEK8_PREP_CHOICES:
        raise ValueError("week8_match_plan prep_choice must be patch_exposed_break or double_down_identity")
    scrim_call = match_plan.get("scrim_call")
    if scrim_call not in WEEK8_SCRIM_CHOICES:
        raise ValueError("week8_match_plan scrim_call must be play_to_prep or cover_the_crack")
    available = match_plan.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK8_MATCH_PLAN_CHOICES for choice in available):
        raise ValueError("week8_match_plan available_choices must list Week-8 match plan choices")
    focus = match_plan.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week8_match_plan chosen_focus must be contain_fallout or prove_ceiling")
    deltas = match_plan.get("deltas")
    if not isinstance(deltas, dict):
        raise ValueError("week8_match_plan JSON must include deltas")
    return Week8MatchPlanLock(
        source_branch=str(match_plan.get("source_branch", "")),
        setup_branch=str(match_plan.get("setup_branch", "")),
        chosen_focus=focus,
        source_pressure_outcome=str(match_plan.get("source_pressure_outcome", "")),
        pressure_headline=str(match_plan.get("pressure_headline", "")),
        prep_choice=prep_choice,
        scrim_call=scrim_call,
        exposed_problem=str(match_plan.get("exposed_problem", "")),
        spotlight_player=str(match_plan.get("spotlight_player", "")),
        scrim_signal=str(match_plan.get("scrim_signal", "")),
        opponent_attack=str(match_plan.get("opponent_attack", "")),
        team_edge=str(match_plan.get("team_edge", "")),
        match_risk=str(match_plan.get("match_risk", "")),
        recommended_plan=recommended,
        available_choices=tuple(available),  # type: ignore[arg-type]
        selected_plan=selected,
        plan_label=str(match_plan.get("plan_label", "")),
        readiness_delta=int(deltas.get("readiness", 0)),
        edge_delta=int(deltas.get("edge", 0)),
        risk_delta=int(deltas.get("risk", 0)),
        match_pressure=str(match_plan.get("match_pressure", "")),
        next_problem=str(match_plan.get("next_problem", "")),
        next_hook=str(match_plan.get("next_hook", "")),
    )


def render_week8_match_plan_json(lock: Week8MatchPlanLock) -> str:
    """Canonical JSON export for a locked Week-8 match plan."""
    payload = {
        "week8_match_plan": {
            "artifact_type": "week8_match_plan",
            "schema_version": 1,
            "source_artifacts": {
                "week7_setup": "week7_setup.json",
                "week7_focus": "week7_focus.json",
                "week7_pressure": "week7_pressure.json",
                "week8_prep": "week8_prep.json",
                "week8_scrim": "week8_scrim.json",
            },
            "week": 8,
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "source_pressure_outcome": lock.source_pressure_outcome,
            "pressure_headline": lock.pressure_headline,
            "prep_choice": lock.prep_choice,
            "scrim_call": lock.scrim_call,
            "exposed_problem": lock.exposed_problem,
            "spotlight_player": lock.spotlight_player,
            "scrim_signal": lock.scrim_signal,
            "opponent_attack": lock.opponent_attack,
            "team_edge": lock.team_edge,
            "match_risk": lock.match_risk,
            "recommended_plan": lock.recommended_plan,
            "available_choices": list(lock.available_choices),
            "selected_plan": lock.selected_plan,
            "plan_label": lock.plan_label,
            "deltas": {
                "readiness": lock.readiness_delta,
                "edge": lock.edge_delta,
                "risk": lock.risk_delta,
            },
            "match_pressure": lock.match_pressure,
            "next_problem": lock.next_problem,
            "next_hook": lock.next_hook,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _match_outcome(lock: Week8MatchPlanLock) -> tuple[Week8MatchOutcome, Week8MatchResult, str]:
    matched = lock.selected_plan == lock.recommended_plan
    if matched and lock.match_risk == "low":
        return "clean_win", "win", "2-0"
    if matched:
        return "messy_win", "win", "2-1"
    if lock.match_risk == "low":
        return "messy_win", "win", "2-1"
    if lock.match_risk == "high":
        return "loss_with_signal", "loss", "0-2"
    return "loss_with_signal", "loss", "1-2"


def _match_plan_effect(lock: Week8MatchPlanLock, outcome: Week8MatchOutcome) -> str:
    if lock.selected_plan == "patch_weakness" and outcome != "loss_with_signal":
        return (
            f"The staff protected {lock.opponent_attack}; the team survived first contact "
            f"even while {lock.team_edge} looked muted."
        )
    if lock.selected_plan == "patch_weakness":
        return (
            f"The team overprotected {lock.opponent_attack} and gave away the "
            f"{lock.team_edge} edge the preview identified."
        )
    if outcome != "loss_with_signal":
        return (
            f"The team trusted {lock.team_edge}; Apex Foundry did not get enough time "
            f"to punish {lock.opponent_attack}."
        )
    return (
        f"Apex Foundry forced {lock.opponent_attack}; {lock.team_edge} never stabilized "
        "long enough to become the match plan."
    )


def _match_public_read(
    lock: Week8MatchPlanLock,
    outcome: Week8MatchOutcome,
    result: Week8MatchResult,
) -> str:
    if outcome == "clean_win":
        return "The public read is prepared team, not lucky team."
    if result == "win" and lock.selected_plan == "patch_weakness":
        return "Fans saw the fix land, but the win looked narrow."
    if result == "win":
        return "Fans saw ceiling, with enough volatility to keep the next preview noisy."
    if lock.selected_plan == "patch_weakness":
        return "Coverage frames the loss as a staff plan that got too careful."
    return "Coverage frames the loss as ignoring the scout read under pressure."


def _match_pressure(lock: Week8MatchPlanLock, outcome: Week8MatchOutcome) -> tuple[str, str, int]:
    if outcome == "clean_win":
        return (
            "Opponents now have a clean first-contact script to copy.",
            "confidence",
            2,
        )
    if outcome == "messy_win" and lock.selected_plan == "patch_weakness":
        return (
            "Sponsors like the correction but want a cleaner Week 9 showing.",
            "coach_trust",
            1,
        )
    if outcome == "messy_win":
        return (
            "The roster likes the freedom, but the staff inherits a louder volatility question.",
            "player_pressure",
            1,
        )
    if lock.selected_plan == "patch_weakness":
        return (
            "The room trusts the intention, but the meta read says the team lost threat.",
            "meta_read",
            -1,
        )
    return (
        "The roster has to answer why the known attack got through untouched.",
        "player_pressure",
        -2,
    )


def _week9_hook(lock: Week8MatchPlanLock, outcome: Week8MatchOutcome) -> str:
    if outcome == "loss_with_signal":
        return (
            f"Week 9 opens on {lock.next_problem}: rebuild the plan after Apex Foundry "
            "proved the pressure read."
        )
    if lock.next_problem.endswith("_managed_but_edge_dulled"):
        return f"Week 9 opens on {lock.next_problem}: restore threat without undoing the patch."
    return f"Week 9 opens on {lock.next_problem}: prove the edge can survive a prepared counter."


def resolve_week8_match_result(lock: Week8MatchPlanLock) -> Week8MatchResultLock:
    """Resolve a locked Week-8 match plan into a deterministic match result."""
    outcome, result, scoreline = _match_outcome(lock)
    pressure, axis, delta = _match_pressure(lock, outcome)
    return Week8MatchResultLock(
        source_branch=lock.source_branch,
        setup_branch=lock.setup_branch,
        chosen_focus=lock.chosen_focus,
        source_pressure_outcome=lock.source_pressure_outcome,
        pressure_headline=lock.pressure_headline,
        prep_choice=lock.prep_choice,
        scrim_call=lock.scrim_call,
        selected_plan=lock.selected_plan,
        recommended_plan=lock.recommended_plan,
        matched_recommendation=lock.selected_plan == lock.recommended_plan,
        match_risk=lock.match_risk,
        opponent_attack=lock.opponent_attack,
        team_edge=lock.team_edge,
        match_pressure=lock.match_pressure,
        source_next_problem=lock.next_problem,
        outcome_id=outcome,
        match_result=result,
        scoreline=scoreline,
        plan_effect=_match_plan_effect(lock, outcome),
        public_read=_match_public_read(lock, outcome, result),
        pressure=pressure,
        consequence_axis=axis,
        consequence_delta=delta,
        week9_hook=_week9_hook(lock, outcome),
    )


def week8_match_result_from_json(text: str) -> Week8MatchResultLock:
    """Parse a written ``week8_match_result.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week8_match_result JSON is malformed") from exc
    result = data.get("week8_match_result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise ValueError("week8_match_result JSON must contain a week8_match_result object")
    selected = result.get("selected_plan")
    if selected not in WEEK8_MATCH_PLAN_CHOICES:
        raise ValueError("week8_match_result selected_plan must be patch_weakness or lean_into_edge")
    recommended = result.get("recommended_plan")
    if recommended not in WEEK8_MATCH_PLAN_CHOICES:
        raise ValueError("week8_match_result recommended_plan must be patch_weakness or lean_into_edge")
    prep_choice = result.get("prep_choice")
    if prep_choice not in WEEK8_PREP_CHOICES:
        raise ValueError("week8_match_result prep_choice must be patch_exposed_break or double_down_identity")
    scrim_call = result.get("scrim_call")
    if scrim_call not in WEEK8_SCRIM_CHOICES:
        raise ValueError("week8_match_result scrim_call must be play_to_prep or cover_the_crack")
    outcome = result.get("outcome_id")
    if outcome not in ("clean_win", "messy_win", "loss_with_signal"):
        raise ValueError("week8_match_result outcome_id must be clean_win, messy_win, or loss_with_signal")
    match_result = result.get("match_result")
    if match_result not in ("win", "loss"):
        raise ValueError("week8_match_result match_result must be win or loss")
    focus = result.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week8_match_result chosen_focus must be contain_fallout or prove_ceiling")
    return Week8MatchResultLock(
        source_branch=str(result.get("source_branch", "")),
        setup_branch=str(result.get("setup_branch", "")),
        chosen_focus=focus,
        source_pressure_outcome=str(result.get("source_pressure_outcome", "")),
        pressure_headline=str(result.get("pressure_headline", "")),
        prep_choice=prep_choice,
        scrim_call=scrim_call,
        selected_plan=selected,
        recommended_plan=recommended,
        matched_recommendation=bool(result.get("matched_recommendation", selected == recommended)),
        match_risk=str(result.get("match_risk", "")),
        opponent_attack=str(result.get("opponent_attack", "")),
        team_edge=str(result.get("team_edge", "")),
        match_pressure=str(result.get("match_pressure", "")),
        source_next_problem=str(result.get("source_next_problem", "")),
        outcome_id=outcome,
        match_result=match_result,
        scoreline=str(result.get("scoreline", "")),
        plan_effect=str(result.get("plan_effect", "")),
        public_read=str(result.get("public_read", "")),
        pressure=str(result.get("pressure", "")),
        consequence_axis=str(result.get("consequence_axis", "")),
        consequence_delta=int(result.get("consequence_delta", 0)),
        week9_hook=str(result.get("week9_hook", "")),
    )


def render_week8_match_result_json(lock: Week8MatchResultLock) -> str:
    """Canonical JSON export for a resolved Week-8 match result."""
    payload = {
        "week8_match_result": {
            "artifact_type": "week8_match_result",
            "schema_version": 1,
            "source_artifacts": {
                "week8_match_plan": "week8_match_plan.json",
            },
            "week": 8,
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "source_pressure_outcome": lock.source_pressure_outcome,
            "pressure_headline": lock.pressure_headline,
            "prep_choice": lock.prep_choice,
            "scrim_call": lock.scrim_call,
            "selected_plan": lock.selected_plan,
            "recommended_plan": lock.recommended_plan,
            "matched_recommendation": lock.matched_recommendation,
            "match_risk": lock.match_risk,
            "opponent_attack": lock.opponent_attack,
            "team_edge": lock.team_edge,
            "match_pressure": lock.match_pressure,
            "source_next_problem": lock.source_next_problem,
            "outcome_id": lock.outcome_id,
            "match_result": lock.match_result,
            "scoreline": lock.scoreline,
            "plan_effect": lock.plan_effect,
            "public_read": lock.public_read,
            "pressure": lock.pressure,
            "consequence_axis": lock.consequence_axis,
            "consequence_delta": lock.consequence_delta,
            "week9_hook": lock.week9_hook,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
