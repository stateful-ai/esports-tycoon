"""Versioned tensor-source contracts for learned player policies."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas.common import Playstyle, Role


class PlayerConditionV1(BaseModel):
    """Compositional player identity; deliberately contains no player id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    role: Role
    playstyle: Playstyle
    personality_tags: tuple[str, ...] = ()
    aim_precision: float = Field(ge=0.0, le=100.0)
    aim_reactivity: float = Field(ge=0.0, le=100.0)
    movement: float = Field(ge=0.0, le=100.0)
    game_sense: float = Field(ge=0.0, le=100.0)
    utility_usage: float = Field(ge=0.0, le=100.0)
    positioning: float = Field(ge=0.0, le=100.0)
    clutch_factor: float = Field(ge=0.0, le=100.0)
    tilt_resistance: float = Field(ge=0.0, le=100.0)
    composure: float = Field(ge=0.0, le=100.0)
    comms_quality: float = Field(ge=0.0, le=100.0)
    agent_mastery: float = Field(ge=0.0, le=100.0)
    map_mastery: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=100.0)
    form: float = Field(ge=0.0, le=100.0)
    stamina: float = Field(ge=0.0, le=100.0)
