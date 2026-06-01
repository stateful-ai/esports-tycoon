"""The slice runner's input/output contracts.

The week-6 slice has a deliberately small decision surface, locked by the founder
(see ``scope-m0.md``): **one multiple-choice decision plus two open-text moments,
each capped at 120 characters.** This module pins that surface as plain, immutable
dataclasses so the headless engine, the recap writers, and the Flask web app all
share one contract and none of them needs the others to interpret a decision.

* :class:`SliceConfig` — the fixed week-6 fixture (opponent, map, seed, stance).
  Not a player choice in M0: the schedule is fixed and the captain calls the
  default. It is config so a run can be reproduced or re-pointed deterministically.
* :class:`SliceDecisions` — the player's M0 inputs: the practice-block focus
  (the MC), the two open-text lines (a private pre-match team talk and a public
  post-match Chirper post), and optional M0.2 training effects. Both open-text
  fields are normalised to a single line and validated against the 120-char cap
  at construction.
* :class:`FeedPost` / :class:`SliceResult` — the engine's output, everything the
  recap writers and the web views render, with no behaviour of its own.

Nothing here imports the resolver, the content adapter, or Flask; this module is
the shared vocabulary they are all written against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional, get_args

from esports_tycoon.schema import (
    DecisionEffect,
    Decisions,
    GeneratedContent,
    PracticeFocus,
    TacticalStance,
    WhyRecord,
)

__all__ = [
    "OPEN_TEXT_MAX",
    "PRACTICE_CHOICES",
    "TRAINING_DRILLS",
    "ANALYST_READS",
    "normalize_open_text",
    "training_decision_for_drill",
    "SliceConfig",
    "SliceDecisions",
    "FeedLocalOutcome",
    "FeedPost",
    "RelationshipFalloutKind",
    "RelationshipFallout",
    "TrainingConsequenceKind",
    "Week7SourceBranch",
    "TrainingConsequence",
    "AnalystRead",
    "ReviewRoomTrust",
    "FollowupScrim",
    "Week7Setup",
    "SliceResult",
]

#: The founder-locked guardrail on every open-text moment (``scope-m0.md``): a
#: bounded surface that still feels "magical" and stays cheap to keep in tone.
OPEN_TEXT_MAX = 120

#: The MC decision: what the practice block drills, as ``(value, label, blurb)``.
#: ``value`` is a :data:`~esports_tycoon.schema.PracticeFocus` the resolver acts
#: on; the label/blurb are the human-facing copy the web form renders. Order is
#: fixed (it is the order the radio options appear in, and is part of the UI's
#: determinism). ``defaults`` leads: it is the captain's disciplined default and
#: the safe must-win call.
PRACTICE_CHOICES: tuple[tuple[PracticeFocus, str, str], ...] = (
    ("defaults", "Defaults & structure", "Run the disciplined default until it is muscle memory. Steadies the caller and the controller."),
    ("aim", "Aim & mechanics", "Hours on the range. Sharpens the duelist's raw fragging."),
    ("comms", "Comms & coordination", "Clean up the callouts. Lifts the caller and the initiator."),
    ("anti_strat", "Anti-strat & site holds", "Study the opponent's tendencies. Lifts the sentinel and the controller."),
    ("rest", "Rest & reset", "No drills. Settle the nerves after a two-loss skid."),
)

_PRACTICE_VALUES: frozenset[str] = frozenset(get_args(PracticeFocus))
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class TrainingDrill:
    """One player-facing focused rep on the practice page.

    A drill is intentionally just a typed, budgeted wrapper around the
    ``DecisionEffect`` foundation. The web app can offer these as radio choices
    without learning resolver weights, and headless callers can still build their
    own richer effect tables directly.
    """

    value: str
    player_id: Optional[str]
    skill: str
    delta: int
    training_points: int
    label: str
    blurb: str
    effect_source: str = "training"


# The first playable TrainingDecision surface: spend one focused four-point rep
# on a starter, or keep the old broad practice-only behavior. Labels are static
# because the canonical week-6 cast is locked; display helpers still resolve
# player ids for artifact copy.
TRAINING_DRILLS: tuple[TrainingDrill, ...] = (
    TrainingDrill(
        "none",
        None,
        "",
        0,
        0,
        "No focused rep",
        "Keep the block broad and let the practice focus carry the week.",
    ),
    TrainingDrill(
        "rook_defaults",
        "rook",
        "defaults",
        4,
        4,
        "Rook: defaults under pressure",
        "Put the caller through late-round structure reps.",
    ),
    TrainingDrill(
        "vex_aim",
        "vex",
        "aim",
        4,
        4,
        "Vex: entry mechanics",
        "Give the duelist the cleanest first-contact reps.",
    ),
    TrainingDrill(
        "pixie_flash_repair",
        "pixie",
        "coordination",
        4,
        4,
        "Vex/Pixie: flash review",
        "Spend the block re-timing the week-5 flash call. Cleaner trust, no extra Vex aim.",
        "pixie_flash_repair",
    ),
    TrainingDrill(
        "sable_sitework",
        "sable",
        "sitework",
        4,
        4,
        "Sable: site hold reads",
        "Drill the anchor on Apex's late-hit timings.",
    ),
    TrainingDrill(
        "pixie_comms",
        "pixie",
        "comms",
        4,
        4,
        "Pixie: concise comms",
        "Make the initiator's info faster and quieter.",
    ),
    TrainingDrill(
        "coyote_structure",
        "coyote",
        "structure",
        4,
        4,
        "Coyote: controller structure",
        "Rehearse the smoke timings that hold the default together.",
    ),
)

_TRAINING_DRILLS_BY_VALUE = {drill.value: drill for drill in TRAINING_DRILLS}


def training_decision_for_drill(value: str) -> tuple[int, tuple[DecisionEffect, ...]]:
    """Return ``(training_points, decision_effects)`` for a web training drill.

    ``"none"`` preserves the original M0 surface: no focused effect and no
    training budget recorded. Unknown values fail loudly so a stale form cannot
    silently choose the wrong player.
    """
    drill = _TRAINING_DRILLS_BY_VALUE.get(value)
    if drill is None:
        known = ", ".join(sorted(_TRAINING_DRILLS_BY_VALUE))
        raise ValueError(f"unknown training drill {value!r}; choose from {known}")
    if drill.player_id is None:
        return 0, ()
    return drill.training_points, (
        DecisionEffect(
            player=drill.player_id,
            skill=drill.skill,
            delta=drill.delta,
            training_points=drill.training_points,
            source=drill.effect_source,
        ),
    )

# The per-author outcome that drove starter Chirper copy. Duplicated here rather
# than imported from content so this contract module stays adapter-independent.
FeedLocalOutcome = Literal["mvp", "carried", "came_apart", "neutral"]
RelationshipFalloutKind = Literal["flashpoint", "split", "simmer", "repair"]
FeedPostRole = Literal["standard", "relationship_fallout"]
TrainingConsequenceKind = Literal["vex_entry_reps", "pixie_flash_repair"]
Week7SourceBranch = Literal["vex_aim", "pixie_flash_repair"]


def normalize_open_text(value: Optional[str], *, label: str = "open-text input") -> str:
    """Trim, collapse to one line, and enforce the 120-char cap.

    Open text arrives from a web textarea, so it can carry leading/trailing space
    and embedded newlines. Both are collapsed to single spaces — the inputs are
    one-line tone-aligned moments, and keeping them single-line also stops a stray
    newline from breaking the markdown recap or the HTML snapshot. Raises
    ``ValueError`` (caught and shown by the web form) if the cleaned text exceeds
    :data:`OPEN_TEXT_MAX`.
    """
    cleaned = _WHITESPACE_RE.sub(" ", (value or "").strip())
    if len(cleaned) > OPEN_TEXT_MAX:
        raise ValueError(
            f"{label} must be at most {OPEN_TEXT_MAX} characters; got {len(cleaned)}"
        )
    return cleaned


@dataclass(frozen=True)
class SliceConfig:
    """The fixed week-6 fixture and the run's reproducibility knobs.

    ``opponent`` is a rival org id and ``map`` the map being played — the week-6
    fixture, "must-win on Helix." ``seed`` makes the whole slice reproducible
    (same seed + same decisions ⇒ identical match, feed, and recap). ``tactical_
    stance`` is the captain's default call; it is config, not a player decision,
    to keep the surface to exactly MC + 2 open-text.
    """

    opponent: str = "apex_foundry"
    map: str = "Helix"
    seed: int = 6
    tactical_stance: TacticalStance = "default"


@dataclass(frozen=True)
class SliceDecisions:
    """The player's inputs for the week: one MC, two open-text, optional training.

    ``practice_focus`` is the multiple-choice decision (one of
    :data:`PRACTICE_CHOICES`). ``team_talk`` is the private pre-match line to the
    five; ``fallout_post`` is the public post-match Chirper post from the org
    account. Both open-text fields are normalised and 120-char-capped on
    construction, so an over-long or multi-line value never reaches the engine.
    Either may be empty — saying nothing is a valid, in-character choice.
    ``training_points``/``decision_effects`` are the M0.2 foundation: default
    empty for the M0 web flow, but structured so headless callers can spend a
    budget on per-player skill deltas.
    """

    practice_focus: PracticeFocus
    team_talk: str = ""
    fallout_post: str = ""
    training_points: int = 0
    decision_effects: tuple[DecisionEffect, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.practice_focus not in _PRACTICE_VALUES:
            raise ValueError(
                f"unknown practice focus {self.practice_focus!r}; "
                f"choose from {', '.join(sorted(_PRACTICE_VALUES))}"
            )
        # Normalise in place (frozen dataclass: assign via object.__setattr__).
        object.__setattr__(self, "team_talk", normalize_open_text(self.team_talk, label="team talk"))
        object.__setattr__(self, "fallout_post", normalize_open_text(self.fallout_post, label="fallout post"))
        if self.training_points < 0:
            raise ValueError("training_points must be >= 0")
        effects = tuple(
            effect if isinstance(effect, DecisionEffect) else DecisionEffect.model_validate(effect)
            for effect in (self.decision_effects or ())
        )
        spent = sum(effect.training_points for effect in effects)
        if spent > self.training_points:
            raise ValueError(
                f"decision_effects spend {spent} training_points, "
                f"but only {self.training_points} are available"
            )
        object.__setattr__(self, "decision_effects", effects)

    def structured(self, config: SliceConfig) -> Decisions:
        """The resolver's structured :class:`Decisions` for this week.

        Open text never crosses into the resolver — interpreting free text would
        need an LLM, and the LLM is never inside the resolver. Only the MC and the
        fixed fixture do.
        """
        return Decisions(
            opponent=config.opponent,
            map=config.map,
            practice_focus=self.practice_focus,
            tactical_stance=config.tactical_stance,
            training_points=self.training_points,
            decision_effects=list(self.decision_effects),
        )


@dataclass(frozen=True)
class FeedPost:
    """One post in the rendered week-6 Chirper feed.

    A presentation-ready view: the display name and handle to show, the text, and
    the memory ids it is grounded in (resolved to summaries at render time).
    ``grounding_status`` mirrors the content adapter's verdict.
    """

    author_handle: str
    author_name: str
    text: str
    cites: tuple[str, ...] = ()
    grounding_status: str = "ok"
    author_player_id: Optional[str] = None
    local_outcome: Optional[FeedLocalOutcome] = None
    role: FeedPostRole = "standard"


@dataclass(frozen=True)
class RelationshipFallout:
    """One live clash pair made visible by this week's result.

    The canned save already declares seeded clash pairs, and the resolver uses
    them as hidden tilt pressure. This view is the player-facing receipt: which
    authored relationship mattered *this week*, how sharply it flared, and which
    memories ground it.
    """

    a: str
    b: str
    axis: str
    summary: str
    cites: tuple[str, ...] = ()
    kind: RelationshipFalloutKind = "simmer"
    score: int = 0


@dataclass(frozen=True)
class TrainingConsequence:
    """The visible payoff/cost of a focused practice branch.

    This stays deliberately authored and tiny: the current slice only proves
    that one prior Vex/Pixie fracture can constrain the next training choice.
    It is not a generalized morale or relationship simulation.
    """

    kind: TrainingConsequenceKind
    label: str
    summary: str
    benefit: str
    cost: str
    cites: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalystRead:
    """Authored pre-choice scouting read for one focused practice branch."""

    drill_value: str
    benefit: str
    risk: str
    recommendation: str


ANALYST_READS: tuple[AnalystRead, ...] = (
    AnalystRead(
        drill_value="vex_aim",
        benefit="Vex can hard-carry the next scrim.",
        risk="Review trust drops if Pixie is left alone with blame.",
        recommendation="High upside, fragile room.",
    ),
    AnalystRead(
        drill_value="pixie_flash_repair",
        benefit="Pixie stabilizes flashes and mid-round calls.",
        risk="Vex loses a chance to sharpen the carry angle.",
        recommendation="Lower ceiling, stronger room.",
    ),
)


@dataclass(frozen=True)
class ReviewRoomTrust:
    """One run-local scarce resource changed by the repair-vs-reps fork."""

    start: int
    delta: int
    final: int
    reason: str


@dataclass(frozen=True)
class FollowupScrim:
    """A second deterministic receipt showing how review trust plays later."""

    label: str
    summary: str
    benefit: str
    cost: str


@dataclass(frozen=True)
class Week7Setup:
    """The future-facing hook exported from the current deterministic run."""

    source_branch: Week7SourceBranch
    fallout_state: str
    review_room_trust: ReviewRoomTrust
    followup_scrim: FollowupScrim
    hook_id: str
    hook_title: str
    hook_prompt: str
    recommended_focus: str


@dataclass(frozen=True)
class SliceResult:
    """Everything one slice produced: the inputs, the match, and the feed.

    Self-contained so the recap writers and the web views render purely from it
    (plus the :class:`~esports_tycoon.schema.WorldState` for resolving cites). It
    carries no behaviour and is fully determined by the world + config + decisions,
    which is what makes the recap byte-identical on re-run with the same seed.
    """

    slice_id: str
    config: SliceConfig
    decisions: SliceDecisions
    why: WhyRecord
    narration: GeneratedContent
    halftime: GeneratedContent
    halftime_scoreline: tuple[int, int]
    feed: tuple[FeedPost, ...]
    grounded_ok: int
    grounded_total: int
    relationship_fallout: tuple[RelationshipFallout, ...] = ()
    training_consequence: Optional[TrainingConsequence] = None
    week7_setup: Optional[Week7Setup] = None
    #: Which content backend produced this slice's prose — the value of
    #: ``ContentConfig.backend`` (``templated`` | ``vllm``). Recorded so the recap
    #: can label the run honestly (a ``vllm`` slice must not claim "zero-API"). A
    #: plain ``str`` to keep this module free of any ``content`` import, per the
    #: module's stated independence; it mirrors ``ContentConfig.backend`` verbatim.
    content_backend: str = "templated"
    cited_memories: tuple[str, ...] = field(default_factory=tuple)

    @property
    def scoreline(self) -> tuple[int, int]:
        """The final ``(overcast, opponent)`` series scoreline."""
        return self.why.scoreline

    @property
    def won(self) -> bool:
        """Whether Overcast won — the week-6 must-win verdict."""
        ovc, opp = self.why.scoreline
        return ovc > opp

    @property
    def grounding_rate(self) -> float:
        """Fraction of grounded content pieces whose cites held (``1.0`` templated)."""
        return self.grounded_ok / self.grounded_total if self.grounded_total else 1.0
