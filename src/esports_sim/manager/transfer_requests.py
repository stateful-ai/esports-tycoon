"""Player transfer requests created by high-stakes manager conversations.

The request is durable campaign state, not a line of flavor copy: it blocks a
renewal, weakens the seller's asking position, and remains visible until the
player leaves or withdraws it. No RNG lives here.
"""

from __future__ import annotations

from esports_sim.manager.state import GameState, TransferRequest


def active(gs: GameState, player_id: str, team_id: str | None = None) -> bool:
    request = gs.transfer_requests_by.get(player_id)
    if request is None:
        return False
    return team_id is None or request.team_id == team_id


def issue(gs: GameState, player_id: str, reason: str) -> TransferRequest:
    team_id = next(
        (tid for tid in sorted(gs.teams) if player_id in gs.teams[tid].player_ids),
        "",
    )
    if not team_id:
        raise ValueError("player is not under contract")
    request = TransferRequest(
        player_id=player_id,
        team_id=team_id,
        season=gs.season,
        week=gs.week,
        reason=reason,
    )
    gs.transfer_requests_by[player_id] = request
    player = gs.players[player_id]
    gs.push_news(f"{player.handle} submits a transfer request at {gs.teams[team_id].name}.")
    return request


def withdraw(gs: GameState, player_id: str) -> bool:
    request = gs.transfer_requests_by.pop(player_id, None)
    if request is None:
        return False
    player = gs.players.get(player_id)
    if player is not None:
        gs.push_news(f"{player.handle} withdraws the transfer request.")
    return True


def clear(gs: GameState, player_id: str) -> None:
    """Clear silently when the player leaves; the transfer/release has news."""
    gs.transfer_requests_by.pop(player_id, None)
