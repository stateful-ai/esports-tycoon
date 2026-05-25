"""The slice runner's input/output contracts.

The week-6 slice has a deliberately small decision surface, locked by the founder
(see ``scope-m0.md``): **one multiple-choice decision plus two open-text moments,
each capped at 120 characters.** This module pins that surface as plain, immutable
dataclasses so the headless engine, the recap writers, and the Flask web app all
share one contract and none of them needs the others to interpret a decision.

* :class:`SliceConfig` — the fixed week-6 fixture (opponent, map, seed, stance).
  Not a player choice in M0: the schedule is fixed and the captain calls the
  default. It is config so a run can be reproduced or re-pointed deterministically.
* :class:`SliceDecisions` — the player's three inputs: the practice-block focus
  (the MC) and the two open-text lines (a private pre-match team talk and a public
  post-match Chirper post). Both open-text fields are normalised to a single line
  and validated against the 120-char cap at construction.
* :class:`FeedPost` / :class:`SliceResult` — the engine's output, everything the
  recap writers and the web views render, with no behaviour of its own.

Nothing here imports the resolver, the content adapter, or Flask; this module is
the shared vocabulary they are all written against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, get_args

from esports_tycoon.schema import (
    Decisions,
    GeneratedContent,
    PracticeFocus,
    TacticalStance,
    WhyRecord,
)

__all__ = [
    "OPEN_TEXT_MAX",
    "PRACTICE_CHOICES",
    "normalize_open_text",
    "SliceConfig",
    "SliceDecisions",
    "FeedPost",
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
    """The player's three inputs for the week: one MC, two open-text.

    ``practice_focus`` is the multiple-choice decision (one of
    :data:`PRACTICE_CHOICES`). ``team_talk`` is the private pre-match line to the
    five; ``fallout_post`` is the public post-match Chirper post from the org
    account. Both open-text fields are normalised and 120-char-capped on
    construction, so an over-long or multi-line value never reaches the engine.
    Either may be empty — saying nothing is a valid, in-character choice.
    """

    practice_focus: PracticeFocus
    team_talk: str = ""
    fallout_post: str = ""

    def __post_init__(self) -> None:
        if self.practice_focus not in _PRACTICE_VALUES:
            raise ValueError(
                f"unknown practice focus {self.practice_focus!r}; "
                f"choose from {', '.join(sorted(_PRACTICE_VALUES))}"
            )
        # Normalise in place (frozen dataclass: assign via object.__setattr__).
        object.__setattr__(self, "team_talk", normalize_open_text(self.team_talk, label="team talk"))
        object.__setattr__(self, "fallout_post", normalize_open_text(self.fallout_post, label="fallout post"))

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
