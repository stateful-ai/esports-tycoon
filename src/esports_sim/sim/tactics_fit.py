"""Roster fit for the coaching dials — the single source of truth shared by
the match engine's ``_execution_mod`` and the web serializer's tactics view,
so the "duel edge" the UI previews is exactly what the engine applies.

Neutral-safety (ADR-007): everything here is a per-dial *edge at full crank*
(deviation 1.0). The caller multiplies it by ``abs(dial - 50) / 50``, which is
zero at neutral — so a neutral team gets exactly ``0.0`` and the golden/balance
gates never see this code.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping

from esports_sim.schemas.team import TeamTactics
from esports_sim.sim import constants as C

# Each attribute-fit dial → the roster attributes that make it work. eco_greed
# is absent on purpose: it is a pure economy lever with no roster-attribute fit.
DIAL_FIT_ATTRS: dict[str, tuple[str, ...]] = {
    "aggression": ("aim_reactivity", "aim_precision"),
    "pace": ("aim_reactivity", "movement"),
    "util_discipline": ("game_sense", "utility_usage"),
    "map_control": ("game_sense", "comms_quality"),
}
# The HIGH side of these two is the coordination-heavy read, so the engine
# additionally gates it on team chemistry (see ``_execution_mod``).
CHEM_GATED = frozenset({"map_control", "util_discipline"})

# Economy and site choice have their own outcome channels. These are the four
# identity dials where a manager can deliberately lean against an opponent.
COUNTER_DIALS = ("aggression", "pace", "util_discipline", "map_control")


def player_fit(scores: Iterable[float]) -> float:
    """One player's fit on a dial: the mean of that dial's attributes."""
    vals = list(scores)
    return sum(vals) / len(vals) if vals else 50.0


def fit_edge(player_fits: Iterable[float]) -> float:
    """Per-dial execution edge at a fully-cranked dial, BEFORE chemistry.

    Scored PER PLAYER, then centred on ``EXEC_FIT_BASELINE`` — but a player
    *below* the baseline is amplified by ``EXEC_MISFIT_PENALTY`` before summing,
    so a team-mate who can't run the system drags harder than an equally-good
    fit lifts. That is what stops "crank every dial" from being free: a couple
    of stars can no longer average away the players who don't fit, and a
    high-variance roster nets negative at an extreme. At ``EXEC_MISFIT_PENALTY
    == 1`` this is exactly the old roster-average behaviour.
    """
    fits = list(player_fits)
    if not fits:
        return 0.0
    total = 0.0
    for f in fits:
        contrib = f - C.EXEC_FIT_BASELINE
        if contrib < 0.0:
            contrib *= C.EXEC_MISFIT_PENALTY
        total += contrib
    return (total / len(fits)) / C.EXEC_FIT_DIV


def chem_edge(chemistry: float) -> float:
    """Chemistry's per-dial contribution at a fully-cranked HIGH side of a
    coordination-heavy dial (map control / discipline). Above the baseline it
    sharpens the system, below it makes it misfire. The engine multiplies this
    by each gated dial's above-neutral deviation, so it too is 0 at neutral."""
    return (chemistry - C.EXEC_CHEM_BASELINE) / C.EXEC_CHEM_DIV


def counter_strat_edge(
    overrides: Mapping[str, float | None],
    opponent_tactics: TeamTactics | Mapping[str, float],
) -> float:
    """Signed duel edge from one-match overrides versus an opponent identity.

    Only explicitly overridden dials count: leaving a box unchecked means
    "play our book", not "we prepared this counter". Opposite poles earn an
    edge, matching poles incur the same-sized malus, and either side at neutral
    contributes exactly zero. Averaging over all four dials makes a full,
    coherent read more valuable than guessing one slider.

    ``opponent_tactics`` may be a TeamTactics model or a public-meta mapping;
    keeping this calculation here lets the campaign resolver and serializers
    share one source of truth without mirroring the formula in JavaScript.
    """
    total = 0.0
    for dial in COUNTER_DIALS:
        value = overrides.get(dial)
        if value is None:
            continue
        opponent_value = (
            opponent_tactics.get(dial, 50.0)
            if isinstance(opponent_tactics, Mapping)
            else getattr(opponent_tactics, dial)
        )
        own_dev = (float(value) - 50.0) / 50.0
        opponent_dev = (float(opponent_value) - 50.0) / 50.0
        total -= own_dev * opponent_dev
    edge = total / len(COUNTER_DIALS) * C.COUNTER_STRAT_SPAN
    return max(-C.COUNTER_STRAT_CAP, min(C.COUNTER_STRAT_CAP, edge))
