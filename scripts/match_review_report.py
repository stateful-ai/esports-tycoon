"""Mine the match-review corpus: what does a win look like vs a loss?

Reads saves/match_review_<code>.jsonl (the append-only corpus written by
web/review_history.py) and prints, per diagnosed signal, its mean value in WON
vs LOST matches and how strongly it separates them -- the offline "what
good/bad looks like" read the corpus exists for. ASCII-only output.

Usage:
  python scripts/match_review_report.py [world_code]
With no code, every match_review_*.jsonl under saves/ is pooled.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run from the repo root without needing an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from esports_sim.web import review_history  # noqa: E402


def _all_codes() -> list[str]:
    pre, suf = "match_review_", ".jsonl"
    return sorted(
        p.name[len(pre): -len(suf)]
        for p in Path("saves").glob("match_review_*.jsonl")
    )


def main(argv: list[str]) -> int:
    codes = [argv[1]] if len(argv) > 1 else _all_codes()
    if not codes:
        print("no match-review corpus under saves/ (play some matches first)")
        return 1

    records = []
    for code in codes:
        records.extend(review_history.load_records(code))
    contested = [r for r in records if r.review.contested]
    if not contested:
        print("corpus has %d record(s) but none contested yet" % len(records))
        return 0

    wins = sum(1 for r in contested if r.review.won)
    losses = len(contested) - wins

    # Per signal code: values seen in won matches, and in lost matches.
    agg: dict[str, tuple[list[float], list[float]]] = {}
    for r in contested:
        for p in r.review.working + r.review.breaking:
            wl, ll = agg.setdefault(p.code, ([], []))
            (wl if r.review.won else ll).append(p.value)

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    rows = []
    for code, (wl, ll) in agg.items():
        rows.append((code, len(wl), mean(wl), len(ll), mean(ll), mean(wl) - mean(ll)))
    rows.sort(key=lambda t: (-abs(t[5]), t[0]))

    print(
        "Match-review corpus: %d contested match(es)  [%d W / %d L]  "
        "across %d world(s)" % (len(contested), wins, losses, len(codes))
    )
    print("(value is a 0-1 rate, except acs_gap which is on the 0-100 ACS scale)")
    print()
    print(
        "%-12s %5s %9s %5s %9s %10s"
        % ("signal", "n(W)", "mean(W)", "n(L)", "mean(L)", "W-L gap")
    )
    print("-" * 55)
    for code, nw, wm, nl, lm, sep in rows:
        print("%-12s %5d %9.3f %5d %9.3f %+10.3f" % (code, nw, wm, nl, lm, sep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
