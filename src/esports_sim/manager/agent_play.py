"""Multi-agent shared-world play over the headless manager contract.

Several agents each manage a team in ONE ``GameState``, exactly the way LAN
humans share a world in the web layer: every externally controlled team is a
``human_team_ids`` seat, each seat observes and acts through the
``decision_env`` contract (fog-safe observation + explicit legal-action
masks), and the week only ticks once EVERY seat has voted ``advance`` — the
same ready-up barrier the web's ``/api/actions/advance`` uses, so agents and
browser humans can share a world.

The objective agents play for is championships: ``objective_view`` serializes
titles won (Champions > Masters > regional split), the live standings/bracket
position, and the rival seats' trophy cases, all derived from the chronicle
and standings — nothing new is persisted, so saves and campaign determinism
are untouched.

Determinism contract: seed + the GLOBAL ordered action sequence (every seat's
actions, in the order they were applied) fully determines the world. Two runs
that replay the same seed and the same interleaving produce byte-identical
``GameState`` saves. Actions from different seats are first-come-first-served
(two agents racing for the same free agent is real multiplayer contention);
``gs.action_log`` records the authoritative order.

This module is deliberately framework-free (no FastAPI): the web layer's
``/api/agent/*`` endpoints and in-process harnesses both drive it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from esports_sim.manager import career, flavor_events, market, media_events, telemetry
from esports_sim.manager.campaign import WeekReport, advance_week, new_campaign
from esports_sim.manager.decision_env import (
    OBSERVATION_VERSION,
    SUPPORTED_ACTIONS,
    HeadlessManagerEnv,
    InvalidManagerAction,
    manager_observation,
)

from esports_sim.manager.state import GameState
from esports_sim.registry import GameData
from esports_sim.registry.rosters import load_roster_pack
from esports_sim.schemas import Event

__all__ = [
    "AGENT_PLAY_VERSION",
    "OBSERVATION_VERSION",
    "SUPPORTED_ACTIONS",
    "TITLE_KINDS",
    "AgentWorld",
    "InvalidManagerAction",
    "ShortRosters",
    "WeekTick",
    "advance_blockers",
    "league_view",
    "manager_observation",
    "objective_view",
    "seat_week_results",
    "sync_view",
    "tick_shared_week",
    "title_counts",
    "titles_timeline",
]

AGENT_PLAY_VERSION = 1

# Chronicle kinds that count as titles, in objective order (the season-capping
# Champions bracket is the top prize agents play for).
TITLE_KINDS = (
    "champions_title",
    "masters_title",
    "regional_title",
    "challengers_title",
)


class ShortRosters(Exception):
    """Raised at tick time when a ready seat's roster fell below legal size
    while it waited (a release/sale after voting). Carries the offenders so
    the caller can strip their ready flags — the web endpoint's semantics."""

    def __init__(self, team_ids: list[str]):
        self.team_ids = list(team_ids)
        super().__init__(
            "short rosters at tick time: " + ", ".join(self.team_ids)
        )


def advance_blockers(gs: GameState, team_id: str) -> str:
    """Why this seat may not vote advance right now ("" = clear to vote).

    Mirrors the guards of both the web advance endpoint and the decision_env
    advance action, so agents see one consistent contract."""
    if gs.fantasy_draft is not None and gs.fantasy_draft.active:
        return "finish the fantasy draft before the season can start"
    if flavor_events.pending_for(gs, team_id) is not None:
        return "resolve the pending flavor event before advancing"
    if media_events.pending_for(gs, team_id) is not None:
        return "resolve the pending media decision before advancing"
    blocked = career.blocked_seats(gs)
    if blocked:
        names = ", ".join(gs.managers[m].name for m in blocked)
        return f"waiting on a manager to accept a new post ({names})"
    ok, why = market.roster_ready(gs, team_id)
    if not ok:
        return why
    return ""


@dataclass(frozen=True)
class WeekTick:
    """One resolved shared week: the campaign report plus a per-seat digest."""

    season: int  # season the tick started in
    week: int  # week that was resolved
    report: WeekReport
    summaries: dict[str, dict[str, Any]]


