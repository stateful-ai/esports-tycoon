"""Campaign orchestration: new game, weekly advance, playoffs, offseason.

`advance_week` is the single tick of the management layer. Everything it
does derives randomness from the campaign seed + (season, week) labels, so
a save can be replayed and two campaigns with the same seed and the same
user decisions are identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from esports_sim.manager import (
    development,
    economy,
    inbox,
    market,
    narrative,
    relationships,
    sponsors,
    staff,
    training,
)
from esports_sim.manager.economy import (
    apply_weekly_finance,
    pay_playoff_prizes,
)
from esports_sim.schemas.common import Region
from esports_sim.manager.gen import generate_free_agents, generate_league_teams
from esports_sim.manager.schedule import (
    build_final,
    build_regular_season,
    build_semifinals,
    regular_season_weeks,
    veto_bo3,
)
from esports_sim.manager.state import (
    ChampionRecord,
    Fixture,
    GameState,
    MapResult,
    PlayerLineSnap,
    PlayerSeasonStats,
    TeamRecord,
    TeamSeasonStats,
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


# The VCT-style world: three regional leagues of 8; their top two meet
# at Masters after the regional playoffs. Underneath, a 6-team
# Challengers circuit per region develops prospects — fully simulated,
# never broadcast.
LEAGUE_REGIONS = [Region.AMERICAS, Region.EMEA, Region.PACIFIC]
TEAMS_PER_REGION = 8
TIER2_PER_REGION = 6


def _build_all_leagues(gs_teams: dict, map_ids: list[str], season: int) -> list:
    """One double round-robin per (region, tier), weeks aligned so every
    league plays the same calendar. Challengers (10 weeks) wraps before
    the franchised leagues (14)."""
    fixtures = []
    for region in LEAGUE_REGIONS:
        for tier in (1, 2):
            tids = sorted(
                t.id
                for t in gs_teams.values()
                if t.region == region and t.tier == tier
            )
            if not tids:
                continue
            regional = build_regular_season(tids, map_ids, season)
            for f in regional:
                # Region+tier-qualified ids stay unique across leagues.
                f.id = f"{f.id}{str(region)[:2]}" + ("t2" if tier == 2 else "")
                f.tier = tier
            fixtures.extend(regional)
    return fixtures


def new_campaign(gd: GameData, seed: int, user_team_id: str = "team_nexus") -> GameState:
    rng = RngTree(seed).derive("campaign", "gen")

    teams = {tid: t.model_copy(deep=True) for tid, t in gd.teams.items()}
    players = {pid: p.model_copy(deep=True) for pid, p in gd.players.items()}

    used_names: set[str] = set()
    for region in LEAGUE_REGIONS:
        have = sum(1 for t in teams.values() if t.region == region)
        gen_teams, gen_players = generate_league_teams(
            rng, gd, n_teams=TEAMS_PER_REGION - have,
            region=region, used_names=used_names,
        )
        t2_teams, t2_players = generate_league_teams(
            rng, gd, n_teams=TIER2_PER_REGION,
            region=region, used_names=used_names, tier=2,
        )
        for t in gen_teams + t2_teams:
            teams[t.id] = t
        for p in gen_players + t2_players:
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
        fixtures=_build_all_leagues(teams, sorted(gd.maps), season=1),
        standings={tid: TeamRecord() for tid in teams},
        training_focus={tid: "tactical" for tid in teams},
    )
    gs.push_news(
        f"Season 1 begins — {len(LEAGUE_REGIONS)} regional leagues of "
        f"{TEAMS_PER_REGION}, {regular_season_weeks(TEAMS_PER_REGION)} weeks "
        f"of league play, then playoffs and Masters."
    )
    staff.refresh_candidates(gs)
    _assign_ai_tactics(gs, rng)
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

    # 1. Matches. Challengers games sim fully (development, stats,
    # scouting) but never capture replay logs — nobody broadcasts tier 2.
    week_fixtures = gs.fixtures_for_week()
    week_kills: dict[str, int] = {}
    for f in sorted(week_fixtures, key=lambda x: x.id):
        _sim_fixture(
            gs, rt_gd, tree, f,
            collector=report.match_stats,
            events_out=None if f.tier == 2 else events_out,
        )
        report.fixtures.append(f)
        for stats in report.match_stats.get(f.id, []):
            _aggregate_stats(gs, f, stats, week_kills)

    # 2. Training (user focus is whatever they set; AI picks its own).
    for tid in sorted(gs.teams):
        roster = gs.roster(tid)
        if tid == gs.user_team_id:
            focus = gs.training_focus.get(tid, "tactical")
            mult = staff.coach_multiplier(gs) * economy.facility_training_mult(gs)
        else:
            focus = training.ai_pick_focus(roster, week_rng)
            gs.training_focus[tid] = focus
            mult = 1.0
        training.apply_training(gs.teams[tid], roster, focus, week_rng, mult)

    # 2b. Physio: extra recovery for the user roster.
    recovery = staff.physio_recovery(gs)
    if recovery > 0:
        for p in gs.roster(gs.user_team_id):
            p.stamina = round(min(100.0, p.stamina + recovery), 1)

    # 2c. Relationships drift; team chemistry chases the pair graph. Every
    # org's chemistry rides its own week's result, not just the user's.
    won_by_team: dict[str, bool] = {}
    for f in report.fixtures:
        if f.played and f.winner_id is not None:
            loser = f.team_b if f.winner_id == f.team_a else f.team_a
            won_by_team[f.winner_id] = True
            won_by_team[loser] = False
    user_fx = next(
        (f for f in report.fixtures if gs.user_team_id in (f.team_a, f.team_b)),
        None,
    )
    relationships.weekly_tick(
        gs, week_rng,
        user_won=bool(user_fx and user_fx.winner_id == gs.user_team_id),
        won_by_team=won_by_team,
    )

    # 3. Finances. The user org's merch/ticket line rides its real
    # win-rate momentum; AI orgs stay at the neutral default.
    for tid in sorted(gs.teams):
        is_user = tid == gs.user_team_id
        cost = staff.weekly_cost(gs) if is_user else 0
        rec = gs.standings.get(tid)
        win_rate = (
            rec.wins / max(rec.wins + rec.losses, 1)
            if is_user and rec is not None
            else 0.5
        )
        income, expenses = apply_weekly_finance(
            gs.teams[tid], gs.roster(tid), staff_cost=cost, win_rate=win_rate
        )
        if is_user:
            report.user_income, report.user_expenses = income, expenses

    # 3b. Sponsorship (user org only): pay the active deal, roll offers.
    user_fixture = next(
        (f for f in report.fixtures if gs.user_team_id in (f.team_a, f.team_b)),
        None,
    )
    user_won = bool(user_fixture and user_fixture.winner_id == gs.user_team_id)
    report.user_income += sponsors.weekly_tick(gs, user_won)
    sponsors.maybe_offer(gs, week_rng)

    # 4. Contracts + transfer window + AI roster upkeep + scouting.
    market.tick_contracts(gs, week_rng)
    market.ai_transfer_window(gs, gd, week_rng)
    market.ai_fill_rosters(gs, gd, week_rng)
    market.ai_poach_free_agents(gs, gd, week_rng)
    _tick_scouting(gs)

    _update_world_ranks(gs)

    # 5. Phase transitions.
    def veto_for(a: str, b: str) -> tuple[list[str], list[str]]:
        return veto_bo3(
            sorted(gd.maps),
            _team_map_mastery(gs, a, sorted(gd.maps)),
            _team_map_mastery(gs, b, sorted(gd.maps)),
            gs.teams[a].tag,
            gs.teams[b].tag,
        )

    n_weeks = regular_season_weeks(TEAMS_PER_REGION)
    season_fixtures = [f for f in gs.fixtures if f.id.startswith(f"s{gs.season}")]

    def _stage_fixtures(stage: str) -> list[Fixture]:
        return [f for f in season_fixtures if f.stage == stage]

    if gs.phase == "regular" and gs.week == n_weeks:
        # Challengers seasons wrap with the franchised leagues: champion
        # by record, a modest prize, and a headline scouts actually read.
        for region in LEAGUE_REGIONS:
            t2 = gs.standings_order(str(region), tier=2)
            if t2:
                champ2 = gs.teams[t2[0]]
                champ2.balance += 25_000
                champ2.reputation = round(min(95.0, champ2.reputation + 2.0), 1)
                best = max(
                    gs.roster(champ2.id),
                    key=lambda p: (gs.player_stats.get(p.id) and gs.player_stats[p.id].rating) or 0.0,
                )
                gs.push_news(
                    f"{champ2.name} win the {str(region).upper()} Challengers "
                    f"season — {best.handle} the standout."
                )
        # Regional playoffs, one bracket per league.
        for region in LEAGUE_REGIONS:
            order = gs.standings_order(str(region))
            _pay_region_prizes(gs, order)
            semis = build_semifinals(order, gs.season, gs.week + 1, veto_for)
            for i, f in enumerate(semis):
                f.id = f"s{gs.season}{str(region)[:2]}semi{i}"
            gs.fixtures.extend(semis)
            top4 = ", ".join(gs.teams[t].name for t in order[:4])
            gs.push_news(f"{str(region).upper()} playoffs set: {top4}.")
        gs.phase = "playoffs"
        report.notes.append("Regular season complete — regional playoffs next week.")
    elif gs.phase == "playoffs":
        semis = _stage_fixtures("semi")
        finals = _stage_fixtures("final")
        qfs = _stage_fixtures("masters_qf")
        msfs = _stage_fixtures("masters_sf")
        mf = next(iter(_stage_fixtures("masters_final")), None)

        if semis and all(f.played for f in semis) and not finals:
            # Regional finals: winners of each region's two semis.
            for region in LEAGUE_REGIONS:
                rsemis = [f for f in semis if f.id.startswith(f"s{gs.season}{str(region)[:2]}")]
                winners = [f.winner_id for f in rsemis if f.winner_id]
                final = build_final(winners, gs.season, gs.week + 1, veto_for)
                final.id = f"s{gs.season}{str(region)[:2]}final"
                gs.fixtures.append(final)
            report.notes.append("Regional finals next week.")
        elif finals and all(f.played for f in finals) and not qfs:
            # Masters: top two per region. Champs seeded by league record;
            # seeds 1-2 bye the QF round.
            champs, runners = [], []
            for region in LEAGUE_REGIONS:
                rf = next(
                    f for f in finals
                    if f.id.startswith(f"s{gs.season}{str(region)[:2]}")
                )
                assert rf.winner_id is not None
                champs.append(rf.winner_id)
                runners.append(
                    rf.team_b if rf.winner_id == rf.team_a else rf.team_a
                )

            def rec_key(tid: str) -> tuple:
                r = gs.standings[tid]
                return (-r.wins, -r.diff, tid)

            champs.sort(key=rec_key)
            runners.sort(key=rec_key)
            seeds = champs + runners  # 1-3 champs, 4-6 runners
            gs.masters_seeds = seeds
            pairs = [(seeds[2], seeds[5]), (seeds[3], seeds[4])]
            for i, (a, b) in enumerate(pairs):
                maps, veto = veto_for(a, b)
                gs.fixtures.append(
                    Fixture(
                        id=f"s{gs.season}mqf{i}",
                        week=gs.week + 1,
                        stage="masters_qf",
                        bracket="masters",
                        best_of=3,
                        team_a=a,
                        team_b=b,
                        maps=maps,
                        veto=veto,
                    )
                )
            names = ", ".join(gs.teams[t].name for t in seeds)
            gs.push_news(f"MASTERS field set: {names}.")
            report.notes.append("Masters begins next week.")
        elif qfs and all(f.played for f in qfs) and not msfs:
            seeds = gs.masters_seeds
            qf_winners = [f.winner_id for f in sorted(qfs, key=lambda f: f.id)]
            pairs = [(seeds[0], qf_winners[1]), (seeds[1], qf_winners[0])]
            for i, (a, b) in enumerate(pairs):
                maps, veto = veto_for(a, b)
                gs.fixtures.append(
                    Fixture(
                        id=f"s{gs.season}msf{i}",
                        week=gs.week + 1,
                        stage="masters_sf",
                        bracket="masters",
                        best_of=3,
                        team_a=a,
                        team_b=b,
                        maps=maps,
                        veto=veto,
                    )
                )
            report.notes.append("Masters semifinals next week.")
        elif msfs and all(f.played for f in msfs) and mf is None:
            winners = [f.winner_id for f in sorted(msfs, key=lambda f: f.id)]
            maps, veto = veto_for(winners[0], winners[1])
            gs.fixtures.append(
                Fixture(
                    id=f"s{gs.season}mfinal",
                    week=gs.week + 1,
                    stage="masters_final",
                    bracket="masters",
                    best_of=5,
                    team_a=winners[0],
                    team_b=winners[1],
                    maps=maps + maps[:2],  # BO5: replay the picks if needed
                    veto=veto,
                )
            )
            report.notes.append("The Masters grand final is next week.")
        elif mf is not None and mf.played and not _stage_fixtures("champ_qf"):
            # Masters resolves; CHAMPIONS — the season-capping second
            # international — is drawn: the six Masters sides plus the two
            # best remaining league records, seeded winner-first.
            assert mf.winner_id is not None
            runner_up = mf.team_b if mf.winner_id == mf.team_a else mf.team_a
            sf_losers = [
                (f.team_b if f.winner_id == f.team_a else f.team_a) for f in msfs
            ]
            pay_playoff_prizes(gs, mf.winner_id, runner_up, sf_losers)
            gs.push_news(f"{gs.teams[mf.winner_id].name} win MASTERS.")

            def rec_key(tid: str) -> tuple:
                r = gs.standings[tid]
                return (-r.wins, -r.diff, tid)

            extras = [
                t for t in gs.standings_order(tier=1) if t not in gs.masters_seeds
            ][:2]
            field = list(gs.masters_seeds) + extras
            rest = sorted(
                (t for t in field if t not in (mf.winner_id, runner_up)),
                key=rec_key,
            )
            seeds = [mf.winner_id, runner_up] + rest
            gs.champions_seeds = seeds
            # Bracket halves: (1v8, 4v5) feed SF0; (2v7, 3v6) feed SF1.
            pairs = [
                (seeds[0], seeds[7]), (seeds[3], seeds[4]),
                (seeds[1], seeds[6]), (seeds[2], seeds[5]),
            ]
            for i, (a, b) in enumerate(pairs):
                maps, veto = veto_for(a, b)
                gs.fixtures.append(
                    Fixture(
                        id=f"s{gs.season}cqf{i}",
                        week=gs.week + 1,
                        stage="champ_qf",
                        bracket="champions",
                        best_of=3,
                        team_a=a,
                        team_b=b,
                        maps=maps,
                        veto=veto,
                    )
                )
            names = ", ".join(gs.teams[t].name for t in seeds)
            gs.push_news(f"CHAMPIONS field set: {names}.")
            report.notes.append("Champions begins next week.")
        elif (
            (cqfs := _stage_fixtures("champ_qf"))
            and all(f.played for f in cqfs)
            and not _stage_fixtures("champ_sf")
        ):
            w = [f.winner_id for f in sorted(cqfs, key=lambda f: f.id)]
            for i, (a, b) in enumerate([(w[0], w[1]), (w[2], w[3])]):
                maps, veto = veto_for(a, b)
                gs.fixtures.append(
                    Fixture(
                        id=f"s{gs.season}csf{i}",
                        week=gs.week + 1,
                        stage="champ_sf",
                        bracket="champions",
                        best_of=3,
                        team_a=a,
                        team_b=b,
                        maps=maps,
                        veto=veto,
                    )
                )
            report.notes.append("Champions semifinals next week.")
        elif (
            (csfs := _stage_fixtures("champ_sf"))
            and all(f.played for f in csfs)
            and not _stage_fixtures("champ_final")
        ):
            w = [f.winner_id for f in sorted(csfs, key=lambda f: f.id)]
            maps, veto = veto_for(w[0], w[1])
            gs.fixtures.append(
                Fixture(
                    id=f"s{gs.season}cfinal",
                    week=gs.week + 1,
                    stage="champ_final",
                    bracket="champions",
                    best_of=5,
                    team_a=w[0],
                    team_b=w[1],
                    maps=maps + maps[:2],
                    veto=veto,
                )
            )
            report.notes.append("The CHAMPIONS grand final is next week.")
        elif (
            cf := next(iter(_stage_fixtures("champ_final")), None)
        ) is not None and cf.played:
            assert cf.winner_id is not None
            cf_runner = cf.team_b if cf.winner_id == cf.team_a else cf.team_a
            csfs = _stage_fixtures("champ_sf")
            cqfs = _stage_fixtures("champ_qf")
            gs.teams[cf.winner_id].balance += 500_000
            gs.teams[cf.winner_id].reputation = round(
                min(99.0, gs.teams[cf.winner_id].reputation + 6.0), 1
            )
            gs.teams[cf_runner].balance += 250_000
            for f in csfs:
                loser = f.team_b if f.winner_id == f.team_a else f.team_a
                gs.teams[loser].balance += 120_000
            for f in cqfs:
                loser = f.team_b if f.winner_id == f.team_a else f.team_a
                gs.teams[loser].balance += 60_000
            champ = gs.teams[cf.winner_id]
            gs.champions.append(
                ChampionRecord(
                    season=gs.season, team_id=champ.id, team_name=champ.name
                )
            )
            gs.push_news(
                f"{champ.name} win CHAMPIONS — Season {gs.season} world champions!"
            )
            gs.phase = "offseason"
            report.notes.append(
                f"{champ.name} are world champions. Offseason next week."
            )

    # 6. News (before the week label moves on).
    narrative.weekly_news(gs, report, week_kills)

    # 7. Inbox: aggregate the week's outcomes into the notification feed.
    # Runs last so it can read every subsystem's artifacts (news included),
    # and before the week label moves on so this-week news is still labelled.
    inbox.generate_inbox(gs, report)

    gs.week += 1
    return report


def _pay_region_prizes(gs: GameState, order: list[str]) -> None:
    """Regional-league placement money (top half). Masters money is paid
    separately via pay_playoff_prizes when the world final resolves."""
    scale = [120_000, 70_000, 40_000, 25_000]
    for i, tid in enumerate(order[: len(scale)]):
        gs.teams[tid].balance += scale[i]
    leader = gs.teams[order[0]]
    gs.push_news(
        f"{leader.name} top the {str(leader.region).upper()} regular season "
        f"({scale[0]:,} cr)."
    )


def _aggregate_stats(gs: GameState, f: Fixture, stats, week_kills: dict) -> None:
    """Fold one map's MatchStats into the season aggregates."""
    n_rounds = len(stats.rounds)
    rosters = {tid: set(gs.teams[tid].player_ids) for tid in (f.team_a, f.team_b)}

    for tid in (f.team_a, f.team_b):
        ts = gs.team_stats.setdefault(tid, TeamSeasonStats())
        ts.maps += 1
        for i, r in enumerate(stats.rounds):
            attacking = r.attacking_team_id == tid
            won = r.winner_id == tid
            if attacking:
                ts.atk_rounds += 1
                ts.atk_won += int(won)
            else:
                ts.def_rounds += 1
                ts.def_won += int(won)
            if r.round_num in (1, 13):
                ts.pistols += 1
                ts.pistols_won += int(won)
        for pid in sorted(rosters[tid]):
            ps = gs.player_stats.setdefault(pid, PlayerSeasonStats())
            ps.maps += 1
            ps.rounds += n_rounds
            line = stats.lines.get(pid)
            if line is None:
                continue
            ps.kills += line.kills
            ps.deaths += line.deaths
            ps.first_kills += line.first_kills
            ps.trade_kills += line.trade_kills
            ps.headshots += line.headshots
            ps.plants += line.plants
            ps.defuses += line.defuses
            ps.first_deaths += line.first_deaths
            ps.multikills += line.multikills
            ps.aces += line.aces
            ps.clutches += line.clutches
            ps.rating_sum += line.rating
            week_kills[pid] = week_kills.get(pid, 0) + line.kills


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
        team_of = {
            pid: tid
            for tid in (f.team_a, f.team_b)
            for pid in rt_gd.teams[tid].player_ids
        }
        stats = compute_match_stats(res.events, team_of)
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


