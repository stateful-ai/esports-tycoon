"""Tournament registration and conditional between-map management.

Campaign weeks resolve atomically, so a manager writes a conditional series
card before advancing.  If its trigger occurs after map one, later maps use
the registered substitute and/or response.  The directive is persisted until
the fixture resolves; the grounded action text is persisted on the Fixture.
"""

from __future__ import annotations

from esports_sim.manager import market
from esports_sim.manager.state import Fixture, GameState, SeriesDirective

TRIGGERS = ("trailing", "after_loss", "always")
RESPONSES = ("steady", "press", "stabilize", "reset")


def registration_for(gs: GameState, team_id: str) -> list[str]:
    """Return the valid registered tournament roster, healing stale ids."""
    roster = set(gs.teams[team_id].player_ids)
    registered = [
        pid for pid in gs.tournament_rosters.get(team_id, []) if pid in roster
    ]
    if len(registered) >= market.ROSTER_MIN:
        return registered[: market.TOURNAMENT_REGISTER]
    return []


def auto_registration(gs: GameState, team_id: str) -> list[str]:
    """Best five plus one bench option, with stable quality/id ordering."""
    team = gs.teams[team_id]
    ordered: list[str] = []
    for pid in team.lineup_ids:
        if pid in team.player_ids and pid not in ordered:
            ordered.append(pid)
    for pid in sorted(
        team.player_ids,
        key=lambda q: (-market.player_quality(gs.players[q]), q),
    ):
        if pid not in ordered:
            ordered.append(pid)
    return ordered[: market.TOURNAMENT_REGISTER]


def register_roster(
    gs: GameState, team_id: str, player_ids: list[str]
) -> tuple[bool, str]:
    """Submit a tournament six while the regular-season registration is open."""
    if gs.phase != "regular":
        return False, "the tournament roster is locked"
    if len(player_ids) not in (market.ROSTER_MIN, market.TOURNAMENT_REGISTER):
        return False, "register five starters and at most one substitute"
    if len(set(player_ids)) != len(player_ids):
        return False, "a player can only be registered once"
    roster = set(gs.teams[team_id].player_ids)
    if any(pid not in roster for pid in player_ids):
        return False, "every registered player must be under contract"
    gs.tournament_rosters[team_id] = list(player_ids)
    return True, f"registered {len(player_ids)} players for the next tournament"


def lock_all(gs: GameState) -> None:
    """Freeze a legal registration for every org at the playoff boundary."""
    for tid in sorted(gs.teams):
        current = registration_for(gs, tid)
        if not current:
            gs.tournament_rosters[tid] = auto_registration(gs, tid)


def eligible_pool(gs: GameState, team_id: str, fixture: Fixture) -> list[str]:
    """Who may dress in a tournament series; league weeks use the full roster."""
    if fixture.best_of <= 1:
        return list(gs.teams[team_id].player_ids)
    registered = registration_for(gs, team_id)
    return registered or auto_registration(gs, team_id)


def starting_five(gs: GameState, team_id: str, fixture: Fixture) -> list[str]:
    """The currently planned map-one five, restricted to registration."""
    pool = eligible_pool(gs, team_id, fixture)
    first_map = fixture.maps[0] if fixture.maps else ""
    key = f"{team_id}|{fixture.id}|{first_map}"
    plan = gs.game_plans_by.get(team_id)
    primary = gs.map_lineups.get(key, [])
    if not primary and plan is not None and plan.fixture_id == fixture.id:
        primary = list(plan.starter_ids)
    if not primary:
        primary = list(gs.teams[team_id].lineup_ids)
    chosen = [pid for pid in primary if pid in pool]
    for pid in sorted(
        pool, key=lambda q: (-market.player_quality(gs.players[q]), q)
    ):
        if pid not in chosen:
            chosen.append(pid)
    return chosen[: market.ROSTER_SIZE]


