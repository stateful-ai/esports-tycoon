"""CLI for the vLLM-mode demo gate.

    python -m esports_tycoon.vllm_demo smoke [--budget <secs>]
    python -m esports_tycoon.vllm_demo preflight [fixture/decision flags]
    python -m esports_tycoon.vllm_demo status
    python -m esports_tycoon.vllm_demo sign-off --approver <founder> [--reason ...]
    python -m esports_tycoon.vllm_demo reject   --approver <founder>  --reason ...

``smoke`` is the bring-up check: one structured round-trip to the live endpoint
through the game's own client, asserting a parseable reply within a warm-latency
budget (default 5s). Run it before ``preflight`` so a down/cold server isn't
mistaken for a bad model.

``preflight`` talks to the live, env-configured local Qwen endpoint
(``GAME_LLM_*``; needs ``pip install -e .[vllm]``), runs the whole slice through
the adapter in ``vllm`` mode, measures latency, screens safety, and writes the
evidence + the founder-reviewable ``recap.md`` / ``feed.snapshot.html``. The
founder reviews those, then ``sign-off`` records the written decision. ``status``
(and the exit code of every command) answers the only question that matters: may a
vLLM-mode screenshot be shared?
"""

from __future__ import annotations

import argparse
import sys
from typing import get_args

from esports_tycoon.canned import loader
from esports_tycoon.runner import SliceConfig, SliceDecisions
from esports_tycoon.schema import PracticeFocus, TacticalStance
from esports_tycoon.vllm_demo.approval import (
    DEFAULT_RECORD_PATH,
    gate_status,
    load_record,
    record_decision,
    screenshot_allowed,
)
from esports_tycoon.vllm_demo.preflight import (
    DEFAULT_ARTIFACTS_DIR,
    load_evidence,
    run_preflight,
    verify_artifacts,
    write_preflight,
)
from esports_tycoon.vllm_demo.smoke import DEFAULT_BUDGET_SECONDS, DEFAULT_PROMPT, run_smoke

_OK = "✓"
_NO = "✗"


def _secs(value: float) -> str:
    return f"{value:.3f}s"


def _endpoint_hint() -> None:
    print(
        "    Check the local Qwen endpoint is up and GAME_LLM_* are set "
        "(and `pip install -e .[vllm]`). Bring it up with scripts/vllm_serve.sh.",
        file=sys.stderr,
    )


def _cmd_smoke(args) -> int:
    result = run_smoke(
        budget_seconds=args.budget,
        warmup=not args.no_warmup,
        prompt=args.prompt if args.prompt is not None else DEFAULT_PROMPT,
    )
    print("=" * 70)
    print(" vLLM ENDPOINT SMOKE TEST")
    print("=" * 70)
    print(f" Model    : {result.model}")
    if result.warmup_seconds is not None:
        print(f" Warm-up  : {_secs(result.warmup_seconds)} (untimed; absorbs first-request load)")
    if result.error is not None:
        print(f" Reachable: {_NO} {result.error}")
        print("=" * 70)
        print(f"{_NO} SMOKE FAILED — the endpoint did not answer.")
        _endpoint_hint()
        return 1
    print(f" Reachable: {_OK}")
    struct_mark = _OK if result.structured_ok else _NO
    print(f" Structured: {struct_mark} reply={result.reply}")
    budget_mark = _OK if result.within_budget else _NO
    print(
        f" Warm call: {budget_mark} {_secs(result.latency_seconds)} "
        f"(budget {_secs(result.budget_seconds)})"
    )
    print("=" * 70)
    if result.ok:
        print(f"{_OK} SMOKE PASSED — endpoint is up, structured, and warm under budget.")
        return 0
    if not result.structured_ok:
        print(f"{_NO} SMOKE FAILED — endpoint answered but the reply did not parse as JSON.")
    else:
        print(f"{_NO} SMOKE FAILED — warm latency {_secs(result.latency_seconds)} exceeded the "
              f"{_secs(result.budget_seconds)} budget.")
    return 1


