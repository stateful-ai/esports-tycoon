"""Deterministic Week-9 setup from the Week-8 match result artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from esports_tycoon.runner.week7 import WEEK7_FOCI, Week7Focus
from esports_tycoon.runner.week8 import Week8MatchResultLock

Week9ResponseChoice = Literal[
    "stabilize_roster",
    "double_down_read",
    "control_public_story",
]
Week9PrepChoice = Literal["lean_into_bias", "balance_risk", "counter_read"]
Week9ScrimReadChoice = Literal["room_read", "public_read", "tactical_read"]
Week9MatchPlanChoice = Literal["protect_the_room", "play_the_prep", "counter_the_read"]
Week9MatchOutcome = Literal[
    "room_held",
    "room_cracked",
    "prep_converted",
    "prep_stalled",
    "read_punished",
    "counter_overreached",
]
Week9MatchResultTier = Literal["win", "loss"]

WEEK9_SETUP_FILENAME = "week9_setup.json"
WEEK9_PREP_FILENAME = "week9_prep.json"
WEEK9_SCRIM_FILENAME = "week9_scrim.json"
WEEK9_MATCH_PLAN_FILENAME = "week9_match_plan.json"
WEEK9_MATCH_RESULT_FILENAME = "week9_match_result.json"
WEEK10_FALLOUT_FILENAME = "week10_fallout.json"
WEEK9_RESPONSE_CHOICES: tuple[Week9ResponseChoice, ...] = (
    "stabilize_roster",
    "double_down_read",
    "control_public_story",
)
WEEK9_PREP_CHOICES: tuple[Week9PrepChoice, ...] = (
    "lean_into_bias",
    "balance_risk",
    "counter_read",
)
WEEK9_SCRIM_CHOICES: tuple[Week9ScrimReadChoice, ...] = (
    "room_read",
    "public_read",
    "tactical_read",
)
WEEK9_MATCH_PLAN_CHOICES: tuple[Week9MatchPlanChoice, ...] = (
    "protect_the_room",
    "play_the_prep",
    "counter_the_read",
)
WEEK9_MATCH_OUTCOMES: tuple[Week9MatchOutcome, ...] = (
    "room_held",
    "room_cracked",
    "prep_converted",
    "prep_stalled",
    "read_punished",
    "counter_overreached",
)


@dataclass(frozen=True)
class Week9SetupOption:
    """One Week-9 response posture available after the Week-8 result."""

    value: Week9ResponseChoice
    label: str
    payoff: str
    cost: str


@dataclass(frozen=True)
class Week9SetupPlan:
    """The read-only Week-9 fallout setup before a response is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_plan: str
    matched_recommendation: bool
    match_risk: str
    public_read: str
    pressure: str
    consequence_axis: str
    consequence_delta: int
    week9_hook: str
    week9_problem_id: str
    manager_problem: str
    fallout_summary: str
    recommended_response: Week9ResponseChoice
    options: tuple[Week9SetupOption, ...]


@dataclass(frozen=True)
class Week9SetupLock:
    """The deterministic artifact produced by locking the Week-9 response."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_plan: str
    matched_recommendation: bool
    match_risk: str
    public_read: str
    pressure: str
    consequence_axis: str
    consequence_delta: int
    week9_hook: str
    week9_problem_id: str
    manager_problem: str
    fallout_summary: str
    available_choices: tuple[Week9ResponseChoice, ...]
    recommended_response: Week9ResponseChoice
    selected_response: Week9ResponseChoice
    response_label: str
    followed_recommendation: bool
    prep_bias: str
    risk_delta: int
    confidence_delta: int
    external_pressure_delta: int
    next_hook: str


@dataclass(frozen=True)
class Week9PrepOption:
    """One tactical prep lane available after the Week-9 setup response."""

    value: Week9PrepChoice
    label: str
    payoff: str
    cost: str
    prep_bias: str
    risk_delta: int
    confidence_delta: int
    external_pressure_delta: int
    match_read_alignment: str


@dataclass(frozen=True)
class Week9PrepPlan:
    """The read-only Week-9 prep meeting before a prep lane is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    response_label: str
    prep_bias: str
    starting_risk_delta: int
    starting_confidence_delta: int
    starting_external_pressure_delta: int
    public_read: str
    pressure: str
    consequence_axis: str
    consequence_delta: int
    recommended_prep: Week9PrepChoice
    options: tuple[Week9PrepOption, ...]


@dataclass(frozen=True)
class Week9PrepLock:
    """The deterministic artifact produced by locking Week-9 prep."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    response_label: str
    starting_prep_bias: str
    starting_risk_delta: int
    starting_confidence_delta: int
    starting_external_pressure_delta: int
    public_read: str
    pressure: str
    consequence_axis: str
    consequence_delta: int
    available_choices: tuple[Week9PrepChoice, ...]
    recommended_prep: Week9PrepChoice
    selected_prep: Week9PrepChoice
    prep_label: str
    selected_prep_bias: str
    prep_risk_delta: int
    prep_confidence_delta: int
    prep_external_pressure_delta: int
    combined_risk_delta: int
    combined_confidence_delta: int
    combined_external_pressure_delta: int
    match_read_alignment: str
    next_hook: str


@dataclass(frozen=True)
class Week9ScrimRead:
    """One deterministic interpretation available after the Week-9 scrim."""

    value: Week9ScrimReadChoice
    label: str
    status: str
    headline: str
    interpretation: str
    recommendation: str
    match_plan_pressure: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class Week9ScrimPlan:
    """The read-only Week-9 scrim read caused by setup + prep artifacts."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    response_label: str
    selected_prep: Week9PrepChoice
    prep_label: str
    selected_prep_bias: str
    match_read_alignment: str
    combined_risk_delta: int
    combined_confidence_delta: int
    combined_external_pressure_delta: int
    setup_read_id: Week9ScrimReadChoice
    prep_read_id: Week9ScrimReadChoice
    recommended_scrim_read: Week9ScrimReadChoice
    recommendation_reason: str
    reads: tuple[Week9ScrimRead, ...]


@dataclass(frozen=True)
class Week9ScrimLock:
    """The deterministic artifact produced by locking a Week-9 scrim read."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    response_label: str
    selected_prep: Week9PrepChoice
    prep_label: str
    selected_prep_bias: str
    match_read_alignment: str
    combined_risk_delta: int
    combined_confidence_delta: int
    combined_external_pressure_delta: int
    setup_read_id: Week9ScrimReadChoice
    prep_read_id: Week9ScrimReadChoice
    available_choices: tuple[Week9ScrimReadChoice, ...]
    recommended_scrim_read: Week9ScrimReadChoice
    selected_scrim_read: Week9ScrimReadChoice
    read_label: str
    scrim_reads: tuple[Week9ScrimRead, ...]
    selected_match_plan_pressure: str
    recommendation_reason: str
    next_hook: str


@dataclass(frozen=True)
class Week9MatchPlanOption:
    """One Week-9 match-week plan available after the scrim read."""

    value: Week9MatchPlanChoice
    label: str
    payoff: str
    cost: str
    read_basis: str
    commitment: str
    result_constraint: str


@dataclass(frozen=True)
class Week9MatchPlanPreview:
    """The read-only Week-9 match preview before the plan is locked."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_week8_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    selected_prep: Week9PrepChoice
    selected_prep_bias: str
    selected_scrim_read: Week9ScrimReadChoice
    selected_match_plan_pressure: str
    setup_read_id: Week9ScrimReadChoice
    prep_read_id: Week9ScrimReadChoice
    recommendation_basis: str
    recommended_plan: Week9MatchPlanChoice
    recommendation_reason: str
    match_risk: str
    options: tuple[Week9MatchPlanOption, ...]


