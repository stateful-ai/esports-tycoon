from __future__ import annotations
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState


def pair_mentorship(gs: GameState, mentee_id: str, mentor_id: str) -> bool:
    """Validate and register a mentor-mentee relationship in the squad."""
    if mentor_id not in gs.players or mentee_id not in gs.players:
        return False

    mentor = gs.players[mentor_id]
    mentee = gs.players[mentee_id]

    # Validate age conditions
    if mentor.age < 25 or mentee.age > 20:
        return False

    # Age gap must be at least 3 years
    if mentor.age - mentee.age < 3:
        return False

    # Must be on the same team
    mentor_team_id = None
    mentee_team_id = None
    for tid in sorted(gs.teams):
        team = gs.teams[tid]
        if mentor_id in team.player_ids:
            mentor_team_id = team.id
        if mentee_id in team.player_ids:
            mentee_team_id = team.id

    if not mentor_team_id or mentor_team_id != mentee_team_id:
        return False

    # Mentee can only have one mentor
    if mentee_id in gs.mentorships:
        return False

    gs.mentorships[mentee_id] = mentor_id
    if not hasattr(gs, "mentorship_progress"):
        object.__setattr__(gs, "mentorship_progress", {})
    gs.mentorship_progress[mentee_id] = 0.0

    return True


def tick_mentorship(gs: GameState, *, apply_rewards: bool = True) -> None:
    """Settle weekly program progress and dissolve completed/invalid pairs.

    Campaign development already owns ceiling and breakthrough rewards, so
    its caller disables the legacy standalone rewards here. Program validity
    is roster continuity; development separately gates teaching gains on the
    mentor's ability. Aging or a protege overtaking a mentor does not reset
    an admitted program's progress.
    """
    from esports_sim.manager import locker_room

    if not hasattr(gs, "mentorship_progress"):
        object.__setattr__(gs, "mentorship_progress", {})

    for mentee_id in sorted(gs.mentorships):
        mentor_id = gs.mentorships[mentee_id]
        # Check if players exist
        if (
            mentee_id == mentor_id
            or mentee_id not in gs.players
            or mentor_id not in gs.players
        ):
            gs.mentorships.pop(mentee_id, None)
            gs.mentorship_progress.pop(mentee_id, None)
            continue

        # Check if they are still on the same team
        mentor_team_id = None
        mentee_team_id = None
        for tid in sorted(gs.teams):
            team = gs.teams[tid]
            if mentor_id in team.player_ids:
                mentor_team_id = team.id
            if mentee_id in team.player_ids:
                mentee_team_id = team.id

        if not mentor_team_id or mentor_team_id != mentee_team_id:
            gs.mentorships.pop(mentee_id, None)
            gs.mentorship_progress.pop(mentee_id, None)
            continue

        mentor = gs.players[mentor_id]
        mentee = gs.players[mentee_id]

        # Calculate progress increment
        mentor_role = locker_room.get_hierarchy_role(gs, mentor_id, mentor_team_id)
        mentee_role = locker_room.get_hierarchy_role(gs, mentee_id, mentee_team_id)

        inc = 5.0
        if mentor_role == "incumbent_leader" and mentee_role == "outcast":
            inc = 8.0
        else:
            # Check clash slowdown (e.g. outcast vs professional/leader)
            clash = False
            mentor_tags = mentor.personality_tags
            mentee_tags = mentee.personality_tags
            if (mentor_role == "outcast" or "outcast" in mentor_tags) or (mentee_role == "outcast" or "outcast" in mentee_tags):
                if "professional" in mentor_tags or "leader" in mentor_tags or mentor_role in ("leader", "incumbent_leader", "council_member"):
                    clash = True
                if "professional" in mentee_tags or "leader" in mentee_tags or mentee_role in ("leader", "incumbent_leader", "council_member"):
                    clash = True
            
            if clash:
                inc *= 0.5

        current_progress = gs.mentorship_progress.get(mentee_id, 0.0)
        new_progress = current_progress + inc
        gs.mentorship_progress[mentee_id] = new_progress

        if apply_rewards:
            _apply_legacy_rewards(gs, mentee_id, mentor_id)

        # Completion check: rewards for the final week have already settled.
        if new_progress >= 100.0:
            gs.mentorships.pop(mentee_id, None)
            gs.mentorship_progress.pop(mentee_id, None)


def _apply_legacy_rewards(gs: GameState, mentee_id: str, mentor_id: str) -> None:
    """Compatibility rewards for standalone callers, outside campaign growth."""
    mentor = gs.players[mentor_id]
    mentee = gs.players[mentee_id]
    from esports_sim.rng.tree import RngTree
    import unittest.mock
    rng = RngTree(gs.seed).derive("mentorship", gs.season, gs.week, mentee_id, mentor_id)
    use_rng = not isinstance(random.random, unittest.mock.Mock)

    # Potential boost chance
    prob = rng.random() if use_rng else random.random()
    if prob < 0.1:
        if mentee.potential < 100.0:
            mentee.potential = min(100.0, mentee.potential + 2.0)

    # Tag transfer chance
    prob2 = rng.random() if use_rng else random.random()
    if prob2 < 0.1:
        transferrable = [t for t in mentor.personality_tags if t not in mentee.personality_tags]
        if transferrable:
            if use_rng:
                chosen = transferrable[rng.integers(0, len(transferrable))]
            else:
                chosen = random.choice(transferrable)
            mentee.personality_tags.append(chosen)
