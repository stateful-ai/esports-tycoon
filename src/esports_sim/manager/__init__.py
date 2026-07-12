"""Management layer: campaign state, seasons, training, economy, market."""

from esports_sim.manager.campaign import (
    WeekReport,
    advance_week,
    new_campaign,
    runtime_gamedata,
)
from esports_sim.manager.decision_env import HeadlessManagerEnv, manager_observation
from esports_sim.manager.state import Fixture, GameState, MapResult, TeamRecord

__all__ = [
    "WeekReport",
    "advance_week",
    "new_campaign",
    "runtime_gamedata",
    "HeadlessManagerEnv",
    "manager_observation",
    "Fixture",
    "GameState",
    "MapResult",
    "TeamRecord",
]
