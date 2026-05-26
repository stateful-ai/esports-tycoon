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
* **active rivalry** — a flat ``+1`` if any actor in the beat has an
  authored ``kind="rival"`` :class:`~esports_tycoon.schema.Relationship`
  whose target appears in the memory entry (in its ``actors`` or its
  ``recall_tags``).

Sort is by ``(-actor_score, -tag_score, -rivalry_score)`` and Python's
``sorted`` is stable, so equal-scored entries fall back to save order
(``world.players`` order, then each player's ``memory_log`` order). This is
what makes the function fully deterministic: every key is a pure function of
the inputs, ties are broken by save order, and **identical inputs always
yield the identical ordered list** — no ``random.Random``, no LLM, no clock,
no entropy of any kind. The function takes no seed and accepts no client.

The templated narrator (:mod:`esports_tycoon.content.templated`) binds against
this: it picks the recalled precedent for the beat it's narrating and stamps
its cite ID into the generated content's ``cites``, which is what the recap's
"What the room remembered" section quotes back. So a week-6 choke surfaces the
week-5 scrim choke (or the unresolved week-2 override that lit it), and that
precedent rides into the rendered output by ID rather than by RNG.
"""

from __future__ import annotations

from dataclasses import dataclass

from esports_tycoon.schema import MemoryEntry, WhyRecord, WorldState

__all__ = ["recall", "Precedent"]


@dataclass(frozen=True)
class Precedent:
    """A canned memory plus the per-signal scores it earned against a match.

    Exposed (and exported) so callers can introspect *why* a precedent rose to
    the top — useful for explanations in the recap and for tests that pin the
    scoring contract rather than the final ordering.
    """

    entry: MemoryEntry
    actor_score: int
    tag_score: int
    rivalry_score: int


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
    those names back in — by including them as an actor or marking ``rivalry``
    in its recall tags — earns the rivalry bonus.
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

    Exposed so callers (tests, the recap) can inspect the ranking without
    paying the ``[:k]`` slice. Same ordering and same determinism contract as
    :func:`recall`.
    """
    actors = _why_actors(why)
    tags = _target_tags(why)
    rivals = _active_rivals(world, actors)

    candidates: list[Precedent] = []
    for player in world.players:
        for entry in player.memory_log:
            entry_actors = set(entry.actors)
            entry_recall_tags = set(entry.recall_tags)
            actor_score = len(actors & entry_actors)
            tag_score = len(tags & entry_recall_tags)
            rivalry_score = 1 if rivals & (entry_actors | entry_recall_tags) else 0
            if actor_score == 0 and tag_score == 0 and rivalry_score == 0:
                continue
            candidates.append(
                Precedent(
                    entry=entry,
                    actor_score=actor_score,
                    tag_score=tag_score,
                    rivalry_score=rivalry_score,
                )
            )
    # Stable sort by descending score components: equal-scored entries fall
    # back to save order, which is the order they were appended above.
    candidates.sort(
        key=lambda p: (-p.actor_score, -p.tag_score, -p.rivalry_score)
    )
    return candidates


def recall(why: WhyRecord, world: WorldState, k: int) -> list[MemoryEntry]:
    """Rank canned precedent against the match and return the top ``k``.

    ``k`` must be non-negative; ``k == 0`` returns an empty list. The function
    is pure: identical ``why`` + ``world`` always yields the identical ordered
    list (Python's ``sorted`` is stable; ties fall back to save order). There
    is no RNG, no model call, no I/O, no clock.
    """
    if k < 0:
        raise ValueError("k must be non-negative")
    if k == 0:
        return []
    return [precedent.entry for precedent in score(why, world)[:k]]
