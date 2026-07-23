"""Run an LLM through the manager-visible campaign contract.

Usage:
    python scripts/run_llm_playtest.py --seasons 1
    python scripts/run_llm_playtest.py --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen2.5-14B-Instruct-AWQ --seasons 1

Without --base-url the provider resolves like the social writer does
(--provider auto): OpenRouter when OPENROUTER_API_KEY is in .env, else a
local OpenAI-compatible server. A dead localhost provider falls back to
OpenRouter when a key exists, so a stale START_VLLM flag cannot strand a run.

Artifacts contain every model-facing observation, raw reply, resolved action,
and a final critique.  A non-zero invalid_responses count means the model did
not meet the no-illegal-actions acceptance gate, even though the harness used
a legal recovery action to finish the diagnostic run.  Traces stream to disk
as they happen, so a crash mid-run keeps everything up to that decision.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from esports_sim.manager.llm_playtest import OpenAICompatibleClient, run_llm_playtest, write_artifacts
from esports_sim.registry import load_all

DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"


def _port_open(url: str, timeout: float = 1.5) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_provider(args: argparse.Namespace) -> tuple[str, str, str | None]:
    """Return (base_url, model, api_key). Explicit --base-url wins outright."""
    if args.base_url:
        if not args.model:
            raise SystemExit("--model is required with --base-url")
        return args.base_url, args.model, args.api_key
    from esports_sim.web.llm_social import _load_env, provider

    _load_env()
    if args.provider == "openrouter":
        key = args.api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY is required for --provider openrouter")
        model = args.model or os.environ.get("SOCIAL_LLM_MODEL", DEFAULT_OPENROUTER_MODEL)
        return "https://openrouter.ai/api/v1", model, key
    cfg = provider()
    if cfg is None:
        raise SystemExit(
            "no LLM provider available: pass --base-url/--model or set OPENROUTER_API_KEY"
        )
    base = cfg["url"].removesuffix("/chat/completions")
    # A stale START_VLLM/SOCIAL_LLM_BASE_URL can resolve to a server that is
    # not actually running; prefer OpenRouter over a guaranteed dead socket.
    if not _port_open(base):
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key:
            model = args.model or os.environ.get("SOCIAL_LLM_MODEL", DEFAULT_OPENROUTER_MODEL)
            print(f"provider at {base} is not reachable; falling back to OpenRouter")
            return "https://openrouter.ai/api/v1", model, key
        raise SystemExit(f"provider at {base} is not reachable and no OPENROUTER_API_KEY is set")
    return base, args.model or cfg["model"], (args.api_key or cfg["key"] or None)


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM manager playtest harness")
    parser.add_argument("--provider", choices=("auto", "openrouter"), default="auto")
    parser.add_argument("--base-url", default=os.environ.get("LLM_PLAYTEST_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("LLM_PLAYTEST_MODEL"))
    parser.add_argument("--api-key", default=os.environ.get("LLM_PLAYTEST_API_KEY"))
    parser.add_argument("--seed", type=int, default=2026)
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--weeks", type=int)
    duration.add_argument("--seasons", type=int, default=1)
    parser.add_argument("--team", default="team_nexus")
    parser.add_argument("--output", type=Path, default=Path("runs/llm_playtests"))
    parser.add_argument(
        "--critique-each-season", action="store_true",
        help="ask the model for a short critique at every season rollover",
    )
    args = parser.parse_args()
    if (args.weeks is not None and args.weeks < 1) or args.seasons < 1:
        parser.error("--weeks and --seasons must be positive")

    base_url, model, api_key = _resolve_provider(args)
    print(f"provider: {base_url} model: {model}")

    args.output.mkdir(parents=True, exist_ok=True)
    stream_path = args.output / f"llm-playtest-seed-{args.seed}.traces.jsonl"
    stream = stream_path.open("w", encoding="utf-8")

    def trace_sink(trace: dict) -> None:
        stream.write(json.dumps(trace, sort_keys=True) + "\n")
        stream.flush()

    try:
        result = run_llm_playtest(
            load_all(),
            OpenAICompatibleClient(base_url, model, api_key),
            seed=args.seed,
            weeks=args.weeks,
            seasons=args.seasons if args.weeks is None else None,
            user_team_id=args.team,
            trace_sink=trace_sink,
            critique_each_season=args.critique_each_season,
        )
    finally:
        stream.close()
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