def _cmd_preflight(args) -> int:
    world = loader.load(args.save)
    config = SliceConfig(opponent=args.opponent, map=args.map, seed=args.seed, tactical_stance=args.stance)
    try:
        decisions = SliceDecisions(
            practice_focus=args.practice, team_talk=args.team_talk, fallout_post=args.fallout
        )
    except ValueError as exc:
        print(f"{_NO} {exc}", file=sys.stderr)
        return 2

    try:
        result = run_preflight(
            world, config, decisions, latency_budget_seconds=args.max_latency
        )
    except Exception as exc:  # noqa: BLE001 — surface endpoint/dep failures plainly
        print(f"{_NO} preflight could not run the slice in vllm mode: {exc}", file=sys.stderr)
        _endpoint_hint()
        return 2

    paths = write_preflight(result, args.artifacts_dir)
    s, c = result.safety, result.safety.corpus

    print("=" * 70)
    print(" vLLM-MODE DEMO PREFLIGHT")
    print("=" * 70)
    print(f" Model    : {result.model}")
    print(f" Slice    : {result.slice_id}  (seed {config.seed}, vs {config.opponent} on {config.map})")
    print(f" Digest   : {result.digest[:16]}...")
    print("-" * 70)
    print(" Latency (measured + recorded):")
    print(f"   total slice      : {_secs(result.latency.total_seconds)}")
    print(
        f"   model calls      : {result.latency.model_calls} "
        f"({_secs(result.latency.model_seconds)} total, "
        f"{_secs(result.latency.mean_call_seconds)} mean, "
        f"{_secs(result.latency.slowest_call_seconds)} slowest)"
    )
    if result.latency.budget_seconds is not None:
        mark = _OK if result.latency.within_budget else _NO
        print(f"   budget           : {mark} <= {_secs(result.latency.budget_seconds)}")
    print(" Safety:")
    corpus_mark = _OK if c.passed else _NO
    print(f"   adversarial corpus: {corpus_mark} {c.blocked}/{c.total} blocked", end="")
    print(f" (leaks: {', '.join(c.leaks)})" if c.leaks else "")
    out_mark = _OK if not s.output_findings else _NO
    print(f"   generated output : {out_mark} {len(s.output_findings)} unsafe line(s)")
    for finding in s.output_findings:
        print(f"      - {finding.source}: {', '.join(finding.categories)}")
    print(f" Grounding : {result.grounded_ok}/{result.grounded_total} grounded lines resolved")
    print("-" * 70)
    print(f" recap : {paths['recap']}")
    print(f" feed  : {paths['feed']}")
    print(f" evidence: {paths['preflight']}")
    print("=" * 70)
    if result.gate_ready:
        print(f"{_OK} GATE READY. Review the recap/feed, then "
              f"`sign-off --approver <you>` to authorise screenshots.")
        return 0
    print(f"{_NO} GATE NOT READY — fix safety/latency above. Sign-off is blocked until green.")
    return 1


def _cmd_status(args) -> int:
    evidence = load_evidence(args.artifacts_dir)
    record = load_record(args.record)
    status = gate_status(evidence, record)

    if evidence is None:
        print(f"status        : {status['status']} (run `preflight` first)")
        return 1
    # The recap/feed files on disk are the actual screenshot surface; require them
    # to still hash to the approved digest, so an out-of-band edit can't ride it.
    artifacts_ok = verify_artifacts(evidence, args.artifacts_dir)
    allowed = screenshot_allowed(evidence, record) and artifacts_ok
    print(f"digest        : {str(evidence.get('digest'))[:16]}...")
    print(f"gate_ready    : {evidence.get('gate_ready')}")
    print(f"sign-off      : {status['status']}")
    for key in ("recorded_decision", "approver", "decided_at", "reason", "detail"):
        if status.get(key):
            print(f"{key:<14}: {status[key]}")
    print(f"artifacts     : {'verified' if artifacts_ok else 'MISMATCH (recap/feed changed on disk)'}")
    print(f"screenshots   : {'ALLOWED' if allowed else 'BLOCKED'}")
    return 0 if allowed else 1


