"""Persistent, deterministic audit trail for roster-market decisions."""

from __future__ import annotations

import hashlib

from esports_sim.manager.state import GameState, MarketDecision


def record(
    gs: GameState,
    kind: str,
    outcome: str,
    player_id: str,
    *,
    actor_team_id: str = "",
    counterparty_team_id: str = "",
    context: str = "",
    stance: str = "",
    fee: int = 0,
    salary: int = 0,
    market_value: int = 0,
    org_value: int = 0,
    components: dict[str, int] | None = None,
    effects: dict[str, int] | None = None,
    reason: str = "",
) -> MarketDecision:
    """Append one decision. The sequence number is part of the stable id so
    repeated weekly choices remain distinct while identical seeded runs stay
    byte-identical."""
    seq = len(gs.market_decisions)
    raw = "|".join(
        str(x) for x in (
            gs.seed, gs.season, gs.week, seq, kind, outcome, player_id,
            actor_team_id, counterparty_team_id,
        )
    )
    entry = MarketDecision(
        id=hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest(),
        season=gs.season,
        week=gs.week,
        phase=gs.phase,
        kind=kind,
        outcome=outcome,
        player_id=player_id,
        actor_team_id=actor_team_id,
        counterparty_team_id=counterparty_team_id,
        context=context,
        stance=stance,
        fee=int(fee),
        salary=int(salary),
        market_value=int(market_value),
        org_value=int(org_value),
        components=dict(components or {}),
        effects=dict(effects or {}),
        reason=reason,
    )
    gs.market_decisions.append(entry)
    return entry
