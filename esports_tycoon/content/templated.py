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

from esports_tycoon.content.context import GenerationContext, LocalOutcome, derive_local_outcome
from esports_tycoon.recall import recall
from esports_tycoon.schema import (
    GeneratedContent,
    MemoryEntry,
    Player,
    WhyRecord,
)

__all__ = ["render", "SUPPORTED_KINDS", "BEAT_KINDS", "CAST_IDS"]

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

#: How deep the narrator looks into the recalled ranking when binding a beat's
#: cite. Eight is enough to step past memories owned by non-fielded characters
#: (e.g. a rival star's authored history) and find one a beat's actors share —
#: small enough that the search is bounded and predictable.
_RECALL_DEPTH = 8

#: Per-event-kind narrator beat templates. Every resolver-emittable kind has at
#: least two tone-locked variations; never empty, never a placeholder. Templates
#: use the slot vocabulary ``{actors}`` / ``{round}`` / ``{descriptor}`` /
#: ``{ovc}`` / ``{opp}``, all of which are always bound at render time — an
#: unbound slot would raise ``KeyError`` rather than ship a literal ``{name}``.
_BEAT_TEMPLATES: dict[str, list[str]] = {
    "ace": [
        "{actors} aced round {round}. It cleared the lobby.",
        "Round {round}: {actors} took the round for five. Nobody traded back.",
    ],
    "clutch": [
        "{actors} {descriptor}. Round {round}.",
        "Round {round} went to {actors}. The round nobody wanted to be in.",
    ],
    "choke": [
        "They {descriptor}. The booth went quiet.",
        "Up, then not up. They {descriptor}.",
    ],
    "comeback": [
        "They {descriptor}.",
        "Down, then level, then ahead. They {descriptor}.",
    ],
    "dominant": [
        "It was never close.",
        "{ovc}–{opp}. They never gave the round back.",
    ],
    "blowout": [
        "It was not close.",
        "{ovc}–{opp}. The booth ran out of things to say.",
    ],
    "match_point": [
        "Match point at round {round}. They could not find the close.",
        "Down to the wire on round {round}. The wire did not bend their way.",
    ],
    "closeout": [
        "Round {round} closed it at {ovc}–{opp}. Nobody celebrated for the camera.",
        "They shook hands at {ovc}–{opp}. Quietly.",
    ],
}


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

    # Colour: the most narratable key moment, rendered from the per-kind beat
    # templates. Every emittable kind has at least one tone-locked variation so
    # ``colour`` is never an empty placeholder once a beat is in hand.
    moments = {m.kind: m for m in why.key_moments}
    lead_kind = next((k for k in _MOMENT_PRIORITY if k in moments), None)
    colour = ""
    cites: list[str] = []
    if lead_kind is not None:
        moment = moments[lead_kind]
        slots = {
            "actors": _name_list(ctx, moment.actors),
            "round": moment.round,
            "descriptor": moment.descriptor,
            "ovc": ovc,
            "opp": opp,
        }
        colour = _pick(rng, _BEAT_TEMPLATES[lead_kind]).format(**slots)
        # The deterministic recall ranks every canned precedent against the
        # whole match; prefer the highest-ranked result whose underlying entry
        # actors overlap the named beat (so the cite reads like *this* round's
        # echo), then fall back to the top recalled result. ``recall`` returns
        # the locked :class:`RecallResult` contract, so the cite is bound by
        # ``cite_id`` and the wider entry (for the beat-actor filter) is
        # resolved through the world. ``recall`` is RNG-free, so the cite
        # binds deterministically from the same scoring the recap reasons over.
        beat_actors = set(moment.actors)
        ranked = recall(why, ctx.world, k=_RECALL_DEPTH)
        precedent = None
        for result in ranked:
            entry = ctx.world.resolve_cite(result.cite_id)
            if entry is not None and beat_actors & set(entry.actors):
                precedent = result
                break
        if precedent is None and ranked:
            precedent = ranked[0]
        if precedent is not None:
            cites.append(precedent.cite_id)

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
#
# Lines are organized as a three-tier copy pack:
#
# 1. ``_CAST_VOICES`` — per-cast authored lines keyed by ``(beat, won)``. ``beat``
#    is one of the resolver-emittable kinds (``ace`` / ``clutch`` / ``choke`` /
#    ``comeback`` / ``dominant`` / ``blowout`` / ``match_point`` / ``closeout``)
#    *or* the sentinel ``"default"``, which is the fallback when the leading beat
#    has no specialized line for this cast member. Every cast voice ships a
#    ``("default", True)`` and ``("default", False)`` so every match has *some*
#    line to render in their register, with kind-specific lines layered on top
#    where the character earns one.
# 2. ``_CAST_LOCAL_OUTCOME_VOICES`` — per-cast lines keyed by the author's local
#    match outcome (``mvp`` / ``carried`` / ``came_apart``). These override
#    team-result copy so an MVP in a loss or a player who melted down in a win
#    reacts to what happened to them, specifically.
# 3. ``_CHIRPER_LINES`` — register-based lines keyed by ``(register, mood)``,
#    used as a safety net when an author has no entry in ``_CAST_VOICES``. The
#    mood is a local outcome when one fired, otherwise ``team_win`` or
#    ``team_loss``. The canned cast all live in ``_CAST_VOICES``; this layer
#    covers any future starter / cameo whose traits the renderer can recognize
#    but whose voice has not been authored yet.
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