@dataclass(frozen=True)
class Week9MatchPlanLock:
    """The deterministic artifact produced by locking the Week-9 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_week8_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    selected_prep: Week9PrepChoice
    selected_prep_bias: str
    selected_scrim_read: Week9ScrimReadChoice
    selected_match_plan_pressure: str
    setup_read_id: Week9ScrimReadChoice
    prep_read_id: Week9ScrimReadChoice
    recommendation_basis: str
    recommended_plan: Week9MatchPlanChoice
    available_choices: tuple[Week9MatchPlanChoice, ...]
    selected_plan: Week9MatchPlanChoice
    plan_label: str
    commitment: str
    risk_taken: str
    thing_to_watch: str
    match_risk: str
    result_constraints: tuple[str, ...]
    recommendation_reason: str
    next_hook: str


@dataclass(frozen=True)
class Week9VisibleEffect:
    """One visible consequence chip rendered on the Week-9 result page."""

    value: str
    label: str
    polarity: str


@dataclass(frozen=True)
class Week9MatchResultLock:
    """The deterministic artifact produced by resolving the Week-9 match plan."""

    source_branch: str
    setup_branch: str
    chosen_focus: Week7Focus
    week8_outcome_id: str
    week8_match_result: str
    week8_scoreline: str
    selected_week8_plan: str
    week9_problem_id: str
    manager_problem: str
    selected_response: Week9ResponseChoice
    selected_prep: Week9PrepChoice
    selected_scrim_read: Week9ScrimReadChoice
    selected_match_plan_pressure: str
    selected_plan: Week9MatchPlanChoice
    recommended_plan: Week9MatchPlanChoice
    matched_recommendation: bool
    commitment: str
    match_risk: str
    outcome_id: Week9MatchOutcome
    result_tier: Week9MatchResultTier
    team_maps: int
    opponent_maps: int
    scoreline: str
    headline: str
    recap: str
    player_read: str
    visible_effects: tuple[Week9VisibleEffect, ...]
    result_basis: tuple[str, ...]
    next_hook: str


def _week9_problem_id(result: Week8MatchResultLock) -> str:
    if result.outcome_id == "clean_win":
        return "expectations_spike"
    if result.outcome_id == "messy_win":
        if result.consequence_axis == "player_pressure":
            return "fragile_confidence"
        return "legitimacy_pressure"
    if result.consequence_axis == "meta_read":
        return "lost_threat_question"
    return "proof_of_learning"


def _manager_problem(result: Week8MatchResultLock, problem_id: str) -> str:
    if problem_id == "expectations_spike":
        return "The clean result raises expectations before the team has proved repeatability."
    if problem_id == "fragile_confidence":
        return "The win landed, but the room can feel how much pressure the volatility carried."
    if problem_id == "legitimacy_pressure":
        return "The win counts, but the public read asks whether the plan is stable enough to repeat."
    if problem_id == "lost_threat_question":
        return "The room understands the patch, but Week 9 asks whether the team still scares anyone."
    return "The loss produced signal, but the team has to decide whether to trust it."


def _recommended_response(result: Week8MatchResultLock) -> Week9ResponseChoice:
    if result.match_result == "loss" or result.consequence_axis == "player_pressure":
        return "stabilize_roster"
    if result.consequence_axis == "confidence":
        return "double_down_read"
    return "control_public_story"


def week9_setup_plan(result: Week8MatchResultLock) -> Week9SetupPlan:
    """Build the deterministic Week-9 fallout setup from the Week-8 result."""
    problem_id = _week9_problem_id(result)
    recommended = _recommended_response(result)
    options = (
        Week9SetupOption(
            value="stabilize_roster",
            label="Stabilize the roster",
            payoff="Lower volatility and protect player confidence before Week 9 prep.",
            cost="The team spends less time pressing the read that created the current hook.",
        ),
        Week9SetupOption(
            value="double_down_read",
            label="Double down on the read",
            payoff="Preserve conviction and make the Week 8 logic the Week 9 identity.",
            cost="External scrutiny rises if the same pressure gets punished again.",
        ),
        Week9SetupOption(
            value="control_public_story",
            label="Control the public story",
            payoff="Reduce outside pressure and frame the result before it frames the room.",
            cost="Internal issues may stay unresolved for one more block.",
        ),
    )
    return Week9SetupPlan(
        source_branch=result.source_branch,
        setup_branch=result.setup_branch,
        chosen_focus=result.chosen_focus,
        week8_outcome_id=result.outcome_id,
        week8_match_result=result.match_result,
        week8_scoreline=result.scoreline,
        selected_plan=result.selected_plan,
        matched_recommendation=result.matched_recommendation,
        match_risk=result.match_risk,
        public_read=result.public_read,
        pressure=result.pressure,
        consequence_axis=result.consequence_axis,
        consequence_delta=result.consequence_delta,
        week9_hook=result.week9_hook,
        week9_problem_id=problem_id,
        manager_problem=_manager_problem(result, problem_id),
        fallout_summary=f"{result.public_read} {result.pressure}",
        recommended_response=recommended,
        options=options,
    )


def resolve_week9_setup(plan: Week9SetupPlan, selected_response: str) -> Week9SetupLock:
    """Resolve one Week-9 response posture into a deterministic artifact."""
    if selected_response not in WEEK9_RESPONSE_CHOICES:
        raise ValueError(
            "selected_response must be stabilize_roster, double_down_read, or control_public_story"
        )
    response: Week9ResponseChoice = selected_response  # type: ignore[assignment]
    selected = next(option for option in plan.options if option.value == response)

    if response == "stabilize_roster":
        prep_bias = "room_stability"
        risk_delta, confidence_delta, external_delta = -1, 1, 0
        next_hook = f"Week 9 prep starts by lowering volatility around {plan.week9_problem_id}."
    elif response == "double_down_read":
        prep_bias = "strategic_conviction"
        risk_delta, confidence_delta, external_delta = 1, 1, 1
        next_hook = f"Week 9 prep starts by proving {plan.week9_problem_id} was a real read."
    else:
        prep_bias = "external_pressure"
        risk_delta, confidence_delta, external_delta = -1, 0, -1
        next_hook = f"Week 9 prep starts by controlling the story around {plan.week9_problem_id}."

    return Week9SetupLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week8_outcome_id=plan.week8_outcome_id,
        week8_match_result=plan.week8_match_result,
        week8_scoreline=plan.week8_scoreline,
        selected_plan=plan.selected_plan,
        matched_recommendation=plan.matched_recommendation,
        match_risk=plan.match_risk,
        public_read=plan.public_read,
        pressure=plan.pressure,
        consequence_axis=plan.consequence_axis,
        consequence_delta=plan.consequence_delta,
        week9_hook=plan.week9_hook,
        week9_problem_id=plan.week9_problem_id,
        manager_problem=plan.manager_problem,
        fallout_summary=plan.fallout_summary,
        available_choices=WEEK9_RESPONSE_CHOICES,
        recommended_response=plan.recommended_response,
        selected_response=response,
        response_label=selected.label,
        followed_recommendation=response == plan.recommended_response,
        prep_bias=prep_bias,
        risk_delta=risk_delta,
        confidence_delta=confidence_delta,
        external_pressure_delta=external_delta,
        next_hook=next_hook,
    )


def week9_setup_from_json(text: str) -> Week9SetupLock:
    """Parse a written ``week9_setup.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week9_setup JSON is malformed") from exc
    setup = data.get("week9_setup") if isinstance(data, dict) else None
    if not isinstance(setup, dict):
        raise ValueError("week9_setup JSON must contain a week9_setup object")
    selected = setup.get("selected_response")
    if selected not in WEEK9_RESPONSE_CHOICES:
        raise ValueError("week9_setup selected_response must list a Week-9 response choice")
    recommended = setup.get("recommended_response")
    if recommended not in WEEK9_RESPONSE_CHOICES:
        raise ValueError("week9_setup recommended_response must list a Week-9 response choice")
    available = setup.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK9_RESPONSE_CHOICES for choice in available):
        raise ValueError("week9_setup available_choices must list Week-9 response choices")
    focus = setup.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week9_setup chosen_focus must be contain_fallout or prove_ceiling")
    response_effect = setup.get("response_effect")
    if not isinstance(response_effect, dict):
        raise ValueError("week9_setup JSON must include response_effect")
    return Week9SetupLock(
        source_branch=str(setup.get("source_branch", "")),
        setup_branch=str(setup.get("setup_branch", "")),
        chosen_focus=focus,
        week8_outcome_id=str(setup.get("week8_outcome_id", "")),
        week8_match_result=str(setup.get("week8_match_result", "")),
        week8_scoreline=str(setup.get("week8_scoreline", "")),
        selected_plan=str(setup.get("selected_plan", "")),
        matched_recommendation=bool(setup.get("matched_recommendation", False)),
        match_risk=str(setup.get("match_risk", "")),
        public_read=str(setup.get("public_read", "")),
        pressure=str(setup.get("pressure", "")),
        consequence_axis=str(setup.get("consequence_axis", "")),
        consequence_delta=int(setup.get("consequence_delta", 0)),
        week9_hook=str(setup.get("week9_hook", "")),
        week9_problem_id=str(setup.get("week9_problem_id", "")),
        manager_problem=str(setup.get("manager_problem", "")),
        fallout_summary=str(setup.get("fallout_summary", "")),
        available_choices=tuple(available),  # type: ignore[arg-type]
        recommended_response=recommended,
        selected_response=selected,
        response_label=str(setup.get("response_label", "")),
        followed_recommendation=bool(setup.get("followed_recommendation", selected == recommended)),
        prep_bias=str(response_effect.get("prep_bias", "")),
        risk_delta=int(response_effect.get("risk", 0)),
        confidence_delta=int(response_effect.get("confidence", 0)),
        external_pressure_delta=int(response_effect.get("external_pressure", 0)),
        next_hook=str(setup.get("next_hook", "")),
    )


