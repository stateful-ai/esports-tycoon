"""Baseline player, team, and timeout-coach policies.

The engine is a referee.  It passes legal actions to every player policy,
asks one team policy per side to make a round plan, and lets a coach policy
intervene only at a timeout.  The classes here are deliberately conventional
heuristics, so a learned policy can replace one layer without replacing the
simulator.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from esports_sim.policy.base import (
    Action,
    ActionType,
    AttackRoundPlan,
    AttackRoundRequest,
    BuyPlanRequest,
    CoachObservation,
    DefenseRoundPlan,
    DefenseRoundRequest,
    MotorControl,
    MotorMovement,
    MovementPace,
    RotationPlanRequest,
    TimeoutDirective,
)
from esports_sim.registry.loader import GameData
from esports_sim.schemas import (
    CommunicationAction,
    Map,
    Player,
    PlayerObservation,
    Playstyle,
)
from esports_sim.schemas.map import CalloutZone, Site
from esports_sim.sim import constants as C
from esports_sim.sim.igl import effectiveness as igl_effectiveness


# These actions are immutable by convention and reused on the hot policy path.
# Pydantic's public Action model remains the external contract; constructing a
# new HOLD object tens of thousands of times per map is simply needless work.
_HOLD_ACTION = Action.model_construct(type=ActionType.HOLD)
_PEEK_ACTION = Action.model_construct(type=ActionType.PEEK)


def _signed_angle_delta(target: float, current: float) -> float:
    """Smallest signed rotation from current heading to target heading."""
    return (target - current + 180.0) % 360.0 - 180.0


class HeuristicPolicy:
    """One player's baseline policy.

    The policy receives a team recommendation but owns the concrete legal
    action: purchases, route steps, planting/defusing, and voluntary peeks.
    A player is queried every live tick, even when their answer is ``HOLD``.
    """

    def __init__(self, gd: GameData, game_map: Map):
        self._gd = gd
        self._map = game_map
        # next-hop table: (src, dst) -> first step of a shortest path.
        self._next_hop: dict[tuple[str, str], str] = {}
        self._build_next_hop()

    # -- pathing -----------------------------------------------------------

    def _build_next_hop(self) -> None:
        """All-pairs next-hop via BFS from every node. Maps are ~20 nodes."""
        for src in sorted(self._map.callouts):
            prev: dict[str, str] = {src: src}
            q = deque([src])
            while q:
                cur = q.popleft()
                for nxt in self._map.neighbors(cur):
                    if nxt not in prev:
                        prev[nxt] = cur
                        q.append(nxt)
            for dst, p in prev.items():
                if dst == src:
                    continue
                # Walk back from dst to the node whose prev is src.
                step = dst
                while prev[step] != src:
                    step = prev[step]
                self._next_hop[(src, dst)] = step

    def next_hop(self, src: str, dst: str) -> str | None:
        return self._next_hop.get((src, dst))

    # -- buy logic ---------------------------------------------------------

    def _choose_buy(
        self, obs: PlayerObservation, rng: np.random.Generator
    ) -> Action:
        state = obs.self_state
        return self._choose_buy_state(
            state.player_id,
            state.credits,
            state.weapon_id,
            state.armor,
            obs.igl_call,
            rng,
        )

    def _choose_buy_state(
        self,
        player_id: str,
        credits: int,
        owned: str,
        current_armor: int,
        call: str | None,
        rng: np.random.Generator,
    ) -> Action:
        """Buy selection shared by the public and allocation-free paths."""
        call = call or "buy:full"
        tier = call.split(":", 1)[1] if ":" in call else "full"
        player = self._gd.players[player_id]
        weapons = self._gd.weapons

        weapon_id = "classic"
        armor = 0
        spend_weapon = 0

        if tier == "pistol":
            # Ghost if we can afford it; leftover goes to util (engine-side).
            if credits >= weapons["ghost"].price:
                weapon_id = "ghost"
                spend_weapon = weapons["ghost"].price
        elif tier == "eco":
            pass  # full save: classic, bank everything
        elif tier == "force":
            if credits >= weapons["spectre"].price + C.ARMOR_PRICE:
                weapon_id, armor = "spectre", C.ARMOR_VALUE
                spend_weapon = weapons["spectre"].price + C.ARMOR_PRICE
            elif credits >= weapons["spectre"].price:
                weapon_id = "spectre"
                spend_weapon = weapons["spectre"].price
            elif credits >= weapons["sheriff"].price:
                weapon_id = "sheriff"
                spend_weapon = weapons["sheriff"].price
        else:  # full
            wants_op = (
                player.playstyle == Playstyle.AWPER
                and credits >= C.OPERATOR_THRESHOLD
            )
            if wants_op:
                weapon_id, armor = "operator", C.ARMOR_VALUE
                spend_weapon = weapons["operator"].price + C.ARMOR_PRICE
            elif credits >= C.FULL_BUY_THRESHOLD:
                # Rifle preference: slight lean by aim profile, tiny rng.
                lean = (
                    player.attr("aim_precision") - player.attr("movement")
                ) * C.RIFLE_PREFERENCE_ATTRIBUTE_SCALE
                pick = "vandal" if lean + rng.uniform(-10, 10) >= 0 else "phantom"
                weapon_id, armor = pick, C.ARMOR_VALUE
                spend_weapon = weapons[pick].price + C.ARMOR_PRICE
            elif credits >= weapons["spectre"].price + C.ARMOR_PRICE:
                weapon_id, armor = "spectre", C.ARMOR_VALUE
                spend_weapon = weapons["spectre"].price + C.ARMOR_PRICE

        # Keep the weapon we already own if it's better than what we'd buy.
        if owned not in ("classic",) and weapons[owned].price >= spend_weapon:
            weapon_id = owned
            armor = max(armor, current_armor and C.ARMOR_VALUE or 0)

        return Action(type=ActionType.BUY, weapon_id=weapon_id, armor=armor)

    # -- protocol ----------------------------------------------------------

    def decide(
        self,
        obs: PlayerObservation,
        legal: list[Action],
        rng: np.random.Generator,
    ) -> Action:
        return self._decide(obs, legal, rng)

    def control(
        self,
        obs: PlayerObservation,
        legal: list[MotorControl],
        rng: np.random.Generator,
    ) -> MotorControl:
        """Keep following an active route and turn toward its next waypoint."""
        return self.control_fast_state(
            obs.self_state.has_active_route,
            obs.self_state.heading_degrees,
            obs.navigation_heading_degrees,
            tuple(legal),
            rng,
        )

    def control_fast_state(
        self,
        has_active_route: bool,
        heading_degrees: float,
        navigation_heading_degrees: float | None,
        legal: tuple[MotorControl, ...],
        rng: np.random.Generator,
    ) -> MotorControl:
        """Allocation-cheap motor head used by the engine's built-in policy."""
        del rng  # deterministic baseline; learned policies may rank stochastically
        movement = (
            MotorMovement.ADVANCE if has_active_route else MotorMovement.HOLD
        )
        pace = MovementPace.RUN
        desired_turn = (
            _signed_angle_delta(navigation_heading_degrees, heading_degrees)
            if has_active_route and navigation_heading_degrees is not None
            else 0.0
        )
        candidates = [
            control
            for control in legal
            if control.movement == movement and control.pace == pace
        ]
        if not candidates:
            candidates = list(legal)
        return min(
            candidates,
            key=lambda control: (
                abs(desired_turn - control.turn_degrees),
                abs(control.turn_degrees),
                control.model_dump_json(),
            ),
        )

    def decide_fast(self, obs, legal, rng: np.random.Generator) -> Action:
        """Fast internal equivalent of :meth:`decide`.

        The referee calls this for the built-in heuristic with a tiny
        structural observation instead of allocating Pydantic snapshots every
        half-second. Third-party policies keep receiving ``PlayerObservation``
        through ``decide`` unchanged.
        """
        return self._decide(obs, legal, rng)

    def decide_fast_state(
        self,
        player_id: str,
        credits: int,
        weapon_id: str,
        armor: int,
        callout_id: str | None,
        order: str,
        legal: tuple[Action, ...],
        rng: np.random.Generator,
        tactical_aggression: float = 50.0,
        timeout_directive: str | None = None,
        role: str = "flex",
        tick: int = 0,
        spike_planted: bool = False,
        is_attacking: bool = False,
        teammates_alive: int = 5,
    ) -> Action:
        """Allocation-free hot path for the shipped heuristic only.

        ``decide`` and ``decide_fast`` remain the external-facing policy
        interfaces.  The referee knows the concrete built-in policy and can
        pass its already-held primitives here instead of materializing an
        observation object for every player on every tick.
        """
        if legal[0].type == ActionType.BUY:
            return self._choose_buy_state(
                player_id, credits, weapon_id, armor, order, rng
            )

        last_type = legal[-1].type
        if (
            (order == "plant" or order.startswith("plant:"))
            and last_type == ActionType.PLANT_SPIKE
        ):
            return legal[-1]
        if (
            (order == "defuse" or order.startswith("defuse:"))
            and last_type == ActionType.DEFUSE_SPIKE
        ):
            return legal[-1]

        if order.startswith("goto:"):
            destination = order[5:]
            if callout_id == destination or callout_id is None:
                return _HOLD_ACTION
            step = self.next_hop(callout_id, destination)
            if step is not None:
                for action in legal:
                    if action.type == ActionType.MOVE_TO and action.callout_id == step:
                        return action

        # Fast legal actions always include PEEK (BUY returned above), so no
        # per-tick action-type set is needed on this built-in path.
        p_peek = self._peek_probability(
            player_id,
            tactical_aggression=tactical_aggression,
            timeout_directive=timeout_directive,
            role=role,
            tick=tick,
            spike_planted=spike_planted,
            is_attacking=is_attacking,
            teammates_alive=teammates_alive,
        )
        if rng.random() < p_peek:
            return _PEEK_ACTION
        return _HOLD_ACTION

    def _peek_probability(
        self,
        player_id: str,
        *,
        tactical_aggression: float,
        timeout_directive: str | None,
        role: str,
        tick: int,
        spike_planted: bool,
        is_attacking: bool,
        teammates_alive: int,
    ) -> float:
        """Actor-visible risk selection for a voluntary angle challenge."""
        player = self._gd.players[player_id]
        probability = C.PEEK_PROB
        if player.playstyle in (Playstyle.ENTRY, Playstyle.AWPER):
            probability += C.PEEK_PROB_AGGRO
        probability += max(0.0, player.attr("aim_reactivity") - 60.0) / 2000.0
        probability *= 1.0 + (
            player.confidence - 50.0
        ) / C.CONFIDENCE_PEEK_DIV
        probability *= 1.0 + (
            tactical_aggression - 50.0
        ) / C.PEEK_AGGRESSION_DIV
        probability *= C.PEEK_ROLE_MULTIPLIERS.get(role, 1.0)
        if timeout_directive == "pressure":
            probability *= C.PEEK_TIMEOUT_PRESSURE_MULT
        elif timeout_directive == "stabilize":
            probability *= C.PEEK_TIMEOUT_STABILIZE_MULT
        if teammates_alive <= 2:
            probability *= C.PEEK_LOW_NUMBERS_MULT
        if spike_planted:
            probability *= (
                C.PEEK_POSTPLANT_ATTACK_MULT
                if is_attacking
                else C.PEEK_RETAKE_DEFENSE_MULT
            )
        elif is_attacking and tick >= C.PEEK_LATE_ATTACK_TICK:
            probability *= C.PEEK_LATE_ATTACK_MULT
        return max(0.0, min(C.PEEK_PROB_CAP, probability))

    def communicate(
        self,
        obs: PlayerObservation,
        legal: list[CommunicationAction],
        rng: np.random.Generator,
    ) -> CommunicationAction:
        """Choose whether to pass on a useful structured call."""
        silence = next((action for action in legal if not action.speak), None)
        claims = [action for action in legal if action.speak]
        if not claims:
            return silence or CommunicationAction()
        player = self._gd.players[obs.self_state.player_id]
        speak_prob = float(
            np.clip(
                C.COMMS_SPEAK_BASE
                + player.attr("comms_quality") / C.COMMS_SPEAK_QUALITY_DIV,
                C.COMMS_SPEAK_MIN,
                C.COMMS_SPEAK_MAX,
            )
        )
        if rng.random() >= speak_prob:
            return silence or CommunicationAction()
        return claims[0]

    def _decide(self, obs, legal, rng: np.random.Generator) -> Action:
        legal_types = {a.type for a in legal}

        if ActionType.BUY in legal_types:
            return self._choose_buy(obs, rng)

        call = obs.igl_call or "hold"
        verb, _, arg = call.partition(":")

        if verb == "plant" and ActionType.PLANT_SPIKE in legal_types:
            return Action(type=ActionType.PLANT_SPIKE)
        if verb == "defuse" and ActionType.DEFUSE_SPIKE in legal_types:
            return Action(type=ActionType.DEFUSE_SPIKE)

        if verb == "goto" and arg:
            here = obs.self_state.callout_id
            if here == arg or here is None:
                return Action(type=ActionType.HOLD)
            step = self.next_hop(here, arg)
            if step is not None:
                for action in legal:
                    if action.type == ActionType.MOVE_TO and action.callout_id == step:
                        return action

        # A peek is no longer a hidden engine roll.  The player owns the
        # decision, based on their own style, reaction, confidence, the
        # team's standing aggression, and (if present) a timeout instruction.
        if ActionType.PEEK in legal_types:
            p_peek = self._peek_probability(
                obs.self_state.player_id,
                tactical_aggression=obs.tactical_aggression,
                timeout_directive=obs.timeout_directive,
                role=obs.role,
                tick=obs.tick,
                spike_planted=obs.spike_planted,
                is_attacking=obs.is_attacking,
                teammates_alive=len(obs.teammates) + 1,
            )
            if rng.random() < p_peek:
                return _PEEK_ACTION

        return _HOLD_ACTION


