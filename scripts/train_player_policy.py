"""Train the dependency-light learned player policy from heuristic matches."""

from __future__ import annotations

import argparse
from pathlib import Path

from esports_sim.policy.learned import (
    LearnedPlayerModel,
    RecordingPlayerPolicy,
    imitation_metrics,
)
from esports_sim.registry import load_all
from esports_sim.sim.engine import MatchPolicies, simulate_match_result
from esports_sim.policy.heuristic import HeuristicPolicy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--map", dest="map_id", default="haven")
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--max-traces", type=int, default=5_000)
    args = parser.parse_args()
    if args.seeds < 1 or args.max_traces < 1:
        parser.error("--seeds and --max-traces must be positive")

    gd = load_all()
    teams = sorted(gd.teams)
    if len(teams) < 2:
        raise SystemExit("at least two teams are required")
    if args.map_id not in gd.maps:
        raise SystemExit(f"unknown map: {args.map_id}")

    recorder = RecordingPlayerPolicy(HeuristicPolicy(gd, gd.maps[args.map_id]))
    policies = MatchPolicies(
        player_by_id={player_id: recorder for player_id in gd.players},
        communication_by_id={player_id: recorder for player_id in gd.players},
    )
    for seed in range(args.seeds):
        simulate_match_result(
            gd,
            teams[0],
            teams[1],
            args.map_id,
            seed,
            policies=policies,
        )
    traces = recorder.traces[: args.max_traces]
    model = LearnedPlayerModel.train(traces, recorder.communication_traces)
    model.save(args.output)
    metrics = imitation_metrics(model, traces)
    print(f"saved: {args.output}")
    print(f"action examples: {len(traces)}")
    print(f"communication examples: {model.communication_examples}")
    print(f"action accuracy: {metrics['action_accuracy']:.1%}")
    print(f"legal rate: {metrics['legal_rate']:.1%}")


if __name__ == "__main__":
    main()
