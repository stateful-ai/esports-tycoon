"""Team entity. MVP keeps chemistry as a scalar; pairwise relationships
and a proper chemistry graph are a post-MVP addition."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas.common import Region


class TeamTactics(BaseModel):
    """EHM-style coaching strategy — the identity a coach stamps on a
    team. The match engine reads these directly; 50 = neutral on every
    dial, so a default team plays exactly like the pre-tactics engine.

    aggression: angle-swinging appetite (peeks up, retreats down)
    pace: execute-vs-default lean (high = fast hits, early go timings)
    util_discipline: dump utility on the hit vs hold it for retakes
    eco_greed: force-buy appetite (greedy teams buy on broke rounds)
    site_focus: attack-side site preference ("balanced" or a site id)
    """

    model_config = ConfigDict(extra="forbid")

    aggression: float = Field(default=50.0, ge=0.0, le=100.0)
    pace: float = Field(default=50.0, ge=0.0, le=100.0)
    util_discipline: float = Field(default=50.0, ge=0.0, le=100.0)
    eco_greed: float = Field(default=50.0, ge=0.0, le=100.0)
    site_focus: str = "balanced"


class Team(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    tag: str  # short prefix for scoreboards, e.g. "NXS"
    region: Region = Region.AMERICAS
    # 1 = franchised league, 2 = Challengers (development circuit — fully
    # simulated, never broadcast).
    tier: int = 1

    # Roster. MVP = 5 active; substitutes/coaches land later.
    player_ids: list[str] = Field(default_factory=list)
    captain_id: str | None = None  # the designated IGL

    # Org state
    balance: int = 500_000
    reputation: float = Field(default=50.0, ge=0.0, le=100.0)
    fan_count: int = 0
    world_rank: int | None = None

    # Coarse chemistry. Will be replaced by a graph of pairwise relationships.
    chemistry: float = Field(default=70.0, ge=0.0, le=100.0)

    # Coaching strategy (defaults are neutral on every dial).
    tactics: TeamTactics = Field(default_factory=TeamTactics)
