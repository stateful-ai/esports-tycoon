"""Typed events emitted by the sim.

Events are the canonical record. UI replays from them, narrative keys off
them, reward functions read them, LLM playtesters observe them.

Adding a new event type: define the Pydantic model below, add it to
EventUnion, and subscribe in whatever consumers care. Pydantic's
discriminated union (on `type`) gives you free parsing from JSONL.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Base


class Event(BaseModel):
    """Base. Every event carries a tick (sim time) and a seed path (for
    reproducibility — which RNG produced the stochastic part of this event).
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    tick: int = 0
    seed_path: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Match lifecycle


class MatchStartEvent(Event):
    type: Literal["match.start"] = "match.start"
    match_id: str
    map_id: str
    team_a_id: str
    team_b_id: str
    seed: int


class MatchEndEvent(Event):
    type: Literal["match.end"] = "match.end"
    match_id: str
    winner_id: str
    score_a: int
    score_b: int


# ---------------------------------------------------------------------------
# Round lifecycle


class RoundStartEvent(Event):
    type: Literal["round.start"] = "round.start"
    round_num: int
    attacking_team_id: str
    defending_team_id: str


class RoundEndEvent(Event):
    type: Literal["round.end"] = "round.end"
    round_num: int
    winner_id: str
    # How the round ended. Useful for narrative + reward shaping.
    reason: Literal["elim", "spike_detonation", "spike_defused", "time"]


# ---------------------------------------------------------------------------
# In-round events


class BuyEvent(Event):
    type: Literal["round.buy"] = "round.buy"
    player_id: str
    weapon_id: str
    armor: int
    abilities_bought: list[str] = Field(default_factory=list)
    spent: int


class KillEvent(Event):
    type: Literal["round.kill"] = "round.kill"
    killer_id: str
    victim_id: str
    weapon_id: str
    headshot: bool = False
    callout_id: str | None = None
    # "trade" = kill within N ticks of a teammate dying, useful for chemistry.
    is_trade: bool = False


class SpikePlantEvent(Event):
    type: Literal["round.spike_plant"] = "round.spike_plant"
    player_id: str
    callout_id: str


class SpikeDefuseEvent(Event):
    type: Literal["round.spike_defuse"] = "round.spike_defuse"
    player_id: str
    # Full = 7s, half = 3.5s
    half_defuse: bool = False


class UtilityUsedEvent(Event):
    type: Literal["round.utility_used"] = "round.utility_used"
    player_id: str
    ability_id: str
    target_callout: str | None = None


# ---------------------------------------------------------------------------
# Discriminated union for parsing from JSONL


EventUnion = Annotated[
    Union[
        MatchStartEvent,
        MatchEndEvent,
        RoundStartEvent,
        RoundEndEvent,
        BuyEvent,
        KillEvent,
        SpikePlantEvent,
        SpikeDefuseEvent,
        UtilityUsedEvent,
    ],
    Field(discriminator="type"),
]
