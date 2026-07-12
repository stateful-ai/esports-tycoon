"""Improve a learned manager checkpoint with simulated rewards.

The candidate is always written for inspection. The champion path is written
only when the candidate passes held-out safety and regression gates.

Usage:
    python scripts/online_train_manager_policy.py BASE_CHECKPOINT [options]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from esports_sim.manager.learned_manager_policy import LearnedManagerModel
from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.online_manager_learning import (
    OnlineLearningConfig,
    evaluate_model,
    fine_tune_online,
    promotion_decision,
)
from esports_sim.registry import load_all


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_checkpoint", type=Path)
    parser.add_argument("--train-seeds", type=int, default=4)
    parser.add_argument("--eval-seeds", type=int, default=4)
    parser.add_argument("--profiles", type=int, default=4)
    parser.add_argument("--weeks", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    parser.add_argument("--temperature", type=float, default=1.1)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--champion", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if min(
        args.train_seeds,
        args.eval_seeds,
        args.profiles,
        args.weeks,
        args.iterations,
    ) <= 0:
        print("seed counts, profiles, weeks, and iterations must be positive")
        return 2
    if not args.base_checkpoint.is_file():
        print(f"base checkpoint does not exist: {args.base_checkpoint}")
        return 2

    candidate_path = args.candidate or args.base_checkpoint.with_name(
        args.base_checkpoint.stem + ".candidate.json"
    )
    champion_path = args.champion or args.base_checkpoint.with_name(
        args.base_checkpoint.stem + ".champion.json"
    )
    report_path = args.report or args.base_checkpoint.with_name(
        args.base_checkpoint.stem + ".online-report.json"
    )
    train_seeds = list(range(30_001, 30_001 + args.train_seeds))
    eval_seeds = list(range(40_001, 40_001 + args.eval_seeds))
    profiles = [
        generate_profile(50_000 + i, f"online-manager-{i + 1}")
        for i in range(args.profiles)
    ]
    gd = load_all()
    incumbent = LearnedManagerModel.load(args.base_checkpoint)
    config = OnlineLearningConfig(
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        temperature=args.temperature,
    )
    print(
        f"training challenger: {len(train_seeds)} seeds, {len(profiles)} profiles, "
        f"{args.weeks} weeks, {args.iterations} iterations"
    )
    challenger, training = fine_tune_online(
        gd,
        incumbent,
        seeds=train_seeds,
        profiles=profiles,
        weeks=args.weeks,
        config=config,
    )
    print(f"evaluating champion and challenger on {len(eval_seeds)} held-out seeds")
    incumbent_eval = evaluate_model(
        gd, incumbent, seeds=eval_seeds, profiles=profiles, weeks=args.weeks
    )
    challenger_eval = evaluate_model(
        gd, challenger, seeds=eval_seeds, profiles=profiles, weeks=args.weeks
    )
    promotion = promotion_decision(incumbent_eval, challenger_eval)
    report = {
        "base_checkpoint": str(args.base_checkpoint),
        "candidate_checkpoint": str(candidate_path),
        "champion_checkpoint": str(champion_path),
        "train_seeds": train_seeds,
        "evaluation_seeds": eval_seeds,
        "training": training,
        "incumbent_evaluation": incumbent_eval,
        "challenger_evaluation": challenger_eval,
        "promotion": promotion,
        "champion_written": bool(promotion["promoted"]),
    }
    challenger.save(candidate_path, metadata={"online_evaluation": report})
    if promotion["promoted"]:
        challenger.save(champion_path, metadata={"online_evaluation": report})
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    status = "PROMOTED" if promotion["promoted"] else "REJECTED"
    print(
        f"{status}: incumbent reward={incumbent_eval['mean_reward']}, "
        f"challenger reward={challenger_eval['mean_reward']}"
    )
    if promotion["failed_checks"]:
        print("failed gates: " + ", ".join(promotion["failed_checks"]))
    print(f"candidate: {candidate_path}")
    print(f"report: {report_path}")
    if promotion["promoted"]:
        print(f"champion: {champion_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
