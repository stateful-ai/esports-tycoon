"""Deterministic, fallible team communication whiteboard.

The engine owns world truth.  This module only stores delivered player claims
and materialises receiver-specific memories of them.  It deliberately has no
API for marking a claim correct or joining it back to hidden match state.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from esports_sim.rng.tree import RngTree
from esports_sim.schemas import Map, Player
from esports_sim.schemas.communication import (
    ClaimKind,
    CommunicationAction,
    TeamBelief,
    TeamClaim,
)
from esports_sim.sim import constants as C


def _language_overlap(a: Player, b: Player) -> float:
    by_lang = {skill.lang: skill.level for skill in a.languages}
    shared = [min(by_lang[skill.lang], skill.level) for skill in b.languages if skill.lang in by_lang]
    return max(shared, default=50.0)


def _half_life(kind: ClaimKind) -> float:
    if kind in (ClaimKind.ENEMY_LOCATION, ClaimKind.AREA_STATUS):
        return C.COMMS_LOCATION_HALF_LIFE
    if kind == ClaimKind.ENEMY_INTENT:
        return C.COMMS_INTENT_HALF_LIFE
    if kind == ClaimKind.OBJECTIVE:
        return C.COMMS_OBJECTIVE_HALF_LIFE
    return C.COMMS_TEAM_INTENT_HALF_LIFE


class TeamWhiteboard:
    """Append-only per-round claim ledger with deterministic noisy recall."""

    def __init__(
        self,
        tree: RngTree,
        match_id: str,
        game_map: Map,
        players: dict[str, Player],
    ):
        self._tree = tree
        self._match_id = match_id
        self._map = game_map
        self._players = players
        self._claims: dict[str, list[TeamClaim]] = defaultdict(list)
        self._next_id = 0

    @property
    def claims(self) -> tuple[TeamClaim, ...]:
        return tuple(
            claim
            for team_id in sorted(self._claims)
            for claim in self._claims[team_id]
        )

    def reset(self) -> None:
        self._claims.clear()
        self._next_id = 0

    def publish(
        self,
        team_id: str,
        sender_id: str,
        action: CommunicationAction,
        tick: int,
        round_num: int,
    ) -> TeamClaim | None:
        """Pass a chosen utterance through the sender's noisy comms channel."""
        if not action.speak or action.kind is None or action.value is None:
            return None

        sender = self._players[sender_id]
        quality = sender.attr("comms_quality")
        claim_index = self._next_id
        self._next_id += 1
        claim_id = f"r{round_num}-c{claim_index}"
        rng = self._tree.derive(
            "match", self._match_id, "comms", "round", round_num,
            "claim", claim_index,
            "sender", sender_id, "channel",
        )

        # A policy can choose to speak and still fail to get a usable message
        # out under pressure.  High quality makes this rare, never impossible.
        transmit_prob = float(
            np.clip(
                C.COMMS_TRANSMIT_BASE
                + quality / C.COMMS_TRANSMIT_QUALITY_DIV,
                C.COMMS_TRANSMIT_BASE,
                C.COMMS_TRANSMIT_MAX,
            )
        )
        if rng.random() >= transmit_prob:
            return None

        callout = action.callout_id
        enemy_id = action.enemy_id
        expressed = action.expressed_confidence
        corrupt_prob = float(
            np.clip(
                (C.COMMS_CORRUPT_THRESHOLD - quality) / C.COMMS_CORRUPT_DIV,
                0.0,
                C.COMMS_CORRUPT_MAX,
            )
        )
        if rng.random() < corrupt_prob:
            callout = self._nearby_wrong_callout(callout, rng)
            if rng.random() < C.COMMS_CORRUPT_FORGET_ENEMY_PROB:
                enemy_id = None
            expressed = min(
                1.0,
                expressed
                + float(rng.uniform(0.0, C.COMMS_CORRUPT_OVERCONFIDENCE)),
            )

        max_delay = max(0, round((100.0 - quality) / C.COMMS_DELAY_QUALITY_DIV))
        delay = int(rng.integers(0, max_delay + 1)) if max_delay else 0
        claim = TeamClaim(
            claim_id=claim_id,
            team_id=team_id,
            sender_id=sender_id,
            kind=action.kind,
            value=action.value,
            callout_id=callout,
            enemy_id=enemy_id,
            observed_tick=tick,
            delivered_tick=tick + delay,
            expressed_confidence=expressed,
            corrects_claim_id=action.corrects_claim_id,
        )
        self._claims[team_id].append(claim)
        return claim

    def view(self, team_id: str, receiver_id: str, tick: int) -> list[TeamBelief]:
        """Materialise the bounded, fallible whiteboard this player recalls."""
        receiver = self._players[receiver_id]
        visible = [
            claim for claim in self._claims.get(team_id, [])
            if claim.delivered_tick <= tick and claim.sender_id != receiver_id
        ][-C.COMMS_MAX_VISIBLE_BELIEFS:]
        beliefs: list[TeamBelief] = []
        for claim in visible:
            age = tick - claim.delivered_tick
            decay = 0.5 ** (age / _half_life(claim.kind))
            sender = self._players[claim.sender_id]
            language = _language_overlap(sender, receiver)
            recall = (
                receiver.attr("game_sense")
                + receiver.attr("comms_quality")
                + receiver.attr("composure")
                + language
            ) / 4.0
            confidence = claim.expressed_confidence * decay * (
                C.COMMS_RECALL_BASE + recall / C.COMMS_RECALL_QUALITY_DIV
            )
            if confidence < C.COMMS_FORGET_CONFIDENCE:
                continue

            callout = claim.callout_id
            enemy_id = claim.enemy_id
            rng = self._tree.derive(
                "match", self._match_id, "comms", "claim", claim.claim_id,
                "receiver", receiver_id, "recall",
            )
            misremember_prob = float(
                np.clip(
                    (C.COMMS_MISREMEMBER_THRESHOLD - recall)
                    / C.COMMS_MISREMEMBER_DIV
                    + age / C.COMMS_MISREMEMBER_AGE_DIV,
                    0.0,
                    C.COMMS_MISREMEMBER_MAX,
                )
            )
            if rng.random() < misremember_prob:
                if rng.random() < C.COMMS_MISREMEMBER_LOCATION_PROB:
                    callout = self._nearby_wrong_callout(callout, rng)
                else:
                    enemy_id = None
                confidence *= C.COMMS_MISREMEMBER_CONFIDENCE_MULT

            beliefs.append(
                TeamBelief(
                    claim_id=claim.claim_id,
                    source_player_id=claim.sender_id,
                    kind=claim.kind,
                    value=claim.value,
                    callout_id=callout,
                    enemy_id=enemy_id,
                    age_ticks=age,
                    confidence=float(np.clip(confidence, 0.0, 1.0)),
                    corrects_claim_id=claim.corrects_claim_id,
                )
            )
        return beliefs

    def _nearby_wrong_callout(
        self, callout_id: str | None, rng: np.random.Generator
    ) -> str | None:
        if callout_id is None or callout_id not in self._map.callouts:
            return None
        neighbors = sorted(self._map.neighbors(callout_id))
        if not neighbors:
            return None
        return neighbors[int(rng.integers(0, len(neighbors)))]
