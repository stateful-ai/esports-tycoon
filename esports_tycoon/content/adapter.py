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
"""

from __future__ import annotations

from typing import Optional

from esports_tycoon.content import llm, templated
from esports_tycoon.content.config import ContentConfig, config_from_env
from esports_tycoon.content.context import GenerationContext
from esports_tycoon.content.llm import LLMClient
from esports_tycoon.schema import GeneratedContent

__all__ = ["generate_content"]


def generate_content(
    kind: str,
    ctx: GenerationContext,
    *,
    config: Optional[ContentConfig] = None,
    client: Optional[LLMClient] = None,
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
        return llm.generate(kind, ctx, config, client=client)
    # ContentConfig validates the backend at construction, so this is unreachable;
    # kept as a loud guard against a future backend being added without a route.
    raise ValueError(f"no route for content backend {config.backend!r}")
