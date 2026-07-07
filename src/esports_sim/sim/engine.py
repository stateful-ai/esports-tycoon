"""Tick-level match engine.

The engine is the *coach and referee*: it decides team-level strategy
(site calls, go timing, rotations), hands each player a per-player order,
and consults that player's `PlayerPolicy` to turn orders into concrete
actions. It also resolves everything physical — movement, duels, utility,
the spike — and emits typed events.

Determinism contract: every random draw comes from a per-round generator
derived from (match, round) labels on the RngTree, and all iteration is in
sorted order. Same seed → byte-identical event log (see
tests/test_determinism.py).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from esports_sim.events.log import EventLog
from esports_sim.policy.base import Action, ActionType
from esports_sim.policy.heuristic import HeuristicPolicy
from esports_sim.registry.loader import GameData
from esports_sim.schemas import (
    Ability,
    BuyEvent,
    Event,
    KillEvent,
    Map,
    MatchEndEvent,
    MatchStartEvent,
    MoveEvent,
    Player,
    PlayerObservation,
    PlayerRoundState,
    Playstyle,
    RoundEndEvent,
    RoundStartEvent,
    SpikeDefuseEvent,
    SpikePlantEvent,
    UtilityUsedEvent,
)
from esports_sim.rng.tree import RngTree
from esports_sim.schemas.map import CalloutZone, Site
from esports_sim.sim import constants as C


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
    order: str = "hold"
    order_dirty: bool = True  # consult policy when set
    move_dest: str | None = None
    move_eta: int = -1
    planting_until: int = -1
    defusing_until: int = -1
    flash_until: int = -1
    bonus_until: int = -1
    bonus: float = 0.0
    no_engage_until: int = -1  # disengage grace while falling back
    has_spike: bool = False
    charges: dict[str, int] = field(default_factory=dict)

    @property
    def busy(self) -> bool:
        return (
            self.move_eta >= 0
            or self.planting_until >= 0
            or self.defusing_until >= 0
        )


class _MatchSim:
    def __init__(
        self,
        gd: GameData,
        team_a: str,
        team_b: str,
        map_id: str,
        seed: int,
        log: EventLog | None = None,
    ):
        self.gd = gd
        self.map: Map = gd.maps[map_id]
        self.team_a = team_a
        self.team_b = team_b
        self.match_id = f"{team_a}_vs_{team_b}_{map_id}_{seed}"
        self.rng_tree = RngTree(root_seed=seed)
        self.seed = seed
        self.log = log if log is not None else EventLog()

        self.policy = HeuristicPolicy(gd, self.map)

        # Roster: sorted player ids per team for deterministic iteration.
        self.roster: dict[str, list[str]] = {
            team_a: sorted(gd.teams[team_a].player_ids),
            team_b: sorted(gd.teams[team_b].player_ids),
        }
        self.p: dict[str, _PState] = {}
        for tid in (team_a, team_b):
            for pid in self.roster[tid]:
                pl = gd.players[pid]
                agent = self._pick_agent(pl)
                self.p[pid] = _PState(pid=pid, team_id=tid, agent_id=agent)

        self.score = {team_a: 0, team_b: 0}
        self.loss_streak = {team_a: 0, team_b: 0}
        self.kills = {team_a: 0, team_b: 0}
        # Per-site attack success this match, for IGL call weighting.
        self.site_wins: dict[str, int] = {}

        # All-pairs BFS hop distances + sightline lookup, computed once.
        self.dist = self._all_pairs_dist()
        self._sight: dict[frozenset[str], str | None] = {
            frozenset((sl.from_callout, sl.to_callout)): sl.advantaged_side
            for sl in self.map.sightlines
        }

        # Day form: correlated per-match noise. Without it, ~100 independent
        # duel rolls per match let the stronger roster win almost every time;
        # real bo1s have upsets because whole teams show up hot or cold.
        # High composure shrinks a player's day-to-day swing.
        df_rng = self.rng_tree.derive("match", self.match_id, "day_form")
        self.day_form: dict[str, float] = {}
        for pid in sorted(self.p):
            sigma = 12.0 - self._player(pid).attr("composure") / 20.0
            self.day_form[pid] = float(
                np.clip(df_rng.normal(0.0, max(sigma, 2.5)), -18.0, 18.0)
            )
        self.tactic_form: dict[str, float] = {
            team_a: float(df_rng.normal(0.0, 6.5)),
            team_b: float(df_rng.normal(0.0, 6.5)),
        }

        # Round-scoped scratch, reset in _play_round.
        self._flashed = False
        self._flash_side = "defense"  # which side eats the pending flash
        self._smoke_until = -1
        self._spike_dropped_at: str | None = None
        self._retake_popped = False

    # -- setup helpers -----------------------------------------------------

    def _pick_agent(self, pl: Player) -> str:
        """Highest-mastery agent the player knows; fall back to a role default."""
        pool = sorted(pl.agent_pool, key=lambda m: (-m.mastery, m.agent_id))
        for m in pool:
            if m.agent_id in self.gd.agents:
                return m.agent_id
        by_role = sorted(
            a.id for a in self.gd.agents.values() if a.role == pl.role
        )
        return by_role[0] if by_role else sorted(self.gd.agents)[0]

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

    def _holder_spots(self, site: str) -> list[str]:
        """Defense-advantaged callouts overlooking the site. Only
        defender-side ground counts — a "holder spot" on an attacker-side
        callout would park a lone defender in the path of five attackers."""
        spots: set[str] = set()
        sites = set(self._site_callouts(site))
        for sl in self.map.sightlines:
            if sl.to_callout in sites and sl.advantaged_side == "defense":
                if sl.from_callout in sites:
                    continue
                zone = self.map.callouts[sl.from_callout].zone
                if zone in (CalloutZone.DEFENDER_SIDE, CalloutZone.DEFENDER_SPAWN):
                    spots.add(sl.from_callout)
        return sorted(spots)

    def _callout_site(self, callout_id: str) -> str:
        return str(self.map.callouts[callout_id].site)

    def _player(self, pid: str) -> Player:
        return self.gd.players[pid]

    def _condition(self, pl: Player) -> float:
        """Form/morale/stamina folded into one additive term. Clamped
        tight: unchecked, hot teams' condition compounded into 13-0
        snowballs (winners gain form/morale, which wins more)."""
        form = max(-5.0, min(5.0, (pl.form - 50.0) / 8.0))
        morale = max(-3.0, min(3.0, (pl.morale - 50.0) / 12.0))
        stamina = (pl.stamina - 100.0) / 10.0
        return form + morale + stamina

    def _emit(self, ev: Event) -> None:
        self.log.append(ev)

    # -- match loop ----------------------------------------------------------

    def run(self) -> MatchResult:
        self._emit(
            MatchStartEvent(
                match_id=self.match_id,
                map_id=self.map.id,
                team_a_id=self.team_a,
                team_b_id=self.team_b,
                seed=self.seed,
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

    def _team_buy_call(self, tid: str, round_num: int) -> str:
        if round_num in (1, C.ROUNDS_PER_HALF + 1):
            return "pistol"
        avg = sum(self.p[pid].credits for pid in self.roster[tid]) / 5.0
        if avg >= C.FULL_BUY_THRESHOLD:
            return "full"
        if avg >= C.FORCE_BUY_THRESHOLD:
            return "force"
        return "eco"

    def _buy_phase(
        self, round_num: int, seed_path: tuple[str, ...], rng: np.random.Generator
    ) -> None:
        for tid in sorted(self.roster):
            call = self._team_buy_call(tid, round_num)
            for pid in self.roster[tid]:
                ps = self.p[pid]
                obs = self._observe(pid, round_num, 0, False, True, f"buy:{call}")
                action = self.policy.decide(obs, [Action(type=ActionType.BUY)], rng)
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

    # -- round -------------------------------------------------------------------

    def _play_round(self, round_num: int) -> None:
        atk, dfn = self._sides(round_num)
        rng = self.rng_tree.derive("match", self.match_id, "round", round_num)
        seed_path = ("match", self.match_id, "round", str(round_num))
        self._emit(
            RoundStartEvent(
                seed_path=seed_path,
                round_num=round_num,
                attacking_team_id=atk,
                defending_team_id=dfn,
            )
        )

        self._grant_economy(round_num)
        self._buy_phase(round_num, seed_path, rng)

        # -- per-round reset ---------------------------------------------------
        self._flashed = False
        self._flash_side = "defense"
        self._smoke_until = -1
        self._spike_dropped_at = None
        self._retake_popped = False
        for pid in sorted(self.p):
            ps = self.p[pid]
            ps.alive = True
            ps.order = "hold"
            ps.order_dirty = True
            ps.move_dest = None
            ps.move_eta = -1
            ps.planting_until = -1
            ps.defusing_until = -1
            ps.flash_until = -1
            ps.bonus_until = -1
            ps.bonus = 0.0
            ps.no_engage_until = -1
            ps.has_spike = False

        attackers = self.roster[atk]
        defenders = self.roster[dfn]
        for pid in attackers:
            self.p[pid].callout = self.map.attacker_spawn
        # Spike carrier: best game_sense (steady hands, good decisions).
        carrier = max(
            attackers, key=lambda pid: (self._player(pid).attr("game_sense"), pid)
        )
        self.p[carrier].has_spike = True

        # -- strategy ------------------------------------------------------------
        sites = [str(s) for s in self.map.sites if s != Site.MID]
        weights = np.array(
            [1.0 + 0.35 * self.site_wins.get(s, 0) for s in sites], dtype=float
        )
        weights /= weights.sum()
        target_site = sites[int(rng.choice(len(sites), p=weights))]
        strat = "execute" if rng.random() < 0.55 else "default"
        if strat == "execute":
            go_tick = C.EXECUTE_GO_EARLIEST + int(rng.integers(0, 15))
        else:
            go_tick = int(rng.integers(C.DEFAULT_GO_EARLIEST, C.DEFAULT_GO_LATEST))
        go_tick = min(go_tick, C.FORCE_GO_TICK)

        # -- defender setup --------------------------------------------------------
        assignment = self._assign_defense(defenders, sites, rng)
        for pid, spot in assignment.items():
            self.p[pid].callout = spot
        defender_site = {pid: self._callout_site(assignment[pid]) for pid in defenders}

        # Round-start placements for the replay viewer (from_callout=None).
        for pid in sorted(self.p):
            self._emit(
                MoveEvent(
                    seed_path=seed_path,
                    player_id=pid,
                    from_callout=None,
                    to_callout=self.p[pid].callout,
                )
            )

        # -- attacker staging ---------------------------------------------------------
        entries = self._entry_callouts(target_site)
        for i, pid in enumerate(attackers):
            self._order(pid, f"goto:{entries[i % len(entries)]}")

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
                            on_site_dfn, tick, seed_path, flash_side="attack"
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
                            12
                            - int(
                                (pl.attr("game_sense") + pl.attr("comms_quality"))
                                / 20.0
                            ),
                        )
                        rotate_at[leaner] = tick + delay

            # -- go decision ------------------------------------------------------
            if not went and tick >= go_tick and alive_atk:
                if not recon_done:
                    recon_done = True
                    new_site = self._recon_recall(
                        alive_atk, defenders, defender_site, target_site,
                        sites, tick, seed_path,
                    )
                    if new_site is not None:
                        target_site = new_site
                        entries = self._entry_callouts(target_site)
                        for i, q in enumerate(alive_atk):
                            self._order(q, f"goto:{entries[i % len(entries)]}")
                        go_tick = tick + 12
                        continue
                went = True
                self._execute_utility(alive_atk, tick, seed_path, flash_side="defense")
                site_cs = self._site_callouts(target_site)
                for i, q in enumerate(alive_atk):
                    self._order(q, f"goto:{site_cs[i % len(site_cs)]}")

            # -- abort a failed hit ------------------------------------------------------
            # Down two bodies in the entry fight with no plant: real teams
            # pull out, regroup, and re-hit late instead of feeding the
            # rest of the roster into a crossfire one at a time.
            if went and not spike_planted and not aborted:
                atk_dead = 5 - len(alive_atk)
                dfn_dead = 5 - len(alive_dfn)
                if atk_dead - dfn_dead >= 2 and alive_atk:
                    aborted = True
                    went = False
                    go_tick = min(tick + 50, C.FORCE_GO_TICK + 30)
                    for q in alive_atk:
                        self.p[q].bonus_until = -1
                    for i, q in enumerate(alive_atk):
                        self._order(q, f"goto:{entries[i % len(entries)]}")

            # -- movement arrivals -----------------------------------------------------
            for pid in sorted(self.p):
                ps = self.p[pid]
                if ps.alive and ps.move_eta == tick:
                    prev = ps.callout
                    ps.callout = ps.move_dest or ps.callout
                    ps.move_dest = None
                    ps.move_eta = -1
                    ps.order_dirty = True
                    if ps.callout != prev:
                        self._emit(
                            MoveEvent(
                                tick=tick,
                                seed_path=seed_path,
                                player_id=pid,
                                from_callout=prev,
                                to_callout=ps.callout,
                            )
                        )

            # -- dropped-spike pickup ------------------------------------------------------
            if self._spike_dropped_at is not None and not spike_planted:
                for q in alive_atk:
                    if self.p[q].callout == self._spike_dropped_at:
                        self.p[q].has_spike = True
                        self._spike_dropped_at = None
                        break

            # -- coach re-orders --------------------------------------------------------------
            self._update_orders(
                tick, alive_atk, alive_dfn, target_site,
                spike_planted, planted_at, plant_tick, went, rotate_at,
                post_plant_spots,
            )

            # -- policy decisions ---------------------------------------------------------------
            for pid in sorted(self.p):
                ps = self.p[pid]
                if not ps.alive or ps.busy or not ps.order_dirty:
                    continue
                ps.order_dirty = False
                legal = self._legal_actions(ps, atk, spike_planted, planted_at, target_site, tick)
                obs = self._observe(
                    pid, round_num, tick, spike_planted, ps.team_id == atk, ps.order
                )
                act = self.policy.decide(obs, legal, rng)
                self._apply_action(ps, act, tick)

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
                        )
                    )
                    for q in sorted(self.p):
                        self.p[q].order_dirty = True

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
                        on_site_dfn, tick, seed_path, flash_side="attack"
                    )
                    # Defensive util STALLS the hit: mollies and setups
                    # make attackers path around, buying rotation time.
                    stall = min(C.STALL_TICKS_MAX, int(round(2.5 * stall_power)))
                    if stall > 0:
                        for q in alive_atk:
                            if self.p[q].move_eta >= 0:
                                self.p[q].move_eta += stall
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
                self._schedule_rotations(tick, defenders, defender_site, target_site, rotate_at)

        # -- round end --------------------------------------------------------------
        assert winner is not None and reason is not None
        self.score[winner] += 1
        loser = dfn if winner == atk else atk
        self.loss_streak[winner] = 0
        self.loss_streak[loser] += 1
        if winner == atk and reason in ("elim", "spike_detonation"):
            self.site_wins[target_site] = self.site_wins.get(target_site, 0) + 1

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

        self._emit(
            RoundEndEvent(
                tick=tick, seed_path=seed_path,
                round_num=round_num, winner_id=winner, reason=reason,
            )
        )

    # -- defense setup ---------------------------------------------------------

    def _assign_defense(
        self, defenders: list[str], sites: list[str], rng: np.random.Generator
    ) -> dict[str, str]:
        """Spread 5 defenders across sites: anchors on site, others on
        defense-advantaged holder spots."""
        counts = {s: 5 // len(sites) for s in sites}
        remainder = 5 - sum(counts.values())
        for idx in list(rng.permutation(len(sites)))[:remainder]:
            counts[sites[int(idx)]] += 1

        def anchor_key(pid: str) -> tuple:
            pl = self._player(pid)
            is_anchor = pl.playstyle in (Playstyle.ANCHOR, Playstyle.SUPPORT)
            return (not is_anchor, -pl.attr("positioning"), pid)

        pool = sorted(defenders, key=anchor_key)
        assignment: dict[str, str] = {}
        i = 0
        for s in sites:
            spots = self._site_callouts(s) + self._holder_spots(s)
            for k in range(counts[s]):
                if i >= len(pool):
                    break
                assignment[pool[i]] = spots[k % len(spots)]
                i += 1
        for pid in pool[i:]:
            assignment[pid] = self.map.defender_spawn
        return assignment

    # -- orders / actions ---------------------------------------------------------

    def _order(self, pid: str, order: str) -> None:
        ps = self.p[pid]
        if ps.order != order:
            ps.order = order
            ps.order_dirty = True

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
                spots = [planted_at] + sorted(self.map.neighbors(planted_at))
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
            for q in alive_dfn:
                ps = self.p[q]
                if ps.defusing_until >= 0:
                    continue
                remaining = plant_tick + C.SPIKE_TICKS - tick
                d_hops = self.dist.get((ps.callout, planted_at), 9)
                needed = d_hops * C.MOVE_TICKS_PER_EDGE + C.DEFUSE_TICKS + 4
                # Save when clearly outmanned (down 2+) or out of time.
                if len(alive_dfn) < len(alive_atk) - 1 or remaining < needed:
                    self._order(q, "hold")
                elif d_hops <= 1 and not group_ready and remaining > needed + 10:
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

    def _legal_actions(
        self,
        ps: _PState,
        atk: str,
        spike_planted: bool,
        planted_at: str | None,
        target_site: str,
        tick: int,
    ) -> list[Action]:
        legal = [Action(type=ActionType.HOLD), Action(type=ActionType.WAIT)]
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

    def _apply_action(self, ps: _PState, act: Action, tick: int) -> None:
        if act.type == ActionType.MOVE_TO and act.callout_id:
            if act.callout_id in self.map.neighbors(ps.callout):
                ps.move_dest = act.callout_id
                ps.move_eta = tick + C.MOVE_TICKS_PER_EDGE
        elif act.type == ActionType.PLANT_SPIKE:
            ps.planting_until = tick + C.PLANT_TICKS
        elif act.type == ActionType.DEFUSE_SPIKE:
            ps.defusing_until = tick + C.DEFUSE_TICKS
        # HOLD / WAIT: nothing to do.

    # -- observation -----------------------------------------------------------------

    def _observe(
        self,
        pid: str,
        round_num: int,
        tick: int,
        spike_planted: bool,
        is_attacking: bool,
        order: str,
    ) -> PlayerObservation:
        ps = self.p[pid]
        mates = [
            self._round_state(self.p[q])
            for q in self.roster[ps.team_id]
            if q != pid and self.p[q].alive
        ]
        return PlayerObservation(
            self_state=self._round_state(ps),
            round_num=round_num,
            tick=tick,
            spike_planted=spike_planted,
            is_attacking=is_attacking,
            teammates=mates,
            enemies=[],
            adjacent_callouts=sorted(self.map.neighbors(ps.callout))
            if ps.callout
            else [],
            igl_call=order,
        )

    def _round_state(self, ps: _PState) -> PlayerRoundState:
        return PlayerRoundState(
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

    def _ability_power(self, ab: Ability) -> float:
        power = 0.0
        if ab.blocks_sight:
            power = max(power, C.UTIL_POWER_SMOKE)
        if ab.flashes:
            power = max(power, C.UTIL_POWER_FLASH)
        if ab.damages:
            power = max(power, C.UTIL_POWER_DAMAGE)
        if ab.info:
            power = max(power, C.UTIL_POWER_INFO)
        return power

    def _best_ability(self, ps: _PState) -> Ability | None:
        best: Ability | None = None
        best_power = 0.0
        for ab in self.gd.agents[ps.agent_id].abilities:
            if ab.type == "ultimate" or ps.charges.get(ab.id, 0) <= 0:
                continue
            power = self._ability_power(ab)
            if power > best_power:
                best, best_power = ab, power
        return best

    def _execute_utility(
        self,
        pids: list[str],
        tick: int,
        seed_path: tuple[str, ...],
        flash_side: str,
    ) -> float:
        """Coarse execute/retake: everyone throws their best util; total
        power becomes a temporary duel bonus. Charged ults pop for extra."""
        power = 0.0
        smoked = False
        flashed = False
        for pid in pids:
            ps = self.p[pid]
            pl = self._player(pid)
            ab = self._best_ability(ps)
            if ab is not None:
                ps.charges[ab.id] -= 1
                power += self._ability_power(ab) * (pl.attr("utility_usage") / 100.0)
                smoked = smoked or ab.blocks_sight
                flashed = flashed or ab.flashes
                self._emit(
                    UtilityUsedEvent(
                        tick=tick, seed_path=seed_path,
                        player_id=pid, ability_id=ab.id,
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
                power += C.UTIL_POWER_ULT * (pl.attr("utility_usage") / 100.0)
                self._emit(
                    UtilityUsedEvent(
                        tick=tick, seed_path=seed_path,
                        player_id=pid, ability_id=ult.id,
                    )
                )
        bonus = min(C.ENTRY_BONUS_MAX, 2.0 * power)
        for pid in pids:
            ps = self.p[pid]
            ps.bonus = bonus
            ps.bonus_until = tick + C.ENTRY_BONUS_TICKS
        if smoked:
            self._smoke_until = tick + C.ENTRY_BONUS_TICKS
        # Flash lands on the first target-site duel; flash_side names the
        # side that eats it.
        if flashed:
            self._flashed = True
            self._flash_side = flash_side
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
                if ab.info and ab.type != "ultimate" and ps.charges.get(ab.id, 0) > 0:
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
            self._execute_utility(sorted(alive_dfn), tick, seed_path, flash_side="attack")
            self._execute_utility(sorted(alive_atk), tick, seed_path, flash_side="defense")
        defuser = sorted(on_spike)[0]
        # Post-plant denial: attackers' damage util can kill the defuser.
        denial_power = 0.0
        denier: tuple[str, Ability] | None = None
        for q in alive_atk:
            qs = self.p[q]
            for ab in self.gd.agents[qs.agent_id].abilities:
                if ab.damages and ab.type != "ultimate" and qs.charges.get(ab.id, 0) > 0:
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
                )
            )
            self._kill(q, defuser, ab.id, tick, seed_path, rng)
            return
        ticks = C.HALF_DEFUSE_TICKS if defuse_half else C.DEFUSE_TICKS
        self.p[defuser].defusing_until = tick + ticks

    # -- combat -------------------------------------------------------------------------

    def _sightline(self, ca: str, cb: str) -> tuple[bool, str | None]:
        """(visible, advantaged_side) between two callouts, either direction."""
        if ca == cb:
            return True, None
        key = frozenset((ca, cb))
        if key in self._sight:
            return True, self._sight[key]
        return False, None

    def _duel_score(
        self,
        pid: str,
        holder: bool,
        advantaged: bool,
        same_callout: bool,
        tick: int,
        n_alive_own: int,
        n_alive_opp: int,
    ) -> float:
        ps = self.p[pid]
        pl = self._player(pid)
        s = (
            0.40 * pl.attr("aim_precision")
            + 0.25 * pl.attr("aim_reactivity")
            + 0.15 * pl.attr("movement")
            + 0.20 * pl.attr("positioning" if holder else "game_sense")
        )
        s += self._condition(pl)
        weapon = self.gd.weapons[ps.weapon]
        s += (weapon.accuracy_base - 0.6) * 20.0
        s += (pl.agent_mastery(ps.agent_id, 50.0) - 50.0) / 25.0
        for m in pl.map_pool:
            if m.map_id == self.map.id:
                s += (m.mastery - 50.0) / 25.0
                break
        if ps.weapon == "operator":
            if holder and advantaged:
                s += C.OPERATOR_HOLD_BONUS
            if same_callout:
                s -= C.OPERATOR_CLOSE_MALUS
        if holder and advantaged:
            s += C.HOLD_ADVANTAGE
        if holder and not same_callout:
            s += C.HOLDER_BONUS  # pre-aimed vs someone mid-move
        if ps.flash_until >= tick:
            s -= C.FLASH_DEBUFF
        if ps.bonus_until >= tick:
            s += ps.bonus
        if n_alive_own == 1 and n_alive_opp >= 2:
            s += (pl.attr("clutch_factor") - 50.0) / 5.0
        if self.loss_streak[ps.team_id] >= C.TILT_STREAK:
            s -= (100.0 - pl.attr("tilt_resistance")) / 15.0
        if ps.armor > 0:
            s += 2.0
        s += self.day_form[pid] + self.tactic_form[ps.team_id]
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
                visible, adv = self._sightline(pa.callout, pd.callout)
                if not visible:
                    continue
                same = pa.callout == pd.callout
                p_engage = C.ENGAGE_PROB_SAME_CALLOUT if same else C.ENGAGE_PROB
                # Pre-commit poking is rare; committed pushes force fights.
                a_committed = pa.move_eta >= 0 or pa.bonus_until >= tick
                d_committed = pd.move_eta >= 0
                if not same and not a_committed and not d_committed:
                    # Pre-commit pokes stay rare on purpose: raising this
                    # was tried and RAISED attack rates — symmetric
                    # attrition favors whichever side has more bodies to
                    # spend, i.e. the attackers pre-hit.
                    p_engage *= 0.05
                if rng.random() >= p_engage:
                    continue
                engaged.add(a_pid)
                engaged.add(d_pid)

                duel_site = self._callout_site(pd.callout)

                # Pending flash pops on the first site duel.
                if self._flashed and duel_site == target_site:
                    hit = pd if self._flash_side == "defense" else pa
                    hit.flash_until = tick + C.FLASH_TICKS
                    self._flashed = False

                if rng.random() < C.DUEL_FIZZLE_PROB:
                    continue

                a_holder = pa.move_eta < 0
                d_holder = pd.move_eta < 0
                adv_a = adv == "attack" and a_holder
                adv_d = adv == "defense" and d_holder
                if same:
                    # Anchored crossfire: whoever was already set on the
                    # callout has the angle on whoever walked in.
                    adv_a = a_holder and not d_holder
                    adv_d = d_holder and not a_holder
                if self._smoke_until >= tick:
                    adv_a = adv_d = False  # utility neutralizes angles
                sa = self._duel_score(
                    a_pid, a_holder, adv_a, same, tick,
                    len(alive_atk), len(alive_dfn),
                )
                sd = self._duel_score(
                    d_pid, d_holder, adv_d, same, tick,
                    len(alive_dfn), len(alive_atk),
                )
                p_a_wins = 1.0 / (1.0 + 10.0 ** (-(sa - sd) / C.DUEL_ELO_SCALE))
                if rng.random() < p_a_wins:
                    killer, victim = a_pid, d_pid
                else:
                    killer, victim = d_pid, a_pid
                self._kill(killer, victim, self.p[killer].weapon, tick, seed_path, rng)
                if duel_site == target_site:
                    fought_at_site = True
                self._try_trade(killer, victim, tick, seed_path, rng)
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
        if vp.has_spike:
            vp.has_spike = False
            self._spike_dropped_at = vp.callout
        w = self.gd.weapons.get(weapon_id)
        kp.credits = min(kp.credits + (w.kill_reward if w else 200), C.CREDIT_CAP)
        kp.ult_points += C.ULT_POINTS_KILL
        self.kills[kp.team_id] += 1
        headshot = rng.random() < (
            C.HEADSHOT_BASE + self._player(killer).attr("aim_precision") / 300.0
        )
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
        )
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
        # The best-positioned off-site defender stays home to watch flank.
        off_site.sort(key=lambda q: (-self._player(q).attr("positioning"), q))
        stay = off_site[0] if len(off_site) > 1 else None
        for q in off_site:
            if q == stay:
                continue
            pl = self._player(q)
            delay = max(
                2,
                12 - int((pl.attr("game_sense") + pl.attr("comms_quality")) / 20.0),
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
) -> MatchResult:
    sim = _MatchSim(gd, team_a, team_b, map_id, seed, log=log)
    return sim.run()


def simulate_match(
    gd: GameData,
    team_a: str,
    team_b: str,
    map_id: str,
    seed: int,
    log: EventLog | None = None,
) -> list[Event]:
    """Simulate one BO1 and return its event list (the canonical record)."""
    return simulate_match_result(gd, team_a, team_b, map_id, seed, log=log).events
