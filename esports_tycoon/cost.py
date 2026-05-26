"""The per-slice cost meter — the gate that halts a run on a $ ceiling breach.

This is rule #3 of the architecture made literal on the money side: LLM mode is
*gated by cost*. One :class:`CostMeter` is created per slice run and threaded
through every generation (see :mod:`esports_tycoon.gate`); it accumulates token
usage, prices it through a :class:`CostModel`, and the instant the running spend
crosses the ceiling it raises :class:`CostCeilingExceeded` — which propagates out
of the gate and halts the whole run rather than quietly overspending.

The M0 inference path is a local vLLM, which is free, so the default
:class:`CostModel` prices every token at ``$0`` and a real slice never trips the
ceiling. The meter still does real work: it carries the *token* totals the recap
reports, and the moment a hosted (paid) model is configured behind the same
adapter the ceiling becomes a live fail-closed guard with no code change — only a
:class:`CostModel` and a ceiling.

Token usage is estimated, not billed: the OpenAI-compatible endpoints behind the
gaming-pack client don't reliably surface a usage block, so the content backend
estimates ``tokens_in``/``tokens_out`` from the prompt and reply (see
:func:`estimate_tokens`) and the meter prices those. The estimate is the same
cheap heuristic everywhere, so the cost number is consistent and monotonic — good
enough to fail-closed a ceiling, which is the meter's whole job.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "CHARS_PER_TOKEN",
    "DEFAULT_CEILING_USD",
    "estimate_tokens",
    "CostModel",
    "CallCost",
    "CostCeilingExceeded",
    "CostMeter",
]

#: Rough characters-per-token for English text. The real ratio is model- and
#: text-dependent (~3.5–4.5); 4 is the conventional estimate and the exact value
#: doesn't matter — the meter only needs a stable, monotonic proxy to gate on.
CHARS_PER_TOKEN = 4

#: The planning-default per-slice ceiling (USD). ``m0_plan_v2.md`` open decision
#: #2 leaves the concrete figure to the founder; $0.50/slice is the proposed
#: default from the build reconciliation brief. With the local-vLLM cost model
#: (free) a slice spends $0, well under this; it bites only behind a paid model.
DEFAULT_CEILING_USD = 0.50


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` (0 for empty/whitespace).

    A deliberately cheap, dependency-free heuristic — ``ceil(len / 4)`` — shared
    by the content backend (to stamp ``tokens_in``/``tokens_out`` on its output)
    and by anything that needs a number without a tokenizer. Consistency matters
    more than precision here: the same text always estimates the same way.
    """
    if not text:
        return 0
    stripped = text.strip()
    if not stripped:
        return 0
    return math.ceil(len(stripped) / CHARS_PER_TOKEN)


@dataclass(frozen=True)
class CostModel:
    """Per-token pricing, in USD per 1000 tokens.

    Defaults to the M0 local-vLLM reality: free. A hosted model is a single
    construction change (``CostModel(usd_per_1k_input=..., usd_per_1k_output=...)``)
    behind the same adapter and meter.
    """

    usd_per_1k_input: float = 0.0
    usd_per_1k_output: float = 0.0

    def __post_init__(self) -> None:
        if self.usd_per_1k_input < 0 or self.usd_per_1k_output < 0:
            raise ValueError("CostModel prices must be non-negative")

    def price(self, tokens_in: int, tokens_out: int) -> float:
        """USD cost of ``tokens_in`` prompt + ``tokens_out`` completion tokens."""
        return (
            tokens_in / 1000.0 * self.usd_per_1k_input
            + tokens_out / 1000.0 * self.usd_per_1k_output
        )


@dataclass(frozen=True)
class CallCost:
    """The cost a single metered unit of work added to the slice."""

    tokens_in: int
    tokens_out: int
    cost_usd: float


class CostCeilingExceeded(RuntimeError):
    """Raised when the running per-slice spend crosses the configured ceiling.

    Carries the breach figures so the caller (the slice runner) can record *why*
    the run halted in the recap. Propagating this out of the gate is the halt:
    no further content is generated once the ceiling is crossed.
    """

    def __init__(self, *, spent_usd: float, ceiling_usd: float, calls: int) -> None:
        self.spent_usd = spent_usd
        self.ceiling_usd = ceiling_usd
        self.calls = calls
        super().__init__(
            f"per-slice cost ceiling exceeded: spent ${spent_usd:.4f} > "
            f"ceiling ${ceiling_usd:.4f} after {calls} metered call(s); run halted"
        )


class CostMeter:
    """A running per-slice token/$ accumulator with a fail-closed ceiling.

    One meter lives for the duration of a slice run and is shared across every
    generation, so its totals *are* the per-slice cost. Each :meth:`record`
    accumulates usage and, if the running spend then exceeds the ceiling, raises
    :class:`CostCeilingExceeded` — fail-closed by design: the breaching call's
    usage is still counted (it happened) and the run stops.

    ``ceiling_usd=None`` disables the ceiling (unbounded) for callers that only
    want accounting; the default is :data:`DEFAULT_CEILING_USD`.
    """

    def __init__(
        self,
        ceiling_usd: Optional[float] = DEFAULT_CEILING_USD,
        model: Optional[CostModel] = None,
    ) -> None:
        if ceiling_usd is not None and ceiling_usd < 0:
            raise ValueError("cost ceiling must be non-negative or None")
        self.ceiling_usd = ceiling_usd
        self.model = model or CostModel()
        self._tokens_in = 0
        self._tokens_out = 0
        self._cost_usd = 0.0
        self._calls = 0

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def spent_usd(self) -> float:
        return self._cost_usd

    @property
    def calls(self) -> int:
        return self._calls

    def record(self, tokens_in: int, tokens_out: int) -> CallCost:
        """Add one unit of usage to the slice total; halt if it breaches.

        Returns the :class:`CallCost` this call contributed. Raises
        :class:`CostCeilingExceeded` *after* accumulating if the new running
        spend crosses the ceiling — so the totals always reflect everything that
        was actually generated, including the call that tipped it over.
        """
        if tokens_in < 0 or tokens_out < 0:
            raise ValueError("token counts must be non-negative")
        cost = self.model.price(tokens_in, tokens_out)
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out
        self._cost_usd += cost
        self._calls += 1
        if self.ceiling_usd is not None and self._cost_usd > self.ceiling_usd:
            raise CostCeilingExceeded(
                spent_usd=self._cost_usd, ceiling_usd=self.ceiling_usd, calls=self._calls
            )
        return CallCost(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
