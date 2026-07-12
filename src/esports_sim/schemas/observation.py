"""Per-player observation. Separated from MatchState so that the match
engine can construct partial observations (fog of war, comms) without
leaking god's-eye state into a PlayerPolicy.

MVP policies receive the full observation; designing the schema split now
means adding partial-observability is additive, not structural.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas.communication import TeamBelief
from esports_sim.schemas.decision import PlayerConditionV1
from esports_sim.schemas.match import PlayerRoundState


class EnemyReadout(BaseModel):
    """What I currently believe about an enemy. Can be empty (no info),
    partial (heard footsteps -> known callout, unknown weapon), or full
    (direct line of sight)."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    last_seen_callout: str | None = None
    last_seen_tick: int | None = None
    weapon_guess: str | None = None
    alive_guess: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: Literal["seen", "remembered", "heard"] = "seen"


class PlayerObservation(BaseModel):
    """Delivered to `PlayerPolicy.decide()`. Stable contract for heuristic,
    RL, and LLM policies.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1

    # Who am I?
    self_state: PlayerRoundState
    player_condition: PlayerConditionV1 | None = None
    # What round is this, and what do I need to know about the clock?
    round_num: int
    tick: int
    spike_planted: bool
    is_attacking: bool

    # Teammates I can coordinate with. Full state — assume perfect comms.
    teammates: list[PlayerRoundState] = Field(default_factory=list)

    # What I believe about enemies. Filled by the match engine based on
    # sightlines, comms, and what I've been told.
    enemies: list[EnemyReadout] = Field(default_factory=list)

    # Fallible shared knowledge reconstructed for this receiver. These are
    # claims, not truth: no correctness bit or pristine source perception is
    # exposed to the policy.
    team_whiteboard: list[TeamBelief] = Field(default_factory=list)

    # Map topology — the policy can ask "what's adjacent to my callout?"
    adjacent_callouts: list[str] = Field(default_factory=list)

    # IGL call this round (e.g. "hit_a", "default", "b_lurk"). None = no call.
    igl_call: str | None = None

    # The team policy's current context. These are recommendations, not hidden
    # referee state: a PlayerPolicy may use, ignore, or reinterpret them.
    role: str = "flex"
    team_target: str | None = None
    timeout_directive: str | None = None
    tactical_aggression: float = 50.0