def _team_map_mastery(
    gs: GameState, tid: str, map_ids: list[str]
) -> dict[str, float]:
    """Roster-average per-map mastery, defaulting to 50 for unknown maps."""
    roster = gs.roster(tid)
    out: dict[str, float] = {}
    for m in map_ids:
        vals = [
            next((mp.mastery for mp in p.map_pool if mp.map_id == m), 50.0)
            for p in roster
        ]
        out[m] = sum(vals) / len(vals) if vals else 50.0
    return out


SCOUT_WEEKLY_GAIN = 0.34  # ~3 weeks of scouting for full knowledge


def _tick_scouting(gs: GameState) -> None:
    """Advance whatever the scout watches: a rival team, or the open
    market ("market" — free agents and prospects, EHM-style)."""
    target = gs.scout_target
    if not target:
        return
    if target != "market" and target not in gs.teams:
        return
    cur = gs.scout_progress.get(target, 0.0)
    gain = (
        SCOUT_WEEKLY_GAIN
        * staff.scout_multiplier(gs)
        * economy.facility_scout_mult(gs)
    )
    # The market is a bigger beat than one team: slower coverage.
    if target == "market":
        gain *= 0.6
    after = min(1.0, round(cur + gain, 2))
    gs.scout_progress[target] = after
    if after >= 1.0 and cur < 1.0:
        label = (
            "the free-agent market"
            if target == "market"
            else gs.teams[target].name
        )
        gs.push_news(f"Scouting report on {label} complete.")


