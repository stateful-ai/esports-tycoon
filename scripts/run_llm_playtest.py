"""Run an LLM through the manager-visible campaign contract.

Usage:
    python scripts/run_llm_playtest.py --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen2.5-14B-Instruct-AWQ --seasons 1

Artifacts contain every model-facing observation, raw reply, resolved action,
and a final critique.  A non-zero invalid_responses count means the model did
not meet the no-illegal-actions acceptance gate, even though the harness used
a legal recovery action to finish the diagnostic run.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from esports_sim.manager.llm_playtest import OpenAICompatibleClient, run_llm_playtest, write_artifacts
from esports_sim.registry import load_all


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM manager playtest harness")
    parser.add_argument("--base-url", default=os.environ.get("LLM_PLAYTEST_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("LLM_PLAYTEST_MODEL"))
    parser.add_argument("--api-key", default=os.environ.get("LLM_PLAYTEST_API_KEY"))
    parser.add_argument("--seed", type=int, default=2026)
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--weeks", type=int)
    duration.add_argument("--seasons", type=int, default=1)
    parser.add_argument("--team", default="team_nexus")
    parser.add_argument("--output", type=Path, default=Path("runs/llm_playtests"))
    args = parser.parse_args()
    if not args.base_url or not args.model:
        parser.error("--base-url and --model (or LLM_PLAYTEST_* environment variables) are required")
    if (args.weeks is not None and args.weeks < 1) or args.seasons < 1:
        parser.error("--weeks and --seasons must be positive")

    result = run_llm_playtest(
        load_all(),
        OpenAICompatibleClient(args.base_url, args.model, args.api_key),
        seed=args.seed,
        weeks=args.weeks,
        seasons=args.seasons if args.weeks is None else None,
        user_team_id=args.team,
    )
    paths = write_artifacts(result, args.output)
    duration_label = (
        f"{result.seasons_completed} seasons"
        if result.seasons_requested else f"{result.weeks} weeks"
    )
    print(f"LLM playtest: {duration_label}, {result.decisions} decisions, "
          f"{result.invalid_responses} invalid replies, reward {result.total_reward:+.3f}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0 if result.invalid_responses == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
