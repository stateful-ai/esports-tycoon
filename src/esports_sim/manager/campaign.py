"""Campaign orchestration: new game, weekly advance, playoffs, offseason.

`advance_week` is the single tick of the management layer. Everything it
does derives randomness from the campaign seed + (season, week) labels, so
a save can be replayed and two campaigns with the same seed and the same
user decisions are identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import hashlib

import numpy as np

from esports_sim import perf

from esports_sim.manager import (
    academy,
    badges,
    career,
    chronicle,
    culture,
    development,
    economy,
    flavor_events,
    hof,
    inbox,
    knowledge,
    market,
    meta,
    narrative,
    preparation,
    relationships,
    role_fit,
    rivalries,
    social,
    sponsors,
    staff,
    series_management,
    telemetry,
    training,
)
from esports_sim.manager.economy import (
    apply_weekly_finance,
    pay_playoff_prizes,
)
from esports_sim.schemas.common import Region
from esports_sim.registry.rosters import RosterPack
from esports_sim.manager.gen import (
    assign_identity as gen_assign_identity,
    backfill_agent_baselines,
    generate_free_agents,
    generate_league_teams,
)
from esports_sim.manager.schedule import (
    build_final,
    build_regular_season,
    build_semifinals,
    regular_season_weeks,
    veto_bo3,
)
from esports_sim.manager.state import (
    PRIZE_CHAMPION,
    PRIZE_CHAMPIONS_QF_LOSER,
    PRIZE_CHAMPIONS_RUNNER_UP,
    PRIZE_CHAMPIONS_SF_LOSER,
    PRIZE_CHAMPIONS_WINNER,
    PRIZE_REGIONAL_CHAMPION,
    PRIZE_REGIONAL_FINAL_LOSER,
    PRIZE_REGIONAL_SEMI_LOSER,
    ChampionRecord,
    DevSnap,
    Fixture,
    GamePlan,
    GameState,
    MapMetaStats,
    MapResult,
    MatchReview,
    PlayerLineSnap,
    PlayerSeasonStats,
    StatSnap,
    TeamMapStats,
    TeamRecord,
    TeamSeasonStats,
)
from esports_sim.registry.loader import GameData
from esports_sim.rng.tree import RngTree
from esports_sim.manager.match_review import build_match_review
from esports_sim.sim import simulate_match_result
from esports_sim.sim import tactics_fit
from esports_sim.policy.base import CoachProfile
from esports_sim.sim.engine import TeamMatchPlan
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
    # Per human manager (team id -> weekly income/expenses). `user_income` /
    # `user_expenses` mirror the PRIMARY human for back-compat; the web layer
    # reads income_by/expenses_by for the manager actually being served.
    income_by: dict[str, int] = field(default_factory=dict)
    expenses_by: dict[str, int] = field(default_factory=dict)
    user_income: int = 0
    user_expenses: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# New game


# The default VCT-style world: three regional leagues of 8; their top two
# meet at Masters after the regional playoffs. Underneath, a 6-team
# Challengers circuit per region develops prospects — fully simulated,
# never broadcast. A roster pack can reshape all three numbers (its world
# block is copied onto GameState, which the season state machine reads).
LEAGUE_REGIONS = [Region.AMERICAS, Region.EMEA, Region.PACIFIC]
TEAMS_PER_REGION = 8
TIER2_PER_REGION = 6


def _build_all_leagues(
    gs_teams: dict, map_ids: list[str], season: int, regions: list[Region]
) -> list:
    """One double round-robin per (region, tier), weeks aligned so every
    league plays the same calendar. Challengers (fewer teams) wraps before
    the franchised leagues."""
    fixtures = []
    for region in regions:
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


def new_campaign(
    gd: GameData,
    seed: int,
    user_team_id: str = "team_nexus",
    pack: "RosterPack | None" = None,
    mode: str = "sandbox",
    manager_name: str = "",
    career_offer=None,
) -> GameState:
    """Build season 1. With a roster pack, the pack's teams/players replace
    the fictional starters and its world block sets the league shape;
    generation only fills any shortfall, so a partial pack still plays.

    `mode` picks the game: "sandbox" (classic — no contracts, never
    fired) or "legacy" (career offers, board goals, dismissal;
    manager/career.py). `career_offer` carries the accepted CareerOffer
    in legacy mode so the seat's contract matches what the lobby showed."""
    rng = RngTree(seed).derive("campaign", "gen")

    if pack is not None:
        regions = list(pack.meta.world.league_regions)
        teams_per_region = pack.meta.world.teams_per_region
        tier2_per_region = pack.meta.world.tier2_per_region
        base_teams, base_players = pack.teams, pack.players
    else:
        regions = list(LEAGUE_REGIONS)
        teams_per_region = TEAMS_PER_REGION
        tier2_per_region = TIER2_PER_REGION
        base_teams, base_players = gd.teams, gd.players

    teams = {tid: t.model_copy(deep=True) for tid, t in base_teams.items()}
    players = {pid: p.model_copy(deep=True) for pid, p in base_players.items()}

    used_names: set[str] = {t.name for t in teams.values()}
    for region in regions:
        have = sum(
            1 for t in teams.values() if t.region == region and t.tier == 1
        )
        have2 = sum(
            1 for t in teams.values() if t.region == region and t.tier == 2
        )
        gen_teams, gen_players = generate_league_teams(
            rng, gd, n_teams=teams_per_region - have,
            region=region, used_names=used_names,
        )
        t2_teams, t2_players = generate_league_teams(
            rng, gd, n_teams=tier2_per_region - have2,
            region=region, used_names=used_names, tier=2,
        )
        for t in gen_teams + t2_teams:
            teams[t.id] = t
        for p in gen_players + t2_players:
            players[p.id] = p

    # Pack worlds seed the FA pool with REAL unrostered players (benched
    # pros, org-less veterans, notable names); generation only tops up any
    # shortfall so the market still has some fictional depth.
    pack_fas: list = []
    future_prospects = {}
    if pack is not None and pack.free_agents:
        for pid in sorted(pack.free_agents):
            p = pack.free_agents[pid].model_copy(deep=True)
            p.contract_weeks_left = 0
            players[p.id] = p
            pack_fas.append(p)
    if pack is not None and pack.future_prospects:
        future_prospects = {
            pid: prospect.model_copy(deep=True)
            for pid, prospect in sorted(pack.future_prospects.items())
        }
    fas = generate_free_agents(rng, gd, n=max(4, 18 - len(pack_fas)))
    for p in fas:
        players[p.id] = p
    fas = pack_fas + fas

    # Authored players (YAML starters / roster packs) carry only their 2-3
    # signature agents — top the sheet up to the full cast so nobody reads
    # as "never played" on the rest of their role, and give everyone a
    # country + spoken languages (comms cohesion input). Hash-based
    # (draw-free) and idempotent; generated players already have both.
    for p in players.values():
        backfill_agent_baselines(p, gd)
        gen_assign_identity(p)

    # Rostered players open the campaign with a real history at their club
    # (12-102 weeks, stable per player) — day-one rosters are settled squads,
    # not a league of brand-new signings, so loyalty premiums vary from the
    # start and the AI churn protections don't freeze week-one management.
    # Free agents stay at 0. Hash-based: no rng stream is touched.
    rostered = {pid for t in teams.values() for pid in t.player_ids}
    for pid in rostered:
        p = players[pid]
        p.tenure_weeks = 12 + int(
            (int.from_bytes(
                hashlib.blake2b(f"{pid}|tenure".encode(), digest_size=8).digest(),
                "big",
            ) % 91)
        )

    gs = GameState(
        seed=seed,
        user_team_id=user_team_id,
        game_mode=mode,
        league_regions=regions,
        teams_per_region=teams_per_region,
        tier2_per_region=tier2_per_region,
        roster_pack=pack.id if pack is not None else None,
        calendar_year=pack.meta.start_year if pack is not None else None,
        teams=teams,
        players=players,
        free_agent_ids=[p.id for p in fas],
        future_prospects=future_prospects,
        fixtures=_build_all_leagues(teams, sorted(gd.maps), 1, regions),
        standings={tid: TeamRecord() for tid in teams},
        training_focus={tid: "tactical" for tid in teams},
    )
    career.create_seat(gs, user_team_id, manager_name, offer=career_offer)
    gs.push_news(
        f"Season 1 begins — {len(regions)} regional leagues of "
        f"{teams_per_region}, {regular_season_weeks(teams_per_region)} weeks "
        f"of league play, then playoffs and Masters."
    )
    staff.seed_pool(gs)
    social.seed_followers(gs)
    # Seed realistic complete contracts after audience sizes exist. The same
    # quality order already supplies default_five, so role labels document the
    # existing depth chart rather than changing who plays.
    for tid in sorted(gs.teams):
        team = gs.teams[tid]
        starters = set(default_five(gs, tid))
        for pid in team.player_ids:
            p = gs.players[pid]
            role = (
                "starter" if pid in starters
                else "academy" if p.age <= 20
                else "bench"
            )
            market.seed_existing_contract_terms(gs, tid, p, role)
    social.seed_stream_load(gs)  # follower-driven streaming load, from week 1
    academy.seed_affiliates(gs)
    culture.ensure_leadership(gs)
    _assign_ai_tactics(gs, rng)
    _update_world_ranks(gs)
    _snapshot_season_start_ca(gs)
    _record_dev_snapshots(gs, week=0)
    return gs


# ---------------------------------------------------------------------------
# Runtime GameData view: static registries + live campaign rosters


def runtime_gamedata(gs: GameState, gd: GameData) -> GameData:
    """Static registries + live campaign rosters. Live balance patches are
    applied HERE — a fresh agents dict, never a mutation of the shared
    registry — so campaign matches play the patched meta while the
    bare-engine gates (which load the registry directly) never see it."""
    return GameData(
        attributes=gd.attributes,
        agents=meta.apply_patches(gd.agents, gs.agent_patches),
        weapons=gd.weapons,
        maps=gd.maps,
        teams=gs.teams,
        players=gs.players,
    )


def _resolve_five(
    gs: GameState,
    team_id: str,
    primary: list[str],
    eligible: list[str] | None = None,
) -> list[str]:
    """Resolve exactly five dressed players: honour `primary` (an ordered lineup
    preference) first, filtering stale ids, then top up with the best remaining
    players by quality. Assumes the roster has more than five (callers short-
    circuit at five-or-fewer). Order is irrelevant — the engine re-sorts by id."""
    roster = list(eligible if eligible is not None else gs.teams[team_id].player_ids)
    chosen: list[str] = []
    seen: set[str] = set()
    for pid in primary:
        if pid in roster and pid not in seen:
            chosen.append(pid)
            seen.add(pid)
            if len(chosen) == market.ROSTER_SIZE:
                return chosen
    for pid in sorted(
        roster, key=lambda q: (-market.player_quality(gs.players[q]), q)
    ):
        if pid not in seen:
            chosen.append(pid)
            seen.add(pid)
            if len(chosen) == market.ROSTER_SIZE:
                break
    return chosen


def default_five(gs: GameState, team_id: str) -> list[str]:
    """The team's default dressed five (its saved `lineup_ids`, topped up by
    quality). Everyone plays when the roster is five or fewer."""
    roster = list(gs.teams[team_id].player_ids)
    if len(roster) <= market.ROSTER_SIZE:
        return roster
    return _resolve_five(gs, team_id, gs.teams[team_id].lineup_ids)


def dressed_for(
    gs: GameState, team_id: str, fixture: Fixture, map_id: str
) -> list[str]:
    """The exactly-five players a team dresses for one map. A roster of five or
    fewer dresses everyone (this is what keeps the match/balance gates
    byte-identical). Deeper rosters resolve, in order of precedence: a per-map
    lineup override, then the team's default `lineup_ids`, then a top-up of the
    best remaining players by quality.

    The engine re-sorts the roster by id, so the returned order is irrelevant to
    match output — only the SET of five matters."""
    roster = series_management.eligible_pool(gs, team_id, fixture)
    if len(roster) <= market.ROSTER_SIZE:
        return roster
    key = f"{team_id}|{fixture.id}|{map_id}"
    primary = gs.map_lineups.get(key) or gs.teams[team_id].lineup_ids
    return _resolve_five(gs, team_id, primary, roster)