_HEART_HANDS = "\U0001faf6"

#: Per-cast voice pack. Keys are the cast member's id — a starter id for a
#: managed-team player ("rook", "vex", "sable", "pixie", "coyote"), or the
#: external handle for the caster and the six rival stars ("@gridcast",
#: "@halo", "@bishop", "@echo", "@grud", "@marlow", "@ghost"). Each cast member
#: ships ``("default", True)`` and ``("default", False)`` lines and adds beat-
#: specialized lines (keyed on the leading key-moment kind) where the character
#: actually has something to say about that beat.
#:
#: Tone-locked against ``docs/tone_and_cast_lock.md``:
#:   - Rook is flat, short, structure-first; his "choke" lines own the call.
#:   - Vex is clipped soundbites; "ace" lines lean clout, "blowout"-lost lines
#:     deflect.
#:   - Sable answers in a word or three; never more.
#:   - Pixie is run-on sincerity with heart-hands and "#overcastfam"; allowed
#:     emoji in-character (the narrator is not).
#:   - Coyote is dry, economical, patient; saves his sharpest line for Bishop.
#:   - @gridcast is the league's deadpan caster (no persona-grounded cite).
#:   - Rival stars echo their archetype: Halo the sterile champion, Bishop the
#:     taunting ex-teammate, Echo the wunderkind, Grud the chaos memer with a
#:     frog emoji on-character, Marlow the rising-underdog respectful note,
#:     Ghost the fallen-star reflection.
_CAST_VOICES: dict[str, dict[tuple[str, bool], list[str]]] = {
    # --- Starters ---------------------------------------------------------- #
    "rook": {
        ("default", True): [
            "we ran the default. it worked.",
            "the plan, executed. moving on.",
            "good map. back to work.",
        ],
        ("default", False): [
            "we had a plan. it was a good plan.",
            "we'll review the tape. all of it.",
            "that's on me. we go again.",
        ],
        ("choke", False): [
            "we had a plan. it was a good plan. i'd like to think about something else now.",
            "i called it. they ran it. we lost it. that's on me.",
        ],
        ("comeback", True): [
            "we were down. then we weren't. same default.",
            "patience, mostly. and a tape they'll be watching all week.",
        ],
        ("match_point", False): [
            "match point twice. neither one ours. we go again.",
            "we had it. then we didn't. i'll review the tape.",
        ],
        ("closeout", True): [
            "closed it. quietly. on to next week.",
            "the close was the plan. the plan was the close.",
        ],
        ("dominant", True): [
            "the default did the work. nobody had to be a hero.",
            "straight maps. tape's short. review's shorter.",
        ],
    },
    "vex": {
        ("default", True): [
            "told you. scoreboard doesn't lie.",
            "easy read. next.",
            "that's the tape. you're welcome.",
        ],
        ("default", False): [
            "hard to win a round that's lost before i get there. but sure.",
            "not my round to lose. it got lost anyway.",
            "we'll be fine. i'll be fine.",
        ],
        ("ace", True): [
            "5k. for the algorithm.",
            "ace on the clock. clip's already up.",
            "five guys. one round. one clip.",
        ],
        ("choke", False): [
            "up nine. lost it. wasn't my entry to call.",
            "i can't carry a lead i'm not allowed to push.",
        ],
        ("blowout", False): [
            "you can't entry a lost round. the tape will show it.",
            "we weren't on the same map. i was. they weren't.",
        ],
        ("dominant", True): [
            "i was the map. quote me on that.",
            "they came to watch. i came to play. that's the math.",
        ],
        ("match_point", False): [
            "match point and the team forgot the duelist exists. cool.",
            "next time, run it through me. radical idea.",
        ],
    },
    "sable": {
        ("default", True): [
            "held. won.",
            "held. won. hungry.",
            "good map.",
        ],
        ("default", False): [
            ".",
            "next.",
            "we hold next time.",
        ],
        ("ace", True): ["clean.", "noted.", "good round."],
        ("clutch", True): ["held.", "anchored.", "good hold."],
        ("choke", False): [".", "noted.", "tape."],
        ("comeback", True): ["held. won. hungry.", "back.", "next."],
        ("blowout", False): [".", "tape."],
        ("dominant", True): ["held.", "clean."],
        ("match_point", False): [".", "next."],
        ("closeout", True): ["closed.", "done.", "next."],
    },
    "pixie": {
        ("default", True): [
            f"that's the bounce-back i KNEW we had {_HEART_HANDS} #overcastfam",
            f"so proud of these five today, what a watch {_HEART_HANDS} #overcastfam",
            f"called it round one. love this team {_HEART_HANDS} #overcastfam",
        ],
        ("default", False): [
            f"that one stings but i love this team, we go again {_HEART_HANDS} #overcastfam",
            f"a little on me but we bounce back, promise {_HEART_HANDS} #overcastfam",
            f"chins up everyone, the week's not over {_HEART_HANDS} #overcastfam",
        ],
        ("ace", True): [
            f"FIVE!!! that's the read of the season already {_HEART_HANDS} #overcastfam",
            f"absolute monster round, hats off teammate {_HEART_HANDS} #overcastfam",
        ],
        ("clutch", True): [
            f"called the lurk before contact, what a hold {_HEART_HANDS} #overcastfam",
            f"that's the read i live for, what a round {_HEART_HANDS} #overcastfam",
        ],
        ("choke", False): [
            f"that one's on me, i'll own it — but i love these five {_HEART_HANDS} #overcastfam",
            f"hard one to take but tape's a teacher {_HEART_HANDS} #overcastfam",
        ],
        ("comeback", True): [
            f"down, then back, then UP, i love this team {_HEART_HANDS} #overcastfam",
            f"the team that bounces back together stays together {_HEART_HANDS} #overcastfam",
        ],
        ("match_point", False): [
            f"so close it hurts but we'll be back week 7 {_HEART_HANDS} #overcastfam",
            f"chins up team, that one was right there {_HEART_HANDS} #overcastfam",
        ],
    },
    "coyote": {
        ("default", True): [
            "won the rounds nobody clapped for. as usual.",
            "quiet game. good game.",
            "someone has to hold the corner. you're welcome.",
        ],
        ("default", False): [
            "you peeked the same corner twice. i noticed.",
            "i'll remember this one. i remember all of them.",
            "we lost. i was watching.",
        ],
        ("clutch", True): [
            "the lurk worked because nobody was listening. as designed.",
            "won it from the corner. the corner is undefeated.",
        ],
        ("choke", False): [
            "lost a nine-three lead. add it to the list.",
            "i was watching. i'm always watching.",
        ],
        ("comeback", True): [
            "patience. the meta forgets it. i don't.",
            "we waited. they didn't. that was the round.",
        ],
        ("dominant", True): [
            "smokes did the work. nobody clipped them.",
            "they didn't see me. they rarely do.",
        ],
        ("match_point", False): [
            "we had it. they took it. i'll remember.",
            "match point and a peek i won't forget. enjoy.",
        ],
    },
    # --- External voices --------------------------------------------------- #
    # The caster: dry, observational, never roots openly. No cite — external
    # voices have no persona-grounded memory log.
    "@gridcast": {
        ("default", True): [
            "and that's the map. clean from Overcast.",
            "tape doesn't lie. they had the better default tonight.",
            "you can hear the bench breathing again.",
        ],
        ("default", False): [
            "and that's the map. a tired room in the Overcast booth.",
            "the scoreboard says it all.",
            "you do not get a lot of these back.",
        ],
        ("ace", True): [
            "a five-piece in this league, in this division, on this map. file it.",
            "the kind of round you build a highlight reel around.",
        ],
        ("clutch", True): [
            "a one-versus-the-room hold. they will be running that back in scrims.",
            "won from the back foot. that's the round of the night, easily.",
        ],
        ("choke", False): [
            "i have covered this league for six years. that is the loudest quiet i have ever heard from a bench.",
            "a lead you do not throw, thrown.",
        ],
        ("comeback", True): [
            "down by a touchdown, up at the buzzer. that is the kind of bounce-back that defines a split.",
            "they were buried. they un-buried themselves. live on broadcast.",
        ],
        ("blowout", False): [
            "it stopped being a series in round eight.",
            "the booth ran out of things to say a long time ago.",
        ],
        ("dominant", True): [
            "straight maps. the wall stayed up.",
            "this is what a peak roster looks like on a quiet night.",
        ],
        ("match_point", False): [
            "match point twice. neither one taken. that is the league for you.",
            "they had a hand on it. they could not close the fingers.",
        ],
        ("closeout", True): [
            "they shook hands. quietly. that's the map.",
            "and that is the close. on to next week.",
        ],
    },
    # The Dynasty's star: sterile, dismissive, never out of register.
    "@halo": {
        ("default", True): [
            "good map by them, i guess. we play next week.",
            "respect. now back to work.",
        ],
        ("default", False): [
            "imagine making us play three maps. couldn't be us.",
            "we'll be on the trophy stage. they'll be on the highlight reel.",
        ],
        ("ace", True): [
            "cute ace. we drop a few a series. anyway.",
            "highlight of their split, probably. next.",
        ],
        ("choke", False): [
            "imagine choking a 9–3 lead. couldn't be me.",
            "leads are for closing. who knew.",
        ],
        ("comeback", True): [
            "a comeback against us would have been a story. against them, it's a tuesday.",
            "respectable. now go run it against a real seed.",
        ],
        ("blowout", False): [
            "the rest of the league should take notes. that's how you finish.",
            "they tried. it was nice.",
        ],
        ("dominant", True): [
            "the only team in this league with a wall. take a look.",
            "we don't run it close. we run it correct.",
        ],
        ("match_point", False): [
            "match point and they bottled it. peak this league.",
            "we don't lose those. that's the difference.",
        ],
    },
    # The Ex-Teammate: taunting, transactional, never lets a grudge sleep.
    "@bishop": {
        ("default", True): [
            "good week for the lads. shame about theirs.",
            "we keep showing up. that's the trick.",
        ],
        ("default", False): [
            "some guys you trade away. some guys trade themselves.",
            "we'll see them again. always do.",
        ],
        ("choke", False): [
            "you peeked the same corner twice tonight, lurker. enjoy week 8.",
            "a 9–3 lead, again. some habits stick.",
        ],
        ("clutch", True): [
            "the lurker found a round. one of them, anyway.",
            "good hold. the rest of the series, less so.",
        ],
        ("comeback", True): [
            "they got one back. enjoy it. it's the one.",
            "comeback of the week, no comeback of the season.",
        ],
        ("blowout", False): [
            "told the front office he wasn't built for it. they signed him anyway.",
            "we used to share comms with that. glad we don't.",
        ],
        ("dominant", True): [
            "still teaching the lurker the league, one map at a time.",
            "we know the corners. taught half of them.",
        ],
        ("match_point", False): [
            "match point and the lurker missed it. nostalgic, really.",
            "this game eats lurkers last. but it eats them.",
        ],
    },
    # The Wunderkind: fast, dismissive, lives for the comparison line.
    "@echo": {
        ("default", True): [
            "good calls. textbook stuff. respect.",
            "we like a quiet win. on to next.",
        ],
        ("default", False): [
            "fair play. their caller had a clean night.",
            "we'll fix it in scrims. boring answer, true answer.",
        ],
        ("ace", True): [
            "ace's nice. calls are nicer. just saying.",
            "five-piece in week 6. our duelist drops them in scrims.",
        ],
        ("choke", False): [
            "calls like it's still last meta. tape will show it.",
            "the old caller threw a lead, again. business as usual.",
        ],
        ("clutch", True): [
            "good round. one is one.",
            "fine read. we'd have called the trade.",
        ],
        ("comeback", True): [
            "we ran the same default for ten rounds and still won. just food for thought.",
            "decent bounce-back. now do it against a real default.",
        ],
        ("blowout", False): [
            "the meta moved. some calls didn't.",
            "we don't lose those. age in IGL years is real.",
        ],
        ("dominant", True): [
            "structure beats vibes. it always has.",
            "good clean calls. nobody had to invent a play.",
        ],
        ("match_point", False): [
            "match point and the old caller hesitated. tape's loud on that one.",
            "match point's a call, not a feeling. some IGLs forget.",
        ],
    },
    # The Chaos Agents' troll initiator: wholesome bait, frog emoji on-brand.
    "@grud": {
        ("default", True): [
            "good map. we'll see y'all in scrims with a comp our coach drew on a napkin \U0001f438",
            "respect. the meta is fake \U0001f438",
        ],
        ("default", False): [
            "we ran a meme. they ran a clinic. tape's still funny \U0001f438",
            "ggs. we'll be back with worse comps and bigger flashes \U0001f438",
        ],
        ("ace", True): [
            "five kills in one round? in *this* economy? \U0001f438",
            "ace by the script kids. respect. \U0001f438",
        ],
        ("choke", False): [
            "throwback to when we ended their whole week with a comp our coach drew on a napkin \U0001f438",
            "9–3 leads are a meta we left behind \U0001f438",
        ],
        ("clutch", True): [
            "lurk diff. we respect a lurk diff \U0001f438",
            "clutch by the structure team. allowed once a split \U0001f438",
        ],
        ("comeback", True): [
            "the comeback is a meta we approve of. carry on \U0001f438",
            "down nine, up at the buzzer. that's our kind of round \U0001f438",
        ],
        ("dominant", True): [
            "clean sweep. boring. respect though \U0001f438",
            "we'll be back with operatives nobody picks \U0001f438",
        ],
        ("match_point", False): [
            "match point is a state of mind. they had the state, not the point \U0001f438",
            "wide open at match point and they ran a default. iconic \U0001f438",
        ],
    },
    # The Rising Underdog's sentinel: respectful, grinding, mentored by Sable.
    "@marlow": {
        ("default", True): [
            "good map by them. taking notes.",
            "respect to the wall. learning every week.",
        ],
        ("default", False): [
            "honest series. honest loss. back to scrims.",
            "we'll be back. tape's where we live.",
        ],
        ("clutch", True): [
            "a hold like that is a clinic. taking notes.",
            "anchored a site i would have stacked. learning.",
        ],
        ("choke", False): [
            "tough one to lose. the league is long.",
            "we've had that one. it doesn't go away. it just fades.",
        ],
        ("comeback", True): [
            "bounced back. that's a sentinel team.",
            "down nine, up at the close. that's a tape.",
        ],
        ("ace", True): [
            "five in one round is a story. nice for them.",
            "respect to the round. and the tape that comes with it.",
        ],
        ("blowout", False): [
            "they cooked. we'll be in scrims.",
            "fair series. our turn next time.",
        ],
        ("dominant", True): [
            "the wall stays. we'll keep grinding ours.",
            "clean sweep by an honest team. taking notes.",
        ],
        ("match_point", False): [
            "match point twice. close enough to learn from.",
            "we'll review that close. that's a tape.",
        ],
    },
    # The Fallen Star: aging-out, ominous, never hype.
    "@ghost": {
        ("default", True): [
            "good map. enjoy them while they come.",
            "win one, then another. the league forgets quickly.",
        ],
        ("default", False): [
            "tough one. the league does not get easier.",
            "you take the loss. it doesn't take you. usually.",
        ],
        ("ace", True): [
            "ace's a souvenir. play long enough and you collect a few.",
            "nice round. mind the next one.",
        ],
        ("clutch", True): [
            "a clutch like that buys you a week. spend it.",
            "the hold is the round. the round is the season. usually.",
        ],
        ("choke", False): [
            "this game eats lurkers last, but it eats them.",
            "leads age out. like everything else.",
        ],
        ("comeback", True): [
            "comebacks are loaned, never given. enjoy it.",
            "you can bounce back once. maybe twice. mind the third.",
        ],
        ("blowout", False): [
            "you take the loss and the loss takes a little of you.",
            "tape's heavy after a series like that. it gets heavier.",
        ],
        ("dominant", True): [
            "straight maps in week 6 is a real thing. enjoy it. quietly.",
            "the wall holds. until it doesn't. enjoy the wall.",
        ],
        ("match_point", False): [
            "match point and the room got quiet. familiar quiet.",
            "you do not get a lot of these back. mind that.",
        ],
    },
}

