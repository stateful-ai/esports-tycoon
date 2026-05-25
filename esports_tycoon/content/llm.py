"""The vLLM content backend: the gaming-pack client behind the adapter seam.

This is the opt-in, LLM-backed twin of :mod:`~esports_tycoon.content.templated`.
It is the **only** module that imports the vendored gaming-pack client
(:mod:`esports_tycoon.content.game_llm`, dropped in verbatim), and it talks to it
exactly as the pack intends: an env-configured, OpenAI-compatible endpoint (a
local vLLM in dev, a cheap hosted Qwen in prod — see ``.env.example``). No
provider is hardcoded here; swapping endpoints is a ``GAME_LLM_*`` env change.

Each kind is given the structured shape the pack's ``structured()`` call wants — a
``{text, cites}`` JSON object validated into :class:`_LLMReply` — plus a tight
token budget. References to prior events are **cites by stable ID**: the prompt
offers a menu of real memory IDs and asks the model to cite only from it; on the
way back every cite is resolved against the world and any the model invented are
dropped, so a returned :class:`~esports_tycoon.schema.GeneratedContent` never
carries a cite that doesn't resolve. The retry-until-grounded loop (regenerate up
to N, *then* drop) is a separate ticket (``grounding.py``); this backend does the
honest minimum — resolve and drop — so its output already satisfies the
no-hallucinated-history contract.

The client is injectable (``client=`` / the module default from
``game_llm.get_llm()``) so the wiring is testable without a live endpoint.
"""

from __future__ import annotations

from typing import Optional, Protocol, TypeVar

from pydantic import BaseModel

from esports_tycoon.content import game_llm
from esports_tycoon.content.config import ContentConfig
from esports_tycoon.content.context import GenerationContext
from esports_tycoon.schema import GeneratedContent, MemoryEntry, Player, WhyRecord

__all__ = ["generate", "LLMClient", "MAX_TOKENS"]

#: Per-kind output budgets (tokens), from the M0 technical plan. Capping output
#: is the cheapest cost lever there is.
MAX_TOKENS: dict[str, int] = {
    "chirper_post": 80,
    "narration": 320,
    "halftime_ack": 200,
}

_T = TypeVar("_T", bound=BaseModel)


class _LLMReply(BaseModel):
    """The structured shape every kind asks the model for."""

    text: str
    cites: list[str] = []


class LLMClient(Protocol):
    """The slice of the gaming-pack client this backend depends on.

    :class:`game_llm.GameLLM` satisfies it; so does any duck-typed stand-in (the
    tests pass one), which is what keeps the wiring testable without a live
    endpoint.
    """

    def structured(
        self,
        prompt: str,
        schema: type[_T],
        *,
        system: Optional[str] = ...,
        max_tokens: Optional[int] = ...,
    ) -> _T: ...


# --------------------------------------------------------------------------- #
# Tone + prompt construction.
# --------------------------------------------------------------------------- #
_TONE = (
    "Tone is dry mockumentary (The Office / Welcome to Wrexham deadpan). Flat, "
    "short, declarative lines; comedy from restraint and understatement, never "
    "jokes, puns, hype, or meme-speak. Let the scoreboard carry the stakes."
)

_NARRATOR_SYSTEM = (
    "You are the deadpan documentary narrator for the team Overcast. " + _TONE +
    " No emoji, no exclamation marks, at most three short sentences."
)


def _citable_menu(entries: list[MemoryEntry]) -> str:
    if not entries:
        return "(no prior events you may cite)"
    return "\n".join(f"- {entry.id}: {entry.summary}" for entry in entries)


def _result_line(why: WhyRecord, ctx: GenerationContext, opponent: Optional[str]) -> str:
    ovc, opp = why.scoreline
    outcome = "won" if ovc > opp else "lost"
    foe = opponent or "the opponent"
    return f"Overcast {outcome} {ovc}-{opp} versus {foe}. MVP: {why.mvp}."


def _fielded(ctx: GenerationContext, why: WhyRecord) -> list[Player]:
    fielded = set(why.morale_deltas)
    return [p for p in ctx.world.players if p.id in fielded]


