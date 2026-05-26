"""Backend selection for the content adapter.

One flag picks which backend :func:`~esports_tycoon.content.adapter.generate_content`
renders through:

* ``templated`` — deterministic, zero-API. **The default**, so the whole slice
  runs with no network, no keys, and no cost out of the box.
* ``vllm`` — the gaming-pack :mod:`game_llm` client against any OpenAI-compatible
  endpoint (a local vLLM in dev, a cheap hosted Qwen in prod). Endpoint, model,
  and key are configured by that client's own ``GAME_LLM_*`` env vars; this flag
  only decides *whether* to use it.

The flag is read from the ``ESPORTS_TYCOON_CONTENT_BACKEND`` environment variable
and falls back to ``templated`` when unset, so zero-API is the path of least
resistance — turning the LLM on is a deliberate act.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, get_args

__all__ = ["Backend", "ContentConfig", "BACKEND_ENV_VAR", "config_from_env"]

#: The two content backends. ``templated`` is the zero-API default.
Backend = Literal["templated", "vllm"]

#: The environment variable that selects the backend.
BACKEND_ENV_VAR = "ESPORTS_TYCOON_CONTENT_BACKEND"

_BACKENDS: tuple[str, ...] = get_args(Backend)


@dataclass(frozen=True)
class ContentConfig:
    """Resolved content-adapter configuration."""

    backend: Backend = "templated"

    def __post_init__(self) -> None:
        if self.backend not in _BACKENDS:
            raise ValueError(
                f"unknown content backend {self.backend!r}; "
                f"valid backends: {', '.join(_BACKENDS)}"
            )


def config_from_env(env: dict[str, str] | None = None) -> ContentConfig:
    """Build a :class:`ContentConfig` from the environment.

    ``env`` defaults to ``os.environ`` but can be passed explicitly (tests do).
    An unset flag yields the zero-API ``templated`` default; an unknown value
    fails loudly rather than silently falling back to the LLM.
    """
    source = os.environ if env is None else env
    backend = source.get(BACKEND_ENV_VAR, "templated").strip().lower()
    return ContentConfig(backend=backend)  # type: ignore[arg-type]  # validated in __post_init__
