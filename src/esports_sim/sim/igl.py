"""Shared, deterministic IGL effectiveness maths.

The engine and campaign UI consume the same calculation so the displayed
shot-calling read cannot drift from round-planning behaviour.
"""

from __future__ import annotations

from esports_sim.schemas import Player


def effectiveness(player: Player, experience: float = 100.0) -> float:
    """Skill-weighted shot-calling quality for one team's IGL assignment."""
    # These are the same two shot-calling stats the pre-assignment engine
    # used, so an established legacy IGL (100 experience) remains exactly
    # neutral for the golden match gate.
    skill = (player.attr("game_sense") + player.attr("comms_quality")) / 2.0
    experience = max(0.0, min(100.0, experience))
    return round(max(1.0, min(99.0, 50.0 + (skill - 50.0) * (0.75 + experience / 400.0) - (100.0 - experience) * 0.05)), 2)
