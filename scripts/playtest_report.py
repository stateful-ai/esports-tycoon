"""Merge every synthetic player's findings into one prioritised report.

    python scripts/playtest_report.py                       # all runs
    python scripts/playtest_report.py --out runs/report.md  # write it down
    python scripts/playtest_report.py --gate blocker        # exit 1 on blockers

One persona's opinion is taste; three personas hitting the same wall is a bug
report. The report groups on (severity, area, title) and prints the count and
who hit it, so corroboration is visible at a glance rather than buried in five
separate files.

`--gate` makes this usable in CI: pass the worst severity you are willing to
ship with, and the script exits non-zero if anything at or above it survives.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from esports_sim.playtest.findings import (  # noqa: E402
    SEVERITIES,
    aggregate,
    load_all,
    render_report,
)

DEFAULT_ROOT = REPO_ROOT / "runs" / "synthetic-players"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT,
                        help=f"directory of persona runs (default: {DEFAULT_ROOT})")
    parser.add_argument("--out", type=Path, default=None, help="write the Markdown here too")
    parser.add_argument("--title", default="Synthetic playtest report")
    parser.add_argument(
        "--gate", choices=SEVERITIES, default=None,
        help="exit 1 if any finding at or above this severity survived",
    )
    args = parser.parse_args()

    findings = load_all(args.root)
    report = render_report(findings, title=args.title)
    print(report)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"wrote {args.out}")

    if args.gate is not None:
        limit = SEVERITIES.index(args.gate)
        offenders = [g for g in aggregate(findings) if SEVERITIES.index(g["severity"]) <= limit]
        if offenders:
            print(f"\nFAIL {len(offenders)} finding(s) at or above '{args.gate}':")
            for group in offenders:
                print(f"  [{group['severity']}/{group['area']}] {group['title']}")
            return 1
        print(f"\nOK nothing at or above '{args.gate}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
