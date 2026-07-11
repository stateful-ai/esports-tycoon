"""Analyse transfer and roster decisions persisted in campaign saves.

Usage: python scripts/market_report.py SAVE_OR_DIRECTORY [--json]
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from esports_sim.manager.state import GameState  # noqa: E402


def _paths(root: Path) -> list[Path]:
    return [root] if root.is_file() else sorted(root.rglob("*.json"))


def build_report(paths: list[Path]) -> dict:
    entries = []
    loaded = 0
    for path in paths:
        try:
            gs = GameState.load(path)
        except Exception:
            continue
        loaded += 1
        entries.extend(gs.market_decisions)
    premiums = [e.org_value / e.market_value for e in entries if e.market_value > 0]
    moves = [e for e in entries if e.kind in ("transfer", "package") and e.outcome == "completed"]
    return {
        "saves_loaded": loaded,
        "decisions": len(entries),
        "completed_moves": len(moves),
        "by_kind_outcome": dict(sorted(Counter(
            f"{e.kind}:{e.outcome}" for e in entries
        ).items())),
        "by_stance": dict(sorted(Counter(e.stance or "unknown" for e in entries).items())),
        "average_org_value_multiple": round(sum(premiums) / len(premiums), 3) if premiums else 0.0,
        "pillar_moves": sum(e.stance in ("club pillar", "not for sale") for e in moves),
        "cash_bid_rejections": sum(e.kind == "bid" and e.outcome == "rejected" for e in entries),
        "fans_lost_to_departures": sum(e.effects.get("fans_lost", 0) for e in entries),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = build_report(_paths(args.path))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(f"market report: {report['saves_loaded']} saves, {report['decisions']} decisions")
    print(f"completed moves: {report['completed_moves']} (pillar moves: {report['pillar_moves']})")
    print(f"average org/market value: {report['average_org_value_multiple']:.3f}x")
    print(f"cash bids rejected: {report['cash_bid_rejections']}")
    print(f"fans lost to departures: {report['fans_lost_to_departures']:,}")
    for label, count in report["by_kind_outcome"].items():
        print(f"  {label}: {count}")
    print("stances:")
    for label, count in report["by_stance"].items():
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
