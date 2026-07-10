"""Rivalries — pairs of orgs whose history means something.

Intensity (0-100) accumulates from chronicle-worthy meetings: playoff
eliminations, finals, international brackets, and poached players. It
decays over each offseason (grudges cool but don't vanish), and a pair
crossing the RIVALRY_BAR gets a chronicle entry + news once per
crossing. Pure campaign layer: rivalry never touches the match engine —
it feeds narrative, the social layer's temperature, and (later phases)
fan/sponsor value.

State is one scalar per pair on GameState.rivalries ("a|b" sorted key),
mirroring the player relationship graph's shape.
"""

from __future__ import annotations

from esports_sim.manager import chronicle
from esports_sim.manager.state import GameState

# Heat per meeting, by what was at stake.
STAGE_HEAT: dict[str, float] = {
    "semi": 5.0,
    "final": 9.0,
    "masters_qf": 7.0,
    "masters_sf": 8.0,
    "masters_final": 12.0,
    "champ_qf": 8.0,
    "champ_sf": 9.0,
    "champ_final": 14.0,
}
POACH_HEAT = 4.0  # buying a player out of a rival's roster
REMATCH_HEAT = 2.0  # a regular-season meeting of an already-hot pair
RIVALRY_BAR = 40.0  # named-rivalry threshold (news + chronicle)
OFFSEASON_COOL = 0.75  # grudges cool over the break...
FLOOR = 4.0  # ...and the faint ones are forgotten


def key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def get(gs: GameState, a: str, b: str) -> float:
    return gs.rivalries.get(key(a, b), 0.0)


def _add(gs: GameState, a: str, b: str, heat: float) -> None:
    k = key(a, b)
    before = gs.rivalries.get(k, 0.0)
    after = round(min(100.0, before + heat), 1)
    gs.rivalries[k] = after
    if before < RIVALRY_BAR <= after:
        ta, tb = gs.teams.get(a), gs.teams.get(b)
        if ta is not None and tb is not None:
            gs.push_news(
                f"{ta.name} vs {tb.name} is a full-blown rivalry now."
            )
            chronicle.record(
                gs, "rivalry",
                f"The {ta.name}-{tb.name} rivalry ignites.",
                team_id=a,
                data={"other": b},
            )


def on_week(gs: GameState, report) -> None:
    """Fold this week's meetings into the rivalry graph. Runs after the
    market tick (so this week's poach chronicle entries exist) and before
    the news (so recaps can read the fresh heat)."""
    for f in sorted(report.fixtures, key=lambda x: x.id):
        if not f.played or f.tier != 1:
            continue
        heat = STAGE_HEAT.get(f.stage)
        if heat is None:
            # A regular meeting only stokes an ALREADY-hot pair.
            if get(gs, f.team_a, f.team_b) >= RIVALRY_BAR / 2:
                _add(gs, f.team_a, f.team_b, REMATCH_HEAT)
            continue
        # A decided series burns hotter for the loser: elimination sticks.
        _add(gs, f.team_a, f.team_b, heat)
    # Poaches: transfers chronicled THIS tick between two orgs.
    for e in gs.chronicle:
        if (
            e.kind == "transfer"
            and e.season == gs.season
            and e.week == gs.week
            and e.data.get("from")
        ):
            _add(gs, e.team_id, e.data["from"], POACH_HEAT)


def offseason_decay(gs: GameState) -> None:
    cooled = {}
    for k in sorted(gs.rivalries):
        v = round(gs.rivalries[k] * OFFSEASON_COOL, 1)
        if v >= FLOOR:
            cooled[k] = v
    gs.rivalries = cooled


def top_rivals(gs: GameState, tid: str, n: int = 3) -> list[tuple[str, float]]:
    """A team's hottest rivals, (other team id, intensity), hot first."""
    out = []
    for k in sorted(gs.rivalries):
        a, b = k.split("|", 1)
        if tid == a:
            out.append((b, gs.rivalries[k]))
        elif tid == b:
            out.append((a, gs.rivalries[k]))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out[:n]
