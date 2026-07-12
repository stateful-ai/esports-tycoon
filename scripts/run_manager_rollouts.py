"""Run deterministic profile-conditioned manager rollouts.

Usage:
    python scripts/run_manager_rollouts.py [seeds] [profiles] [weeks] [out-stem]

Defaults: 2 seeds, 3 generated profiles, 4 weeks, telemetry/manager_rollouts.
"""

from __future__ import annotations

import sys
from pathlib import Path

from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.rollout import evaluate_rollouts, export_rollouts, run_batch
from esports_sim.registry import load_all


def main() -> int:
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n_profiles = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    weeks = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    stem = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("telemetry/manager_rollouts")
    if min(n_seeds, n_profiles, weeks) <= 0:
        print("seeds, profiles, and weeks must all be positive")
        return 2

    gd = load_all()
    seeds = list(range(1, n_seeds + 1))
    profiles = [generate_profile(10_000 + i, f"manager-{i + 1}") for i in range(n_profiles)]
    results = run_batch(gd, seeds, profiles, weeks=weeks)
    paths = export_rollouts(results, stem)
    evaluation = evaluate_rollouts(results)
    print(
        f"exported {len(results)} runs, "
        f"{sum(len(r.traces) for r in results)} decisions; "
        f"profile action TV={evaluation['mean_profile_action_tv']:.3f}"
    )
    for label, path in paths.items():
        print(f"  {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
