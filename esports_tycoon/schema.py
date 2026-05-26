"""Typed game schema for esports-tycoon (M0).

These are the runtime pydantic models the rest of the slice is built on. They
mirror the schemas pinned in ``m0_technical_plan.md`` and are the typed twin of
the hand-authored canned save at the canonical save root, ``saves/week6.yaml``
(loaded by ``esports_tycoon.canned.loader``; field reference in
``saves/SCHEMA.md``).

Two domain invariants are enforced here, not just by the (decoupled) cast-lock
gate:

* **Stable cite IDs.** Every memory entry carries a stable, opaque identifier of
  the form ``mem:<player_id>:<event_slug>``. The format is validated wherever an
  ID or a cite to one appears, the owner segment must match the player whose log
  it lives in, and IDs are globally unique.
* **No hallucinated history.** Every cite emitted anywhere in a :class:`WorldState`
  (clash pairs, rivals, the Chirper feed) must resolve to a memory entry that
  actually exists in the log. :meth:`WorldState.resolve_cite` is the renderer's
  resolution hook.

The cast-lock validator deliberately stays a structural, dict-based gate (see
``esports_tycoon/cast_lock``); this module is the typed schema it referred to as
a later ticket.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "MEMORY_ID_RE",
    "GroundingError",
    "Role",
    "MemoryKind",
    "Sentiment",
    "MemoryId",
    "Relationship",
    "MemoryEntry",
    "Player",
    "Standing",
    "Team",
    "Season",
    "SaveMeta",
    "RivalStar",
    "Rival",
    "ClashPair",
    "MapResult",
    "Scoreline",
    "ChirperPost",
    "LastWeek",
    "WorldState",
    "PracticeFocus",
    "TacticalStance",
    "Decisions",
    "KeyMoment",
    "RoundResult",
    "WhyRecord",
    "GeneratedContent",
]

#: The save-format version this build reads and writes. The save is
#: self-describing (``m0_0_canonical_contract.md`` §3): every save carries a
#: ``schema_version``, and the loader turns an older save into this version or
#: refuses it with a clear message. Bump this when the on-disk shape changes
#: incompatibly, and register the upgrade step in
#: :mod:`esports_tycoon.canned.loader` so old saves migrate forward rather than
#: being rejected.
CURRENT_SCHEMA_VERSION = 0


class GroundingError(ValueError):
    """A :class:`WorldState` failed its grounding contract.

    Raised from :meth:`WorldState._grounding_holds` when memory IDs collide or a
    cite anywhere in the world (clash pairs, rivals, the Chirper feed) points
    at no memory entry the save defines. Carries a structured ``field_path``
    naming the offending location (e.g.
    ``"clash_pairs[0].seeded_by[0]"``) so the loader can lift it into the
    shared :class:`esports_tycoon.canned.loader.SaveError` contract without
    parsing the message back out. A ``ValueError`` subclass so direct
    ``WorldState.model_validate`` callers that catch ``ValueError`` on a bad
    save keep working, and so pydantic preserves it as ``ctx['error']`` on the
    resulting :class:`pydantic.ValidationError`.
    """

    def __init__(self, message: str, *, field_path: str) -> None:
        super().__init__(message)
        self.field_path = field_path

# `mem:<player_id>:<event_slug>` — lowercase ascii, dash-snake event slug.
# Kept identical to esports_tycoon.cast_lock.spec.MEMORY_ID_RE; the two modules
# stay decoupled, and tests/test_schema.py guards against the formats drifting.
MEMORY_ID_RE = re.compile(r"^mem:([a-z0-9_]+):([a-z0-9]+(?:_[a-z0-9]+)*)$")


def _check_memory_id(value: str) -> str:
    if not MEMORY_ID_RE.match(value):
        raise ValueError(
            f"{value!r} is not a valid memory ID (want mem:<player_id>:<event_slug>, "
            "lowercase ascii dash-snake)"
        )
    return value


#: A string constrained to the stable cite-ID format. Used for memory entry IDs
#: and for every cite that points at one.
MemoryId = Annotated[str, AfterValidator(_check_memory_id)]


class Role(str, Enum):
    """The five Vector Strike roles; exactly one per starter."""

    IGL = "IGL"
    DUELIST = "DUELIST"
    CONTROLLER = "CONTROLLER"
    SENTINEL = "SENTINEL"
    INITIATOR = "INITIATOR"


#: The kinds of precedent a memory entry can record.
MemoryKind = Literal["match", "scrim", "social", "1on1", "press", "rumor"]

#: A memory entry's emotional charge.
Sentiment = Literal["positive", "neutral", "negative"]


class _Model(BaseModel):
    """Base config shared by every save model.

    ``extra="forbid"`` makes the schema a faithful, total description of the
    canned save: any key in the YAML that is not modelled here fails the load
    loudly instead of being silently dropped, which is what keeps the
    round-trip lossless.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Relationship(_Model):
    """A directed relationship from a player to a teammate or rival."""

    # `with` is a Python keyword, so the field is `with_` with a YAML alias.
    with_: str = Field(alias="with")
    kind: str
    status: str
    note: str


