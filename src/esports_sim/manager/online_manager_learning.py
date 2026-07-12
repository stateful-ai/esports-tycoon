"""Deterministic reward fine-tuning and champion promotion for manager agents.

This milestone updates only the learned action-category head. Existing heads
still choose legal players, staff, tactics, and other action parameters. That
keeps online improvement small, auditable, and reversible while simulation
rewards begin replacing heuristic demonstrations as the learning signal.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any, Iterable

import numpy as np

from esports_sim.manager.learned_manager_policy import (
    ACTION_VOCAB,
    LearnedManagerModel,
    LearnedManagerPolicy,
)
from esports_sim.manager.manager_policy import ManagerProfile
from esports_sim.manager.rollout import RolloutResult, evaluate_rollouts, run_rollout
from esports_sim.registry import GameData

ONLINE_POLICY_VERSION = "learned-manager-online-explore-v1"


@dataclass(frozen=True)
class OnlineLearningConfig:
    iterations: int = 3
    learning_rate: float = 0.03
    temperature: float = 1.1
    anchor_l2: float = 0.01
    max_gradient_norm: float = 5.0
    max_actions_per_week: int = 12


@dataclass(frozen=True)
class PromotionGate:
    reward_tolerance: float = 0.05
    balance_tolerance: float = 25_000.0
    wins_tolerance: float = 0.25
    profile_tv_ratio: float = 0.5


@dataclass
class ExplorationSample:
    features: np.ndarray
    probabilities: np.ndarray
    selected_index: int
    trainable: bool


def _exploration_seed(iteration: int, campaign_seed: int, profile_id: str) -> int:
    digest = hashlib.blake2b(
        f"manager-online|{iteration}|{campaign_seed}|{profile_id}".encode(),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big")


class ExploringLearnedManagerPolicy(LearnedManagerPolicy):
    """A reproducible masked sampler used only to generate training episodes."""

    version = ONLINE_POLICY_VERSION

    def __init__(
        self,
        model: LearnedManagerModel,
        profile: ManagerProfile,
        *,
        exploration_seed: int,
        temperature: float = 1.1,
        max_actions_per_week: int = 12,
    ) -> None:
        super().__init__(model, profile)
        self.rng = np.random.default_rng(exploration_seed)
        self.temperature = max(float(temperature), 1e-6)
        self.max_actions_per_week = max(int(max_actions_per_week), 2)
        self.samples: list[ExplorationSample] = []
        self._decision_counts: dict[tuple[int, int], int] = {}

    def choose_action(self, obs: dict[str, Any]) -> dict[str, Any]:
        obs, x, mask, probs = self._action_distribution(
            obs, temperature=self.temperature
        )
        week = (int(obs["season"]), int(obs["week"]))
        count = self._decision_counts.get(week, 0)
        advance_index = ACTION_VOCAB.index("advance")
        forced_action = count >= self.max_actions_per_week - 1
        forced_advance = forced_action and bool(mask[advance_index])
        forced_recovery = False
        if forced_advance:
            selected_index = advance_index
        elif forced_action:
            # Exploration can legally release a player, which temporarily
            # makes ``advance`` illegal until the roster is repaired. Recover
            # through a manager-visible legal action rather than sampling
            # unrelated actions until the rollout's decision budget expires.
            recovery = next(
                (
                    ACTION_VOCAB.index(kind)
                    for kind in ("accept_job", "sign")
                    if mask[ACTION_VOCAB.index(kind)]
                ),
                None,
            )
            if recovery is None:
                raise RuntimeError("exploration policy cannot recover a blocked week")
            selected_index = recovery
            forced_recovery = True
        else:
            selected_index = int(self.rng.choice(len(ACTION_VOCAB), p=probs))
        kind = ACTION_VOCAB[selected_index]
        self._decision_counts[week] = count + 1
        self._used.setdefault(week, set()).add(kind)
        action = self._build_action(obs, kind, x)
        self.samples.append(
            ExplorationSample(
                features=x.copy(),
                probabilities=probs.copy(),
                selected_index=selected_index,
                trainable=not forced_action,
            )
        )
        probabilities = {
            name: round(float(probs[i]), 6) for i, name in enumerate(ACTION_VOCAB)
        }
        self.last_decision = {
            "selected": kind,
            "probability": probabilities[kind],
            "sampled": True,
            "forced_advance": forced_advance,
            "forced_recovery": forced_recovery,
            "legal_action_count": int(mask.sum()),
            "profile": self.profile.to_dict(),
            "top_actions": sorted(
                probabilities.items(), key=lambda item: (-item[1], item[0])
            )[:5],
            "action": action,
        }
        return action


def _validate_training_inputs(
    seeds: list[int],
    profiles: list[ManagerProfile],
    weeks: int,
    config: OnlineLearningConfig,
) -> None:
    if not seeds or not profiles:
        raise ValueError("online learning requires seeds and manager profiles")
    if weeks <= 0 or config.iterations <= 0:
        raise ValueError("weeks and online-learning iterations must be positive")
    if config.learning_rate <= 0 or config.temperature <= 0:
        raise ValueError("learning rate and exploration temperature must be positive")


def fine_tune_online(
    gd: GameData,
    incumbent: LearnedManagerModel,
    *,
    seeds: Iterable[int],
    profiles: Iterable[ManagerProfile],
    weeks: int,
    config: OnlineLearningConfig | None = None,
) -> tuple[LearnedManagerModel, dict[str, Any]]:
    """Fine-tune a cloned checkpoint with deterministic REINFORCE updates."""
    config = config or OnlineLearningConfig()
    seed_list = list(seeds)
    profile_list = list(profiles)
    _validate_training_inputs(seed_list, profile_list, weeks, config)
    challenger = incumbent.clone()
    anchor = incumbent.action_weights.copy()
    iteration_reports: list[dict[str, Any]] = []

    for iteration in range(config.iterations):
        episodes: list[tuple[RolloutResult, ExploringLearnedManagerPolicy]] = []
        for profile in profile_list:
            for campaign_seed in seed_list:
                policy = ExploringLearnedManagerPolicy(
                    challenger,
                    profile,
                    exploration_seed=_exploration_seed(
                        iteration, campaign_seed, profile.id
                    ),
                    temperature=config.temperature,
                    max_actions_per_week=config.max_actions_per_week,
                )
                run = run_rollout(
                    gd,
                    seed=campaign_seed,
                    weeks=weeks,
                    profile=profile,
                    policy=policy,
                    # A forced recovery may be needed before the following
                    # forced advance, so leave two deterministic recovery
                    # slots beyond the sampler's normal action budget.
                    max_decisions_per_week=config.max_actions_per_week + 2,
                )
                episodes.append((run, policy))

        rewards = np.asarray(
            [run.total_reward for run, _ in episodes], dtype=np.float64
        )
        baseline = float(rewards.mean())
        scale = float(rewards.std())
        if scale < 1e-9:
            scale = 1.0
        gradient = np.zeros_like(challenger.action_weights)
        sample_count = 0
        for (run, policy), reward in zip(episodes, rewards):
            advantage = (float(reward) - baseline) / scale
            for sample in policy.samples:
                if not sample.trainable:
                    continue
                direction = -sample.probabilities
                direction = direction.copy()
                direction[sample.selected_index] += 1.0
                gradient += (
                    advantage
                    * np.outer(direction, sample.features)
                    / config.temperature
                )
                sample_count += 1
        if sample_count:
            gradient /= sample_count
        gradient -= config.anchor_l2 * (challenger.action_weights - anchor)
        raw_norm = float(np.linalg.norm(gradient))
        if raw_norm > config.max_gradient_norm > 0:
            gradient *= config.max_gradient_norm / raw_norm
        applied_norm = float(np.linalg.norm(gradient))
        challenger.action_weights += config.learning_rate * gradient
        iteration_reports.append(
            {
                "iteration": iteration + 1,
                "episodes": len(episodes),
                "samples": sample_count,
                "mean_reward": round(baseline, 6),
                "reward_std": round(float(rewards.std()), 6),
                "gradient_norm": round(applied_norm, 8),
                "action_weight_delta": round(
                    float(np.linalg.norm(challenger.action_weights - anchor)), 8
                ),
                "invalid_actions": sum(run.invalid_actions for run, _ in episodes),
            }
        )

    report = {
        "algorithm": "reinforce-action-head-v1",
        "config": asdict(config),
        "seeds": seed_list,
        "profiles": [profile.id for profile in profile_list],
        "weeks": weeks,
        "iterations": iteration_reports,
    }
    challenger.metadata = {**challenger.metadata, "online_learning": report}
    return challenger, report


def evaluate_model(
    gd: GameData,
    model: LearnedManagerModel,
    *,
    seeds: Iterable[int],
    profiles: Iterable[ManagerProfile],
    weeks: int,
) -> dict[str, Any]:
    """Evaluate a checkpoint deterministically and retain rollout failures."""
    seed_list = list(seeds)
    profile_list = list(profiles)
    if not seed_list or not profile_list or weeks <= 0:
        raise ValueError("evaluation requires seeds, profiles, and positive weeks")
    runs: list[RolloutResult] = []
    failures: list[dict[str, Any]] = []
    for profile in profile_list:
        for campaign_seed in seed_list:
            try:
                runs.append(
                    run_rollout(
                        gd,
                        seed=campaign_seed,
                        weeks=weeks,
                        profile=profile,
                        policy=model.make_policy(profile),
                    )
                )
            except (RuntimeError, ValueError) as exc:
                failures.append(
                    {
                        "seed": campaign_seed,
                        "profile_id": profile.id,
                        "error": str(exc),
                    }
                )
    rollout_evaluation = evaluate_rollouts(runs)
    return {
        "expected_runs": len(seed_list) * len(profile_list),
        "successful_runs": len(runs),
        "profile_count": len(profile_list),
        "weeks": weeks,
        "mean_reward": round(mean(r.total_reward for r in runs), 6) if runs else None,
        "mean_balance": (
            round(mean(r.final_features.get("balance", 0.0) for r in runs), 2)
            if runs else None
        ),
        "mean_wins": (
            round(mean(r.final_features.get("wins", 0.0) for r in runs), 6)
            if runs else None
        ),
        "invalid_actions": sum(r.invalid_actions for r in runs),
        "failures": failures,
        "mean_profile_action_tv": rollout_evaluation["mean_profile_action_tv"],
        "profiles": rollout_evaluation.get("profiles", {}),
    }


def promotion_decision(
    incumbent: dict[str, Any],
    challenger: dict[str, Any],
    gate: PromotionGate | None = None,
) -> dict[str, Any]:
    """Apply auditable safety and regression gates to held-out evaluations."""
    gate = gate or PromotionGate()
    incumbent_reward = incumbent.get("mean_reward")
    challenger_reward = challenger.get("mean_reward")
    incumbent_balance = incumbent.get("mean_balance")
    challenger_balance = challenger.get("mean_balance")
    incumbent_wins = incumbent.get("mean_wins")
    challenger_wins = challenger.get("mean_wins")
    required_tv = (
        float(incumbent.get("mean_profile_action_tv", 0.0)) * gate.profile_tv_ratio
        if int(challenger.get("profile_count", 0)) > 1 else 0.0
    )
    checks = {
        "incumbent_evaluation_complete": (
            incumbent.get("successful_runs") == incumbent.get("expected_runs")
            and not incumbent.get("failures")
        ),
        "all_runs_completed": (
            challenger.get("successful_runs") == challenger.get("expected_runs")
            and not challenger.get("failures")
        ),
        "zero_invalid_actions": challenger.get("invalid_actions") == 0,
        "reward_guard": (
            challenger_reward is not None
            and incumbent_reward is not None
            and challenger_reward >= incumbent_reward - gate.reward_tolerance
        ),
        "balance_guard": (
            challenger_balance is not None
            and incumbent_balance is not None
            and challenger_balance >= incumbent_balance - gate.balance_tolerance
        ),
        "wins_guard": (
            challenger_wins is not None
            and incumbent_wins is not None
            and challenger_wins >= incumbent_wins - gate.wins_tolerance
        ),
        "profile_distinctness_guard": (
            float(challenger.get("mean_profile_action_tv", 0.0)) >= required_tv
        ),
    }
    return {
        "promoted": all(checks.values()),
        "checks": checks,
        "thresholds": {**asdict(gate), "required_profile_tv": round(required_tv, 6)},
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }
