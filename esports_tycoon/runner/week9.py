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

WEEK9_SETUP_FILENAME = "week9_setup.json"
WEEK9_PREP_FILENAME = "week9_prep.json"
WEEK9_SCRIM_FILENAME = "week9_scrim.json"
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
