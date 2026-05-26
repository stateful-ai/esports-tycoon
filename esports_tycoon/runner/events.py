"""The append-only slice run-log: ordered, typed events in ``events.jsonl``.

Running a slice emits an ordered stream of typed events — the practice call, the
private team talk, the resolved match, every key moment and morale delta, the
Chirper feed, the precedent the room remembered, and the grounding tally —
appended one JSON object per line to ``runs/<slice_id>/events.jsonl``. This log is
the *source the recap is derived from*: :func:`~esports_tycoon.runner.recap.render_recap_md`
projects the event stream rather than re-authoring the week from the
:class:`~esports_tycoon.runner.model.SliceResult`. The architecture principle this
lands (company memory ``mem_20260525T191715Z_469386``): the recap artifact is a
*view over the log*, never the authority — and the log stays separate from both the
artifact and the canned memory store.

Events carry the **run's** facts (the decisions made, the resolved match, the
generated prose, the morale deltas, the cite IDs the room grounded) and reference
the cast and the memory log **by ID** — they never copy a player's name or a
memory's summary into the log. The recap renderer resolves those IDs against the
:class:`~esports_tycoon.schema.WorldState` at render time, exactly as it already
resolved cites, so events stay decoupled from the cast/memory stores.

Determinism: events are projected purely from the (deterministic) ``SliceResult``
and serialized with sorted keys, ASCII-safe escaping, and explicit ``\\n``
newlines — so the same seed + decisions yield a byte-identical ``events.jsonl``,
and round-tripping the log through disk reproduces the identical recap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from esports_tycoon.runner.model import SliceResult
from esports_tycoon.schema import PracticeFocus, WorldState

__all__ = [
    "EVENTS_FILENAME",
    "SliceStarted",
    "PracticeChosen",
    "TeamTalk",
    "MatchResolved",
    "HalftimeAck",
    "KeyMomentLogged",
    "StandoutsLogged",
    "MoraleDelta",
    "FeedPosted",
    "RoomRemembered",
    "GroundingSummary",
    "SliceEvent",
    "slice_events",
    "serialize_event",
    "write_events",
    "read_events",
]

#: The run-log filename, alongside ``recap.md`` + ``feed.snapshot.html`` in
#: ``runs/<slice_id>/``.
EVENTS_FILENAME = "events.jsonl"


class _Event(BaseModel):
    """Base for every run-log event.

    ``extra="forbid"`` makes each event a total description of its line: an
    unmodelled key in a stored log fails the read loudly instead of being
    silently dropped, which keeps the log honest about what a run recorded.
    """

    model_config = ConfigDict(extra="forbid")


class SliceStarted(_Event):
    """The run's identity and fixture knobs — the first line of every log.

    Carries only the *config* of the run (the content-addressed id, the seed, the
    backend, and the week's fixture). The static world context — the team name,
    the standing, the opponent's name and archetype — is resolved from the
    :class:`~esports_tycoon.schema.WorldState` at render time, not copied here.
    """

    type: Literal["slice_started"] = "slice_started"
    slice_id: str
    seed: int
    content_backend: str
    opponent: str
    map: str


class PracticeChosen(_Event):
    """The MC decision: what the practice block drilled this week."""

    type: Literal["practice_chosen"] = "practice_chosen"
    focus: PracticeFocus


class TeamTalk(_Event):
    """The private pre-match team talk (open text; empty means nothing was said)."""

    type: Literal["team_talk"] = "team_talk"
    text: str


class MatchResolved(_Event):
    """The resolved match: the final + half scorelines and the narration prose.

    ``cites`` are the memory IDs the narration bound — the bound precedent the
    recap surfaces in its fixed scannable slot. Stored as IDs (the renderer
    resolves them at render time, the same way feed-post cites are handled), so
    a memory's summary text never lands in the log.
    """

    type: Literal["match_resolved"] = "match_resolved"
    scoreline: tuple[int, int]
    halftime_scoreline: tuple[int, int]
    narration: str
    cites: list[str] = Field(default_factory=list)


class HalftimeAck(_Event):
    """The half-time ack: who said it (``None`` ⇒ the bench) and the line."""

    type: Literal["halftime_ack"] = "halftime_ack"
    text: str
    author: Optional[str] = None


class KeyMomentLogged(_Event):
    """One narratable beat the resolver surfaced; ``actors`` are player IDs."""

    type: Literal["key_moment"] = "key_moment"
    round: int
    kind: str
    actors: list[str]
    descriptor: str


class StandoutsLogged(_Event):
    """The match standouts, as player IDs: who was MVP, carried, and came apart."""

    type: Literal["standouts"] = "standouts"
    mvp: str
    who_carried: list[str]
    who_tilted: list[str]


class MoraleDelta(_Event):
    """One player's morale change. Emitted in roster order, one event per player."""

    type: Literal["morale_delta"] = "morale_delta"
    player: str
    delta: int


class FeedPosted(_Event):
    """One Chirper post, in feed order. ``cites`` are memory IDs the post grounded.

    The display ``author_name``/``author_handle`` are part of the run's generated
    output (external voices have no player ID), so they are recorded verbatim;
    the ``cites`` stay as IDs the recap resolves against the memory log.
    """

    type: Literal["feed_post"] = "feed_post"
    author_handle: str
    author_name: str
    text: str
    cites: list[str] = Field(default_factory=list)
    grounding_status: str = "ok"


class RoomRemembered(_Event):
    """The precedent the week cited, as sorted memory IDs (resolved at render time)."""

    type: Literal["memories_remembered"] = "memories_remembered"
    cites: list[str]


class GroundingSummary(_Event):
    """The grounding tally over the pieces that attempt to cite precedent."""

    type: Literal["grounding_summary"] = "grounding_summary"
    grounded_ok: int
    grounded_total: int


#: A single run-log line: the discriminated union of every event kind, dispatched
#: on its ``type`` tag so a stored line parses back to its exact subtype.
SliceEvent = Annotated[
    Union[
        SliceStarted,
        PracticeChosen,
        TeamTalk,
        MatchResolved,
        HalftimeAck,
        KeyMomentLogged,
        StandoutsLogged,
        MoraleDelta,
        FeedPosted,
        RoomRemembered,
        GroundingSummary,
    ],
    Field(discriminator="type"),
]

_EVENT_ADAPTER: TypeAdapter[SliceEvent] = TypeAdapter(SliceEvent)


def slice_events(result: SliceResult, world: WorldState) -> list[SliceEvent]:
    """Project a finished :class:`SliceResult` into its ordered event stream.

    The order is the run's order — the same top-to-bottom order the recap reads
    them back in: the run's identity, the week's decisions, the resolved match and
    its beats, the morale fallout (in roster order), the feed, then what the room
    remembered and how well it grounded. Pure: a function of ``result`` (which is
    itself deterministic) plus the roster order from ``world``.
    """
    events: list[SliceEvent] = [
        SliceStarted(
            slice_id=result.slice_id,
            seed=result.config.seed,
            content_backend=result.content_backend,
            opponent=result.config.opponent,
            map=result.config.map,
        ),
        PracticeChosen(focus=result.decisions.practice_focus),
        TeamTalk(text=result.decisions.team_talk),
        MatchResolved(
            scoreline=result.scoreline,
            halftime_scoreline=result.halftime_scoreline,
            narration=result.narration.text,
            cites=list(result.narration.cites),
        ),
        HalftimeAck(author=result.halftime.author, text=result.halftime.text),
    ]

    for moment in result.why.key_moments:
        events.append(
            KeyMomentLogged(
                round=moment.round,
                kind=moment.kind,
                actors=list(moment.actors),
                descriptor=moment.descriptor,
            )
        )

    events.append(
        StandoutsLogged(
            mvp=result.why.mvp,
            who_carried=list(result.why.who_carried),
            who_tilted=list(result.why.who_tilted),
        )
    )

    # Roster order keeps the morale stream — and so the recap's morale table —
    # stable across runs, independent of the morale_deltas dict's ordering.
    for player in world.players:
        if player.id in result.why.morale_deltas:
            events.append(MoraleDelta(player=player.id, delta=result.why.morale_deltas[player.id]))

    for post in result.feed:
        events.append(
            FeedPosted(
                author_handle=post.author_handle,
                author_name=post.author_name,
                text=post.text,
                cites=list(post.cites),
                grounding_status=post.grounding_status,
            )
        )

    events.append(RoomRemembered(cites=list(result.cited_memories)))
    events.append(GroundingSummary(grounded_ok=result.grounded_ok, grounded_total=result.grounded_total))
    return events


def serialize_event(event: SliceEvent) -> str:
    """One canonical, diff-stable JSON line for ``event`` (no trailing newline).

    ``sort_keys`` + ASCII escaping + compact separators mirror the
    content-addressing in :func:`~esports_tycoon.runner.engine.slice_id`, so the
    bytes are independent of field declaration order and identical across runs and
    platforms.
    """
    payload = event.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def write_events(events: list[SliceEvent], path: Union[str, Path]) -> Path:
    """Write the ordered run-log to ``path``, appending one event per line.

    The log is append-only by nature — records are only ever added, in run order,
    never edited or reordered. A slice is content-addressed and deterministic, so
    finalizing a run materializes its full ordered log; re-finalizing the same
    slice reproduces a byte-identical file (UTF-8, explicit ``\\n``). Returns the
    path written.
    """
    target = Path(path)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        for event in events:
            fh.write(serialize_event(event) + "\n")
    return target


def read_events(path: Union[str, Path]) -> list[SliceEvent]:
    """Parse an ``events.jsonl`` run-log back into typed, ordered events.

    Each non-blank line is validated against the discriminated union, so a line
    parses back to its exact event subtype (and a malformed or unknown line fails
    loudly rather than being skipped). Order is preserved.
    """
    events: list[SliceEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(_EVENT_ADAPTER.validate_json(line))
    return events