def seat_week_results(gs: GameState, team_id: str, week: int) -> list[dict[str, Any]]:
    """This seat's played fixtures for one week, from the seat's viewpoint."""
    out: list[dict[str, Any]] = []
    for f in sorted(gs.fixtures, key=lambda x: (x.week, x.id)):
        if f.week != week or not f.played or team_id not in (f.team_a, f.team_b):
            continue
        opponent = f.team_b if f.team_a == team_id else f.team_a
        a, b = f.map_score
        mine, theirs = (a, b) if f.team_a == team_id else (b, a)
        out.append(
            {
                "fixture_id": f.id,
                "stage": f.stage,
                "bracket": f.bracket,
                "best_of": f.best_of,
                "opponent_id": opponent,
                "opponent_name": (
                    gs.teams[opponent].name if opponent in gs.teams else opponent
                ),
                "score": [mine, theirs],
                "won": f.winner_id == team_id,
                "maps": [
                    {
                        "map_id": r.map_id,
                        "score": (
                            [r.score_a, r.score_b]
                            if f.team_a == team_id
                            else [r.score_b, r.score_a]
                        ),
                        "won": r.winner_id == team_id,
                    }
                    for r in f.results
                ],
            }
        )
    return out


def _region_position(gs: GameState, team_id: str) -> dict[str, Any]:
    team = gs.teams[team_id]
    order = gs.standings_order(str(team.region), tier=team.tier)
    rec = gs.standings.get(team_id)
    return {
        "region": str(team.region),
        "position": order.index(team_id) + 1 if team_id in order else 0,
        "teams": len(order),
        "wins": rec.wins if rec is not None else 0,
        "losses": rec.losses if rec is not None else 0,
        "round_diff": rec.diff if rec is not None else 0,
    }


def tick_shared_week(
    gs: GameState,
    gd: GameData,
    ready: set[str],
    *,
    events_out: dict[str, list[list[Event]]] | None = None,
    source: str = "agent",
) -> WeekTick:
    """Advance the shared world exactly once, after every seat has voted.

    The caller owns the vote (the ready set) and its lifecycle; this function
    owns the deterministic tick: revalidate every seat's roster (raising
    ``ShortRosters`` so the caller can strip offenders' votes), record each
    seat's advance decision, run ``advance_week`` once, and build a per-seat
    digest (reward components, match results, standings movement) so every
    agent learns what the week did to THEM regardless of which request
    triggered the tick."""
    humans = sorted(gs.human_team_ids)
    if set(humans) - set(ready):
        raise ValueError("tick_shared_week called before every seat was ready")
    # A seat may have sold/released a player AFTER voting; a short roster
    # cannot slip the week through.
    short = [t for t in humans if not market.roster_ready(gs, t)[0]]
    if short:
        raise ShortRosters(short)

    previous_acting = gs.acting_team_id
    season_before = gs.season
    week_before = gs.week
    phase_before = gs.phase
    seats_before = {t: gs.manager_for(t) for t in humans}
    # Each seat's ready-up is its own recorded decision (the advance is the
    # RL episode's step boundary) — same ordering as the web endpoint.
    for t in humans:
        telemetry.record_action(gs, "advance", team_id=t, source=source)
    features_before = {t: telemetry.state_features(gs, t) for t in humans}
    positions_before = {t: _region_position(gs, t) for t in humans}

    report = advance_week(gs, gd, events_out=events_out)
    # advance_week churns the acting pointer internally; restore the caller's.
    gs.set_acting(previous_acting)

    season_rolled = gs.season > season_before
    crowned = next(
        (c for c in gs.champions if c.season == season_before), None
    ) if season_rolled else None
    summaries: dict[str, dict[str, Any]] = {}
    for t in humans:
        after = telemetry.state_features(gs, t)
        seat = seats_before[t]
        dismissed = bool(
            seat is not None
            and seat.id in gs.managers
            and not gs.managers[seat.id].team_id
        )
        components = (
            telemetry.reward_components(
                features_before[t], after, dismissed=dismissed
            )
            if gs.season == season_before
            else {}
        )
        reward = float(components.pop("reward", 0.0)) if components else 0.0
        summaries[t] = {
            "season": season_before,
            "week": week_before,
            "phase_before": phase_before,
            "now_season": gs.season,
            "now_week": gs.week,
            "now_phase": gs.phase,
            "results": seat_week_results(gs, t, week_before),
            "income": report.income_by.get(t, 0),
            "expenses": report.expenses_by.get(t, 0),
            "position_before": positions_before[t],
            "position": _region_position(gs, t),
            "reward": reward,
            "reward_components": components,
            "done": dismissed,
            "season_rolled": season_rolled,
            "season_champion": (
                {
                    "season": crowned.season,
                    "team_id": crowned.team_id,
                    "team_name": crowned.team_name,
                    "yours": crowned.team_id == t,
                }
                if crowned is not None
                else None
            ),
        }
    return WeekTick(
        season=season_before, week=week_before, report=report, summaries=summaries
    )


