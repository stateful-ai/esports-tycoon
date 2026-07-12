"""Management layer: campaign state, seasons, training, economy, market."""

from esports_sim.manager.campaign import (
    WeekReport,
    advance_week,
    new_campaign,
    runtime_gamedata,
)
from esports_sim.manager.decision_env import HeadlessManagerEnv, manager_observation
from esports_sim.manager.manager_policy import ManagerProfile, generate_profile
from esports_sim.manager.learned_manager_policy import LearnedManagerModel
from esports_sim.manager.online_manager_learning import (
    OnlineLearningConfig,
    PromotionGate,
    evaluate_model,
    fine_tune_online,
    promotion_decision,
)
from esports_sim.manager.rollout import (
    evaluate_rollouts,
    play_policy_week,
    run_batch,
    run_rollout,
)
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
    "LearnedManagerModel",
    "OnlineLearningConfig",
    "PromotionGate",
    "fine_tune_online",
    "evaluate_model",
    "promotion_decision",
    "run_rollout",
    "play_policy_week",
    "run_batch",
    "evaluate_rollouts",
    "Fixture",
    "GameState",
    "MapResult",
    "TeamRecord",
]
