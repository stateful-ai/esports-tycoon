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
    # Agent each player locked for this map (player_id -> agent_id). Lets
    # stats attribute a whole map line to the agent actually played.
    agents: dict[str, str] = Field(default_factory=dict)


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
    # Breakable doors the defense shut during setup (gimmick ids).
    closed_doors: list[str] = Field(default_factory=list)


class RoundEndEvent(Event):
    type: Literal["round.end"] = "round.end"
    round_num: int
    winner_id: str
    # How the round ended. Useful for narrative + reward shaping.
    reason: Literal["elim", "spike_detonation", "spike_defused", "time"]


class TimeoutEvent(Event):
    """A coach timeout between rounds.

    It is deliberately observable because it is the coach's only live match
    input.  ``directive`` is advice received by the next round's team policy,
    never a direct stat modifier.
    """

    type: Literal["round.timeout"] = "round.timeout"
    round_num: int
    team_id: str
    coach_id: str
    directive: Literal["stabilize", "pressure", "retake"]
    clarity: float


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
    # Flash assist: the teammate whose flash the victim was still blind
    # from when they died (None = unassisted).
    assist_id: str | None = None
    # Where the victim actually stood (continuous layer; None in old logs).
    victim_x: float | None = None
    victim_y: float | None = None


class SpikePlantEvent(Event):
    type: Literal["round.spike_plant"] = "round.spike_plant"
    player_id: str
    callout_id: str
    # Exact plant spot (continuous layer; None in old logs).
    x: float | None = None
    y: float | None = None


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
    # A whiffed lineup: charge spent, no effect (low utility_usage).
    failed: bool = False


class WhiffEvent(Event):
    """A duel where the opening shots missed — both players live and
    reposition. Pure texture for the feed/viewer; no reward impact."""

    type: Literal["round.whiff"] = "round.whiff"
    a_id: str
    b_id: str
    x: float | None = None
    y: float | None = None


class CommsEvent(Event):
    """Team communication moment: a clean rotate call, or crossed comms
    that stall the rotation. `player_id` is the voice on the call."""

    type: Literal["round.comms"] = "round.comms"
    team_id: str
    player_id: str
    kind: str  # call | miscomm


class GimmickUsedEvent(Event):
    """A map mechanic fired: a rotating door swung, a teleporter took
    someone, a shut door got shot open. Loud by design — the viewer pings
    it and nearby enemies react in-engine."""

    type: Literal["round.gimmick"] = "round.gimmick"
    gimmick_id: str
    kind: str  # rotating_door | teleporter | breakable_door
    action: str  # "used" | "broken"
    player_id: str
    x: float | None = None
    y: float | None = None


class MoveEvent(Event):
    """Player movement in continuous space.

    Emitted at move START (`tick`), carrying the waypoint polyline and the
    expected `arrive_tick`; a re-paced move (defensive utility stalls the
    push) emits a fresh event that supersedes the old one. Placement:
    `from_callout is None`, waypoints hold the single spawn position.
    Viewers lerp along `waypoints` by arc length between tick and
    arrive_tick — no sim logic needed. Coordinate-free consumers can keep
    using the callout fields.
    """

    type: Literal["round.move"] = "round.move"
    player_id: str
    from_callout: str | None = None
    to_callout: str
    # Continuous layer (absent in pre-geometry logs).
    waypoints: list[tuple[float, float]] = Field(default_factory=list)
    arrive_tick: int | None = None


class MotorControlEvent(Event):
    """Observable change in a player's per-tick motor command.

    Repeated identical commands are intentionally coalesced. Training traces
    may retain every decision while replay logs only need state transitions.
    """

    type: Literal["round.control"] = "round.control"
    player_id: str
    movement: Literal["hold", "advance"]
    pace: Literal["walk", "run"]
    turn_degrees: float = 0.0
    heading_degrees: float = 0.0
    x: float
    y: float
    route_active: bool = False
    callout_id: str | None = None
    route_target_callout: str | None = None


from esports_sim.schemas.team import HalftimeTalk, TouchlineShout


class HalftimeTalkEvent(Event):
    type: Literal["round.halftime_talk"] = "round.halftime_talk"
    round_num: int
    team_id: str
    talk: HalftimeTalk


class TouchlineShoutEvent(Event):
    type: Literal["round.touchline_shout"] = "round.touchline_shout"
    round_num: int
    team_id: str
    shout: TouchlineShout


class DuelTelemetryEvent(Event):
    type: Literal["round.duel_telemetry"] = "round.duel_telemetry"
    attacker_id: str
    defender_id: str
    attacker_score: float
    defender_score: float
    expected_win_prob: float
    winner_id: str
    attacker_breakdown: dict[str, float]
    defender_breakdown: dict[str, float]
    duel_range: float
    height_delta: float
    attacker_cover: bool
    defender_cover: bool
    attacker_peeking: bool
    defender_peeking: bool
    attacker_holder: bool
    defender_holder: bool


# ---------------------------------------------------------------------------
# Discriminated union for parsing from JSONL


EventUnion = Annotated[
    Union[
        MatchStartEvent,
        MatchEndEvent,
        RoundStartEvent,
        RoundEndEvent,
        TimeoutEvent,
        BuyEvent,
        KillEvent,
        SpikePlantEvent,
        SpikeDefuseEvent,
        UtilityUsedEvent,
        MoveEvent,
        MotorControlEvent,
        GimmickUsedEvent,
        WhiffEvent,
        CommsEvent,
        HalftimeTalkEvent,
        TouchlineShoutEvent,
        DuelTelemetryEvent,
    ],
    Field(discriminator="type"),
]


class ChronicleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season: int
    week: int
    message: str