# ---------------------------------------------------------------------------
# Objective + league serializers (championships are the goal)


def title_counts(gs: GameState, team_id: str) -> dict[str, int]:
    counts = {kind: 0 for kind in TITLE_KINDS}
    for e in gs.chronicle:
        if e.kind in counts and e.team_id == team_id:
            counts[e.kind] += 1
    # Champions has a dedicated record list too (pre-chronicle saves); take
    # the max so neither source undercounts.
    counts["champions_title"] = max(
        counts["champions_title"],
        sum(1 for c in gs.champions if c.team_id == team_id),
    )
    return {
        "champions": counts["champions_title"],
        "masters": counts["masters_title"],
        "regional": counts["regional_title"],
        "challengers": counts["challengers_title"],
        "total": sum(counts.values()),
    }


def titles_timeline(gs: GameState) -> list[dict[str, Any]]:
    """Every title in the world's history: season, kind, and who won it."""
    out = [
        {
            "season": e.season,
            "kind": e.kind,
            "team_id": e.team_id,
            "team_name": (
                gs.teams[e.team_id].name if e.team_id in gs.teams else e.team_id
            ),
        }
        for e in gs.chronicle
        if e.kind in TITLE_KINDS and e.team_id
    ]
    seen_champion_seasons = {
        row["season"] for row in out if row["kind"] == "champions_title"
    }
    for c in gs.champions:
        if c.season not in seen_champion_seasons:
            out.append(
                {
                    "season": c.season,
                    "kind": "champions_title",
                    "team_id": c.team_id,
                    "team_name": c.team_name,
                }
            )
    out.sort(key=lambda r: (r["season"], TITLE_KINDS.index(r["kind"]), r["team_id"]))
    return out


def _season_prefix(gs: GameState) -> str:
    return f"s{gs.season}"


def _postseason_fixtures(
    gs: GameState, team_id: str | None = None
) -> list[dict[str, Any]]:
    """This season's non-regular fixtures (regional playoffs, Masters,
    Champions), optionally restricted to one team, in schedule order."""
    prefix = _season_prefix(gs)
    out = []
    for f in sorted(gs.fixtures, key=lambda x: (x.week, x.id)):
        if f.stage == "regular" or not f.id.startswith(prefix):
            continue
        if team_id is not None and team_id not in (f.team_a, f.team_b):
            continue
        a, b = f.map_score
        out.append(
            {
                "fixture_id": f.id,
                "week": f.week,
                "stage": f.stage,
                "bracket": f.bracket,
                "team_a": f.team_a,
                "team_b": f.team_b,
                "played": f.played,
                "score": [a, b] if f.played else None,
                "winner_id": f.winner_id,
            }
        )
    return out


def _h2h_this_season(gs: GameState, team_id: str, rival_id: str) -> dict[str, int]:
    prefix = _season_prefix(gs)
    wins = losses = 0
    for f in gs.fixtures:
        if not f.played or not f.id.startswith(prefix):
            continue
        if {f.team_a, f.team_b} != {team_id, rival_id}:
            continue
        if f.winner_id == team_id:
            wins += 1
        elif f.winner_id == rival_id:
            losses += 1
    return {"wins": wins, "losses": losses}


