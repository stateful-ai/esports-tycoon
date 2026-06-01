"""Deterministic Week-7 focus lock from a ``week7_setup`` payload.

This module is intentionally narrow: it consumes the run-local Week-7 setup
export and resolves exactly one next-block choice. No database, no season
planner, no generalized resource economy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Optional

from esports_tycoon.runner.model import Week7Setup

Week7Focus = Literal["contain_fallout", "prove_ceiling"]

WEEK7_FOCUS_FILENAME = "week7_focus.json"
WEEK7_PRESSURE_FILENAME = "week7_pressure.json"
WEEK7_FOCI: tuple[Week7Focus, ...] = ("contain_fallout", "prove_ceiling")


@dataclass(frozen=True)
class Week7SetupPayload:
    """The subset of ``week7_setup.json`` that the focus lock consumes."""

    source_branch: str
    fallout_state: str
    hook_id: str
    hook_title: str
    hook_prompt: str
    recommended_focus: Week7Focus
    review_room_trust_start: int
    review_room_trust_delta: int
    review_room_trust_final: int


@dataclass(frozen=True)
class Week7FocusOption:
    """One selectable Week-7 focus with authored preview copy."""

    value: Week7Focus
    label: str
    payoff: str
    risk: str
    recommended: bool = False


@dataclass(frozen=True)
class Week7FocusLock:
    """The deterministic artifact produced by locking a Week-7 focus."""

    hook_id: str
    hook_title: str
    chosen_focus: Week7Focus
    recommended_focus: Week7Focus
    followed_recommendation: bool
    pressure_note: str
    next_preview: str
    review_room_trust_delta: int
    ceiling_signal_delta: int
    consequence_id: Optional[str] = None
    consequence_copy: Optional[str] = None


@dataclass(frozen=True)
class Week7FocusPayload:
    """The subset of ``week7_focus.json`` that a payoff surface consumes."""

    hook_id: str
    hook_title: str
    chosen_focus: Week7Focus
    recommended_focus: Week7Focus
    followed_recommendation: bool
    review_room_trust_delta: int
    ceiling_signal_delta: int
    ignored_recommendation_cost_tag: Optional[str] = None


@dataclass(frozen=True)
class Week7PressureResult:
    """The deterministic Week-7 pressure payoff from setup + locked focus."""

    source_branch: str
    setup_branch: str
    hook_title: str
    chosen_focus: Week7Focus
    recommended_focus: Week7Focus
    matched_recommendation: bool
    outcome_id: str
    scrim_result: str
    headline: str
    review_room_beat: str
    feed_beat: str
    visible_consequence: str
    review_room_trust_delta: int
    ceiling_signal_delta: int
    relationship_heat_delta: int
    fan_confidence_delta: int


def setup_payload_from_week7_setup(setup: Week7Setup) -> Week7SetupPayload:
    """Project the in-memory setup dataclass to the import contract."""
    return Week7SetupPayload(
        source_branch=setup.source_branch,
        fallout_state=setup.fallout_state,
        hook_id=setup.hook_id,
        hook_title=setup.hook_title,
        hook_prompt=setup.hook_prompt,
        recommended_focus=setup.recommended_focus,  # type: ignore[arg-type]
        review_room_trust_start=setup.review_room_trust.start,
        review_room_trust_delta=setup.review_room_trust.delta,
        review_room_trust_final=setup.review_room_trust.final,
    )


def setup_payload_from_json(text: str) -> Week7SetupPayload:
    """Parse a ``week7_setup.json`` export into the focus-lock contract."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week7_setup JSON is malformed") from exc
    setup = data.get("week7_setup") if isinstance(data, dict) else None
    if not isinstance(setup, dict):
        raise ValueError("week7_setup JSON must contain a week7_setup object")
    hook = setup.get("next_week_hook")
    trust = setup.get("review_room_trust")
    if not isinstance(hook, dict) or not isinstance(trust, dict):
        raise ValueError("week7_setup JSON must include next_week_hook and review_room_trust")
    recommended = setup.get("recommended_focus")
    if recommended not in WEEK7_FOCI:
        raise ValueError("week7_setup recommended_focus must be contain_fallout or prove_ceiling")
    return Week7SetupPayload(
        source_branch=str(setup.get("source_branch", "")),
        fallout_state=str(setup.get("fallout_state", "")),
        hook_id=str(hook.get("id", "")),
        hook_title=str(hook.get("title", "")),
        hook_prompt=str(hook.get("prompt", "")),
        recommended_focus=recommended,
        review_room_trust_start=int(trust.get("start", 0)),
        review_room_trust_delta=int(trust.get("delta", 0)),
        review_room_trust_final=int(trust.get("final", 0)),
    )


