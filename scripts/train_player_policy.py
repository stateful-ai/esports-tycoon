"""Generate expert match data and train the learned player policy.

Train and validation matches use disjoint seeds.  ``--map all`` builds a
cross-map corpus; ``--dataset`` preserves the typed decisions as JSONL for
later model experiments without putting research artifacts in Git.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from esports_sim.policy.heuristic import HeuristicPolicy
from esports_sim.policy.learned import (
    CommunicationDecisionTraceV1,
    LearnedPlayerModel,
    PlayerDecisionTraceV1,
    RecordingPlayerPolicy,
    communication_imitation_metrics,
    imitation_metrics,
)
from esports_sim.registry import load_all
from esports_sim.sim.engine import MatchPolicies, simulate_match_result


ActionRow = tuple[str, int, PlayerDecisionTraceV1]
CommunicationRow = tuple[str, int, CommunicationDecisionTraceV1]


def _maps(value: str, available: Iterable[str]) -> list[str]:
    known = sorted(available)
    requested = known if value == "all" else [part.strip() for part in value.split(",")]
    unknown = sorted(set(requested) - set(known))
    if unknown:
        raise ValueError(f"unknown map(s): {', '.join(unknown)}")
    return requested


def _even_sample(rows: list[Any], limit: int) -> list[Any]:
    """Deterministically cover the whole corpus rather than its first match."""
    if len(rows) <= limit:
        return rows
    indices = np.linspace(0, len(rows) - 1, num=limit, dtype=int)
    return [rows[int(index)] for index in indices]


def _generate(
    map_ids: list[str], seeds: range
) -> tuple[list[ActionRow], list[CommunicationRow]]:
    gd = load_all()
    teams = sorted(gd.teams)
    if len(teams) < 2:
        raise ValueError("at least two teams are required")
    actions: list[ActionRow] = []
    communications: list[CommunicationRow] = []
    for map_id in map_ids:
        for seed in seeds:
            recorder = RecordingPlayerPolicy(HeuristicPolicy(gd, gd.maps[map_id]))
            policies = MatchPolicies(
                player_by_id={player_id: recorder for player_id in gd.players},
                communication_by_id={player_id: recorder for player_id in gd.players},
            )
            simulate_match_result(
                gd,
                teams[0],
                teams[1],
                map_id,
                seed,
                policies=policies,
            )
            actions.extend((map_id, seed, trace) for trace in recorder.traces)
            communications.extend(
                (map_id, seed, trace) for trace in recorder.communication_traces
            )
    return actions, communications


def _write_dataset(
    path: Path,
    train_actions: list[ActionRow],
    validation_actions: list[ActionRow],
    train_comms: list[CommunicationRow],
    validation_comms: list[CommunicationRow],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for split, kind, rows in (
            ("train", "action", train_actions),
            ("validation", "action", validation_actions),
            ("train", "communication", train_comms),
            ("validation", "communication", validation_comms),
        ):
            for map_id, seed, trace in rows:
                payload = {
                    "split": split,
                    "kind": kind,
                    "map_id": map_id,
                    "seed": seed,
                    "trace": trace.model_dump(mode="json"),
                }
                handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--map",
        dest="map_id",
        default="all",
        help="map id, comma-separated ids, or 'all' (default)",
    )
    parser.add_argument("--seeds", type=int, default=4, help="training seeds")
    parser.add_argument("--validation-seeds", type=int, default=2)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--max-traces", type=int, default=10_000)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.seeds < 1 or args.validation_seeds < 1 or args.max_traces < 1:
        parser.error("--seeds, --validation-seeds, and --max-traces must be positive")

    gd = load_all()
    try:
        map_ids = _maps(args.map_id, gd.maps)
    except ValueError as error:
        parser.error(str(error))
    train_seeds = range(args.seed_offset, args.seed_offset + args.seeds)
    validation_seeds = range(train_seeds.stop, train_seeds.stop + args.validation_seeds)

    train_actions, train_comms = _generate(map_ids, train_seeds)
    validation_actions, validation_comms = _generate(map_ids, validation_seeds)
    sampled_actions = _even_sample(train_actions, args.max_traces)
    model = LearnedPlayerModel.train(
        [row[2] for row in sampled_actions],
        [row[2] for row in train_comms],
    )
    model.save(args.output)

    train_metrics = imitation_metrics(model, [row[2] for row in train_actions])
    validation_metrics = imitation_metrics(
        model, [row[2] for row in validation_actions]
    )
    communication_metrics = communication_imitation_metrics(
        model, [row[2] for row in validation_comms]
    )
    report = {
        "maps": map_ids,
        "train_seeds": list(train_seeds),
        "validation_seeds": list(validation_seeds),
        "generated_action_examples": len(train_actions),
        "sampled_action_examples": len(sampled_actions),
        "generated_communication_examples": len(train_comms),
        "validation_action_examples": len(validation_actions),
        "validation_communication_examples": len(validation_comms),
        "imitation_train": train_metrics,
        "imitation_validation": validation_metrics,
        "communication_validation": communication_metrics,
    }
    report_path = args.report or args.output.with_suffix(".report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.dataset is not None:
        _write_dataset(
            args.dataset,
            train_actions,
            validation_actions,
            train_comms,
            validation_comms,
        )

    print(f"saved: {args.output}")
    print(f"report: {report_path}")
    if args.dataset is not None:
        print(f"dataset: {args.dataset}")
    print(f"maps: {', '.join(map_ids)}")
    print(
        f"action examples: {len(train_actions)} generated / "
        f"{len(sampled_actions)} trained / {len(validation_actions)} validation"
    )
    print(
        "validation accuracy: "
        f"{float(validation_metrics['action_accuracy']):.1%} "
        f"(majority baseline {float(validation_metrics['majority_baseline']):.1%})"
    )
    print(
        "validation tactical recall: "
        f"{float(validation_metrics['macro_action_recall']):.1%} macro / "
        f"{float(validation_metrics['non_hold_accuracy']):.1%} non-hold"
    )
    print(
        "learned stochastic action rate: "
        f"{float(validation_metrics['expected_non_hold_rate']):.1%} non-hold"
    )
    print(f"legal rate: {float(validation_metrics['legal_rate']):.1%}")


if __name__ == "__main__":
    main()