class MemoryEntry(_Model):
    """One canned, ordered precedent with a stable, opaque ID.

    Templates and LLM prompts are passed entries from this log (and never
    free-form simulation strings); the renderer resolves cites back to them.
    """

    id: MemoryId
    week: int = Field(ge=0)
    day: int = Field(ge=1, le=7)
    kind: MemoryKind
    actors: list[str]
    summary: str
    sentiment: Sentiment
    tags: list[str] = Field(default_factory=list)


class Player(_Model):
    """A starter: their identity, voice contract, relationships, and memory log."""

    id: str
    name: str
    handle: str
    role: Role
    age: int = Field(ge=0)
    signature_operative: str
    bio: str
    persona_voice: str
    traits: list[str]
    relationships: list[Relationship] = Field(default_factory=list)
    memory_log: list[MemoryEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _memory_owner_matches(self) -> "Player":
        """Every entry in this log must be owned by this player.

        The owner segment of ``mem:<player_id>:<event_slug>`` is the contract
        that ties a memory to whose head it lives in; a mismatch means the entry
        was filed under the wrong player.
        """
        mismatched = [
            entry.id
            for entry in self.memory_log
            if MEMORY_ID_RE.match(entry.id).group(1) != self.id  # type: ignore[union-attr]
        ]
        if mismatched:
            raise ValueError(
                f"player {self.id!r} owns memories belonging to others: {mismatched}"
            )
        return self


class Standing(_Model):
    """Where a team sits in the table."""

    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    place: int = Field(ge=1)
    of: int = Field(ge=1)
    note: str


class Team(_Model):
    """The org the founder manages."""

    id: str
    name: str
    tag: str
    handle: str
    blurb: str
    standing: Standing


class Season(_Model):
    """League / split context for the current week."""

    league: str
    division: str
    total_weeks: int = Field(ge=1)
    current_week: int = Field(ge=1)
    playoff_cutoff: int = Field(ge=1)


class SaveMeta(_Model):
    """Top-level save identity plus the locked tone/flavor and standings."""

    id: str
    title: str
    game: str
    tone: str
    flavor: str
    fiction_note: str
    season: Season
    team: Team


class RivalStar(_Model):
    """The named star carrying a rival org's narrative pressure."""

    id: str
    name: str
    role: Role
    handle: str


class Rival(_Model):
    """An opposing org and the distinct pressure it puts on the roster."""

    id: str
    name: str
    tag: str
    handle: str
    archetype: str
    star: RivalStar
    bio: str
    pressure_on_overcast: str
    seeded_by: list[MemoryId] = Field(default_factory=list)


class ClashPair(_Model):
    """An explicit, seeded tension between two characters.

    Intra-team pairs are the room's combustion; cross-team pairs (``cross_team``
    true, with a ``rival_org``) seed the rival subplots. ``seeded_by`` cites the
    memories that justify the clash.
    """

    a: str
    b: str
    cross_team: bool
    axis: str
    summary: str
    seeded_by: list[MemoryId] = Field(default_factory=list)
    rival_org: Optional[str] = None


class MapResult(_Model):
    """One map's scoreline inside a series."""

    map: str
    overcast: int = Field(ge=0)
    opponent: int = Field(ge=0)
    result: str
    note: Optional[str] = None


class Scoreline(_Model):
    """A series result with its per-map breakdown."""

    overcast: int = Field(ge=0)
    opponent: int = Field(ge=0)
    maps: list[MapResult]


class ChirperPost(_Model):
    """A single post in the in-universe social feed.

    ``cites`` are memory IDs the post is grounded in; the renderer resolves them
    against the log. External voices (casters) may omit ``author_id``.
    """

    id: str
    author: str
    day: int = Field(ge=1, le=7)
    text: str
    cites: list[MemoryId] = Field(default_factory=list)
    likes: int = Field(ge=0)
    author_id: Optional[str] = None
    reply_to: Optional[str] = None
    note: Optional[str] = None


class LastWeek(_Model):
    """Last week's result and the Chirper feed that came out of it."""

    week: int = Field(ge=0)
    opponent: str
    format: str
    result: str
    scoreline: Scoreline
    headline: str
    chirper_feed: list[ChirperPost] = Field(default_factory=list)


class WorldState(_Model):
    """The whole canned world: the typed result of loading the canned save.

    Construction enforces the grounding contract — globally unique memory IDs and
    no dangling cites — so a successfully loaded ``WorldState`` is one whose
    history every cite can resolve against.

    The save is the system of record for determinism, too: it carries its own RNG
    :attr:`seed` (the *seed-in-save* contract, ``m0_0_canonical_contract.md`` §2/§6).
    The seed is **required** — a save with no seed is not a valid save — so every
    load yields a world that knows the generator its outcomes derive from, and the
    seed survives the byte-identical round-trip like any other authored field. The
    match resolver draws its randomness from this seed by default, which is what
    anchors "same save ⇒ bit-reproducible match" in the save itself rather than in
    whatever a caller happens to pass.
    """

    #: The save-format version this document was written against. Carried so the
    #: save is self-describing; the load-time gate in
    #: :mod:`esports_tycoon.canned.loader` migrates an older value forward to
    #: :data:`CURRENT_SCHEMA_VERSION` or refuses the save. The field itself only
    #: constrains the shape (a non-negative int) — version *compatibility* is the
    #: loader's job, not the schema's, so direct ``model_validate`` stays usable.
    schema_version: int = Field(ge=0)
    #: The save's RNG seed. Required (no default) so it is always present in the
    #: save and always serialized; ``ge=0`` matches the house style for the save's
    #: other integers and keeps authored seeds clean.
    seed: int = Field(ge=0)
    save: SaveMeta
    players: list[Player]
    clash_pairs: list[ClashPair] = Field(default_factory=list)
    rivals: list[Rival] = Field(default_factory=list)
    last_week: LastWeek

    @model_validator(mode="after")
    def _grounding_holds(self) -> "WorldState":
        # Globally unique memory IDs. Walk in save order, remember the first
        # entry's path per id, and report each duplicate against the path it
        # collides at — first-seen path goes in the message body, the
        # *second* occurrence is the surfaced ``field_path`` so the author
        # can take the message straight to the offending line they just added.
        first_path: dict[str, str] = {}
        duplicates: list[tuple[str, str, str]] = []  # (mem_id, first, second)
        for pi, player in enumerate(self.players):
            for mi, entry in enumerate(player.memory_log):
                path = (
                    f"players[{pi}={player.id}].memory_log[{mi}={entry.id}].id"
                )
                if entry.id in first_path:
                    duplicates.append((entry.id, first_path[entry.id], path))
                else:
                    first_path[entry.id] = path
        if duplicates:
            details = "; ".join(
                f"{mem_id!r} appears at {first} and {second}"
                for mem_id, first, second in duplicates
            )
            raise GroundingError(
                f"memory IDs must be globally unique: {details}",
                field_path=duplicates[0][2],
            )

        known = set(first_path)
        # Each dangling reference is reported with its structured field path
        # *and* the entity descriptor (``clash a/b``, ``rival id``,
        # ``chirp post-id``) so a human reader sees both the line to jump to
        # and the actor context, while the loader can lift the first path
        # into the shared ``SaveError.field_path`` without parsing the body.
        dangling: list[tuple[str, str, str]] = []  # (path, descriptor, cite)
        for ci, pair in enumerate(self.clash_pairs):
            for cj, cite in enumerate(pair.seeded_by):
                if cite not in known:
                    dangling.append(
                        (
                            f"clash_pairs[{ci}].seeded_by[{cj}]",
                            f"clash {pair.a}/{pair.b}",
                            cite,
                        )
                    )
        for ri, rival in enumerate(self.rivals):
            for cj, cite in enumerate(rival.seeded_by):
                if cite not in known:
                    dangling.append(
                        (
                            f"rivals[{ri}={rival.id}].seeded_by[{cj}]",
                            f"rival {rival.id}",
                            cite,
                        )
                    )
        for fi, post in enumerate(self.last_week.chirper_feed):
            for cj, cite in enumerate(post.cites):
                if cite not in known:
                    dangling.append(
                        (
                            f"last_week.chirper_feed[{fi}={post.id}].cites[{cj}]",
                            f"chirp {post.id}",
                            cite,
                        )
                    )
        if dangling:
            details = "; ".join(
                f"{path} ({descriptor}) -> {cite}"
                for path, descriptor, cite in dangling
            )
            raise GroundingError(
                f"cites must resolve to a real memory (no hallucinated history): {details}",
                field_path=dangling[0][0],
            )
        return self

    @property
    def team(self) -> Team:
        """The org the founder manages — shorthand for ``save.team``.

        Pairs with :attr:`roster`: together they are the canonical "managed team
        and its players" the match resolver fields. Exposing them here lets a
        consumer take the side straight off the loaded world instead of
        re-assembling it from ``save.team`` plus the top-level player list.
        """
        return self.save.team

    @property
    def roster(self) -> list[Player]:
        """The managed team's starters, in save order.

        In M0 the top-level ``players`` list *is* :attr:`team`'s roster — rival
        personnel live under ``rivals[].star``, never here — so this names that
        relationship explicitly. The resolver fields its lineup from this roster
        rather than reaching for the bare ``players`` list, which keeps its input
        the canonical team/roster pair. Derived (not a stored field), so the
        byte-identical save round-trip is unaffected.
        """
        return self.players

    @property
    def cite_index(self) -> dict[str, MemoryEntry]:
        """Map every stable cite ID to its memory entry."""
        return {entry.id: entry for player in self.players for entry in player.memory_log}

    @property
    def memory_ids(self) -> frozenset[str]:
        """The set of all stable cite IDs in this world."""
        return frozenset(entry.id for player in self.players for entry in player.memory_log)

    def resolve_cite(self, cite: str) -> Optional[MemoryEntry]:
        """Resolve a cite ID to its memory entry, or ``None`` if unknown.

        This is the renderer's grounding hook: an unresolvable cite is the signal
        to regenerate (then drop) LLM output rather than ship invented history.
        """
        return self.cite_index.get(cite)


# --------------------------------------------------------------------------- #
# Resolver input. Not part of the canned save; defined here so the slice runner
# and the resolver share one contract. See m0_technical_plan.md.
# --------------------------------------------------------------------------- #
#: What the practice block drilled. Each focus lifts the roles it suits.
PracticeFocus = Literal["aim", "comms", "defaults", "anti_strat", "rest"]

#: How the team is told to play the match.
TacticalStance = Literal["aggressive", "default", "disciplined"]


class Decisions(_Model):
    """The manager's inputs to one week's match resolution.

    This is the *structured* half of the weekly decision surface — the part a
    pure, headless resolver can act on. The open-text moments (capped, tone-
    aligned) belong to the content layer, never here: interpreting free text
    would require an LLM, and rule #1 of the architecture is that the LLM is
    never inside the resolver.

    ``opponent`` (a rival org id) and ``map`` are the week's fixture;
    ``lineup``, ``practice_focus`` and ``tactical_stance`` are the controllables.
    An empty ``lineup`` means "field the five canned starters" — the resolver
    fills it in, so the common case needs only an opponent.
    """

    opponent: str
    map: str = "Helix"
    lineup: list[str] = Field(default_factory=list)
    practice_focus: PracticeFocus = "defaults"
    tactical_stance: TacticalStance = "default"


# --------------------------------------------------------------------------- #
# Resolver / content-adapter outputs. Not part of the canned save; defined here
# so every ticket shares one schema. See m0_technical_plan.md.
# --------------------------------------------------------------------------- #
class KeyMoment(_Model):
    """A narratable beat the resolver surfaces from a match."""

    round: int = Field(ge=1)
    kind: str
    actors: list[str]
    descriptor: str


class RoundResult(_Model):
    """One round's outcome. Carried for debug / replay; never narrated directly."""

    round: int = Field(ge=1)
    winner: str
    summary: str


class WhyRecord(_Model):
    """The structured match explanation the resolver hands the narrator.

    The LLM is never inside the resolver: narration consumes this record (plus
    the relevant slice of memory log) verbatim — no free-form simulation strings.
    """

    scoreline: tuple[int, int]
    mvp: str
    key_moments: list[KeyMoment] = Field(default_factory=list)
    who_carried: list[str] = Field(default_factory=list)
    who_tilted: list[str] = Field(default_factory=list)
    morale_deltas: dict[str, int] = Field(default_factory=dict)
    seed: int
    round_log: list[RoundResult] = Field(default_factory=list)


class GeneratedContent(_Model):
    """A single piece of rendered content, post-grounding.

    Produced by the content adapter in either templated (zero-API) or LLM mode;
    ``cites`` are the memory IDs the renderer resolved, and ``grounding_status``
    records whether the cites held, were regenerated, or were dropped.
    """

    kind: Literal["chirper_post", "narration", "halftime_ack", "interview"]
    text: str
    grounding_status: Literal["ok", "regen", "dropped"]
    author: Optional[str] = None
    cites: list[MemoryId] = Field(default_factory=list)
    raw_llm_output: Optional[str] = None
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
