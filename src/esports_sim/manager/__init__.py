"""Management layer: campaign state, seasons, training, economy, market."""

from esports_sim.manager.campaign import (
    WeekReport,
    advance_week,
    new_campaign,
    runtime_gamedata,
)
from esports_sim.manager.decision_env import HeadlessManagerEnv, manager_observation
from esports_sim.manager.manager_policy import ManagerProfile, generate_profile
from esports_sim.manager.rollout import evaluate_rollouts, run_batch, run_rollout
from esports_sim.manager.state import Fixture, GameState, MapResult, TeamRecord

__all__ = [
    "WeekReport",
    "advance_week",
    "new_campaign",
    "runtime_gamedata",
    "HeadlessManagerEnv",
    "manager_observation",
    "ManagerProfile",
    "generate_profile",
    "run_rollout",
    "run_batch",
    "evaluate_rollouts",
    "Fixture",
    "GameState",
    "MapResult",
    "TeamRecord",
]