class HeuristicTeamPolicy:
    """Shared decision-making for the five player policies on one side.

    This is not a live coach.  It is the side's on-server tactical policy:
    it reads the five players' attributes, the pre-match team identity, and
    any *already-issued* timeout directive to make a round plan.
    """

    def __init__(self, gd: GameData, game_map: Map):
        self._gd = gd
        self._map = game_map

    def _site_callouts(self, site: str) -> list[str]:
        return sorted(
            c.id
            for c in self._map.callouts.values()
            if c.site == site and c.zone == CalloutZone.SITE
        )

    def _entry_callouts(self, site: str) -> list[str]:
        entries: set[str] = set()
        for callout in self._site_callouts(site):
            for neighbor in self._map.neighbors(callout):
                if self._map.callouts[neighbor].zone in (
                    CalloutZone.ATTACKER_SIDE,
                    CalloutZone.MID,
                ):
                    entries.add(neighbor)
        return sorted(entries) or self._site_callouts(site)

    def _holder_spots(self, site: str) -> list[str]:
        sites = set(self._site_callouts(site))
        spots: set[str] = set()
        for sightline in self._map.sightlines:
            if (
                sightline.to_callout in sites
                and sightline.advantaged_side == "defense"
                and sightline.from_callout not in sites
                and self._map.callouts[sightline.from_callout].zone
                in (CalloutZone.DEFENDER_SIDE, CalloutZone.DEFENDER_SPAWN)
            ):
                spots.add(sightline.from_callout)
        return sorted(spots)

    @staticmethod
    def _captain(players: tuple[Player, ...], captain_id: str | None) -> Player:
        for player in players:
            if player.id == captain_id:
                return player
        return max(
            players,
            key=lambda p: (p.attr("game_sense") + p.attr("comms_quality"), p.id),
        )

    def choose_buy(self, request: BuyPlanRequest) -> str:
        if request.round_num in (1, C.ROUNDS_PER_HALF + 1):
            return "pistol"
        if request.average_credits >= C.FULL_BUY_THRESHOLD:
            return "full"
        greed = request.tactics.eco_greed
        force_mult = C.ECO_FORCE_BASE_MULT - (
            (greed - 50.0) / 50.0 * C.ECO_FORCE_MULT_SPAN
        )
        if request.average_credits >= C.FORCE_BUY_THRESHOLD * force_mult:
            return "force"
        return "eco"

    def plan_attack(
        self, request: AttackRoundRequest, rng: np.random.Generator
    ) -> AttackRoundPlan:
        players = tuple(sorted(request.players, key=lambda p: p.id))
        captain = self._captain(players, request.captain_id)
        tactics = request.tactics
        sites = list(request.sites)
        weights = np.array(
            [
                (1.0 + 0.35 * request.site_wins.get(site, 0))
                * (1.6 if tactics.site_focus == site else 1.0)
                for site in sites
            ],
            dtype=float,
        )
        if request.scouted_site_load and request.prep_edge > 0.0:
            # Scouting is a partial read of the defensive setup.  At the
            # engine cap it is exact; below it, the estimate stays close to
            # a flat split.  The policy favors the under-loaded site rather
            # than receiving a direct combat bonus for "being prepared".
            mean_load = sum(request.scouted_site_load.values()) / max(len(sites), 1)
            clarity = min(1.0, request.prep_edge / C.PREP_EDGE_CAP)
            for index, site in enumerate(sites):
                load = request.scouted_site_load.get(site, mean_load)
                weights[index] *= max(
                    0.1,
                    1.0
                    + clarity * C.PREP_POLICY_SITE_READ_SPAN * (mean_load - load),
                )
        weights /= weights.sum()
        target_site = sites[int(rng.choice(len(sites), p=weights))]

        # The standing pace dial is the preference.  The actual choice is a
        # player-led IGL call: game sense and comms make an early execute more
        # likely, while the timeout can deliberately speed up or steady it.
        call_quality = igl_effectiveness(captain, request.captain_experience)
        p_execute = 0.35 + tactics.pace / 250.0
        p_execute += (call_quality - 50.0) / 50.0 * C.POLICY_IGL_EXECUTE_SPAN
        if request.under_gunned and request.round_num not in (1, C.ROUNDS_PER_HALF + 1):
            p_execute += (tactics.eco_greed - 50.0) / 50.0 * C.ECO_EXECUTE_SPAN
        if request.timeout is not None:
            if request.timeout.kind == "pressure":
                p_execute += C.TIMEOUT_PRESSURE_EXECUTE_SPAN * request.timeout.clarity
            elif request.timeout.kind == "stabilize":
                p_execute -= C.TIMEOUT_STABILIZE_EXECUTE_SPAN * request.timeout.clarity
        p_execute = min(0.9, max(0.05, p_execute))
        strategy: str = "execute" if rng.random() < p_execute else "default"
        if strategy == "execute":
            go_tick = C.EXECUTE_GO_EARLIEST + int(rng.integers(0, 15))
        else:
            go_tick = int(rng.integers(C.DEFAULT_GO_EARLIEST, C.DEFAULT_GO_LATEST))
        if request.timeout is not None:
            shift = round(C.TIMEOUT_GO_TICK_SHIFT * request.timeout.clarity)
            if request.timeout.kind == "pressure":
                go_tick -= shift
            elif request.timeout.kind == "stabilize":
                go_tick += shift
        go_tick -= round(
            (tactics.pace - 50.0) / 50.0 * C.PACE_GO_TICK_SPAN
        )
        go_tick = min(C.FORCE_GO_TICK, max(1, go_tick))

        carrier = max(
            players,
            key=lambda p: (p.attr("game_sense") + 0.35 * p.attr("composure"), p.id),
        )
        lurker: Player | None = None
        if tactics.map_control > C.LURK_MIN_CONTROL:
            chance = (
                (tactics.map_control - C.LURK_MIN_CONTROL)
                / (100.0 - C.LURK_MIN_CONTROL)
                * C.LURK_MAX_PROB
            )
            candidates = [p for p in players if p.id != carrier.id]
            if candidates and rng.random() < chance:
                lurker = max(
                    candidates,
                    key=lambda p: (p.attr("game_sense") + p.attr("positioning"), p.id),
                )

        entries = self._entry_callouts(target_site)
        width = len(entries)
        if tactics.map_control < C.STACK_MIN_CONTROL:
            width = max(1, round(len(entries) * tactics.map_control / C.STACK_MIN_CONTROL))
        use_entries = entries[:width] or entries
        stackers = [p for p in players if p != lurker]
        entry_candidates = [player for player in stackers if player.id != carrier.id]
        entry = max(
            entry_candidates or stackers,
            key=lambda p: (p.attr("aim_reactivity") + p.attr("movement"), p.id),
        )
        ordered_stackers = [entry]
        ordered_stackers.extend(
            player
            for player in stackers
            if player.id not in (entry.id, carrier.id)
        )
        if carrier in stackers and carrier.id != entry.id:
            ordered_stackers.append(carrier)
        staging_orders = {
            player.id: f"goto:{use_entries[index % len(use_entries)]}"
            for index, player in enumerate(ordered_stackers)
        }
        if lurker is not None:
            mids = sorted(
                c.id for c in self._map.callouts.values() if c.zone == CalloutZone.MID
            )
            lurk_dest = mids[len(mids) // 2] if mids else use_entries[0]
            staging_orders[lurker.id] = f"goto:{lurk_dest}"

        roles = {player.id: "support" for player in players}
        roles[carrier.id] = "carrier"
        roles[entry.id] = "entry"
        if lurker is not None:
            roles[lurker.id] = "lurker"
        return AttackRoundPlan(
            target_site=target_site,
            strategy=strategy,  # type: ignore[arg-type]
            go_tick=go_tick,
            spike_carrier_id=carrier.id,
            lurker_id=lurker.id if lurker is not None else None,
            staging_orders=staging_orders,
            roles=roles,
        )

    def plan_defense(
        self, request: DefenseRoundRequest, rng: np.random.Generator
    ) -> DefenseRoundPlan:
        players = tuple(sorted(request.players, key=lambda p: p.id))
        counts = {site: 5 // len(request.sites) for site in request.sites}
        remainder = 5 - sum(counts.values())
        for index in list(rng.permutation(len(request.sites)))[:remainder]:
            counts[request.sites[int(index)]] += 1

        def anchor_key(player: Player) -> tuple:
            is_anchor = player.playstyle in (Playstyle.ANCHOR, Playstyle.SUPPORT)
            return (not is_anchor, -player.attr("positioning"), player.id)

        forward = request.tactics.aggression > 55.0
        passive = request.tactics.aggression < 45.0
        # The timeout's retake instruction is advice to anchor the sites,
        # not a direct hold/duel bonus.
        if request.timeout is not None and request.timeout.kind == "retake":
            passive = True
            forward = False
        pool = sorted(players, key=anchor_key)
        assignments: dict[str, str] = {}
        roles: dict[str, str] = {}
        player_index = 0
        for site in request.sites:
            site_callouts = self._site_callouts(site)
            holders = self._holder_spots(site)
            if forward and holders:
                spots = holders + site_callouts
            elif passive:
                spots = site_callouts
            else:
                spots = site_callouts + holders
            for spot_index in range(counts[site]):
                if player_index >= len(pool):
                    break
                player = pool[player_index]
                assignment = spots[spot_index % len(spots)]
                assignments[player.id] = assignment
                roles[player.id] = "holder" if assignment in holders else "anchor"
                player_index += 1
        for player in pool[player_index:]:
            assignments[player.id] = self._map.defender_spawn
            roles[player.id] = "flex"
        return DefenseRoundPlan(assignments=assignments, roles=roles)

    def choose_rotation_holdback(self, request: RotationPlanRequest) -> str | None:
        if len(request.off_site_ids) <= 1:
            return None
        return max(
            request.off_site_ids,
            key=lambda pid: (request.players_by_id[pid].attr("positioning"), pid),
        )


class HeuristicCoachPolicy:
    """Thin timeout-only coach baseline.

    Coach quality determines whether the coach recognizes an urgent slide in
    time; specialty and traits choose the advice.  The advice changes only
    the next team-policy plan, never the referee's combat maths directly.
    """

    def call_timeout(
        self, observation: CoachObservation, rng: np.random.Generator
    ) -> TimeoutDirective | None:
        if observation.loss_streak < C.TIMEOUT_MIN_LOSS_STREAK:
            return None
        urgency = (
            (observation.loss_streak - C.TIMEOUT_MIN_LOSS_STREAK + 1)
            * C.TIMEOUT_URGENCY_PER_LOSS
            + max(0, observation.score_against - observation.score_for)
            * C.TIMEOUT_SCORE_DEFICIT_WEIGHT
        )
        recognition = (
            observation.profile.quality * 0.35
            + observation.profile.tactical_knowledge * 0.45
            + observation.profile.analysis * 0.20
        )
        if recognition + urgency < C.TIMEOUT_CALL_THRESHOLD:
            return None

        traits = set(observation.profile.traits)
        if observation.profile.specialty == "mental" or "players_coach" in traits:
            kind: str = "stabilize"
        elif observation.profile.specialty == "tactical" or "innovator" in traits:
            kind = "pressure" if observation.is_attacking else "retake"
        else:
            kind = "pressure" if observation.is_attacking else "retake"
        clarity_score = (
            observation.profile.tactical_knowledge * 0.35
            + observation.profile.people_management * 0.30
            + observation.profile.motivation * 0.20
            + observation.profile.system_fit * 0.15
        )
        clarity = max(0.25, min(1.0, clarity_score / 100.0))
        return TimeoutDirective(kind=kind, clarity=clarity)  # type: ignore[arg-type]
