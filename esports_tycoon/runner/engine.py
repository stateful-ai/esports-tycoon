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
from esports_tycoon.content.context import derive_local_outcome
from esports_tycoon.content.config import ContentConfig
from esports_tycoon.runner.model import (
    FeedLocalOutcome,
    FeedPost,
    FollowupScrim,
    RelationshipFallout,
    ReviewRoomTrust,
    SliceConfig,
    SliceDecisions,
    SliceResult,
    TrainingConsequence,
    Week7Setup,
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
_MAX_RELATIONSHIP_FALLOUT = 1
_REVIEW_ROOM_TRUST_START = 2


def slice_id(world: WorldState, config: SliceConfig, decisions: SliceDecisions) -> str:
    """A short, stable id for this run, derived from its full input.

    Content-addressed on purpose: identical inputs ⇒ identical id ⇒ the same
    ``runs/<slice_id>/`` folder re-written with identical bytes, which is exactly
    the "identical recap on re-run with the same seed" contract. A different
    open-text line, opponent, or seed yields a different id and its own folder.
    """
    payload_fields = {
        "save": world.save.id,
        "week": world.save.season.current_week,
        "seed": config.seed,
        "opponent": config.opponent,
        "map": config.map,
        "stance": config.tactical_stance,
        "practice": decisions.practice_focus,
        "team_talk": decisions.team_talk,
        "fallout_post": decisions.fallout_post,
    }
    if decisions.training_points or decisions.decision_effects:
        payload_fields["training_points"] = decisions.training_points
        payload_fields["decision_effects"] = [
            effect.model_dump(mode="json") for effect in decisions.decision_effects
        ]
    payload = json.dumps(
        payload_fields,
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


def _player_by_id(world: WorldState, player_id: str):
    return next((player for player in world.players if player.id == player_id), None)


def _effect_sources(decisions: SliceDecisions) -> frozenset[str]:
    return frozenset(effect.source for effect in decisions.decision_effects)


def _has_vex_entry_reps(decisions: SliceDecisions) -> bool:
    return any(
        effect.player == "vex" and effect.skill == "aim" and effect.delta > 0
        for effect in decisions.decision_effects
    )


def _has_pixie_flash_repair(decisions: SliceDecisions) -> bool:
    return "pixie_flash_repair" in _effect_sources(decisions)


def _vex_pixie_clash(world: WorldState):
    return next(
        (
            clash for clash in world.clash_pairs
            if not clash.cross_team and {clash.a, clash.b} == {"vex", "pixie"}
        ),
        None,
    )


def _relationship_fallout_author(why: WhyRecord, fallout: RelationshipFallout) -> str:
    """Pick the starter whose post best explains the relationship split."""
    if fallout.kind == "repair" and {fallout.a, fallout.b} == {"vex", "pixie"}:
        return "pixie"
    carried = set(why.who_carried)
    tilted = set(why.who_tilted)
    if fallout.a == why.mvp or fallout.a in carried:
        return fallout.a
    if fallout.b == why.mvp or fallout.b in carried:
        return fallout.b
    if fallout.a in tilted and fallout.b not in tilted:
        return fallout.a
    if fallout.b in tilted and fallout.a not in tilted:
        return fallout.b
    return fallout.a


def _relationship_fallout_text(
    world: WorldState,
    why: WhyRecord,
    fallout: RelationshipFallout,
    author: str,
) -> str:
    """Authored social-feed copy for the first fallout receipt.

    The generic fallback stays deterministic, but the Vex/Pixie split gets a
    hand-authored line because it is the canonical smoke path for this slice.
    """
    other = fallout.b if author == fallout.a else fallout.a
    if {fallout.a, fallout.b} == {"vex", "pixie"} and fallout.kind == "split":
        if author == "vex":
            return "entry reps helped. still not peeking through our own flash again."
        return "reps showed up. flash review is still on me."
    if {fallout.a, fallout.b} == {"vex", "pixie"} and fallout.kind == "repair":
        if author == "pixie":
            return "flash review helped. less apology, more timing."
        return "flash was clean. keep it like that."
    author_name = _first_name(_player_by_id(world, author).name) if _player_by_id(world, author) else author
    other_name = _first_name(_player_by_id(world, other).name) if _player_by_id(world, other) else other
    if fallout.kind == "flashpoint":
        return f"{author_name}/{other_name} tape is loud. we all heard it."
    if fallout.kind == "split":
        return f"{author_name}/{other_name} tape split the room. fair."
    return f"{author_name}/{other_name} tape stays in the room."


def _relationship_fallout_post(
    world: WorldState,
    why: WhyRecord,
    fallout: RelationshipFallout,
) -> Optional[FeedPost]:
    author = _relationship_fallout_author(why, fallout)
    player = _player_by_id(world, author)
    if player is None:
        return None
    local_outcome: FeedLocalOutcome = derive_local_outcome(why, author)
    return FeedPost(
        author_handle=player.handle,
        author_name=_first_name(player.name),
        text=_relationship_fallout_text(world, why, fallout, author),
        cites=fallout.cites,
        grounding_status="ok",
        author_player_id=author,
        local_outcome=local_outcome,
        role="relationship_fallout",
    )


def _build_feed(
    world: WorldState,
    config: SliceConfig,
    decisions: SliceDecisions,
    why: WhyRecord,
    content_config: ContentConfig,
    relationship_fallout: tuple[RelationshipFallout, ...] = (),
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
        local_outcome = derive_local_outcome(why, player.id)
        gc = generate_content(
            "chirper_post",
            GenerationContext(
                world=world, why=why, author=player.id, local_outcome=local_outcome
            ),
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
                author_player_id=player.id,
                local_outcome=local_outcome,
            )
        )

    if relationship_fallout:
        fallout_post = _relationship_fallout_post(world, why, relationship_fallout[0])
        if fallout_post is not None:
            posts.append(fallout_post)

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


def _relationship_fallout(
    world: WorldState,
    decisions: SliceDecisions,
    why: WhyRecord,
) -> tuple[RelationshipFallout, ...]:
    """The highest-pressure authored clash made visible by this week's result.

    The resolver already uses live intra-team clashes as hidden tilt pressure.
    This projection turns that invisible pressure into a screenshotable receipt:
    the seeded pair whose morale/local-outcome contrast most explains what the
    room will argue about after the match.
    """
    if not decisions.decision_effects:
        return ()

    if _has_pixie_flash_repair(decisions):
        clash = _vex_pixie_clash(world)
        if clash is not None:
            return (
                RelationshipFallout(
                    a=clash.a,
                    b=clash.b,
                    axis="working review",
                    summary=(
                        "Pixie and Vex owned the week-5 flash review; the next entry "
                        "call had one timing instead of two."
                    ),
                    cites=tuple(clash.seeded_by),
                    kind="repair",
                    score=12,
                ),
            )

    morale = why.morale_deltas
    tilted = set(why.who_tilted)
    carried = set(why.who_carried)
    trained = {effect.player for effect in decisions.decision_effects}
    candidates: list[tuple[int, int, RelationshipFallout]] = []

    for order, clash in enumerate(world.clash_pairs):
        if clash.cross_team or clash.a not in morale or clash.b not in morale:
            continue
        pair = {clash.a, clash.b}
        a_bad = clash.a in tilted or morale[clash.a] <= -4
        b_bad = clash.b in tilted or morale[clash.b] <= -4
        a_good = clash.a == why.mvp or clash.a in carried or morale[clash.a] > 0
        b_good = clash.b == why.mvp or clash.b in carried or morale[clash.b] > 0

        score = max(0, -morale[clash.a]) + max(0, -morale[clash.b])
        score += 4 if clash.a in tilted else 0
        score += 4 if clash.b in tilted else 0
        if (a_good and b_bad) or (b_good and a_bad):
            score += 3
        if trained & pair:
            score += 2
        if score <= 0:
            continue

        if a_bad and b_bad:
            kind = "flashpoint"
        elif (a_good and b_bad) or (b_good and a_bad):
            kind = "split"
        else:
            kind = "simmer"
        candidates.append(
            (
                score,
                order,
                RelationshipFallout(
                    a=clash.a,
                    b=clash.b,
                    axis=clash.axis,
                    summary=clash.summary,
                    cites=tuple(clash.seeded_by),
                    kind=kind,
                    score=score,
                ),
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return tuple(item for _, _, item in candidates[:_MAX_RELATIONSHIP_FALLOUT])


def _training_consequence(
    world: WorldState,
    decisions: SliceDecisions,
    relationship_fallout: tuple[RelationshipFallout, ...],
) -> Optional[TrainingConsequence]:
    """Authored payoff/cost copy for the fallout-aware focused-rep fork."""
    clash = _vex_pixie_clash(world)
    cites = tuple(clash.seeded_by) if clash is not None else ()
    if _has_pixie_flash_repair(decisions):
        return TrainingConsequence(
            kind="pixie_flash_repair",
            label="Flash review",
            summary="No highlight reel, but the entry call and flash finally matched.",
            benefit="Pixie steadied the timing and the Vex/Pixie review cooled down.",
            cost="Vex did not get another raw aim bump.",
            cites=cites,
        )
    if _has_vex_entry_reps(decisions) and any(
        {fallout.a, fallout.b} == {"vex", "pixie"}
        and fallout.kind in {"split", "flashpoint"}
        for fallout in relationship_fallout
    ):
        return TrainingConsequence(
            kind="vex_entry_reps",
            label="Entry reps",
            summary="Vex looked sharper, but the room still played like two calls at once.",
            benefit="Vex gained more first-contact power.",
            cost="The unresolved Vex/Pixie flash timing stayed public.",
            cites=cites,
        )
    return None


def _fallout_state(relationship_fallout: tuple[RelationshipFallout, ...]) -> str:
    if not relationship_fallout:
        return "none"
    fallout = relationship_fallout[0]
    if {fallout.a, fallout.b} == {"vex", "pixie"}:
        return fallout.axis
    return f"{fallout.a}:{fallout.b}:{fallout.axis}"


def _week7_setup(
    training_consequence: Optional[TrainingConsequence],
    relationship_fallout: tuple[RelationshipFallout, ...],
) -> Optional[Week7Setup]:
    """Run-local setup state that makes this week's fork matter next week."""
    fallout_state = _fallout_state(relationship_fallout)
    if training_consequence is None:
        return None
    if training_consequence.kind == "vex_entry_reps":
        trust = ReviewRoomTrust(
            start=_REVIEW_ROOM_TRUST_START,
            delta=-2,
            final=_REVIEW_ROOM_TRUST_START - 2,
            reason="Vex's entry block worked, but Pixie absorbed the review blame alone.",
        )
        return Week7Setup(
            source_branch="vex_aim",
            fallout_state=fallout_state,
            review_room_trust=trust,
            followup_scrim=FollowupScrim(
                label="Late retake crack",
                summary=(
                    "Vex cracked the opener in the follow-up scrim, then the late "
                    "retake stalled when the flash call split again."
                ),
                benefit="First-duel pressure stayed elite.",
                cost="Low review-room trust made the trade call late.",
            ),
            hook_id="vex_pixie_review_room_heat",
            hook_title="Review room heat",
            hook_prompt="Vex has the highlight reel, but the room knows Pixie paid for it.",
            recommended_focus="contain_fallout",
        )
    if training_consequence.kind == "pixie_flash_repair":
        trust = ReviewRoomTrust(
            start=_REVIEW_ROOM_TRUST_START,
            delta=2,
            final=_REVIEW_ROOM_TRUST_START + 2,
            reason="Pixie and Vex spent the review together, so the room trusted the next call.",
        )
        return Week7Setup(
            source_branch="pixie_flash_repair",
            fallout_state=fallout_state,
            review_room_trust=trust,
            followup_scrim=FollowupScrim(
                label="Clean second contact",
                summary=(
                    "Pixie's flash landed on the follow-up retake timing, and the "
                    "room converted the second contact."
                ),
                benefit="High review-room trust made the execute cleaner.",
                cost="No extra Vex aim block left the opener less explosive.",
            ),
            hook_id="pixie_stability_low_clip_value",
            hook_title="Stable, not loud",
            hook_prompt="Pixie steadied the map, but sponsors are asking who sells the next clip.",
            recommended_focus="prove_ceiling",
        )
    return None


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

    relationship_fallout = _relationship_fallout(world, decisions, why)
    training_consequence = _training_consequence(world, decisions, relationship_fallout)
    week7_setup = _week7_setup(training_consequence, relationship_fallout)
    feed, feed_grounded = _build_feed(
        world,
        config,
        decisions,
        why,
        content_config,
        relationship_fallout,
        client,
    )

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
        relationship_fallout=relationship_fallout,
        training_consequence=training_consequence,
        week7_setup=week7_setup,
        grounded_ok=grounded_ok,
        grounded_total=len(grounded_pieces),
        content_backend=content_config.backend,
        cited_memories=cited_memories,
    )