#: Per-cast local-outcome lines. These fire before beat/team-result lines for
#: starters only, because they are the most visible "this happened to me" layer.
_CAST_LOCAL_OUTCOME_VOICES: dict[str, dict[LocalOutcome, list[str]]] = {
    "rook": {
        "mvp": ["kept the call clean. still work to do.", "good personal tape. team tape next."],
        "carried": ["did my job. more next time.", "structure held where it held."],
        "came_apart": ["bad calls. mine.", "that's my tape. all of it."],
    },
    "vex": {
        "mvp": ["scoreboard checked my pulse. team meeting can wait.", "top frag is top frag. even here."],
        "carried": ["i did my job. look left.", "entry found space. the rest is a meeting."],
        "came_apart": ["bad map. don't clip it.", "rough one. algorithm gets nothing."],
    },
    "sable": {
        "mvp": ["held.", "clean."],
        "carried": ["held site.", "did job."],
        "came_apart": ["missed.", "bad hold."],
    },
    "pixie": {
        "mvp": [
            f"mvp on a hard day, still proud of the fight {_HEART_HANDS} #overcastfam",
            f"did everything i could and still love this team {_HEART_HANDS} #overcastfam",
        ],
        "carried": [
            f"found some rounds for us, we'll find more {_HEART_HANDS} #overcastfam",
            f"happy with the work, hungry for the close {_HEART_HANDS} #overcastfam",
        ],
        "came_apart": [
            f"rough map from me, owning it and back to tape {_HEART_HANDS} #overcastfam",
            f"that one was on my desk, i'll clean it up {_HEART_HANDS} #overcastfam",
        ],
    },
    "coyote": {
        "mvp": ["quiet top frag. loud room.", "i found rounds. not enough of them."],
        "carried": ["did the quiet work. check the tape.", "corner held. map didn't."],
        "came_apart": ["missed the timing. i noticed.", "bad lurk. i remember."],
    },
}

