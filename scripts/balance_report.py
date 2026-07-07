"""Balance report: sim N matches per map and print side/reason splits.

Run after touching sim/constants.py or map data:

    python scripts/balance_report.py [n_matches]

Targets to eyeball:
  - attack round win rate ~50-60% per map
  - all four round-end reasons present
  - the stronger roster wins 70-85% of bo1s (not ~100%)
"""

from __future__ import annotations

import sys
from collections import Counter

from esports_sim.registry import load_all
from esports_sim.sim import simulate_match_result

n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
gd = load_all()

for map_id in sorted(gd.maps):
    wins: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    atk_wins = total = 0
    loser_rounds = []
    for seed in range(n):
        res = simulate_match_result(gd, "team_nexus", "team_vanguard", map_id, seed)
        wins[res.winner_id] += 1
        loser_rounds.append(min(res.score_a, res.score_b))
        atk = None
        for e in res.events:
            if e.type == "round.start":
                atk = e.attacking_team_id
            elif e.type == "round.end":
                reasons[e.reason] += 1
                total += 1
                atk_wins += e.winner_id == atk
    med = sorted(loser_rounds)[len(loser_rounds) // 2]
    print(
        f"{map_id:8s} atk {atk_wins / total:5.1%}  "
        f"favorite {wins['team_vanguard']}/{n}  median loser rounds {med}  "
        f"{dict(reasons)}"
    )
