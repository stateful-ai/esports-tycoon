"""Valorant agents (the in-game characters: Jett, Raze, Omen, etc.).

Ability flags and optional explicit effect metadata feed the engine's
contextual, site-targeted utility model. Legacy roster packs remain valid
because their original flags are still a complete effect fallback.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum
from esports_sim.schemas.common import Role


class AbilityType(StrEnum):
    BASIC = "basic"  # purchasable each round
    SIGNATURE = "signature"  # free on cooldown / per round
    ULTIMATE = "ultimate"  # charges over rounds/kills/orbs


class AbilityEffect(StrEnum):
    """Concrete utility affordances the match engine can resolve.

    ``effects`` supplements the original coarse boolean flags. Keeping the
    flags makes older roster packs and viewer consumers compatible while
    letting newer agent data distinguish, for example, a dash from a smoke.
    """

    SMOKE = "smoke"
    FLASH = "flash"
    DAMAGE = "damage"
    INFO = "info"
    MOBILITY = "mobility"


class Ability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    type: AbilityType
    charges: int = 1
    cost: int = 0  # creds for basic/signature, 0 for ult
    ult_points: int | None = None  # for ultimates
    # Legacy mechanical flags. The engine derives effects from these when an
    # older roster pack does not provide explicit ``effects`` metadata.
    blocks_sight: bool = False
    flashes: bool = False
    damages: bool = False
    info: bool = False  # reveals enemy positions
    effects: tuple[AbilityEffect, ...] = ()


class Agent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str
    role: Role
    abilities: list[Ability] = Field(default_factory=list)
    description: str = ""
    # This agent's kit is built around operator play (Jett's disengage
    # dash, Chamber's TP): op duels on them get a small engine bonus
    # (C.OPERATOR_AGENT_AFFINITY) — you can op on anyone, but only these
    # kits buff it.
    op_affinity: bool = False
