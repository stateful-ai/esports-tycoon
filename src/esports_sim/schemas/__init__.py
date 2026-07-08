"""Pydantic schemas. Every cross-module boundary in the sim is typed."""

from esports_sim.schemas.common import Role, Playstyle, Side, Region, TournamentTier
from esports_sim.schemas.attributes import AttributeDefinition, AttributeRegistry
from esports_sim.schemas.agent import Agent, Ability, AbilityType
from esports_sim.schemas.weapon import Weapon, WeaponClass
from esports_sim.schemas.map import Callout, Gimmick, GimmickType, Map, SightLine
from esports_sim.schemas.player import Player, AgentMastery, MapMastery
from esports_sim.schemas.team import Team
from esports_sim.schemas.match import MatchState, RoundState, PlayerRoundState, RoundPhase
from esports_sim.schemas.observation import PlayerObservation
from esports_sim.schemas.events import (
    Event,
    MatchStartEvent,
    MatchEndEvent,
    RoundStartEvent,
    RoundEndEvent,
    KillEvent,
    SpikePlantEvent,
    SpikeDefuseEvent,
    BuyEvent,
    UtilityUsedEvent,
    MoveEvent,
    GimmickUsedEvent,
    EventUnion,
)

__all__ = [
    "Role",
    "Playstyle",
    "Side",
    "Region",
    "TournamentTier",
    "AttributeDefinition",
    "AttributeRegistry",
    "Agent",
    "Ability",
    "AbilityType",
    "Weapon",
    "WeaponClass",
    "Callout",
    "Gimmick",
    "GimmickType",
    "Map",
    "SightLine",
    "Player",
    "AgentMastery",
    "MapMastery",
    "Team",
    "MatchState",
    "RoundState",
    "PlayerRoundState",
    "RoundPhase",
    "PlayerObservation",
    "Event",
    "MatchStartEvent",
    "MatchEndEvent",
    "RoundStartEvent",
    "RoundEndEvent",
    "KillEvent",
    "SpikePlantEvent",
    "SpikeDefuseEvent",
    "BuyEvent",
    "UtilityUsedEvent",
    "MoveEvent",
    "GimmickUsedEvent",
    "EventUnion",
]