def _update_world_ranks(gs: GameState) -> None:
    def key(tid: str) -> tuple:
        r = gs.standings.get(tid, TeamRecord())
        return (-r.wins, -r.diff, -gs.teams[tid].reputation, tid)

    for rank, tid in enumerate(sorted(gs.teams, key=key), start=1):
        gs.teams[tid].world_rank = rank


# ---------------------------------------------------------------------------
# Offseason


def _process_retirements(gs: GameState, rng) -> int:
    """Roll every player against their retirement odds. Rosters lose the
    player on the spot (AI refills next tick; the user gets a news warning
    and an open seat)."""
    from esports_sim.manager.state import RetiredRecord

    retiring: list[str] = []
    for pid in sorted(gs.players):
        if rng.random() < development.retirement_prob(gs.players[pid]):
            retiring.append(pid)

    notable: list[str] = []
    for pid in retiring:
        p = gs.players[pid]
        team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
        if team is not None:
            team.player_ids.remove(pid)
            if team.captain_id == pid:
                team.captain_id = team.player_ids[0] if team.player_ids else None
            if team.id == gs.user_team_id:
                gs.push_news(
                    f"{p.handle} retires — your roster has an open seat."
                )
        if pid in gs.free_agent_ids:
            gs.free_agent_ids.remove(pid)
        ca = development.overall(p)
        gs.retired.append(
            RetiredRecord(
                season=gs.season,
                handle=p.handle,
                real_name=p.real_name,
                age=p.age,
                team_name=team.name if team else "",
                peak_note=f"retired at {ca:.0f} CA",
            )
        )
        if ca >= 62 or p.age >= 31:
            notable.append(f"{p.handle} ({p.age})")
        del gs.players[pid]
    del gs.retired[:-40]

    if notable:
        rest = len(retiring) - len(notable)
        tail = f" and {rest} others" if rest > 0 else ""
        gs.push_news(
            f"Retirements: {', '.join(notable[:4])}{tail} call it a career."
        )
    elif retiring:
        gs.push_news(f"{len(retiring)} players quietly retire over the break.")
    return len(retiring)


