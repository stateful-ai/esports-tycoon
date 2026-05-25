"""The one render-time gate: safety + grounding + cost in a single pass.

Every piece of generated content flows through :func:`render` before it reaches
the Chirper feed or the recap. This is the single choke point the three
red-team rules converge on (``scope-red-team.md``, ``m0_plan_v2.md``):

* **safety** (:mod:`esports_tycoon.safety`) — the input is pre-filtered before it
  ever reaches the model, and every completion is post-filtered; an unsafe
  completion is regenerated and, if it stays unsafe, withheld.
* **grounding** (:mod:`esports_tycoon.grounding`) — cites are parsed, resolved
  against the canned log, regenerated up to ``N=2``, then dropped.
* **cost** (:mod:`esports_tycoon.cost`) — every attempt (regens included) is
  metered, and a per-slice ceiling breach raises out of here and halts the run.

These share *one* regen loop: the gate hands :func:`grounding.ground` an ``accept``
predicate (safety must also pass) and an ``on_attempt`` hook (the cost meter), so
a regeneration is triggered by an un-resolvable cite *or* an unsafe completion,
and the same attempt budget covers both. The gate is backend-agnostic: it drives
a caller-supplied ``generate`` callable, never importing the templated or vLLM
backend, so it composes over either and never pulls the opt-in ``openai`` path.

The result of one render is a :class:`GateResult` — the final, safe, grounded
content plus the per-gate bookkeeping the recap aggregates. The cost meter is
passed in (one per slice) so its running total *is* the per-slice spend and a
breach anywhere stops the whole run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from esports_tycoon import grounding, safety
from esports_tycoon.cost import CallCost, CostMeter
from esports_tycoon.grounding import GroundingOutcome
from esports_tycoon.safety import SafetyVerdict
from esports_tycoon.schema import GeneratedContent, WorldState

__all__ = [
    "WITHHELD_TEXT",
    "UnsafeInputError",
    "GateResult",
    "render",
]

#: What a completion's text is replaced with when it cannot be made safe within
#: the regen budget. The piece is kept (so the recap can count it) but carries no
#: unsafe prose and no cites.
WITHHELD_TEXT = "[withheld: failed safety filter]"


class UnsafeInputError(ValueError):
    """Raised when a manager open-text input fails the safety pre-filter.

    The unsafe text never reaches the model: the caller (the slice runner) should
    reject the input and re-prompt rather than spend tokens amplifying it.
    """

    def __init__(self, text: str, verdict: SafetyVerdict) -> None:
        self.text = text
        self.verdict = verdict
        super().__init__(
            "open-text input rejected by safety pre-filter "
            f"({', '.join(verdict.categories)})"
        )


@dataclass(frozen=True)
class GateResult:
    """The outcome of pushing one generation through the render-time gate."""

    content: GeneratedContent  # final: safe, grounded, priced
    grounding: GroundingOutcome
    safety: SafetyVerdict  # verdict on the final completion
    cost: CallCost  # this render's total usage (all attempts), priced
    blocked: bool  # True if the completion was withheld for safety
    attempts: int


def render(
    generate: Callable[[], GeneratedContent],
    *,
    world: WorldState,
    meter: CostMeter,
    max_regen: int = grounding.DEFAULT_MAX_REGEN,
    inputs: Optional[list[str]] = None,
) -> GateResult:
    """Push one generation through the safety + grounding + cost gate.

    ``generate`` is a zero-arg producer of a fresh
    :class:`~esports_tycoon.schema.GeneratedContent` (typically a closure over the
    chosen backend, kind, and context); it is called once, then again per
    regeneration. ``meter`` is the per-slice
    :class:`~esports_tycoon.cost.CostMeter`. ``inputs``, if given, are manager
    open-text moments pre-filtered before any generation — an unsafe one raises
    :class:`UnsafeInputError`.

    Raises :class:`~esports_tycoon.cost.CostCeilingExceeded` (out of the meter)
    the moment the per-slice spend crosses the ceiling, which halts the run.
    """
    # --- pre-filter: never feed unsafe manager text to the model -------------- #
    for text in inputs or []:
        verdict = safety.screen(text)
        if not verdict.ok:
            raise UnsafeInputError(text, verdict)

    # --- one regen loop, metering every attempt and requiring safe output ----- #
    def on_attempt(content: GeneratedContent) -> None:
        # Meter this attempt's usage. The meter may raise CostCeilingExceeded,
        # which propagates out of render() and halts the run; the breaching
        # attempt is still counted (it happened).
        meter.record(content.tokens_in, content.tokens_out)

    def accept(content: GeneratedContent, _resolved: list[str], _unresolved: list[str]) -> bool:
        return safety.is_safe(content.text)

    before = (meter.tokens_in, meter.tokens_out, meter.spent_usd)
    final, outcome = grounding.ground(
        generate, world, max_regen=max_regen, accept=accept, on_attempt=on_attempt
    )
    # This render's cost is the slice meter's delta across its attempts.
    cost = CallCost(
        tokens_in=meter.tokens_in - before[0],
        tokens_out=meter.tokens_out - before[1],
        cost_usd=meter.spent_usd - before[2],
    )

    # --- post-filter the survivor: if still unsafe, withhold it --------------- #
    verdict = safety.screen(final.text)
    blocked = not verdict.ok
    if blocked:
        final = final.model_copy(update={"text": WITHHELD_TEXT, "cites": []})

    # Stamp the gate-priced cost onto the content so the recap can read it back.
    final = final.model_copy(update={"cost_usd": cost.cost_usd})

    return GateResult(
        content=final,
        grounding=outcome,
        safety=verdict,
        cost=cost,
        blocked=blocked,
        attempts=outcome.attempts,
    )