def set_directive(
    gs: GameState,
    team_id: str,
    fixture_id: str,
    *,
    trigger: str = "trailing",
    response: str = "steady",
    substitute_in: str | None = None,
    substitute_out: str | None = None,
) -> tuple[bool, str]:
    fixture = next((f for f in gs.fixtures if f.id == fixture_id), None)
    if fixture is None or team_id not in (fixture.team_a, fixture.team_b):
        return False, "that fixture is not on your calendar"
    if fixture.played or fixture.week < gs.week:
        return False, "that series has already been played"
    if fixture.best_of < 3:
        return False, "between-map instructions require a best-of-three or longer"
    if trigger not in TRIGGERS:
        return False, "unknown series trigger"
    if response not in RESPONSES:
        return False, "unknown between-map response"
    if bool(substitute_in) != bool(substitute_out):
        return False, "choose both the player coming in and the player coming out"
    if substitute_in is not None:
        pool = eligible_pool(gs, team_id, fixture)
        if substitute_in not in pool or substitute_out not in pool:
            return False, "both players must be on the registered tournament roster"
        if substitute_in == substitute_out:
            return False, "substitute in and out must be different players"
        starters = starting_five(gs, team_id, fixture)
        if substitute_out not in starters:
            return False, "the player coming out must be in the planned starting five"
        if substitute_in in starters:
            return False, "the player coming in must begin the series on the bench"
    gs.series_directives_by[team_id] = SeriesDirective(
        fixture_id=fixture_id,
        trigger=trigger,
        response=response,
        substitute_in=substitute_in,
        substitute_out=substitute_out,
    )
    return True, "between-map instruction saved"


def clear_directive(gs: GameState, team_id: str) -> None:
    gs.series_directives_by.pop(team_id, None)


def auto_directives(gs: GameState) -> None:
    """Give AI tournament teams the same conditional substitution/response
    lever. Selection is public-roster, deterministic, and never overwrites a
    human or existing directive."""
    if gs.phase != "playoffs":
        return
    for fixture in sorted(gs.fixtures_for_week(), key=lambda f: f.id):
        if fixture.played or fixture.best_of < 3:
            continue
        for tid in sorted((fixture.team_a, fixture.team_b)):
            if gs.is_human(tid) or tid in gs.series_directives_by:
                continue
            pool = eligible_pool(gs, tid, fixture)
            starters = [pid for pid in auto_registration(gs, tid) if pid in pool]
            for pid in sorted(
                pool, key=lambda q: (-market.player_quality(gs.players[q]), q)
            ):
                if pid not in starters:
                    starters.append(pid)
            starters = starters[: market.ROSTER_SIZE]
            bench = [pid for pid in pool if pid not in starters]
            sub_in = bench[0] if bench else None
            sub_out = min(
                starters,
                key=lambda pid: (market.player_quality(gs.players[pid]), pid),
            ) if starters and sub_in else None
            response = (
                "stabilize" if gs.teams[tid].tactics.aggression >= 55 else "press"
            )
            gs.series_directives_by[tid] = SeriesDirective(
                fixture_id=fixture.id,
                trigger="trailing",
                response=response,
                substitute_in=sub_in,
                substitute_out=sub_out,
            )


def should_fire(
    directive: SeriesDirective,
    fixture: Fixture,
    team_id: str,
    map_index: int,
) -> bool:
    """Evaluate immediately before map `map_index` (zero based)."""
    if map_index < 1 or not fixture.results:
        return False
    last_lost = fixture.results[-1].winner_id != team_id
    if directive.trigger == "always":
        return True
    if directive.trigger == "after_loss":
        return last_lost
    a_wins, b_wins = fixture.map_score
    ours, theirs = (a_wins, b_wins) if team_id == fixture.team_a else (b_wins, a_wins)
    return ours < theirs


def adjusted_lineup(
    lineup: list[str], directive: SeriesDirective
) -> list[str]:
    """Apply the optional one-for-one registered substitution."""
    if directive.substitute_in is None or directive.substitute_out is None:
        return list(lineup)
    if directive.substitute_out not in lineup:
        return list(lineup)
    changed = [
        directive.substitute_in if pid == directive.substitute_out else pid
        for pid in lineup
    ]
    return changed if len(set(changed)) == len(changed) else list(lineup)
