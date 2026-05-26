"""OpenAI-endpoint smoke test: is the local vLLM up, structured, and warm-fast?

This is the bring-up acceptance check — *"`curl /v1/chat/completions` returns a
structured response under 5s warm"* — and the **step zero** before the demo
preflight (:mod:`~esports_tycoon.vllm_demo.preflight`): preflight assumes a
healthy endpoint and runs the whole slice through it; this proves the endpoint is
healthy first, in one cheap call, so a red preflight isn't mistaken for a bad
model when the server is simply down or cold.

It talks to the endpoint through the **exact client the game uses**
(:meth:`game_llm.GameLLM.structured` — prompted JSON validated into a pydantic
model), so a green smoke means the game's own LLM path works end to end, not just
that the port answers. Three things are asserted, mirroring the acceptance bar:

* **reachable** — the request completes without raising (endpoint up, model
  loaded, ``GAME_LLM_*`` pointed right, ``openai`` installed);
* **structured** — the reply parses into the expected schema (the model returns
  usable JSON, not free prose); and
* **warm-fast** — the *warm* call (after a warm-up round-trip that absorbs vLLM's
  first-request graph capture / weight load) lands within the latency budget,
  default ``5.0`` seconds.

The client is injected (``client=`` / the env-configured
:func:`game_llm.get_llm` default), so the CLI runs it against the real local
endpoint while the tests exercise every branch against a duck-typed stand-in with
no network.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

from esports_tycoon.content import game_llm

__all__ = [
    "DEFAULT_BUDGET_SECONDS",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_PROMPT",
    "SmokeResult",
    "run_smoke",
]

#: The warm-latency budget the bring-up acceptance criterion names.
DEFAULT_BUDGET_SECONDS = 5.0
#: A tiny output cap — the smoke only needs a two-field object, and a small cap is
#: the cheapest, fastest round-trip that still proves the structured path.
DEFAULT_MAX_TOKENS = 64
#: The smoke prompt. Deliberately content-free (no game fiction): this checks the
#: transport + structured-decode path, not tone or grounding.
DEFAULT_PROMPT = (
    "Reply with a JSON object reporting that you are reachable. "
    'Set "ready" to true and "note" to a single short word.'
)

_SYSTEM = (
    "You are a health probe for a local LLM server. Answer only with the JSON "
    "object the user asks for."
)


class _SmokePing(BaseModel):
    """The minimal structured shape the smoke asks the endpoint to return."""

    ready: bool
    note: str = ""


@dataclass(frozen=True)
class SmokeResult:
    """The verdict of one endpoint smoke test.

    :attr:`ok` is the single gate signal — reachable **and** structured **and**
    within the warm-latency budget. The component fields are kept so a failure is
    actionable rather than just a red light: ``error`` names a transport/parse
    failure, ``structured_ok`` distinguishes a parse miss from a slow-but-valid
    reply, and :attr:`within_budget` isolates the latency verdict.
    """

    ok: bool
    model: str
    reachable: bool
    structured_ok: bool
    latency_seconds: float
    budget_seconds: float
    warmup_seconds: Optional[float]
    reply: Optional[dict]
    error: Optional[str]

    @property
    def within_budget(self) -> bool:
        """Whether the *warm* call met the budget. Only meaningful once
        :attr:`structured_ok` (a call that never returned has no honest latency)."""
        return self.structured_ok and self.latency_seconds <= self.budget_seconds


def run_smoke(
    client: Optional[object] = None,
    *,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    prompt: str = DEFAULT_PROMPT,
    warmup: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> SmokeResult:
    """Probe the endpoint once (after an optional warm-up) and report the verdict.

    ``client`` defaults to the env-configured process client
    (:func:`game_llm.get_llm`) — the real local-Qwen endpoint; pass a stand-in to
    exercise the smoke without a live server. ``warmup`` runs one untimed
    round-trip first so the *measured* call is genuinely warm (vLLM pays graph
    capture / weight load on the first request); turn it off to measure a cold
    call. Any transport or decode failure is caught and reported as
    ``ok=False`` with ``error`` set — the smoke never raises, so a CLI/caller can
    branch on the result.
    """
    # Default before the client exists, so a get_llm() failure (e.g. the `vllm`
    # extra / openai not installed) is still reportable with a sensible model name.
    model = game_llm._DEFAULTS["GAME_LLM_MODEL"]
    warmup_seconds: Optional[float] = None
    try:
        delegate = client if client is not None else game_llm.get_llm()
        model = getattr(delegate, "model", None) or model

        if warmup:
            w0 = time.perf_counter()
            delegate.structured(prompt, _SmokePing, system=_SYSTEM, max_tokens=max_tokens)
            warmup_seconds = time.perf_counter() - w0

        t0 = time.perf_counter()
        reply = delegate.structured(prompt, _SmokePing, system=_SYSTEM, max_tokens=max_tokens)
        latency_seconds = time.perf_counter() - t0
    except Exception as exc:  # noqa: BLE001 — endpoint/dep/parse failures are the verdict
        return SmokeResult(
            ok=False,
            model=model,
            reachable=False,
            structured_ok=False,
            latency_seconds=0.0,
            budget_seconds=budget_seconds,
            warmup_seconds=warmup_seconds,
            reply=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    structured_ok = isinstance(reply, _SmokePing)
    within_budget = latency_seconds <= budget_seconds
    return SmokeResult(
        ok=structured_ok and within_budget,
        model=model,
        reachable=True,
        structured_ok=structured_ok,
        latency_seconds=latency_seconds,
        budget_seconds=budget_seconds,
        warmup_seconds=warmup_seconds,
        reply=reply.model_dump() if structured_ok else None,
        error=None,
    )
