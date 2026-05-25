"""The templated content backend: deterministic, zero-API renderers.

This is the default backend and the one that lets the whole slice run with no
network, no keys, and no cost. It renders the three M0 content kinds —
``chirper_post``, ``narration`` and ``halftime_ack`` — straight from the typed
:class:`~esports_tycoon.schema.WorldState` / :class:`~esports_tycoon.schema.WhyRecord`
already in hand. There is **no LLM, no I/O, and no entropy beyond the inputs**:
identical context in always yields identical content out.

Two properties are load-bearing and tested:

* **Determinism.** Any variation in phrasing is drawn from a local
  ``random.Random`` seeded from stable fields of the context (the match seed, the
  scoreline, the kind, the author). ``random.Random`` seeds reproducibly from a
  string across processes, so the same context selects the same template variant
  every time, while different matches and authors still read differently.
* **Grounding by construction.** Every cite this backend emits is pulled from a
  memory that already lives in the world, so it resolves and the
  ``grounding_status`` is always ``ok`` — the templated path can't hallucinate
  history because it only ever quotes the log it was handed.

Tone is the dry-mockumentary voice from ``docs/tone_and_cast_lock.md``: the
narrator is flat and never uses emoji or hype; characters keep their authored
register on Chirper (Sable answers in a word; Pixie is sincere and emoji-prone).
"""

from __future__ import annotations

from random import Random
from typing import Optional

from esports_tycoon.content.context import GenerationContext
from esports_tycoon.schema import (
    GeneratedContent,
    MemoryEntry,
    Player,
    WhyRecord,
)

__all__ = ["render", "SUPPORTED_KINDS"]

#: The kinds the templated backend renders. ``interview`` is a later ticket.
SUPPORTED_KINDS: frozenset[str] = frozenset({"chirper_post", "narration", "halftime_ack"})


# --------------------------------------------------------------------------- #
# Deterministic choice. random.Random seeds reproducibly from a string, so the
# variant a context selects is stable across runs and processes.
# --------------------------------------------------------------------------- #
def _rng(*parts: object) -> Random:
    return Random("|".join(str(part) for part in parts))


def _pick(rng: Random, options: list[str]) -> str:
    return options[rng.randrange(len(options))]


# --------------------------------------------------------------------------- #
# World lookups.
# --------------------------------------------------------------------------- #
def _rival_name(ctx: GenerationContext, opponent_id: str) -> str:
    for rival in ctx.world.rivals:
        if rival.id == opponent_id:
            return rival.name
    return opponent_id


def _player_name(ctx: GenerationContext, player_id: str) -> str:
    player = ctx.player(player_id)
    return player.name.split()[0] if player else player_id  # first name, dry register


def _name_list(ctx: GenerationContext, ids: list[str]) -> str:
    names = [_player_name(ctx, pid) for pid in ids]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _fielded(ctx: GenerationContext, why: WhyRecord) -> list[Player]:
    """The starters in this match — exactly the ids ``why.morale_deltas`` covers."""
    fielded = set(why.morale_deltas)
    return [p for p in ctx.world.players if p.id in fielded]


# --------------------------------------------------------------------------- #
# Grounding: choose a real precedent to cite. Every id returned resolves, because
# it is read straight out of a player's memory log.
# --------------------------------------------------------------------------- #
def _pick_memory(
    rng: Random, players: list[Player], *, tags: frozenset[str] = frozenset(), sentiment: Optional[str] = None
) -> Optional[MemoryEntry]:
    """A precedent matching the filters, chosen deterministically (or ``None``)."""
    candidates: list[MemoryEntry] = []
    for player in players:
        for entry in player.memory_log:
            if tags and not (tags & {t.lower() for t in entry.tags}):
                continue
            if sentiment is not None and entry.sentiment != sentiment:
                continue
            candidates.append(entry)
    if not candidates:
        return None
    candidates.sort(key=lambda e: (e.week, e.day, e.id))
    return candidates[rng.randrange(len(candidates))]


#: Key-moment kinds the resolver emits → the memory tags that rhyme with them, so
#: narration can cite the precedent a beat echoes ("the same choke as week 5").
_MOMENT_TAGS: dict[str, frozenset[str]] = {
    "choke": frozenset({"choke"}),
    "match_point": frozenset({"choke", "tilt"}),
    "blowout": frozenset({"tilt", "choke"}),
    "comeback": frozenset({"clutch", "revenge"}),
    "dominant": frozenset({"clutch"}),
    "ace": frozenset({"ace"}),
    "clutch": frozenset({"clutch"}),
    "closeout": frozenset({"clutch"}),
}