def render_week9_setup_json(lock: Week9SetupLock) -> str:
    """Canonical JSON export for a locked Week-9 setup response."""
    payload = {
        "week9_setup": {
            "artifact_type": "week9_setup",
            "schema_version": 1,
            "source_artifacts": {
                "week8_match_result": "week8_match_result.json",
            },
            "week": 9,
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week8_outcome_id": lock.week8_outcome_id,
            "week8_match_result": lock.week8_match_result,
            "week8_scoreline": lock.week8_scoreline,
            "selected_plan": lock.selected_plan,
            "matched_recommendation": lock.matched_recommendation,
            "match_risk": lock.match_risk,
            "public_read": lock.public_read,
            "pressure": lock.pressure,
            "consequence_axis": lock.consequence_axis,
            "consequence_delta": lock.consequence_delta,
            "week9_hook": lock.week9_hook,
            "week9_problem_id": lock.week9_problem_id,
            "manager_problem": lock.manager_problem,
            "fallout_summary": lock.fallout_summary,
            "available_choices": list(lock.available_choices),
            "recommended_response": lock.recommended_response,
            "selected_response": lock.selected_response,
            "response_label": lock.response_label,
            "followed_recommendation": lock.followed_recommendation,
            "response_effect": {
                "prep_bias": lock.prep_bias,
                "risk": lock.risk_delta,
                "confidence": lock.confidence_delta,
                "external_pressure": lock.external_pressure_delta,
            },
            "next_hook": lock.next_hook,
            "next_artifact": "week9_prep.json",
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _recommended_prep(setup: Week9SetupLock) -> Week9PrepChoice:
    if setup.prep_bias == "strategic_conviction":
        return "lean_into_bias"
    if setup.prep_bias == "external_pressure":
        return "counter_read"
    if setup.prep_bias == "room_stability":
        return "balance_risk"
    if setup.external_pressure_delta > 0:
        return "counter_read"
    if setup.risk_delta > 0:
        return "balance_risk"
    return "lean_into_bias"


def week9_prep_plan(setup: Week9SetupLock) -> Week9PrepPlan:
    """Build the deterministic Week-9 prep meeting from ``week9_setup.json``."""
    options = (
        Week9PrepOption(
            value="lean_into_bias",
            label="Lean into the posture",
            payoff=f"Turn {setup.prep_bias} into the main practice lane.",
            cost="The room gets a clearer identity, but the same pressure can punish it.",
            prep_bias=setup.prep_bias,
            risk_delta=1,
            confidence_delta=1,
            external_pressure_delta=0,
            match_read_alignment="follow_bias",
        ),
        Week9PrepOption(
            value="balance_risk",
            label="Balance the risk",
            payoff="Rebuild fundamentals around the current pressure before adding new looks.",
            cost="The prep may look conservative if the next opponent sits deep.",
            prep_bias="fundamentals",
            risk_delta=-1,
            confidence_delta=0,
            external_pressure_delta=-1,
            match_read_alignment="hedge",
        ),
        Week9PrepOption(
            value="counter_read",
            label="Counter the public read",
            payoff="Prepare the answer the outside conversation expects to see.",
            cost="External attention rises because the team is visibly reacting to the read.",
            prep_bias="public_read_counter",
            risk_delta=0,
            confidence_delta=0,
            external_pressure_delta=1,
            match_read_alignment="counter_public",
        ),
    )
    return Week9PrepPlan(
        source_branch=setup.source_branch,
        setup_branch=setup.setup_branch,
        chosen_focus=setup.chosen_focus,
        week8_outcome_id=setup.week8_outcome_id,
        week8_match_result=setup.week8_match_result,
        week8_scoreline=setup.week8_scoreline,
        selected_plan=setup.selected_plan,
        week9_problem_id=setup.week9_problem_id,
        manager_problem=setup.manager_problem,
        selected_response=setup.selected_response,
        response_label=setup.response_label,
        prep_bias=setup.prep_bias,
        starting_risk_delta=setup.risk_delta,
        starting_confidence_delta=setup.confidence_delta,
        starting_external_pressure_delta=setup.external_pressure_delta,
        public_read=setup.public_read,
        pressure=setup.pressure,
        consequence_axis=setup.consequence_axis,
        consequence_delta=setup.consequence_delta,
        recommended_prep=_recommended_prep(setup),
        options=options,
    )


def resolve_week9_prep(plan: Week9PrepPlan, selected_prep: str) -> Week9PrepLock:
    """Resolve one Week-9 prep lane into a deterministic artifact."""
    if selected_prep not in WEEK9_PREP_CHOICES:
        raise ValueError("selected_prep must be lean_into_bias, balance_risk, or counter_read")
    prep: Week9PrepChoice = selected_prep  # type: ignore[assignment]
    selected = next(option for option in plan.options if option.value == prep)
    combined_risk = plan.starting_risk_delta + selected.risk_delta
    combined_confidence = plan.starting_confidence_delta + selected.confidence_delta
    combined_external = plan.starting_external_pressure_delta + selected.external_pressure_delta
    return Week9PrepLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week8_outcome_id=plan.week8_outcome_id,
        week8_match_result=plan.week8_match_result,
        week8_scoreline=plan.week8_scoreline,
        selected_plan=plan.selected_plan,
        week9_problem_id=plan.week9_problem_id,
        manager_problem=plan.manager_problem,
        selected_response=plan.selected_response,
        response_label=plan.response_label,
        starting_prep_bias=plan.prep_bias,
        starting_risk_delta=plan.starting_risk_delta,
        starting_confidence_delta=plan.starting_confidence_delta,
        starting_external_pressure_delta=plan.starting_external_pressure_delta,
        public_read=plan.public_read,
        pressure=plan.pressure,
        consequence_axis=plan.consequence_axis,
        consequence_delta=plan.consequence_delta,
        available_choices=WEEK9_PREP_CHOICES,
        recommended_prep=plan.recommended_prep,
        selected_prep=prep,
        prep_label=selected.label,
        selected_prep_bias=selected.prep_bias,
        prep_risk_delta=selected.risk_delta,
        prep_confidence_delta=selected.confidence_delta,
        prep_external_pressure_delta=selected.external_pressure_delta,
        combined_risk_delta=combined_risk,
        combined_confidence_delta=combined_confidence,
        combined_external_pressure_delta=combined_external,
        match_read_alignment=selected.match_read_alignment,
        next_hook=(
            f"Week 9 scrim tests {selected.prep_bias} against "
            f"{plan.week9_problem_id}."
        ),
    )


def week9_prep_from_json(text: str) -> Week9PrepLock:
    """Parse a written ``week9_prep.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week9_prep JSON is malformed") from exc
    prep = data.get("week9_prep") if isinstance(data, dict) else None
    if not isinstance(prep, dict):
        raise ValueError("week9_prep JSON must contain a week9_prep object")
    selected = prep.get("selected_prep")
    if selected not in WEEK9_PREP_CHOICES:
        raise ValueError("week9_prep selected_prep must list a Week-9 prep choice")
    recommended = prep.get("recommended_prep")
    if recommended not in WEEK9_PREP_CHOICES:
        raise ValueError("week9_prep recommended_prep must list a Week-9 prep choice")
    response = prep.get("selected_response")
    if response not in WEEK9_RESPONSE_CHOICES:
        raise ValueError("week9_prep selected_response must list a Week-9 response choice")
    available = prep.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK9_PREP_CHOICES for choice in available):
        raise ValueError("week9_prep available_choices must list Week-9 prep choices")
    focus = prep.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week9_prep chosen_focus must be contain_fallout or prove_ceiling")
    starting = prep.get("starting_effect")
    selected_effect = prep.get("selected_prep_effect")
    combined = prep.get("combined_effect")
    if not isinstance(starting, dict):
        raise ValueError("week9_prep JSON must include starting_effect")
    if not isinstance(selected_effect, dict):
        raise ValueError("week9_prep JSON must include selected_prep_effect")
    if not isinstance(combined, dict):
        raise ValueError("week9_prep JSON must include combined_effect")
    return Week9PrepLock(
        source_branch=str(prep.get("source_branch", "")),
        setup_branch=str(prep.get("setup_branch", "")),
        chosen_focus=focus,
        week8_outcome_id=str(prep.get("week8_outcome_id", "")),
        week8_match_result=str(prep.get("week8_match_result", "")),
        week8_scoreline=str(prep.get("week8_scoreline", "")),
        selected_plan=str(prep.get("selected_plan", "")),
        week9_problem_id=str(prep.get("week9_problem_id", "")),
        manager_problem=str(prep.get("manager_problem", "")),
        selected_response=response,
        response_label=str(prep.get("response_label", "")),
        starting_prep_bias=str(starting.get("prep_bias", "")),
        starting_risk_delta=int(starting.get("risk", 0)),
        starting_confidence_delta=int(starting.get("confidence", 0)),
        starting_external_pressure_delta=int(starting.get("external_pressure", 0)),
        public_read=str(prep.get("public_read", "")),
        pressure=str(prep.get("pressure", "")),
        consequence_axis=str(prep.get("consequence_axis", "")),
        consequence_delta=int(prep.get("consequence_delta", 0)),
        available_choices=tuple(available),  # type: ignore[arg-type]
        recommended_prep=recommended,
        selected_prep=selected,
        prep_label=str(prep.get("prep_label", "")),
        selected_prep_bias=str(prep.get("selected_prep_bias", "")),
        prep_risk_delta=int(selected_effect.get("risk", 0)),
        prep_confidence_delta=int(selected_effect.get("confidence", 0)),
        prep_external_pressure_delta=int(selected_effect.get("external_pressure", 0)),
        combined_risk_delta=int(combined.get("risk", 0)),
        combined_confidence_delta=int(combined.get("confidence", 0)),
        combined_external_pressure_delta=int(combined.get("external_pressure", 0)),
        match_read_alignment=str(prep.get("match_read_alignment", "")),
        next_hook=str(prep.get("next_hook", "")),
    )


def render_week9_prep_json(lock: Week9PrepLock) -> str:
    """Canonical JSON export for a locked Week-9 prep lane."""
    payload = {
        "week9_prep": {
            "artifact_type": "week9_prep",
            "schema_version": 1,
            "source_artifacts": {
                "week9_setup": "week9_setup.json",
            },
            "week": 9,
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week8_outcome_id": lock.week8_outcome_id,
            "week8_match_result": lock.week8_match_result,
            "week8_scoreline": lock.week8_scoreline,
            "selected_plan": lock.selected_plan,
            "week9_problem_id": lock.week9_problem_id,
            "manager_problem": lock.manager_problem,
            "selected_response": lock.selected_response,
            "response_label": lock.response_label,
            "public_read": lock.public_read,
            "pressure": lock.pressure,
            "consequence_axis": lock.consequence_axis,
            "consequence_delta": lock.consequence_delta,
            "available_choices": list(lock.available_choices),
            "recommended_prep": lock.recommended_prep,
            "selected_prep": lock.selected_prep,
            "prep_label": lock.prep_label,
            "selected_prep_bias": lock.selected_prep_bias,
            "starting_effect": {
                "prep_bias": lock.starting_prep_bias,
                "risk": lock.starting_risk_delta,
                "confidence": lock.starting_confidence_delta,
                "external_pressure": lock.starting_external_pressure_delta,
            },
            "selected_prep_effect": {
                "risk": lock.prep_risk_delta,
                "confidence": lock.prep_confidence_delta,
                "external_pressure": lock.prep_external_pressure_delta,
            },
            "combined_effect": {
                "risk": lock.combined_risk_delta,
                "confidence": lock.combined_confidence_delta,
                "external_pressure": lock.combined_external_pressure_delta,
            },
            "match_read_alignment": lock.match_read_alignment,
            "next_hook": lock.next_hook,
            "next_artifact": "week9_scrim.json",
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_READ_LABELS: dict[Week9ScrimReadChoice, str] = {
    "room_read": "Room read",
    "public_read": "Public read",
    "tactical_read": "Tactical read",
}

_MATCH_PLAN_PRESSURES: dict[Week9ScrimReadChoice, str] = {
    "room_read": "room_confidence",
    "public_read": "external_pressure",
    "tactical_read": "tactical_proof",
}

_READ_HEADLINES: dict[Week9ScrimReadChoice, dict[str, str]] = {
    "room_read": {
        "reinforced": "The room heard one message twice",
        "exposed": "The room is where the prep can crack",
        "watch": "The room still owns the first pressure",
        "secondary": "The room is steady enough to monitor",
    },
    "public_read": {
        "reinforced": "The outside story is now the scrim story",
        "exposed": "The public counter is the first stress point",
        "watch": "The public read still frames the block",
        "secondary": "The public noise stays outside the main test",
    },
    "tactical_read": {
        "reinforced": "The tape and the prep point at the same test",
        "exposed": "The tactical tell is what breaks first",
        "watch": "The tactical question still has to be respected",
        "secondary": "The tactical read is useful but not decisive yet",
    },
}

_READ_INTERPRETATIONS: dict[Week9ScrimReadChoice, dict[str, str]] = {
    "room_read": {
        "reinforced": (
            "Players repeated the same call language under pressure; the staff can treat "
            "the room as a strength only if it holds through the next plan."
        ),
        "exposed": (
            "The prep lane moved the stress back inside the room; the first missed protocol "
            "will read like a confidence problem."
        ),
        "watch": (
            "The setup response still sits in the room, but the prep lane is testing another "
            "surface first."
        ),
        "secondary": (
            "The room stayed playable through the scrim, but it was not the loudest signal "
            "from the block."
        ),
    },
    "public_read": {
        "reinforced": (
            "The scrim gave the staff enough evidence to keep shaping the outside story "
            "before it shapes the team."
        ),
        "exposed": (
            "The prep lane visibly reacted to the outside read; if Week 9 starts slow, the "
            "story will look defensive."
        ),
        "watch": (
            "The setup response still has public pressure attached, even though the prep "
            "block searched elsewhere."
        ),
        "secondary": (
            "The outside noise did not dominate the scrim, but the match plan still has to "
            "leave fewer public questions."
        ),
    },
    "tactical_read": {
        "reinforced": (
            "The scrim repeated the same tactical stress and found a usable first answer; "
            "the next plan can be more specific."
        ),
        "exposed": (
            "The prep lane created one clear tactical tell: opponents can force this look "
            "before the room is fully settled."
        ),
        "watch": (
            "The original response still carries a tactical question, but the prep lane "
            "did not spend the whole block solving it."
        ),
        "secondary": (
            "The staff has usable tape, but the tactical read is not strong enough to carry "
            "the plan by itself."
        ),
    },
}

_READ_RECOMMENDATIONS: dict[Week9ScrimReadChoice, str] = {
    "room_read": "Build the Week 9 plan around protecting room confidence at first contact.",
    "public_read": "Build the Week 9 plan around reducing the outside pressure's cleanest angle.",
    "tactical_read": "Build the Week 9 plan around the clearest tactical proof from the block.",
}


def _setup_read_id(setup: Week9SetupLock) -> Week9ScrimReadChoice:
    if setup.selected_response == "stabilize_roster":
        return "room_read"
    if setup.selected_response == "control_public_story":
        return "public_read"
    return "tactical_read"


def _prep_read_id(prep: Week9PrepLock) -> Week9ScrimReadChoice:
    if prep.selected_prep == "counter_read" or prep.selected_prep_bias == "public_read_counter":
        return "public_read"
    if prep.selected_prep == "balance_risk" or prep.selected_prep_bias == "fundamentals":
        return "tactical_read"
    if prep.selected_prep_bias == "room_stability":
        return "room_read"
    if prep.selected_prep_bias == "external_pressure":
        return "public_read"
    return "tactical_read"


def _read_status(
    read_id: Week9ScrimReadChoice,
    setup_read_id: Week9ScrimReadChoice,
    prep_read_id: Week9ScrimReadChoice,
) -> str:
    if read_id == setup_read_id == prep_read_id:
        return "reinforced"
    if read_id == prep_read_id:
        return "exposed"
    if read_id == setup_read_id:
        return "watch"
    return "secondary"


def _recommendation_reason(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    setup_read_id: Week9ScrimReadChoice,
    prep_read_id: Week9ScrimReadChoice,
) -> str:
    if setup_read_id == prep_read_id:
        return (
            f"{setup.selected_response} and {prep.selected_prep} both point at "
            f"{_READ_LABELS[prep_read_id].lower()}."
        )
    return (
        f"{prep.selected_prep} pulls the scrim toward {_READ_LABELS[prep_read_id].lower()} "
        f"after {setup.selected_response} opened {_READ_LABELS[setup_read_id].lower()}."
    )


def _scrim_read_options(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    setup_read_id: Week9ScrimReadChoice,
    prep_read_id: Week9ScrimReadChoice,
) -> tuple[Week9ScrimRead, ...]:
    source_refs = (
        f"setup:{setup.selected_response}",
        f"prep:{prep.selected_prep}",
    )
    reads: list[Week9ScrimRead] = []
    for read_id in WEEK9_SCRIM_CHOICES:
        status = _read_status(read_id, setup_read_id, prep_read_id)
        reads.append(
            Week9ScrimRead(
                value=read_id,
                label=_READ_LABELS[read_id],
                status=status,
                headline=_READ_HEADLINES[read_id][status],
                interpretation=_READ_INTERPRETATIONS[read_id][status],
                recommendation=_READ_RECOMMENDATIONS[read_id],
                match_plan_pressure=_MATCH_PLAN_PRESSURES[read_id],
                source_refs=source_refs,
            )
        )
    return tuple(reads)


def week9_scrim_plan(setup: Week9SetupLock, prep: Week9PrepLock) -> Week9ScrimPlan:
    """Build the deterministic Week-9 scrim read from setup + prep artifacts."""
    if setup.source_branch != prep.source_branch or setup.setup_branch != prep.setup_branch:
        raise ValueError("week9 scrim artifacts do not agree on source branch")
    if setup.chosen_focus != prep.chosen_focus:
        raise ValueError("week9 scrim artifacts do not agree on chosen focus")
    if setup.week8_outcome_id != prep.week8_outcome_id:
        raise ValueError("week9 scrim artifacts do not agree on Week-8 outcome")
    if setup.selected_response != prep.selected_response:
        raise ValueError("week9 scrim prep does not match setup response")
    if setup.week9_problem_id != prep.week9_problem_id:
        raise ValueError("week9 scrim prep does not match setup problem")

    setup_read_id = _setup_read_id(setup)
    prep_read_id = _prep_read_id(prep)
    reads = _scrim_read_options(setup, prep, setup_read_id, prep_read_id)
    return Week9ScrimPlan(
        source_branch=setup.source_branch,
        setup_branch=setup.setup_branch,
        chosen_focus=setup.chosen_focus,
        week8_outcome_id=setup.week8_outcome_id,
        week8_match_result=setup.week8_match_result,
        week8_scoreline=setup.week8_scoreline,
        selected_plan=setup.selected_plan,
        week9_problem_id=setup.week9_problem_id,
        manager_problem=setup.manager_problem,
        selected_response=setup.selected_response,
        response_label=setup.response_label,
        selected_prep=prep.selected_prep,
        prep_label=prep.prep_label,
        selected_prep_bias=prep.selected_prep_bias,
        match_read_alignment=prep.match_read_alignment,
        combined_risk_delta=prep.combined_risk_delta,
        combined_confidence_delta=prep.combined_confidence_delta,
        combined_external_pressure_delta=prep.combined_external_pressure_delta,
        setup_read_id=setup_read_id,
        prep_read_id=prep_read_id,
        recommended_scrim_read=prep_read_id,
        recommendation_reason=_recommendation_reason(setup, prep, setup_read_id, prep_read_id),
        reads=reads,
    )


def resolve_week9_scrim(plan: Week9ScrimPlan, selected_read: str) -> Week9ScrimLock:
    """Resolve one Week-9 scrim read into a deterministic artifact."""
    if selected_read not in WEEK9_SCRIM_CHOICES:
        raise ValueError("selected_read must be room_read, public_read, or tactical_read")
    read: Week9ScrimReadChoice = selected_read  # type: ignore[assignment]
    selected = next(option for option in plan.reads if option.value == read)
    return Week9ScrimLock(
        source_branch=plan.source_branch,
        setup_branch=plan.setup_branch,
        chosen_focus=plan.chosen_focus,
        week8_outcome_id=plan.week8_outcome_id,
        week8_match_result=plan.week8_match_result,
        week8_scoreline=plan.week8_scoreline,
        selected_plan=plan.selected_plan,
        week9_problem_id=plan.week9_problem_id,
        manager_problem=plan.manager_problem,
        selected_response=plan.selected_response,
        response_label=plan.response_label,
        selected_prep=plan.selected_prep,
        prep_label=plan.prep_label,
        selected_prep_bias=plan.selected_prep_bias,
        match_read_alignment=plan.match_read_alignment,
        combined_risk_delta=plan.combined_risk_delta,
        combined_confidence_delta=plan.combined_confidence_delta,
        combined_external_pressure_delta=plan.combined_external_pressure_delta,
        setup_read_id=plan.setup_read_id,
        prep_read_id=plan.prep_read_id,
        available_choices=WEEK9_SCRIM_CHOICES,
        recommended_scrim_read=plan.recommended_scrim_read,
        selected_scrim_read=read,
        read_label=selected.label,
        scrim_reads=plan.reads,
        selected_match_plan_pressure=selected.match_plan_pressure,
        recommendation_reason=plan.recommendation_reason,
        next_hook=(
            f"Week 9 match planning inherits {selected.match_plan_pressure} "
            f"from {read}."
        ),
    )


def week9_scrim_from_json(text: str) -> Week9ScrimLock:
    """Parse a written ``week9_scrim.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week9_scrim JSON is malformed") from exc
    scrim = data.get("week9_scrim") if isinstance(data, dict) else None
    if not isinstance(scrim, dict):
        raise ValueError("week9_scrim JSON must contain a week9_scrim object")
    selected = scrim.get("selected_scrim_read")
    if selected not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_scrim selected_scrim_read must list a Week-9 scrim read")
    recommended = scrim.get("recommended_scrim_read")
    if recommended not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_scrim recommended_scrim_read must list a Week-9 scrim read")
    setup_read = scrim.get("setup_read_id")
    if setup_read not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_scrim setup_read_id must list a Week-9 scrim read")
    prep_read = scrim.get("prep_read_id")
    if prep_read not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_scrim prep_read_id must list a Week-9 scrim read")
    response = scrim.get("selected_response")
    if response not in WEEK9_RESPONSE_CHOICES:
        raise ValueError("week9_scrim selected_response must list a Week-9 response choice")
    prep_choice = scrim.get("selected_prep")
    if prep_choice not in WEEK9_PREP_CHOICES:
        raise ValueError("week9_scrim selected_prep must list a Week-9 prep choice")
    available = scrim.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK9_SCRIM_CHOICES for choice in available):
        raise ValueError("week9_scrim available_choices must list Week-9 scrim reads")
    focus = scrim.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week9_scrim chosen_focus must be contain_fallout or prove_ceiling")
    combined = scrim.get("combined_effect")
    if not isinstance(combined, dict):
        raise ValueError("week9_scrim JSON must include combined_effect")
    raw_reads = scrim.get("scrim_reads")
    if not isinstance(raw_reads, list) or len(raw_reads) != len(WEEK9_SCRIM_CHOICES):
        raise ValueError("week9_scrim scrim_reads must list exactly three reads")
    if scrim.get("next_artifact") not in {None, "week9_match_plan.json"}:
        raise ValueError("week9_scrim next_artifact must be week9_match_plan.json")
    reads: list[Week9ScrimRead] = []
    for raw in raw_reads:
        if not isinstance(raw, dict):
            raise ValueError("week9_scrim scrim_reads entries must be objects")
        read_id = raw.get("id")
        if read_id not in WEEK9_SCRIM_CHOICES:
            raise ValueError("week9_scrim scrim_reads ids must be Week-9 scrim reads")
        source_refs = raw.get("source_refs")
        if not isinstance(source_refs, list):
            raise ValueError("week9_scrim scrim_reads entries must include source_refs")
        reads.append(
            Week9ScrimRead(
                value=read_id,
                label=str(raw.get("label", "")),
                status=str(raw.get("status", "")),
                headline=str(raw.get("headline", "")),
                interpretation=str(raw.get("interpretation", "")),
                recommendation=str(raw.get("recommendation", "")),
                match_plan_pressure=str(raw.get("match_plan_pressure", "")),
                source_refs=tuple(str(item) for item in source_refs),
            )
        )
    if tuple(read.value for read in reads) != WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_scrim scrim_reads must use room/public/tactical order")
    return Week9ScrimLock(
        source_branch=str(scrim.get("source_branch", "")),
        setup_branch=str(scrim.get("setup_branch", "")),
        chosen_focus=focus,
        week8_outcome_id=str(scrim.get("week8_outcome_id", "")),
        week8_match_result=str(scrim.get("week8_match_result", "")),
        week8_scoreline=str(scrim.get("week8_scoreline", "")),
        selected_plan=str(scrim.get("selected_plan", "")),
        week9_problem_id=str(scrim.get("week9_problem_id", "")),
        manager_problem=str(scrim.get("manager_problem", "")),
        selected_response=response,
        response_label=str(scrim.get("response_label", "")),
        selected_prep=prep_choice,
        prep_label=str(scrim.get("prep_label", "")),
        selected_prep_bias=str(scrim.get("selected_prep_bias", "")),
        match_read_alignment=str(scrim.get("match_read_alignment", "")),
        combined_risk_delta=int(combined.get("risk", 0)),
        combined_confidence_delta=int(combined.get("confidence", 0)),
        combined_external_pressure_delta=int(combined.get("external_pressure", 0)),
        setup_read_id=setup_read,
        prep_read_id=prep_read,
        available_choices=tuple(available),  # type: ignore[arg-type]
        recommended_scrim_read=recommended,
        selected_scrim_read=selected,
        read_label=str(scrim.get("read_label", "")),
        scrim_reads=tuple(reads),
        selected_match_plan_pressure=str(scrim.get("selected_match_plan_pressure", "")),
        recommendation_reason=str(scrim.get("recommendation_reason", "")),
        next_hook=str(scrim.get("next_hook", "")),
    )


