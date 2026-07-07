"""Multi-season snowball report.

Measures whether the league stays competitive across seasons: map scoreline
distribution (blowout share) and top-team dominance, per season. Run before
and after balance changes to compare.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\snowball_report.py [seeds...]
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from esports_sim.manager import advance_week, new_campaign
from esports_sim.manager.schedule import regular_season_weeks
from esports_sim.registry import load_all

N_SEASONS = 3


def run(seed: int) -> None:
    gd = load_all()
    gs = new_campaign(gd, seed=seed)
    per_season: dict[int, Counter] = defaultdict(Counter)
    wins: dict[int, Counter] = defaultdict(Counter)

    while gs.season <= N_SEASONS:
        season = gs.season
        advance_week(gs, gd)
        for f in gs.fixtures_for_week(gs.week - 1):
            if not f.played or f.stage != "regular":
                continue
            for r in f.results:
                loser_rounds = min(r.score_a, r.score_b)
                bucket = (
                    "0-2" if loser_rounds <= 2
                    else "3-7" if loser_rounds <= 7
                    else "8-11" if loser_rounds <= 11
                    else "OT/close"
                )
                per_season[season][bucket] += 1
            if f.winner_id:
                wins[season][f.winner_id] += 1

    print(f"\nseed {seed}")
    for season in sorted(per_season):
        c = per_season[season]
        total = sum(c.values())
        n_weeks = regular_season_weeks(len(gs.teams))
        top = wins[season].most_common(1)[0] if wins[season] else ("-", 0)
        blowout = 100 * (c["0-2"]) / max(total, 1)
        close = 100 * (c["8-11"] + c["OT/close"]) / max(total, 1)
        print(
            f"  S{season}: {total} maps | blowout(<=2) {blowout:4.1f}% | "
            f"close(>=8) {close:4.1f}% | top team {top[1]}/{n_weeks} wins"
        )


if __name__ == "__main__":
    seeds = [int(s) for s in sys.argv[1:]] or [777, 2026, 31337]
    for s in seeds:
        run(s)