#: Per-register reaction lines, keyed (register, mood). ``mood`` is one of the
#: local outcomes (``mvp``, ``carried``, ``came_apart``) or the team fallback
#: moods (``team_win``, ``team_loss``). Safety-net fallback for any author who is
#: not in the cast voice pack.
_CHIRPER_LINES: dict[tuple[str, str], list[str]] = {
    ("flat", "team_win"): ["we ran the default. it worked.", "good map. back to work.", "the plan, executed. moving on."],
    ("flat", "team_loss"): ["we had a plan. it was a good plan.", "we'll review the tape. all of it.", "that's on me. we go again."],
    ("flat", "mvp"): ["good personal tape. team tape next.", "kept the plan alive."],
    ("flat", "carried"): ["did my job. more next time.", "structure held where it held."],
    ("flat", "came_apart"): ["bad calls. mine.", "that's my tape. all of it."],
    ("terse", "team_win"): ["held. won.", "held. won. hungry.", "good map."],
    ("terse", "team_loss"): [".", "next.", "we hold next time."],
    ("terse", "mvp"): ["held.", "clean."],
    ("terse", "carried"): ["held site.", "did job."],
    ("terse", "came_apart"): ["missed.", "bad hold."],
    ("boastful", "team_win"): ["told you. scoreboard doesn't lie.", "easy read. next.", "that's the tape. you're welcome."],
    ("boastful", "team_loss"): ["hard to win a round that's lost before i get there. but sure.", "not my round to lose. it got lost anyway.", "we'll be fine. i'll be fine."],
    ("boastful", "mvp"): ["top frag is top frag. even here.", "scoreboard checked my pulse."],
    ("boastful", "carried"): ["i did my job. look left.", "entry found space. watch it back."],
    ("boastful", "came_apart"): ["bad map. don't clip it.", "rough one. algorithm gets nothing."],
    ("sincere", "team_win"): [f"that's the bounce-back i KNEW we had {_HEART_HANDS} #overcastfam", f"so proud of these five today, what a watch {_HEART_HANDS} #overcastfam", f"called it round one. love this team {_HEART_HANDS} #overcastfam"],
    ("sincere", "team_loss"): [f"that one stings but i love this team, we go again {_HEART_HANDS} #overcastfam", f"a little on me but we bounce back, promise {_HEART_HANDS} #overcastfam", f"chins up everyone, the week's not over {_HEART_HANDS} #overcastfam"],
    ("sincere", "mvp"): [f"mvp on a hard day, still proud of the fight {_HEART_HANDS} #overcastfam", f"did everything i could and still love this team {_HEART_HANDS} #overcastfam"],
    ("sincere", "carried"): [f"found some rounds for us, we'll find more {_HEART_HANDS} #overcastfam", f"happy with the work, hungry for the close {_HEART_HANDS} #overcastfam"],
    ("sincere", "came_apart"): [f"rough map from me, owning it and back to tape {_HEART_HANDS} #overcastfam", f"that one was on my desk, i'll clean it up {_HEART_HANDS} #overcastfam"],
    ("dry", "team_win"): ["won the rounds nobody clapped for. as usual.", "quiet game. good game.", "someone has to hold the corner. you're welcome."],
    ("dry", "team_loss"): ["you peeked the same corner twice. i noticed.", "i'll remember this one. i remember all of them.", "we lost. i was watching."],
    ("dry", "mvp"): ["quiet top frag. loud room.", "i found rounds. not enough of them."],
    ("dry", "carried"): ["did the quiet work. check the tape.", "corner held. map didn't."],
    ("dry", "came_apart"): ["missed the timing. i noticed.", "bad lurk. i remember."],
}

