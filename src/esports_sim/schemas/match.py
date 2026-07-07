"""Match and round state. Skeleton types — enough for downstream code to
take shape without pinning the match engine's internal representation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum
from esports_sim.schemas.common import Side


class RoundPhase(StrEnum):
    BUY = "buy"
    ROUND = "round"
    POST_PLANT = "post_plant"
    END = "end"


class PlayerRoundState(BaseModel):
    """Per-player state inside a round. Mutable within the round; the match
    engine reconstructs this from events on replay.
    """

    model_config = ConfigDict(extra="forbid")

    player_id: str
    agent_id: str
    alive: bool = True
    hp: int = 100
    armor: int = 0
    credits: int = 0
    weapon_id: str = "classic"
    # Current callout. None = spawn / not yet moved.
    callout_id: str | None = None
    # Remaining ability charges keyed by ability id.
    ability_charges: dict[str, int] = Field(default_factory=dict)
    ult_points: int = 0


class RoundState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_num: int
    phase: RoundPhase = RoundPhase.BUY
    attacking_team_id: str
    defending_team_id: str
    # Per-team per-player round state, keyed by player_id.
    players: dict[str, PlayerRoundState] = Field(default_factory=dict)
    spike_planted: bool = False
    spike_callout: str | None = None
    # Tick within the round (100ms each). Buy phase sits at tick 0.
    tick: int = 0


class MatchState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    map_id: str
    team_a_id: str
    team_b_id: str
    # Starting side for team_a. Team_b is the opposite.
    team_a_starting_side: Side = Side.ATTACK
    # Rounds won per team.
    score_a: int = 0
    score_b: int = 0
    rounds: list[RoundState] = Field(default_factory=list)
    # True once match has a winner (bo1 first-to-13 + OT).
    finished: bool = False
    winner_id: str | None = None
