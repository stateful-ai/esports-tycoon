"""The input contract for the content adapter: ``GenerationContext``.

``generate_content(kind, ctx)`` takes one of these. It is the content layer's
twin of :class:`~esports_tycoon.schema.Decisions` (the resolver's input): a small,
immutable bundle of *already-validated* domain objects plus the few presentation
knobs a renderer needs (whose voice, the half-time situation). It deliberately
carries no behaviour and lives in its own module so both backends and the adapter
can import it without a cycle.

A context holds a superset of what any one ``kind`` needs; each renderer asserts
the fields it requires are present and raises a clear ``ValueError`` otherwise
(see :func:`require`). That keeps the single ``generate_content`` signature while
letting the three content kinds have genuinely different inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from esports_tycoon.schema import (
    Decisions,
    Player,
    Role,
    TacticalStance,
    WhyRecord,
    WorldState,
)

LocalOutcome = Literal["mvp", "carried", "came_apart", "neutral"]

__all__ = ["GenerationContext", "LocalOutcome", "derive_local_outcome"]


def derive_local_outcome(why: WhyRecord, author: str) -> LocalOutcome:
    """Return the author's personal match outcome from a resolved match."""
    if author == why.mvp:
        return "mvp"
    if author in why.who_tilted:
        return "came_apart"
    if author in why.who_carried:
        return "carried"
    return "neutral"


@dataclass(frozen=True)
class GenerationContext:
    """Everything a content renderer might read, as one immutable bundle.

    ``world`` is always required. The rest are populated per kind:

    * ``narration`` needs ``why`` and ``decisions`` (the resolved match plus the
      fixture it was played on — opponent and map).
    * ``chirper_post`` needs ``why`` and ``author`` (whose reaction this is);
      ``local_outcome`` can override the renderer's derived per-author read
      (``mvp`` / ``carried`` / ``came_apart`` / ``neutral``) when a caller has
      already computed it.
    * ``halftime_ack`` needs ``halftime_scoreline`` and ``second_half_stance``;
      ``author`` defaults to the fielded in-game leader.

    The objects here are passed verbatim from the loader/resolver — a context is a
    view over them, never a copy, and is never mutated.
    """

    world: WorldState
    why: Optional[WhyRecord] = None
    decisions: Optional[Decisions] = None
    author: Optional[str] = None
    local_outcome: Optional[LocalOutcome] = None
    halftime_scoreline: Optional[tuple[int, int]] = None
    second_half_stance: Optional[TacticalStance] = None

    def require(self, kind: str, **fields: object) -> None:
        """Assert that every named field is set, or raise a pointed ``ValueError``.

        ``fields`` maps a human field name to its value; any whose value is
        ``None`` names a missing requirement for ``kind``.
        """
        missing = [name for name, value in fields.items() if value is None]
        if missing:
            raise ValueError(
                f"{kind} content requires {', '.join(sorted(missing))} in the "
                f"GenerationContext"
            )

    def player(self, player_id: str) -> Optional[Player]:
        """The starter with this id, or ``None`` if it is an external voice."""
        for candidate in self.world.players:
            if candidate.id == player_id:
                return candidate
        return None

    def igl(self) -> Optional[Player]:
        """The team's in-game leader, who owns the half-time call by default."""
        for candidate in self.world.players:
            if candidate.role is Role.IGL:
                return candidate
        return None