def _dressed_gamedata(
    gs: GameState, gd: GameData, dressed: dict[str, list[str]]
) -> GameData:
    """A per-map runtime view where the two competing teams expose only their
    dressed five. Non-mutating: `gs.teams` is untouched; the two Team objects
    are shallow copies with overridden `player_ids`."""
    teams = dict(gs.teams)
    for tid, pids in dressed.items():
        teams[tid] = gs.teams[tid].model_copy(update={"player_ids": list(pids)})
    # A player keeps their raw attributes in GameState. The match only sees a
    # derived view: job-weighted ability plus the execution cost of unfamiliar
    # role/style assignments. This makes the hidden rating mechanically real
    # without rewriting development, scouting, or roster data.
    players = dict(gs.players)
    for pids in dressed.values():
        for pid in pids:
            player = gs.players[pid]
            raw = development.overall(player)
            delta = role_fit.current_ability(player) - raw
            if abs(delta) > 1e-9:
                players[pid] = player.model_copy(update={
                    "attributes": {
                        attr: max(1.0, min(99.0, value + delta))
                        for attr, value in player.attributes.items()
                    }
                })
    return GameData(
        attributes=gd.attributes,
        agents=gd.agents,
        weapons=gd.weapons,
        maps=gd.maps,
        teams=teams,
        players=players,
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
    # Observability: phase checkpoints for this tick. Write-only wall-clock
    # sink (see esports_sim.perf) — nothing here reads it, so determinism
    # is untouched.
    _cp = perf.Checkpoints()

    # Heal pre-baseline saves: players authored before full mastery sheets
    # (or before countries/languages existed) top up here. Hash-based and
    # idempotent (no-op once full), so campaign determinism is untouched —
    # a fresh campaign is already full.
    for p in gs.players.values():
        backfill_agent_baselines(p, gd)
        gen_assign_identity(p)
    if not gs.academy_affiliates:
        academy.seed_affiliates(gs)
    culture.ensure_leadership(gs)
    _cp.mark("heal")

    if gs.phase == "offseason":
        return _run_offseason(gs, gd)

    report = WeekReport(season=gs.season, week=gs.week, phase=gs.phase)
    tree = RngTree(gs.seed)
    week_rng = tree.derive("season", gs.season, "week", gs.week, "weekly")

    # 0. Mid-split balance patch — BEFORE matches (and before rt_gd is
    # built), so this week's games and their replays run on the new meta.
    # The second patch of the year ships in the offseason. The split's
    # midpoint is derived from the fixtures actually on the calendar, not
    # the module's default world shape — roster-pack worlds (a different
    # teams-per-region) get the right week for free.
    season_len = max(
        (f.week for f in gs.fixtures if f.stage == "regular" and f.tier == 1),
        default=0,
    )
    if gs.phase == "regular" and season_len > 0 and gs.week == season_len // 2 + 1:
        note = meta.roll_patch(
            gs, gd,
            tree.derive("season", gs.season, "patch", "mid"),
            version=f"{gs.season}.{gs.week:02d}",
        )
        if note is not None:
            report.notes.append(f"Patch {note.version} shakes the meta.")
            knowledge.on_patch(gs)  # setups date when the numbers move

    rt_gd = runtime_gamedata(gs, gd)

    # Manager-booked scrims/bootcamps resolve before kickoff. A dedicated RNG
    # stream only selects restrained report phrasing; all gameplay effects are
    # stored campaign tradeoffs and organizational knowledge.
    preparation.weekly_tick(
        gs, tree.derive("season", gs.season, "week", gs.week, "preparation")
    )
    series_management.auto_directives(gs)

    # 1. Matches. Challengers games sim fully (development, stats,
    # scouting) but never capture replay logs — nobody broadcasts tier 2.
    week_fixtures = gs.fixtures_for_week()
    week_kills: dict[str, int] = {}
    week_perf: dict[str, dict] = {}  # pid -> this week's tallies (snapshots)
    # tid -> everyone who dressed at least one map this week. Drives the
    # bench treatment below: with per-map overrides a rotated-in player is
    # NOT benched even though they sit outside the default five.
    week_dressed: dict[str, set[str]] = {}
    for f in sorted(week_fixtures, key=lambda x: x.id):
        _sim_fixture(
            gs, rt_gd, tree, f,
            collector=report.match_stats,
            events_out=None if f.tier == 2 else events_out,
        )
        report.fixtures.append(f)
        # Each played map's stats line up with f.results in order. Recompute the
        # dressed five per map (rosters haven't moved yet this tick) so only the
        # players who actually took the map get maps/rounds credited — and
        # only they bank match experience (playing time IS development).
        for map_res, stats in zip(f.results, report.match_stats.get(f.id, [])):
            dressed = {
                tid: set(dressed_for(gs, tid, f, map_res.map_id))
                for tid in (f.team_a, f.team_b)
            }
            for tid, pids in dressed.items():
                week_dressed.setdefault(tid, set()).update(pids)
            _aggregate_stats(gs, f, stats, week_kills, dressed, week_perf)
            _apply_match_development(gs, stats)

    # First professional appearances (pending rookies only) go into the
    # chronicle while the week's dressed sets are still in hand.
    chronicle.record_debuts(gs, week_dressed)

    # The academy is the existing simulated Challengers affiliate, so its
    # bounded coaching gain reads the tier-2 results that just actually played.
    academy.weekly_tick(gs)

    # Per-map lineups are single-use: drop the entries for fixtures just played
    # so `map_lineups` can't grow unbounded across a season.
    _played_ids = {f.id for f in week_fixtures}
    gs.map_lineups = {
        k: v
        for k, v in gs.map_lineups.items()
        if k.split("|", 2)[1] not in _played_ids
    }

    _cp.mark("matches")

    # Assignment comfort is earned through a week of preparation and matches.
    # It is deliberately after this week's fixtures, so a last-minute switch
    # cannot be fully comfortable on the same match day.
    for p in gs.players.values():
        role_fit.build_comfort(p)
    for tid, team in gs.teams.items():
        role_fit.build_igl_experience(team, week_dressed.get(tid, set()))

    # 2. Training (human focus is whatever each manager set; AI picks its own,
    # and each human's coach/facility multiplier comes from their own org).
    for tid in sorted(gs.teams):
        roster = gs.roster(tid)
        if gs.is_human(tid):
            gs.set_acting(tid)
            focus = gs.training_focus.get(tid, "tactical")
            mult = (
                staff.coach_multiplier(gs, focus)
                * economy.facility_training_mult(gs)
                * career.philosophy_training_mult(gs, tid)
            )
        else:
            focus = training.ai_pick_focus(roster, week_rng, gs.teams[tid])
            gs.training_focus[tid] = focus
            mult = 1.0
        training.apply_training(
            gs.teams[tid], roster, focus, week_rng, mult,
            mentor_mults=_mentor_mults(gs, tid),
            support_bonuses=_development_support_bonuses(gs, tid),
            language_rate=staff.language_learning_rate(gs) if gs.is_human(tid) else 0.0,
            scout_guidance=_active_scout_guidance(gs, tid),
        )
    gs.set_acting(None)

    # 2a'. Mentorship, the CEILING half: a valid, manager-set mentorship slowly
    # raises the protege's ceiling on the mentor's best skills (a great aimer
    # lifts a young player's aim ceiling), gated by the mentor's hidden
    # mentor_skill. gs.mentorships is empty in hands-off sims, so this is a
    # no-op there and the balance gates stay byte-identical.
    development.apply_mentorship_growth(gs)

    # 2b. Backroom department effects, per human org: physio restores
    # stamina; psychologist pulls shaken confidence back toward neutral;
    # performance coach does the same for slumped form. The department
    # roles are pulls toward 50, never boosts past it — support staff
    # steady a roster, they don't inflate one.
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        recovery = staff.physio_recovery(gs)
        support = staff.confidence_support(gs)
        upkeep = staff.form_upkeep(gs)
        for p in gs.roster(tid):
            if recovery > 0:
                p.stamina = round(min(100.0, p.stamina + recovery), 1)
            if support > 0 and p.confidence < 50.0:
                p.confidence = round(min(50.0, p.confidence + support), 1)
            if upkeep > 0 and p.form < 50.0:
                p.form = round(min(50.0, p.form + upkeep), 1)
    gs.set_acting(None)

    # 2b'. Bench minutes: players who did NOT dress a single map this week
    # (while the team played) scrim instead — a fraction of real reps,
    # fresher legs, and (for anyone good enough to start elsewhere) a
    # weekly reminder that they want minutes. Keyed off who ACTUALLY
    # dressed, so a per-map rotation counts as minutes and a default-five
    # player who sat via overrides is treated as benched. Bye weeks apply
    # no bench treatment — nobody was denied minutes.
    _apply_bench_week(gs, week_dressed)

    # 2b''. Development events: the random texture of a career (breakouts,
    # slumps, tweaked wrists, viral clips). Own rng stream so the rest of
    # the week's draws never shift; effects apply to every org (AI parity),
    # news lines only to the owning human manager.
    dev_events = development.weekly_dev_events(
        gs, tree.derive("season", gs.season, "week", gs.week, "devevents")
    )

    # 2b'''. Mental momentum: tilt spirals and heaters — threshold events
    # on top of the smooth per-map confidence movement. Own stream
    # ("tilt"), AI parity like dev events, fed to the social layer below.
    mental_events = development.weekly_mental_events(
        gs, tree.derive("season", gs.season, "week", gs.week, "tilt")
    )

    # 2b''''. Badges: roll match-performance + negative badges from this week's
    # box scores and dev events. Dedicated "badges" stream so no match/other
    # draw ever shifts; title-winning rosters also roll (in the phase machine
    # below, off this same weekly stream). Every org (AI parity).
    badge_rng = tree.derive("season", gs.season, "week", gs.week, "badges")
    badges.weekly_feats(gs, badge_rng, report, dev_events)

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
    culture.ai_manage(gs)
    culture.weekly_tick(
        gs, tree.derive("season", gs.season, "week", gs.week, "culture")
    )

    _cp.mark("training_dev")

    # 3. Finances. Each human org's merch/ticket line rides its real win-rate
    # momentum and pays its own staff; AI orgs stay at the neutral default.
    for tid in sorted(gs.teams):
        is_human = gs.is_human(tid)
        if is_human:
            gs.set_acting(tid)
        cost = staff.weekly_cost(gs) if is_human else 0
        rec = gs.standings.get(tid)
        win_rate = (
            rec.wins / max(rec.wins + rec.losses, 1)
            if is_human and rec is not None
            else 0.5
        )
        income, expenses = apply_weekly_finance(
            gs.teams[tid], gs.roster(tid), staff_cost=cost, win_rate=win_rate
        )
        if is_human:
            report.income_by[tid] = income
            report.expenses_by[tid] = expenses
    gs.set_acting(None)

    # 3b. Sponsorship (per human org): pay the active deal, roll offers.
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        fx = gs.team_fixture(tid)
        won = bool(fx and fx.winner_id == tid)
        report.income_by[tid] = report.income_by.get(tid, 0) + sponsors.weekly_tick(
            gs, won
        )
        sponsors.maybe_offer(gs, week_rng)
    gs.set_acting(None)

    # Primary human mirrors into the legacy single-manager report fields.
    primary = gs.user_team_id
    report.user_income = report.income_by.get(primary, 0)
    report.user_expenses = report.expenses_by.get(primary, 0)

    _cp.mark("finances")

    # 4. Contracts + transfer window + AI roster upkeep + scouting.
    market.tick_contracts(gs, week_rng)
    academy.ai_manage(gs)
    market.ai_transfer_window(gs, gd, week_rng)
    market.ai_fill_rosters(gs, gd, week_rng)
    market.ai_poach_free_agents(gs, gd, week_rng)
    _tick_scouting(gs, report)

    # 4b. Stale game plans (fixture gone or already played — the consumed
    # case is handled at sim time in _sim_fixture) quietly expire.
    for tid in sorted(list(gs.game_plans_by)):
        plan = gs.game_plans_by[tid]
        fx = next((x for x in gs.fixtures if x.id == plan.fixture_id), None)
        if fx is None or fx.played:
            del gs.game_plans_by[tid]

    _update_world_ranks(gs)

    _cp.mark("market_scouting")

    # 5. Phase transitions.
    def veto_for(a: str, b: str) -> tuple[list[str], list[str]]:
        return veto_bo3(
            sorted(gd.maps),
            _team_map_mastery(gs, a, sorted(gd.maps)),
            _team_map_mastery(gs, b, sorted(gd.maps)),
            gs.teams[a].tag,
            gs.teams[b].tag,
        )

    n_weeks = regular_season_weeks(gs.teams_per_region)
    season_fixtures = [f for f in gs.fixtures if f.id.startswith(f"s{gs.season}")]

    def _stage_fixtures(stage: str) -> list[Fixture]:
        return [f for f in season_fixtures if f.stage == stage]

    if gs.phase == "regular" and gs.week == n_weeks:
        # Challengers seasons wrap with the franchised leagues: champion
        # by record, a modest prize, and a headline scouts actually read.
        for region in gs.league_regions:
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
                chronicle.record(
                    gs, "challengers_title",
                    f"{champ2.name} win the {str(region).upper()} "
                    f"Challengers season.",
                    team_id=champ2.id,
                    data={"title": f"S{gs.season} {str(region).upper()} Challengers"},
                )
        # Regional playoffs, one bracket per league.
        for region in gs.league_regions:
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
        _nudge_tournament_registration(gs)
    elif gs.phase == "playoffs":
        semis = _stage_fixtures("semi")
        finals = _stage_fixtures("final")
        qfs = _stage_fixtures("masters_qf")
        msfs = _stage_fixtures("masters_sf")
        mf = next(iter(_stage_fixtures("masters_final")), None)

        if semis and all(f.played for f in semis) and not finals:
            # Regional finals: winners of each region's two semis.
            for region in gs.league_regions:
                rsemis = [f for f in semis if f.id.startswith(f"s{gs.season}{str(region)[:2]}")]
                winners = [f.winner_id for f in rsemis if f.winner_id]
                final = build_final(winners, gs.season, gs.week + 1, veto_for)
                final.id = f"s{gs.season}{str(region)[:2]}final"
                gs.fixtures.append(final)
            report.notes.append("Regional finals next week.")
        elif finals and all(f.played for f in finals) and not qfs:
            # Masters: top two per region. Champs seeded by league record.
            # 3 regions (6 sides): seeds 1-2 bye the QF round. 4 regions
            # (8 sides): a full quarterfinal bracket, no byes.
            champs, runners = [], []
            for region in gs.league_regions:
                rf = next(
                    f for f in finals
                    if f.id.startswith(f"s{gs.season}{str(region)[:2]}")
                )
                assert rf.winner_id is not None
                champs.append(rf.winner_id)
                runners.append(
                    rf.team_b if rf.winner_id == rf.team_a else rf.team_a
                )
                # Regional playoff money: the title pays real prize money
                # (on top of regular-season placement), the final loser and
                # semi losers take home a cut — deep runs fund rosters.
                gs.teams[rf.winner_id].balance += PRIZE_REGIONAL_CHAMPION
                gs.teams[runners[-1]].balance += PRIZE_REGIONAL_FINAL_LOSER
                for sf in semis:
                    if not sf.id.startswith(f"s{gs.season}{str(region)[:2]}"):
                        continue
                    sf_loser = sf.team_b if sf.winner_id == sf.team_a else sf.team_a
                    gs.teams[sf_loser].balance += PRIZE_REGIONAL_SEMI_LOSER
                gs.push_news(
                    f"{gs.teams[rf.winner_id].name} bank "
                    f"{PRIZE_REGIONAL_CHAMPION:,} cr for the "
                    f"{str(region).upper()} title."
                )
                chronicle.record(
                    gs, "regional_title",
                    f"{gs.teams[rf.winner_id].name} win the "
                    f"{str(region).upper()} title.",
                    team_id=rf.winner_id,
                    data={
                        "title": f"S{gs.season} {str(region).upper()}",
                        "runner_up": runners[-1],
                    },
                )
                # A domestic title nudges the winners' ceilings up a touch.
                _moment_team_bump(gs, rf.winner_id, MOMENT_REGIONAL)

            def rec_key(tid: str) -> tuple:
                r = gs.standings[tid]
                return (-r.wins, -r.diff, tid)

            champs.sort(key=rec_key)
            runners.sort(key=rec_key)
            seeds = champs + runners  # champs first, then runners, by record
            gs.masters_seeds = seeds
            if len(seeds) == 6:
                # Seeds 1-2 bye straight to the semis.
                pairs = [(seeds[2], seeds[5]), (seeds[3], seeds[4])]
            elif len(seeds) == 8:
                # Full QF bracket: 1v8/4v5 feed SF0, 2v7/3v6 feed SF1.
                pairs = [
                    (seeds[0], seeds[7]), (seeds[3], seeds[4]),
                    (seeds[1], seeds[6]), (seeds[2], seeds[5]),
                ]
            else:
                raise ValueError(
                    f"Masters supports 3 or 4 regional leagues "
                    f"({len(seeds)} qualified sides is not a bracket shape "
                    "the season state machine knows)."
                )
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
            if len(seeds) == 6:
                # The two byes meet the cross-bracket QF winners.
                pairs = [(seeds[0], qf_winners[1]), (seeds[1], qf_winners[0])]
            else:
                # 8-side Masters: QF winners pair off within their halves.
                pairs = [
                    (qf_winners[0], qf_winners[1]),
                    (qf_winners[2], qf_winners[3]),
                ]
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
            qf_losers = [
                (f.team_b if f.winner_id == f.team_a else f.team_a) for f in qfs
            ]
            pay_playoff_prizes(gs, mf.winner_id, runner_up, sf_losers, qf_losers)
            staff.record_title(gs, mf.winner_id, f"S{gs.season} Masters")
            _hist = chronicle.title_history_line(gs, mf.winner_id, "masters_title")
            gs.push_news(
                f"{gs.teams[mf.winner_id].name} win MASTERS "
                f"({PRIZE_CHAMPION:,} cr)" + (f" — {_hist}." if _hist else ".")
            )
            chronicle.record(
                gs, "masters_title",
                f"{gs.teams[mf.winner_id].name} win Masters.",
                team_id=mf.winner_id,
                data={
                    "title": f"S{gs.season} Masters",
                    "runner_up": runner_up,
                },
            )
            # First international of the season — a real ceiling revision, and a
            # Big-Game Player roll for the winners.
            _moment_team_bump(gs, mf.winner_id, MOMENT_MASTERS)
            badges.title_feats(gs, badge_rng, mf.winner_id)

            def rec_key(tid: str) -> tuple:
                r = gs.standings[tid]
                return (-r.wins, -r.diff, tid)

            # Champions is always an 8-side bracket: the Masters field plus
            # the best remaining league records (2 in a 3-region world; 0 in
            # a 4-region world, where Masters already fields 8).
            n_extra = max(0, 8 - len(gs.masters_seeds))
            extras = [
                t for t in gs.standings_order(tier=1) if t not in gs.masters_seeds
            ][:n_extra]
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
            gs.teams[cf.winner_id].balance += PRIZE_CHAMPIONS_WINNER
            gs.teams[cf.winner_id].reputation = round(
                min(99.0, gs.teams[cf.winner_id].reputation + 6.0), 1
            )
            gs.teams[cf_runner].balance += PRIZE_CHAMPIONS_RUNNER_UP
            for f in csfs:
                loser = f.team_b if f.winner_id == f.team_a else f.team_a
                gs.teams[loser].balance += PRIZE_CHAMPIONS_SF_LOSER
            for f in cqfs:
                loser = f.team_b if f.winner_id == f.team_a else f.team_a
                gs.teams[loser].balance += PRIZE_CHAMPIONS_QF_LOSER
            champ = gs.teams[cf.winner_id]
            staff.record_title(gs, cf.winner_id, f"S{gs.season} Champions")
            gs.champions.append(
                ChampionRecord(
                    season=gs.season, team_id=champ.id, team_name=champ.name
                )
            )
            _hist = chronicle.title_history_line(gs, champ.id, "champions_title")
            gs.push_news(
                f"{champ.name} win CHAMPIONS — Season {gs.season} world "
                f"champions ({PRIZE_CHAMPIONS_WINNER:,} cr)!"
                + (f" ({_hist.capitalize()}.)" if _hist else "")
            )
            chronicle.record(
                gs, "champions_title",
                f"{champ.name} win Champions.",
                team_id=champ.id,
                data={
                    "title": f"S{gs.season} Champions",
                    "runner_up": cf_runner,
                },
            )
            # A world title is the biggest ceiling revision in the game, and a
            # shot at the Big-Game Player badge for anyone on the roster.
            _moment_team_bump(gs, cf.winner_id, MOMENT_CHAMPIONS)
            badges.title_feats(gs, badge_rng, cf.winner_id)
            gs.phase = "offseason"
            report.notes.append(
                f"{champ.name} are world champions. Offseason next week."
            )

    _cp.mark("transitions")

    # 5b. Solvency: only AFTER every balance mutation for the week —
    # including the same-week regional/Masters/Champions prize payouts in
    # the phase transitions above — so a team that ends the tick in the
    # black off prize money never takes a spurious debt hit or board warning.
    economy.check_solvency(gs)

    # 5c. Rivalries: fold this week's playoff meetings and poaches into
    # the pair graph — before the news, so recaps can read fresh heat.
    rivalries.on_week(gs, report)

    # 5c'. Organizational knowledge accrues from this week's play (maps
    # executed, opponents met, a coached practice week). Rng-free.
    knowledge.on_week(gs, report)

    # 6. News (before the week label moves on). Recaps read each winner's
    # tactics, so this must run BEFORE the coaches adapt below — otherwise a
    # recap could credit a style the team only shifted to after the match.
    narrative.weekly_news(gs, report, week_kills)

    # 6b. AI coaches review the week and adapt their identity for next week —
    # winners entrench, strugglers drift back toward vanilla. Deliberately
    # after the news so the match-time tactics are what gets reported.
    _adapt_ai_tactics(gs, tree.derive("season", gs.season, "week", gs.week, "adapt"))

    _cp.mark("news_adapt")

    # 6c. Social layer: follower counts chase the week's real outcomes,
    # the feed writes itself (results, player of the week, viral moments),
    # and community sentiment folds the week in and feeds back into
    # confidence/morale (sponsors read it next week — deterministic lag).
    # Result bumps are pinned to the MATCH-TIME side — contracts/transfers
    # already ran above, so live rosters can misattribute a same-tick mover.
    social.weekly_tick(
        gs, report, dev_events,
        tree.derive("season", gs.season, "week", gs.week, "social"),
        match_team_of={
            pid: tid
            for tid in sorted(week_dressed)
            for pid in sorted(week_dressed[tid])
        },
        mental_events=mental_events,
    )

    # 6c''. Streaming load drifts toward each player's follower-driven
    # baseline (rng-free, so the 'social' draw order above is untouched).
    # Runs AFTER follower counts move (fresh baseline) and after training
    # already read this week's load — so a manager's "rein it in" 1:1 gets a
    # full week of extra practice before the load starts drifting back.
    social.stream_load_tick(gs)

    # 6c'. Development milestones: band crossings read AFTER training, dev
    # events, and mental momentum have all landed (a heater-driven crossing
    # found before heater growth would be permanently lost). Chronicle
    # entries record inside; the private news line feeds the owner's inbox.
    for owner_tid, msg in chronicle.weekly_milestones(gs):
        gs.push_private_news(msg, owner=owner_tid)

    _cp.mark("social")

    # 6d. History snapshots (before the week counter rolls): a performance
    # point for everyone who played, a development point for human rosters.
    for pid in sorted(week_perf):
        wp = week_perf[pid]
        if wp["maps"] == 0 or pid not in gs.players:
            continue
        hist = gs.stat_history.setdefault(pid, [])
        hist.append(
            StatSnap(
                season=gs.season,
                week=gs.week,
                maps=wp["maps"],
                rating=round(wp["rating_sum"] / wp["maps"], 2),
                acs=round(wp["cs"] / max(wp["rounds"], 1), 1),
                kd=round(wp["kills"] / max(wp["deaths"], 1), 2),
                kast_pct=round(100.0 * wp["kast"] / max(wp["rounds"], 1), 1),
                kills=wp["kills"],
                deaths=wp["deaths"],
            )
        )
        del hist[:-60]
    _record_dev_snapshots(gs)

    # 6e. Legacy mode: board patience drifts with streaks; a manager deep
    # under the floor is sacked mid-season. The news lands BEFORE the
    # inbox generates; the unseat itself is applied AFTER (below), so the
    # fired manager still receives their own bad news.
    sacked = career.weekly_patience(gs)

    _cp.mark("snapshots")

    # 7. Inbox: aggregate the week's outcomes into each human manager's feed.
    # Runs last so it can read every subsystem's artifacts (news included),
    # and before the week label moves on so this-week news is still labelled.
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        inbox.generate_inbox(gs, report)
    gs.set_acting(None)

    if sacked:
        career.apply_dismissals(gs, sacked)
        for mid in sacked:
            old = gs.managers[mid].last_team_id
            gs.inboxes.setdefault(old, []).append(
                career.dismissal_inbox_item(gs, mid, gs.season, gs.week)
            )

    # 8. Telemetry: the post-tick org feature snapshot per human seat —
    # the state half of the RL episode stream. After dismissals, and
    # before the week counter rolls so snap N pairs with week N's actions.
    telemetry.weekly_snapshots(gs)

    # Observability: this tick's breakdown, paired with the sizes of the
    # structures that grow with save age — the "why is advancing slower in
    # season 5" question answers itself from /api/perf. Write-only sink.
    _cp.mark("inbox")
    perf.record("tick.total", _cp.total_ms)
    perf.record_tick({
        "season": report.season,
        "week": report.week,
        "total_ms": _cp.total_ms,
        "phases": _cp.phases,
        "sizes": {
            "players": len(gs.players),
            "fixtures": len(gs.fixtures),
            "chronicle": len(gs.chronicle),
            "news": len(gs.news),
            "social_feed": len(gs.social_feed),
            "relationships": len(gs.relationships),
            "career_stats": len(gs.career_stats),
            "inbox_items": sum(len(v) for v in gs.inboxes.values()),
        },
    })

    gs.week += 1
    # A fresh, isolated roll queues a decision for the newly opened week.
    flavor_events.queue_weekly_events(gs)
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


def _fold_line(ps: PlayerSeasonStats, line, n_rounds: int) -> None:
    """Fold one map's PlayerLine into a season aggregate (also used for
    the per-map and per-agent splits — one source of folding truth)."""
    ps.maps += 1
    ps.rounds += n_rounds
    ps.kills += line.kills
    ps.deaths += line.deaths
    ps.assists += line.assists
    ps.first_kills += line.first_kills
    ps.trade_kills += line.trade_kills
    ps.headshots += line.headshots
    ps.plants += line.plants
    ps.defuses += line.defuses
    ps.first_deaths += line.first_deaths
    ps.multikills += line.multikills
    ps.aces += line.aces
    ps.clutches += line.clutches
    ps.clutch_1v1 += line.clutch_1v1
    ps.clutch_1v2 += line.clutch_1v2
    ps.clutch_1v3 += line.clutch_1v3
    ps.kast_rounds += line.kast_rounds
    ps.combat_score += line.combat_score
    ps.pistol_kills += line.pistol_kills
    ps.eco_kills += line.eco_kills
    ps.save_kills += line.save_kills
    for wid in sorted(line.kills_by_weapon):
        ps.kills_by_weapon[wid] = (
            ps.kills_by_weapon.get(wid, 0) + line.kills_by_weapon[wid]
        )
    ps.rating_sum += line.rating


def _aggregate_stats(
    gs: GameState,
    f: Fixture,
    stats,
    week_kills: dict,
    dressed: dict[str, set[str]],
    week_perf: dict,
) -> None:
    """Fold one map's MatchStats into the season aggregates + splits. Only
    players who DRESSED for this map are credited a map/rounds — a benched
    player sat it out, which is exactly the point of minutes mattering.
    (For a five-player roster the dressed set is the whole roster.)"""
    n_rounds = len(stats.rounds)
    dressed_all: set[str] = set().union(*dressed.values()) if dressed else set()

    for tid in (f.team_a, f.team_b):
        ts = gs.team_stats.setdefault(tid, TeamSeasonStats())
        tm = gs.team_map_stats.setdefault(tid, {}).setdefault(
            stats.map_id, TeamMapStats()
        )
        ts.maps += 1
        tm.maps += 1
        if stats.winner_id == tid:
            tm.wins += 1
        for r in stats.rounds:
            attacking = r.attacking_team_id == tid
            won = r.winner_id == tid
            if attacking:
                ts.atk_rounds += 1
                ts.atk_won += int(won)
                tm.atk_rounds += 1
                tm.atk_won += int(won)
            else:
                ts.def_rounds += 1
                ts.def_won += int(won)
                tm.def_rounds += 1
                tm.def_won += int(won)
            if r.round_num in (1, 13):
                ts.pistols += 1
                ts.pistols_won += int(won)

    for pid in sorted(stats.lines):
        if pid not in gs.players or (dressed_all and pid not in dressed_all):
            continue
        line = stats.lines[pid]
        _fold_line(
            gs.player_stats.setdefault(pid, PlayerSeasonStats()), line, n_rounds
        )
        _fold_line(
            gs.player_map_stats.setdefault(pid, {}).setdefault(
                stats.map_id, PlayerSeasonStats()
            ),
            line,
            n_rounds,
        )
        _fold_line(
            gs.player_agent_stats.setdefault(pid, {}).setdefault(
                line.agent_id or "unknown", PlayerSeasonStats()
            ),
            line,
            n_rounds,
        )
        week_kills[pid] = week_kills.get(pid, 0) + line.kills
        wp = week_perf.setdefault(
            pid,
            {
                "maps": 0, "rounds": 0, "kills": 0, "deaths": 0,
                "rating_sum": 0.0, "cs": 0.0, "kast": 0,
            },
        )
        wp["maps"] += 1
        wp["rounds"] += n_rounds
        wp["kills"] += line.kills
        wp["deaths"] += line.deaths
        wp["rating_sum"] += line.rating
        wp["cs"] += line.combat_score
        wp["kast"] += line.kast_rounds


_META_DIALS = ("aggression", "pace", "util_discipline", "eco_greed", "map_control")


def _record_map_meta(gs: GameState, stats, tactics_by_team: dict[str, object]) -> None:
    """Fold a completed map into the public, scouting-independent meta."""
    trend = gs.map_meta_stats.setdefault(stats.map_id, MapMetaStats())
    for tid in sorted(tactics_by_team):
        tactics = tactics_by_team[tid]
        trend.team_maps += 1
        for dial in _META_DIALS:
            trend.tactic_sums[dial] = trend.tactic_sums.get(dial, 0.0) + float(
                getattr(tactics, dial)
            )
        focus = str(getattr(tactics, "site_focus"))
        trend.site_focuses[focus] = trend.site_focuses.get(focus, 0) + 1
    for pid in sorted(stats.lines):
        agent_id = stats.lines[pid].agent_id or "unknown"
        trend.agent_picks[agent_id] = trend.agent_picks.get(agent_id, 0) + 1


def _apply_match_development(gs: GameState, stats) -> None:
    """Minutes are development: every played line becomes attribute reps
    (see training.apply_match_experience). Deterministic — no rng."""
    n_rounds = len(stats.rounds)
    pid_to_tid = {
        pid: tid
        for tid in sorted(gs.teams)
        for pid in gs.teams[tid].player_ids
    }
    playing_teams = sorted(
        {pid_to_tid[pid] for pid in stats.lines if pid in pid_to_tid}
    )
    supports = {
        tid: _development_support_bonuses(gs, tid) or {}
        for tid in playing_teams
    }
    for pid in sorted(stats.lines):
        p = gs.players.get(pid)
        if p is not None:
            tid = pid_to_tid.get(pid, "")
            training.apply_match_experience(
                p, stats.lines[pid], n_rounds, supports.get(tid, {}).get(pid, 0.0)
            )


def _apply_bench_week(gs: GameState, week_dressed: dict[str, set[str]]) -> None:
    """One week of bench life for every human roster deeper than five:
    anyone who dressed no map (while the team played) gets scrim reps, a
    stamina refund, and a minutes-morale drain scaled by how good they are.
    Teams with no fixture this week are skipped entirely."""
    for tid in sorted(gs.human_team_ids):
        team = gs.teams[tid]
        if len(team.player_ids) <= market.ROSTER_SIZE:
            continue
        played = week_dressed.get(tid)
        if not played:
            continue
        supports = _development_support_bonuses(gs, tid) or {}
        for p in gs.roster(tid):
            if p.id in played:
                continue
            training.apply_scrim_reps(p, supports.get(p.id, 0.0))
            p.stamina = round(min(100.0, p.stamina + 6.0), 1)
            drain = (
                2.0
                if market.player_quality(p) >= 60
                else 0.5 if p.age <= 20 else 1.2
            )
            p.morale = round(max(0.0, p.morale - drain), 1)


def _nudge_tournament_registration(gs: GameState) -> None:
    """Freeze submitted registrations (or deterministic automatic ones) as
    the playoff bracket is drawn, then tell each human what was locked."""
    series_management.lock_all(gs)
    for tid in sorted(gs.human_team_ids):
        registered = series_management.registration_for(gs, tid)
        names = ", ".join(gs.players[pid].handle for pid in registered)
        gs.push_private_news(
            f"Roster lock: {gs.teams[tid].name} register "
            f"{len(registered)} players for tournament play ({names}).",
            owner=tid,
        )


# ---------------------------------------------------------------------------
# Fixture simulation

# Scouting-driven prep: a manager who set a game plan brings a small duel
# edge — a baseline for having prepped at all, plus the real payoff for
# scout knowledge of THIS opponent (0..1). The engine clamps the total
# (sim/constants.PREP_EDGE_CAP). AI orgs don't set plans — their weekly
# tactic adaptation is the AI's version of prep (documented parity choice,
# same shape as the human-only bench in market.py).
PREP_EDGE_BASE = 0.3
PREP_EDGE_SPAN = 1.0

_PLAN_DIALS = (
    "aggression", "pace", "util_discipline", "eco_greed", "map_control",
    "site_focus",
)


def _match_coach_profile(gs: GameState, tid: str) -> CoachProfile:
    """Project campaign staff into the match's timeout-only coach contract.

    AI sides deliberately receive the league-average fallback.  Human sides
    gain the real quality/specialty/traits only when they have actually hired
    a coach; no match code reaches into the campaign staff market directly.
    """
    coach = gs.staff_by.get(tid, {}).get("coach")
    if coach is None:
        return CoachProfile(id=f"{tid}:coach")
    return CoachProfile(
        id=coach.id,
        quality=coach.quality,
        specialty=coach.specialty,
        traits=tuple(sorted(coach.traits)),
    )


def _fixture_plans(
    gs: GameState, f: Fixture
) -> tuple[dict[str, TeamMatchPlan], dict[str, list[str]]]:
    """Resolve each human side's game plan for this fixture into (engine
    plans, per-match lineup overrides). Stored plans are RE-VALIDATED here
    — rosters move under them (transfers, retirements), so ids are never
    trusted at rest. A focus target only has to be on the opponent's
    ROSTER: if their coach benches the hunted man, the prep tax still
    stands and the edge never fires — benching your star is real
    counterplay to an anti-strat."""
    plans: dict[str, TeamMatchPlan] = {}
    lineups: dict[str, list[str]] = {}
    stored: dict[str, GamePlan] = {}
    overrides_by: dict[str, dict[str, object]] = {}
    resolved_tactics = {
        f.team_a: gs.teams[f.team_a].tactics,
        f.team_b: gs.teams[f.team_b].tactics,
    }

    # Resolve both identities first. Counter-strat scoring is simultaneous:
    # if both human managers change their book for this fixture, each side is
    # measured against what the opponent will actually bring to the server.
    for tid, opp in ((f.team_a, f.team_b), (f.team_b, f.team_a)):
        coach = _match_coach_profile(gs, tid)
        # Every campaign side has a coach profile.  Without a hired coach it
        # is the league-average fallback; its only possible live input is a
        # timeout, never an always-on engine modifier.
        plans[tid] = TeamMatchPlan(coach=coach)
        if not gs.is_human(tid):
            continue
        plan = gs.game_plans_by.get(tid)
        if plan is None or plan.fixture_id != f.id:
            continue
        overrides = {
            k: getattr(plan, k)
            for k in _PLAN_DIALS
            if getattr(plan, k) is not None
        }
        stored[tid] = plan
        overrides_by[tid] = overrides
        if overrides:
            resolved_tactics[tid] = gs.teams[tid].tactics.model_copy(update=overrides)

    for tid, opp in ((f.team_a, f.team_b), (f.team_b, f.team_a)):
        plan = stored.get(tid)
        if plan is None:
            continue
        overrides = overrides_by[tid]
        target = plan.focus_target
        if target is not None and target not in gs.teams[opp].player_ids:
            target = None
        know = gs.scout_progress_by.get(tid, {}).get(opp, 0.0)
        # Institutional knowledge amplifies preparation: the org's book on
        # these maps and this opponent adds to the edge — but only WITH a
        # plan (no prep, no payoff). The engine clamps the total.
        book = knowledge.prep_bonus(gs, tid, opp, list(f.maps))
        plans[tid] = TeamMatchPlan(
            tactics=resolved_tactics[tid] if overrides else None,
            focus_target=target,
            prep_edge=PREP_EDGE_BASE + PREP_EDGE_SPAN * know + book,
            counter_edge=tactics_fit.counter_strat_edge(
                {
                    dial: getattr(plan, dial)
                    for dial in tactics_fit.COUNTER_DIALS
                },
                resolved_tactics[opp],
            ),
            coach=_match_coach_profile(gs, tid),
        )
        lineup = [pid for pid in plan.starter_ids if pid in gs.teams[tid].player_ids]
        if len(lineup) == market.ROSTER_SIZE and len(set(lineup)) == market.ROSTER_SIZE:
            lineups[tid] = lineup
    return plans, lineups


TEAM_TALK_APPROACHES = ("fire_up", "reassure", "focus")


def _talk_recipients(gs: GameState, tid: str, f: Fixture) -> list[str]:
    """Everyone who will dress for `tid` across the fixture's maps — the union
    of dressed_for over f.maps (which reads the finalised map_lineups, so a
    per-map rotation is reflected). The pre-match team-talk audience. Sorted
    for deterministic iteration."""
    return sorted(
        {pid for map_id in f.maps for pid in dressed_for(gs, tid, f, map_id)}
    )


def _apply_team_talk(gs: GameState, approach: str, five: list[str]) -> None:
    """A pre-match team talk nudges the dressed five's confidence, modulated
    by personality and bounded to [5, 95] — the same range the rest of the
    campaign clamps confidence to. Deterministic (personality is a pure
    function). Called ONLY for a human side that set a talk in its game plan,
    so hands-off sims never reach here and the balance gates are unchanged.

    - fire_up:  a lift, bigger for ambitious players (they ride motivation).
    - reassure: a lift, bigger for fragile (low-resilience) players.
    - focus:    settle everyone toward a steady 55 (calms tilt AND hubris).
    """
    from esports_sim.manager import personality

    for pid in five:
        p = gs.players.get(pid)
        if p is None:
            continue
        if approach == "focus":
            delta = (55.0 - p.confidence) * 0.25
        elif approach == "reassure":
            delta = 3.0 * (1.0 - 0.4 * personality.dev(p, "resilience"))
        else:  # fire_up
            delta = 5.0 * (1.0 + 0.4 * personality.dev(p, "ambition"))
        p.confidence = round(min(95.0, max(5.0, p.confidence + delta)), 1)


def _between_map_plan(
    gs: GameState, tid: str, base: TeamMatchPlan, response: str
) -> TeamMatchPlan:
    """Project one conditional series response into the optional match-plan
    seam. This never mutates the standing team tactics and is only reachable
    after a manager's directive fires."""
    tactics = base.tactics or gs.teams[tid].tactics
    update: dict[str, float] = {}
    if response == "press":
        update = {
            "aggression": min(100.0, tactics.aggression + 12.0),
            "pace": min(100.0, tactics.pace + 10.0),
            "map_control": min(100.0, tactics.map_control + 6.0),
        }
    elif response == "stabilize":
        update = {
            "aggression": max(0.0, tactics.aggression - 6.0),
            "pace": max(0.0, tactics.pace - 10.0),
            "util_discipline": min(100.0, tactics.util_discipline + 10.0),
        }
    return TeamMatchPlan(
        tactics=tactics.model_copy(update=update) if update else base.tactics,
        focus_target=base.focus_target,
        prep_edge=base.prep_edge,
        counter_edge=base.counter_edge,
        coach=base.coach,
    )


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
        # A walkover has no rounds to diagnose — leave a thin (uncontested)
        # review so the dashboard shows the scoreline, not a stale prior match.
        a_wins, b_wins = f.map_score
        for tid in (f.team_a, f.team_b):
            if not gs.is_human(tid):
                continue
            you_a = tid == f.team_a
            gs.last_review_by[tid] = MatchReview(
                fixture_id=f.id,
                season=gs.season,
                week=f.week,
                team_id=tid,
                opp_id=f.team_b if you_a else f.team_a,
                won=tid == walkover,
                best_of=f.best_of,
                your_maps=a_wins if you_a else b_wins,
                their_maps=b_wins if you_a else a_wins,
                contested=False,
            )
        return

    # Game plans: per-match tactics/target/prep go to the engine as an
    # override parameter (never by mutating live Teams); a plan's
    # one-match lineup rides the map_lineups override channel — the same
    # single-use, swept-with-the-fixture mechanism explicit per-map
    # lineups use — so the caller's post-match dressed_for re-derivation
    # (stats + development attribution) sees exactly the five who played.
    # setdefault: an explicit per-map lineup, being more specific, beats
    # the plan's match-wide five.
    plans, plan_lineups = _fixture_plans(gs, f)
    for tid in sorted(plan_lineups):
        for map_id in f.maps:
            gs.map_lineups.setdefault(
                f"{tid}|{f.id}|{map_id}", plan_lineups[tid]
            )

    # Pre-match team talks land on the players who will ACTUALLY dress, resolved
    # via dressed_for against the now-finalised map_lineups (explicit per-map
    # overrides included). So a rotation gives the talk to the rotated-in five,
    # not default_five. Applied here, once, before any map sim reads confidence.
    # Human sides with a set talk only -> hands-off sims skip it -> gates hold.
    for tid in (f.team_a, f.team_b):
        if not gs.is_human(tid):
            continue
        plan = gs.game_plans_by.get(tid)
        if plan is None or plan.fixture_id != f.id:
            continue
        if plan.team_talk in TEAM_TALK_APPROACHES:
            _apply_team_talk(gs, plan.team_talk, _talk_recipients(gs, tid, f))

    # Per-map (box score, event log, dressed roster) bundles, kept for the
    # post-series match-review synthesis while the full stats + events are
    # still alive (they are transient — dropped once the week rolls over).
    review_bundles: list[tuple] = []
    review_weapon_class: dict[str, str] = {}
    active_series_responses: dict[str, str] = {}
    fired_directives: set[str] = set()
    for map_index, map_id in enumerate(f.maps):
        a_wins, b_wins = f.map_score
        if a_wins >= need or b_wins >= need:
            break

        # Conditional between-map card. Once it fires, the response persists
        # for the rest of this series; a substitution rewrites each remaining
        # map's dressed-five override. The fixture note is the grounded audit
        # trail shown by the UI.
        for tid in (f.team_a, f.team_b):
            directive = gs.series_directives_by.get(tid)
            if (
                tid not in fired_directives
                and directive is not None
                and directive.fixture_id == f.id
                and series_management.should_fire(directive, f, tid, map_index)
            ):
                current = dressed_for(gs, tid, f, map_id)
                changed = series_management.adjusted_lineup(current, directive)
                if changed != current:
                    for remaining_map in f.maps[map_index:]:
                        gs.map_lineups[f"{tid}|{f.id}|{remaining_map}"] = list(changed)
                    in_name = gs.players[directive.substitute_in].handle
                    out_name = gs.players[directive.substitute_out].handle
                    f.series_notes.append(
                        f"{gs.teams[tid].tag}: {in_name} replaces {out_name} after map {map_index}."
                    )
                active_series_responses[tid] = directive.response
                if directive.response == "reset":
                    for pid in changed:
                        p = gs.players[pid]
                        p.confidence = round(min(95.0, p.confidence + 2.0), 1)
                elif directive.response == "press":
                    for pid in changed:
                        gs.players[pid].stamina = round(
                            max(0.0, gs.players[pid].stamina - 2.0), 1
                        )
                if directive.response != "steady":
                    f.series_notes.append(
                        f"{gs.teams[tid].tag}: {directive.response} response after map {map_index}."
                    )
                fired_directives.add(tid)

        map_plans = dict(plans)
        for tid, response in sorted(active_series_responses.items()):
            map_plans[tid] = _between_map_plan(gs, tid, map_plans[tid], response)
        seed = tree.derive_seed(
            "season", gs.season, "week", f.week, "fixture", f.id, "map", map_index
        )
        dressed = {
            f.team_a: dressed_for(gs, f.team_a, f, map_id),
            f.team_b: dressed_for(gs, f.team_b, f, map_id),
        }
        map_gd = _dressed_gamedata(gs, rt_gd, dressed)
        res = simulate_match_result(
            map_gd, f.team_a, f.team_b, map_id, seed, plans=map_plans or None
        )
        # The dressed five per side (bench players have no line), plus the
        # weapon registry's class map for the economy splits (eco/save kills).
        team_of = {
            pid: tid for tid in (f.team_a, f.team_b) for pid in dressed[tid]
        }
        weapon_class_of = {
            wid: str(w.weapon_class) for wid, w in rt_gd.weapons.items()
        }
        stats = compute_match_stats(res.events, team_of, weapon_class_of)
        _record_map_meta(
            gs,
            stats,
            {
                tid: (
                    map_plans[tid].tactics
                    if tid in map_plans and map_plans[tid].tactics is not None
                    else gs.teams[tid].tactics
                )
                for tid in (f.team_a, f.team_b)
            },
        )
        review_bundles.append((stats, res.events, team_of))
        review_weapon_class = weapon_class_of
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

    # Match review: synthesize a "why you won/lost" diagnosis for each human
    # side while the full box score + event log are still in hand. Only the
    # latest per team is kept on GameState (the dashboard card reads it); the
    # durable corpus is appended on disk at the web layer, off the tick.
    for tid in (f.team_a, f.team_b):
        if not gs.is_human(tid):
            continue
        opp = f.team_b if tid == f.team_a else f.team_a
        gs.last_review_by[tid] = build_match_review(
            gs.season,
            f.week,
            f.id,
            tid,
            opp,
            f.best_of,
            review_bundles,
            review_weapon_class,
        )

    # A plan is one match's prep: consumed when its fixture sims.
    for tid in (f.team_a, f.team_b):
        plan = gs.game_plans_by.get(tid)
        if plan is not None and plan.fixture_id == f.id:
            del gs.game_plans_by[tid]
        directive = gs.series_directives_by.get(tid)
        if directive is not None and directive.fixture_id == f.id:
            del gs.series_directives_by[tid]

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
        won = tid == map_winner
        for p in gs.roster(tid):
            line = stats.lines.get(p.id)
            if line is None:
                continue
            p.stamina = max(0.0, p.stamina - 7.0)
            # Form chases recent performance.
            perf = 30.0 + line.rating * 28.0
            p.form = round(min(100.0, max(0.0, 0.75 * p.form + 0.25 * perf)), 1)
            # Confidence chases results AND the player's own game: a carry
            # on a losing team keeps believing; a passenger on a winning
            # one doesn't bank much. Clamped off the rails (5..95) and
            # regressed weekly in training, so it can't snowball.
            dc = 1.2 if won else -1.2
            if line.rating >= 1.15:
                dc += 0.8
            elif line.rating <= 0.6:
                dc -= 0.8
            dc += 0.4 * min(2, line.clutch_1v1 + line.clutch_1v2 + line.clutch_1v3)
            p.confidence = round(min(95.0, max(5.0, p.confidence + dc)), 1)


def _apply_match_effects(gs: GameState, f: Fixture) -> None:
    assert f.winner_id is not None
    big = 2.0 if f.stage in ("semi", "final") else 1.0
    for tid in (f.team_a, f.team_b):
        team = gs.teams[tid]
        won = tid == f.winner_id
        for p in gs.roster(tid):
            p.morale = round(min(100.0, max(0.0, p.morale + (5.0 if won else -4.0))), 1)
            # Series result moves the whole locker room's belief a little
            # (bench included); the big stages cut deeper both ways.
            p.confidence = round(
                min(95.0, max(5.0, p.confidence + (1.0 if won else -1.0) * big)), 1
            )
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


SCOUT_WEEKLY_GAIN = 0.34
# Assignment ceilings are deliberately different kinds of knowledge.  A broad
# survey identifies the shape of a market/team, watching real matches adds
# behavioral context, and only a named-player deep dive can compile a full
# book.  "Full" is information depth, not omniscience; web/market views retain
# player-specific residual uncertainty even at 1.0.
SCOUT_SURVEY_CAP = 0.50
SCOUT_MATCH_CAP = 0.75
SCOUT_DEEP_CAP = 1.00
# A single player is a focused beat, but reading a CEILING is slow, careful
# work — a deep-dive book is a multi-week investment, not a one-week glance
# (and even a full book only ever yields a projection BAND, never an exact
# ceiling number; see development.scout_report / potential_projection).
SCOUT_PLAYER_MULT = 0.7
# ...and watching them play LIVE this week adds a small bonus on top.
SCOUT_LIVE_WATCH_BONUS = 0.05
# Per-week ceiling on deep-dive progress: even an elite analyst desk can't
# compile the full book faster than a few weeks of real observation.
SCOUT_PLAYER_WEEK_CAP = 0.30
# One-shot match intel: attending a fixture grants this much knowledge of
# BOTH participants (a weekend at the venue ~= a week and a half of tape).
SCOUT_MATCH_INTEL = 0.5


def _active_scout_guidance(gs: GameState, tid: str) -> dict[str, str] | None:
    """The one own-player recommendation eligible for this week's bonus."""
    progress = gs.scout_progress_by.get(tid, {})
    target = gs.scout_targets.get(tid)
    if not target or not target.startswith("player:"):
        return None
    pid = target[len("player:"):]
    if pid not in gs.teams[tid].player_ids:
        return None
    if progress.get(target, 0.0) < training.SCOUT_GUIDANCE_UNLOCK:
        return None
    p = gs.players.get(pid)
    if p is None:
        return None
    return {pid: str(training.scouting_guidance(p)["focus"])}

# Monumental-moment ceiling revisions: a career peak (an international title, a
# league award, a record) revises a player's ceiling UP — most for the young
# with room, ~nothing for a veteran at their cap (development.moment_potential
# _bump scales by age and soft-caps). Fires for EVERY org (AI parity); the soft
# cap is what keeps it from snowballing dynasties (an 85-PA star barely moves).
MOMENT_CHAMPIONS = 3.0
MOMENT_MASTERS = 2.2
MOMENT_REGIONAL = 1.0
MOMENT_AWARD_MVP = 3.0  # Season MVP / Rookie of the Season
MOMENT_AWARD = 1.5      # other league awards
MOMENT_ALL_STAR = 1.5
MOMENT_RECORD = 1.0     # career-kill milestones


def _moment_team_bump(gs: GameState, tid: str, base: float) -> None:
    """Revise the ceiling of every player on a title-winning roster (sorted,
    rng-free), scaled per-player by age inside moment_potential_bump."""
    team = gs.teams.get(tid)
    if team is None:
        return
    for pid in sorted(team.player_ids):
        p = gs.players.get(pid)
        if p is not None:
            development.moment_potential_bump(p, base)


def _tick_scouting(gs: GameState, report: WeekReport) -> None:
    """Advance each human manager's scout by one week (own desk, own
    target/progress/staff/facilities). `report` carries this week's played
    fixtures for match assignments and live-watch bonuses."""
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        _tick_scouting_one(gs, report)
    gs.set_acting(None)


def _tick_scouting_one(gs: GameState, report: WeekReport) -> None:
    """One manager's scout, by assignment type (all stored in the same
    per-manager progress dict — team ids, "market", "player:<pid>",
    "match:<fixture id>"):

    * a rival TEAM — steady weekly coverage (the classic beat);
    * the MARKET — slower, wider free-agent coverage;
    * one PLAYER — a deep-dive book that fills ~1.5x faster, faster still
      the weeks they actually play (progressive intel tiers: comfort picks,
      style read, mental read, full verdict — see development.scout_report);
    * one MATCH — the scout attends the fixture and comes home with a
      one-shot intel packet on BOTH teams (then needs a new assignment)."""
    target = gs.scout_target
    if not target:
        return
    mult = staff.scout_multiplier(gs) * economy.facility_scout_mult(gs)

    if target.startswith("match:"):
        fid = target[len("match:"):]
        fx = next((f for f in report.fixtures if f.id == fid and f.played), None)
        if fx is None:
            # Not played this tick. If it vanished from the calendar
            # entirely, send the scout home; otherwise keep waiting.
            if not any(f.id == fid for f in gs.fixtures):
                gs.scout_target = None
                gs.push_private_news(
                    "Scouted fixture is off the calendar — the scout needs "
                    "a new assignment."
                )
            return
        gained = min(SCOUT_MATCH_CAP, round(SCOUT_MATCH_INTEL * mult, 2))
        # Keep a completion marker in the existing prefixed progress store.
        # The active assignment still clears below; the scouting serializer
        # uses this key to derive the latest post-match report from Fixture.
        gs.scout_progress[target] = gained
        for observed_tid in (fx.team_a, fx.team_b):
            team = gs.teams.get(observed_tid)
            if team is None:
                continue
            for dial in ("aggression", "pace", "eco_greed", "map_control"):
                gs.scout_progress[
                    f"matchobs:{fid}:{observed_tid}:{dial}"
                ] = float(getattr(team.tactics, dial))
            gs.scout_progress[
                f"matchobs:{fid}:{observed_tid}:site:{team.tactics.site_focus}"
            ] = 1.0
        names = []
        for tid in (fx.team_a, fx.team_b):
            if tid == gs.acting_team_id or tid not in gs.teams:
                continue
            cur = gs.scout_progress.get(tid, 0.0)
            gs.scout_progress[tid] = min(
                SCOUT_MATCH_CAP, round(cur + gained, 2)
            )
            names.append(gs.teams[tid].name)
        gs.scout_target = None  # one-shot: the scout comes home
        if names:
            gs.push_private_news(
                f"Match intel: your scout's report from "
                f"{gs.teams[fx.team_a].name} vs {gs.teams[fx.team_b].name} "
                f"is in — coverage of {' and '.join(names)} jumps."
            )
        return

    if target.startswith("player:"):
        pid = target[len("player:"):]
        p = gs.players.get(pid)
        if p is None:
            gs.scout_target = None
            return
        cur = gs.scout_progress.get(target, 0.0)
        # A ceiling read is slow work: capped per week so no single week (even
        # an elite analyst desk) compiles the full book — a deep dive is a
        # multi-week commitment now, not a one-week reveal.
        gain = min(SCOUT_PLAYER_WEEK_CAP, SCOUT_WEEKLY_GAIN * SCOUT_PLAYER_MULT * mult)
        # They played this week: the scout watched it live.
        played = any(
            pid in stats.lines
            for fid in report.match_stats
            for stats in report.match_stats[fid]
        )
        if played:
            gain += SCOUT_LIVE_WATCH_BONUS
        after = min(SCOUT_DEEP_CAP, round(cur + gain, 2))
        gs.scout_progress[target] = after
        if after >= 1.0 and cur < 1.0:
            gs.push_private_news(
                f"The full book on {p.handle} is compiled — style, "
                "mentality, ceiling, the lot."
            )
        return

    if target != "market" and target not in gs.teams:
        return
    cur = gs.scout_progress.get(target, 0.0)
    gain = SCOUT_WEEKLY_GAIN * mult
    # The market is a bigger beat than one team: slower coverage.
    if target == "market":
        gain *= 0.6
    after = min(SCOUT_SURVEY_CAP, round(cur + gain, 2))
    gs.scout_progress[target] = after
    if after >= SCOUT_SURVEY_CAP and cur < SCOUT_SURVEY_CAP:
        label = (
            "the free-agent market"
            if target == "market"
            else gs.teams[target].name
        )
        # Private to this manager (their scout desk) — see push_private_news.
        gs.push_private_news(f"Broad scouting survey of {label} complete.")


def _update_world_ranks(gs: GameState) -> None:
    def key(tid: str) -> tuple:
        r = gs.standings.get(tid, TeamRecord())
        return (-r.wins, -r.diff, -gs.teams[tid].reputation, tid)

    for rank, tid in enumerate(sorted(gs.teams, key=key), start=1):
        gs.teams[tid].world_rank = rank


# ---------------------------------------------------------------------------
# Offseason


def mentorship_valid(gs: GameState, protege_id: str, mentor_id: str) -> bool:
    """A mentorship holds when both players share a roster and the mentor is
    the older, higher-ability of the pair. The logic lives in development (the
    ceiling-raise reads it too); this stays the campaign/web entry point."""
    return development.mentorship_valid(gs, protege_id, mentor_id)


def _mentor_mults(gs: GameState, tid: str) -> dict[str, float] | None:
    """Development multipliers for this team's protégés under a valid, set
    mentorship. None when nothing applies — hands-off sims never set a
    mentorship, so this returns None and training stays byte-identical
    (rate * 1.0), keeping the snowball/dynasty gates unchanged."""
    if not gs.mentorships:
        return None
    roster = set(gs.teams[tid].player_ids)
    out = {
        pid: training.MENTOR_GROWTH_MULT
        for pid, mentor_id in gs.mentorships.items()
        if pid in roster and mentorship_valid(gs, pid, mentor_id)
    }
    return out or None


def _development_support_bonuses(
    gs: GameState, tid: str
) -> dict[str, float] | None:
    """Contextual headroom for every player, with AI parity.

    Explicit manager mentorship is strongest, but AI teams and hands-off
    players can still benefit from an obvious senior teammate. Named duos,
    individual morale/confidence/form, and team chemistry apply equally to
    every organization.
    """
    roster = sorted(gs.roster(tid), key=lambda p: p.id)
    if not roster:
        return None
    out: dict[str, float] = {}
    for p in roster:
        explicit = gs.mentorships.get(p.id)
        mentor_strength = 1.0 if explicit and mentorship_valid(gs, p.id, explicit) else 0.0
        if mentor_strength == 0.0:
            candidates = [
                q for q in roster
                if q.id != p.id
                and q.age >= p.age + 5
                and development.overall(q) > development.overall(p)
            ]
            if candidates:
                best = max(
                    candidates,
                    key=lambda q: (
                        development.mentor_skill(
                            q,
                            gs.career_stats.get(q.id).seasons
                            if gs.career_stats.get(q.id) else 0,
                        ),
                        q.id,
                    ),
                )
                skill = development.mentor_skill(
                    best,
                    gs.career_stats.get(best.id).seasons
                    if gs.career_stats.get(best.id) else 0,
                )
                if skill >= 55.0:
                    mentor_strength = 0.55 * (skill / 99.0)
        duo_affinity = max(
            (relationships.get(gs, p.id, q.id) for q in roster if q.id != p.id),
            default=50.0,
        )
        bonus = development.contextual_ceiling_bonus(
            p,
            mentor_strength=mentor_strength,
            duo_affinity=duo_affinity,
            team_chemistry=gs.teams[tid].chemistry,
        )
        if bonus > 0.0:
            out[p.id] = bonus
    return out or None


def _snapshot_season_start_ca(gs: GameState) -> None:
    """Freeze every current player's current ability as the season's
    baseline. Pure read of settled rosters (rng-free, sorted iteration),
    so it's campaign-deterministic. The Most Improved award diffs
    end-of-season CA against this."""
    gs.season_start_ca = {
        pid: round(development.overall(gs.players[pid]), 2)
        for pid in sorted(gs.players)
    }


def _record_dev_snapshots(gs: GameState, week: int | None = None) -> None:
    """Record the private human-roster development series.

    Week zero is used at campaign/season creation so a season report measures
    from the settled opening roster, before the first training tick. Players
    who join later start tracking on their first week at the club.
    """
    snap_week = gs.week if week is None else week
    for tid in sorted(gs.human_team_ids):
        for p in gs.roster(tid):
            dh = gs.dev_history.setdefault(p.id, [])
            dh.append(
                DevSnap(
                    season=gs.season,
                    week=snap_week,
                    ca=round(development.overall(p), 1),
                    confidence=p.confidence,
                    form=p.form,
                    morale=p.morale,
                    followers=p.followers,
                    attributes={
                        aid: round(value, 1)
                        for aid, value in sorted(p.attributes.items())
                    },
                )
            )
            del dh[:-80]


CAREER_KILL_BARS = (500, 1000, 1500, 2000, 3000, 5000)


def _accumulate_career_stats(gs: GameState) -> None:
    """Roll this season's box score into each player's lifetime totals
    (before the per-season reset), and chronicle career-kill milestones the
    moment they're crossed. Pure read of gs.player_stats (rng-free, sorted
    iteration), so it stays campaign-deterministic."""
    from esports_sim.manager.state import CareerStats

    for pid in sorted(gs.player_stats):
        st = gs.player_stats[pid]
        if st.maps <= 0:
            continue
        cs = gs.career_stats.setdefault(pid, CareerStats())
        prev_kills = cs.kills
        cs.maps += st.maps
        cs.rounds += st.rounds
        cs.kills += st.kills
        cs.deaths += st.deaths
        cs.first_kills += st.first_kills
        cs.clutches += st.clutches
        cs.seasons += 1
        p = gs.players.get(pid)
        if p is not None:
            cs.handle = p.handle  # keep the record's name current
        if p is None:
            continue
        team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
        for bar in CAREER_KILL_BARS:
            if prev_kills < bar <= cs.kills:
                chronicle.record(
                    gs, "milestone",
                    f"{p.handle} passes {bar} career kills.",
                    team_id=team.id if team else "",
                    player_id=pid,
                    data={"career_kills": str(bar)},
                )
                gs.push_news(f"{p.handle} reaches {bar} career kills.")
                # A record entering the books is a (small) ceiling revision —
                # meaningful only if they're young enough to still have room.
                development.moment_potential_bump(p, MOMENT_RECORD)


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
            team.lineup_ids = [q for q in team.lineup_ids if q != pid]
            team.lineup.starters = [q for q in team.lineup.starters if q != pid]
            team.lineup.agents.pop(pid, None)
            if team.captain_id == pid:
                team.captain_id = team.player_ids[0] if team.player_ids else None
            if gs.is_human(team.id):
                # Private to the owning manager (not the whole world's inbox);
                # _process_retirements runs outside any set_acting loop, so name
                # the owner explicitly.
                gs.push_private_news(
                    f"{p.handle} retires — {team.name} has an open seat.",
                    owner=team.id,
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
        # Career honours make a retirement land harder in history, and a
        # decorated career earns a dry sendoff in the news. All grounded in
        # the chronicle: this player's individual awards, and their debut
        # season (career length) when the debut system saw them arrive.
        mine = [e for e in gs.chronicle if e.player_id == pid]
        honours = [e for e in mine if e.kind == "award"]
        n_honours = len(honours)
        mvps = sum(1 for e in honours if "MVP" in e.data.get("award", ""))
        debut_season = next((e.season for e in mine if e.kind == "debut"), None)
        seasons = (
            gs.season - debut_season + 1 if debut_season is not None else None
        )
        resume_bits: list[str] = []
        if seasons is not None:
            resume_bits.append(f"{seasons} pro season{'s' if seasons != 1 else ''}")
        if n_honours:
            resume_bits.append(
                f"{n_honours} individual honour{'s' if n_honours != 1 else ''}"
                + (f" ({mvps}x MVP)" if mvps else "")
            )
        resume = ", ".join(resume_bits)
        chronicle.record(
            gs, "retirement",
            f"{p.handle} retires at {p.age}"
            + (f" ({team.name})" if team else "")
            + (f" - {resume}." if resume else "."),
            team_id=team.id if team else "",
            player_id=pid,
            importance=min(80.0, 40.0 + 8.0 * n_honours + (5.0 if ca >= 78 else 0.0)),
            data={"age": str(p.age), "ca": f"{ca:.0f}"},
        )
        # A genuinely decorated career (multiple honours, an MVP, or a
        # star-level peak) gets its own sendoff line, not just a name in the
        # bulk retirements list below.
        if n_honours >= 2 or mvps >= 1 or ca >= 80:
            gs.push_news(
                f"End of an era: {p.handle} retires at {p.age} after "
                f"{resume or f'a {ca:.0f} CA career'}."
            )
        # A completed career faces the Hall (score reads the chronicle
        # entries above, so it runs after the retirement is recorded).
        hof.consider_at_retirement(gs, p, ca, team.name if team else "")
        # The coaching tree: IGLs and high-game-sense retirees re-enter
        # the world as staff candidates (deterministic — no rng draw, so
        # the offseason stream never shifts).
        staff.retire_into_staff(gs, p, ca, team.name if team else "")
        if ca >= 62 or p.age >= 31:
            notable.append(f"{p.handle} ({p.age})")
        gs.academy_player_rights.pop(pid, None)
        for team_id in sorted(gs.leadership_groups):
            gs.leadership_groups[team_id] = [
                q for q in gs.leadership_groups[team_id] if q != pid
            ]
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


def _release_future_prospects(gs: GameState) -> dict[str, int]:
    """Publish eligible historical prospects without consuming RNG draws."""
    if gs.calendar_year is None:
        return {}
    next_year = gs.calendar_year + 1
    released: dict[str, int] = {}
    released_ids: list[str] = []
    for pid in sorted(gs.future_prospects):
        prospect = gs.future_prospects[pid]
        if prospect.debut_year > next_year:
            continue
        p = prospect.player
        if p.age < 17:
            raise ValueError(
                f"future prospect {pid!r} debuts in {next_year} at age {p.age}"
            )
        p.contract_weeks_left = 0
        p.personality_tags = sorted({*p.personality_tags, "rookie"})
        gs.players[pid] = p
        gs.free_agent_ids.append(pid)
        chronicle.mark_debut_pending(gs, pid)
        region = str(p.region)
        released[region] = released.get(region, 0) + 1
        released_ids.append(pid)
    for pid in released_ids:
        del gs.future_prospects[pid]
    if released_ids:
        names = [gs.players[pid].handle for pid in released_ids]
        gs.push_news(
            f"Historical class of {next_year} enters free agency: "
            f"{', '.join(names[:4])}."
        )
    return released


def _rookie_classes(
    gs: GameState, gd: GameData, rng, n_retired: int,
    historical_debuts: dict[str, int] | None = None,
) -> None:
    """Each region graduates a rookie class into free agency — the talent
    pipeline that replaces retiring careers. Class size breathes with how
    many careers just ended."""
    from esports_sim.manager.gen import _FA_SLOTS, generate_player

    per_region = 2 + max(0, n_retired) // (len(gs.league_regions) * 2)
    headliners: list[str] = []
    historical_debuts = historical_debuts or {}
    for region in gs.league_regions:
        for _ in range(max(0, per_region - historical_debuts.get(str(region), 0))):
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
            chronicle.mark_debut_pending(gs, pid)
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
        if gs.is_human(tid):
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
        captain = next((p for p in roster if p.id == gs.teams[tid].captain_id), None)
        igl_sense = role_fit.igl_effectiveness(
            captain, role_fit.igl_experience(gs.teams[tid], captain.id)
        ) if captain else 55.0
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


# How far a coach nudges the dials each week (small — identities shift over
# a season, not overnight). Winners push their identity ~1.5 further from
# neutral; strugglers shrink 8% back toward it; pistol form pulls eco_greed.
_ADAPT_STEP = 1.5
_ADAPT_SHRINK = 0.08
_ADAPT_NOISE = 1.0
_ADAPT_PISTOL = 6.0
_ADAPT_MIN_MAPS = 3  # too few maps to read anything meaningful


_DIFFUSION_PULL = 0.5  # how much of the meta identity a struggler copies
_META_WIN_BAR = 0.55  # round win rate that makes a team worth copying

_ADAPT_DIALS = ("aggression", "pace", "util_discipline", "map_control")


def _meta_identity(gs: GameState) -> dict[str, float] | None:
    """What winning looks like right now: the mean dial identity of the
    league's in-form teams (round win rate >= _META_WIN_BAR, enough maps).
    None when nobody stands out — early season has no meta to copy."""
    winners: list = []
    for tid in sorted(gs.teams):
        if gs.teams[tid].tier != 1:
            continue
        ts = gs.team_stats.get(tid)
        if ts is None or ts.maps < _ADAPT_MIN_MAPS:
            continue
        rounds = ts.atk_rounds + ts.def_rounds
        if rounds and (ts.atk_won + ts.def_won) / rounds >= _META_WIN_BAR:
            winners.append(gs.teams[tid].tactics)
    if not winners:
        return None
    return {
        dial: float(np.mean([getattr(t, dial) for t in winners]))
        for dial in _ADAPT_DIALS
    }


def _adapt_ai_tactics(gs: GameState, rng) -> None:
    """AI orgs are no longer frozen for a season: each week a coach nudges
    the dials toward how the campaign is actually going. A winning team
    entrenches its identity (pushes each dial further from neutral); a
    struggling team abandons a failing plan and drifts toward what is
    WORKING for others — the blend of neutral and the current meta
    identity (strategy diffusion: successful approaches get copied).
    Pistol-round form pulls eco_greed. The user team is never touched,
    and the match gates never run the campaign, so this is invisible to
    golden/balance."""
    clamp = lambda v: float(np.clip(v, 15.0, 85.0))  # noqa: E731
    meta_id = _meta_identity(gs)
    for tid in sorted(gs.teams):
        if gs.is_human(tid):
            continue
        ts = gs.team_stats.get(tid)
        if ts is None or ts.maps < _ADAPT_MIN_MAPS:
            continue
        rounds = ts.atk_rounds + ts.def_rounds
        if rounds == 0:
            continue
        rwr = (ts.atk_won + ts.def_won) / rounds
        winning, losing = rwr >= 0.52, rwr <= 0.45
        tac = gs.teams[tid].tactics
        for dial in _ADAPT_DIALS:
            v = getattr(tac, dial)
            if winning and v != 50.0:
                v += _ADAPT_STEP if v > 50.0 else -_ADAPT_STEP
            elif losing:
                # Not "back to vanilla" — toward what wins around here.
                target = 50.0
                if meta_id is not None:
                    target += (meta_id[dial] - 50.0) * _DIFFUSION_PULL
                v += (target - v) * _ADAPT_SHRINK
            v += float(rng.normal(0, _ADAPT_NOISE))
            setattr(tac, dial, round(clamp(v), 1))
        if ts.pistols >= 2:
            pwr = ts.pistols_won / ts.pistols
            tac.eco_greed = round(clamp(tac.eco_greed + (pwr - 0.5) * _ADAPT_PISTOL), 1)


# A dial whose league-wide mean ends a season this far from neutral marks
# a meta era worth remembering (chronicled at the offseason).
_META_ERA_DEV = 6.0
_META_ERA_NAMES = {
    ("aggression", True): "an all-out aggression era",
    ("aggression", False): "a disciplined, patient era",
    ("pace", True): "a fast-execute era",
    ("pace", False): "a default-heavy, slow era",
    ("util_discipline", True): "a utility-hoarding era",
    ("util_discipline", False): "a dump-and-hit era",
    ("map_control", True): "a spread-map-control era",
    ("map_control", False): "a stack-and-hit era",
}


def _record_meta_era(gs: GameState) -> None:
    """Season's end: if the league's tactical center of mass drifted off
    neutral, the chronicle remembers the era — and credits the regional
    champions who defined it (their dial furthest out the same way),
    which is what feeds a manager's tactical-innovation reputation."""
    tier1 = [t for t in gs.teams.values() if t.tier == 1]
    if not tier1:
        return
    champs = {
        e.team_id
        for e in gs.chronicle
        if e.kind == "regional_title" and e.season == gs.season
    }
    for dial in _ADAPT_DIALS:
        mean = float(np.mean([getattr(t.tactics, dial) for t in tier1]))
        if abs(mean - 50.0) < _META_ERA_DEV:
            continue
        high = mean > 50.0
        era = _META_ERA_NAMES[(dial, high)]
        chronicle.record(
            gs, "meta_shift",
            f"Season {gs.season} closes as {era}.",
            data={"dial": dial, "mean": f"{mean:.1f}"},
        )
        for tid in sorted(champs):
            t = gs.teams.get(tid)
            if t is None:
                continue
            v = getattr(t.tactics, dial)
            if (high and v >= mean + 4.0) or (not high and v <= mean - 4.0):
                chronicle.record(
                    gs, "meta_shift",
                    f"{t.name} defined the season's style ({era}).",
                    team_id=tid,
                    data={"dial": dial},
                )


def _run_offseason(gs: GameState, gd: GameData) -> WeekReport:
    report = WeekReport(season=gs.season, week=gs.week, phase="offseason")
    tree = RngTree(gs.seed)
    rng = tree.derive("season", gs.season, "offseason")

    # Awards first — they read the season aggregates being retired.
    season_awards = narrative.season_awards(gs)
    off_badge_rng = tree.derive("season", gs.season, "offseason", "badges")
    for a in season_awards:
        report.notes.append(f"{a.award}: {a.handle} ({a.team_name}) — {a.value}")
        winner_tid = next(
            (t.id for t in gs.teams.values() if a.player_id in t.player_ids),
            "",
        )
        chronicle.record(
            gs, "award",
            f"{a.handle} wins {a.award} ({a.value}).",
            team_id=winner_tid,
            player_id=a.player_id,
            importance=75.0 if "MVP" in a.award else 60.0,
            data={"award": a.award, "value": a.value},
        )
        # A league award revises the winner's ceiling up; the marquee ones
        # (MVP / Rookie of the Season) revise hardest and stamp the poster.
        winner = gs.players.get(a.player_id)
        if winner is not None:
            marquee = "MVP" in a.award or "Rookie" in a.award
            development.moment_potential_bump(
                winner, MOMENT_AWARD_MVP if marquee else MOMENT_AWARD
            )
            if marquee and "star_player" not in winner.personality_tags:
                winner.personality_tags = sorted(
                    {*winner.personality_tags, "star_player"}
                )

    # Award-linked badges — a chance at a named badge, not a coronation:
    # winning Clutch King only gives a shot at Clutch Master.
    badges.award_feats(gs, off_badge_rng, season_awards)

    # The All-Star Five (best per role) — chronicled + a news line inside.
    stars = narrative.season_all_star(gs)
    if stars:
        for s in stars:
            sp = gs.players.get(s["player_id"])
            if sp is not None:
                development.moment_potential_bump(sp, MOMENT_ALL_STAR)
        report.notes.append(
            "All-Star Five: " + ", ".join(f"{s['handle']} ({s['role']})" for s in stars)
        )

    # The season's tactical era enters the chronicle while the final
    # identities are still in state (tactics reassign below).
    _record_meta_era(gs)

    # Legacy mode: the board reviews the season goal while the season's
    # brackets and Masters seeds are still in state (they clear below).
    # Dismissals are only PARKED here — the unseat applies after the
    # inboxes generate at the end of this tick.
    board_dismissed = career.review_boards(gs)

    # The big offseason balance patch — rolled BEFORE the per-agent splits
    # reset below (patch content reads this season's pick rates).
    note = meta.roll_patch(
        gs, gd,
        tree.derive("season", gs.season, "patch", "off"),
        version=f"{gs.season + 1}.00",
    )
    if note is not None:
        report.notes.append(f"Patch {note.version} lands over the break.")
        knowledge.on_patch(gs)

    # Lifetime career totals absorb this season before the per-season stats
    # reset wipes them, and career-kill milestones enter the chronicle.
    _accumulate_career_stats(gs)

    gs.player_stats = {}
    gs.team_stats = {}
    gs.player_map_stats = {}
    gs.player_agent_stats = {}
    gs.team_map_stats = {}
    gs.map_meta_stats = {}

    # Earned traits unlock from settled career state (career_stats just rolled
    # up, season_start_ca still this season's baseline, age still the played-
    # season age) BEFORE aging shifts any of it. rng-free; AI parity.
    development.offseason_trait_unlocks(gs)

    for pid in sorted(gs.players):
        training.apply_offseason_aging(gs.players[pid], rng)
    prospect_rng = tree.derive("season", gs.season, "offseason", "future-prospects")
    for pid in sorted(gs.future_prospects):
        training.apply_offseason_aging(gs.future_prospects[pid].player, prospect_rng)

    # Badges decay: a fallen-off skill or a badge gone stale is lost — its CA
    # edge reverts, the ceiling it earned is kept. rng-free; every org.
    badges.decay(gs)

    # Careers end: a year older, some hang it up. Then the next
    # generation arrives as regional rookie classes.
    n_retired = _process_retirements(gs, rng)
    historical_debuts = _release_future_prospects(gs)
    _rookie_classes(gs, gd, rng, n_retired, historical_debuts)
    social.seed_followers(gs)  # rookies arrive with a baseline audience

    # Retirements just opened AI seats; refill them from the (now rookie-fed)
    # free-agent pool so every AI side starts the new season legal at
    # ROSTER_SIZE instead of carrying the gap into week 1. Humans keep their
    # open seat and sign for themselves. A dedicated rng stream leaves the
    # offseason's other draws — aging, retirements, tactics — byte-identical.
    refill_rng = tree.derive("season", gs.season, "offseason", "refill")
    market.ai_fill_rosters(gs, gd, refill_rng)

    # Season-in-review: one grounded paragraph over the season's records
    # (champion, MVP, biggest riser, marquee retirement, tactical era),
    # read while gs.season still names the season that just ended.
    review = narrative.season_in_review(gs)
    if review is not None:
        gs.push_news(review)
        report.notes.append(review)

    # Ended careers stop charting: prune the bulky per-week chart series for
    # anyone who has left. career_stats is DELIBERATELY exempt — it's the
    # persistent lifetime record the all-time record book / playtest exports
    # read (it carries its own handle), so a retired career-kill leader must
    # not vanish from the books.
    for hist in (gs.stat_history, gs.dev_history):
        for pid in sorted(hist):
            if pid not in gs.players:
                del hist[pid]
    # Mentorships dissolve when either party leaves (retirement / transfer).
    for pid in sorted(gs.mentorships):
        if pid not in gs.players or gs.mentorships[pid] not in gs.players:
            del gs.mentorships[pid]

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

    # New season. Each human manager's scouting knowledge goes stale over the
    # break (staff market refreshes below, after the season counter rolls).
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        gs.scout_progress = {}
    gs.set_acting(None)
    gs.masters_seeds = []
    gs.champions_seeds = []
    gs.transfer_offers = []
    gs.negotiations_by = {}
    gs.talks_cooldown_by = {}
    gs.map_lineups = {}
    gs.game_plans_by = {}
    gs.tournament_rosters = {}
    gs.series_directives_by = {}
    gs.preparation_plans_by = {}
    # Grudges cool over the break; the faint ones are forgotten.
    rivalries.offseason_decay(gs)
    # Institutional knowledge fades: anti-strats gut (their roster moved),
    # playbooks date, methodology mostly keeps.
    knowledge.offseason_decay(gs)
    # The break cools every fanbase halfway back to neutral — last
    # season's euphoria (or bile) carries in, but softer.
    gs.team_sentiment = {
        tid: round(50.0 + (v - 50.0) * 0.5, 1)
        for tid, v in sorted(gs.team_sentiment.items())
    }
    gs.season += 1
    if gs.calendar_year is not None:
        gs.calendar_year += 1
    # Staff market churn: retirements out, the new season's class in
    # (one shared pool — no per-manager refresh).
    staff.offseason_churn(gs)
    gs.week = 1
    gs.phase = "regular"
    _assign_ai_tactics(gs, rng)  # new rosters, new coaching identities
    gs.fixtures = _build_all_leagues(
        gs.teams, sorted(gd.maps), gs.season, gs.league_regions
    )
    gs.standings = {tid: TeamRecord() for tid in gs.teams}
    academy.offseason_intake(gs)
    culture.ensure_leadership(gs)
    gs.push_news(f"Season {gs.season} begins.")
    report.notes.append(f"Offseason complete — Season {gs.season} starts now.")
    _update_world_ranks(gs)
    _snapshot_season_start_ca(gs)  # baseline for next season's Most Improved
    _record_dev_snapshots(gs, week=0)
    # Inbox for the offseason tick, per manager: retirements, rookie class,
    # award slate. `report` still carries the pre-rollover (season, week) the
    # offseason news was labelled with, so generate_inbox reads the right lines.
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        inbox.generate_inbox(gs, report)
    gs.set_acting(None)
    if board_dismissed:
        career.apply_dismissals(gs, board_dismissed)
        for mid in board_dismissed:
            old = gs.managers[mid].last_team_id
            gs.inboxes.setdefault(old, []).append(
                career.dismissal_inbox_item(gs, mid, report.season, report.week)
            )
        report.notes.append(
            "The board has made a change - accept a new post to continue."
        )
    # The offseason tick's snapshot is the new season's baseline (season
    # already rolled, standings reset) — the episode boundary marker.
    telemetry.weekly_snapshots(gs)
    flavor_events.queue_weekly_events(gs)
    return report
