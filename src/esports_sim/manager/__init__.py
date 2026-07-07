"""Management layer: campaign state, seasons, training, economy, market."""

from esports_sim.manager.campaign import (
    WeekReport,
    advance_week,
    new_campaign,
    runtime_gamedata,
)
from esports_sim.manager.state import Fixture, GameState, MapResult, TeamRecord

__all__ = [
    "WeekReport",
    "advance_week",
    "new_campaign",
    "runtime_gamedata",
    "Fixture",
    "GameState",
    "MapResult",
    "TeamRecord",
]
