"""Policy contracts for the match engine.

The referee owns legality, physics, objective channels, and event emission.
Policies own decisions:

* one :class:`PlayerPolicy` for every dressed player;
* one :class:`TeamPolicy` for each side's round plan; and
* one :class:`CoachPolicy` for each side's *timeout-only* intervention.

Heuristic policies (MVP), per-player RL agents (research phase), and
LLM-in-the-loop playtesters all implement this.

Kept minimal on purpose. The action vocabulary will expand as the match
engine takes shape; adding an ActionType here is the only coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum
from esports_sim.schemas.observation import PlayerObservation
from esports_sim.schemas.player import Player
from esports_sim.schemas.team import TeamTactics


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


@dataclass(frozen=True)
class CoachProfile:
    """The match-facing projection of a coach.

    Campaign staff stay in the manager layer.  This intentionally small
    profile lets a match receive the decision-relevant coach facts without
    coupling the simulator to ``GameState`` or its staff market.
    """

    id: str
    quality: float = 50.0
    specialty: str = ""
    traits: tuple[str, ...] = ()


@dataclass(frozen=True)
class TimeoutDirective:
    """The only live input a coach may make during a map.

    A directive is advice for the policy, not a duel buff.  It is consumed by
    the next round plan, where players still choose and execute the actions.
    """

    kind: Literal["stabilize", "pressure", "retake"]
    clarity: float


@dataclass(frozen=True)
class CoachObservation:
    """Information available to a coach between rounds."""

    team_id: str
    round_num: int
    score_for: int
    score_against: int
    loss_streak: int
    is_attacking: bool
    profile: CoachProfile


@dataclass(frozen=True)
class BuyPlanRequest:
    """Team-level economy snapshot for a buy decision."""

    team_id: str
    round_num: int
    average_credits: float
    tactics: TeamTactics


@dataclass(frozen=True)
class AttackRoundRequest:
    """Shared information used to form one attacking round plan."""

    team_id: str
    opponent_id: str
    players: tuple[Player, ...]
    captain_id: str | None
    round_num: int
    sites: tuple[str, ...]
    site_wins: dict[str, int]
    tactics: TeamTactics
    under_gunned: bool
    prep_edge: float = 0.0
    scouted_site_load: dict[str, float] = field(default_factory=dict)
    timeout: TimeoutDirective | None = None


@dataclass(frozen=True)
class AttackRoundPlan:
    """Policy-selected attack identity for one round.

    ``staging_orders`` and ``roles`` are player-addressed deliberately: the
    referee no longer assigns entry/lurk responsibilities itself.
    """

    target_site: str
    strategy: Literal["execute", "default"]
    go_tick: int
    spike_carrier_id: str
    lurker_id: str | None
    staging_orders: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DefenseRoundRequest:
    """Shared information used to form one defensive setup."""

    team_id: str
    opponent_id: str
    players: tuple[Player, ...]
    tactics: TeamTactics
    sites: tuple[str, ...]
    timeout: TimeoutDirective | None = None


@dataclass(frozen=True)
class DefenseRoundPlan:
    """Policy-selected defensive positions and player responsibilities."""

    assignments: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RotationPlanRequest:
    """Information available when a defender team reacts to a hit."""

    team_id: str
    off_site_ids: tuple[str, ...]
    players_by_id: dict[str, Player]


class TeamPolicy(Protocol):
    """Policy that turns shared team information into a round plan."""

    def choose_buy(self, request: BuyPlanRequest) -> str: ...

    def plan_attack(
        self, request: AttackRoundRequest, rng: np.random.Generator
    ) -> AttackRoundPlan: ...

    def plan_defense(
        self, request: DefenseRoundRequest, rng: np.random.Generator
    ) -> DefenseRoundPlan: ...

    def choose_rotation_holdback(
        self, request: RotationPlanRequest
    ) -> str | None: ...


class CoachPolicy(Protocol):
    """A coach can speak only by calling a timeout between rounds."""

    def call_timeout(
        self, observation: CoachObservation, rng: np.random.Generator
    ) -> TimeoutDirective | None: ...


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