def focus_payload_from_json(text: str) -> Week7FocusPayload:
    """Parse a ``week7_focus.json`` export into the payoff contract."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week7_focus JSON is malformed") from exc
    focus = data.get("week7_focus") if isinstance(data, dict) else None
    if not isinstance(focus, dict):
        raise ValueError("week7_focus JSON must contain a week7_focus object")
    chosen = focus.get("chosen_focus")
    recommended = focus.get("recommended_focus")
    if chosen not in WEEK7_FOCI:
        raise ValueError("week7_focus chosen_focus must be contain_fallout or prove_ceiling")
    if recommended not in WEEK7_FOCI:
        raise ValueError("week7_focus recommended_focus must be contain_fallout or prove_ceiling")
    deltas = focus.get("resource_deltas")
    if not isinstance(deltas, dict):
        raise ValueError("week7_focus JSON must include resource_deltas")
    ignored = data.get("ignored_recommendation")
    cost_tag = None
    if isinstance(ignored, dict):
        raw_cost_tag = ignored.get("cost_tag")
        cost_tag = str(raw_cost_tag) if raw_cost_tag is not None else None
    return Week7FocusPayload(
        hook_id=str(focus.get("hook_id", "")),
        hook_title=str(focus.get("hook_title", "")),
        chosen_focus=chosen,
        recommended_focus=recommended,
        followed_recommendation=bool(focus.get("followed_recommendation", chosen == recommended)),
        review_room_trust_delta=int(deltas.get("review_room_trust", 0)),
        ceiling_signal_delta=int(deltas.get("ceiling_signal", 0)),
        ignored_recommendation_cost_tag=cost_tag,
    )


def week7_focus_options(setup: Week7SetupPayload) -> tuple[Week7FocusOption, ...]:
    """The two fixed focus choices, marked with the setup's recommendation."""
    return (
        Week7FocusOption(
            value="contain_fallout",
            label="Contain fallout",
            payoff="Protects trust before the next pressure spike.",
            risk="Lower short-term pop. Gives the room less to rally around.",
            recommended=setup.recommended_focus == "contain_fallout",
        ),
        Week7FocusOption(
            value="prove_ceiling",
            label="Prove ceiling",
            payoff="Turns stability into a higher-upside scrim plan.",
            risk="More visible strain if the block misses.",
            recommended=setup.recommended_focus == "prove_ceiling",
        ),
    )


