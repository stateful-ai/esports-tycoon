"""Shared enums used across the simulator."""

from __future__ import annotations

from esports_sim._compat import StrEnum


class Role(StrEnum):
    """Canonical Valorant role. Determines what an agent is *built for*."""

    DUELIST = "duelist"
    CONTROLLER = "controller"
    INITIATOR = "initiator"
    SENTINEL = "sentinel"
    FLEX = "flex"


class Playstyle(StrEnum):
    """Orthogonal to role: how a player tends to approach a round.

    IGL calls strats; Entry takes first duels; Anchor holds sites;
    Lurker plays off-angles/timings; Awper snipes with the Operator;
    Support trades and provides util.
    """

    IGL = "igl"
    ENTRY = "entry"
    ANCHOR = "anchor"
    LURKER = "lurker"
    AWPER = "awper"
    SUPPORT = "support"


class Side(StrEnum):
    ATTACK = "attack"
    DEFENSE = "defense"


class Region(StrEnum):
    AMERICAS = "americas"
    EMEA = "emea"
    PACIFIC = "pacific"
    CHINA = "china"


class TournamentTier(StrEnum):
    """MVP tier set. Ascension / franchising structure comes later."""

    OPEN_QUALIFIER = "open_qualifier"
    CHALLENGERS = "challengers"
    MASTERS = "masters"
    CHAMPIONS = "champions"
