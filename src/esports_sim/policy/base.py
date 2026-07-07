"""`PlayerPolicy` — the stable contract between the match engine and
any decision-maker that controls a player.

Heuristic policies (MVP), per-player RL agents (research phase), and
LLM-in-the-loop playtesters all implement this.

Kept minimal on purpose. The action vocabulary will expand as the match
engine takes shape; adding an ActionType here is the only coupling.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum
from esports_sim.schemas.observation import PlayerObservation


class ActionType(StrEnum):
    # Movement
    MOVE_TO = "move_to"  # -> callout_id
    HOLD = "hold"  # stay put
    PEEK = "peek"  # commit to angle
    ROTATE = "rotate"  # higher-level: cross the map
    # Combat
    SHOOT = "shoot"  # -> target_player_id
    # Utility / economy
    USE_ABILITY = "use_ability"  # -> ability_id, target_callout
    BUY = "buy"  # -> weapon_id, armor, abilities (buy phase only)
    # Objective
    PLANT_SPIKE = "plant_spike"
    DEFUSE_SPIKE = "defuse_spike"
    # Null / no-op
    WAIT = "wait"


class Action(BaseModel):
    """Structured action emitted by a policy. Fields beyond `type` are
    action-specific; the match engine validates."""

    model_config = ConfigDict(extra="forbid")

    type: ActionType
    callout_id: str | None = None
    target_player_id: str | None = None
    weapon_id: str | None = None
    ability_id: str | None = None
    armor: int = 0
    abilities: list[str] = Field(default_factory=list)


class PlayerPolicy(Protocol):
    """Any decision-maker for an in-match player implements this.

    `decide` is called every tick that the player is alive and must act.
    The policy is given:
      - `obs`: a per-player observation (what they can see / were told)
      - `legal`: the set of legal actions right now, pre-filtered by the engine
      - `rng`: a deterministic numpy Generator — the policy MUST NOT use any
        other randomness source. Anything stochastic must go through this RNG.
    """

    def decide(
        self,
        obs: PlayerObservation,
        legal: list[Action],
        rng: np.random.Generator,
    ) -> Action: ...
