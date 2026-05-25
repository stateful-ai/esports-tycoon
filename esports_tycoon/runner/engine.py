"""The headless slice engine: one week of play, practice → match → fallout.

This is the slice runner with no UI attached. :func:`run_slice` takes the loaded
:class:`~esports_tycoon.schema.WorldState`, the fixed :class:`SliceConfig`, and the
player's :class:`SliceDecisions`, and runs the week end-to-end:

1. **Practice** sets the structured resolver inputs (the MC focus + the fixture).
2. **Match** is the pure, seeded resolver producing a :class:`WhyRecord`; the
   templated content adapter narrates it and the IGL acks the half.
3. **Fallout** assembles the week-6 Chirper feed — each fielded starter reacts in
   character, a caster and the opponent's star chime in, and the manager's public
   open-text line leads as the org's official word.

Everything here is **deterministic**: the resolver is seeded, the templated
adapter is seeded from stable fields, and the run carries no clock or entropy of
its own. The :func:`slice_id` is content-addressed — a hash of the save, seed, and
every decision — so the same inputs always land in the same ``runs/<slice_id>/``
folder with byte-identical artifacts, and a changed open-text line gets its own.

The Flask layer in :mod:`esports_tycoon.web` is a thin shell over this engine; the
acceptance-critical behaviour (determinism, the artifact contract) lives here and
is tested here, with no web dependency.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Optional

from esports_tycoon import resolver
from esports_tycoon.content import GenerationContext, generate_content
from esports_tycoon.content.config import ContentConfig
from esports_tycoon.runner.model import (
    FeedPost,
    SliceConfig,
    SliceDecisions,
    SliceResult,
)
from esports_tycoon.schema import GeneratedContent, WhyRecord, WorldState

if TYPE_CHECKING:
    # Type-only: naming the injected client must not pull the opt-in vllm backend
    # (and its ``openai`` dep) onto the always-imported templated path.
    from esports_tycoon.content.llm import LLMClient

__all__ = ["run_slice", "slice_id", "halftime_scoreline"]

#: First-to-13: sides swap after 12 rounds, so the half-time read is the score at
#: the end of round 12 (or the final score if the series ended sooner).
_HALFTIME_ROUND = 12

#: An in-universe caster who covers every week — an external voice (no persona, no
#: cite), there for colour in the feed.
_CASTER_HANDLE = "@gridcast"
_CASTER_NAME = "GridCast"


def slice_id(world: WorldState, config: SliceConfig, decisions: SliceDecisions) -> str:
    """A short, stable id for this run, derived from its full input.

    Content-addressed on purpose: identical inputs ⇒ identical id ⇒ the same
    ``runs/<slice_id>/`` folder re-written with identical bytes, which is exactly
    the "identical recap on re-run with the same seed" contract. A different
    open-text line, opponent, or seed yields a different id and its own folder.
    """
    payload = json.dumps(
        {
            "save": world.save.id,
            "week": world.save.season.current_week,
            "seed": config.seed,
            "opponent": config.opponent,
            "map": config.map,
            "stance": config.tactical_stance,
            "practice": decisions.practice_focus,
            "team_talk": decisions.team_talk,
            "fallout_post": decisions.fallout_post,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"wk{world.save.season.current_week}-{digest}"


def halftime_scoreline(why: WhyRecord, team_id: str) -> tuple[int, int]:
    """The ``(overcast, opponent)`` score at the half, read from the round log.

    Counts won rounds rather than parsing summaries so it stays correct if the
    summary format ever changes.
    """
    first_half = [r for r in why.round_log if r.round <= _HALFTIME_ROUND]
    overcast = sum(1 for r in first_half if r.winner == team_id)
    return overcast, len(first_half) - overcast


def _first_name(name: str) -> str:
    """A display first name, robust to handles like ``Mariana "Vex" Okonkwo``."""
    if '"' in name:
        return name.split('"')[1]
    return name.split()[0] if name.split() else name


def _build_feed(
    world: WorldState,
    config: SliceConfig,
    decisions: SliceDecisions,
    why: WhyRecord,
    content_config: ContentConfig,
    client: Optional["LLMClient"] = None,
) -> tuple[tuple[FeedPost, ...], list[GeneratedContent]]:
    """The week-6 Chirper feed, plus the grounded content pieces it generated.

    Order is fixed and meaningful: the org's official line first (if the manager
    posted one), then the five starters in roster order reacting in character,
    then the external voices. Only the starter reactions attempt grounding, so
    only they feed the grounding rate.
    """
    posts: list[FeedPost] = []
    grounded: list[GeneratedContent] = []

    if decisions.fallout_post:
        posts.append(
            FeedPost(
                author_handle=world.save.team.handle,
                author_name=world.save.team.name,
                text=decisions.fallout_post,
            )
        )

    fielded = set(why.morale_deltas)
    for player in world.players:
        if player.id not in fielded:
            continue
        gc = generate_content(
            "chirper_post",
            GenerationContext(world=world, why=why, author=player.id),
            config=content_config,
            client=client,
        )
        grounded.append(gc)
        posts.append(
            FeedPost(
                author_handle=gc.author or player.handle,
                author_name=_first_name(player.name),
                text=gc.text,
                cites=tuple(gc.cites),
                grounding_status=gc.grounding_status,
            )
        )

    caster = generate_content(
        "chirper_post",
        GenerationContext(world=world, why=why, author=_CASTER_HANDLE),
        config=content_config,
        client=client,
    )
    posts.append(FeedPost(_CASTER_HANDLE, _CASTER_NAME, caster.text, tuple(caster.cites), caster.grounding_status))

    rival = next((r for r in world.rivals if r.id == config.opponent), None)
    if rival is not None:
        star = generate_content(
            "chirper_post",
            GenerationContext(world=world, why=why, author=rival.star.handle),
            config=content_config,
            client=client,
        )
        posts.append(FeedPost(rival.star.handle, rival.star.name, star.text, tuple(star.cites), star.grounding_status))

    return tuple(posts), grounded


def run_slice(
    world: WorldState,
    config: SliceConfig,
    decisions: SliceDecisions,
    *,
    content_config: Optional[ContentConfig] = None,
    client: Optional["LLMClient"] = None,
) -> SliceResult:
    """Play one week and return the structured :class:`SliceResult`.

    Pure with respect to ``world`` (read, never mutated) and deterministic for a
    given ``config`` + ``decisions``. ``content_config`` defaults to the zero-API
    templated backend, the mode the whole slice is built to run in.

    ``client`` is the optional LLM client the ``vllm`` backend should talk through;
    it is threaded to every generation and ignored by the templated backend (which
    makes no API call). The default (``None``) lets the ``vllm`` backend fall back
    to its env-configured process default — and, in templated mode, nothing is ever
    constructed. This is the injection seam the vLLM demo preflight uses to run the
    whole slice against a chosen endpoint (and to time it) without reaching into
    module globals.
    """
    content_config = content_config or ContentConfig()
    structured = decisions.structured(config)

    why = resolver.run(world, structured, config.seed)

    narration = generate_content(
        "narration",
        GenerationContext(world=world, why=why, decisions=structured),
        config=content_config,
        client=client,
    )

    half_score = halftime_scoreline(why, world.team.id)
    halftime = generate_content(
        "halftime_ack",
        GenerationContext(world=world, halftime_scoreline=half_score, second_half_stance=config.tactical_stance),
        config=content_config,
        client=client,
    )

    feed, feed_grounded = _build_feed(world, config, decisions, why, content_config, client)

    # Grounding rate over the pieces that actually attempt to cite precedent:
    # the narration and the five starter reactions. Half-time acks and external
    # voices never cite, so counting them would only flatter the number.
    grounded_pieces = [narration, *feed_grounded]
    grounded_ok = sum(1 for gc in grounded_pieces if gc.grounding_status == "ok")

    cited = {c for gc in grounded_pieces for c in gc.cites}
    cited_memories = tuple(sorted(cited))

    return SliceResult(
        slice_id=slice_id(world, config, decisions),
        config=config,
        decisions=decisions,
        why=why,
        narration=narration,
        halftime=halftime,
        halftime_scoreline=half_score,
        feed=feed,
        grounded_ok=grounded_ok,
        grounded_total=len(grounded_pieces),
        content_backend=content_config.backend,
        cited_memories=cited_memories,
    )
