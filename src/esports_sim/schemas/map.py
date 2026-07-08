"""Map as a callout graph.

A map is a directed graph of named callouts with:
 - traversal edges (you can walk between these two callouts)
 - sight lines (if you stand in A you can potentially see into B, subject to
   smokes/utility)

This is coarse by design — the spatial unit is the callout, not pixels.
Decisions ("hold A short", "smoke mid", "lurk garage") are first-class.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum


class Site(StrEnum):
    A = "a"
    B = "b"
    C = "c"
    MID = "mid"
    NONE = "none"  # spawn / connector callouts


class CalloutZone(StrEnum):
    """Rough tactical zone used for strat-level reasoning."""

    ATTACKER_SPAWN = "attacker_spawn"
    DEFENDER_SPAWN = "defender_spawn"
    ATTACKER_SIDE = "attacker_side"  # attacker-favoured connectors
    DEFENDER_SIDE = "defender_side"  # defender-favoured connectors
    SITE = "site"
    MID = "mid"


class Callout(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str
    site: Site
    zone: CalloutZone
    # Free-form 2D position used only by the viewer. Not consumed by the sim.
    x: float = 0.0
    y: float = 0.0


class SightLine(BaseModel):
    """A potential sight connection between two callouts.

    The match engine decides, round-by-round, whether the sightline is
    *actually* active given smokes/walls/etc.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_callout: str
    to_callout: str
    # Which side is "holding" this sightline by default. Non-binding; either
    # side can contest.
    advantaged_side: str | None = None  # "attack" | "defense" | None


class GimmickType(StrEnum):
    """Map mechanics that live on an adjacency edge."""

    ROTATING_DOOR = "rotating_door"  # Lotus: usable but LOUD
    TELEPORTER = "teleporter"  # Bind: near-instant hop, loud at both ends
    BREAKABLE_DOOR = "breakable_door"  # Ascent: can start shut; shoot through


class Gimmick(BaseModel):
    """A mechanical feature on an edge. All uses are loud: enemies within
    `noise_radius` of the sound learn something real (watch snaps toward
    it; defenders may launch rotations off it) — which also makes fakes a
    legitimate play."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    type: GimmickType
    between: tuple[str, str]  # must also be an adjacency edge
    noise_radius: float = 25.0
    # breakable_door only: chance the defense starts the round with it shut.
    start_closed_prob: float = 0.7


class Map(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str
    sites: list[Site] = Field(default_factory=lambda: [Site.A, Site.B])
    callouts: dict[str, Callout]
    # Directed adjacency: from_id -> list of callouts you can walk into.
    adjacency: dict[str, list[str]]
    sightlines: list[SightLine] = Field(default_factory=list)
    attacker_spawn: str
    defender_spawn: str
    gimmicks: list[Gimmick] = Field(default_factory=list)

    def neighbors(self, callout_id: str) -> list[str]:
        return self.adjacency.get(callout_id, [])

    def exists(self, callout_id: str) -> bool:
        return callout_id in self.callouts