def _cmd_decide(args, decision: str) -> int:
    evidence = load_evidence(args.artifacts_dir)
    if evidence is None:
        print(f"{_NO} no preflight evidence at {args.artifacts_dir}; run `preflight` first", file=sys.stderr)
        return 2
    if decision == "approve" and not verify_artifacts(evidence, args.artifacts_dir):
        print(
            f"{_NO} the recap/feed on disk no longer match the recorded digest; "
            f"re-run `preflight` so you sign off on the exact output you reviewed",
            file=sys.stderr,
        )
        return 1
    try:
        record = record_decision(
            evidence, decision=decision, approver=args.approver, reason=args.reason, record_path=args.record
        )
    except ValueError as exc:
        print(f"{_NO} {exc}", file=sys.stderr)
        return 1
    print(f"{_OK} recorded: {record['decision'].upper()} by {record['approver']} at {record['decided_at']}")
    print(f"   bound to digest {record['digest'][:16]}...")
    print(f"   written to {args.record}")
    if decision == "approve":
        print(f"{_OK} vLLM-mode screenshots of this preflight are now authorised.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon.vllm_demo", description=__doc__)
    parser.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACTS_DIR), help="where the preflight bundle lives")
    parser.add_argument("--record", default=str(DEFAULT_RECORD_PATH), help="path to the sign-off record")
    sub = parser.add_subparsers(dest="command", required=True)

    sm = sub.add_parser("smoke", help="bring-up check: one structured round-trip, warm latency under budget")
    sm.add_argument(
        "--budget", type=float, default=DEFAULT_BUDGET_SECONDS,
        help=f"warm-latency budget in seconds (default: {DEFAULT_BUDGET_SECONDS})",
    )
    sm.add_argument("--no-warmup", action="store_true", help="skip the warm-up call (measure a cold call)")
    sm.add_argument("--prompt", default=None, help="override the smoke prompt")

    pf = sub.add_parser("preflight", help="run + measure + screen the vllm-mode slice, write the bundle")
    pf.add_argument("--save", default=str(loader.DEFAULT_SAVE_PATH), help="path to the canned save YAML")
    pf.add_argument("--seed", type=int, default=6, help="match seed (default: 6)")
    pf.add_argument("--opponent", default="apex_foundry", help="rival org id for the week-6 fixture")
    pf.add_argument("--map", default="Helix", help="map being played (default: Helix)")
    pf.add_argument("--stance", choices=list(get_args(TacticalStance)), default="default", help="the captain's stance")
    pf.add_argument("--practice", choices=list(get_args(PracticeFocus)), default="defaults", help="the practice MC")
    pf.add_argument("--team-talk", default="", help="open-text #1: private pre-match line (<=120 chars)")
    pf.add_argument("--fallout", default="", help="open-text #2: public post-match Chirper post (<=120 chars)")
    pf.add_argument(
        "--max-latency", type=float, default=None,
        help="optional total-latency budget in seconds; unset = measured but not gated",
    )

    sub.add_parser("status", help="show the sign-off state and whether screenshots are allowed")

    for name in ("sign-off", "reject"):
        sp = sub.add_parser(name, help=f"record a {name} decision over the latest preflight")
        sp.add_argument("--approver", required=True, help="who is signing off (the founder)")
        sp.add_argument("--reason", default="", help="rationale (required for reject)")

    args = parser.parse_args(argv)

    if args.command == "smoke":
        return _cmd_smoke(args)
    if args.command == "preflight":
        return _cmd_preflight(args)
    if args.command == "status":
        return _cmd_status(args)
    if args.command == "sign-off":
        return _cmd_decide(args, "approve")
    if args.command == "reject":
        return _cmd_decide(args, "reject")
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
