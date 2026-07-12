"""Deterministic batch rollouts and exports for manager-policy training."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv, InvalidManagerAction
from esports_sim.manager.manager_policy import (
    HeuristicManagerPolicy,
    ManagerProfile,
    generate_profile,
)
from esports_sim.registry import GameData


@dataclass
class RolloutResult:
    run_id: str
    seed: int
    profile_id: str
    profile: dict[str, float]
    policy_version: str
    weeks: int
    total_reward: float
    invalid_actions: int
    action_counts: dict[str, int]
    behavior_counts: dict[str, int]
    final_features: dict[str, float]
    traces: list[dict[str, Any]]

    def summary(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("traces")
        return out


def run_rollout(
    gd: GameData,
    *,
    seed: int,
    weeks: int,
    profile: ManagerProfile | None = None,
    user_team_id: str = "team_nexus",
    max_decisions_per_week: int = 16,
) -> RolloutResult:
    """Run one reproducible manager episode and retain decision-time traces."""
    profile = profile or generate_profile(seed, f"manager-{seed}")
    policy = HeuristicManagerPolicy(profile)
    traces: list[dict[str, Any]] = []
    gs = new_campaign(gd, seed=seed, user_team_id=user_team_id)
    env = HeadlessManagerEnv(
        gs,
        gd,
        user_team_id,
        manager_profile=profile.to_dict(),
        trace_sink=traces.append,
        policy_version=policy.version,
    )
    rewards: list[float] = []
    invalid = 0
    advanced = 0
    decisions_this_week = 0
    while advanced < weeks:
        obs = env.observe()
        action = policy.choose_action(obs)
        try:
            result = env.step(action)
        except InvalidManagerAction as exc:
            invalid += 1
            traces.append(
                {
                    "trace_version": 1,
                    "policy_version": policy.version,
                    "season": obs["season"],
                    "week": obs["week"],
                    "team_id": obs["team_id"],
                    "manager_profile": profile.to_dict(),
                    "observation": obs,
                    "action": action,
                    "reward": 0.0,
                    "reward_components": {},
                    "advanced": False,
                    "done": False,
                    "message": str(exc),
                    "invalid": True,
                }
            )
            result = None
        decisions_this_week += 1
        if result is not None and result.advanced:
            advanced += 1
            rewards.append(result.reward)
            decisions_this_week = 0
        elif decisions_this_week >= max_decisions_per_week:
            raise RuntimeError(
                f"policy failed to advance after {max_decisions_per_week} decisions "
                f"in season {gs.season} week {gs.week}"
            )
    final = env.observe()["features"]
    counts = Counter(t["action"]["kind"] for t in traces)
    behavior = Counter(_behavior_token(t) for t in traces)
    return RolloutResult(
        run_id=f"seed-{seed}-{profile.id}",
        seed=seed,
        profile_id=profile.id,
        profile=profile.to_dict(),
        policy_version=policy.version,
        weeks=weeks,
        total_reward=round(sum(rewards), 4),
        invalid_actions=invalid,
        action_counts=dict(sorted(counts.items())),
        behavior_counts=dict(sorted(behavior.items())),
        final_features=final,
        traces=traces,
    )


def run_batch(
    gd: GameData,
    seeds: Iterable[int],
    profiles: Iterable[ManagerProfile],
    *,
    weeks: int,
) -> list[RolloutResult]:
    return [
        run_rollout(gd, seed=seed, weeks=weeks, profile=profile)
        for profile in profiles
        for seed in seeds
    ]


def _bucket(value: object) -> str:
    number = float(value)
    return "low" if number < 40 else "high" if number > 60 else "mid"


def _behavior_token(trace: dict[str, Any]) -> str:
    action = trace["action"]
    kind = action["kind"]
    params = action.get("params", {})
    if kind == "set_training":
        return f"{kind}:{params.get('focus', '')}"
    if kind == "set_tactics":
        return (
            f"{kind}:agg-{_bucket(params.get('aggression', 50))}:"
            f"pace-{_bucket(params.get('pace', 50))}:"
            f"util-{_bucket(params.get('util_discipline', 50))}"
        )
    if kind == "set_scout":
        target = str(params.get("target", ""))
        category = "market" if target == "market" else target.split(":", 1)[0]
        return f"{kind}:{category}"
    for field in ("facility", "structure", "dev_focus", "team_talk", "option_id"):
        if field in params and params[field]:
            return f"{kind}:{params[field]}"
    return kind


def _behavior_distribution(result: RolloutResult, vocabulary: list[str]) -> list[float]:
    total = max(sum(result.behavior_counts.values()), 1)
    return [result.behavior_counts.get(token, 0) / total for token in vocabulary]


def evaluate_rollouts(results: list[RolloutResult]) -> dict[str, Any]:
    """Summarize competence and profile-level behavioral distinctness."""
    if not results:
        return {"runs": 0, "profiles": {}, "mean_profile_action_tv": 0.0}
    by_profile: dict[str, list[RolloutResult]] = {}
    for result in results:
        by_profile.setdefault(result.profile_id, []).append(result)
    profiles = {
        pid: {
            "runs": len(rows),
            "mean_reward": round(mean(r.total_reward for r in rows), 4),
            "mean_balance": round(mean(r.final_features.get("balance", 0.0) for r in rows), 2),
            "mean_wins": round(mean(r.final_features.get("wins", 0.0) for r in rows), 3),
            "invalid_actions": sum(r.invalid_actions for r in rows),
            "action_counts": dict(
                sorted(sum((Counter(r.action_counts) for r in rows), Counter()).items())
            ),
            "behavior_counts": dict(
                sorted(sum((Counter(r.behavior_counts) for r in rows), Counter()).items())
            ),
        }
        for pid, rows in sorted(by_profile.items())
    }
    vocabulary = sorted({token for r in results for token in r.behavior_counts})
    profile_distributions: dict[str, list[float]] = {}
    for pid, rows in sorted(by_profile.items()):
        vectors = [_behavior_distribution(r, vocabulary) for r in rows]
        profile_distributions[pid] = [mean(values) for values in zip(*vectors)]
    distances = []
    ids = sorted(profile_distributions)
    for i, left in enumerate(ids):
        for right in ids[i + 1:]:
            distances.append(
                0.5 * sum(
                    abs(a - b)
                    for a, b in zip(profile_distributions[left], profile_distributions[right])
                )
            )
    return {
        "runs": len(results),
        "profiles": profiles,
        "mean_profile_action_tv": round(mean(distances), 4) if distances else 0.0,
    }


def export_rollouts(results: list[RolloutResult], stem: Path) -> dict[str, Path]:
    """Write training traces, run summaries, and aggregate evaluation."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = {
        "traces": stem.with_name(stem.name + ".traces.jsonl"),
        "runs": stem.with_name(stem.name + ".runs.jsonl"),
        "evaluation": stem.with_name(stem.name + ".evaluation.json"),
    }
    with paths["traces"].open("w", encoding="utf-8") as f:
        for result in results:
            for trace in result.traces:
                f.write(json.dumps({"run_id": result.run_id, **trace}, sort_keys=True) + "\n")
    with paths["runs"].open("w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result.summary(), sort_keys=True) + "\n")
    paths["evaluation"].write_text(
        json.dumps(evaluate_rollouts(results), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths
