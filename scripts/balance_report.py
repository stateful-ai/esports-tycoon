"""Balance gate: sim N matches per map and check the attack-round band.

Run after touching sim/constants.py or map data:

    python scripts/balance_report.py [n_matches]

This is a GATE (exit 1 = fail), matching CLAUDE.md's stated band: every map
must land 45-65% attack-round win rate, and the three core round-end reasons
(elim, detonation, defuse) must all show up — a map that can't be won by,
say, detonation is degenerate. `time` (defenders run out the clock) is rare
and legitimately absent on fast maps, so it is NOT required. It reads
simulated outcomes only — no golden re-bless.
"""

from __future__ import annotations

import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from esports_sim.registry import load_all
from esports_sim.sim import simulate_match_result

ATK_BAND = (0.45, 0.65)  # per-map attack-round win rate (CLAUDE.md invariant 3)
# `time` is intentionally excluded — it's a rare defender-clock win that some
# fast maps never see over a few hundred seeds; requiring it flakes.
REQUIRED_REASONS = {"elim", "spike_detonation", "spike_defused"}

def _simulate_map(map_id: str, n: int) -> tuple[str, Counter, Counter, float, int]:
    """Independent deterministic map sweep, safe to run in a worker."""
    gd = load_all()
    wins: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    atk_wins = total = 0
    loser_rounds = []
    for seed in range(n):
        res = simulate_match_result(
            gd,
            "team_nexus",
            "team_vanguard",
            map_id,
            seed,
            capture_control_events=False,
        )
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
    atk_rate = atk_wins / max(total, 1)
    med = sorted(loser_rounds)[len(loser_rounds) // 2]
    return map_id, wins, reasons, atk_rate, med


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    map_ids = sorted(load_all().maps)
    with ProcessPoolExecutor(max_workers=len(map_ids)) as pool:
        futures = [pool.submit(_simulate_map, map_id, n) for map_id in map_ids]
        results = [future.result() for future in futures]

    failures: list[str] = []
    for map_id, wins, reasons, atk_rate, med in sorted(results):
        flags = []
        if not (ATK_BAND[0] <= atk_rate <= ATK_BAND[1]):
            flags.append(
                f"atk {atk_rate:.1%} out of "
                f"{ATK_BAND[0]:.0%}-{ATK_BAND[1]:.0%}"
            )
        missing = REQUIRED_REASONS - set(reasons)
        if missing:
            flags.append(f"missing reasons {sorted(missing)}")
        if flags:
            failures.append(f"{map_id}: " + "; ".join(flags))
        note = ("  <-- " + "; ".join(flags)) if flags else ""
        print(
            f"{map_id:8s} atk {atk_rate:5.1%}  "
            f"favorite {wins['team_vanguard']}/{n}  median loser rounds {med}  "
            f"{dict(reasons)}{note}"
        )

    print(
        f"\nband: attack {ATK_BAND[0]:.0%}-{ATK_BAND[1]:.0%} per map, "
        "elim/detonation/defuse present"
    )
    if failures:
        print("BALANCE GATE FAIL:")
        for failure in failures:
            print(f"  {failure}")
        raise SystemExit(1)
    print("balance gate OK")


if __name__ == "__main__":
    main()