def _rookie_classes(gs: GameState, gd: GameData, rng, n_retired: int) -> None:
    """Each region graduates a rookie class into free agency — the talent
    pipeline that replaces retiring careers. Class size breathes with how
    many careers just ended."""
    from esports_sim.manager.gen import _FA_SLOTS, generate_player

    per_region = 2 + max(0, n_retired) // (len(LEAGUE_REGIONS) * 2)
    headliners: list[str] = []
    for region in LEAGUE_REGIONS:
        for _ in range(per_region):
            style, role = _FA_SLOTS[gs.fa_counter % len(_FA_SLOTS)]
            gs.fa_counter += 1
            pid = f"fa_gen_{gs.fa_counter}"
            quality = float(rng.uniform(40, 58))
            p = generate_player(
                rng, pid, style, role, quality, gd,
                region=region, age_lo=17, age_hi=20,
            )
            p.contract_weeks_left = 0
            p.personality_tags = sorted({*p.personality_tags, "rookie"})
            gs.players[pid] = p
            gs.free_agent_ids.append(pid)
            if development.potential_of(p) >= 78:
                headliners.append(f"{p.handle} ({str(region)[:2].upper()})")
    if headliners:
        gs.push_news(
            f"Season {gs.season + 1} rookie class arrives — scouts circle "
            f"{', '.join(headliners[:3])}."
        )
    else:
        gs.push_news(f"Season {gs.season + 1} rookie class enters free agency.")


