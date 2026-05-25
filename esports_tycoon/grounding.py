"""The grounding resolver — parse LLM cites, resolve them, regen, then drop.

This is rule #2 of the architecture made literal: LLM references to prior events
are **cites by stable ID** (``mem:<player>:<slug>``), and the renderer resolves
every one against the canned memory log. A cite that doesn't resolve is the model
inventing history, which is exactly the failure that "kills the spell"
(``scope-red-team.md`` failure mode #2). So this module:

1. **parses** the cites a generation offered (the structured ``cites`` field plus
   any ``mem:`` tokens left inline in the prose);
2. **resolves** each against the :class:`~esports_tycoon.schema.WorldState`,
   splitting them into resolved and un-resolvable; and
3. runs the **regen loop**: if anything is un-resolvable it regenerates, up to
   ``max_regen`` times (the locked ``N=2`` — see ``m0_plan_v2.md``), and if cites
   *still* don't resolve it **drops** them and stamps ``grounding_status``.

The status it stamps is precise about cite history: ``ok`` (resolved first try),
``regen`` (needed at least one regeneration but ended clean), ``dropped`` (gave
up and discarded the un-resolvable cites). A :class:`GroundingOutcome` carries the
per-piece offered/resolved/dropped counts the recap aggregates into the per-slice
grounding-rate and drop-rate.

The loop is parameterised so the one render-time gate can compose it with the
safety and cost gates without a second copy of the regen logic: ``accept`` adds an
extra acceptance test (the gate passes the safety post-filter), and ``on_attempt``
fires once per attempt (the gate meters cost there, and a cost-ceiling breach
raised from it halts the run mid-loop). Neither hook leaks back into the cite
bookkeeping: ``grounding_status`` stays about cites only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from esports_tycoon.schema import GeneratedContent, WorldState

__all__ = [
    "CITE_TOKEN_RE",
    "parse_cites",
    "offered_cites",
    "resolve_cites",
    "GroundingOutcome",
    "ground",
]

#: A *boundary-anchored* twin of ``schema.MEMORY_ID_RE`` for pulling cite tokens
#: out of free prose. The token body is identical (``mem:<player>:<event_slug>``);
#: the schema regex anchors with ``^``/``$`` for whole-string validation, while this
#: one brackets the body with non-identifier boundaries so ``findall`` can't carve a
#: well-formed cite out of a malformed run — e.g. ``xmem:rook:scrim_w5_choke`` and
#: ``mem:rook:scrim_w5_choke-extra`` must *not* yield a clean ``mem:rook:scrim_w5_choke``
#: that then resolves, which would mask the malformed cite from the grounding guard.
CITE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_:-])mem:[a-z0-9_]+:[a-z0-9]+(?:_[a-z0-9]+)*(?![A-Za-z0-9_:-])"
)

#: How many times a generation may be regenerated before its un-resolvable cites
#: are dropped. Locked at 2 (``m0_plan_v2.md``); a high drop-rate at N=2 is a
#: model/prompt smell the recap is meant to surface.
DEFAULT_MAX_REGEN = 2


def _dedup(items: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_cites(text: str) -> list[str]:
    """Extract well-formed ``mem:`` cite tokens from free text, in order, de-duped.

    The structured backend returns cites in a dedicated field, but a model may
    also leave a cite inline in the prose; this catches those so a stray inline
    cite is held to the same grounding contract.
    """
    return _dedup(CITE_TOKEN_RE.findall(text or ""))


def offered_cites(content: GeneratedContent) -> list[str]:
    """Every cite a generation *offered*, before any were dropped.

    For an LLM generation that is the model's raw ``cites`` (recovered from
    ``raw_llm_output``, which is logged precisely for this audit) — including
    malformed ones, which must still count as offered-and-un-resolvable — merged
    with any inline cites and the kept cites, de-duped in offer order. For
    templated / raw-less content it is the kept cites plus any inline tokens; the
    templated backend only ever quotes the real log, so these all resolve.
    """
    offered: list[str] = []
    if content.raw_llm_output:
        data = _safe_json(content.raw_llm_output)
        raw = data.get("cites") if isinstance(data, dict) else None
        if isinstance(raw, list):
            offered.extend(str(cite) for cite in raw)
    offered.extend(content.cites)
    offered.extend(parse_cites(content.text))
    return _dedup(offered)


def _safe_json(text: str) -> object:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def resolve_cites(world: WorldState, cites: list[str]) -> tuple[list[str], list[str]]:
    """Split ``cites`` into ``(resolved, unresolved)`` against the memory log.

    Order-preserving. A cite is resolved iff :meth:`WorldState.resolve_cite`
    finds it; malformed strings simply don't resolve, so they land in
    ``unresolved`` and are treated as drops.
    """
    resolved: list[str] = []
    unresolved: list[str] = []
    for cite in cites:
        if world.resolve_cite(cite) is not None:
            resolved.append(cite)
        else:
            unresolved.append(cite)
    return resolved, unresolved


@dataclass(frozen=True)
class GroundingOutcome:
    """Per-piece grounding bookkeeping, for the recap's per-slice rates."""

    status: str  # "ok" | "regen" | "dropped"
    attempts: int
    offered: int
    resolved: int
    dropped: int
    kept_cites: list[str] = field(default_factory=list)


def ground(
    generate: Callable[[], GeneratedContent],
    world: WorldState,
    *,
    max_regen: int = DEFAULT_MAX_REGEN,
    accept: Optional[Callable[[GeneratedContent, list[str], list[str]], bool]] = None,
    on_attempt: Optional[Callable[[GeneratedContent], None]] = None,
) -> tuple[GeneratedContent, GroundingOutcome]:
    """Generate, resolve cites, and regenerate up to ``max_regen`` times, then drop.

    ``generate`` is a zero-arg producer of a fresh :class:`GeneratedContent`
    (calling it again re-runs the model, which differs at temperature > 0). At
    most ``1 + max_regen`` attempts are made. Returns the final content — with
    un-resolvable cites dropped and ``grounding_status`` set — and a
    :class:`GroundingOutcome`.

    ``accept(content, resolved, unresolved)`` is an optional extra acceptance
    test (the gate passes the safety post-filter); when it returns ``False`` the
    piece is regenerated even if its cites resolved, but it never changes the
    cite-based ``grounding_status``. ``on_attempt(content)`` fires once per
    attempt before resolution (the gate meters cost there); an exception it raises
    — e.g. a cost-ceiling breach — propagates out and halts the run.
    """
    if max_regen < 0:
        raise ValueError("max_regen must be >= 0")

    attempts = 0
    ever_unresolved = False
    content = generate()
    offered: list[str] = []
    resolved: list[str] = []
    unresolved: list[str] = []
    while True:
        attempts += 1
        if on_attempt is not None:
            on_attempt(content)  # may raise to halt the run (e.g. cost ceiling)
        offered = offered_cites(content)
        resolved, unresolved = resolve_cites(world, offered)
        if unresolved:
            ever_unresolved = True
        accepted = (accept is None) or accept(content, resolved, unresolved)
        if (not unresolved and accepted) or attempts > max_regen:
            break
        content = generate()

    if unresolved:
        status = "dropped"
    elif ever_unresolved:
        status = "regen"
    else:
        status = "ok"

    final = content.model_copy(update={"cites": resolved, "grounding_status": status})
    outcome = GroundingOutcome(
        status=status,
        attempts=attempts,
        offered=len(offered),
        resolved=len(resolved),
        dropped=len(unresolved),
        kept_cites=list(resolved),
    )
    return final, outcome