#: Final fallback for an external author with no authored voice pack — keeps the
#: contract that every Chirper post renders to non-empty text even for an
#: out-of-cast handle (a future broadcast cameo, an ad-hoc rival).
_EXTERNAL_FALLBACK: dict[bool, list[str]] = {
    True: ["good map.", "and that's the map."],
    False: ["tape doesn't lie.", "and that's the map."],
}


def _lead_kind(why: WhyRecord) -> Optional[str]:
    """The leading key-moment kind in this match, by colour priority (or ``None``)."""
    moments = {m.kind for m in why.key_moments}
    return next((k for k in _MOMENT_PRIORITY if k in moments), None)


def _chirper_mood(local_outcome: LocalOutcome, won: bool) -> str:
    """Register-copy key: personal outcome first, team mood for neutral players."""
    if local_outcome == "neutral":
        return "team_win" if won else "team_loss"
    return local_outcome


def _memory_sentiment(local_outcome: LocalOutcome, won: bool) -> str:
    """Ground starter posts in a precedent matching the player's visible mood."""
    if local_outcome in {"mvp", "carried"}:
        return "positive"
    if local_outcome == "came_apart":
        return "negative"
    return "positive" if won else "negative"


def _cast_lookup(
    voice: dict[tuple[str, bool], list[str]],
    beat: Optional[str],
    won: bool,
    *,
    local_outcome: LocalOutcome = "neutral",
    outcome_voice: Optional[dict[LocalOutcome, list[str]]] = None,
) -> list[str]:
    """Resolve a cast voice + local outcome + beat → the line list to draw from.

    Priority is the author's personal outcome, then ``(beat, won)`` for the
    exact key moment, then the cast's ``("default", won)``. Every cast voice in
    ``_CAST_VOICES`` ships a ``("default", True)`` and ``("default", False)``,
    so this always returns a non-empty list for an authored cast member.
    """
    if local_outcome != "neutral" and outcome_voice is not None:
        lines = outcome_voice.get(local_outcome)
        if lines:
            return lines
    if beat is not None:
        lines = voice.get((beat, won))
        if lines:
            return lines
    return voice[("default", won)]


