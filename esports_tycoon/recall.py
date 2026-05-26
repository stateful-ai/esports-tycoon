"""Deterministic precedent-recall selector — pure, engine-side, zero RNG.

The narrator never asks "what precedent feels right" — it asks
:func:`recall`, which ranks every canned memory in the world by how strongly
it rhymes with the match that just resolved. The ranking has three signals,
in priority order:

* **shared actors** — the count of overlap between the people the resolver
  named (key-moment actors and actor_refs, the MVP, who carried, who came
  apart) and the memory entry's actors. Memory is a social object; a precedent
  involving the same people is the strongest possible match.
* **tag overlap** — the count of overlap between the *frozen recall
  vocabulary* the resolver tagged the beats with
  (:data:`~esports_tycoon.schema.RECALL_TAGS` = ``{choke, clutch, tilt,
  rivalry}``, populating :attr:`~esports_tycoon.schema.KeyMoment.tag` and
  augmented with ``"tilt"`` when :attr:`~esports_tycoon.schema.WhyRecord.who_tilted`
  is non-empty) and the memory entry's
  :attr:`~esports_tycoon.schema.MemoryEntry.recall_tags`. Both sides of the
  join speak the same typed enum — a beat the resolver could not tag, or a
  memory the author did not opt onto the recall plane, contributes no tag
  score. There is no fallback to the open-form
  :attr:`~esports_tycoon.schema.MemoryEntry.tags` list: recall fails closed
  when the typed signal is absent, by design.
* **active rivalry** — a flat ``+1`` when any actor in the beat has an
  authored ``kind="rival"`` :class:`~esports_tycoon.schema.Relationship` and
  the memory entry rhymes with that rivalry. The entry rhymes by either
  (a) *naming* the rival directly in its ``actors`` (the entry calls out
  Halo, and Halo is the rival of someone on the beat); or (b) *opting
  onto the rivalry plane* with ``"rivalry"`` in its
  :attr:`~esports_tycoon.schema.MemoryEntry.recall_tags` *and* sharing an
  actor with the beat (a Vex-owned rivalry-tagged memory surfaces when
  Vex is on the line, but not when she's benched). The actor-overlap
  guard on the tag route is deliberate — without it, every rivalry-
  tagged memory in the save would surface for every beat carrying any
  active rival, regardless of whose rivalry it documents.

Sort is by ``(-actor_score, -tag_score, -rivalry_score)`` and Python's
``sorted`` is stable, so equal-scored entries fall back to save order
(``world.players`` order, then each player's ``memory_log`` order). This is
what makes the function fully deterministic: every key is a pure function of
the inputs, ties are broken by save order, and **identical inputs always
yield the identical ordered list** — no ``random.Random``, no LLM, no clock,
no entropy of any kind. The function takes no seed and accepts no client.

The selector's output is the locked :class:`RecallResult` contract — six
named, typed fields that copy templates bind by name without any further
world lookups. The seam was locked so Wave-1 (this selector) and Wave-2
(copy) can land in parallel: Wave-1 fills the fields, Wave-2 reads them,
and neither has to rework the other when their work meets in the middle.
See ``docs/recall_render_contract.md`` for the seam's prose contract.

The templated narrator (:mod:`esports_tycoon.content.templated`) binds
against this: it picks the recalled precedent for the beat it's narrating
and stamps its ``cite_id`` into the generated content's ``cites``, which is
what the recap's "What the room remembered" section quotes back. So a week-6
choke surfaces the week-5 scrim choke (or the unresolved week-2 override
that lit it), and that precedent rides into the rendered output by ID
rather than by RNG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from esports_tycoon.schema import MEMORY_ID_RE, MemoryEntry, WhyRecord, WorldState

__all__ = ["recall", "score", "Precedent", "RecallResult"]


@dataclass(frozen=True)
class Precedent:
    """A canned memory plus the per-signal scores it earned against a match.

    Exposed (and exported) so callers can introspect *why* a precedent rose to
    the top — useful for explanations in the recap and for tests that pin the
    scoring contract rather than the final ordering. Carries the structured
    "which" sets (``matched_actors`` / ``matched_tags`` / ``matched_rivals``)
    alongside the integer scores so :class:`RecallResult` can name the
    specific signals without re-scoring.
    """

    entry: MemoryEntry
    actor_score: int
    tag_score: int
    rivalry_score: int
    matched_actors: frozenset[str]
    matched_tags: frozenset[str]
    matched_rivals: frozenset[str]


@dataclass(frozen=True)
class RecallResult:
    """The locked recall→render output contract.

    Every field is a stable handle copy templates bind by name without any
    further world lookups: the cite to ground against, the cast member the
    precedent attaches to, the week it happened, a one-line summary, the
    strongest authored tag that rhymes with the match, and a short structured
    reason. Wave-1 (the selector) populates these; Wave-2 (copy) reads them.
    The seam is closed: changing the rendered text never requires re-shaping
    the selector, and re-tuning the selector never breaks the copy pack as
    long as these six fields keep the same names and types.

    See ``docs/recall_render_contract.md`` for the prose contract and the
    Wave-1 / Wave-2 split this struct exists to lock down.

    Fields:
      cite_id: stable memory id, ``mem:<owner>:<event_slug>``. The grounding
        handle the renderer stamps into ``GeneratedContent.cites``; resolves
        back to a :class:`~esports_tycoon.schema.MemoryEntry` via
        :meth:`WorldState.resolve_cite`.
      actor_ref: the cast member the precedent attaches to — the owner of
        the ``memory_log`` it lives in (parsed from ``cite_id``). A single-
        string anchor copy can bind without joining against the world (e.g.
        ``f"{actor_ref} remembered ..."``).
      week: the in-fiction week the original event happened. Plain int so
        copy can render ``"week {week}"`` or compare against the current
        week to phrase "last week" / "five weeks ago".
      event_summary: the canned one-line summary copy can quote verbatim.
        Comes from the authored memory entry, so it stays in the save's
        tone and never contains free-form simulation text.
      matched_tag: the authored tag from the entry's own ``tags`` list that
        rhymes with this match's target tag vocabulary — preserves the
        entry's casing (so copy can render it without re-casing). ``None``
        when the entry surfaced on actor or rivalry overlap alone. Picked
        deterministically by entry-tag order: the first authored tag whose
        lowercase form is in the matched set, so the same precedent always
        projects the same tag.
      relevance_reason: a short, structured explanation of *why* this entry
        ranked, assembled from the matched signals in priority order
        (``"shared actors: ...; tag: ...; active rivalry: ..."``). Always
        non-empty — the selector only yields entries with at least one
        non-zero signal — so copy can render it verbatim ("the room
        remembered, because of …") or branch on the leading clause.
    """

    cite_id: str
    actor_ref: str
    week: int
    event_summary: str
    matched_tag: Optional[str]
    relevance_reason: str


def _why_actors(why: WhyRecord) -> frozenset[str]:
    """Every player the resolver named in this match.

    The narrator may pick any one beat to lead with, but recall ranks against
    the *whole* match: every key moment's actors and its (typed) actor_ref,
    plus the MVP, who carried, and who came apart. That keeps the signal
    strong on a match where one beat names one starter and another names the
    rest.
    """
    actors: set[str] = set()
    for moment in why.key_moments:
        actors.update(moment.actors)
        if moment.actor_ref is not None:
            actors.add(moment.actor_ref)
    if why.mvp:
        actors.add(why.mvp)
    actors.update(why.who_carried)
    actors.update(why.who_tilted)
    return frozenset(actors)


def _target_tags(why: WhyRecord) -> frozenset[str]:
    """The frozen recall vocabulary this match rhymes with.

    Reads :attr:`KeyMoment.tag` (the typed
    :data:`~esports_tycoon.schema.RecallTag` opt-in) directly — there is no
    fallback to ``kind`` or any other open-form signal, so a beat the resolver
    could not tag contributes nothing to tag-overlap. The ``"tilt"`` boost from
    :attr:`WhyRecord.who_tilted` is layered on top: a tilted lineup pulls
    tilt-tagged precedents even on a beat that does not itself rhyme with tilt.
    """
    tags: set[str] = set()
    for moment in why.key_moments:
        if moment.tag is not None:
            tags.add(moment.tag)
    if why.who_tilted:
        tags.add("tilt")
    return frozenset(tags)


def _active_rivals(world: WorldState, actors: frozenset[str]) -> frozenset[str]:
    """Every party named in a ``kind="rival"`` relationship of an actor.

    These are the rivalries the *fielded* roster carries into this match (Rook
    has Echo, Vex has Halo, Coyote has Bishop). A memory that drags one of
    those names back in — either by naming the rival in its actors or by
    opting onto the rivalry plane with ``"rivalry"`` in its recall tags —
    earns the rivalry bonus. See :func:`score` for how the two routes are
    matched.
    """
    rivals: set[str] = set()
    for player in world.players:
        if player.id not in actors:
            continue
        for rel in player.relationships:
            if rel.kind == "rival":
                rivals.add(rel.with_)
    return frozenset(rivals)


def score(why: WhyRecord, world: WorldState) -> list[Precedent]:
    """The full ranked candidate list, before truncation.

    Exposed so callers (tests, the recap) can inspect the ranking and the
    structured signals each entry earned, without paying the ``[:k]`` slice.
    Same ordering and same determinism contract as :func:`recall`.
    """
    actors = _why_actors(why)
    tags = _target_tags(why)
    rivals = _active_rivals(world, actors)

    candidates: list[Precedent] = []
    for player in world.players:
        for entry in player.memory_log:
            entry_actors = set(entry.actors)
            entry_recall_tags = set(entry.recall_tags)
            matched_actors = frozenset(actors & entry_actors)
            matched_tags = frozenset(tags & entry_recall_tags)
            # Rivalry has two routes onto the recall plane and they live in
            # disjoint value spaces — player IDs vs. the {choke,clutch,tilt,
            # rivalry} enum — so a single intersection cannot express both.
            #
            # The named-actor route fires when the entry names a rival of
            # someone on the beat (the rival appears in entry.actors). This is
            # the strong, specific signal: "Vex once trash-talked Halo, and
            # Halo is on the line today."
            #
            # The tag route fires when the entry opts onto the rivalry plane
            # with ``"rivalry"`` in recall_tags AND one of its actors is on
            # the beat AND that player has an active rival. The actor-overlap
            # guard is what keeps "vex's rivalry-tagged memory" off of beats
            # where Vex isn't fielded — without it, every rivalry-tagged
            # memory in the save would surface on every beat with any active
            # rival, regardless of whose rivalry it actually documents.
            rivals_by_actor = rivals & entry_actors
            rivalry_via_tag = (
                "rivalry" in entry_recall_tags
                and bool(entry_actors & actors)
                and bool(rivals)
            )
            rivals_by_tag = rivals if rivalry_via_tag else frozenset()
            matched_rivals = frozenset(rivals_by_actor | rivals_by_tag)
            actor_score = len(matched_actors)
            tag_score = len(matched_tags)
            rivalry_score = 1 if matched_rivals else 0
            if actor_score == 0 and tag_score == 0 and rivalry_score == 0:
                continue
            candidates.append(
                Precedent(
                    entry=entry,
                    actor_score=actor_score,
                    tag_score=tag_score,
                    rivalry_score=rivalry_score,
                    matched_actors=matched_actors,
                    matched_tags=matched_tags,
                    matched_rivals=matched_rivals,
                )
            )
    # Stable sort by descending score components: equal-scored entries fall
    # back to save order, which is the order they were appended above.
    candidates.sort(
        key=lambda p: (-p.actor_score, -p.tag_score, -p.rivalry_score)
    )
    return candidates


def _owner_of(cite_id: str) -> str:
    """Parse the owner segment out of a ``mem:<owner>:<event_slug>`` cite.

    ``MemoryEntry.id`` is validated against :data:`MEMORY_ID_RE` at construction
    time, so this match is guaranteed to succeed for any id that came off a
    loaded :class:`~esports_tycoon.schema.WorldState`.
    """
    match = MEMORY_ID_RE.match(cite_id)
    # MemoryId is validated at MemoryEntry construction — the only way this
    # would fail is if a caller hand-built a Precedent with an unvalidated id.
    assert match is not None, f"malformed cite id reached recall: {cite_id!r}"
    return match.group(1)


def _pick_matched_tag(entry: MemoryEntry, matched_tags: frozenset[str]) -> Optional[str]:
    """The first authored tag (in entry order) whose lowercase form matched.

    Preserves the entry's casing so copy renders the tag as authored. ``None``
    when nothing in the entry's tag list rhymed with the match (the entry
    surfaced on actor and/or rivalry overlap alone).
    """
    for tag in entry.tags:
        if tag.lower() in matched_tags:
            return tag
    return None


def _relevance_reason(precedent: Precedent, matched_tag: Optional[str]) -> str:
    """Build the structured ``relevance_reason`` string from matched signals.

    Clauses are emitted in scoring priority — shared actors first, then tag
    overlap, then active rivalry — and joined with ``"; "``. Multi-value
    clauses are sorted alphabetically so the string is byte-identical across
    runs. Always non-empty: recall only yields entries with ≥1 non-zero
    signal, so at least one clause fires.
    """
    clauses: list[str] = []
    if precedent.matched_actors:
        actors = ", ".join(sorted(precedent.matched_actors))
        clauses.append(f"shared actors: {actors}")
    if precedent.matched_tags:
        # Prefer the casing the renderer will see; fall back to a sorted
        # lowercase list when no authored tag was picked (shouldn't happen
        # since matched_tags is non-empty here, but defensive).
        tag_label = matched_tag if matched_tag is not None else ", ".join(sorted(precedent.matched_tags))
        clauses.append(f"tag: {tag_label}")
    if precedent.matched_rivals:
        rivals = ", ".join(sorted(precedent.matched_rivals))
        clauses.append(f"active rivalry: {rivals}")
    return "; ".join(clauses)


def _to_result(precedent: Precedent) -> RecallResult:
    """Project a scored :class:`Precedent` to the locked :class:`RecallResult`."""
    entry = precedent.entry
    matched_tag = _pick_matched_tag(entry, precedent.matched_tags)
    return RecallResult(
        cite_id=entry.id,
        actor_ref=_owner_of(entry.id),
        week=entry.week,
        event_summary=entry.summary,
        matched_tag=matched_tag,
        relevance_reason=_relevance_reason(precedent, matched_tag),
    )


def recall(why: WhyRecord, world: WorldState, k: int) -> list[RecallResult]:
    """Rank canned precedent against the match and return the top ``k`` results.

    Returns the locked :class:`RecallResult` contract — six named fields the
    renderer and copy templates can bind by name. ``k`` must be non-negative;
    ``k == 0`` returns an empty list. The function is pure: identical ``why``
    + ``world`` always yields the identical ordered list (Python's ``sorted``
    is stable; ties fall back to save order). There is no RNG, no model call,
    no I/O, no clock.
    """
    if k < 0:
        raise ValueError("k must be non-negative")
    if k == 0:
        return []
    return [_to_result(precedent) for precedent in score(why, world)[:k]]