def objective_view(gs: GameState, team_id: str) -> dict[str, Any]:
    """The championship scoreboard from one seat's viewpoint.

    This is the block a harness scores agents on: titles won so far (the
    chronicle never forgets), where the seat stands right now, and how the
    rival seats' trophy cases compare."""
    if team_id not in gs.teams:
        raise KeyError(f"unknown team {team_id!r}")
    rivals = []
    for tid in sorted(gs.human_team_ids):
        if tid == team_id or tid not in gs.teams:
            continue
        rivals.append(
            {
                "team_id": tid,
                "team_name": gs.teams[tid].name,
                "region": str(gs.teams[tid].region),
                "position": _region_position(gs, tid),
                "titles": title_counts(gs, tid),
                "head_to_head_this_season": _h2h_this_season(gs, team_id, tid),
            }
        )
    return {
        "goal": (
            "Win championships. The season-capping Champions bracket is the "
            "top prize; Masters and the regional split are secondary titles. "
            "Every title is chronicled forever and counted in titles below."
        ),
        "team_id": team_id,
        "team_name": gs.teams[team_id].name,
        "season": gs.season,
        "week": gs.week,
        "phase": gs.phase,
        "titles": title_counts(gs, team_id),
        "titles_won": [
            row for row in titles_timeline(gs) if row["team_id"] == team_id
        ],
        "regular_season": _region_position(gs, team_id),
        "postseason": {
            "masters_seed": team_id in gs.masters_seeds,
            "champions_seed": team_id in gs.champions_seeds,
            "my_fixtures": _postseason_fixtures(gs, team_id),
        },
        "champions_history": [
            {"season": c.season, "team_id": c.team_id, "team_name": c.team_name}
            for c in gs.champions
        ],
        "rival_seats": rivals,
    }


def league_view(gs: GameState) -> dict[str, Any]:
    """The whole league at a glance: tables, postseason, titles, seats."""
    regions: dict[str, list[dict[str, Any]]] = {}
    region_names = sorted(
        {str(t.region) for t in gs.teams.values() if t.tier == 1}
    )
    for region in region_names:
        rows = []
        for pos, tid in enumerate(gs.standings_order(region, tier=1), start=1):
            rec = gs.standings.get(tid)
            rows.append(
                {
                    "position": pos,
                    "team_id": tid,
                    "team_name": gs.teams[tid].name,
                    "wins": rec.wins if rec is not None else 0,
                    "losses": rec.losses if rec is not None else 0,
                    "round_diff": rec.diff if rec is not None else 0,
                    "human": gs.is_human(tid),
                }
            )
        regions[region] = rows
    return {
        "agent_play_version": AGENT_PLAY_VERSION,
        "season": gs.season,
        "week": gs.week,
        "phase": gs.phase,
        "regions": regions,
        "postseason_fixtures": _postseason_fixtures(gs),
        "masters_seeds": list(gs.masters_seeds),
        "champions_seeds": list(gs.champions_seeds),
        "titles": titles_timeline(gs),
        "champions_history": [
            {"season": c.season, "team_id": c.team_id, "team_name": c.team_name}
            for c in gs.champions
        ],
        "seats": [
            {
                "team_id": tid,
                "team_name": gs.teams[tid].name if tid in gs.teams else tid,
                "region": (
                    str(gs.teams[tid].region) if tid in gs.teams else ""
                ),
            }
            for tid in sorted(gs.human_team_ids)
        ],
    }