#: Which key moment is most worth narrating, most colourful first.
_MOMENT_PRIORITY = ("choke", "comeback", "ace", "blowout", "dominant", "clutch", "match_point", "closeout")


# --------------------------------------------------------------------------- #
# narration — the dry post-match recap. Narrator voice: flat, no emoji, no hype.
# --------------------------------------------------------------------------- #
def _render_narration(ctx: GenerationContext) -> GeneratedContent:
    ctx.require("narration", why=ctx.why, decisions=ctx.decisions)
    why, decisions = ctx.why, ctx.decisions
    assert why is not None and decisions is not None  # narrowed by require()

    team = ctx.world.save.team.name
    opponent = _rival_name(ctx, decisions.opponent)
    ovc, opp = why.scoreline
    won = ovc > opp
    rng = _rng("narration", why.seed, ovc, opp, decisions.opponent, decisions.map)

    if won:
        headline = _pick(
            rng,
            [
                f"{team} took {opponent} {ovc}–{opp} on {decisions.map}.",
                f"{team} beat {opponent} {ovc}–{opp}. {decisions.map}.",
            ],
        )
    else:
        headline = _pick(
            rng,
            [
                f"{team} lost to {opponent} {ovc}–{opp} on {decisions.map}.",
                f"{opponent} beat {team} {opp}–{ovc}. {decisions.map}.",
            ],
        )

    # Colour: the most narratable key moment, quoted from the resolver's descriptor.
    moments = {m.kind: m for m in why.key_moments}
    lead_kind = next((k for k in _MOMENT_PRIORITY if k in moments), None)
    colour = ""
    cites: list[str] = []
    if lead_kind is not None:
        moment = moments[lead_kind]
        colour = {
            "choke": f"They {moment.descriptor}. The booth went quiet.",
            "comeback": f"They {moment.descriptor}.",
            "ace": f"{_name_list(ctx, moment.actors)} aced round {moment.round}. It cleared the lobby.",
            "blowout": "It was not close.",
            "dominant": "It was never close.",
            "clutch": f"{_name_list(ctx, moment.actors)} {moment.descriptor}.",
            "match_point": "",
            "closeout": "",
        }.get(lead_kind, "")
        # Prefer a precedent owned by the players in the beat (the same name the
        # narration just used), then fall back to anyone fielded.
        moment_tags = _MOMENT_TAGS.get(lead_kind, frozenset())
        actors = [p for p in _fielded(ctx, why) if p.id in set(moment.actors)]
        precedent = _pick_memory(rng, actors, tags=moment_tags) or _pick_memory(
            rng, _fielded(ctx, why), tags=moment_tags
        )
        if precedent is not None:
            cites.append(precedent.id)

    # Who stood out / came apart.
    if won:
        standout = f"{_player_name(ctx, why.mvp)} carried."
        if why.who_tilted:
            standout += f" {_name_list(ctx, why.who_tilted)} did not."
    else:
        if why.who_tilted:
            standout = f"{_name_list(ctx, why.who_tilted)} came apart."
        else:
            standout = f"{_player_name(ctx, why.mvp)} kept it honest."

    text = " ".join(part for part in (headline, colour, standout) if part)
    return GeneratedContent(kind="narration", text=text, grounding_status="ok", author=None, cites=cites)


# --------------------------------------------------------------------------- #
# chirper_post — an in-character reaction. Characters keep their authored voice;
# they may use emoji in-character (the narrator may not).
# --------------------------------------------------------------------------- #
def _register(player: Player) -> str:
    traits = set(player.traits)
    if traits & {"stoic", "low-ego"}:
        return "terse"
    if traits & {"sincere", "optimist", "oversharer", "motormouth"}:
        return "sincere"
    if traits & {"clout-chasing", "hotshot"}:
        return "boastful"
    if traits & {"cynical", "lurker", "patient", "grudge-holder"}:
        return "dry"
    return "flat"


#: Per-register reaction lines, keyed (register, won). Authored to the tone bible.
_CHIRPER_LINES: dict[tuple[str, bool], list[str]] = {
    ("flat", True): ["we ran the default. it worked.", "good map. back to work.", "the plan, executed. moving on."],
    ("flat", False): ["we had a plan. it was a good plan.", "we'll review the tape. all of it.", "that's on me. we go again."],
    ("terse", True): ["held. won.", "held. won. hungry.", "good map."],
    ("terse", False): [".", "next.", "we hold next time."],
    ("boastful", True): ["told you. scoreboard doesn't lie.", "easy read. next.", "that's the tape. you're welcome."],
    ("boastful", False): ["hard to win a round that's lost before i get there. but sure.", "not my round to lose. it got lost anyway.", "we'll be fine. i'll be fine."],
    ("sincere", True): ["that's the bounce-back i KNEW we had \U0001faf6 #overcastfam", "so proud of these five today, what a watch \U0001faf6 #overcastfam", "called it round one. love this team \U0001faf6 #overcastfam"],
    ("sincere", False): ["that one stings but i love this team, we go again \U0001faf6 #overcastfam", "a little on me but we bounce back, promise \U0001faf6 #overcastfam", "chins up everyone, the week's not over \U0001faf6 #overcastfam"],
    ("dry", True): ["won the rounds nobody clapped for. as usual.", "quiet game. good game.", "someone has to hold the corner. you're welcome."],
    ("dry", False): ["you peeked the same corner twice. i noticed.", "i'll remember this one. i remember all of them.", "we lost. i was watching."],
}


