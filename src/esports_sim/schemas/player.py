"""Player entity. Attributes are a dict keyed by attribute-registry ids —
adding a new attribute is a config change, not a schema migration.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas.common import Playstyle, Region, Role


class AgentMastery(BaseModel):
    """Per-agent mastery — a player's third-best Jett is not their main Jett."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    mastery: float = Field(ge=0.0, le=100.0)


class MapMastery(BaseModel):
    """Per-map comfort. Teams have map pool depth; so do individuals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    map_id: str
    mastery: float = Field(ge=0.0, le=100.0)


class Player(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Identity
    id: str
    handle: str
    real_name: str = ""
    region: Region = Region.AMERICAS
    age: int = 20

    # Role / style
    role: Role
    playstyle: Playstyle

    # Attributes: dict keyed by attribute-registry id. Sim code reads by id
    # with a default if a key is missing, so adding attributes is non-breaking.
    attributes: dict[str, float] = Field(default_factory=dict)

    # Per-agent / per-map mastery. MVP uses these in future match-engine tuning;
    # the data is authored now so policies can start reading it immediately.
    agent_pool: list[AgentMastery] = Field(default_factory=list)
    map_pool: list[MapMastery] = Field(default_factory=list)

    # Hidden ceiling (EHM-style Potential Ability, 1-99 like attributes).
    # 0 = not assigned; manager/development.py derives a stable fallback.
    potential: float = Field(default=0.0, ge=0.0, le=99.0)

    # Career / contract
    salary: int = 0  # per week
    contract_weeks_left: int = 0
    morale: float = Field(default=70.0, ge=0.0, le=100.0)
    stamina: float = Field(default=100.0, ge=0.0, le=100.0)
    form: float = Field(default=50.0, ge=0.0, le=100.0)

    # Confidence: belief in their own game right now. The match engine
    # reads it NEUTRAL-SAFE (exact no-op at 50 — see ADR-007), so the
    # default keeps the golden gates byte-stable; the campaign layer moves
    # it on results, personal ratings, dev events and the social layer.
    confidence: float = Field(default=50.0, ge=0.0, le=100.0)

    # Social reach. 0 = not seeded yet; manager/social.py derives a stable
    # per-player baseline (ability + id hash) on first touch.
    followers: int = 0

    # Individual development plan, user-set (AI players stay on defaults).
    # dev_focus: "auto" follows the team's weekly focus, otherwise pins one
    # training category for this player every week.
    dev_focus: str = "auto"  # auto | mechanical | tactical | mental | team
    # Intensity trades growth for stamina (and burnout risk at "intense").
    training_intensity: str = "normal"  # light | normal | intense

    # Free-form tags for personality. The narrative layer keys off these.
    personality_tags: list[str] = Field(default_factory=list)

    def attr(self, attr_id: str, default: float = 50.0) -> float:
        """Read an attribute by id with a default, never raises."""
        return self.attributes.get(attr_id, default)

    def agent_mastery(self, agent_id: str, default: float = 0.0) -> float:
        for m in self.agent_pool:
            if m.agent_id == agent_id:
                return m.mastery
        return default
