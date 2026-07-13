"""Tick-level match referee.

The engine enforces legality, movement, utility resolution, combat, the
spike, and typed event emission.  Policies make the tactical decisions: one
player policy per dressed player, a team policy per side, and a thin coach
policy that may speak only through a timeout between rounds.

Determinism contract: every random draw comes from a per-round generator
derived from (match, round) labels on the RngTree, and all iteration is in
sorted order. Same seed → byte-identical event log (see
tests/test_determinism.py).
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from esports_sim.events.log import EventLog
from esports_sim.policy.base import (
    Action,
    ActionType,
    AttackRoundRequest,
    BuyPlanRequest,
    CoachObservation,
    CoachPolicy,
    CoachProfile,
    CommunicationPolicy,
    DefenseRoundRequest,
    PlayerPolicy,
    RotationPlanRequest,
    TeamPolicy,
    TimeoutDirective,
)
from esports_sim.registry.loader import GameData, load_geometry
from esports_sim.sim import lineup as lineup_resolve
from esports_sim.schemas import (
    Ability,
    AbilityEffect,
    BuyEvent,
    ClaimKind,
    ClaimValue,
    CommunicationAction,
    EnemyReadout,
    Event,
    DuelTelemetryEvent,
    HalftimeTalkEvent,
    TouchlineShoutEvent,
    Gimmick,
    GimmickType,
    GimmickUsedEvent,
    KillEvent,
    Map,
    MatchEndEvent,
    MatchStartEvent,
    MoveEvent,
    Player,
    PlayerConditionV1,
    PlayerObservation,
    PlayerRoundState,
    RoundEndEvent,
    RoundStartEvent,
    SpikeDefuseEvent,
    SpikePlantEvent,
    TimeoutEvent,
    UtilityUsedEvent,
)
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import CommsEvent, WhiffEvent
from esports_sim.schemas.map import CalloutZone, Site
from esports_sim.schemas.team import TeamTactics, HalftimeTalk, TouchlineShout, ShoutTrigger
from esports_sim.schemas.traits import trait_value
from esports_sim.sim import constants as C
from esports_sim.sim.comms import TeamWhiteboard
from esports_sim.sim import tactics_fit


@dataclass
class MatchResult:
    match_id: str
    map_id: str
    team_a_id: str
    team_b_id: str
    score_a: int
    score_b: int
    winner_id: str
    events: list[Event]


@dataclass
class MatchPolicies:
    """Optional replacements for the heuristic policy stack.

    Missing entries use the deterministic in-repo heuristics, which lets an
    RL or playtest policy replace one player (or one layer) without having to
    supply the other nine actors.
    """

    player_by_id: dict[str, PlayerPolicy] = field(default_factory=dict)
    communication_by_id: dict[str, CommunicationPolicy] = field(default_factory=dict)
    team_by_id: dict[str, TeamPolicy] = field(default_factory=dict)
    coach_by_team: dict[str, CoachPolicy] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamMatchPlan:
    """Per-match inputs supplied by the campaign layer.

    ``tactics`` is a pre-match identity selected by the manager; it is read
    by the team policy rather than used as live coach input.  ``coach`` is a
    thin match projection of campaign staff and can act only at a timeout.

    tactics: replaces the standing TeamTactics for THIS match only (the
        dials themselves stay neutral-safe per ADR-007).
    focus_target: opponent pid the anti-strat keys on — a real duel edge
        against the hunted player, paid for with a small tax everywhere
        else (over-indexing prep on one man has a cost).
    prep_edge: scouting-driven duel bonus for the prepared side; the
        campaign computes it from scout knowledge, the engine only clamps.
    counter_edge: signed matchup bonus from deliberate dial overrides; a
        correct anti-strat helps and leaning into the opponent's identity hurts.
    """

    tactics: TeamTactics | None = None
    focus_target: str | None = None
    prep_edge: float = 0.0
    counter_edge: float = 0.0
    coach: CoachProfile | None = None
    halftime_talk: HalftimeTalk | None = None
    shouts: dict[ShoutTrigger, TouchlineShout] = field(default_factory=dict)


@dataclass
class _PState:
    """Engine-internal runtime state for one player. The pydantic
    PlayerRoundState is materialized from this only when a policy is
    consulted."""

    pid: str
    team_id: str
    agent_id: str
    # persistent across rounds
    credits: int = C.STARTING_CREDITS
    weapon: str = "classic"
    armor: int = 0
    ult_points: int = 0
    # per-round state
    alive: bool = True
    callout: str = ""
    # Continuous position (grid coords). Updated every tick while moving.
    x: float = 0.0
    y: float = 0.0
    # Waypoints still ahead on the current move (excludes current pos).
    path: list[tuple[float, float]] = field(default_factory=list)
    order: str = "hold"
    role: str = "flex"
    move_dest: str | None = None
    move_eta: int = -1
    planting_until: int = -1
    defusing_until: int = -1
    flash_until: int = -1
    # Who flashed this player last (flash-assist credit while blind).
    flashed_by: str | None = None
    bonus_until: int = -1
    bonus: float = 0.0
    no_engage_until: int = -1  # disengage grace while falling back
    peek_until: int = -1  # player-policy selected swing window
    mobility_until: int = -1  # dash/blast/teleport speeds the next move
    # Unit vector this player is pre-aiming down while stationary.
    watch: tuple[float, float] | None = None
    has_spike: bool = False
    charges: dict[str, int] = field(default_factory=dict)

    @property
    def busy(self) -> bool:
        return (
            self.move_eta >= 0
            or self.planting_until >= 0
            or self.defusing_until >= 0
        )


@dataclass(slots=True)
class _FastPlayerState:
    """Minimal, allocation-cheap state consumed by the shipped heuristic."""

    player_id: str
    credits: int
    weapon_id: str
    armor: int
    callout_id: str | None


@dataclass(slots=True)
class _FastObservation:
    """Private hot-path counterpart to the public PlayerObservation schema."""

    self_state: _FastPlayerState
    tick: int
    igl_call: str | None
    tactical_aggression: float
    timeout_directive: str | None


@dataclass(slots=True)
class _PendingFlash:
    """One flash waiting for a duel at its intended site."""

    target_side: str
    target_site: str
    owner_id: str | None
    expires_at: int


class _MatchSim:
    def __init__(
        self,
        gd: GameData,
        team_a: str,
        team_b: str,
        map_id: str,
        seed: int,
        log: EventLog | None = None,
        plans: dict[str, TeamMatchPlan] | None = None,
        policies: MatchPolicies | None = None,
    ):
        self.gd = gd
        self.map: Map = gd.maps[map_id]
        self.team_a = team_a
        self.team_b = team_b
        self.match_id = f"{team_a}_vs_{team_b}_{map_id}_{seed}"
        self.rng_tree = RngTree(root_seed=seed)
        self.seed = seed
        self.log = log if log is not None else EventLog()
        hold = Action.model_construct(type=ActionType.HOLD)
        wait = Action.model_construct(type=ActionType.WAIT)
        peek = Action.model_construct(type=ActionType.PEEK)
        self._fast_legal_by_callout: dict[str, tuple[Action, ...]] = {
            callout: (
                hold,
                wait,
                peek,
                *(
                    Action.model_construct(
                        type=ActionType.MOVE_TO, callout_id=neighbor
                    )
                    for neighbor in sorted(self.map.neighbors(callout))
                ),
            )
            for callout in sorted(self.map.callouts)
        }
        self._fast_buy_legal = (Action.model_construct(type=ActionType.BUY),)
        self._fast_plant_action = Action.model_construct(type=ActionType.PLANT_SPIKE)
        self._fast_defuse_action = Action.model_construct(type=ActionType.DEFUSE_SPIKE)

        # Game plans (campaign-fed; None for the bare-engine gates). Must
        # be bound BEFORE exec_mod below — _execution_mod reads tactics
        # through _tactics(), which honours a plan's override.
        self._plans: dict[str, TeamMatchPlan] = plans or {}
        self._prep: dict[str, float] = {
            team_a: 0.0,
            team_b: 0.0,
        }
        self._counter: dict[str, float] = {
            team_a: 0.0,
            team_b: 0.0,
        }
        for tid in (team_a, team_b):
            plan = self._plans.get(tid)
            if plan is not None:
                self._prep[tid] = float(
                    np.clip(plan.prep_edge, 0.0, C.PREP_EDGE_CAP)
                )
                self._counter[tid] = float(
                    np.clip(
                        plan.counter_edge,
                        -C.COUNTER_STRAT_CAP,
                        C.COUNTER_STRAT_CAP,
                    )
                )

        # Roster: the week's committed starters, sorted for deterministic
        # iteration. Default (no lineup set) = the whole roster, so this stays
        # byte-identical to the pre-lineup engine (see sim/lineup.py). The
        # campaign fields benched rosters through _dressed_gamedata, so the
        # engine itself never sees more than the dressed five.
        self.roster: dict[str, list[str]] = {
            team_a: lineup_resolve.resolve_starters(gd.teams[team_a]),
            team_b: lineup_resolve.resolve_starters(gd.teams[team_b]),
        }
        self.p: dict[str, _PState] = {}
        for tid in (team_a, team_b):
            for pid in self.roster[tid]:
                pl = gd.players[pid]
                agent = lineup_resolve.resolve_agent(gd.teams[tid], pl, gd.agents)
                self.p[pid] = _PState(pid=pid, team_id=tid, agent_id=agent)

        # Local import keeps policy.heuristic independently importable even
        # though it reads sim constants and sim.__init__ exposes this engine.
        from esports_sim.policy.heuristic import (
            HeuristicCoachPolicy,
            HeuristicPolicy,
            HeuristicTeamPolicy,
        )

        self._heuristic_player_type = HeuristicPolicy
        supplied = policies or MatchPolicies()
        self.team_policies: dict[str, TeamPolicy] = {
            tid: supplied.team_by_id.get(tid, HeuristicTeamPolicy(gd, self.map))
            for tid in (team_a, team_b)
        }
        self.player_policies: dict[str, PlayerPolicy] = {
            pid: supplied.player_by_id.get(pid, HeuristicPolicy(gd, self.map))
            for pid in sorted(self.p)
        }
        self.communication_policies = dict(supplied.communication_by_id)
        self.coach_policies: dict[str, CoachPolicy] = {
            tid: supplied.coach_by_team.get(tid, HeuristicCoachPolicy())
            for tid in (team_a, team_b)
        }
        self.coaches: dict[str, CoachProfile] = {}
        for tid in (team_a, team_b):
            plan = self._plans.get(tid)
            self.coaches[tid] = (
                plan.coach
                if plan is not None and plan.coach is not None
                else CoachProfile(id=f"{tid}:coach")
            )
        self._timeout_used = {team_a: False, team_b: False}
        self._timeout_directive: dict[str, TimeoutDirective | None] = {
            team_a: None,
            team_b: None,
        }
        self._round_target: dict[str, str | None] = {team_a: None, team_b: None}
        self._round_policy_rngs: dict[str, np.random.Generator] = {}
        self._whiteboard = TeamWhiteboard(
            self.rng_tree, self.match_id, self.map, gd.players
        )
        self._enemy_memory: dict[str, dict[str, EnemyReadout]] = {
            pid: {} for pid in self.p
        }
        self._round_num = 0

        self.score = {team_a: 0, team_b: 0}
        self.loss_streak = {team_a: 0, team_b: 0}
        self.kills = {team_a: 0, team_b: 0}
        self.site_wins: dict[str, int] = {}
        self.active_shout: dict[str, tuple[str, int] | None] = {team_a: None, team_b: None}
        self.fired_shouts: dict[str, set[str]] = {team_a: set(), team_b: set()}
        self._tactics_offsets: dict[str, dict[str, float]] = {
            tid: {"aggression": 0.0, "pace": 0.0, "util_discipline": 0.0, "eco_greed": 0.0, "map_control": 0.0}
            for tid in (team_a, team_b)
        }

        # All-pairs BFS hop distances + sightline lookup, computed once.
        self.dist = self._all_pairs_dist()
        self._sight: dict[frozenset[str], str | None] = {
            frozenset((sl.from_callout, sl.to_callout)): sl.advantaged_side
            for sl in self.map.sightlines
        }

        # Floor geometry (optional): rooms, props, elevation. With it,
        # players hold real positions at tactical slots, travel at speed
        # through corridors, and duels are fought point-to-point. Without
        # it, positions collapse to the callout anchors and everything
        # still runs (straight-line paths, no cover/height/blocking).
        self._geo = load_geometry(map_id)
        self._z: dict[str, float] = {}
        self._slots: dict[str, list[tuple[float, float, str]]] = {}
        if self._geo is not None:
            for rid, region in self._geo.regions.items():
                self._z[rid] = region.z
                self._slots[rid] = self._geo.room_slots(rid)
        for cid, c in self.map.callouts.items():
            if not self._slots.get(cid):
                self._slots[cid] = [(c.x, c.y, "spread")]

        # Day form: correlated per-match noise. Without it, ~100 independent
        # duel rolls per match let the stronger roster win almost every time;
        # real bo1s have upsets because whole teams show up hot or cold.
        # High composure shrinks a player's day-to-day swing.
        df_rng = self.rng_tree.derive("match", self.match_id, "day_form")
        self.day_form: dict[str, float] = {}
        for pid in sorted(self.p):
            pl = self._player(pid)
            # Volatile personalities swing harder day to day; ice runs flat.
            sigma = (
                C.DAY_FORM_BASE_SIGMA
                - pl.attr("composure") / C.DAY_FORM_COMPOSURE_DIV
                + trait_value(pl, "day_sigma", 0.0)
            )
            self.day_form[pid] = float(
                np.clip(
                    df_rng.normal(0.0, max(sigma, C.DAY_FORM_MIN_SIGMA)),
                    -C.DAY_FORM_CAP,
                    C.DAY_FORM_CAP,
                )
            )
        self.tactic_form: dict[str, float] = {
            team_a: float(np.clip(
                df_rng.normal(0.0, C.TEAM_FORM_SIGMA),
                -C.TEAM_FORM_CAP, C.TEAM_FORM_CAP,
            )),
            team_b: float(np.clip(
                df_rng.normal(0.0, C.TEAM_FORM_SIGMA),
                -C.TEAM_FORM_CAP, C.TEAM_FORM_CAP,
            )),
        }
        # How well each team's roster + chemistry can EXECUTE its coach's
        # system. Zero at neutral tactics (see _execution_mod), so it never
        # touches the golden/balance gates.
        self.exec_mod: dict[str, float] = {
            team_a: self._execution_mod(team_a),
            team_b: self._execution_mod(team_b),
        }

        # In-match momentum: kills build it, deaths bleed it, it decays
        # every round. Pure bookkeeping (no rng, no events) — it only ever
        # AMPLIFIES a player's confidence deviation (see _conf_dev), so at
        # the default confidence 50 it is an exact no-op and the golden
        # gates stay byte-stable.
        self.momentum: dict[str, float] = {pid: 0.0 for pid in self.p}

        # Map gimmicks keyed by the adjacency edge they sit on.
        self._gimmicks = {
            frozenset(g.between): g for g in self.map.gimmicks
        }

        # Round-scoped scratch, reset in _play_round.
        self._pending_flashes: list[_PendingFlash] = []
        # Per-team setup credit: (top utility contributor, valid-until tick)
        # from the last execute/retake — kills converted inside that window
        # count as their assist (the sim's stand-in for damage assists).
        self._setup_owner: dict[str, tuple[str, int]] = {}
        self._smoke_until_by_site: dict[str, int] = {}
        self._spike_dropped_at: str | None = None
        self._retake_popped = False
        self._info_rotate_used = False
        self._doors_closed: set[str] = set()
        # (gimmick, mover_team, dest_room, x, y) — resolved in the tick loop.
        self._pending_sounds: list[tuple] = []
        # Attackers peeled off the main hit to lurk a flank this round.
        self._lurkers: set[str] = set()

    # -- setup helpers -----------------------------------------------------

    def _pick_agent(self, pl: Player) -> str:
        """Highest-mastery agent the player knows; fall back to a role default.
        Delegates to the shared resolver so engine and web never diverge."""
        return lineup_resolve.auto_pick_agent(pl, self.gd.agents)

    def _all_pairs_dist(self) -> dict[tuple[str, str], int]:
        dist: dict[tuple[str, str], int] = {}
        for src in sorted(self.map.callouts):
            dist[(src, src)] = 0
            q = deque([src])
            while q:
                cur = q.popleft()
                for nxt in self.map.neighbors(cur):
                    if (src, nxt) not in dist:
                        dist[(src, nxt)] = dist[(src, cur)] + 1
                        q.append(nxt)
        return dist

    def _site_callouts(self, site: str) -> list[str]:
        return sorted(
            c.id
            for c in self.map.callouts.values()
            if c.site == site and c.zone == CalloutZone.SITE
        )

    def _entry_callouts(self, site: str) -> list[str]:
        """Attacker-side / mid callouts adjacent to the site's site-zone
        callouts — where an execute stages."""
        entries: set[str] = set()
        for sc in self._site_callouts(site):
            for nb in self.map.neighbors(sc):
                zone = self.map.callouts[nb].zone
                if zone in (CalloutZone.ATTACKER_SIDE, CalloutZone.MID):
                    entries.add(nb)
        return sorted(entries) or self._site_callouts(site)

    def _lurk_strike_due(
        self, lurk_strike: int, tick: int, went: bool, spike_planted: bool
    ) -> bool:
        """Whether the armed lurker should peel off its flank into the site.

        Gated on `went`: if the hit aborted and re-defaulted (went -> False),
        the strike is HELD — the re-hit re-arms a fresh delay — so the lurker
        never commits into the site alone during the regroup and get fed
        ahead of the second wave."""
        return (
            lurk_strike >= 0
            and tick >= lurk_strike
            and went
            and not spike_planted
            and bool(self._lurkers)
        )

    def _callout_site(self, callout_id: str) -> str:
        return str(self.map.callouts[callout_id].site)

    def _player(self, pid: str) -> Player:
        return self.gd.players[pid]

    def _condition(self, pid: str, pl: Player) -> float:
        """Form/morale/stamina/confidence folded into one additive term.
        Clamped tight: unchecked, hot teams' condition compounded into
        13-0 snowballs (winners gain form/morale, which wins more).
        Confidence is neutral-safe: exactly zero at the default 50 —
        in-match momentum only amplifies an existing deviation
        (see _conf_dev)."""
        form = max(-5.0, min(5.0, (pl.form - 50.0) / 8.0))
        morale = max(-3.0, min(3.0, (pl.morale - 50.0) / 12.0))
        stamina = (pl.stamina - 100.0) / 10.0
        conf = max(
            -C.CONFIDENCE_COND_CAP,
            min(
                C.CONFIDENCE_COND_CAP,
                self._conf_dev(pid) / C.CONFIDENCE_COND_DIV,
            ),
        )
        return form + morale + stamina + conf

    def _emit(self, ev: Event) -> None:
        self.log.append(ev)

    def _policy_rng(self, round_num: int, pid: str) -> np.random.Generator:
        """Independent deterministic stream for one player's decision.

        A policy's draw budget must not perturb another player's choices or
        the referee's combat rolls.  One generator is retained per player per
        round, so a player can sample on every tick without repeatedly hashing
        and constructing a fresh NumPy generator.
        """
        rng = self._round_policy_rngs.get(pid)
        if rng is None:
            rng = self.rng_tree.derive(
                "match", self.match_id, "round", round_num, "player", pid, "policy"
            )
            self._round_policy_rngs[pid] = rng
        return rng

    def _maybe_call_timeouts(
        self,
        round_num: int,
        atk: str,
        dfn: str,
        seed_path: tuple[str, ...],
    ) -> None:
        """Give each coach one between-round, timeout-only input window."""
        for tid in (self.team_a, self.team_b):
            self._timeout_directive[tid] = None
            if self._timeout_used[tid]:
                continue
            directive = self.coach_policies[tid].call_timeout(
                CoachObservation(
                    team_id=tid,
                    round_num=round_num,
                    score_for=self.score[tid],
                    score_against=self.score[dfn if tid == atk else atk],
                    loss_streak=self.loss_streak[tid],
                    is_attacking=tid == atk,
                    profile=self.coaches[tid],
                ),
                self.rng_tree.derive(
                    "match", self.match_id, "round", round_num, "coach", tid
                ),
            )
            if directive is None:
                continue
            self._timeout_used[tid] = True
            self._timeout_directive[tid] = directive
            self._emit(
                TimeoutEvent(
                    tick=0,
                    seed_path=seed_path,
                    round_num=round_num,
                    team_id=tid,
                    coach_id=self.coaches[tid].id,
                    directive=directive.kind,
                    clarity=directive.clarity,
                )
            )

    # -- match loop ----------------------------------------------------------

    def run(self) -> MatchResult:
        self._emit(
            MatchStartEvent(
                match_id=self.match_id,
                map_id=self.map.id,
                team_a_id=self.team_a,
                team_b_id=self.team_b,
                seed=self.seed,
                agents={pid: self.p[pid].agent_id for pid in sorted(self.p)},
            )
        )
        round_num = 0
        while True:
            round_num += 1
            self._play_round(round_num)
            a, b = self.score[self.team_a], self.score[self.team_b]
            if self._match_over(a, b) or round_num >= C.MAX_ROUNDS:
                break

        a, b = self.score[self.team_a], self.score[self.team_b]
        winner = self._decide_winner(a, b)
        self._emit(
            MatchEndEvent(
                match_id=self.match_id, winner_id=winner, score_a=a, score_b=b,
            )
        )
        return MatchResult(
            match_id=self.match_id,
            map_id=self.map.id,
            team_a_id=self.team_a,
            team_b_id=self.team_b,
            score_a=a,
            score_b=b,
            winner_id=winner,
            events=self.log.events(),
        )

    def _match_over(self, a: int, b: int) -> bool:
        """First to 13; overtime is win-by-2 (capped by MAX_ROUNDS)."""
        return max(a, b) >= C.ROUNDS_TO_WIN and abs(a - b) >= 2

    def _decide_winner(self, a: int, b: int) -> str:
        if a != b:
            return self.team_a if a > b else self.team_b
        # MAX_ROUNDS tie: kills, then a coin from the match rng.
        ka, kb = self.kills[self.team_a], self.kills[self.team_b]
        if ka != kb:
            return self.team_a if ka > kb else self.team_b
        rng = self.rng_tree.derive("match", self.match_id, "tiebreak")
        return self.team_a if rng.random() < 0.5 else self.team_b

    def _sides(self, round_num: int) -> tuple[str, str]:
        """(attacking_team, defending_team). team_a attacks the first half,
        then swap; overtime alternates every round."""
        if round_num <= C.ROUNDS_PER_HALF:
            first_attack = True
        elif round_num <= 2 * C.ROUNDS_PER_HALF:
            first_attack = False
        else:
            first_attack = (round_num - 2 * C.ROUNDS_PER_HALF) % 2 == 1
        return (
            (self.team_a, self.team_b) if first_attack else (self.team_b, self.team_a)
        )

    # -- economy ---------------------------------------------------------------

    def _grant_economy(self, round_num: int) -> None:
        pistol = round_num in (1, C.ROUNDS_PER_HALF + 1)
        overtime = round_num > 2 * C.ROUNDS_PER_HALF
        for pid in sorted(self.p):
            ps = self.p[pid]
            if pistol:
                ps.credits = C.STARTING_CREDITS
                ps.weapon = "classic"
                ps.armor = 0
                ps.ult_points = 0
            elif overtime:
                ps.credits = C.OVERTIME_CREDITS
                ps.weapon = "classic"
                ps.armor = 0
            ps.credits = min(ps.credits, C.CREDIT_CAP)

    def _buy_phase(
        self, round_num: int, seed_path: tuple[str, ...], rng: np.random.Generator
    ) -> None:
        for tid in sorted(self.roster):
            avg = sum(self.p[pid].credits for pid in self.roster[tid]) / 5.0
            call = self.team_policies[tid].choose_buy(
                BuyPlanRequest(
                    team_id=tid,
                    round_num=round_num,
                    average_credits=avg,
                    tactics=self._tactics(tid),
                )
            )
            for pid in self.roster[tid]:
                ps = self.p[pid]
                policy = self.player_policies[pid]
                # The shipped heuristic gets primitives directly. Custom
                # policies retain the public observation contract below.
                if type(policy) is self._heuristic_player_type:
                    action = policy.decide_fast_state(
                        pid,
                        ps.credits,
                        ps.weapon,
                        ps.armor,
                        ps.callout or None,
                        f"buy:{call}",
                        self._fast_buy_legal,
                        self._policy_rng(round_num, pid),
                    )
                else:
                    legal = self._buy_legal_actions(ps)
                    fast_decide = getattr(policy, "decide_fast", None)
                    if callable(fast_decide):
                        action = fast_decide(
                            self._fast_observe(pid, 0, f"buy:{call}"),
                            tuple(legal),
                            self._policy_rng(round_num, pid),
                        )
                    else:
                        obs = self._observe(
                            pid, round_num, 0, False, True, f"buy:{call}"
                        )
                        action = policy.decide(
                            obs,
                            legal,
                            self._policy_rng(round_num, pid),
                        )
                weapon = self.gd.weapons.get(action.weapon_id or "classic")
                if weapon is None:
                    weapon = self.gd.weapons["classic"]
                spent = 0
                if weapon.id != ps.weapon and weapon.price <= ps.credits:
                    spent += weapon.price
                    ps.weapon = weapon.id
                if action.armor and ps.armor == 0:
                    if ps.credits - spent >= C.ARMOR_PRICE:
                        spent += C.ARMOR_PRICE
                        ps.armor = C.ARMOR_VALUE
                # Utility: signature is free; basics fill with leftovers,
                # cheapest first, keeping a small float.
                bought: list[str] = []
                agent = self.gd.agents[ps.agent_id]
                ps.charges = {}
                for ab in agent.abilities:
                    if ab.type == "signature":
                        ps.charges[ab.id] = ab.charges
                basics = sorted(
                    (ab for ab in agent.abilities if ab.type == "basic"),
                    key=lambda ab: (ab.cost, ab.id),
                )
                for ab in basics:
                    for _ in range(ab.charges):
                        if ps.credits - spent - ab.cost >= 100:
                            spent += ab.cost
                            ps.charges[ab.id] = ps.charges.get(ab.id, 0) + 1
                            bought.append(ab.id)
                ps.credits -= spent
                self._emit(
                    BuyEvent(
                        seed_path=seed_path,
                        player_id=pid,
                        weapon_id=ps.weapon,
                        armor=ps.armor,
                        abilities_bought=bought,
                        spent=spent,
                    )
                )

    def _buy_legal_actions(self, ps: _PState) -> list[Action]:
        """Enumerate concrete affordable candidates for learned policies."""
        candidates: dict[str, Action] = {}
        for weapon_id in sorted(self.gd.weapons):
            weapon = self.gd.weapons[weapon_id]
            if weapon_id != ps.weapon and weapon.price > ps.credits:
                continue
            armor_options = [0]
            can_have_armor = ps.armor > 0 or (
                weapon_id == ps.weapon and ps.credits >= C.ARMOR_PRICE
            ) or (
                weapon_id != ps.weapon
                and weapon.price + C.ARMOR_PRICE <= ps.credits
            )
            if can_have_armor:
                armor_options.append(C.ARMOR_VALUE)
            for armor in armor_options:
                action = Action(
                    type=ActionType.BUY,
                    weapon_id=weapon_id,
                    armor=armor,
                )
                candidates[action.model_dump_json()] = action
        return [candidates[key] for key in sorted(candidates)]

    # -- round -------------------------------------------------------------------

    def _play_round(self, round_num: int) -> None:
        self._round_num = round_num
        self._whiteboard.reset()
        for memory in self._enemy_memory.values():
            memory.clear()
        atk, dfn = self._sides(round_num)
        rng = self.rng_tree.derive("match", self.match_id, "round", round_num)
        seed_path = ("match", self.match_id, "round", str(round_num))
        self._round_policy_rngs = {
            pid: self.rng_tree.derive(
                "match", self.match_id, "round", round_num, "player", pid, "policy"
            )
            for pid in sorted(self.p)
        }
        self._round_target[atk] = None
        self._round_target[dfn] = None

        # 1. Halftime talks trigger at Round 13 (start of second half)
        if round_num == C.ROUNDS_PER_HALF + 1:
            for tid in (self.team_a, self.team_b):
                plan = self._plans.get(tid)
                if plan is not None and plan.halftime_talk is not None:
                    self._apply_halftime_talk(tid, plan.halftime_talk, round_num, seed_path)

        # 2. Touchline shouts check trigger
        for tid in (self.team_a, self.team_b):
            plan = self._plans.get(tid)
            if plan is not None and plan.shouts:
                fired_this_round = False
                for trigger in ("tilted_player", "loss_streak_3"):
                    if trigger in plan.shouts and trigger not in self.fired_shouts[tid]:
                        if self.loss_streak[tid] >= C.TILT_STREAK:
                            shout = plan.shouts[trigger]
                            self._apply_touchline_shout(tid, shout, round_num, trigger, seed_path)
                            fired_this_round = True
                            break
                if not fired_this_round and "round_16_close" in plan.shouts and "round_16_close" not in self.fired_shouts[tid]:
                    if round_num >= 16 and abs(self.score[self.team_a] - self.score[self.team_b]) <= 2:
                        shout = plan.shouts["round_16_close"]
                        self._apply_touchline_shout(tid, shout, round_num, "round_16_close", seed_path)

        # Coaches have no live control.  Their one chance to speak is here,
        # between rounds, before the two team policies form fresh plans.
        self._maybe_call_timeouts(round_num, atk, dfn, seed_path)

        # Defense setup: shut breakable doors (usually).
        self._doors_closed = {
            g.id
            for g in sorted(self.map.gimmicks, key=lambda g: g.id)
            if g.type == GimmickType.BREAKABLE_DOOR
            and rng.random() < g.start_closed_prob
        }

        self._emit(
            RoundStartEvent(
                seed_path=seed_path,
                round_num=round_num,
                attacking_team_id=atk,
                defending_team_id=dfn,
                closed_doors=sorted(self._doors_closed),
            )
        )

        self._grant_economy(round_num)
        self._buy_phase(round_num, seed_path, rng)

        # -- per-round reset ---------------------------------------------------
        self._pending_flashes = []
        self._setup_owner = {}
        self._smoke_until_by_site = {}
        self._spike_dropped_at = None
        self._retake_popped = False
        self._info_rotate_used = False
        self._pending_sounds = []
        self._lurkers = set()
        for pid in sorted(self.p):
            ps = self.p[pid]
            ps.alive = True
            ps.order = "hold"
            ps.move_dest = None
            ps.move_eta = -1
            ps.planting_until = -1
            ps.defusing_until = -1
            ps.flash_until = -1
            ps.flashed_by = None
            ps.bonus_until = -1
            ps.bonus = 0.0
            ps.no_engage_until = -1
            ps.peek_until = -1
            ps.mobility_until = -1
            ps.watch = None
            ps.has_spike = False

        attackers = self.roster[atk]
        defenders = self.roster[dfn]
        # -- policy-owned round plans -------------------------------------------
        # The standing book is an input; the player/team policies make the
        # actual site, pace, roles, carrier, and defensive-deployment choices.
        tac = self._tactics(atk)
        sites = [str(s) for s in self.map.sites if s != Site.MID]
        defense_plan = self.team_policies[dfn].plan_defense(
            DefenseRoundRequest(
                team_id=dfn,
                opponent_id=atk,
                players=tuple(self._player(pid) for pid in sorted(defenders)),
                tactics=self._tactics(dfn),
                sites=tuple(sites),
                timeout=self._timeout_directive[dfn],
            ),
            self.rng_tree.derive("match", self.match_id, "round", round_num, "team", dfn),
        )
        assignment = defense_plan.assignments
        scouted_site_load: dict[str, float] = {}
        if self._prep[atk] > 0.0:
            actual = {
                site: float(
                    sum(
                        1 for pid in defenders
                        if self._callout_site(assignment[pid]) == site
                    )
                )
                for site in sites
            }
            mean_load = sum(actual.values()) / max(len(actual), 1)
            clarity = min(1.0, self._prep[atk] / C.PREP_EDGE_CAP)
            scouted_site_load = {
                site: mean_load + (load - mean_load) * clarity
                for site, load in actual.items()
            }
        attack_plan = self.team_policies[atk].plan_attack(
            AttackRoundRequest(
                team_id=atk,
                opponent_id=dfn,
                players=tuple(self._player(pid) for pid in sorted(attackers)),
                captain_id=(
                    self.gd.teams[atk].captain_id
                    if self.gd.teams[atk].captain_id in attackers else None
                ),
                captain_experience=self.gd.teams[atk].igl_experience.get(
                    self.gd.teams[atk].captain_id or "", 100.0
                ) if self.gd.teams[atk].captain_id in attackers else 100.0,
                round_num=round_num,
                sites=tuple(sites),
                site_wins=dict(self.site_wins),
                tactics=tac,
                under_gunned=self._under_gunned(atk),
                prep_edge=self._prep[atk],
                scouted_site_load=scouted_site_load,
                timeout=self._timeout_directive[atk],
            ),
            self.rng_tree.derive("match", self.match_id, "round", round_num, "team", atk),
        )
        target_site = attack_plan.target_site
        go_tick = attack_plan.go_tick
        self._round_target[atk] = target_site
        self._round_target[dfn] = target_site
        defender_site = {pid: self._callout_site(assignment[pid]) for pid in defenders}
        self.p[attack_plan.spike_carrier_id].has_spike = True
        if attack_plan.lurker_id is not None:
            self._lurkers.add(attack_plan.lurker_id)
        for pid in attackers:
            self.p[pid].role = attack_plan.roles.get(pid, "support")
        for pid in defenders:
            self.p[pid].role = defense_plan.roles.get(pid, "flex")

        # Round-start placements: attackers spread across spawn, defenders
        # take tactical slots (cover/doorway angles) at their assignment.
        for pid in sorted(attackers):
            self._place(pid, self.map.attacker_spawn, "enter", seed_path)
            self._set_watch(self.p[pid], atk)
        for pid in sorted(defenders):
            self._place(pid, assignment[pid], "hold", seed_path)
            self._set_watch(self.p[pid], atk)

        # -- player-addressed staging orders -------------------------------------
        entries = self._entry_callouts(target_site)
        for pid in attackers:
            self._order(pid, attack_plan.staging_orders.get(pid, "hold"))

        # -- round tick loop --------------------------------------------------------------
        spike_planted = False
        plant_tick = -1
        planted_at: str | None = None
        planter: str | None = None
        defuse_half = False
        recon_done = False
        went = False
        committed = False
        aborted = False
        lean_done = False
        lurk_strike = -1  # tick the lurker peels off its flank into the site
        rotate_at: dict[str, int] = {}
        post_plant_spots: dict[str, str] = {}
        winner: str | None = None
        reason: str | None = None

        tick = 0
        while winner is None:
            tick += 1

            # Timer checks first: no completed plant → time win for defense.
            if not spike_planted and tick > C.ROUND_TICKS:
                winner, reason = dfn, "time"
                break
            if spike_planted and tick >= plant_tick + C.SPIKE_TICKS:
                winner, reason = atk, "spike_detonation"
                break

            alive_atk = [q for q in attackers if self.p[q].alive]
            alive_dfn = [q for q in defenders if self.p[q].alive]
            if not alive_atk and not spike_planted:
                winner, reason = dfn, "elim"
                break
            if not alive_dfn:
                winner, reason = atk, "elim"
                break

            # -- defensive lean ---------------------------------------------------
            # Five bodies staging at one site's entries is loud. The best
            # communicator off-site leans over early — one rotator, not a
            # full commit (fakes would punish that, once they exist).
            if not went and not lean_done and not spike_planted:
                entry_set = set(self._entry_callouts(target_site))
                staged = sum(1 for q in alive_atk if self.p[q].callout in entry_set)
                if staged >= 3:
                    lean_done = True
                    # Site defenders set up: trips armed, angles pre-smoked.
                    on_site_dfn = [
                        q
                        for q in alive_dfn
                        if self._callout_site(self.p[q].callout) == target_site
                    ]
                    if on_site_dfn:
                        self._execute_utility(
                            on_site_dfn, tick, seed_path,
                            flash_side="attack", target_site=target_site,
                            intent="stall", rng=rng,
                        )
                    off_site = [
                        q
                        for q in alive_dfn
                        if defender_site.get(q) != target_site and q not in rotate_at
                    ]
                    if off_site:
                        leaner = max(
                            off_site,
                            key=lambda q: (
                                self._player(q).attr("game_sense")
                                + self._player(q).attr("comms_quality"),
                                q,
                            ),
                        )
                        pl = self._player(leaner)
                        delay = max(
                            2,
                            C.ROTATE_DELAY_BASE
                            - int(
                                (pl.attr("game_sense") + pl.attr("comms_quality"))
                                / C.ROTATE_SKILL_DIV
                            ),
                        )
                        rotate_at[leaner] = tick + delay

            # -- go decision ------------------------------------------------------
            # The hit waits for bodies in position (utility popped while
            # half the team is mid-corridor is wasted) — but never past
            # the force-go point.
            staged_ready = True
            if not went and tick >= go_tick and alive_atk:
                staged = sum(
                    1
                    for q in alive_atk
                    if self.p[q].callout in entries
                    or any(
                        nb in entries
                        for nb in self.map.neighbors(self.p[q].callout)
                    )
                )
                staged_ready = (
                    staged >= min(2, len(alive_atk)) or tick >= C.FORCE_GO_TICK
                )
            if not went and tick >= go_tick and alive_atk and staged_ready:
                if not recon_done:
                    recon_done = True
                    new_site = self._recon_recall(
                        alive_atk, defenders, defender_site, target_site,
                        sites, tick, seed_path,
                    )
                    if new_site is not None:
                        target_site = new_site
                        entries = self._entry_callouts(target_site)
                        pushers = [q for q in alive_atk if q not in self._lurkers]
                        for i, q in enumerate(pushers):
                            self._order(q, f"goto:{entries[i % len(entries)]}")
                        go_tick = tick + 12
                        continue
                went = True
                # The lurker sits out the group execute — it keeps its util
                # and its flank instead of committing to the site — then
                # strikes in as a late second wave once the hit has landed.
                pushers = [q for q in alive_atk if q not in self._lurkers]
                self._execute_utility(
                    pushers or alive_atk, tick, seed_path,
                    flash_side="defense", target_site=target_site,
                    intent="execute", rng=rng,
                )
                site_cs = self._site_callouts(target_site)
                for i, q in enumerate(pushers):
                    self._order(q, f"goto:{site_cs[i % len(site_cs)]}")
                if self._lurkers:
                    lurk_strike = tick + C.LURK_STRIKE_DELAY

            # -- lurk strike -------------------------------------------------------------
            # The bait is set; now the lurker flanks the site from its off
            # angle, hitting defenders collapsed on the entry or rotating.
            if self._lurk_strike_due(lurk_strike, tick, went, spike_planted):
                site_cs = self._site_callouts(target_site)
                for q in sorted(self._lurkers):
                    if self.p[q].alive:
                        dest = min(
                            site_cs,
                            key=lambda c: (self.dist.get((self.p[q].callout, c), 99), c),
                        )
                        self._order(q, f"goto:{dest}")
                self._lurkers = set()  # committed — they're part of the hit now
                lurk_strike = -1

            # -- abort a failed hit ------------------------------------------------------
            # Down two bodies in the entry fight with no plant: real teams
            # pull out, regroup, and re-hit late instead of feeding the
            # rest of the roster into a crossfire one at a time.
            if went and not spike_planted and not aborted:
                atk_dead = 5 - len(alive_atk)
                dfn_dead = 5 - len(alive_dfn)
                # Fast books ram a floundering hit through; slow books pull
                # out and re-default. Neutral pace bails at down-2.
                abort_thresh = 2 + round(
                    (tac.pace - 50.0) / 50.0 * C.PACE_ABORT_SPAN
                )
                if atk_dead - dfn_dead >= abort_thresh and alive_atk:
                    aborted = True
                    went = False
                    go_tick = min(tick + 50, C.FORCE_GO_TICK + 30)
                    for q in alive_atk:
                        self.p[q].bonus_until = -1
                    pushers = [q for q in alive_atk if q not in self._lurkers]
                    for i, q in enumerate(pushers):
                        self._order(q, f"goto:{entries[i % len(entries)]}")

            # -- movement: continuous stepping, then arrivals ----------------------------
            self._advance_movers(tick)
            for pid in sorted(self.p):
                ps = self.p[pid]
                if ps.alive and 0 <= ps.move_eta <= tick:
                    if ps.path:
                        ps.x, ps.y = ps.path[-1]
                    ps.path = []
                    ps.callout = ps.move_dest or ps.callout
                    ps.move_dest = None
                    ps.move_eta = -1
                    self._set_watch(ps, atk)  # settle onto the new angle

            # -- dropped-spike pickup ------------------------------------------------------
            if self._spike_dropped_at is not None and not spike_planted:
                for q in alive_atk:
                    if self.p[q].callout == self._spike_dropped_at:
                        self.p[q].has_spike = True
                        self._spike_dropped_at = None
                        # A lurker that grabs the spike abandons the flank
                        # and rejoins the hit.
                        self._lurkers.discard(q)
                        # If the execute is already underway, route the fresh
                        # carrier onto site. Its standing order is a stale
                        # goto:<drop> (from the fetch) or a lurk/flank hold —
                        # and the plant logic only takes over once the
                        # carrier is already on-site, so without this the
                        # carrier parks at the pickup spot until the round
                        # times out. This fires for any carrier (not just
                        # lurkers), so it does shift neutral play — it wiped
                        # out the undeserved clock losses in the balance
                        # report — but the golden match (haven/42) never hits
                        # this path, so that fixture is unchanged.
                        if went:
                            site_cs = self._site_callouts(target_site)
                            if self.p[q].callout not in site_cs and site_cs:
                                dest = min(
                                    site_cs,
                                    key=lambda c: (
                                        self.dist.get((self.p[q].callout, c), 99),
                                        c,
                                    ),
                                )
                                self._order(q, f"goto:{dest}")
                        break

            # -- referee reacts to objective state --------------------------------------------
            self._update_orders(
                tick, alive_atk, alive_dfn, target_site,
                spike_planted, planted_at, plant_tick, went, rotate_at,
                post_plant_spots,
            )

            # -- player decisions ---------------------------------------------------------------
            # Every alive, available player receives a fresh legal-action
            # decision each tick.  Orders are team-policy recommendations,
            # not an engine-owned action queue.
            round_states: dict[str, PlayerRoundState] | None = None
            for pid in sorted(self.p):
                ps = self.p[pid]
                if not ps.alive or ps.busy:
                    continue
                policy = self.player_policies[pid]
                if type(policy) is self._heuristic_player_type:
                    directive = self._timeout_directive[ps.team_id]
                    act = policy.decide_fast_state(
                        pid,
                        ps.credits,
                        ps.weapon,
                        ps.armor,
                        ps.callout or None,
                        ps.order,
                        self._fast_legal_actions(
                            ps, atk, spike_planted, planted_at, target_site, tick
                        ),
                        self._policy_rng(round_num, pid),
                        self._tactics(ps.team_id).aggression,
                        directive.kind if directive is not None else None,
                        ps.role,
                        tick,
                        spike_planted,
                        ps.team_id == atk,
                        len(alive_atk if ps.team_id == atk else alive_dfn),
                    )
                else:
                    fast_decide = getattr(policy, "decide_fast", None)
                    if callable(fast_decide):
                        act = fast_decide(
                            self._fast_observe(pid, tick, ps.order),
                            self._fast_legal_actions(
                                ps, atk, spike_planted, planted_at, target_site, tick
                            ),
                            self._policy_rng(round_num, pid),
                        )
                    else:
                        if round_states is None:
                            round_states = {
                                q: self._round_state(self.p[q])
                                for q in sorted(self.p)
                            }
                        legal = self._legal_actions(
                            ps, atk, spike_planted, planted_at, target_site, tick
                        )
                        obs = self._observe(
                            pid, round_num, tick, spike_planted, ps.team_id == atk, ps.order,
                            round_states=round_states,
                        )
                        act = policy.decide(obs, legal, self._policy_rng(round_num, pid))
                # Holders (defenders, post-plant attackers) settle into
                # cover/angle slots; pushing players spread through rooms.
                prefer = (
                    "hold"
                    if ps.team_id != atk or spike_planted
                    else "enter"
                )
                self._apply_action(ps, act, tick, seed_path, prefer)

            # -- gimmick sounds ------------------------------------------------------
            # Everyone in earshot reacts: watch snaps toward the noise, and
            # pre-plant defenders treat sound headed at a site as a rotate
            # call (fakes through a teleporter buy real rotations).
            for gimmick, mover_team, dest_room, sx, sy in self._pending_sounds:
                for q in sorted(self.p):
                    hs = self.p[q]
                    if not hs.alive or hs.team_id == mover_team:
                        continue
                    d = ((hs.x - sx) ** 2 + (hs.y - sy) ** 2) ** 0.5
                    if d > gimmick.noise_radius:
                        continue
                    dx, dy = sx - hs.x, sy - hs.y
                    norm = (dx * dx + dy * dy) ** 0.5
                    if norm > 0 and hs.move_eta < 0:
                        hs.watch = (dx / norm, dy / norm)
                if mover_team == atk and not spike_planted:
                    sound_site = self._callout_site(dest_room)
                    if sound_site in sites:
                        self._schedule_rotations(
                            tick, defenders, defender_site, sound_site,
                            rotate_at, seed_path, rng,
                        )
            self._pending_sounds.clear()

            # -- plant channel ------------------------------------------------------------------
            for pid in sorted(self.p):
                ps = self.p[pid]
                if ps.alive and ps.planting_until == tick:
                    ps.planting_until = -1
                    ps.has_spike = False
                    spike_planted = True
                    plant_tick = tick
                    planted_at = ps.callout
                    planter = pid
                    ps.ult_points += C.ULT_POINTS_OBJECTIVE
                    self._emit(
                        SpikePlantEvent(
                            tick=tick, seed_path=seed_path,
                            player_id=pid, callout_id=ps.callout,
                            x=round(ps.x, 2), y=round(ps.y, 2),
                        )
                    )
            # -- defuse channel ---------------------------------------------------------------------
            for pid in sorted(self.p):
                ps = self.p[pid]
                if not ps.alive or ps.defusing_until < 0:
                    continue
                remaining = ps.defusing_until - tick
                if C.DEFUSE_TICKS - remaining >= C.HALF_DEFUSE_TICKS:
                    defuse_half = True
                if ps.defusing_until == tick:
                    ps.defusing_until = -1
                    ps.ult_points += C.ULT_POINTS_OBJECTIVE
                    self._emit(
                        SpikeDefuseEvent(
                            tick=tick, seed_path=seed_path,
                            player_id=pid, half_defuse=defuse_half,
                        )
                    )
                    winner, reason = dfn, "spike_defused"
            if winner is not None:
                break

            # -- defuse start / retake utility / post-plant denial ----------------------------------
            if spike_planted and planted_at is not None and alive_dfn:
                self._maybe_start_defuse(
                    alive_dfn, alive_atk, planted_at, defuse_half, tick, seed_path, rng
                )

            # -- combat --------------------------------------------------------------------------------
            fought_at_site = self._combat(
                tick, alive_atk, alive_dfn, target_site, seed_path, rng
            )
            if fought_at_site and went and not committed:
                committed = True
                # Site anchors dump their defensive kit as the hit starts.
                on_site_dfn = [
                    q
                    for q in alive_dfn
                    if self.p[q].alive
                    and self._callout_site(self.p[q].callout) == target_site
                ]
                if on_site_dfn:
                    stall_power = self._execute_utility(
                        on_site_dfn, tick, seed_path,
                        flash_side="attack", target_site=target_site,
                        intent="stall", rng=rng,
                    )
                    # Defensive util STALLS the hit: mollies and setups
                    # make attackers path around, buying rotation time.
                    stall = min(C.STALL_TICKS_MAX, int(round(2.5 * stall_power)))
                    if stall > 0:
                        for q in alive_atk:
                            self._stall_move(self.p[q], stall, tick, seed_path)
                    # Fallback: badly outnumbered site defenders break
                    # contact and rally instead of dying in the crossfire.
                    # The post-plant grouped retake then arrives with
                    # numbers — that's the asymmetry that keeps defense
                    # in the round.
                    if len(alive_atk) - len(on_site_dfn) >= C.FALLBACK_OUTNUMBER:
                        for q in on_site_dfn:
                            pl = self._player(q)
                            p_fall = (
                                C.FALLBACK_BASE_PROB
                                + (pl.attr("game_sense") - 50.0) / 150.0
                                + trait_value(pl, "fallback_bonus", 0.0)
                                # Aggressive systems hold the site and die.
                                - (self._tactics(dfn).aggression - 50.0) / 300.0
                            )
                            if rng.random() < p_fall:
                                qs = self.p[q]
                                qs.no_engage_until = tick + C.FALLBACK_GRACE_TICKS
                                qs.planting_until = -1
                                qs.defusing_until = -1
                                self._order(q, f"goto:{self.map.defender_spawn}")

            # -- rotations ---------------------------------------------------------------------------------
            # Defenders react to the *execute* (utility popping is loud),
            # not to first blood — waiting for a site kill meant rotators
            # always arrived post-plant and the defense never held.
            if went and not spike_planted:
                self._schedule_rotations(
                    tick, defenders, defender_site, target_site, rotate_at,
                    seed_path, rng,
                )

        # -- round end --------------------------------------------------------------
        assert winner is not None and reason is not None
        self.score[winner] += 1
        loser = dfn if winner == atk else atk
        self.loss_streak[winner] = 0
        self.loss_streak[loser] += 1
        if winner == atk and reason in ("elim", "spike_detonation"):
            self.site_wins[target_site] = self.site_wins.get(target_site, 0) + 1

        # Momentum: winning a round as the last one standing is the stuff
        # heaters are made of; everyone else's momentum decays toward flat.
        # Bookkeeping only — feeds _conf_dev, an exact no-op at conf 50.
        clutcher: str | None = None
        alive_winners = [q for q in self.roster[winner] if self.p[q].alive]
        if len(alive_winners) == 1:
            clutcher = alive_winners[0]
        for pid in sorted(self.p):
            self.momentum[pid] *= C.MOMENTUM_DECAY
        if clutcher is not None:
            self.momentum[clutcher] = min(
                C.MOMENTUM_CAP, self.momentum[clutcher] + C.MOMENTUM_CLUTCH
            )

        overtime = round_num > 2 * C.ROUNDS_PER_HALF
        for pid in sorted(self.p):
            ps = self.p[pid]
            if not overtime:
                if ps.team_id == winner:
                    ps.credits += C.WIN_REWARD
                else:
                    idx = min(self.loss_streak[ps.team_id], len(C.LOSS_BONUS)) - 1
                    ps.credits += C.LOSS_BONUS[max(idx, 0)]
                if spike_planted and ps.team_id == atk:
                    ps.credits += C.PLANT_BONUS
            ps.credits = min(ps.credits, C.CREDIT_CAP)
            if not ps.alive:
                ps.weapon = "classic"
                ps.armor = 0
            ps.ult_points += C.ULT_POINTS_ROUND

        # Decay active shouts
        for tid in (self.team_a, self.team_b):
            if self.active_shout[tid] is not None:
                shout, rounds_left = self.active_shout[tid]
                rounds_left -= 1
                if rounds_left <= 0:
                    self.active_shout[tid] = None
                    self._tactics_offsets[tid] = {"aggression": 0.0, "pace": 0.0, "util_discipline": 0.0, "eco_greed": 0.0, "map_control": 0.0}
                else:
                    self.active_shout[tid] = (shout, rounds_left)

        self._emit(
            RoundEndEvent(
                tick=tick, seed_path=seed_path,
                round_num=round_num, winner_id=winner, reason=reason,
            )
        )

    # -- continuous movement --------------------------------------------------

    def _slot_for(self, pid: str, room: str, prefer: str) -> tuple[float, float]:
        """Deterministic tactical spot in a room. Holders gravitate to
        cover and doorway angles; entries spread out. Hash-spread so five
        players don't stack on one crate (never Python's `hash` — it's
        salted per process and would break replay determinism)."""
        slots = self._slots.get(room)
        if not slots:
            c = self.map.callouts.get(room)
            return (c.x, c.y) if c else (50.0, 50.0)
        if prefer == "hold":
            ranked = sorted(
                slots, key=lambda s: {"cover": 0, "portal": 1, "spread": 2}[s[2]]
            )
        else:
            ranked = sorted(
                slots, key=lambda s: {"spread": 0, "portal": 1, "cover": 2}[s[2]]
            )
        h = hashlib.blake2b(f"{pid}|{room}".encode(), digest_size=4)
        idx = int.from_bytes(h.digest(), "big") % min(len(ranked), 4)
        x, y, _ = ranked[idx]
        return (x, y)

    def _set_watch(self, ps: _PState, atk: str) -> None:
        """Face the likely threat: defenders watch toward attacker spawn,
        attackers toward defender spawn. Flanks come from everywhere else."""
        enemy_spawn = (
            self.map.defender_spawn if ps.team_id == atk else self.map.attacker_spawn
        )
        c = self.map.callouts[enemy_spawn]
        dx, dy = c.x - ps.x, c.y - ps.y
        norm = (dx * dx + dy * dy) ** 0.5
        ps.watch = (dx / norm, dy / norm) if norm > 0 else None

    def _facing(self, ps: _PState, ex: float, ey: float) -> float:
        """cos(angle) between this player's watch direction and the enemy
        at (ex, ey); 0.0 when not watching anything (mid-move)."""
        if ps.watch is None:
            return 0.0
        dx, dy = ex - ps.x, ey - ps.y
        norm = (dx * dx + dy * dy) ** 0.5
        if norm == 0:
            return 0.0
        return ps.watch[0] * dx / norm + ps.watch[1] * dy / norm

    def _place(
        self, pid: str, room: str, prefer: str, seed_path: tuple[str, ...]
    ) -> None:
        ps = self.p[pid]
        ps.callout = room
        ps.x, ps.y = self._slot_for(pid, room, prefer)
        ps.path = []
        self._emit(
            MoveEvent(
                seed_path=seed_path,
                player_id=pid,
                from_callout=None,
                to_callout=room,
                waypoints=[(round(ps.x, 2), round(ps.y, 2))],
                arrive_tick=0,
            )
        )

    def _speed(self, pid: str) -> float:
        """Grid units per tick — quick players rotate meaningfully faster."""
        return C.PLAYER_SPEED * (0.9 + self._player(pid).attr("movement") / 500.0)

    def _path_pts(
        self, from_room: str, to_room: str,
        from_pt: tuple[float, float], to_pt: tuple[float, float],
    ) -> list[tuple[float, float]]:
        if self._geo is not None:
            return self._geo.path_between_points(from_room, to_room, from_pt, to_pt)
        return [from_pt, to_pt]

    @staticmethod
    def _poly_len(pts: list[tuple[float, float]]) -> float:
        return sum(
            ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            for (x1, y1), (x2, y2) in zip(pts, pts[1:])
        )

    def _begin_move(
        self, ps: _PState, dest: str, tick: int,
        seed_path: tuple[str, ...], prefer: str,
    ) -> None:
        target = self._slot_for(ps.pid, dest, prefer)
        pts = self._path_pts(ps.callout, dest, (ps.x, ps.y), target)
        ticks = max(C.MIN_MOVE_TICKS, round(self._poly_len(pts) / self._speed(ps.pid)))

        # Map gimmicks on this edge: teleporters beat walking, doors cost
        # time — and everything mechanical is LOUD.
        gimmick = self._gimmicks.get(frozenset((ps.callout, dest)))
        if gimmick is not None:
            if gimmick.type == GimmickType.TELEPORTER:
                ticks = C.TELEPORT_TICKS + 2
                pts = [pts[0], pts[-1]]  # the box takes you; no corridor
                ps.no_engage_until = tick + ticks  # can't fight in transit
                self._gimmick_noise(gimmick, ps, dest, tick, seed_path, "used")
            elif gimmick.type == GimmickType.ROTATING_DOOR:
                ticks += C.ROTATING_DOOR_DELAY
                self._gimmick_noise(gimmick, ps, dest, tick, seed_path, "used")
            elif (
                gimmick.type == GimmickType.BREAKABLE_DOOR
                and gimmick.id in self._doors_closed
            ):
                ticks += C.DOOR_BREAK_TICKS
                self._doors_closed.discard(gimmick.id)  # open for the round
                self._gimmick_noise(gimmick, ps, dest, tick, seed_path, "broken")

        if ps.mobility_until >= tick and (
            gimmick is None or gimmick.type != GimmickType.TELEPORTER
        ):
            ticks = max(C.MIN_MOVE_TICKS, round(ticks * C.MOBILITY_MOVE_MULT))
            ps.mobility_until = -1  # one dash/blast/step opens one move

        ps.move_dest = dest
        ps.move_eta = tick + ticks
        ps.path = pts[1:]
        ps.watch = None  # no pre-aim while running
        self._emit(
            MoveEvent(
                tick=tick,
                seed_path=seed_path,
                player_id=ps.pid,
                from_callout=ps.callout,
                to_callout=dest,
                waypoints=[(round(x, 2), round(y, 2)) for x, y in pts],
                arrive_tick=ps.move_eta,
            )
        )

    def _gimmick_noise(
        self, gimmick: Gimmick, ps: _PState, dest: str,
        tick: int, seed_path: tuple[str, ...], action: str,
    ) -> None:
        self._emit(
            GimmickUsedEvent(
                tick=tick,
                seed_path=seed_path,
                gimmick_id=gimmick.id,
                kind=str(gimmick.type),
                action=action,
                player_id=ps.pid,
                x=round(ps.x, 2),
                y=round(ps.y, 2),
            )
        )
        self._pending_sounds.append((gimmick, ps.team_id, dest, ps.x, ps.y))

    def _stall_move(
        self, ps: _PState, extra: int, tick: int, seed_path: tuple[str, ...]
    ) -> None:
        """Defensive utility re-paces an in-flight move; the fresh event
        supersedes the old one for any replay consumer."""
        if ps.move_eta < 0 or ps.move_dest is None:
            return
        ps.move_eta += extra
        self._emit(
            MoveEvent(
                tick=tick,
                seed_path=seed_path,
                player_id=ps.pid,
                from_callout=ps.callout,
                to_callout=ps.move_dest,
                waypoints=[(round(ps.x, 2), round(ps.y, 2))]
                + [(round(x, 2), round(y, 2)) for x, y in ps.path],
                arrive_tick=ps.move_eta,
            )
        )

    def _advance_movers(self, tick: int) -> None:
        """Step every moving player along their path so that they land on
        the final waypoint exactly at move_eta (stall-aware re-pacing)."""
        for pid in sorted(self.p):
            ps = self.p[pid]
            if not ps.alive or ps.move_eta < 0 or not ps.path:
                continue
            remaining_ticks = ps.move_eta - tick
            if remaining_ticks <= 0:
                ps.x, ps.y = ps.path[-1]
                ps.path = []
                continue
            step = self._poly_len([(ps.x, ps.y), *ps.path]) / (remaining_ticks + 1)
            while step > 0 and ps.path:
                nx, ny = ps.path[0]
                d = ((nx - ps.x) ** 2 + (ny - ps.y) ** 2) ** 0.5
                if d <= step:
                    ps.x, ps.y = nx, ny
                    ps.path.pop(0)
                    step -= d
                else:
                    ps.x += (nx - ps.x) / d * step
                    ps.y += (ny - ps.y) / d * step
                    step = 0.0

    # -- orders / actions ---------------------------------------------------------

    def _order(self, pid: str, order: str) -> None:
        ps = self.p[pid]
        if ps.order != order:
            ps.order = order

    def _update_orders(
        self,
        tick: int,
        alive_atk: list[str],
        alive_dfn: list[str],
        target_site: str,
        spike_planted: bool,
        planted_at: str | None,
        plant_tick: int,
        went: bool,
        rotate_at: dict[str, int],
        post_plant_spots: dict[str, str],
    ) -> None:
        if not spike_planted:
            # Fetch a dropped spike.
            drop = self._spike_dropped_at
            if drop is not None and alive_atk:
                nearest = min(
                    alive_atk,
                    key=lambda q: (self.dist.get((self.p[q].callout, drop), 99), q),
                )
                self._order(nearest, f"goto:{drop}")
            # Plant once the carrier is standing on the called site.
            carrier = next((q for q in alive_atk if self.p[q].has_spike), None)
            if carrier is not None and went:
                cps = self.p[carrier]
                on_site = (
                    self.map.callouts[cps.callout].zone == CalloutZone.SITE
                    and self._callout_site(cps.callout) == target_site
                )
                if on_site:
                    self._order(carrier, "plant")
        else:
            # Post-plant: attackers take stable crossfire spots and hold.
            # Assignments are sticky — constant re-shuffling would keep
            # everyone mid-move and forfeit holder advantage.
            if planted_at is not None:
                # Aggression bends where they hold: an aggressive team pushes
                # off the spike onto the surrounding angles to deny the
                # defuse wide; a passive team double-stacks the spike itself
                # to make the defuse impossible to sneak. Neutral (45-55)
                # keeps the original ordering (one on spike) exactly.
                neighbors = sorted(self.map.neighbors(planted_at))
                aggr = (
                    self._tactics(self.p[alive_atk[0]].team_id).aggression
                    if alive_atk
                    else 50.0
                )
                if aggr > 55.0 and neighbors:
                    spots = neighbors + [planted_at]
                elif aggr < 45.0:
                    spots = [planted_at, planted_at] + neighbors
                else:
                    spots = [planted_at] + neighbors
                taken = set(post_plant_spots.values())
                free = [s for s in spots if s not in taken]
                for q in alive_atk:
                    if q not in post_plant_spots:
                        post_plant_spots[q] = free.pop(0) if free else planted_at
                    self._order(q, f"goto:{post_plant_spots[q]}")

        if spike_planted and planted_at is not None:
            # Retake or save? Outnumbered defenders (or ones who can no
            # longer make it in time) save weapons and concede — that's
            # how attackers win by detonation. Retakers group up one edge
            # out and enter together instead of feeding one by one.
            near = [
                q
                for q in alive_dfn
                if self.dist.get((self.p[q].callout, planted_at), 99) <= 1
            ]
            group_ready = len(near) >= min(2, len(alive_dfn))
            # Eco greed sets the risk appetite for the retake: a greedy book
            # values the round over the rifles and pushes a retake even a
            # body down; a thrifty book concedes early to save weapons.
            # Neutral (50) keeps the original down-2 save line exactly.
            dfn_tac = self._tactics(self.p[alive_dfn[0]].team_id) if alive_dfn else None
            greed = dfn_tac.eco_greed if dfn_tac else 50.0
            retake_deficit = 1 + round((greed - 50.0) / 50.0)
            # Fast books commit the retake without grouping; patient (neutral
            # or slow) books wait for a partner at the door.
            impatient = dfn_tac is not None and dfn_tac.pace >= 60.0
            for q in alive_dfn:
                ps = self.p[q]
                if ps.defusing_until >= 0:
                    continue
                remaining = plant_tick + C.SPIKE_TICKS - tick
                d_hops = self.dist.get((ps.callout, planted_at), 9)
                needed = d_hops * C.MOVE_TICKS_PER_EDGE + C.DEFUSE_TICKS + 4
                # Save when outmanned past the appetite line, or out of time.
                if len(alive_dfn) < len(alive_atk) - retake_deficit or remaining < needed:
                    self._order(q, "hold")
                elif (
                    d_hops <= 1
                    and not group_ready
                    and remaining > needed + 10
                    and not impatient
                ):
                    self._order(q, "hold")  # wait for a partner at the door
                else:
                    self._order(q, f"goto:{planted_at}")
        else:
            # Pre-plant rotators rally toward spawn rather than trickling
            # into the site fight one at a time; the post-plant grouped
            # retake is where the numbers get spent.
            for q in alive_dfn:
                due = rotate_at.get(q)
                if due is not None and tick >= due:
                    self._order(q, f"goto:{self.map.defender_spawn}")

    def _fast_legal_actions(
        self,
        ps: _PState,
        atk: str,
        spike_planted: bool,
        planted_at: str | None,
        target_site: str,
        tick: int,
    ) -> tuple[Action, ...]:
        """Reuse immutable legal-action objects for the built-in heuristic."""
        legal = self._fast_legal_by_callout.get(ps.callout, ())
        if (
            ps.team_id == atk
            and ps.has_spike
            and not spike_planted
            and self.map.callouts[ps.callout].zone == CalloutZone.SITE
            and self._callout_site(ps.callout) == target_site
            and tick + C.PLANT_TICKS <= C.ROUND_TICKS
        ):
            return (*legal, self._fast_plant_action)
        if (
            ps.team_id != atk
            and spike_planted
            and planted_at is not None
            and ps.callout == planted_at
        ):
            return (*legal, self._fast_defuse_action)
        return legal

    def _legal_actions(
        self,
        ps: _PState,
        atk: str,
        spike_planted: bool,
        planted_at: str | None,
        target_site: str,
        tick: int,
    ) -> list[Action]:
        legal = [
            Action(type=ActionType.HOLD),
            Action(type=ActionType.WAIT),
            Action(type=ActionType.PEEK),
        ]
        for nb in sorted(self.map.neighbors(ps.callout)):
            legal.append(Action(type=ActionType.MOVE_TO, callout_id=nb))
        if (
            ps.team_id == atk
            and ps.has_spike
            and not spike_planted
            and self.map.callouts[ps.callout].zone == CalloutZone.SITE
            and self._callout_site(ps.callout) == target_site
            and tick + C.PLANT_TICKS <= C.ROUND_TICKS
        ):
            legal.append(Action(type=ActionType.PLANT_SPIKE))
        if (
            ps.team_id != atk
            and spike_planted
            and planted_at is not None
            and ps.callout == planted_at
        ):
            legal.append(Action(type=ActionType.DEFUSE_SPIKE))
        return legal

    def _apply_action(
        self, ps: _PState, act: Action, tick: int,
        seed_path: tuple[str, ...], prefer: str,
    ) -> None:
        if act.type == ActionType.MOVE_TO and act.callout_id:
            if act.callout_id in self.map.neighbors(ps.callout):
                self._begin_move(ps, act.callout_id, tick, seed_path, prefer)
        elif act.type == ActionType.PLANT_SPIKE:
            ps.planting_until = tick + C.PLANT_TICKS
        elif act.type == ActionType.DEFUSE_SPIKE:
            ps.defusing_until = tick + C.DEFUSE_TICKS
        elif act.type == ActionType.PEEK:
            ps.peek_until = tick
        # HOLD / WAIT: nothing to do.

    # -- observation -----------------------------------------------------------------

    def _fast_observe(
        self, pid: str, tick: int, order: str
    ) -> _FastObservation:
        ps = self.p[pid]
        directive = self._timeout_directive[ps.team_id]
        return _FastObservation(
            self_state=_FastPlayerState(
                player_id=ps.pid,
                credits=ps.credits,
                weapon_id=ps.weapon,
                armor=ps.armor,
                callout_id=ps.callout or None,
            ),
            tick=tick,
            igl_call=order,
            tactical_aggression=self._tactics(ps.team_id).aggression,
            timeout_directive=directive.kind if directive is not None else None,
        )

    def _observe(
        self,
        pid: str,
        round_num: int,
        tick: int,
        spike_planted: bool,
        is_attacking: bool,
        order: str,
        round_states: dict[str, PlayerRoundState] | None = None,
    ) -> PlayerObservation:
        ps = self.p[pid]
        mates = [
            round_states[q] if round_states is not None else self._round_state(self.p[q])
            for q in self.roster[ps.team_id]
            if q != pid and self.p[q].alive
        ]
        # This is an internal, already-valid snapshot on the hot per-tick
        # path.  ``model_construct`` preserves the public Pydantic contract
        # for policies without paying validation ten times every half-second.
        return PlayerObservation.model_construct(
            self_state=(round_states[pid] if round_states is not None else self._round_state(ps)),
            player_condition=self._player_condition(pid),
            round_num=round_num,
            tick=tick,
            spike_planted=spike_planted,
            is_attacking=is_attacking,
            teammates=mates,
            enemies=self._enemy_readouts(pid, tick),
            team_whiteboard=self._whiteboard.view(ps.team_id, pid, tick),
            adjacent_callouts=sorted(self.map.neighbors(ps.callout))
            if ps.callout
            else [],
            igl_call=order,
            role=ps.role,
            # Attackers know their own called site. Defenders must infer it
            # through private perception and the fallible team whiteboard.
            team_target=(self._round_target.get(ps.team_id) if is_attacking else None),
            timeout_directive=(
                self._timeout_directive[ps.team_id].kind
                if self._timeout_directive[ps.team_id] is not None
                else None
            ),
            tactical_aggression=self._tactics(ps.team_id).aggression,
        )

    def _enemy_readouts(self, pid: str, tick: int) -> list[EnemyReadout]:
        """Current sight plus the observer's own decaying private memory."""
        if tick <= 0:
            return []
        observer = self.p[pid]
        memory = self._enemy_memory[pid]
        for enemy_id in sorted(self.p):
            enemy = self.p[enemy_id]
            if enemy.team_id == observer.team_id or not enemy.alive:
                continue
            visible = bool(observer.callout and enemy.callout)
            if visible:
                visible, _ = self._sightline(observer.callout, enemy.callout)
            visible = (
                visible
                and observer.flash_until < tick
                and not (
                    self._smoke_until_by_site.get(
                        self._callout_site(observer.callout), -1
                    ) >= tick
                    and observer.callout != enemy.callout
                )
            )
            if visible:
                memory[enemy_id] = EnemyReadout(
                    player_id=enemy_id,
                    last_seen_callout=enemy.callout,
                    last_seen_tick=tick,
                    weapon_guess=enemy.weapon,
                    alive_guess=True,
                    confidence=1.0,
                    source="seen",
                )

        out: list[EnemyReadout] = []
        for enemy_id in sorted(memory):
            readout = memory[enemy_id]
            age = max(0, tick - (readout.last_seen_tick or 0))
            confidence = 0.5 ** (age / C.PRIVATE_ENEMY_MEMORY_HALF_LIFE)
            if confidence < C.PRIVATE_ENEMY_FORGET_CONFIDENCE:
                continue
            out.append(
                readout.model_copy(
                    update={
                        "confidence": confidence,
                        "source": "seen" if age == 0 else "remembered",
                    }
                )
            )
        return out

    def _player_condition(self, pid: str) -> PlayerConditionV1:
        player = self._player(pid)
        ps = self.p[pid]
        return PlayerConditionV1(
            role=player.role,
            playstyle=player.playstyle,
            personality_tags=tuple(sorted(player.personality_tags)),
            aim_precision=player.attr("aim_precision"),
            aim_reactivity=player.attr("aim_reactivity"),
            movement=player.attr("movement"),
            game_sense=player.attr("game_sense"),
            utility_usage=player.attr("utility_usage"),
            positioning=player.attr("positioning"),
            clutch_factor=player.attr("clutch_factor"),
            tilt_resistance=player.attr("tilt_resistance"),
            composure=player.attr("composure"),
            comms_quality=player.attr("comms_quality"),
            agent_mastery=player.agent_mastery(ps.agent_id, 50.0),
            map_mastery=player.map_mastery(self.map.id, 50.0),
            confidence=player.confidence,
            form=player.form,
            stamina=player.stamina,
        )

    def _round_state(self, ps: _PState) -> PlayerRoundState:
        return PlayerRoundState.model_construct(
            player_id=ps.pid,
            agent_id=ps.agent_id,
            alive=ps.alive,
            hp=100 if ps.alive else 0,
            armor=ps.armor,
            credits=ps.credits,
            weapon_id=ps.weapon,
            callout_id=ps.callout or None,
            ability_charges=dict(sorted(ps.charges.items())),
            ult_points=ps.ult_points,
        )

    # -- utility model ------------------------------------------------------------------

    @staticmethod
    def _utility_effects(ab: Ability) -> frozenset[AbilityEffect]:
        """Explicit effect metadata, with a compatible legacy-flag fallback."""
        effects = set(ab.effects)
        if ab.blocks_sight:
            effects.add(AbilityEffect.SMOKE)
        if ab.flashes:
            effects.add(AbilityEffect.FLASH)
        if ab.damages:
            effects.add(AbilityEffect.DAMAGE)
        if ab.info:
            effects.add(AbilityEffect.INFO)
        return frozenset(effects)

    def _ability_power(self, ab: Ability) -> float:
        """Credit every effect carried by a utility, rather than only its
        strongest flag (a drone that scouts and damages is not just one of
        those things)."""
        power_by_effect = {
            AbilityEffect.SMOKE: C.UTIL_POWER_SMOKE,
            AbilityEffect.FLASH: C.UTIL_POWER_FLASH,
            AbilityEffect.DAMAGE: C.UTIL_POWER_DAMAGE,
            AbilityEffect.INFO: C.UTIL_POWER_INFO,
            AbilityEffect.MOBILITY: C.UTIL_POWER_MOBILITY,
        }
        return sum(power_by_effect[effect] for effect in self._utility_effects(ab))

    def _best_ability(self, ps: _PState, intent: str) -> Ability | None:
        """Choose a charged utility for the situation, not a kit-wide
        generic power ranking. Signatures break otherwise-equal ties so a
        player uses their distinctive tool before a bought duplicate."""
        best: Ability | None = None
        best_score = 0.0
        weights = C.UTILITY_INTENT_WEIGHTS[intent]
        for ab in self.gd.agents[ps.agent_id].abilities:
            if ab.type == "ultimate" or ps.charges.get(ab.id, 0) <= 0:
                continue
            score = sum(
                weights.get(effect.value, 0.0)
                for effect in self._utility_effects(ab)
            )
            if ab.type == "signature":
                score += C.UTILITY_SIGNATURE_PRIORITY
            if score > best_score:
                best, best_score = ab, score
        return best

    def _utility_target_callout(self, site: str) -> str | None:
        """Stable representative target for event/replay consumers."""
        callouts = sorted(
            callout.id
            for callout in self.map.callouts.values()
            if str(callout.site) == site and callout.zone == CalloutZone.SITE
        )
        return callouts[0] if callouts else None

    def _execute_utility(
        self,
        pids: list[str],
        tick: int,
        seed_path: tuple[str, ...],
        flash_side: str,
        target_site: str,
        intent: str,
        rng: np.random.Generator | None = None,
    ) -> float:
        """Coarse execute/retake: everyone throws their best util; total
        power becomes a temporary duel bonus. Charged ults pop for extra.
        Sloppy throwers WHIFF lineups — charge spent, no effect.
        Disciplined books hold charges back for the retake/stall instead
        of dumping everything on one hit."""
        power = 0.0
        smoked = False
        flash_owner: str | None = None
        target_callout = self._utility_target_callout(target_site)
        if pids:
            # Neutral (50) throws everything, like the engine always did;
            # only genuinely disciplined books hold charges back.
            disc = self._tactics(self.p[pids[0]].team_id).util_discipline
            n_throw = max(1, round(len(pids) * (1.0 - max(0.0, disc - 50.0) / 125.0)))
            pids = list(pids)[:n_throw]
        best_contrib: tuple[float, str] | None = None  # (power, pid)
        for pid in pids:
            ps = self.p[pid]
            pl = self._player(pid)
            ab = self._best_ability(ps, intent)
            if ab is not None:
                ps.charges[ab.id] -= 1
                # Utility usage is the player's mechanical baseline; the
                # team book changes whether the lineup is cleanly prepared.
                # The coaching term is centered at 50 so neutral tactics
                # preserve the canonical match log exactly.
                fail_p = min(
                    C.UTIL_FAIL_MAX,
                    max(
                        0.03,
                        C.UTIL_FAIL_BASE
                        + (55.0 - pl.attr("utility_usage")) / 250.0
                        + (50.0 - disc) / 50.0 * C.UTIL_DISCIPLINE_FAIL_SPAN,
                    ),
                )
                failed = rng is not None and rng.random() < fail_p
                if not failed:
                    effects = self._utility_effects(ab)
                    contrib = self._ability_power(ab) * (
                        pl.attr("utility_usage") / 100.0
                    )
                    power += contrib
                    if best_contrib is None or contrib > best_contrib[0]:
                        best_contrib = (contrib, pid)
                    smoked = smoked or AbilityEffect.SMOKE in effects
                    if AbilityEffect.FLASH in effects and flash_owner is None:
                        flash_owner = pid  # first flasher gets the assist
                    if AbilityEffect.MOBILITY in effects:
                        ps.mobility_until = max(
                            ps.mobility_until, tick + C.MOBILITY_TICKS
                        )
                self._emit(
                    UtilityUsedEvent(
                        tick=tick, seed_path=seed_path,
                        player_id=pid, ability_id=ab.id,
                        target_callout=target_callout, failed=failed,
                    )
                )
            ult = next(
                (
                    a
                    for a in self.gd.agents[ps.agent_id].abilities
                    if a.type == "ultimate"
                ),
                None,
            )
            if ult is not None and ult.ult_points and ps.ult_points >= ult.ult_points:
                ps.ult_points = 0
                effects = self._utility_effects(ult)
                power += max(C.UTIL_POWER_ULT, self._ability_power(ult)) * (
                    pl.attr("utility_usage") / 100.0
                )
                smoked = smoked or AbilityEffect.SMOKE in effects
                if AbilityEffect.FLASH in effects and flash_owner is None:
                    flash_owner = pid
                if AbilityEffect.MOBILITY in effects:
                    ps.mobility_until = max(ps.mobility_until, tick + C.MOBILITY_TICKS)
                self._emit(
                    UtilityUsedEvent(
                        tick=tick, seed_path=seed_path,
                        player_id=pid, ability_id=ult.id,
                        target_callout=target_callout,
                    )
                )
        bonus = min(C.ENTRY_BONUS_MAX, 2.0 * power)
        for pid in pids:
            ps = self.p[pid]
            ps.bonus = bonus
            ps.bonus_until = tick + C.ENTRY_BONUS_TICKS
        if best_contrib is not None and pids:
            self._setup_owner[self.p[pids[0]].team_id] = (
                best_contrib[1],
                tick + C.ENTRY_BONUS_TICKS,
            )
        if smoked:
            self._smoke_until_by_site[target_site] = tick + C.ENTRY_BONUS_TICKS
        # A flash lands on the next duel AT ITS TARGET SITE. It expires if
        # the hit never materializes, rather than blinding a later rotate.
        if flash_owner is not None:
            self._pending_flashes.append(
                _PendingFlash(
                    target_side=flash_side,
                    target_site=target_site,
                    owner_id=flash_owner,
                    expires_at=tick + C.ENTRY_BONUS_TICKS,
                )
            )
        return power

    def _recon_recall(
        self,
        alive_atk: list[str],
        defenders: list[str],
        defender_site: dict[str, str],
        target_site: str,
        sites: list[str],
        tick: int,
        seed_path: tuple[str, ...],
    ) -> str | None:
        """If an initiator has info util and the called site is stacked,
        a smart IGL re-calls to the weakest site."""
        scout: tuple[str, Ability] | None = None
        for pid in alive_atk:
            ps = self.p[pid]
            for ab in self.gd.agents[ps.agent_id].abilities:
                if (
                    AbilityEffect.INFO in self._utility_effects(ab)
                    and ab.type != "ultimate"
                    and ps.charges.get(ab.id, 0) > 0
                ):
                    scout = (pid, ab)
                    break
            if scout:
                break
        if scout is None:
            return None
        igl = max(alive_atk, key=lambda q: (self._player(q).attr("game_sense"), q))
        if self._player(igl).attr("game_sense") < 70:
            return None
        stacked = sum(
            1
            for d in defenders
            if self.p[d].alive and defender_site.get(d) == target_site
        )
        if stacked < 3:
            return None
        pid, ab = scout
        self.p[pid].charges[ab.id] -= 1
        self._emit(
            UtilityUsedEvent(
                tick=tick, seed_path=seed_path, player_id=pid, ability_id=ab.id,
                target_callout=self._utility_target_callout(target_site),
            )
        )
        others = sorted(
            (s for s in sites if s != target_site),
            key=lambda s: (
                sum(
                    1
                    for d in defenders
                    if self.p[d].alive and defender_site.get(d) == s
                ),
                s,
            ),
        )
        return others[0] if others else None

    def _maybe_start_defuse(
        self,
        alive_dfn: list[str],
        alive_atk: list[str],
        planted_at: str,
        defuse_half: bool,
        tick: int,
        seed_path: tuple[str, ...],
        rng: np.random.Generator,
    ) -> None:
        if any(self.p[q].defusing_until >= 0 for q in alive_dfn):
            return
        on_spike = [q for q in alive_dfn if self.p[q].callout == planted_at]
        if not on_spike:
            return
        # Retake utility pops the moment the first defender reaches the
        # spike — and the attackers answer with their remaining lineups,
        # so the post-plant is a util battle, not a free defender win.
        if not self._retake_popped:
            self._retake_popped = True
            target_site = self._callout_site(planted_at)
            self._execute_utility(
                sorted(alive_dfn), tick, seed_path,
                flash_side="attack", target_site=target_site,
                intent="retake", rng=rng,
            )
            self._execute_utility(
                sorted(alive_atk), tick, seed_path,
                flash_side="defense", target_site=target_site,
                intent="retake", rng=rng,
            )
        defuser = sorted(on_spike)[0]
        # Post-plant denial: attackers' damage util can kill the defuser.
        denial_power = 0.0
        denier: tuple[str, Ability] | None = None
        for q in alive_atk:
            qs = self.p[q]
            for ab in self.gd.agents[qs.agent_id].abilities:
                if (
                    AbilityEffect.DAMAGE in self._utility_effects(ab)
                    and ab.type != "ultimate"
                    and qs.charges.get(ab.id, 0) > 0
                ):
                    denial_power += C.UTIL_POWER_DAMAGE * (
                        self._player(q).attr("utility_usage") / 100.0
                    )
                    if denier is None:
                        denier = (q, ab)
                    break
        if denier is not None and rng.random() < C.POST_PLANT_DENIAL_PROB * denial_power:
            q, ab = denier
            self.p[q].charges[ab.id] -= 1
            self._emit(
                UtilityUsedEvent(
                    tick=tick, seed_path=seed_path, player_id=q, ability_id=ab.id,
                    target_callout=planted_at,
                )
            )
            self._kill(q, defuser, ab.id, tick, seed_path, rng)
            return
        ticks = C.HALF_DEFUSE_TICKS if defuse_half else C.DEFUSE_TICKS
        self.p[defuser].defusing_until = tick + ticks

    # -- micro combat helpers ---------------------------------------------------

    def _tactics(self, team_id: str):
        plan = self._plans.get(team_id)
        base_tactics = plan.tactics if (plan is not None and plan.tactics is not None) else self.gd.teams[team_id].tactics
        offsets = self._tactics_offsets.get(team_id)
        if not offsets or not any(offsets.values()):
            return base_tactics
        return base_tactics.model_copy(update={
            k: max(0.0, min(100.0, getattr(base_tactics, k) + v))
            for k, v in offsets.items()
            if isinstance(getattr(base_tactics, k), float)
        })

    def _conf_dev(self, pid: str) -> float:
        """Confidence deviation from neutral, amplified by in-match
        momentum: eff = dev + m * SPAN * |dev|. Momentum scales the
        deviation, never creates one — exactly 0.0 whenever confidence is
        50, which is what keeps the golden gates byte-stable (ADR-007).
        In a campaign a heater lifts a shaky player back toward level and
        a cold streak dims a swaggering one."""
        dev = self._player(pid).confidence - 50.0
        if dev == 0.0:
            return 0.0
        m = max(-C.MOMENTUM_CAP, min(C.MOMENTUM_CAP, self.momentum[pid]))
        eff = dev + m * C.MOMENTUM_SPAN * abs(dev)
        return max(-45.0, min(45.0, eff))

    def _eco_tempo_shift(self, atk: str, round_num: int) -> float:
        """Execute-probability shift from eco discipline.

        A greedy book runs a save/force round down (a fast hit to catch the
        buy off-guard); a thrifty book plays slow for picks and the exit.
        Zero unless the round is a genuine eco: pistol rounds are excluded
        (everyone is on pistols by rule, not an eco choice), gun rounds are
        excluded (judged on the actual loadout, so rifles carried through a
        broke round don't count), and neutral eco_greed is a no-op — which
        is what keeps the golden/sweep gates byte-identical."""
        if round_num in (1, C.ROUNDS_PER_HALF + 1):
            return 0.0
        if not self._under_gunned(atk):
            return 0.0
        return (self._tactics(atk).eco_greed - 50.0) / 50.0 * C.ECO_EXECUTE_SPAN

    def _under_gunned(self, tid: str) -> bool:
        """Whether the team is genuinely on a save/force by FIREPOWER — most
        players lack a rifle-tier primary. Credit-based buy calls misfire
        here: a team that carried rifles through a broke round reads as
        'eco' on cash but is fully armed, so the eco tempo shift keys off the
        actual post-buy loadout instead."""
        rifle_tier = {"rifle", "sniper", "lmg"}
        armed = 0
        for pid in self.roster[tid]:
            w = self.gd.weapons.get(self.p[pid].weapon)
            if w is not None and str(w.weapon_class) in rifle_tier:
                armed += 1
        return armed < 3  # majority lack a real primary

    def _execution_mod(self, tid: str) -> float:
        """Per-team duel modifier for how well the roster + chemistry can
        EXECUTE the coach's chosen system.

        Zero when every dial is neutral — each term scales by that dial's
        deviation from 50 — so this cannot move the golden log or the
        balance band (both run neutral tactics). Off neutral, an extreme
        system rewards a roster suited to it (aim for aggression, movement
        for pace, game-sense/util for discipline, game-sense/comms for map
        control) and punishes one that isn't; fit is scored per player, so a
        team-mate who can't run the system drags the whole book down (see
        sim/tactics_fit.py). The coordination-heavy dials (map control,
        discipline) also lean on team chemistry."""
        roster = [self._player(p) for p in self.roster[tid]]
        if not roster:
            return 0.0
        tac = self._tactics(tid)

        total = 0.0
        for dial_key, attrs in tactics_fit.DIAL_FIT_ATTRS.items():
            dev = abs(getattr(tac, dial_key) - 50.0) / 50.0  # 0 at neutral
            edge = tactics_fit.fit_edge(
                tactics_fit.player_fit(pl.attr(a) for a in attrs) for pl in roster
            )
            total += dev * edge
        # Only the HIGH side of these dials is a coordination-heavy system —
        # spread/lurk map control and held-for-retake discipline lean on
        # cohesion. The low side (stacking tight, dumping utility on the hit)
        # is the SIMPLER read and shouldn't be chemistry-gated, so count only
        # the above-neutral deviation.
        complexity = (
            max(0.0, tac.map_control - 50.0)
            + max(0.0, tac.util_discipline - 50.0)
        ) / 50.0
        chem = self.gd.teams[tid].chemistry
        total += complexity * tactics_fit.chem_edge(chem)
        return float(np.clip(total, -C.EXEC_MOD_CAP, C.EXEC_MOD_CAP))

    def _apply_halftime_talk(self, team_id: str, talk: str, round_num: int, seed_path: tuple[str, ...]) -> None:
        from esports_sim.manager.personality import dev

        self._emit(
            HalftimeTalkEvent(
                seed_path=seed_path,
                round_num=round_num,
                team_id=team_id,
                talk=talk,
            )
        )
        for pid in self.roster[team_id]:
            p = self._player(pid)
            dc = 0.0
            dm = 0.0
            dstamina = 0.0
            if talk == "reassure":
                dc = 4.0 * (1.0 - 0.5 * dev(p, "resilience"))
                dm = 3.0 * (1.0 - 0.3 * dev(p, "ego"))
            elif talk == "challenge":
                dc = 5.0 * dev(p, "ambition")
                dm = 4.0 * dev(p, "ambition") - 2.0 * dev(p, "ego")
            elif talk == "demand_more":
                dc = 3.0 * (1.0 + 0.3 * dev(p, "professionalism"))
                dm = -2.0 * dev(p, "ego") - 3.0 * (1.0 - dev(p, "resilience"))
                dstamina = -8.0 * (1.0 - 0.2 * dev(p, "professionalism"))

            p.confidence = max(5.0, min(95.0, p.confidence + dc))
            p.morale = max(0.0, min(100.0, p.morale + dm))
            p.stamina = max(0.0, min(100.0, p.stamina + dstamina))

    def _apply_touchline_shout(self, team_id: str, shout: str, round_num: int, trigger: str, seed_path: tuple[str, ...]) -> None:
        from esports_sim.manager.personality import dev

        self.fired_shouts[team_id].add(trigger)
        self.active_shout[team_id] = (shout, 3)
        self._emit(
            TouchlineShoutEvent(
                seed_path=seed_path,
                round_num=round_num,
                team_id=team_id,
                shout=shout,
            )
        )
        offsets = {"aggression": 0.0, "pace": 0.0, "util_discipline": 0.0, "eco_greed": 0.0, "map_control": 0.0}
        if shout == "focus":
            offsets["aggression"] = -8.0
            offsets["util_discipline"] = 10.0
        elif shout == "play_safe":
            offsets["aggression"] = -12.0
            offsets["pace"] = -8.0
            offsets["util_discipline"] = 10.0
        elif shout == "encourage":
            offsets["pace"] = 5.0
            offsets["aggression"] = 5.0
        elif shout == "demand_effort":
            offsets["aggression"] = 12.0
            offsets["pace"] = 8.0
        self._tactics_offsets[team_id] = offsets

        for pid in self.roster[team_id]:
            p = self._player(pid)
            dc = 0.0
            dm = 0.0
            dstamina = 0.0
            if shout == "focus":
                self.momentum[pid] = 0.0
                dc = (55.0 - p.confidence) * 0.3
                dm = -2.0 * dev(p, "ego")
            elif shout == "play_safe":
                dc = 2.0 * (1.0 - 0.5 * dev(p, "resilience"))
                dm = 1.0 * (1.0 - 0.2 * dev(p, "ego"))
            elif shout == "encourage":
                dc = 3.0 * (1.0 - 0.4 * dev(p, "resilience"))
                dm = 2.0 * (1.0 + 0.3 * dev(p, "sociability"))
            elif shout == "demand_effort":
                dc = 3.0 * dev(p, "ambition")
                dm = 2.0 * dev(p, "ambition") - 3.0 * dev(p, "ego")
                dstamina = -4.0

            p.confidence = max(5.0, min(95.0, p.confidence + dc))
            p.morale = max(0.0, min(100.0, p.morale + dm))
            p.stamina = max(0.0, min(100.0, p.stamina + dstamina))

    def _flash_ability(self, ps: _PState) -> Ability | None:
        for ab in self.gd.agents[ps.agent_id].abilities:
            if (
                AbilityEffect.FLASH in self._utility_effects(ab)
                and ab.type != "ultimate"
                and ps.charges.get(ab.id, 0) > 0
            ):
                return ab
        return None

    def _apply_pending_flashes(
        self, attacker: _PState, defender: _PState, duel_site: str, tick: int
    ) -> None:
        """Apply only flashes aimed at this duel's site and retain the rest."""
        remaining_flashes: list[_PendingFlash] = []
        for pending in self._pending_flashes:
            if pending.expires_at < tick:
                continue
            if pending.target_site == duel_site:
                hit = defender if pending.target_side == "defense" else attacker
                hit.flash_until = tick + C.FLASH_TICKS
                hit.flashed_by = pending.owner_id
            else:
                remaining_flashes.append(pending)
        self._pending_flashes = remaining_flashes

    def _micro_move(
        self,
        ps: _PState,
        tick: int,
        seed_path: tuple[str, ...],
        rng: np.random.Generator,
    ) -> None:
        """Shuffle a few units within the current room — toward another
        slot (cover) when one is in range, otherwise a short strafe.
        Emits a real MoveEvent so replays show the fight footwork."""
        if not ps.alive or ps.busy:
            return
        room = ps.callout
        candidates = [
            (x, y)
            for x, y, _kind in self._slots.get(room, [])
            if C.MICRO_MOVE_MIN
            <= ((x - ps.x) ** 2 + (y - ps.y) ** 2) ** 0.5
            <= C.MICRO_MOVE_RADIUS
        ]
        if candidates:
            tx, ty = candidates[int(rng.integers(0, len(candidates)))]
        else:
            ang = float(rng.uniform(0.0, 2.0 * np.pi))
            tx, ty = ps.x + np.cos(ang) * 3.0, ps.y + np.sin(ang) * 3.0
            if self._geo is not None and room in self._geo.regions:
                r = self._geo.regions[room]
                tx = min(max(tx, r.x + 1.0), r.x + r.w - 1.0)
                ty = min(max(ty, r.y + 1.0), r.y + r.h - 1.0)
        dist = ((tx - ps.x) ** 2 + (ty - ps.y) ** 2) ** 0.5
        if dist < 0.5:
            return
        ps.move_dest = room  # same-room shuffle; callout is unchanged
        ps.move_eta = tick + max(1, round(dist / self._speed(ps.pid)))
        ps.path = [(tx, ty)]
        ps.watch = None
        self._emit(
            MoveEvent(
                tick=tick,
                seed_path=seed_path,
                player_id=ps.pid,
                from_callout=room,
                to_callout=room,
                waypoints=[
                    (round(ps.x, 2), round(ps.y, 2)),
                    (round(tx, 2), round(ty, 2)),
                ],
                arrive_tick=ps.move_eta,
            )
        )

    # -- combat -------------------------------------------------------------------------

    def _sightline(self, ca: str, cb: str) -> tuple[bool, str | None]:
        """(visible, advantaged_side) between two callouts, either direction."""
        if ca == cb:
            return True, None
        key = frozenset((ca, cb))
        if key in self._sight:
            return True, self._sight[key]
        return False, None

    def _range_mod(self, weapon, dist: float) -> float:
        """Additive duel-score term from engagement range."""
        wc = str(weapon.weapon_class)
        if wc == "sniper":
            raw = (dist - C.RANGE_SNIPER_PIVOT) * C.RANGE_SNIPER_SLOPE
            return max(-C.RANGE_SNIPER_CAP, min(C.RANGE_SNIPER_CAP, raw))
        if wc == "pistol":
            raw = (C.RANGE_PISTOL_PIVOT - dist) * C.RANGE_PISTOL_SLOPE
            return max(-C.RANGE_PISTOL_CAP, min(C.RANGE_PISTOL_CAP, raw))
        if wc == "smg":
            raw = (C.RANGE_SMG_PIVOT - dist) * C.RANGE_SMG_SLOPE
            return max(-C.RANGE_SMG_CAP, min(C.RANGE_SMG_CAP, raw))
        if wc == "shotgun":
            raw = (C.RANGE_SHOTGUN_PIVOT - dist) * C.RANGE_SHOTGUN_SLOPE
            return max(-C.RANGE_SHOTGUN_CAP, min(C.RANGE_SHOTGUN_CAP, raw))
        return 0.0  # rifles shoot flat everywhere

    def _duel_score(
        self,
        pid: str,
        holder: bool,
        advantaged: bool,
        same_callout: bool,
        tick: int,
        n_alive_own: int,
        n_alive_opp: int,
        duel_range: float = 20.0,
        height_delta: float = 0.0,
        in_cover: bool = False,
        facing: float = 0.0,
        peeking: bool = False,
        opp_pid: str | None = None,
        return_breakdown: bool = False,
    ) -> float | tuple[float, dict[str, float]]:
        ps = self.p[pid]
        pl = self._player(pid)

        # 1. Aim
        aim_precision_term = C.DUEL_AIM_PRECISION_WEIGHT * pl.attr("aim_precision")
        aim_reactivity_term = C.DUEL_AIM_REACTIVITY_WEIGHT * pl.attr("aim_reactivity")
        movement_term = C.DUEL_MOVEMENT_WEIGHT * pl.attr("movement")
        aim_total = aim_precision_term + aim_reactivity_term + movement_term

        # 2. Positioning
        pos_attr_term = (
            C.DUEL_POSITIONING_WEIGHT * pl.attr("positioning")
            if holder
            else C.DUEL_GAME_SENSE_WEIGHT * pl.attr("game_sense")
        )
        hold_adv_term = C.HOLD_ADVANTAGE if (holder and advantaged) else 0.0
        preaim_term = 0.0
        if holder and not same_callout:
            if facing >= C.PREAIM_FACING_COS:
                preaim_term = C.HOLDER_BONUS
            elif facing <= C.FLANK_FACING_COS:
                preaim_term = -C.FLANK_MALUS
        peek_term = C.PEEK_INITIATIVE if peeking else 0.0
        pos_total = pos_attr_term + hold_adv_term + preaim_term + peek_term

        # 3. Cover
        cover_total = C.COVER_BONUS if in_cover else 0.0

        # 4. High Ground
        high_ground_total = min(C.HEIGHT_CAP, height_delta * C.HEIGHT_PER_Z) if height_delta > 0 else 0.0

        # 5. Tactics Fit
        tactic_form_term = self.tactic_form[ps.team_id]
        exec_mod_term = self.exec_mod[ps.team_id]
        prep_term = self._prep[ps.team_id]
        counter_term = self._counter[ps.team_id]
        focus_term = 0.0
        plan = self._plans.get(ps.team_id)
        if plan is not None and plan.focus_target is not None and opp_pid is not None:
            if opp_pid == plan.focus_target:
                focus_term = C.FOCUS_TARGET_EDGE
            else:
                focus_term = -C.FOCUS_OFF_MALUS
        tactics_total = tactic_form_term + exec_mod_term + prep_term + counter_term + focus_term

        # 6. Weapon
        weapon = self.gd.weapons[ps.weapon]
        w_acc_term = (weapon.accuracy_base - 0.6) * C.WEAPON_ACCURACY_SCORE
        w_dmg_term = max(
            -C.WEAPON_DAMAGE_CAP,
            min(
                C.WEAPON_DAMAGE_CAP,
                (weapon.dmg_body - C.WEAPON_DAMAGE_PIVOT) * C.WEAPON_DAMAGE_SCORE,
            ),
        )
        op_affinity_term = 0.0
        if ps.weapon == "operator":
            agent = self.gd.agents.get(ps.agent_id)
            if agent is not None and agent.op_affinity:
                op_affinity_term = C.OPERATOR_AGENT_AFFINITY
        op_hold_term = C.OPERATOR_HOLD_BONUS if (ps.weapon == "operator" and holder and advantaged) else 0.0
        range_term = self._range_mod(weapon, duel_range)
        armor_term = 2.0 if ps.armor > 0 else 0.0
        weapon_total = w_acc_term + w_dmg_term + op_affinity_term + op_hold_term + range_term + armor_term

        # 7. Mastery
        agent_mastery_term = (pl.agent_mastery(ps.agent_id, 50.0) - 50.0) / 25.0
        map_mastery_term = 0.0
        for m in pl.map_pool:
            if m.map_id == self.map.id:
                map_mastery_term = (m.mastery - 50.0) / 25.0
                break
        mastery_total = agent_mastery_term + map_mastery_term

        # 8. Status
        cond_term = self._condition(pid, pl)
        flash_term = -C.FLASH_DEBUFF if ps.flash_until >= tick else 0.0
        bonus_term = ps.bonus if ps.bonus_until >= tick else 0.0
        clutch_term = 0.0
        if n_alive_own == 1 and n_alive_opp >= 2:
            clutch_term = ((pl.attr("clutch_factor") - 50.0) / 5.0) * (
                1.0 + self._conf_dev(pid) / C.CONFIDENCE_CLUTCH_DIV
            )
        tilt_term = 0.0
        if self.loss_streak[ps.team_id] >= C.TILT_STREAK:
            tilt_term = -(100.0 - pl.attr("tilt_resistance")) / 15.0
        day_form_term = self.day_form[pid]
        status_total = cond_term + flash_term + bonus_term + clutch_term + tilt_term + day_form_term

        # Original s calculation to maintain byte-identical float values
        s = (
            C.DUEL_AIM_PRECISION_WEIGHT * pl.attr("aim_precision")
            + C.DUEL_AIM_REACTIVITY_WEIGHT * pl.attr("aim_reactivity")
            + C.DUEL_MOVEMENT_WEIGHT * pl.attr("movement")
            + (
                C.DUEL_POSITIONING_WEIGHT * pl.attr("positioning")
                if holder
                else C.DUEL_GAME_SENSE_WEIGHT * pl.attr("game_sense")
            )
        )
        s += self._condition(pid, pl)
        weapon = self.gd.weapons[ps.weapon]
        s += (weapon.accuracy_base - 0.6) * C.WEAPON_ACCURACY_SCORE
        s += max(
            -C.WEAPON_DAMAGE_CAP,
            min(
                C.WEAPON_DAMAGE_CAP,
                (weapon.dmg_body - C.WEAPON_DAMAGE_PIVOT)
                * C.WEAPON_DAMAGE_SCORE,
            ),
        )
        s += (pl.agent_mastery(ps.agent_id, 50.0) - 50.0) / 25.0
        for m in pl.map_pool:
            if m.map_id == self.map.id:
                s += (m.mastery - 50.0) / 25.0
                break
        if ps.weapon == "operator":
            agent = self.gd.agents.get(ps.agent_id)
            if agent is not None and agent.op_affinity:
                s += C.OPERATOR_AGENT_AFFINITY
        if ps.weapon == "operator" and holder and advantaged:
            s += C.OPERATOR_HOLD_BONUS
        s += self._range_mod(weapon, duel_range)
        if height_delta > 0:
            s += min(C.HEIGHT_CAP, height_delta * C.HEIGHT_PER_Z)
        if in_cover:
            s += C.COVER_BONUS
        if holder and advantaged:
            s += C.HOLD_ADVANTAGE
        if holder and not same_callout:
            if facing >= C.PREAIM_FACING_COS:
                s += C.HOLDER_BONUS
            elif facing <= C.FLANK_FACING_COS:
                s -= C.FLANK_MALUS
        if peeking:
            s += C.PEEK_INITIATIVE
        if ps.flash_until >= tick:
            s -= C.FLASH_DEBUFF
        if ps.bonus_until >= tick:
            s += ps.bonus
        if n_alive_own == 1 and n_alive_opp >= 2:
            s += ((pl.attr("clutch_factor") - 50.0) / 5.0) * (
                1.0 + self._conf_dev(pid) / C.CONFIDENCE_CLUTCH_DIV
            )
        if self.loss_streak[ps.team_id] >= C.TILT_STREAK:
            s -= (100.0 - pl.attr("tilt_resistance")) / 15.0
        if ps.armor > 0:
            s += 2.0
        s += self.day_form[pid] + self.tactic_form[ps.team_id]
        s += self.exec_mod[ps.team_id]
        s += self._prep[ps.team_id]
        s += self._counter[ps.team_id]
        plan = self._plans.get(ps.team_id)
        if plan is not None and plan.focus_target is not None and opp_pid is not None:
            if opp_pid == plan.focus_target:
                s += C.FOCUS_TARGET_EDGE
            else:
                s -= C.FOCUS_OFF_MALUS

        if return_breakdown:
            breakdown = {
                "aim": aim_total,
                "positioning": pos_total,
                "cover": cover_total,
                "high_ground": high_ground_total,
                "tactics_fit": tactics_total,
                "weapon": weapon_total,
                "mastery": mastery_total,
                "status": status_total,
            }
            # Calculate the returned score directly as the sum of the breakdown values.
            # This guarantees that sum(breakdown.values()) == score_refactored exactly.
            s_sum = sum(breakdown.values())
            return s_sum, breakdown
        return s

    def _combat(
        self,
        tick: int,
        alive_atk: list[str],
        alive_dfn: list[str],
        target_site: str,
        seed_path: tuple[str, ...],
        rng: np.random.Generator,
    ) -> bool:
        """Resolve engagements this tick. Returns True if any duel happened
        at the target site (commit detection for defender rotations)."""
        engaged: set[str] = set()
        fought_at_site = False
        for a_pid in list(alive_atk):
            for d_pid in list(alive_dfn):
                pa, pd = self.p[a_pid], self.p[d_pid]
                if not (pa.alive and pd.alive):
                    continue
                if a_pid in engaged or d_pid in engaged:
                    continue
                # Disengage grace: a player falling back has broken
                # contact — neither side gets the duel.
                if pa.no_engage_until >= tick or pd.no_engage_until >= tick:
                    continue
                # A shut door between the two rooms blocks everything.
                door = self._gimmicks.get(frozenset((pa.callout, pd.callout)))
                if (
                    door is not None
                    and door.type == GimmickType.BREAKABLE_DOOR
                    and door.id in self._doors_closed
                ):
                    continue
                visible, adv = self._sightline(pa.callout, pd.callout)
                if not visible:
                    continue
                same = pa.callout == pd.callout
                p_engage = C.ENGAGE_PROB_SAME_CALLOUT if same else C.ENGAGE_PROB
                aggression = (
                    (self._tactics(pa.team_id).aggression - 50.0)
                    + (self._tactics(pd.team_id).aggression - 50.0)
                ) / 100.0
                p_engage *= 1.0 + aggression * C.AGGRO_ENGAGE_SPAN
                # Positional line of sight: a full-height box between the
                # two ACTUAL positions breaks the angle — even inside one
                # room (dancing around the mid box).
                angle_broken = self._geo is not None and self._geo.los_blocked_at(
                    pa.x, pa.y, pd.x, pd.y
                )
                if angle_broken:
                    p_engage *= C.SIGHT_BLOCK_ENGAGE_FACTOR
                # Pre-commit poking is rare; committed pushes force fights.
                # A deliberate PEEK is now selected by each player policy,
                # not rolled by the referee at combat resolution.
                a_committed = pa.move_eta >= 0 or pa.bonus_until >= tick
                d_committed = pd.move_eta >= 0
                peek_a = pa.peek_until >= tick
                peek_d = pd.peek_until >= tick
                if not same and not a_committed and not d_committed:
                    if peek_a or peek_d:
                        p_engage = 1.0
                    else:
                        # Pre-commit pokes stay rare on purpose: raising
                        # this was tried and RAISED attack rates —
                        # symmetric attrition favors whichever side has
                        # more bodies to spend, i.e. the attackers pre-hit.
                        p_engage *= 0.05
                if rng.random() >= min(1.0, max(0.0, p_engage)):
                    continue
                engaged.add(a_pid)
                engaged.add(d_pid)

                duel_site = self._callout_site(pd.callout)

                # Pending flashes pop only on a duel at the site they were
                # thrown for. A late rotate cannot inherit an old flash.
                self._apply_pending_flashes(pa, pd, duel_site, tick)

                # A peeker with a flash in the pocket swings behind it.
                # Disciplined books hold a flash back for exactly this;
                # dump-it-all books rarely have one left to pop.
                if peek_a or peek_d:
                    peeker, mark = (pa, pd) if peek_a else (pd, pa)
                    flash_ab = self._flash_ability(peeker)
                    disc = self._tactics(peeker.team_id).util_discipline
                    p_pop = C.PEEK_FLASH_PROB * (
                        1.0 + (disc - 50.0) / 50.0 * C.DISC_PEEK_FLASH_SPAN
                    )
                    if flash_ab is not None and rng.random() < p_pop:
                        peeker.charges[flash_ab.id] -= 1
                        mark.flash_until = tick + C.FLASH_TICKS
                        mark.flashed_by = peeker.pid
                        self._emit(
                            UtilityUsedEvent(
                                tick=tick, seed_path=seed_path,
                                player_id=peeker.pid, ability_id=flash_ab.id,
                                target_callout=mark.callout,
                            )
                        )

                # Fizzle: nobody commits — both shuffle to new spots
                # (jiggle-peek bait doubles the odds of that).
                fizzle = C.DUEL_FIZZLE_PROB * (
                    C.PEEK_FIZZLE_MULT if (peek_a or peek_d) else 1.0
                )
                if rng.random() < fizzle:
                    # Shots traded, nobody drops — both live and shuffle.
                    self._emit(
                        WhiffEvent(
                            tick=tick, seed_path=seed_path,
                            a_id=a_pid, b_id=d_pid,
                            x=round((pa.x + pd.x) / 2, 2),
                            y=round((pa.y + pd.y) / 2, 2),
                        )
                    )
                    self._micro_move(pa, tick, seed_path, rng)
                    self._micro_move(pd, tick, seed_path, rng)
                    continue

                # A peeker forfeits their anchored status for initiative.
                a_holder = pa.move_eta < 0 and not peek_a
                d_holder = pd.move_eta < 0 and not peek_d
                adv_a = adv == "attack" and a_holder
                adv_d = adv == "defense" and d_holder
                if same:
                    # Anchored crossfire: whoever was already set on the
                    # callout has the angle on whoever walked in.
                    adv_a = a_holder and not d_holder
                    adv_d = d_holder and not a_holder
                if self._smoke_until_by_site.get(duel_site, -1) >= tick:
                    adv_a = adv_d = False  # smoke neutralizes this site's angles
                if angle_broken:
                    adv_a = adv_d = False  # can't hold an angle through a box
                # The fight happens at the real distance between the two
                # players — not between their rooms' centers.
                duel_range = max(
                    2.0,
                    ((pa.x - pd.x) ** 2 + (pa.y - pd.y) ** 2) ** 0.5,
                )
                dz = self._z.get(pa.callout, 0.0) - self._z.get(pd.callout, 0.0)
                cover_a = (
                    a_holder
                    and self._geo is not None
                    and self._geo.cover_near(pa.x, pa.y, pd.x, pd.y)
                )
                cover_d = (
                    d_holder
                    and self._geo is not None
                    and self._geo.cover_near(pd.x, pd.y, pa.x, pa.y)
                )
                sa, breakdown_a = self._duel_score(
                    a_pid, a_holder, adv_a, same, tick,
                    len(alive_atk), len(alive_dfn), duel_range, dz, cover_a,
                    self._facing(pa, pd.x, pd.y), peek_a, d_pid,
                    return_breakdown=True,
                )
                sd, breakdown_d = self._duel_score(
                    d_pid, d_holder, adv_d, same, tick,
                    len(alive_dfn), len(alive_atk), duel_range, -dz, cover_d,
                    self._facing(pd, pa.x, pa.y), peek_d, a_pid,
                    return_breakdown=True,
                )
                p_a_wins = 1.0 / (1.0 + 10.0 ** (-(sa - sd) / C.DUEL_ELO_SCALE))
                if rng.random() < p_a_wins:
                    killer, victim = a_pid, d_pid
                else:
                    killer, victim = d_pid, a_pid

                # Emit telemetry event
                self._emit(
                    DuelTelemetryEvent(
                        tick=tick, seed_path=seed_path,
                        attacker_id=a_pid, defender_id=d_pid,
                        attacker_score=round(sa, 4), defender_score=round(sd, 4),
                        expected_win_prob=round(p_a_wins, 6), winner_id=killer,
                        attacker_breakdown=breakdown_a, defender_breakdown=breakdown_d,
                        duel_range=round(duel_range, 3), height_delta=round(dz, 3),
                        attacker_cover=cover_a, defender_cover=cover_d,
                        attacker_peeking=peek_a, defender_peeking=peek_d,
                        attacker_holder=a_holder, defender_holder=d_holder,
                    )
                )

                self._kill(killer, victim, self.p[killer].weapon, tick, seed_path, rng)
                if duel_site == target_site:
                    fought_at_site = True
                self._try_trade(killer, victim, tick, seed_path, rng)
                # Winners re-angle after the fight more often than not.
                kp = self.p[killer]
                if kp.alive and rng.random() < C.KILLER_REPOSITION_PROB:
                    self._micro_move(kp, tick, seed_path, rng)
        return fought_at_site

    def _kill(
        self,
        killer: str,
        victim: str,
        weapon_id: str,
        tick: int,
        seed_path: tuple[str, ...],
        rng: np.random.Generator,
        is_trade: bool = False,
    ) -> None:
        kp, vp = self.p[killer], self.p[victim]
        vp.alive = False
        vp.planting_until = -1
        vp.defusing_until = -1
        vp.move_eta = -1
        vp.move_dest = None
        vp.path = []  # died where they stood
        if vp.has_spike:
            vp.has_spike = False
            self._spike_dropped_at = vp.callout
        w = self.gd.weapons.get(weapon_id)
        kp.credits = min(kp.credits + (w.kill_reward if w else 200), C.CREDIT_CAP)
        kp.ult_points += C.ULT_POINTS_KILL
        self.kills[kp.team_id] += 1
        # Momentum bookkeeping (no rng, no events — see _conf_dev).
        self.momentum[killer] = min(
            C.MOMENTUM_CAP, self.momentum[killer] + C.MOMENTUM_KILL
        )
        self.momentum[victim] = max(
            -C.MOMENTUM_CAP, self.momentum[victim] - C.MOMENTUM_DEATH
        )
        headshot = rng.random() < (
            C.HEADSHOT_BASE + self._player(killer).attr("aim_precision") / 300.0
        )
        # Assists — pure bookkeeping off already-tracked state, no rng.
        # Flash assist first: the victim died while still blind from a
        # teammate's flash. Otherwise a setup assist: the kill converted
        # inside an execute/retake window, credited to the teammate whose
        # utility did the most to open it (the damage-assist stand-in).
        assist = None
        if vp.flash_until >= tick and vp.flashed_by:
            cand = self.p.get(vp.flashed_by)
            if (
                cand is not None
                and cand.pid != killer
                and cand.team_id == kp.team_id
            ):
                assist = cand.pid
        if assist is None:
            setup = self._setup_owner.get(kp.team_id)
            if setup is not None and setup[1] >= tick and setup[0] != killer:
                so = self.p.get(setup[0])
                if so is not None and so.alive:
                    assist = setup[0]
        self._emit(
            KillEvent(
                tick=tick,
                seed_path=seed_path,
                killer_id=killer,
                victim_id=victim,
                weapon_id=weapon_id,
                headshot=headshot,
                callout_id=vp.callout or None,
                is_trade=is_trade,
                assist_id=assist,
                victim_x=round(vp.x, 2),
                victim_y=round(vp.y, 2),
            )
        )

    def _try_trade(
        self,
        killer: str,
        victim: str,
        tick: int,
        seed_path: tuple[str, ...],
        rng: np.random.Generator,
    ) -> None:
        kp, vp = self.p[killer], self.p[victim]
        if not kp.alive:
            return
        candidates = []
        for q in self.roster[vp.team_id]:
            if q == victim or not self.p[q].alive:
                continue
            qc = self.p[q].callout
            visible, _ = self._sightline(qc, kp.callout)
            if qc == vp.callout or visible:
                candidates.append(q)
        if not candidates:
            return
        trader = max(
            candidates, key=lambda q: (self._player(q).attr("aim_reactivity"), q)
        )
        pl = self._player(trader)
        p_trade = (
            C.TRADE_BASE_PROB
            + (pl.attr("aim_reactivity") - 50.0) / 200.0
            + (pl.attr("game_sense") - 50.0) / 300.0
            + trait_value(pl, "trade_bonus", 0.0)  # glue players refrag
        )
        # Coaching identity: aggressive teams stack tight and hunt the
        # refrag, passive teams give some trades up for safer spacing.
        aggr = self._tactics(self.p[trader].team_id).aggression
        p_trade *= 1.0 + (aggr - 50.0) / 50.0 * C.AGGRO_TRADE_SPAN
        p_trade = min(0.95, max(0.0, p_trade))
        if rng.random() < p_trade:
            self._kill(
                trader, killer, self.p[trader].weapon, tick, seed_path, rng,
                is_trade=True,
            )

    def _schedule_rotations(
        self,
        tick: int,
        defenders: list[str],
        defender_site: dict[str, str],
        target_site: str,
        rotate_at: dict[str, int],
        seed_path: tuple[str, ...],
        rng: np.random.Generator | None = None,
    ) -> None:
        off_site = [
            q
            for q in defenders
            if self.p[q].alive
            and defender_site.get(q) != target_site
            and q not in rotate_at
        ]
        if not off_site:
            return

        # A communication policy may choose whether to publish a structured
        # call. With no supplied comms head, retain the byte-identical legacy
        # behavior while populating the whiteboard in shadow mode.
        alive = [q for q in defenders if self.p[q].alive]
        caller = max(
            alive, key=lambda q: (self._player(q).attr("comms_quality"), q)
        )
        site_callouts = sorted(
            cid for cid in self.map.callouts
            if self._callout_site(cid) == target_site
            and self.map.callouts[cid].zone == CalloutZone.SITE
        )
        callout_id = site_callouts[0] if site_callouts else None
        offered = CommunicationAction(
            speak=True,
            kind=ClaimKind.ENEMY_INTENT,
            value=ClaimValue.EXECUTING,
            callout_id=callout_id,
            expressed_confidence=0.9,
        )
        miscomm_extra = 0
        comm_policy = self.communication_policies.get(caller)
        if comm_policy is not None:
            legal_comms = [CommunicationAction(), offered]
            comm_action = comm_policy.communicate(
                self._observe(
                    caller,
                    self._round_num,
                    tick,
                    False,
                    False,
                    self.p[caller].order,
                ),
                legal_comms,
                self.rng_tree.derive(
                    "match", self.match_id, "round", self._round_num,
                    "tick", tick, "player", caller, "communication",
                ),
            )
            if comm_action not in legal_comms:
                comm_action = CommunicationAction()
            claim = self._whiteboard.publish(
                self.p[caller].team_id,
                caller,
                comm_action,
                tick,
                self._round_num,
            )
            if claim is None or claim.callout_id != callout_id:
                miscomm_extra = C.MISCOMM_DELAY
            else:
                miscomm_extra = claim.delivered_tick - tick
            if claim is not None and miscomm_extra == 0:
                self._emit(
                    CommsEvent(
                        tick=tick, seed_path=seed_path,
                        team_id=self.p[caller].team_id,
                        player_id=caller, kind="call",
                    )
                )
            elif comm_action.speak:
                self._emit(
                    CommsEvent(
                        tick=tick, seed_path=seed_path,
                        team_id=self.p[caller].team_id,
                        player_id=caller, kind="miscomm",
                    )
                )
        else:
            avg_comms = sum(
                self._player(q).attr("comms_quality") for q in alive
            ) / max(len(alive), 1)
            legacy_action: CommunicationAction | None = None
            if rng is not None and avg_comms < C.MISCOMM_COMMS_THRESHOLD:
                p_mis = min(
                    C.MISCOMM_MAX_PROB,
                    (C.MISCOMM_COMMS_THRESHOLD - avg_comms) / 80.0,
                )
                if rng.random() < p_mis:
                    miscomm_extra = C.MISCOMM_DELAY
                    garbled = min(
                        alive,
                        key=lambda q: (self._player(q).attr("comms_quality"), q),
                    )
                    caller = garbled
                    legacy_action = offered
                    self._emit(
                        CommsEvent(
                            tick=tick, seed_path=seed_path,
                            team_id=self.p[caller].team_id,
                            player_id=garbled, kind="miscomm",
                        )
                    )
            if miscomm_extra == 0 and avg_comms >= C.CALL_COMMS_THRESHOLD:
                legacy_action = offered
                self._emit(
                    CommsEvent(
                        tick=tick, seed_path=seed_path,
                        team_id=self.p[caller].team_id,
                        player_id=caller, kind="call",
                    )
                )
            if legacy_action is not None:
                self._whiteboard.publish(
                    self.p[caller].team_id,
                    caller,
                    legacy_action,
                    tick,
                    self._round_num,
                )
        # An initiator burning an info charge calls the hit early — the
        # whole rotation leaves sooner. Once per round.
        info_bonus = 0
        if not self._info_rotate_used:
            for q in sorted(q for q in defenders if self.p[q].alive):
                ps = self.p[q]
                ab = next(
                    (
                        a
                        for a in self.gd.agents[ps.agent_id].abilities
                        if AbilityEffect.INFO in self._utility_effects(a)
                        and a.type != "ultimate"
                        and ps.charges.get(a.id, 0) > 0
                    ),
                    None,
                )
                if ab is not None:
                    ps.charges[ab.id] -= 1
                    self._info_rotate_used = True
                    info_bonus = C.INFO_ROTATE_BONUS
                    self._emit(
                        UtilityUsedEvent(
                            tick=tick, seed_path=seed_path, player_id=q,
                            ability_id=ab.id,
                            target_callout=self._utility_target_callout(target_site),
                        )
                    )
                    break
        # Which defender holds the flank is a team-policy decision.  The
        # referee still applies timing, information utility, and movement.
        team_id = self.p[defenders[0]].team_id if defenders else ""
        stay = self.team_policies[team_id].choose_rotation_holdback(
            RotationPlanRequest(
                team_id=team_id,
                off_site_ids=tuple(sorted(off_site)),
                players_by_id={q: self._player(q) for q in sorted(off_site)},
            )
        ) if team_id else None
        # Defensive tempo: a fast book shaves ticks off every rotation, a
        # slow book plays it patient. Neutral pace is a no-op.
        def_pace = self._tactics(self.p[defenders[0]].team_id).pace if defenders else 50.0
        pace_rotate = round((def_pace - 50.0) / 50.0 * C.PACE_ROTATE_SPAN)
        for q in off_site:
            if q == stay:
                continue
            pl = self._player(q)
            delay = max(
                2,
                C.ROTATE_DELAY_BASE
                - int(
                    (pl.attr("game_sense") + pl.attr("comms_quality"))
                    / C.ROTATE_SKILL_DIV
                )
                - info_bonus
                - pace_rotate,
            )
            rotate_at[q] = tick + delay


# ---------------------------------------------------------------------------
# Public API


def simulate_match_result(
    gd: GameData,
    team_a: str,
    team_b: str,
    map_id: str,
    seed: int,
    log: EventLog | None = None,
    plans: dict[str, TeamMatchPlan] | None = None,
    policies: MatchPolicies | None = None,
) -> MatchResult:
    """`plans` carries per-match coaching overrides (game plans) from the
    campaign layer; None — the only thing the match gates ever pass — is
    exactly the pre-plan engine."""
    sim = _MatchSim(
        gd, team_a, team_b, map_id, seed, log=log, plans=plans, policies=policies
    )
    return sim.run()


def simulate_match(
    gd: GameData,
    team_a: str,
    team_b: str,
    map_id: str,
    seed: int,
    log: EventLog | None = None,
    policies: MatchPolicies | None = None,
) -> list[Event]:
    """Simulate one BO1 and return its event list (the canonical record)."""
    return simulate_match_result(
        gd, team_a, team_b, map_id, seed, log=log, policies=policies
    ).events
