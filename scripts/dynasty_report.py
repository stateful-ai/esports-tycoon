"""Dynasty gate: does organizational knowledge (or anything else) let one
org ratchet the league shut?

Runs a headless multi-season campaign and measures title concentration:
the share of Champions titles held by the single most-decorated org, and
how many DISTINCT orgs win one. The org-knowledge system (manager/
knowledge.py) is the designed dynasty engine, so this report is its
permanent guardrail — the same role snowball_report.py plays for
condition feedback.

Bands (over >= 8 completed seasons):
- FAIL if one org holds  > 50% of all titles (a shut league)
- FAIL if fewer than 3 distinct champions exist
Exit 1 on failure — same contract as the other report gates.

Usage: python scripts/dynasty_report.py [seasons] [seed]
ASCII-only output (cp1252 consoles).
"""

from __future__ import annotations

import sys
from collections import Counter

from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.registry import load_all

MAX_TICKS_PER_SEASON = 40
TOP_SHARE_MAX = 0.50
MIN_DISTINCT = 3


def main() -> int:
    seasons = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 4242
    gd = load_all()
    gs = new_campaign(gd, seed=seed)

    print(f"dynasty report: {seasons} seasons, seed {seed}")
    while gs.season <= seasons:
        season = gs.season
        for _ in range(MAX_TICKS_PER_SEASON):
            advance_week(gs, gd)
            if gs.season != season:
                break
        else:
            print(f"FAIL: season {season} never completed "
                  f"({MAX_TICKS_PER_SEASON} ticks)")
            return 1

    titles = Counter(c.team_id for c in gs.champions)
    total = sum(titles.values())
    if total < seasons:
        print(f"FAIL: only {total} champions recorded over {seasons} seasons")
        return 1

    top_id, top_n = titles.most_common(1)[0]
    top_share = top_n / total
    distinct = len(titles)
    print(f"champions: {total} titles, {distinct} distinct orgs")
    for tid, n in titles.most_common():
        name = gs.teams[tid].name if tid in gs.teams else tid
        print(f"  {n:2d}  {name}")
    print(f"top share: {top_share:.0%} "
          f"({gs.teams[top_id].name if top_id in gs.teams else top_id})")

    ok = True
    if total >= 8 and top_share > TOP_SHARE_MAX:
        print(f"FAIL: top org holds {top_share:.0%} of titles "
              f"(> {TOP_SHARE_MAX:.0%})")
        ok = False
    if total >= 8 and distinct < MIN_DISTINCT:
        print(f"FAIL: only {distinct} distinct champions (< {MIN_DISTINCT})")
        ok = False
    print("PASS" if ok else "the league has snapped shut")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
