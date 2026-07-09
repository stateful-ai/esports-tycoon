"""Tactics sanity harness: sweep each coaching dial to its extremes and
report what it does to the wielding team's macro outcomes.

The balance/golden gates only ever exercise NEUTRAL tactics (that's what
keeps them byte-stable). Nothing else checks that cranking a dial stays
sane — a wiring bug or a lever with a runaway feedback loop could make an
extreme setting degenerate (0% or 100% attack, no plants ever) and no
existing gate would catch it. This does.

For each dial we set it on team_nexus only (vanguard stays neutral), sim N
matches per map, and report nexus's attack-round win rate and plant rate at
low / neutral / high. Extremes are *allowed* to move the numbers — that's
the point of the dial — but not off a cliff. Exit 1 if any setting drives
attack rate outside the sanity band or kills plants entirely.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\tactics_report.py [n_matches]
"""

from __future__ import annotations

import sys

from esports_sim.registry import load_all
from esports_sim.sim import simulate_match

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60

# A wide degenerate-detector band — not the tight 45-65 neutral balance
# gate. Extreme tactics may legitimately push the wielder's attack rate to
# these edges, but past them means a lever has run away.
SANITY_ATK = (0.30, 0.75)
MIN_PLANT_RATE = 0.10

DIALS = {
    "aggression": (10.0, 90.0),
    "pace": (10.0, 90.0),
    "util_discipline": (10.0, 90.0),
    "eco_greed": (10.0, 90.0),
    "map_control": (10.0, 90.0),
}


_GD = load_all()
_TAC = _GD.teams["team_nexus"].tactics


def measure(dial: str | None, value: float) -> tuple[float, float]:
    """(nexus attack-round win rate, plant rate) over N matches per map with
    `dial` set to `value` on team_nexus only. Registries load once; the one
    dial is set before the sweep and reset to neutral after."""
    gd = _GD
    for f in ("aggression", "pace", "util_discipline", "eco_greed", "map_control"):
        setattr(_TAC, f, 50.0)
    if dial is not None:
        setattr(_TAC, dial, value)
    atk_rounds = atk_wins = plants = 0
    for map_id in sorted(gd.maps):
        for seed in range(N):
            atk = None
            planted_this = False
            for e in simulate_match(gd, "team_nexus", "team_vanguard", map_id, seed):
                if e.type == "round.start":
                    atk = e.attacking_team_id
                    planted_this = False
                elif e.type == "round.spike_plant":
                    planted_this = True
                elif e.type == "round.end":
                    if atk == "team_nexus":
                        atk_rounds += 1
                        atk_wins += e.winner_id == "team_nexus"
                        plants += planted_this
    if atk_rounds == 0:
        return 0.0, 0.0
    return atk_wins / atk_rounds, plants / atk_rounds


def main() -> int:
    neutral_atk, neutral_plant = measure(None, 50.0)
    print(
        f"{'dial':16s} {'setting':>8s} {'atk%':>7s} {'plant%':>7s} {'d-atk':>7s}"
    )
    print(
        f"{'(neutral)':16s} {'50':>8s} {neutral_atk:7.1%} {neutral_plant:7.1%} {'--':>7s}"
    )
    bad: list[str] = []
    for dial, (lo, hi) in DIALS.items():
        for value in (lo, hi):
            atk, plant = measure(dial, value)
            flag = ""
            if not (SANITY_ATK[0] <= atk <= SANITY_ATK[1]):
                flag = "  <-- ATK OUT OF SANITY BAND"
                bad.append(f"{dial}={value:.0f} atk {atk:.1%}")
            if plant < MIN_PLANT_RATE:
                flag += "  <-- PLANTS COLLAPSED"
                bad.append(f"{dial}={value:.0f} plant {plant:.1%}")
            print(
                f"{dial:16s} {value:>8.0f} {atk:7.1%} {plant:7.1%} "
                f"{atk - neutral_atk:+7.1%}{flag}"
            )
    print()
    print(f"sanity band: attack {SANITY_ATK[0]:.0%}-{SANITY_ATK[1]:.0%}, "
          f"plant rate >= {MIN_PLANT_RATE:.0%}")
    if bad:
        print("DEGENERATE:", "; ".join(bad))
        return 1
    print("all dial extremes within sanity band")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
