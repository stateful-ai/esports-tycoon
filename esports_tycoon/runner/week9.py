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

WEEK9_SETUP_FILENAME = "week9_setup.json"
WEEK9_RESPONSE_CHOICES: tuple[Week9ResponseChoice, ...] = (
    "stabilize_roster",
    "double_down_read",
    "control_public_story",
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
