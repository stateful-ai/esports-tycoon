"""The content layer: turn match facts + memory into rendered, grounded prose.

One interface — :func:`generate_content` — renders the M0 content kinds through a
config-selected backend:

* ``templated`` (default): deterministic, zero-API.
* ``vllm``: the gaming-pack OpenAI-compatible client (opt-in, env-configured).

    from esports_tycoon.content import generate_content, GenerationContext
    post = generate_content("chirper_post", GenerationContext(world=w, why=r, author="vex"))

The resolver never imports this package — generation consumes the resolver's
finished :class:`~esports_tycoon.schema.WhyRecord`, never the other way round.
"""

from esports_tycoon.content.adapter import generate_content
from esports_tycoon.content.config import (
    BACKEND_ENV_VAR,
    Backend,
    ContentConfig,
    config_from_env,
)
from esports_tycoon.content.context import GenerationContext

__all__ = [
    "generate_content",
    "GenerationContext",
    "ContentConfig",
    "Backend",
    "BACKEND_ENV_VAR",
    "config_from_env",
]
