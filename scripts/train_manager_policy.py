"""Generate simulation demonstrations and train the first learned manager policy.

Usage:
    python scripts/train_manager_policy.py [train-seeds] [val-seeds] [profiles]
                                           [weeks] [checkpoint]

Defaults: 4 training seeds, 2 disjoint validation seeds, 4 profiles, 3 weeks,
telemetry/manager_policy_v1.json.

Contract-growth note: the decision contract only ever GROWS additively
(``OBSERVATION_VERSION`` stays put; checkpoints store their own action
vocabulary), so existing checkpoints and recorded traces keep working when
new action kinds land — an old checkpoint simply never emits them. To teach
a policy the newer actions (e.g. the transfer-market kinds ``bid``,
``buyout``, ``transfer_offer``, ``assignment``, ``igl``), rerun this script:
a fresh train picks up the full current vocabulary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from esports_sim.manager.learned_manager_policy import (
    LearnedManagerModel,
    imitation_metrics,
)
from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.rollout import evaluate_rollouts, export_rollouts, run_batch, run_rollout
from esports_sim.registry import load_all


def main() -> int:
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n_val = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    n_profiles = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    weeks = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    checkpoint = (
        Path(sys.argv[5]) if len(sys.argv) > 5
        else Path("telemetry/manager_policy_v1.json")
    )
    if min(n_train, n_val, n_profiles, weeks) <= 0:
        print("train seeds, validation seeds, profiles, and weeks must be positive")
        return 2

    train_seeds = list(range(1, n_train + 1))
    val_seeds = list(range(10_001, 10_001 + n_val))
    if set(train_seeds) & set(val_seeds):
        print("training and validation campaign seeds must be disjoint")
        return 2
    profiles = [
        generate_profile(20_000 + i, f"manager-{i + 1}")
        for i in range(n_profiles)
    ]
    gd = load_all()
    print(
        f"generating demonstrations: {n_train} train seeds, {n_val} validation "
        f"seeds, {n_profiles} profiles, {weeks} weeks"
    )
    train_runs = run_batch(gd, train_seeds, profiles, weeks=weeks)
    val_runs = run_batch(gd, val_seeds, profiles, weeks=weeks)
    train_traces = [trace for run in train_runs for trace in run.traces]
    val_traces = [trace for run in val_runs for trace in run.traces]

    model = LearnedManagerModel.train(train_traces)
    train_metrics = imitation_metrics(model, train_traces)
    val_metrics = imitation_metrics(model, val_traces)
    learned_runs = [
        run_rollout(
            gd,
            seed=seed,
            weeks=weeks,
            profile=profile,
            policy=model.make_policy(profile),
        )
        for profile in profiles
        for seed in val_seeds
    ]
    baseline_eval = evaluate_rollouts(val_runs)
    learned_eval = evaluate_rollouts(learned_runs)
    metrics = {
        "train_seeds": train_seeds,
        "validation_seeds": val_seeds,
        "profiles": [profile.id for profile in profiles],
        "weeks": weeks,
        "imitation_train": train_metrics,
        "imitation_validation": val_metrics,
        "baseline_evaluation": baseline_eval,
        "learned_evaluation": learned_eval,
    }
    model.save(checkpoint, metadata=metrics)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    metrics_path = checkpoint.with_name(checkpoint.stem + ".metrics.json")
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    export_rollouts(train_runs, checkpoint.with_name(checkpoint.stem + ".train"))
    export_rollouts(val_runs, checkpoint.with_name(checkpoint.stem + ".validation"))
    print(
        f"trained {model.metadata['training_examples']} examples; "
        f"train accuracy={train_metrics['action_accuracy']:.3f}; "
        f"validation accuracy={val_metrics['action_accuracy']:.3f}; "
        f"learned invalid actions="
        f"{sum(run.invalid_actions for run in learned_runs)}"
    )
    print(f"checkpoint: {checkpoint}")
    print(f"metrics: {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
