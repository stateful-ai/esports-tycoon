"""Campaign orchestration: new game, weekly advance, playoffs, offseason.

`advance_week` is the single tick of the management layer. Everything it
does derives randomness from the campaign seed + (season, week) labels, so
a save can be replayed and two campaigns with the same seed and the same
user decisions are identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from esports_sim.manager import market, training
from esports_sim.manager.economy import (
    apply_weekly_finance,
    pay_playoff_prizes,
    pay_regular_season_prizes,
)
from esports_sim.manager.gen import generate_free_agents, generate_league_teams
from esports_sim.manager.schedule import (
    build_final,
    build_regular_season,
    build_semifinals,
    regular_season_weeks,
)
from esports_sim.manager.state import (
    ChampionRecord,
    Fixture,
    GameState,
    MapResult,
    PlayerLineSnap,
    TeamRecord,
)
from esports_sim.registry.loader import GameData
from esports_sim.rng.tree import RngTree
from esports_sim.sim import simulate_match_result
from esports_sim.sim.stats import compute_match_stats


@dataclass
class WeekReport:
    """What happened when the week advanced — the CLI renders this.

    `match_stats` (fixture id -> one MatchStats per map) is transient
    viewing data captured at sim time; it is NOT saved. Replaying a match
    later would require the exact roster state it was simmed with, which
    training/aging have already moved on from.
    """

    season: int
    week: int
    phase: str
    fixtures: list[Fixture] = field(default_factory=list)
    match_stats: dict[str, list] = field(default_factory=dict)
    user_income: int = 0
    user_expenses: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# New game


def new_campaign(gd: GameData, seed: int, user_team_id: str = "team_nexus") -> GameState:
    rng = RngTree(seed).derive("campaign", "gen")

    teams = {tid: t.model_copy(deep=True) for tid, t in gd.teams.items()}
    players = {pid: p.model_copy(deep=True) for pid, p in gd.players.items()}

    gen_teams, gen_players = generate_league_teams(rng, gd, n_teams=6)
    for t in gen_teams:
        teams[t.id] = t
    for p in gen_players:
        players[p.id] = p

    fas = generate_free_agents(rng, gd, n=18)
    for p in fas:
        players[p.id] = p

    gs = GameState(
        seed=seed,
        user_team_id=user_team_id,
        teams=teams,
        players=players,
        free_agent_ids=[p.id for p in fas],
        fixtures=build_regular_season(sorted(teams), sorted(gd.maps), season=1),
        standings={tid: TeamRecord() for tid in teams},
        training_focus={tid: "tactical" for tid in teams},
    )
    gs.push_news(
        f"Season 1 begins — {len(teams)} teams, "
        f"{regular_season_weeks(len(teams))} weeks of league play, then playoffs."
    )
    _update_world_ranks(gs)
    return gs


# ---------------------------------------------------------------------------
# Runtime GameData view: static registries + live campaign rosters


def runtime_gamedata(gs: GameState, gd: GameData) -> GameData:
    return GameData(
        attributes=gd.attributes,
        agents=gd.agents,
        weapons=gd.weapons,
        maps=gd.maps,
        teams=gs.teams,
        players=gs.players,
    )


# ---------------------------------------------------------------------------
# Weekly tick


def advance_week(
    gs: GameState,
    gd: GameData,
    events_out: dict[str, list[list]] | None = None,
) -> WeekReport:
    """`events_out` (fixture id -> one event list per map) captures full
    match logs at sim time for replay viewers. Like WeekReport.match_stats
    it is transient: rosters move on (training/aging) immediately after,
    so a later re-sim from the stored seed would not reproduce these logs.
    """
    if gs.phase == "offseason":
        return _run_offseason(gs, gd)

    report = WeekReport(season=gs.season, week=gs.week, phase=gs.phase)
    tree = RngTree(gs.seed)
    week_rng = tree.derive("season", gs.season, "week", gs.week, "weekly")
    rt_gd = runtime_gamedata(gs, gd)

    # 1. Matches.
    week_fixtures = gs.fixtures_for_week()
    for f in sorted(week_fixtures, key=lambda x: x.id):
        _sim_fixture(
            gs, rt_gd, tree, f, collector=report.match_stats, events_out=events_out
        )
        report.fixtures.append(f)

    # 2. Training (user focus is whatever they set; AI picks its own).
    for tid in sorted(gs.teams):
        roster = gs.roster(tid)
        if tid == gs.user_team_id:
            focus = gs.training_focus.get(tid, "tactical")
        else:
            focus = training.ai_pick_focus(roster, week_rng)
            gs.training_focus[tid] = focus
        training.apply_training(gs.teams[tid], roster, focus, week_rng)

    # 3. Finances.
    for tid in sorted(gs.teams):
        income, expenses = apply_weekly_finance(gs.teams[tid], gs.roster(tid))
        if tid == gs.user_team_id:
            report.user_income, report.user_expenses = income, expenses

    # 4. Contracts + AI roster upkeep.
    market.tick_contracts(gs, week_rng)
    market.ai_fill_rosters(gs, gd, week_rng)

    _update_world_ranks(gs)

    # 5. Phase transitions.
    n_weeks = regular_season_weeks(len(gs.teams))
    if gs.phase == "regular" and gs.week == n_weeks:
        pay_regular_season_prizes(gs)
        order = gs.standings_order()
        gs.fixtures.extend(
            build_semifinals(order, sorted(gd.maps), gs.season, gs.week + 1)
        )
        gs.phase = "playoffs"
        top4 = ", ".join(gs.teams[t].name for t in order[:4])
        gs.push_news(f"Playoffs set: {top4}.")
        report.notes.append("Regular season complete — playoffs next week.")
    elif gs.phase == "playoffs":
        semis = [f for f in gs.fixtures if f.stage == "semi"]
        final = next((f for f in gs.fixtures if f.stage == "final"), None)
        if all(f.played for f in semis) and final is None:
            winners = [f.winner_id for f in semis if f.winner_id]
            gs.fixtures.append(
                build_final(winners, sorted(gd.maps), gs.season, gs.week + 1)
            )
            report.notes.append("Grand final next week.")
        elif final is not None and final.played:
            assert final.winner_id is not None
            runner_up = (
                final.team_b if final.winner_id == final.team_a else final.team_a
            )
            semi_losers = [
                (f.team_b if f.winner_id == f.team_a else f.team_a) for f in semis
            ]
            pay_playoff_prizes(gs, final.winner_id, runner_up, semi_losers)
            champ = gs.teams[final.winner_id]
            gs.champions.append(
                ChampionRecord(
                    season=gs.season, team_id=champ.id, team_name=champ.name
                )
            )
            gs.push_news(f"{champ.name} are the Season {gs.season} champions!")
            gs.phase = "offseason"
            report.notes.append(
                f"{champ.name} win the title. Offseason next week."
            )

    gs.week += 1
    return report


# ---------------------------------------------------------------------------
# Fixture simulation


def _sim_fixture(
    gs: GameState,
    rt_gd: GameData,
    tree: RngTree,
    f: Fixture,
    collector: dict[str, list] | None = None,
    events_out: dict[str, list[list]] | None = None,
) -> None:
    need = f.best_of // 2 + 1

    # A team with nobody on the roster forfeits the series.
    empty_a = not gs.teams[f.team_a].player_ids
    empty_b = not gs.teams[f.team_b].player_ids
    if empty_a or empty_b:
        walkover = f.team_b if empty_a else f.team_a
        for map_id in f.maps[:need]:
            f.results.append(
                MapResult(
                    map_id=map_id,
                    seed=0,
                    score_a=0 if empty_a else 13,
                    score_b=13 if empty_a else 0,
                    winner_id=walkover,
                )
            )
        f.winner_id = walkover
        f.played = True
        gs.push_news(
            f"{gs.teams[f.team_a if empty_a else f.team_b].name} forfeit "
            f"(no roster) — {gs.teams[walkover].name} take the series."
        )
        if f.stage == "regular":
            rec_a, rec_b = gs.standings[f.team_a], gs.standings[f.team_b]
            (rec_b if empty_a else rec_a).wins += 1
            (rec_a if empty_a else rec_b).losses += 1
            for r in f.results:
                rec_a.rounds_won += r.score_a
                rec_a.rounds_lost += r.score_b
                rec_b.rounds_won += r.score_b
                rec_b.rounds_lost += r.score_a
        return

    for map_index, map_id in enumerate(f.maps):
        a_wins, b_wins = f.map_score
        if a_wins >= need or b_wins >= need:
            break
        seed = tree.derive_seed(
            "season", gs.season, "week", f.week, "fixture", f.id, "map", map_index
        )
        res = simulate_match_result(rt_gd, f.team_a, f.team_b, map_id, seed)
        stats = compute_match_stats(res.events)
        if collector is not None:
            collector.setdefault(f.id, []).append(stats)
        if events_out is not None:
            events_out.setdefault(f.id, []).append(res.events)
        lines = [
            PlayerLineSnap(
                player_id=pid,
                kills=line.kills,
                deaths=line.deaths,
                rating=line.rating,
            )
            for pid, line in sorted(stats.lines.items())
        ]
        f.results.append(
            MapResult(
                map_id=map_id,
                seed=seed,
                score_a=res.score_a,
                score_b=res.score_b,
                winner_id=res.winner_id,
                lines=lines,
            )
        )
        # Per-map wear and per-map form movement.
        _apply_map_effects(gs, f, res.winner_id, stats)

    a_wins, b_wins = f.map_score
    f.winner_id = f.team_a if a_wins > b_wins else f.team_b
    f.played = True
    _apply_match_effects(gs, f)

    # Standings only track the regular season.
    if f.stage == "regular":
        rec_a, rec_b = gs.standings[f.team_a], gs.standings[f.team_b]
        if f.winner_id == f.team_a:
            rec_a.wins += 1
            rec_b.losses += 1
        else:
            rec_b.wins += 1
            rec_a.losses += 1
        for r in f.results:
            rec_a.rounds_won += r.score_a
            rec_a.rounds_lost += r.score_b
            rec_b.rounds_won += r.score_b
            rec_b.rounds_lost += r.score_a


def _apply_map_effects(gs: GameState, f: Fixture, map_winner: str, stats) -> None:
    for tid in (f.team_a, f.team_b):
        for p in gs.roster(tid):
            line = stats.lines.get(p.id)
            if line is None:
                continue
            p.stamina = max(0.0, p.stamina - 7.0)
            # Form chases recent performance.
            perf = 30.0 + line.rating * 28.0
            p.form = round(min(100.0, max(0.0, 0.75 * p.form + 0.25 * perf)), 1)


def _apply_match_effects(gs: GameState, f: Fixture) -> None:
    assert f.winner_id is not None
    big = 2.0 if f.stage in ("semi", "final") else 1.0
    for tid in (f.team_a, f.team_b):
        team = gs.teams[tid]
        won = tid == f.winner_id
        for p in gs.roster(tid):
            p.morale = round(min(100.0, max(0.0, p.morale + (5.0 if won else -4.0))), 1)
        team.chemistry = round(
            min(100.0, max(0.0, team.chemistry + (1.5 if won else -1.0))), 1
        )
        team.reputation = round(
            min(100.0, max(1.0, team.reputation + (0.8 if won else -0.5) * big)), 1
        )
        if won:
            team.fan_count = int(team.fan_count * 1.01) + 500


def _update_world_ranks(gs: GameState) -> None:
    def key(tid: str) -> tuple:
        r = gs.standings.get(tid, TeamRecord())
        return (-r.wins, -r.diff, -gs.teams[tid].reputation, tid)

    for rank, tid in enumerate(sorted(gs.teams, key=key), start=1):
        gs.teams[tid].world_rank = rank


# ---------------------------------------------------------------------------
# Offseason


def _run_offseason(gs: GameState, gd: GameData) -> WeekReport:
    report = WeekReport(season=gs.season, week=gs.week, phase="offseason")
    tree = RngTree(gs.seed)
    rng = tree.derive("season", gs.season, "offseason")

    for pid in sorted(gs.players):
        training.apply_offseason_aging(gs.players[pid], rng)

    # Refresh the free-agent pool: cull the weakest, add fresh prospects.
    fas = sorted(
        gs.free_agent_ids, key=lambda pid: market.player_quality(gs.players[pid])
    )
    while len(fas) > 14:
        cut = fas.pop(0)
        gs.free_agent_ids.remove(cut)
        del gs.players[cut]
    for _ in range(5):
        market._generate_rookie(gs, gd, rng)

    # New season.
    gs.season += 1
    gs.week = 1
    gs.phase = "regular"
    gs.fixtures = build_regular_season(sorted(gs.teams), sorted(gd.maps), gs.season)
    gs.standings = {tid: TeamRecord() for tid in gs.teams}
    gs.push_news(f"Season {gs.season} begins.")
    report.notes.append(f"Offseason complete — Season {gs.season} starts now.")
    _update_world_ranks(gs)
    return report
