from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState


def should_trigger_halftime_talk(round_idx: int) -> bool:
    """Return True exactly at halftime (round 12)."""
    return round_idx == 12


def apply_pep_talk(gs: GameState, team_id: str, talk_type: str | None, relative_score: int = 0) -> None:
    """Apply pep talk adjustments to team confidence, morale, and aggression dial."""
    if not talk_type or talk_type not in ("reassure", "fire_up", "focus"):
        return

    team = gs.teams.get(team_id)
    if not team:
        return

    # Apply adjustments to team members
    for pid in team.player_ids:
        player = gs.players.get(pid)
        if not player:
            continue

        if talk_type == "reassure":
            if relative_score < 0:
                # Trailing reassure: stabilize/boost confidence slightly
                player.confidence = min(100.0, max(0.0, round(player.confidence + 5.0, 1)))
            # No-op at relative_score == 0

        elif talk_type == "fire_up":
            if relative_score < 0:
                # Trailing fire up: boost confidence
                player.confidence = min(100.0, max(0.0, round(player.confidence + 10.0, 1)))
                # aggression dial boost
                if hasattr(team, "tactics") and hasattr(team.tactics, "aggression"):
                    team.tactics.aggression = min(100.0, max(0.0, round(team.tactics.aggression + 15.0, 1)))
            elif relative_score >= 8:
                # Leading heavily fire up: backfires, drops morale
                player.morale = min(100.0, max(0.0, round(player.morale - 15.0, 1)))

        elif talk_type == "focus":
            if relative_score < 0:
                # Trailing focus: shift confidence towards 55 midpoint
                diff = 55.0 - player.confidence
                player.confidence = min(100.0, max(0.0, round(player.confidence + diff * 0.5, 1)))
