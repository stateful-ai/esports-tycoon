"""Role/style current ability and assignment comfort.

``overall`` intentionally remains the simple mean of every attribute.  This
module answers the separate question: how well can this player perform in the
role and style they are currently being asked to play?  It is deterministic
and has no RNG of its own.
"""

from __future__ import annotations

from esports_sim.schemas import Player, Playstyle, Role, Team
from esports_sim.sim.igl import effectiveness as igl_effectiveness


# The first group is the job's core; the style overlay gives a player a way to
# distinguish themselves inside the same agent role without making every
# assignment a completely different rating system.
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "duelist": {"aim_precision": 3.0, "aim_reactivity": 3.0, "movement": 2.0, "clutch_factor": 1.0, "positioning": 1.0},
    "controller": {"utility_usage": 3.0, "game_sense": 3.0, "comms_quality": 2.0, "positioning": 2.0, "composure": 1.0},
    "initiator": {"utility_usage": 3.0, "game_sense": 2.5, "comms_quality": 2.0, "aim_reactivity": 1.5, "positioning": 1.0},
    "sentinel": {"positioning": 3.0, "game_sense": 2.5, "utility_usage": 2.0, "composure": 1.5, "clutch_factor": 1.0},
    "flex": {"aim_precision": 1.5, "aim_reactivity": 1.5, "utility_usage": 1.5, "game_sense": 1.5, "positioning": 1.5, "comms_quality": 1.0},
}

STYLE_WEIGHTS: dict[str, dict[str, float]] = {
    "entry": {"aim_reactivity": 2.0, "movement": 2.0, "aim_precision": 1.0},
    "igl": {"game_sense": 2.0, "comms_quality": 2.0, "composure": 1.0},
    "anchor": {"positioning": 2.0, "utility_usage": 1.5, "clutch_factor": 1.0},
    "lurker": {"game_sense": 2.0, "positioning": 2.0, "aim_precision": 1.0},
    "awper": {"aim_precision": 2.5, "composure": 1.5, "positioning": 1.0},
    "support": {"utility_usage": 2.0, "comms_quality": 1.5, "game_sense": 1.0},
}

NEW_ASSIGNMENT_COMFORT = 40.0
COMFORT_GAIN_PER_WEEK = 8.0
NEW_IGL_EXPERIENCE = 40.0
IGL_EXPERIENCE_GAIN_PER_WEEK = 8.0


def assignment_key(p: Player) -> str:
    return f"{p.role}:{p.playstyle}"


def assignment_comfort(p: Player) -> float:
    """Comfort with the current role/style; legacy players start established."""
    return float(p.role_style_comfort.get(assignment_key(p), 100.0))


def weighted_ability(p: Player) -> float:
    """Role/style ability, emphasizing the skills the assignment actually uses."""
    weights: dict[str, float] = {}
    for source, multiplier in ((ROLE_WEIGHTS.get(str(p.role), {}), 1.0), (STYLE_WEIGHTS.get(str(p.playstyle), {}), 0.55)):
        for attr, weight in source.items():
            weights[attr] = weights.get(attr, 0.0) + weight * multiplier
    if not weights:
        return 50.0
    return sum(p.attr(attr) * weight for attr, weight in weights.items()) / sum(weights.values())


def current_ability(p: Player) -> float:
    """Hidden match ability for the assigned job.

    A new assignment can only access 80% of its role/style potential; repeated
    weeks build that toward 100%. This is deliberately relative to raw overall
    so a role change may help or hurt depending on the player's skills.
    """
    raw_overall = sum(p.attributes.values()) / len(p.attributes) if p.attributes else 50.0
    comfort_factor = 0.80 + 0.20 * assignment_comfort(p) / 100.0
    value = raw_overall + (weighted_ability(p) - raw_overall) * comfort_factor
    # Being unfamiliar with a job carries a real execution cost even for a
    # broadly skilled player, while avoiding an implausibly severe cliff.
    value -= (100.0 - assignment_comfort(p)) * 0.06
    return round(max(1.0, min(99.0, value)), 2)


def change_assignment(p: Player, role: Role, playstyle: Playstyle) -> None:
    """Switch a player's job, preserving any prior experience with it."""
    old = assignment_key(p)
    p.role_style_comfort[old] = round(assignment_comfort(p), 1)
    p.role = role  # validated enum values at the web/schema boundary
    p.playstyle = playstyle
    key = assignment_key(p)
    p.role_style_comfort[key] = min(100.0, p.role_style_comfort.get(key, NEW_ASSIGNMENT_COMFORT))


def build_comfort(p: Player) -> None:
    key = assignment_key(p)
    p.role_style_comfort[key] = round(min(100.0, assignment_comfort(p) + COMFORT_GAIN_PER_WEEK), 1)


def igl_experience(team: Team, player_id: str) -> float:
    """Experience as this team's caller; legacy captains start established."""
    return float(team.igl_experience.get(
        player_id, 100.0 if player_id == team.captain_id else NEW_IGL_EXPERIENCE
    ))


def assign_igl(team: Team, player_id: str) -> None:
    """Make a rostered player the IGL while retaining prior calling reps."""
    if team.captain_id:
        team.igl_experience[team.captain_id] = round(
            igl_experience(team, team.captain_id), 1
        )
    team.captain_id = player_id
    team.igl_experience[player_id] = min(
        100.0, team.igl_experience.get(player_id, NEW_IGL_EXPERIENCE)
    )


def build_igl_experience(team: Team, active_ids: set[str]) -> None:
    """A caller gains reps only when they actually dress for the week."""
    captain = team.captain_id
    if captain is None or captain not in active_ids:
        return
    team.igl_experience[captain] = round(min(
        100.0, igl_experience(team, captain) + IGL_EXPERIENCE_GAIN_PER_WEEK
    ), 1)
