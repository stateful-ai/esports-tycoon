"""Default heuristic policy.

The engine acts as the coach: each decision point it hands the player a
per-player order via `obs.igl_call` (e.g. "goto:a_site", "hold", "plant",
"buy:full"). The policy is the player's hands — it translates the order
into a concrete legal Action, choosing weapons and routes itself.

RL agents and LLM playtesters replace this class without touching the
engine; they receive the same observations and legal-action lists.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from esports_sim.policy.base import Action, ActionType
from esports_sim.registry.loader import GameData
from esports_sim.schemas import Map, PlayerObservation, Playstyle
from esports_sim.sim import constants as C


class HeuristicPolicy:
    """Order-following baseline. One instance per match (holds the map)."""

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
        credits = obs.self_state.credits
        call = obs.igl_call or "buy:full"
        tier = call.split(":", 1)[1] if ":" in call else "full"
        player = self._gd.players[obs.self_state.player_id]
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
                lean = player.attr("aim_precision") - player.attr("movement")
                pick = "vandal" if lean + rng.uniform(-10, 10) >= 0 else "phantom"
                weapon_id, armor = pick, C.ARMOR_VALUE
                spend_weapon = weapons[pick].price + C.ARMOR_PRICE
            elif credits >= weapons["spectre"].price + C.ARMOR_PRICE:
                weapon_id, armor = "spectre", C.ARMOR_VALUE
                spend_weapon = weapons["spectre"].price + C.ARMOR_PRICE

        # Keep the weapon we already own if it's better than what we'd buy.
        owned = obs.self_state.weapon_id
        if owned not in ("classic",) and weapons[owned].price >= spend_weapon:
            weapon_id = owned
            armor = max(armor, obs.self_state.armor and C.ARMOR_VALUE or 0)

        return Action(type=ActionType.BUY, weapon_id=weapon_id, armor=armor)

    # -- protocol ----------------------------------------------------------

    def decide(
        self,
        obs: PlayerObservation,
        legal: list[Action],
        rng: np.random.Generator,
    ) -> Action:
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
            if step is not None and any(
                a.type == ActionType.MOVE_TO and a.callout_id == step
                for a in legal
            ):
                return Action(type=ActionType.MOVE_TO, callout_id=step)

        return Action(type=ActionType.HOLD)
