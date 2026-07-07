"""Valorant agents (the in-game characters: Jett, Raze, Omen, etc.).

Deliberately sparse for MVP — abilities have names + types but no mechanics
yet. Mechanics land when the match engine starts using them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum
from esports_sim.schemas.common import Role


class AbilityType(StrEnum):
    BASIC = "basic"  # purchasable each round
    SIGNATURE = "signature"  # free on cooldown / per round
    ULTIMATE = "ultimate"  # charges over rounds/kills/orbs


class Ability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    type: AbilityType
    charges: int = 1
    cost: int = 0  # creds for basic/signature, 0 for ult
    ult_points: int | None = None  # for ultimates
    # Mechanical flags for the future match engine. Consumed later.
    blocks_sight: bool = False
    flashes: bool = False
    damages: bool = False
    info: bool = False  # reveals enemy positions


class Agent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str
    role: Role
    abilities: list[Ability] = Field(default_factory=list)
    description: str = ""