def sync_view(
    gs: GameState,
    ready: Iterable[str],
    team_id: str,
    *,
    tick_seq: int = 0,
    last_tick: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The multiplayer heartbeat one seat polls: who else is in the world,
    who has voted advance, whether this seat may vote, and what the most
    recently resolved week did to this seat."""
    ready_set = set(ready)
    return {
        "agent_play_version": AGENT_PLAY_VERSION,
        "season": gs.season,
        "week": gs.week,
        "phase": gs.phase,
        "tick_seq": tick_seq,
        "seats": [
            {
                "team_id": tid,
                "team_name": gs.teams[tid].name if tid in gs.teams else tid,
                "is_you": tid == team_id,
                "ready": tid in ready_set,
            }
            for tid in sorted(gs.human_team_ids)
        ],
        "you_ready": team_id in ready_set,
        "waiting_on": [
            tid for tid in sorted(gs.human_team_ids) if tid not in ready_set
        ],
        "advance_blocker": advance_blockers(gs, team_id),
        "last_tick": last_tick,
    }


# ---------------------------------------------------------------------------
# In-process coordinator


class AgentWorld:
    """N externally controlled seats sharing one deterministic world.

    The in-process counterpart of a shared web world: harnesses that run all
    their agents in one process (tests, RL loops, tournament scripts) drive
    this directly; remote agents use the ``/api/agent/*`` HTTP surface, which
    shares the same functions. Not thread-safe — callers serialize access
    (the web layer holds its per-world lock)."""

    def __init__(
        self,
        gs: GameState,
        gd: GameData,
        *,
        capture_events: bool = False,
        policy_version: str = "agent-world-v1",
    ) -> None:
        self.gs = gs
        self.gd = gd
        self.ready: set[str] = set()
        self.tick_seq = 0
        self.last_tick: dict[str, dict[str, Any]] = {}
        self.last_report: WeekReport | None = None
        self.event_logs: dict[str, list[list[Event]]] | None = (
            {} if capture_events else None
        )
        self._envs = {
            tid: HeadlessManagerEnv(gs, gd, tid, policy_version=policy_version)
            for tid in sorted(gs.human_team_ids)
        }
        if not self._envs:
            raise ValueError("world has no externally controlled seats")

    @classmethod
    def create(
        cls,
        gd: GameData,
        *,
        seed: int,
        team_ids: list[str] | None = None,
        n_teams: int | None = None,
        pack_id: str | None = None,
        manager_names: list[str] | None = None,
        capture_events: bool = False,
    ) -> "AgentWorld":
        """Build a fresh sandbox world with one seat per agent team.

        Exactly one of ``team_ids`` (explicit clubs) or ``n_teams`` (the
        first N tier-1 clubs, deterministic) is required. Sandbox mode only:
        career offers/dismissal are a lobby flow, and a fantasy draft would
        gate the season behind draft picks the decision contract does not
        include."""
        if (team_ids is None) == (n_teams is None):
            raise ValueError("specify exactly one of team_ids or n_teams")
        pack = load_roster_pack(pack_id) if pack_id else None
        # Fictional worlds GENERATE their team ids from the seed, so resolve
        # and validate picks against a same-seed probe world (the id set the
        # real build below will produce; user_team_id does not affect it).
        if pack is not None:
            placeholder = sorted(
                t.id for t in pack.teams.values() if t.tier == 1
            )[0]
        else:
            placeholder = "team_nexus"
        probe = new_campaign(
            gd, seed=seed, pack=pack, mode="sandbox", user_team_id=placeholder
        )
        tier1 = [
            tid for tid in sorted(probe.teams) if probe.teams[tid].tier == 1
        ]
        if n_teams is not None:
            if not 1 <= n_teams <= len(tier1):
                raise ValueError(
                    f"n_teams must be between 1 and {len(tier1)} for this world"
                )
            team_ids = tier1[:n_teams]
        assert team_ids is not None
        if len(set(team_ids)) != len(team_ids):
            raise ValueError("team_ids contains duplicates")
        unknown = [tid for tid in team_ids if tid not in probe.teams]
        if unknown:
            raise ValueError(
                "unknown team ids for this world: " + ", ".join(unknown)
            )
        names = list(manager_names or [])
        if names and len(names) != len(team_ids):
            raise ValueError("manager_names must match team_ids in length")
        gs = new_campaign(
            gd,
            seed=seed,
            user_team_id=team_ids[0],
            pack=pack,
            mode="sandbox",
            manager_name=names[0] if names else "",
        )
        for i, tid in enumerate(team_ids[1:], start=1):
            gs.human_team_ids.append(tid)
            if gs.manager_for(tid) is None:
                career.create_seat(gs, tid, name=names[i] if names else "")
        return cls(gs, gd, capture_events=capture_events)

    @property
    def team_ids(self) -> list[str]:
        return sorted(self._envs)

    def _env(self, team_id: str) -> HeadlessManagerEnv:
        env = self._envs.get(team_id)
        if env is None:
            raise KeyError(f"no agent seat controls team {team_id!r}")
        return env

    def observe(self, team_id: str) -> dict[str, Any]:
        """One seat's full turn context: the decision_env observation (with
        legal_actions) plus the multiplayer sync block and the championship
        objective."""
        env = self._env(team_id)
        obs = env.observe()
        obs["sync"] = sync_view(
            self.gs,
            self.ready,
            team_id,
            tick_seq=self.tick_seq,
            last_tick=self.last_tick.get(team_id),
        )
        obs["objective"] = objective_view(self.gs, team_id)
        return obs

    def act(self, team_id: str, action: dict[str, Any]) -> dict[str, Any]:
        """Apply one action for one seat.

        Non-advance actions resolve immediately through the seat's
        ``HeadlessManagerEnv`` (raising ``InvalidManagerAction`` with the
        reason when malformed/illegal). ``advance`` is a ready vote: the
        world ticks exactly once when the LAST seat votes, and every seat's
        digest of that week lands in its next ``observe()`` under
        ``sync.last_tick``."""
        env = self._env(team_id)
        kind = str(action.get("kind", ""))
        if kind != "advance":
            step = env.step(action)
            # accept_job moves the seat to a new club (legacy worlds); the
            # coordinator's keys and vote follow the seat, like the web
            # session rebinding.
            if kind == "accept_job" and env.team_id != team_id:
                self._envs[env.team_id] = self._envs.pop(team_id)
                self.ready.discard(team_id)
                if team_id in self.last_tick:
                    self.last_tick[env.team_id] = self.last_tick.pop(team_id)
            return {
                "ok": True,
                "kind": kind,
                "message": step.message,
                "advanced": False,
                "team_id": env.team_id,
                "seq": len(self.gs.action_log),
            }

        blocker = advance_blockers(self.gs, team_id)
        if blocker:
            raise InvalidManagerAction(blocker)
        self.ready.add(team_id)
        waiting = [
            t for t in sorted(self.gs.human_team_ids) if t not in self.ready
        ]
        if waiting:
            return {
                "ok": True,
                "kind": "advance",
                "message": "ready — waiting on the other seats",
                "advanced": False,
                "waiting_on": waiting,
                "ready": sorted(self.ready),
                "seq": len(self.gs.action_log),
            }
        try:
            tick = tick_shared_week(
                self.gs, self.gd, self.ready, events_out=self.event_logs
            )
        except ShortRosters as exc:
            for t in exc.team_ids:
                self.ready.discard(t)
            names = ", ".join(
                self.gs.teams[t].name if t in self.gs.teams else t
                for t in exc.team_ids
            )
            raise InvalidManagerAction(
                f"can't advance — {names} need {market.ROSTER_MIN} players "
                "(re-ready once fixed)"
            ) from exc
        self.ready.clear()
        self.tick_seq += 1
        self.last_tick = tick.summaries
        self.last_report = tick.report
        return {
            "ok": True,
            "kind": "advance",
            "message": "week advanced",
            "advanced": True,
            "seq": len(self.gs.action_log),
            "tick": tick.summaries.get(team_id),
        }

    def objective(self, team_id: str) -> dict[str, Any]:
        return objective_view(self.gs, team_id)

    def league(self) -> dict[str, Any]:
        return league_view(self.gs)

    def observation_for_prompt(self, team_id: str) -> str:
        """The observation as canonical JSON — what an LLM seat is shown."""
        return json.dumps(self.observe(team_id), sort_keys=True)