def resolve_week7_focus(setup: Week7SetupPayload, selected_focus: str) -> Week7FocusLock:
    """Resolve one Week-7 focus choice into a deterministic artifact."""
    if selected_focus not in WEEK7_FOCI:
        raise ValueError("selected_focus must be contain_fallout or prove_ceiling")
    focus: Week7Focus = selected_focus  # type: ignore[assignment]
    followed = focus == setup.recommended_focus

    if setup.hook_id == "vex_pixie_review_room_heat" and focus == "contain_fallout":
        return Week7FocusLock(
            hook_id=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus,
            recommended_focus=setup.recommended_focus,
            followed_recommendation=followed,
            pressure_note="The block opens by lowering the temperature before anyone asks for a hero fix.",
            next_preview="Trust is protected; ceiling work waits.",
            review_room_trust_delta=1,
            ceiling_signal_delta=-1,
        )
    if setup.hook_id == "vex_pixie_review_room_heat" and focus == "prove_ceiling":
        return Week7FocusLock(
            hook_id=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus,
            recommended_focus=setup.recommended_focus,
            followed_recommendation=followed,
            pressure_note="The block asks a hot room to play bigger before it has cooled down.",
            next_preview="Higher upside, but any miss will read as avoidance.",
            review_room_trust_delta=-1,
            ceiling_signal_delta=2,
            consequence_id="ignored_trust_fire",
            consequence_copy="The staff chose ceiling into heat. The room will judge the next miss faster.",
        )
    if setup.hook_id == "pixie_stability_low_clip_value" and focus == "prove_ceiling":
        return Week7FocusLock(
            hook_id=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus,
            recommended_focus=setup.recommended_focus,
            followed_recommendation=followed,
            pressure_note="The block treats stability as a platform, not a finish line.",
            next_preview="Ceiling work opens while trust is still available.",
            review_room_trust_delta=0,
            ceiling_signal_delta=2,
        )
    if setup.hook_id == "pixie_stability_low_clip_value" and focus == "contain_fallout":
        return Week7FocusLock(
            hook_id=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus,
            recommended_focus=setup.recommended_focus,
            followed_recommendation=followed,
            pressure_note="The block spends a stable moment on caution.",
            next_preview="Trust stays safe, but the team may lose a chance to press advantage.",
            review_room_trust_delta=1,
            ceiling_signal_delta=-1,
            consequence_id="overcorrected_stability",
            consequence_copy=(
                "The staff chose caution into stability. The next preview should show "
                "delayed upside, not collapse."
            ),
        )
    raise ValueError(f"unsupported week7 hook/focus pair: {setup.hook_id!r}/{focus!r}")


