"""Append player-intent observations without adding wall-clock data to GameState.

Run from the repository root. See .claude/skills/playtest-log/SKILL.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "docs" / "playtests"
FIELDS = [
    "session_id", "step", "started_at_utc", "finished_at_utc", "commit",
    "working_tree_dirty", "game_version", "model", "effort", "surface",
    "world_code", "seed", "game_time", "intent", "action", "expected_outcome",
    "actual_outcome", "result", "evidence", "analytics_status", "analytics_evidence",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["begin", "finish"])
    parser.add_argument("--session", required=True)
    parser.add_argument("--step", required=True, type=int)
    for field in ["model", "effort", "surface", "world-code", "seed", "game-time",
                  "intent", "action", "expected-outcome", "actual-outcome", "result",
                  "evidence", "analytics-status", "analytics-evidence"]:
        parser.add_argument("--" + field, default="")
    args = parser.parse_args()
    if args.step < 1 or not all(c.isalnum() or c in "-_" for c in args.session):
        parser.error("use a positive step and an alphanumeric/hyphen/underscore session id")
    pending = ROOT / "runs" / "playtests" / args.session / f"pending-{args.step}.json"
    log = LOG_DIR / "actions.csv"
    if args.operation == "begin":
        if pending.exists():
            parser.error("this step already has a pending intention")
        if not all([args.model, args.effort, args.surface, args.intent, args.action, args.expected_outcome]):
            parser.error("begin requires model, effort, surface, intent, action, expected-outcome")
        row = dict.fromkeys(FIELDS, "")
        row.update({k: getattr(args, k) for k in FIELDS if hasattr(args, k)})
        row["session_id"] = args.session
        row["started_at_utc"] = now()
        row["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        row["working_tree_dirty"] = str(bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())).lower()
        row["game_version"] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(json.dumps(row, indent=2), encoding="utf-8")
    else:
        if not args.actual_outcome or args.result not in {"met", "partial", "unexpected", "blocked"}:
            parser.error("finish requires actual-outcome and result: met/partial/unexpected/blocked")
        row = json.loads(pending.read_text(encoding="utf-8"))
        for field in ["actual_outcome", "result", "evidence", "analytics_status", "analytics_evidence", "world_code"]:
            if getattr(args, field):
                row[field] = getattr(args, field)
        row["finished_at_utc"] = now()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        exists = log.exists() and log.stat().st_size > 0
        if exists:
            with log.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != FIELDS:
                    parser.error("CSV schema mismatch; migrate explicitly instead of corrupting history")
                if any(r["session_id"] == args.session and r["step"] == str(args.step) for r in reader):
                    parser.error("session/step already logged")
        with log.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(row)
        pending.unlink()
    print(f"{args.operation}: {args.session} step {args.step}")


if __name__ == "__main__":
    main()