def _render_chirper(ctx: GenerationContext) -> GeneratedContent:
    ctx.require("chirper_post", why=ctx.why, author=ctx.author)
    why, author = ctx.why, ctx.author
    assert why is not None and author is not None  # narrowed by require()

    ovc, opp = why.scoreline
    won = ovc > opp
    player = ctx.player(author)
    rng = _rng("chirper_post", author, why.seed, ovc, opp)

    if player is None:
        # An external voice (a caster handle, a rival): no persona, no precedent.
        text = _pick(rng, ["the scoreboard says it all.", "tape doesn't lie.", "and that's the map."])
        return GeneratedContent(kind="chirper_post", text=text, grounding_status="ok", author=author, cites=[])

    register = _register(player)
    text = _pick(rng, _CHIRPER_LINES[(register, won)])

    # Ground the post in one of the author's own memories matching the mood.
    precedent = _pick_memory(rng, [player], sentiment="positive" if won else "negative")
    cites = [precedent.id] if precedent is not None else []
    return GeneratedContent(
        kind="chirper_post", text=text, grounding_status="ok", author=player.handle, cites=cites
    )


# --------------------------------------------------------------------------- #
# halftime_ack — the IGL's deadpan acknowledgement of the half-time call.
# --------------------------------------------------------------------------- #
_HALFTIME_LINES: dict[tuple[str, str], list[str]] = {
    ("up", "disciplined"): ["Up {n}. We don't get cute. Same default.", "Up {n}. Tighten up, close it out."],
    ("up", "aggressive"): ["Up {n}. You want more. Fine.", "Up {n}. We press. Don't trade it back."],
    ("up", "default"): ["Up {n}. Hold the line.", "Up {n}. Same as the first half."],
    ("down", "disciplined"): ["Down {n}. We tighten up. No heroes.", "Down {n}. Slow it down. Trade smart."],
    ("down", "aggressive"): ["Down {n}. We stop waiting. We push.", "Down {n}. Nothing to save now."],
    ("down", "default"): ["Down {n}. We've been here. We had a plan.", "Down {n}. Reset. Run it back."],
    ("even", "disciplined"): ["Even. We don't force it.", "Even. Discipline wins this one."],
    ("even", "aggressive"): ["Even. We take the next one.", "Even. First to blink loses. Not us."],
    ("even", "default"): ["Even. Same default. Earn it.", "Even. Back to work."],
}


def _render_halftime(ctx: GenerationContext) -> GeneratedContent:
    ctx.require(
        "halftime_ack",
        halftime_scoreline=ctx.halftime_scoreline,
        second_half_stance=ctx.second_half_stance,
    )
    scoreline, stance = ctx.halftime_scoreline, ctx.second_half_stance
    assert scoreline is not None and stance is not None  # narrowed by require()

    ovc, opp = scoreline
    if ovc > opp:
        position, margin = "up", ovc - opp
    elif ovc < opp:
        position, margin = "down", opp - ovc
    else:
        position, margin = "even", 0

    speaker = ctx.player(ctx.author) if ctx.author else ctx.igl()
    rng = _rng("halftime_ack", ovc, opp, stance, speaker.id if speaker else "team")
    template = _pick(rng, _HALFTIME_LINES[(position, stance)])
    text = template.format(n=margin)
    author = speaker.handle if speaker else None
    return GeneratedContent(kind="halftime_ack", text=text, grounding_status="ok", author=author, cites=[])


_RENDERERS = {
    "narration": _render_narration,
    "chirper_post": _render_chirper,
    "halftime_ack": _render_halftime,
}


def render(kind: str, ctx: GenerationContext) -> GeneratedContent:
    """Render ``kind`` from ``ctx`` deterministically, with zero API calls."""
    try:
        renderer = _RENDERERS[kind]
    except KeyError:
        raise ValueError(
            f"templated backend does not render {kind!r}; "
            f"supported: {', '.join(sorted(SUPPORTED_KINDS))}"
        ) from None
    return renderer(ctx)
