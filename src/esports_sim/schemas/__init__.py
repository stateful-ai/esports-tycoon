"""Pydantic schemas. Every cross-module boundary in the sim is typed."""

from esports_sim.schemas.common import Role, Playstyle, Side, Region, TournamentTier
from esports_sim.schemas.attributes import AttributeDefinition, AttributeRegistry
from esports_sim.schemas.agent import Agent, Ability, AbilityEffect, AbilityType
from esports_sim.schemas.weapon import Weapon, WeaponClass
from esports_sim.schemas.map import Callout, Gimmick, GimmickType, Map, SightLine
from esports_sim.schemas.player import Player, AgentMastery, LanguageSkill, MapMastery
from esports_sim.schemas.team import Team, TeamLineup, TeamTactics
from esports_sim.schemas.match import MatchState, RoundState, PlayerRoundState, RoundPhase
from esports_sim.schemas.observation import PlayerObservation
from esports_sim.schemas.events import (
    Event,
    MatchStartEvent,
    MatchEndEvent,
    RoundStartEvent,
    RoundEndEvent,
    TimeoutEvent,
    KillEvent,
    SpikePlantEvent,
    SpikeDefuseEvent,
    BuyEvent,
    UtilityUsedEvent,
    MoveEvent,
    GimmickUsedEvent,
    WhiffEvent,
    CommsEvent,
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
    "AbilityEffect",
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
    "LanguageSkill",
    "MapMastery",
    "Team",
    "TeamLineup",
    "TeamTactics",
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
    "TimeoutEvent",
    "KillEvent",
    "SpikePlantEvent",
    "SpikeDefuseEvent",
    "BuyEvent",
    "UtilityUsedEvent",
    "MoveEvent",
    "GimmickUsedEvent",
    "WhiffEvent",
    "CommsEvent",
    "EventUnion",
]