def _render_chirper(ctx: GenerationContext) -> GeneratedContent:
    ctx.require("chirper_post", why=ctx.why, author=ctx.author)
    why, author = ctx.why, ctx.author
    assert why is not None and author is not None  # narrowed by require()

    ovc, opp = why.scoreline
    won = ovc > opp
    player = ctx.player(author)
    beat = _lead_kind(why)
    local_outcome = ctx.local_outcome or (
        derive_local_outcome(why, author) if player is not None else "neutral"
    )
    # The beat is woven into the rng so a "choke" and a "blowout" loss read
    # differently for the same cast member, while two same-beat matches still
    # render identically. The local outcome is part of the seed because "MVP in
    # a loss" should not draw from the same line slot as a neutral loss.
    rng = _rng(
        "chirper_post", author, why.seed, ovc, opp, beat or "no_beat", local_outcome
    )

    if player is None:
        # External voice (caster / rival star): no persona-grounded memory log,
        # so no cite. Fall back through the authored external pack, then to the
        # safety net.
        voice = _CAST_VOICES.get(author)
        if voice is not None:
            text = _pick(rng, _cast_lookup(voice, beat, won))
        else:
            text = _pick(rng, _EXTERNAL_FALLBACK[won])
        return GeneratedContent(kind="chirper_post", text=text, grounding_status="ok", author=author, cites=[])

    voice = _CAST_VOICES.get(player.id)
    if voice is not None:
        text = _pick(
            rng,
            _cast_lookup(
                voice,
                beat,
                won,
                local_outcome=local_outcome,
                outcome_voice=_CAST_LOCAL_OUTCOME_VOICES.get(player.id),
            ),
        )
    else:
        register = _register(player)
        text = _pick(rng, _CHIRPER_LINES[(register, _chirper_mood(local_outcome, won))])

    # Ground the post in one of the author's own memories matching the mood.
    precedent = _pick_memory(rng, [player], sentiment=_memory_sentiment(local_outcome, won))
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


#: Every resolver-emittable key-moment kind has at least one authored beat
#: template. Exported so test suites can assert coverage stays total as the
#: resolver grows new kinds.
BEAT_KINDS: frozenset[str] = frozenset(_BEAT_TEMPLATES)

#: Every authored cast voice (the 5 starters plus the caster and the 6 rival
#: stars). Exported so a coverage test can confirm every cast member named in
#: ``docs/tone_and_cast_lock.md`` has an authored entry rather than falling
#: through to the register-based safety net.
CAST_IDS: frozenset[str] = frozenset(_CAST_VOICES)


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