def _build_request(kind: str, ctx: GenerationContext) -> tuple[str, str]:
    """Return ``(system, user)`` prompts for ``kind`` from the typed context."""
    if kind == "narration":
        ctx.require("narration", why=ctx.why, decisions=ctx.decisions)
        why, decisions = ctx.why, ctx.decisions
        assert why is not None and decisions is not None
        opponent = decisions.opponent
        menu = _citable_menu([e for p in _fielded(ctx, why) for e in p.memory_log])
        user = (
            f"{_result_line(why, ctx, opponent)} Map: {decisions.map}. "
            f"Key moments: {[ (m.kind, m.descriptor) for m in why.key_moments ]}. "
            f"Carried: {why.who_carried}. Tilted: {why.who_tilted}.\n"
            f"Write the post-match narration. You may cite prior events only by the "
            f"IDs below, and only when one genuinely echoes this match:\n{menu}"
        )
        return _NARRATOR_SYSTEM, user

    if kind == "chirper_post":
        ctx.require("chirper_post", why=ctx.why, author=ctx.author)
        why, author = ctx.why, ctx.author
        assert why is not None and author is not None
        player = ctx.player(author)
        opponent = ctx.decisions.opponent if ctx.decisions else None
        if player is not None:
            system = (
                f"You are {player.name} ({player.handle}), posting on Chirper. "
                f"Voice: {player.persona_voice} {_TONE} Stay in character; you may "
                f"use emoji only if it fits this character. One post, under 240 characters."
            )
            menu = _citable_menu(player.memory_log)
        else:
            system = (
                f"You are {author}, posting on Chirper. {_TONE} One post, under 240 characters."
            )
            menu = _citable_menu([])
        user = (
            f"{_result_line(why, ctx, opponent)}\n"
            f"Write your reaction post. You may cite a prior event only by an ID "
            f"below, and only if you would really bring it up:\n{menu}"
        )
        return system, user

    if kind == "halftime_ack":
        ctx.require(
            "halftime_ack",
            halftime_scoreline=ctx.halftime_scoreline,
            second_half_stance=ctx.second_half_stance,
        )
        scoreline, stance = ctx.halftime_scoreline, ctx.second_half_stance
        assert scoreline is not None and stance is not None
        speaker = ctx.player(ctx.author) if ctx.author else ctx.igl()
        ovc, opp = scoreline
        who = f"{speaker.name} ({speaker.handle})" if speaker else "the in-game leader"
        voice = f"Voice: {speaker.persona_voice} " if speaker else ""
        system = (
            f"You are {who}, the in-game leader, acknowledging the manager's "
            f"half-time call to the documentary crew. {voice}{_TONE} One flat line, "
            f"no emoji, no exclamation marks."
        )
        user = (
            f"Half-time score: Overcast {ovc}, opponent {opp}. The manager's call for "
            f"the second half is a {stance} stance. Acknowledge it in one line."
        )
        return system, user

    raise ValueError(f"vllm backend does not render {kind!r}")


def _ground(reply: _LLMReply, ctx: GenerationContext) -> tuple[list[str], str]:
    """Resolve the model's cites against the world; drop any that don't exist.

    Returns ``(kept_cites, grounding_status)``. ``dropped`` means the model named
    a memory that isn't in the log (it was discarded); ``ok`` means every cite it
    offered resolved.
    """
    kept: list[str] = []
    dropped = False
    for cite in reply.cites:
        if ctx.world.resolve_cite(cite) is not None:
            if cite not in kept:
                kept.append(cite)
        else:
            dropped = True
    return kept, ("dropped" if dropped else "ok")


def generate(
    kind: str,
    ctx: GenerationContext,
    config: Optional[ContentConfig] = None,
    *,
    client: Optional[LLMClient] = None,
) -> GeneratedContent:
    """Render ``kind`` via the gaming-pack LLM client.

    ``client`` defaults to the process-wide ``game_llm.get_llm()`` (configured
    from ``GAME_LLM_*`` env); pass one to target a specific endpoint or to test
    the wiring without a live server. ``config`` is accepted for interface
    symmetry with the templated backend.
    """
    if kind not in MAX_TOKENS:
        raise ValueError(
            f"vllm backend does not render {kind!r}; supported: {', '.join(sorted(MAX_TOKENS))}"
        )
    system, user = _build_request(kind, ctx)
    llm = client if client is not None else game_llm.get_llm()
    reply: _LLMReply = llm.structured(user, _LLMReply, system=system, max_tokens=MAX_TOKENS[kind])

    cites, status = _ground(reply, ctx)
    author = _resolved_author(kind, ctx)
    return GeneratedContent(
        kind=kind,  # type: ignore[arg-type]  # guarded against MAX_TOKENS above
        text=reply.text.strip(),
        grounding_status=status,
        author=author,
        cites=cites,
        raw_llm_output=reply.model_dump_json(),
    )


def _resolved_author(kind: str, ctx: GenerationContext) -> Optional[str]:
    """The handle to stamp on the output, matching the templated backend."""
    if kind == "narration":
        return None
    if kind == "chirper_post" and ctx.author is not None:
        player = ctx.player(ctx.author)
        return player.handle if player is not None else ctx.author
    if kind == "halftime_ack":
        speaker = ctx.player(ctx.author) if ctx.author else ctx.igl()
        return speaker.handle if speaker is not None else None
    return None