def render_week9_scrim_json(lock: Week9ScrimLock) -> str:
    """Canonical JSON export for a locked Week-9 scrim read."""
    payload = {
        "week9_scrim": {
            "artifact_type": "week9_scrim",
            "schema_version": 1,
            "source_artifacts": {
                "week9_setup": "week9_setup.json",
                "week9_prep": "week9_prep.json",
            },
            "week": 9,
            "route": "/week9/scrim",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week8_outcome_id": lock.week8_outcome_id,
            "week8_match_result": lock.week8_match_result,
            "week8_scoreline": lock.week8_scoreline,
            "selected_plan": lock.selected_plan,
            "week9_problem_id": lock.week9_problem_id,
            "manager_problem": lock.manager_problem,
            "selected_response": lock.selected_response,
            "response_label": lock.response_label,
            "selected_prep": lock.selected_prep,
            "prep_label": lock.prep_label,
            "selected_prep_bias": lock.selected_prep_bias,
            "match_read_alignment": lock.match_read_alignment,
            "combined_effect": {
                "risk": lock.combined_risk_delta,
                "confidence": lock.combined_confidence_delta,
                "external_pressure": lock.combined_external_pressure_delta,
            },
            "setup_read_id": lock.setup_read_id,
            "prep_read_id": lock.prep_read_id,
            "available_choices": list(lock.available_choices),
            "recommended_scrim_read": lock.recommended_scrim_read,
            "selected_scrim_read": lock.selected_scrim_read,
            "read_label": lock.read_label,
            "scrim_reads": [
                {
                    "id": read.value,
                    "label": read.label,
                    "status": read.status,
                    "headline": read.headline,
                    "interpretation": read.interpretation,
                    "recommendation": read.recommendation,
                    "match_plan_pressure": read.match_plan_pressure,
                    "source_refs": list(read.source_refs),
                }
                for read in lock.scrim_reads
            ],
            "selected_match_plan_pressure": lock.selected_match_plan_pressure,
            "recommendation_reason": lock.recommendation_reason,
            "next_hook": lock.next_hook,
            "next_artifact": "week9_match_plan.json",
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_MATCH_PLAN_OPTIONS: tuple[Week9MatchPlanOption, ...] = (
    Week9MatchPlanOption(
        value="protect_the_room",
        label="Protect the room",
        payoff="Keep roles and first-contact comms stable around the room read.",
        cost="The team spends less match prep on surprise and pressure.",
        read_basis="room_read",
        commitment="stabilize",
        result_constraint="room_confidence_must_hold",
    ),
    Week9MatchPlanOption(
        value="play_the_prep",
        label="Play the prep",
        payoff="Commit the match plan to the prep lane the week already bought.",
        cost="If the read is wrong, the team has less room to pivot mid-map.",
        read_basis="prep_lane",
        commitment="commit",
        result_constraint="prep_lane_must_translate",
    ),
    Week9MatchPlanOption(
        value="counter_the_read",
        label="Counter the read",
        payoff="Use the clearest scrim pressure as the first match-week adjustment.",
        cost="The plan adds complexity after a week already shaped by fallout.",
        read_basis="scrim_read",
        commitment="counter",
        result_constraint="counter_must_land_early",
    ),
)


def _week9_match_recommendation(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
) -> tuple[Week9MatchPlanChoice, str, str]:
    if (
        scrim.selected_scrim_read == "room_read"
        or scrim.selected_match_plan_pressure == "room_confidence"
        or setup.selected_response == "stabilize_roster"
    ):
        return (
            "protect_the_room",
            "room_instability",
            "The setup or scrim read puts the room at the center of the Week 9 risk.",
        )
    if scrim.selected_scrim_read == scrim.prep_read_id:
        return (
            "play_the_prep",
            "prep_scrim_alignment",
            "The locked prep lane and selected scrim read point at the same match-week posture.",
        )
    if scrim.selected_scrim_read in {"public_read", "tactical_read"}:
        return (
            "counter_the_read",
            "sharp_scrim_adjustment",
            "The selected scrim read creates a concrete public or tactical adjustment.",
        )
    if prep.selected_prep == "counter_read":
        return (
            "counter_the_read",
            "prep_counter_lane",
            "The prep lane already asked the team to answer the outside read.",
        )
    return (
        "play_the_prep",
        "default_to_preparation",
        "No single pressure dominates, so the cleanest plan is to trust the week's prep.",
    )


def _week9_match_risk(
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
    recommended_plan: Week9MatchPlanChoice,
) -> str:
    if prep.combined_risk_delta >= 2 or scrim.selected_match_plan_pressure == "external_pressure":
        return "high"
    if prep.combined_risk_delta <= -1 and recommended_plan == "protect_the_room":
        return "low"
    return "medium"


def week9_match_plan_preview(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
) -> Week9MatchPlanPreview:
    """Build the deterministic Week-9 match-plan preview from prior artifacts."""
    if setup.source_branch != prep.source_branch or setup.source_branch != scrim.source_branch:
        raise ValueError("week9 match artifacts do not agree on source branch")
    if setup.setup_branch != prep.setup_branch or setup.setup_branch != scrim.setup_branch:
        raise ValueError("week9 match artifacts do not agree on setup branch")
    if setup.chosen_focus != prep.chosen_focus or setup.chosen_focus != scrim.chosen_focus:
        raise ValueError("week9 match artifacts do not agree on chosen focus")
    if setup.week8_outcome_id != prep.week8_outcome_id or setup.week8_outcome_id != scrim.week8_outcome_id:
        raise ValueError("week9 match artifacts do not agree on Week-8 outcome")
    if setup.selected_response != prep.selected_response or setup.selected_response != scrim.selected_response:
        raise ValueError("week9 match artifacts do not agree on Week-9 response")
    if prep.selected_prep != scrim.selected_prep:
        raise ValueError("week9 match scrim does not match Week-9 prep")
    if setup.week9_problem_id != prep.week9_problem_id or setup.week9_problem_id != scrim.week9_problem_id:
        raise ValueError("week9 match artifacts do not agree on Week-9 problem")

    recommended, basis, reason = _week9_match_recommendation(setup, prep, scrim)
    return Week9MatchPlanPreview(
        source_branch=setup.source_branch,
        setup_branch=setup.setup_branch,
        chosen_focus=setup.chosen_focus,
        week8_outcome_id=setup.week8_outcome_id,
        week8_match_result=setup.week8_match_result,
        week8_scoreline=setup.week8_scoreline,
        selected_week8_plan=setup.selected_plan,
        week9_problem_id=setup.week9_problem_id,
        manager_problem=setup.manager_problem,
        selected_response=setup.selected_response,
        selected_prep=prep.selected_prep,
        selected_prep_bias=prep.selected_prep_bias,
        selected_scrim_read=scrim.selected_scrim_read,
        selected_match_plan_pressure=scrim.selected_match_plan_pressure,
        setup_read_id=scrim.setup_read_id,
        prep_read_id=scrim.prep_read_id,
        recommendation_basis=basis,
        recommended_plan=recommended,
        recommendation_reason=reason,
        match_risk=_week9_match_risk(prep, scrim, recommended),
        options=_MATCH_PLAN_OPTIONS,
    )


def resolve_week9_match_plan(
    preview: Week9MatchPlanPreview,
    selected_plan: str,
) -> Week9MatchPlanLock:
    """Resolve one Week-9 match plan into a deterministic artifact."""
    if selected_plan not in WEEK9_MATCH_PLAN_CHOICES:
        raise ValueError("selected_plan must be protect_the_room, play_the_prep, or counter_the_read")
    plan: Week9MatchPlanChoice = selected_plan  # type: ignore[assignment]
    selected = next(option for option in preview.options if option.value == plan)

    if plan == "protect_the_room":
        risk_taken = "lower_ceiling_if_match_needs_a_fast_pivot"
        thing_to_watch = "first-contact comms after the opening mistake"
        extra_constraints = ("protect_room_first", "avoid_blame_spiral")
    elif plan == "play_the_prep":
        risk_taken = "the week becomes predictable if the prep read is off"
        thing_to_watch = "whether the prep lane survives the first opponent answer"
        extra_constraints = ("trust_prep_lane", "prove_week9_process")
    else:
        risk_taken = "complexity rises before the room has a match result"
        thing_to_watch = "whether the counter lands before outside pressure grows"
        extra_constraints = ("counter_selected_read", "win_first_adjustment")

    constraints = (
        selected.result_constraint,
        f"setup:{preview.selected_response}",
        f"prep:{preview.selected_prep}",
        f"scrim:{preview.selected_scrim_read}",
        *extra_constraints,
    )
    return Week9MatchPlanLock(
        source_branch=preview.source_branch,
        setup_branch=preview.setup_branch,
        chosen_focus=preview.chosen_focus,
        week8_outcome_id=preview.week8_outcome_id,
        week8_match_result=preview.week8_match_result,
        week8_scoreline=preview.week8_scoreline,
        selected_week8_plan=preview.selected_week8_plan,
        week9_problem_id=preview.week9_problem_id,
        manager_problem=preview.manager_problem,
        selected_response=preview.selected_response,
        selected_prep=preview.selected_prep,
        selected_prep_bias=preview.selected_prep_bias,
        selected_scrim_read=preview.selected_scrim_read,
        selected_match_plan_pressure=preview.selected_match_plan_pressure,
        setup_read_id=preview.setup_read_id,
        prep_read_id=preview.prep_read_id,
        recommendation_basis=preview.recommendation_basis,
        recommended_plan=preview.recommended_plan,
        available_choices=WEEK9_MATCH_PLAN_CHOICES,
        selected_plan=plan,
        plan_label=selected.label,
        commitment=selected.commitment,
        risk_taken=risk_taken,
        thing_to_watch=thing_to_watch,
        match_risk=preview.match_risk,
        result_constraints=constraints,
        recommendation_reason=preview.recommendation_reason,
        next_hook=(
            f"Week 9 result can test {selected.commitment} against "
            f"{preview.week9_problem_id}."
        ),
    )


def week9_match_plan_from_json(text: str) -> Week9MatchPlanLock:
    """Parse a written ``week9_match_plan.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week9_match_plan JSON is malformed") from exc
    match_plan = data.get("week9_match_plan") if isinstance(data, dict) else None
    if not isinstance(match_plan, dict):
        raise ValueError("week9_match_plan JSON must contain a week9_match_plan object")
    selected = match_plan.get("selected_plan")
    if selected not in WEEK9_MATCH_PLAN_CHOICES:
        raise ValueError("week9_match_plan selected_plan must list a Week-9 match plan")
    recommended = match_plan.get("recommended_plan")
    if recommended not in WEEK9_MATCH_PLAN_CHOICES:
        raise ValueError("week9_match_plan recommended_plan must list a Week-9 match plan")
    response = match_plan.get("selected_response")
    if response not in WEEK9_RESPONSE_CHOICES:
        raise ValueError("week9_match_plan selected_response must list a Week-9 response choice")
    prep = match_plan.get("selected_prep")
    if prep not in WEEK9_PREP_CHOICES:
        raise ValueError("week9_match_plan selected_prep must list a Week-9 prep choice")
    scrim_read = match_plan.get("selected_scrim_read")
    if scrim_read not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_match_plan selected_scrim_read must list a Week-9 scrim read")
    setup_read = match_plan.get("setup_read_id")
    if setup_read not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_match_plan setup_read_id must list a Week-9 scrim read")
    prep_read = match_plan.get("prep_read_id")
    if prep_read not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_match_plan prep_read_id must list a Week-9 scrim read")
    available = match_plan.get("available_choices")
    if not isinstance(available, list) or any(choice not in WEEK9_MATCH_PLAN_CHOICES for choice in available):
        raise ValueError("week9_match_plan available_choices must list Week-9 match plans")
    focus = match_plan.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week9_match_plan chosen_focus must be contain_fallout or prove_ceiling")
    constraints = match_plan.get("result_constraints")
    if not isinstance(constraints, list):
        raise ValueError("week9_match_plan JSON must include result_constraints")
    return Week9MatchPlanLock(
        source_branch=str(match_plan.get("source_branch", "")),
        setup_branch=str(match_plan.get("setup_branch", "")),
        chosen_focus=focus,
        week8_outcome_id=str(match_plan.get("week8_outcome_id", "")),
        week8_match_result=str(match_plan.get("week8_match_result", "")),
        week8_scoreline=str(match_plan.get("week8_scoreline", "")),
        selected_week8_plan=str(match_plan.get("selected_week8_plan", "")),
        week9_problem_id=str(match_plan.get("week9_problem_id", "")),
        manager_problem=str(match_plan.get("manager_problem", "")),
        selected_response=response,
        selected_prep=prep,
        selected_prep_bias=str(match_plan.get("selected_prep_bias", "")),
        selected_scrim_read=scrim_read,
        selected_match_plan_pressure=str(match_plan.get("selected_match_plan_pressure", "")),
        setup_read_id=setup_read,
        prep_read_id=prep_read,
        recommendation_basis=str(match_plan.get("recommendation_basis", "")),
        recommended_plan=recommended,
        available_choices=tuple(available),  # type: ignore[arg-type]
        selected_plan=selected,
        plan_label=str(match_plan.get("plan_label", "")),
        commitment=str(match_plan.get("commitment", "")),
        risk_taken=str(match_plan.get("risk_taken", "")),
        thing_to_watch=str(match_plan.get("thing_to_watch", "")),
        match_risk=str(match_plan.get("match_risk", "")),
        result_constraints=tuple(str(item) for item in constraints),
        recommendation_reason=str(match_plan.get("recommendation_reason", "")),
        next_hook=str(match_plan.get("next_hook", "")),
    )


def render_week9_match_plan_json(lock: Week9MatchPlanLock) -> str:
    """Canonical JSON export for a locked Week-9 match plan."""
    payload = {
        "week9_match_plan": {
            "artifact_type": "week9_match_plan",
            "schema_version": 1,
            "source_artifacts": {
                "week9_setup": "week9_setup.json",
                "week9_prep": "week9_prep.json",
                "week9_scrim": "week9_scrim.json",
            },
            "week": 9,
            "route": "/week9/match",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week8_outcome_id": lock.week8_outcome_id,
            "week8_match_result": lock.week8_match_result,
            "week8_scoreline": lock.week8_scoreline,
            "selected_week8_plan": lock.selected_week8_plan,
            "week9_problem_id": lock.week9_problem_id,
            "manager_problem": lock.manager_problem,
            "selected_response": lock.selected_response,
            "selected_prep": lock.selected_prep,
            "selected_prep_bias": lock.selected_prep_bias,
            "selected_scrim_read": lock.selected_scrim_read,
            "selected_match_plan_pressure": lock.selected_match_plan_pressure,
            "setup_read_id": lock.setup_read_id,
            "prep_read_id": lock.prep_read_id,
            "recommendation_basis": lock.recommendation_basis,
            "recommended_plan": lock.recommended_plan,
            "available_choices": list(lock.available_choices),
            "selected_plan": lock.selected_plan,
            "plan_label": lock.plan_label,
            "commitment": lock.commitment,
            "risk_taken": lock.risk_taken,
            "thing_to_watch": lock.thing_to_watch,
            "match_risk": lock.match_risk,
            "result_constraints": list(lock.result_constraints),
            "recommendation_reason": lock.recommendation_reason,
            "next_hook": lock.next_hook,
            "stops_before": "match_result",
            "next_artifact": WEEK9_MATCH_RESULT_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


_WEEK9_RESULT_COPY: dict[Week9MatchOutcome, dict[str, str]] = {
    "room_held": {
        "headline": "The room holds when the match pushes back.",
        "recap": (
            "The opening map got loud, but the team kept the same comms language and "
            "turned the second half through cleaner first contact."
        ),
        "player_read": "Protecting the room paid off because the setup and scrim pressure were already about confidence.",
    },
    "room_cracked": {
        "headline": "The room plan absorbs too much pressure.",
        "recap": (
            "The staff protected the room, but the opponent forced faster pivots than the "
            "plan could support and the late calls got heavy."
        ),
        "player_read": "The plan missed the louder read, so stabilizing the room became reactive instead of decisive.",
    },
    "prep_converted": {
        "headline": "The prep holds under pressure.",
        "recap": (
            "The match followed the week's lane: the first answer was messy, but the team "
            "kept returning to the prep and converted the final map."
        ),
        "player_read": "Trusting the prep worked because the selected scrim read and prep lane pointed at the same test.",
    },
    "prep_stalled": {
        "headline": "The prep lane stalls on first contact.",
        "recap": (
            "The team tried to play the week exactly as practiced, but the match exposed "
            "a different pressure before the plan could settle."
        ),
        "player_read": "The prep was real, but it did not match the strongest Week 9 read.",
    },
    "read_punished": {
        "headline": "The counter lands before the story gets away.",
        "recap": (
            "The staff used the scrim read aggressively, caught the opponent's first "
            "adjustment, and made the public question look late."
        ),
        "player_read": "Countering worked because the prep and scrim both identified a punishable read.",
    },
    "counter_overreached": {
        "headline": "The counter adds one layer too many.",
        "recap": (
            "The team opened with the counter, but the extra layer slowed the room and "
            "the match was decided before the adjustment could land."
        ),
        "player_read": "The counter asked for complexity that the current room and prep chain had not earned.",
    },
}

_WEEK9_VISIBLE_EFFECTS: dict[Week9MatchOutcome, tuple[Week9VisibleEffect, ...]] = {
    "room_held": (
        Week9VisibleEffect("trust_reinforced", "Trust reinforced", "positive"),
        Week9VisibleEffect("noise_contained", "Noise contained", "positive"),
        Week9VisibleEffect("ceiling_delayed", "Ceiling delayed", "watch"),
    ),
    "room_cracked": (
        Week9VisibleEffect("room_confidence_hit", "Room confidence hit", "negative"),
        Week9VisibleEffect("pivot_speed_exposed", "Pivot speed exposed", "negative"),
        Week9VisibleEffect("fallout_needed", "Fallout needed", "watch"),
    ),
    "prep_converted": (
        Week9VisibleEffect("process_validated", "Process validated", "positive"),
        Week9VisibleEffect("prep_lane_trusted", "Prep lane trusted", "positive"),
        Week9VisibleEffect("opponent_answer_logged", "Opponent answer logged", "watch"),
    ),
    "prep_stalled": (
        Week9VisibleEffect("prep_confidence_shaken", "Prep confidence shaken", "negative"),
        Week9VisibleEffect("read_mismatch_visible", "Read mismatch visible", "negative"),
        Week9VisibleEffect("week10_review_pressure", "Review pressure", "watch"),
    ),
    "read_punished": (
        Week9VisibleEffect("counter_read_validated", "Counter read validated", "positive"),
        Week9VisibleEffect("public_angle_closed", "Public angle closed", "positive"),
        Week9VisibleEffect("complexity_spent", "Complexity spent", "watch"),
    ),
    "counter_overreached": (
        Week9VisibleEffect("complexity_punished", "Complexity punished", "negative"),
        Week9VisibleEffect("outside_pressure_rises", "Outside pressure rises", "negative"),
        Week9VisibleEffect("simplify_next", "Simplify next", "watch"),
    ),
}


def _validate_week9_result_sources(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
    plan: Week9MatchPlanLock,
) -> None:
    if setup.source_branch != prep.source_branch or setup.source_branch != scrim.source_branch:
        raise ValueError("week9 result artifacts do not agree on source branch")
    if setup.source_branch != plan.source_branch:
        raise ValueError("week9 result match plan does not agree on source branch")
    if setup.setup_branch != prep.setup_branch or setup.setup_branch != scrim.setup_branch:
        raise ValueError("week9 result artifacts do not agree on setup branch")
    if setup.setup_branch != plan.setup_branch:
        raise ValueError("week9 result match plan does not agree on setup branch")
    if setup.chosen_focus != prep.chosen_focus or setup.chosen_focus != scrim.chosen_focus:
        raise ValueError("week9 result artifacts do not agree on chosen focus")
    if setup.chosen_focus != plan.chosen_focus:
        raise ValueError("week9 result match plan does not agree on chosen focus")
    if setup.week8_outcome_id != prep.week8_outcome_id or setup.week8_outcome_id != scrim.week8_outcome_id:
        raise ValueError("week9 result artifacts do not agree on Week-8 outcome")
    if setup.week8_outcome_id != plan.week8_outcome_id:
        raise ValueError("week9 result match plan does not agree on Week-8 outcome")
    if setup.week8_match_result != prep.week8_match_result or setup.week8_match_result != scrim.week8_match_result:
        raise ValueError("week9 result artifacts do not agree on Week-8 match result")
    if setup.week8_match_result != plan.week8_match_result:
        raise ValueError("week9 result match plan does not agree on Week-8 match result")
    if setup.week8_scoreline != prep.week8_scoreline or setup.week8_scoreline != scrim.week8_scoreline:
        raise ValueError("week9 result artifacts do not agree on Week-8 scoreline")
    if setup.week8_scoreline != plan.week8_scoreline:
        raise ValueError("week9 result match plan does not agree on Week-8 scoreline")
    if setup.week9_problem_id != prep.week9_problem_id or setup.week9_problem_id != scrim.week9_problem_id:
        raise ValueError("week9 result artifacts do not agree on Week-9 problem")
    if setup.week9_problem_id != plan.week9_problem_id:
        raise ValueError("week9 result match plan does not agree on Week-9 problem")
    if setup.selected_response != prep.selected_response or setup.selected_response != scrim.selected_response:
        raise ValueError("week9 result artifacts do not agree on Week-9 response")
    if setup.selected_response != plan.selected_response:
        raise ValueError("week9 result match plan does not agree on Week-9 response")
    if prep.selected_prep != scrim.selected_prep or prep.selected_prep != plan.selected_prep:
        raise ValueError("week9 result match plan does not agree on Week-9 prep")
    if scrim.selected_scrim_read != plan.selected_scrim_read:
        raise ValueError("week9 result match plan does not agree on Week-9 scrim read")
    if scrim.setup_read_id != plan.setup_read_id or scrim.prep_read_id != plan.prep_read_id:
        raise ValueError("week9 result match plan does not agree on scrim read basis")


def _week9_match_succeeded(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
    plan: Week9MatchPlanLock,
) -> bool:
    if plan.selected_plan == plan.recommended_plan:
        return True
    if plan.selected_plan == "protect_the_room":
        return (
            setup.selected_response == "stabilize_roster"
            or scrim.selected_scrim_read == "room_read"
            or (prep.combined_confidence_delta >= 1 and plan.match_risk != "high")
        )
    if plan.selected_plan == "play_the_prep":
        return scrim.selected_scrim_read == scrim.prep_read_id and plan.match_risk != "high"
    return (
        prep.selected_prep == "counter_read"
        and scrim.selected_scrim_read in {"public_read", "tactical_read"}
        and plan.match_risk != "high"
    )


def _week9_outcome_id(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
    plan: Week9MatchPlanLock,
) -> Week9MatchOutcome:
    succeeded = _week9_match_succeeded(setup, prep, scrim, plan)
    if plan.selected_plan == "protect_the_room":
        return "room_held" if succeeded else "room_cracked"
    if plan.selected_plan == "play_the_prep":
        return "prep_converted" if succeeded else "prep_stalled"
    return "read_punished" if succeeded else "counter_overreached"


def _week9_scoreline(outcome_id: Week9MatchOutcome, plan: Week9MatchPlanLock) -> tuple[Week9MatchResultTier, int, int]:
    if outcome_id in {"room_held", "prep_converted", "read_punished"}:
        if outcome_id == "read_punished" and plan.match_risk != "high":
            return "win", 2, 0
        return "win", 2, 1
    if outcome_id == "counter_overreached" or plan.match_risk == "high":
        return "loss", 0, 2
    return "loss", 1, 2


def _week9_result_basis(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
    plan: Week9MatchPlanLock,
) -> tuple[str, ...]:
    return (
        f"plan:{plan.selected_plan}",
        f"recommended:{plan.recommended_plan}",
        f"response:{setup.selected_response}",
        f"prep:{prep.selected_prep}",
        f"scrim:{scrim.selected_scrim_read}",
        f"risk:{plan.match_risk}",
        f"pressure:{scrim.selected_match_plan_pressure}",
    )


def resolve_week9_match_result(
    setup: Week9SetupLock,
    prep: Week9PrepLock,
    scrim: Week9ScrimLock,
    plan: Week9MatchPlanLock,
) -> Week9MatchResultLock:
    """Resolve a locked Week-9 match plan into a deterministic result artifact."""
    _validate_week9_result_sources(setup, prep, scrim, plan)
    outcome_id = _week9_outcome_id(setup, prep, scrim, plan)
    result_tier, team_maps, opponent_maps = _week9_scoreline(outcome_id, plan)
    copy = _WEEK9_RESULT_COPY[outcome_id]
    return Week9MatchResultLock(
        source_branch=setup.source_branch,
        setup_branch=setup.setup_branch,
        chosen_focus=setup.chosen_focus,
        week8_outcome_id=setup.week8_outcome_id,
        week8_match_result=setup.week8_match_result,
        week8_scoreline=setup.week8_scoreline,
        selected_week8_plan=setup.selected_plan,
        week9_problem_id=setup.week9_problem_id,
        manager_problem=setup.manager_problem,
        selected_response=setup.selected_response,
        selected_prep=prep.selected_prep,
        selected_scrim_read=scrim.selected_scrim_read,
        selected_match_plan_pressure=scrim.selected_match_plan_pressure,
        selected_plan=plan.selected_plan,
        recommended_plan=plan.recommended_plan,
        matched_recommendation=plan.selected_plan == plan.recommended_plan,
        commitment=plan.commitment,
        match_risk=plan.match_risk,
        outcome_id=outcome_id,
        result_tier=result_tier,
        team_maps=team_maps,
        opponent_maps=opponent_maps,
        scoreline=f"{team_maps}-{opponent_maps}",
        headline=copy["headline"],
        recap=copy["recap"],
        player_read=copy["player_read"],
        visible_effects=_WEEK9_VISIBLE_EFFECTS[outcome_id],
        result_basis=_week9_result_basis(setup, prep, scrim, plan),
        next_hook=(
            f"Week 10 fallout can start from {outcome_id} after "
            f"{plan.selected_plan}."
        ),
    )


def week9_match_result_from_json(text: str) -> Week9MatchResultLock:
    """Parse a written ``week9_match_result.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week9_match_result JSON is malformed") from exc
    result = data.get("week9_match_result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise ValueError("week9_match_result JSON must contain a week9_match_result object")
    selected_plan = result.get("selected_plan")
    if selected_plan not in WEEK9_MATCH_PLAN_CHOICES:
        raise ValueError("week9_match_result selected_plan must list a Week-9 match plan")
    recommended_plan = result.get("recommended_plan")
    if recommended_plan not in WEEK9_MATCH_PLAN_CHOICES:
        raise ValueError("week9_match_result recommended_plan must list a Week-9 match plan")
    selected_response = result.get("selected_response")
    if selected_response not in WEEK9_RESPONSE_CHOICES:
        raise ValueError("week9_match_result selected_response must list a Week-9 response choice")
    selected_prep = result.get("selected_prep")
    if selected_prep not in WEEK9_PREP_CHOICES:
        raise ValueError("week9_match_result selected_prep must list a Week-9 prep choice")
    selected_scrim = result.get("selected_scrim_read")
    if selected_scrim not in WEEK9_SCRIM_CHOICES:
        raise ValueError("week9_match_result selected_scrim_read must list a Week-9 scrim read")
    outcome_id = result.get("outcome_id")
    if outcome_id not in WEEK9_MATCH_OUTCOMES:
        raise ValueError("week9_match_result outcome_id must list a Week-9 outcome")
    result_tier = result.get("result_tier")
    if result_tier not in ("win", "loss"):
        raise ValueError("week9_match_result result_tier must be win or loss")
    focus = result.get("chosen_focus")
    if focus not in WEEK7_FOCI:
        raise ValueError("week9_match_result chosen_focus must be contain_fallout or prove_ceiling")
    scoreline = result.get("scoreline")
    if not isinstance(scoreline, dict):
        raise ValueError("week9_match_result JSON must include scoreline")
    effects = result.get("visible_effects")
    if not isinstance(effects, list):
        raise ValueError("week9_match_result JSON must include visible_effects")
    basis = result.get("result_basis")
    if not isinstance(basis, list):
        raise ValueError("week9_match_result JSON must include result_basis")
    next_artifact = result.get("next_artifact")
    if next_artifact != WEEK10_FALLOUT_FILENAME:
        raise ValueError("week9_match_result next_artifact must be week10_fallout.json")
    return Week9MatchResultLock(
        source_branch=str(result.get("source_branch", "")),
        setup_branch=str(result.get("setup_branch", "")),
        chosen_focus=focus,
        week8_outcome_id=str(result.get("week8_outcome_id", "")),
        week8_match_result=str(result.get("week8_match_result", "")),
        week8_scoreline=str(result.get("week8_scoreline", "")),
        selected_week8_plan=str(result.get("selected_week8_plan", "")),
        week9_problem_id=str(result.get("week9_problem_id", "")),
        manager_problem=str(result.get("manager_problem", "")),
        selected_response=selected_response,
        selected_prep=selected_prep,
        selected_scrim_read=selected_scrim,
        selected_match_plan_pressure=str(result.get("selected_match_plan_pressure", "")),
        selected_plan=selected_plan,
        recommended_plan=recommended_plan,
        matched_recommendation=bool(result.get("matched_recommendation", selected_plan == recommended_plan)),
        commitment=str(result.get("commitment", "")),
        match_risk=str(result.get("match_risk", "")),
        outcome_id=outcome_id,
        result_tier=result_tier,
        team_maps=int(scoreline.get("team_maps", 0)),
        opponent_maps=int(scoreline.get("opponent_maps", 0)),
        scoreline=str(scoreline.get("display", "")),
        headline=str(result.get("headline", "")),
        recap=str(result.get("recap", "")),
        player_read=str(result.get("player_read", "")),
        visible_effects=tuple(
            Week9VisibleEffect(
                value=str(effect.get("id", "")),
                label=str(effect.get("label", "")),
                polarity=str(effect.get("polarity", "")),
            )
            for effect in effects
            if isinstance(effect, dict)
        ),
        result_basis=tuple(str(item) for item in basis),
        next_hook=str(result.get("next_hook", "")),
    )


def render_week9_match_result_json(lock: Week9MatchResultLock) -> str:
    """Canonical JSON export for a resolved Week-9 match result."""
    payload = {
        "week9_match_result": {
            "artifact_type": "week9_match_result",
            "schema_version": 1,
            "source_artifacts": {
                "week9_setup": WEEK9_SETUP_FILENAME,
                "week9_prep": WEEK9_PREP_FILENAME,
                "week9_scrim": WEEK9_SCRIM_FILENAME,
                "week9_match_plan": WEEK9_MATCH_PLAN_FILENAME,
            },
            "week": 9,
            "route": "/week9/match/result",
            "source_branch": lock.source_branch,
            "setup_branch": lock.setup_branch,
            "chosen_focus": lock.chosen_focus,
            "week8_outcome_id": lock.week8_outcome_id,
            "week8_match_result": lock.week8_match_result,
            "week8_scoreline": lock.week8_scoreline,
            "selected_week8_plan": lock.selected_week8_plan,
            "week9_problem_id": lock.week9_problem_id,
            "manager_problem": lock.manager_problem,
            "selected_response": lock.selected_response,
            "selected_prep": lock.selected_prep,
            "selected_scrim_read": lock.selected_scrim_read,
            "selected_match_plan_pressure": lock.selected_match_plan_pressure,
            "selected_plan": lock.selected_plan,
            "recommended_plan": lock.recommended_plan,
            "matched_recommendation": lock.matched_recommendation,
            "commitment": lock.commitment,
            "match_risk": lock.match_risk,
            "outcome_id": lock.outcome_id,
            "result_tier": lock.result_tier,
            "scoreline": {
                "team_maps": lock.team_maps,
                "opponent_maps": lock.opponent_maps,
                "display": lock.scoreline,
            },
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
            "next_hook": lock.next_hook,
            "stops_before": "week10_fallout",
            "next_artifact": WEEK10_FALLOUT_FILENAME,
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
