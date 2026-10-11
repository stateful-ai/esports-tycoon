"""Conservative qualification bounds from public league records and fixtures."""

from esports_sim.manager.state import GameState

PLAYOFF_CUT = 4


def qualification_statuses(
    gs: GameState, region: str, *, tier: int = 1, cut: int = PLAYOFF_CUT,
) -> dict[str, str]:
    """Return secured / contested / eliminated without predicting tiebreakers.

    A rival whose win ceiling ties a team's current wins can still pass it
    on round differential. Conversely, only strictly higher current wins
    prove a rival must finish above a team's ceiling. These independent
    bounds deliberately leave some schedule-dependent outcomes contested.
    Callers supply the relevant competition's cut; Challengers has no
    top-four playoff berth. This view never changes standings or fixtures.
    """
    if gs.phase != "regular" or cut < 1:
        return {}
    tids = sorted(t.id for t in gs.teams.values()
                  if str(t.region) == region and t.tier == tier)
    wins = {tid: gs.standings[tid].wins if tid in gs.standings else 0 for tid in tids}
    remaining = dict.fromkeys(tids, 0)
    for fixture in gs.fixtures:
        if (fixture.played or fixture.stage != "regular" or fixture.bracket != "league"
                or fixture.tier != tier
                or fixture.team_a not in remaining or fixture.team_b not in remaining):
            continue
        remaining[fixture.team_a] += 1
        remaining[fixture.team_b] += 1
    ceiling = {tid: wins[tid] + remaining[tid] for tid in tids}
    statuses = {}
    for tid in tids:
        if sum(wins[rival] > ceiling[tid] for rival in tids if rival != tid) >= cut:
            statuses[tid] = "eliminated"
        elif sum(ceiling[rival] >= wins[tid] for rival in tids if rival != tid) < cut:
            statuses[tid] = "secured"
        else:
            statuses[tid] = "contested"
    return statuses
