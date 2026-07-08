"""Team entity. MVP keeps chemistry as a scalar; pairwise relationships
and a proper chemistry graph are a post-MVP addition."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas.common import Region


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