def _assign_ai_tactics(gs: GameState, rng) -> None:
    """Every AI coach stamps an identity on their team, derived from the
    roster they actually have (re-derived each season — rosters change).
    The user's dials are never touched."""
    for tid in sorted(gs.teams):
        if tid == gs.user_team_id:
            continue
        roster = gs.roster(tid)
        if not roster:
            continue
        tac = gs.teams[tid].tactics
        avg_reac = sum(p.attr("aim_reactivity") for p in roster) / len(roster)
        entries = [
            p for p in roster if str(p.playstyle) in ("entry", "awper")
        ]
        entry_q = (
            sum(market.player_quality(p) for p in entries) / len(entries)
            if entries
            else 50.0
        )
        igl_sense = max(
            (p.attr("game_sense") for p in roster if str(p.playstyle) == "igl"),
            default=55.0,
        )
        clamp = lambda v: float(np.clip(v, 15.0, 85.0))  # noqa: E731
        tac.aggression = round(clamp(50 + (avg_reac - 60) * 0.8 + rng.normal(0, 8)), 1)
        tac.pace = round(clamp(50 + (entry_q - 60) * 0.7 + rng.normal(0, 8)), 1)
        tac.util_discipline = round(clamp(igl_sense * 0.8 + rng.normal(0, 8)), 1)
        tac.eco_greed = round(clamp(50 + rng.normal(0, 12)), 1)
        # Map control tracks the IGL's read of the game: sharp IGLs spread
        # and lurk for picks, blunt ones stack and hit as five.
        tac.map_control = round(clamp(50 + (igl_sense - 55) * 0.6 + rng.normal(0, 9)), 1)
        tac.site_focus = (
            "balanced"
            if rng.random() < 0.65
            else str(rng.choice(["a", "b", "c"]))
        )


