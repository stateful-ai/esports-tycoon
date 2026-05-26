"""The content adapter: one ``generate_content(kind, ctx)`` seam, two backends.

This is the ``generateContent(kind, ctx) -> GeneratedContent`` interface from the
M0 technical plan. Everything that wants rendered prose — the TUI, the Chirper
feed builder, the static ``feed.html`` dump — goes through this one call and stays
ignorant of *how* the text was produced. A single config flag (see
:mod:`~esports_tycoon.content.config`) routes each call to one of two backends:

* ``templated`` — deterministic, zero-API. The default.
* ``vllm`` — the gaming-pack LLM client against an OpenAI-compatible endpoint.

Both return the same :class:`~esports_tycoon.schema.GeneratedContent`, so a caller
can flip backends with an env change and nothing downstream moves.

Direction of dependency matters and is one-way: the adapter imports the resolver's
*output* type (``WhyRecord``, via the context) but the resolver never imports the
adapter — narration consumes a finished record; generation can't leak back into
the deterministic sim.

The default ``templated`` backend is imported eagerly (it is pure-stdlib, zero
dependency). The opt-in ``vllm`` backend is imported **lazily**, inside the branch
that selects it, so the no-install default never even loads the LLM module — the
zero-API guarantee holds by construction, not by trusting the verbatim-vendored
``game_llm`` to keep deferring its ``openai`` import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from esports_tycoon.content import templated
from esports_tycoon.content.config import ContentConfig, config_from_env
from esports_tycoon.content.context import GenerationContext
from esports_tycoon.schema import GeneratedContent

if TYPE_CHECKING:
    # Type-only: the symbol is needed for the signature below but must not pull the
    # opt-in backend into the always-imported path at runtime.
    from esports_tycoon.content.llm import LLMClient

__all__ = ["generate_content"]


def generate_content(
    kind: str,
    ctx: GenerationContext,
    *,
    config: Optional[ContentConfig] = None,
    client: Optional["LLMClient"] = None,
) -> GeneratedContent:
    """Render ``kind`` from ``ctx`` through the configured backend.

    ``kind`` is one of ``"chirper_post"``, ``"narration"``, ``"halftime_ack"``.
    ``config`` defaults to :func:`config_from_env` (so the backend follows the
    ``ESPORTS_TYCOON_CONTENT_BACKEND`` env var, defaulting to ``templated``).
    ``client`` overrides the LLM client and is honoured only by the ``vllm``
    backend; the ``templated`` backend ignores it and makes no API call.
    """
    config = config or config_from_env()
    if config.backend == "templated":
        return templated.render(kind, ctx)
    if config.backend == "vllm":
        # Imported here, not at module top: selecting vllm is what pulls in the
        # gaming-pack client (and, only when a client is constructed, ``openai``).
        from esports_tycoon.content import llm

        return llm.generate(kind, ctx, config, client=client)
    # ContentConfig validates the backend at construction, so this is unreachable;
    # kept as a loud guard against a future backend being added without a route.
    raise ValueError(f"no route for content backend {config.backend!r}")
