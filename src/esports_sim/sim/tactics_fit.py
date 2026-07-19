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
from typing import Any, Literal

from esports_sim.schemas.team import TeamTactics
from esports_sim.sim import constants as C

# Each pole has distinct execution demands. The edge compares a roster's fit
# for the selected system against its fit for the opposite system. eco_greed
# is absent on purpose: it is a pure economy lever with no roster fit.
Pole = Literal["low", "high"]
DIAL_POLE_FIT_ATTRS: dict[str, dict[Pole, tuple[str, ...]]] = {
    "aggression": {
        "low": ("positioning", "game_sense", "composure"),
        "high": ("aim_reactivity", "aim_precision", "movement"),
    },
    "pace": {
        "low": ("game_sense", "utility_usage", "comms_quality"),
        "high": ("movement", "aim_reactivity", "comms_quality"),
    },
    "util_discipline": {
        "low": ("utility_usage", "movement", "aim_reactivity"),
        "high": ("game_sense", "utility_usage", "comms_quality"),
    },
    "map_control": {
        "low": ("aim_precision", "aim_reactivity", "utility_usage"),
        "high": ("game_sense", "positioning", "comms_quality"),
    },
}
DIAL_POLE_PLAYSTYLES: dict[str, dict[Pole, frozenset[str]]] = {
    "aggression": {
        "low": frozenset({"anchor", "support", "igl"}),
        "high": frozenset({"entry", "awper"}),
    },
    "pace": {
        "low": frozenset({"igl", "support", "lurker"}),
        "high": frozenset({"entry", "awper"}),
    },
    "util_discipline": {
        "low": frozenset({"entry", "support"}),
        "high": frozenset({"igl", "anchor", "support"}),
    },
    "map_control": {
        "low": frozenset({"entry", "support"}),
        "high": frozenset({"lurker", "igl", "anchor"}),
    },
}
# Compatibility/catalog view: every attribute relevant to either pole. Engine
# and serializer calculations use DIAL_POLE_FIT_ATTRS / dial_pole_edge.
DIAL_FIT_ATTRS: dict[str, tuple[str, ...]] = {
    dial: tuple(dict.fromkeys(poles["low"] + poles["high"]))
    for dial, poles in DIAL_POLE_FIT_ATTRS.items()
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


def dial_pole_player_fits(
    roster: Iterable[Any], dial: str, pole: Pole
) -> list[float]:
    """Per-player raw fit scores for one side of a tactics dial."""
    attrs = DIAL_POLE_FIT_ATTRS[dial][pole]
    aligned = DIAL_POLE_PLAYSTYLES[dial][pole]
    return [
        player_fit(player.attr(attr) for attr in attrs)
        + (
            C.EXEC_PLAYSTYLE_FIT_BONUS
            if str(player.playstyle) in aligned
            else 0.0
        )
        for player in roster
    ]


def dial_pole_edge(roster: Iterable[Any], dial: str, pole: Pole) -> float:
    """Roster execution edge for one pole, before chemistry.

    The primary signal is comparative: how much better each player fits this
    pole than the opposite system. That prevents raw overall quality from
    making both directions of every dial free upside. A player below the
    absolute execution baseline also adds a readiness tax, preserving the
    rule that a system can fail because one member cannot run it.
    """
    players = list(roster)
    if not players:
        return 0.0
    opposite: Pole = "high" if pole == "low" else "low"
    preferred = dial_pole_player_fits(players, dial, pole)
    alternatives = dial_pole_player_fits(players, dial, opposite)
    total = 0.0
    for fit, alternative in zip(preferred, alternatives):
        readiness_tax = max(0.0, C.EXEC_FIT_BASELINE - fit) * (
            C.EXEC_MISFIT_PENALTY - 1.0
        )
        total += fit - alternative - readiness_tax
    return (total / len(players)) / C.EXEC_FIT_DIV


def dial_execution_impact(
    roster: Iterable[Any], dial: str, value: float, chemistry: float
) -> float:
    """Exact engine/UI execution modifier for one dial value.

    This remains piecewise-linear with a hard zero at 50, so the existing
    impact_lo/impact_hi API contract stays valid and neutral matches remain
    byte-identical.
    """
    deviation = (float(value) - 50.0) / 50.0
    if deviation == 0.0:
        return 0.0
    pole: Pole = "high" if deviation > 0.0 else "low"
    edge = dial_pole_edge(roster, dial, pole)
    if pole == "high" and dial in CHEM_GATED:
        edge += chem_edge(chemistry)
    return abs(deviation) * edge


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