def render_week7_focus_json(lock: Week7FocusLock) -> str:
    """Canonical JSON export for a selected Week-7 focus."""
    payload = {
        "week7_focus": {
            "artifact_type": "week7_focus",
            "hook_id": lock.hook_id,
            "hook_title": lock.hook_title,
            "chosen_focus": lock.chosen_focus,
            "recommended_focus": lock.recommended_focus,
            "followed_recommendation": lock.followed_recommendation,
            "pressure_note": lock.pressure_note,
            "next_preview": lock.next_preview,
            "resource_deltas": {
                "review_room_trust": lock.review_room_trust_delta,
                "ceiling_signal": lock.ceiling_signal_delta,
            },
        }
    }
    if lock.consequence_id is not None:
        payload["ignored_recommendation"] = {
            "artifact_type": "ignored_recommendation",
            "hook_id": lock.hook_id,
            "chosen_focus": lock.chosen_focus,
            "cost_tag": lock.consequence_id,
            "copy": lock.consequence_copy or "",
        }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def resolve_week7_pressure(
    setup: Week7SetupPayload, focus: Week7FocusPayload
) -> Week7PressureResult:
    """Resolve the locked Week-7 focus into the next deterministic payoff."""
    if setup.hook_id != focus.hook_id:
        raise ValueError("week7 setup and focus hook_id do not match")
    if setup.recommended_focus != focus.recommended_focus:
        raise ValueError("week7 setup and focus recommended_focus do not match")

    if setup.hook_id == "vex_pixie_review_room_heat" and focus.chosen_focus == "contain_fallout":
        return Week7PressureResult(
            source_branch=setup.source_branch,
            setup_branch=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus.chosen_focus,
            recommended_focus=focus.recommended_focus,
            matched_recommendation=focus.followed_recommendation,
            outcome_id="heat_contained_scrappy_win",
            scrim_result="win_2_1",
            headline="Ugly 2-1, room steadier",
            review_room_beat=(
                "Vex accepts the first correction; Pixie speaks once without getting buried."
            ),
            feed_beat="Fans call it ugly. Staff call it necessary.",
            visible_consequence="review_trust_repaired",
            review_room_trust_delta=2,
            ceiling_signal_delta=-1,
            relationship_heat_delta=-2,
            fan_confidence_delta=0,
        )
    if setup.hook_id == "vex_pixie_review_room_heat" and focus.chosen_focus == "prove_ceiling":
        return Week7PressureResult(
            source_branch=setup.source_branch,
            setup_branch=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus.chosen_focus,
            recommended_focus=focus.recommended_focus,
            matched_recommendation=focus.followed_recommendation,
            outcome_id="heat_ignored_highlight_loss",
            scrim_result="loss_1_2",
            headline="Vex clip, room worse",
            review_room_beat="Vex looks vindicated; Pixie checks out after the second map.",
            feed_beat="One clip goes viral, but the room looks worse.",
            visible_consequence=focus.ignored_recommendation_cost_tag or "ignored_trust_fire",
            review_room_trust_delta=-2,
            ceiling_signal_delta=2,
            relationship_heat_delta=2,
            fan_confidence_delta=1,
        )
    if setup.hook_id == "pixie_stability_low_clip_value" and focus.chosen_focus == "prove_ceiling":
        return Week7PressureResult(
            source_branch=setup.source_branch,
            setup_branch=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus.chosen_focus,
            recommended_focus=focus.recommended_focus,
            matched_recommendation=focus.followed_recommendation,
            outcome_id="stability_unlocked_clean_2_0",
            scrim_result="win_2_0",
            headline="Stable base, higher ceiling",
            review_room_beat="The room trusts the prep enough to push harder next block.",
            feed_beat="Analysts finally notice the ceiling.",
            visible_consequence="ceiling_proven",
            review_room_trust_delta=1,
            ceiling_signal_delta=3,
            relationship_heat_delta=0,
            fan_confidence_delta=2,
        )
    if setup.hook_id == "pixie_stability_low_clip_value" and focus.chosen_focus == "contain_fallout":
        return Week7PressureResult(
            source_branch=setup.source_branch,
            setup_branch=setup.hook_id,
            hook_title=setup.hook_title,
            chosen_focus=focus.chosen_focus,
            recommended_focus=focus.recommended_focus,
            matched_recommendation=focus.followed_recommendation,
            outcome_id="stability_overmanaged_flat_win",
            scrim_result="win_2_1",
            headline="Quiet win, low clip value",
            review_room_beat="Nobody fights the plan, but nobody learns much either.",
            feed_beat="Quiet win, low clip value.",
            visible_consequence="overmanaged_stability",
            review_room_trust_delta=0,
            ceiling_signal_delta=-2,
            relationship_heat_delta=-1,
            fan_confidence_delta=-1,
        )
    raise ValueError(
        f"unsupported week7 pressure pair: {setup.hook_id!r}/{focus.chosen_focus!r}"
    )


def render_week7_pressure_json(result: Week7PressureResult) -> str:
    """Canonical JSON export for a resolved Week-7 pressure payoff."""
    payload = {
        "week7_pressure": {
            "artifact_type": "week7_pressure",
            "schema_version": 1,
            "source_setup_artifact": "week7_setup.json",
            "source_focus_artifact": "week7_focus.json",
            "week": 7,
            "source_branch": result.source_branch,
            "setup_branch": result.setup_branch,
            "hook_title": result.hook_title,
            "chosen_focus": result.chosen_focus,
            "recommended_focus": result.recommended_focus,
            "matched_recommendation": result.matched_recommendation,
            "outcome_id": result.outcome_id,
            "scrim_result": result.scrim_result,
            "headline": result.headline,
            "review_room_beat": result.review_room_beat,
            "feed_beat": result.feed_beat,
            "visible_consequence": result.visible_consequence,
            "deltas": {
                "review_room_trust": result.review_room_trust_delta,
                "ceiling_signal": result.ceiling_signal_delta,
                "relationship_heat": result.relationship_heat_delta,
                "fan_confidence": result.fan_confidence_delta,
            },
        }
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
