"""Typed communication and team-belief contracts for player policies.

World truth never uses these models.  A claim is what one player says; a
belief is the fallible, decaying version a particular teammate remembers.
Keeping the two distinct prevents policy observations from acquiring a hidden
ground-truth channel when comms are wrong.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from esports_sim._compat import StrEnum


class ClaimKind(StrEnum):
    ENEMY_LOCATION = "enemy_location"
    ENEMY_INTENT = "enemy_intent"
    AREA_STATUS = "area_status"
    OBJECTIVE = "objective"
    TEAM_INTENT = "team_intent"


class ClaimValue(StrEnum):
    PRESENT = "present"
    ROTATING = "rotating"
    EXECUTING = "executing"
    CLEAR = "clear"
    CONTESTED = "contested"
    SPIKE_SEEN = "spike_seen"
    SPIKE_DROPPED = "spike_dropped"
    PLANTING = "planting"
    HOLD = "hold"
    ROTATE = "rotate"
    RETAKE = "retake"
    SAVE = "save"
    TRADE = "trade"


class CommunicationAction(BaseModel):
    """A structured, optional utterance from a policy's parallel comms head."""

    model_config = ConfigDict(extra="forbid")

    speak: bool = False
    kind: ClaimKind | None = None
    value: ClaimValue | None = None
    callout_id: str | None = None
    enemy_id: str | None = None
    expressed_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    corrects_claim_id: str | None = None

    @model_validator(mode="after")
    def _spoken_claim_is_complete(self) -> "CommunicationAction":
        if self.speak and (self.kind is None or self.value is None):
            raise ValueError("spoken communication requires kind and value")
        if not self.speak and any(
            value is not None
            for value in (
                self.kind,
                self.value,
                self.callout_id,
                self.enemy_id,
                self.corrects_claim_id,
            )
        ):
            raise ValueError("silent communication cannot carry a claim")
        return self


class TeamClaim(BaseModel):
    """One delivered assertion in the append-only round comms ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    claim_id: str
    team_id: str
    sender_id: str
    kind: ClaimKind
    value: ClaimValue
    callout_id: str | None = None
    enemy_id: str | None = None
    observed_tick: int = Field(ge=0)
    delivered_tick: int = Field(ge=0)
    expressed_confidence: float = Field(ge=0.0, le=1.0)
    corrects_claim_id: str | None = None


class TeamBelief(BaseModel):
    """Receiver-specific memory of a claim exposed in PlayerObservation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    claim_id: str
    source_player_id: str
    kind: ClaimKind
    value: ClaimValue
    callout_id: str | None = None
    enemy_id: str | None = None
    age_ticks: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    corrects_claim_id: str | None = None
