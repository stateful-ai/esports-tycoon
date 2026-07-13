from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState


def can_trigger_shout(shout_type: str, loss_streak: int = 0) -> bool:
    """Check if the trigger conditions for a shout are satisfied."""
    if shout_type == "encourage":
        return loss_streak >= 3
    return True


def apply_touchline_shout(gs: GameState, team_id: str, shout_type: str | None, target_player_id: str | None = None, loss_streak: int = 0) -> None:
    """Apply touchline shout adjustments to confidence, morale, aggression, and stamina."""
    if not shout_type or shout_type not in ("demand_focus", "encourage", "demand_effort"):
        return

    team = gs.teams.get(team_id)
    if not team:
        return

    # Check cooldown / no double-dipping in the same round
    shouts_applied = getattr(gs, "shouts_applied_this_round", set())
    if team_id in shouts_applied:
        return
    shouts_applied.add(team_id)
    object.__setattr__(gs, "shouts_applied_this_round", shouts_applied)

    if shout_type == "demand_focus":
        if target_player_id and target_player_id in team.player_ids:
            player = gs.players.get(target_player_id)
            if player:
                # Returns confidence towards 55 midpoint
                diff = 55.0 - player.confidence
                player.confidence = min(100.0, max(0.0, round(player.confidence + diff * 0.5, 1)))

    elif shout_type == "encourage":
        if loss_streak >= 3:
            for pid in team.player_ids:
                player = gs.players.get(pid)
                if player:
                    player.confidence = min(100.0, max(0.0, round(player.confidence + 10.0, 1)))
                    player.morale = min(100.0, max(0.0, round(player.morale + 10.0, 1)))

    elif shout_type == "demand_effort":
        # Boost aggression
        if hasattr(team, "tactics") and hasattr(team.tactics, "aggression"):
            team.tactics.aggression = min(100.0, max(0.0, round(team.tactics.aggression + 15.0, 1)))
        
        # Drain stamina
        for pid in team.player_ids:
            player = gs.players.get(pid)
            if player:
                player.stamina = max(0.0, round(player.stamina - 15.0, 1))


def reset_shout_effects(gs: GameState, team_id: str) -> None:
    """Reset tactical dial adjustments back to 50 at match end."""
    team = gs.teams.get(team_id)
    if team and hasattr(team, "tactics") and hasattr(team.tactics, "aggression"):
        team.tactics.aggression = 50.0

    # Reset cooldown
    shouts_applied = getattr(gs, "shouts_applied_this_round", set())
    shouts_applied.discard(team_id)
    object.__setattr__(gs, "shouts_applied_this_round", shouts_applied)