def _run_offseason(gs: GameState, gd: GameData) -> WeekReport:
    report = WeekReport(season=gs.season, week=gs.week, phase="offseason")
    tree = RngTree(gs.seed)
    rng = tree.derive("season", gs.season, "offseason")

    # Awards first — they read the season aggregates being retired.
    for a in narrative.season_awards(gs):
        report.notes.append(f"{a.award}: {a.handle} ({a.team_name}) — {a.value}")
    gs.player_stats = {}
    gs.team_stats = {}

    for pid in sorted(gs.players):
        training.apply_offseason_aging(gs.players[pid], rng)

    # Careers end: a year older, some hang it up. Then the next
    # generation arrives as regional rookie classes.
    n_retired = _process_retirements(gs, rng)
    _rookie_classes(gs, gd, rng, n_retired)

    # Refresh the free-agent pool: cull the weakest journeymen (rookies
    # are exempt — prospects deserve a season on the market).
    fas = sorted(
        (
            pid
            for pid in gs.free_agent_ids
            if gs.players[pid].age >= 21
        ),
        key=lambda pid: market.player_quality(gs.players[pid]),
    )
    while len(gs.free_agent_ids) > 20 and fas:
        cut = fas.pop(0)
        gs.free_agent_ids.remove(cut)
        del gs.players[cut]

    # New season. Scouting knowledge goes stale over the break; the staff
    # candidate market refreshes.
    gs.scout_progress = {}
    gs.masters_seeds = []
    gs.champions_seeds = []
    gs.transfer_offers = []
    gs.season += 1
    staff.refresh_candidates(gs)
    gs.week = 1
    gs.phase = "regular"
    _assign_ai_tactics(gs, rng)  # new rosters, new coaching identities
    gs.fixtures = _build_all_leagues(gs.teams, sorted(gd.maps), gs.season)
    gs.standings = {tid: TeamRecord() for tid in gs.teams}
    gs.push_news(f"Season {gs.season} begins.")
    report.notes.append(f"Offseason complete — Season {gs.season} starts now.")
    _update_world_ranks(gs)
    # Inbox for the offseason tick: retirements, rookie class, award slate.
    # `report` still carries the pre-rollover (season, week) the offseason
    # news was labelled with, so generate_inbox reads the right lines.
    inbox.generate_inbox(gs, report)
    return report
