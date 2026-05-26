"""CLI for the tone + cast lock gate.

    python -m esports_tycoon.cast_lock review     # one-screen batch summary
    python -m esports_tycoon.cast_lock validate   # acceptance-bar checklist
    python -m esports_tycoon.cast_lock approve --approver <founder> [--reason ...]
    python -m esports_tycoon.cast_lock reject  --approver <founder>  --reason ...
    python -m esports_tycoon.cast_lock status     # decision vs. current content
"""

from __future__ import annotations

import argparse
import sys

from .approval import (
    DEFAULT_DOC_PATH,
    DEFAULT_RECORD_PATH,
    DEFAULT_SAVE_PATH,
    approval_status,
    build_batch,
    load_record,
    record_decision,
)
from .spec import MIN_MEMORIES

_OK = "✓"
_NO = "✗"


def _print_checklist(batch) -> None:
    for c in batch.validation.checks:
        mark = _OK if c.passed else _NO
        print(f"  {mark} {c.name:<26} {c.detail}")


def _cmd_validate(batch) -> int:
    print(f"Validating {batch.save_path}\n")
    _print_checklist(batch)
    print()
    if batch.validation.ok:
        print(f"{_OK} canned save meets the M0.0 acceptance bar.")
        return 0
    print(f"{_NO} {len(batch.validation.failures)} check(s) failed.")
    return 1


def _cmd_review(batch) -> int:
    save = batch.save
    meta = save.get("save", {})
    players = save.get("players", [])
    rivals = save.get("rivals", [])
    clashes = save.get("clash_pairs", [])
    last_week = save.get("last_week", {})
    feed = last_week.get("chirper_feed", []) or []
    mem_total = sum(len(p.get("memory_log", []) or []) for p in players)

    print("=" * 70)
    print(" TONE + CAST LOCK — one batched approve/reject pass")
    print("=" * 70)
    print(f" Title : {meta.get('title')}")
    print(f" Tone  : {meta.get('tone')}    Flavor: {meta.get('flavor')} ({meta.get('game')})")
    print(f" Docs  : {batch.doc_path.name} + {batch.save_path.name}")
    print(f" Digest: {batch.digest[:16]}...")
    print("-" * 70)
    print(f" Starters ({len(players)}):")
    for p in players:
        clash = next(
            (c for c in clashes if p.get("id") in (c.get("a"), c.get("b"))),
            None,
        )
        axis = clash.get("axis") if clash else "(no clash!)"
        print(f"   - {p.get('name'):<22} {p.get('role'):<11} clash: {axis}")
    print(f" Rival archetypes ({len(rivals)}):")
    for r in rivals:
        print(f"   - {r.get('name'):<16} {r.get('archetype')}")
    print(f" Clash pairs    : {len(clashes)}")
    print(f" Memory entries : {mem_total}  (>= {MIN_MEMORIES} required)")
    sl = last_week.get("scoreline", {})
    print(
        f" Last week      : wk{last_week.get('week')} vs {last_week.get('opponent')} "
        f"{sl.get('overcast')}-{sl.get('opponent')} ({last_week.get('result')}); "
        f"{len(feed)} Chirper posts"
    )
    print("-" * 70)
    print(" Acceptance checklist:")
    _print_checklist(batch)
    print("=" * 70)
    if batch.approvable:
        print(f"{_OK} APPROVABLE. Run `approve --approver <you>` or `reject --approver <you> --reason ...`")
        return 0
    print(f"{_NO} NOT APPROVABLE — fix the failing checks first.")
    return 1


def _cmd_decide(batch, decision: str, approver: str, reason: str, record_path) -> int:
    try:
        record = record_decision(
            batch, decision=decision, approver=approver, reason=reason, record_path=record_path
        )
    except ValueError as exc:
        print(f"{_NO} {exc}", file=sys.stderr)
        return 1
    print(f"{_OK} recorded: {record['decision'].upper()} by {record['approver']} at {record['decided_at']}")
    print(f"   bound to batch digest {record['batch_digest'][:16]}...")
    print(f"   written to {record_path}")
    return 0


def _cmd_status(batch, record_path) -> int:
    record = load_record(record_path)
    status = approval_status(batch, record)
    print(f"batch digest : {batch.digest[:16]}...")
    print(f"status       : {status['status']}")
    for key in ("recorded_decision", "approver", "decided_at", "reason", "detail"):
        if status.get(key):
            print(f"{key:<13}: {status[key]}")
    return 0 if status.get("approved") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon.cast_lock", description=__doc__)
    parser.add_argument("--save", default=str(DEFAULT_SAVE_PATH), help="path to the canned save YAML")
    parser.add_argument("--doc", default=str(DEFAULT_DOC_PATH), help="path to the tone 1-pager")
    parser.add_argument("--record", default=str(DEFAULT_RECORD_PATH), help="path to the approval record")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="print the acceptance-bar checklist")
    sub.add_parser("review", help="print the one-screen batch summary")
    sub.add_parser("status", help="show the recorded decision vs current content")
    for name in ("approve", "reject"):
        sp = sub.add_parser(name, help=f"record a {name} decision over the whole batch")
        sp.add_argument("--approver", required=True, help="who is making the call (the founder)")
        sp.add_argument("--reason", default="", help="rationale (required for reject)")

    args = parser.parse_args(argv)
    batch = build_batch(save_path=args.save, doc_path=args.doc)

    if args.command == "validate":
        return _cmd_validate(batch)
    if args.command == "review":
        return _cmd_review(batch)
    if args.command == "status":
        return _cmd_status(batch, args.record)
    if args.command in ("approve", "reject"):
        return _cmd_decide(batch, args.command, args.approver, args.reason, args.record)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
