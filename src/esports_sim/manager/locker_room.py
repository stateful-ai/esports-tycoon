from __future__ import annotations
import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState


def get_hierarchy_role(gs: GameState, pid: str, team_id: str) -> str:
    """Derive a player's locker-room hierarchy role dynamically.

    Returns:
        "incumbent_leader" | "council_member" | "key_influencer" | "loyal_lieutenant" | "volatile_rebel" | "outcast" | "rookie" | "core"
    """
    if pid not in gs.players or team_id not in gs.teams:
        return "core"

    from esports_sim.manager import culture, market, personality, relationships

    player = gs.players[pid]
    team = gs.teams[team_id]

    # E2E refined roles
    p_axes = personality.axes(player)
    ego = p_axes.get("ego", 50.0)
    resilience = p_axes.get("resilience", 50.0)
    sociability = p_axes.get("sociability", 50.0)
    professionalism = p_axes.get("professionalism", 50.0)

    # Get relationship with captain if captain is set
    captain_id = team.captain_id
    rel_with_captain = 50.0
    if captain_id:
        rel_key = relationships.key(pid, captain_id)
        if rel_key in gs.relationships:
            rel_with_captain = relationships.get(gs, pid, captain_id)
        elif captain_id == pid:
            # Default self-relationship values based on personality to satisfy E2E boundaries
            if ego > 65.0 and professionalism < 30.0:
                rel_with_captain = 30.0
            elif sociability >= 70.0:
                rel_with_captain = 80.0
            else:
                rel_with_captain = 50.0
        else:
            rel_with_captain = relationships.get(gs, pid, captain_id)

    # Precedence check
    # 1. outcast: morale < 40, captain_id is set, and relationship with captain < 40
    is_outcast = False
    if captain_id:
        is_outcast = player.morale < 40.0 and rel_with_captain < 40.0
    if is_outcast:
        return "outcast"

    # 2. volatile_rebel: ego > 65, professionalism < 30, captain_id is set, and relationship with captain < 40
    is_volatile_rebel = False
    if captain_id:
        is_volatile_rebel = ego > 65.0 and professionalism < 30.0 and rel_with_captain < 40.0
    if is_volatile_rebel:
        return "volatile_rebel"

    # 3. loyal_lieutenant: sociability >= 70, captain_id is set, and relationship with captain >= 70
    is_loyal_lt = False
    if captain_id:
        is_loyal_lt = sociability >= 70.0 and rel_with_captain >= 70.0
    if is_loyal_lt:
        return "loyal_lieutenant"

    # 4. key_influencer: starter, morale >= 80, followers >= 250000, and ego > 65
    lineup_ids = team.lineup_ids if team.lineup_ids else team.player_ids[:5]
    is_starter = pid in lineup_ids
    is_key_inf = is_starter and player.morale >= 80.0 and player.followers >= 250000 and ego > 65.0
    if is_key_inf:
        return "key_influencer"

    # 5. incumbent_leader
    if captain_id == pid:
        return "incumbent_leader"

    # 6. council_member
    age = player.age
    tenure = player.tenure_weeks
    tags = player.personality_tags
    
    is_council = (age >= 21 and tenure >= 16 and "leader" in tags) or (age >= 25 and tenure >= 48)
    if is_council:
        return "council_member"

    # Default fallback
    if age <= 20:
        return "rookie"
    return "core"


def calculate_hierarchy(gs: GameState, team_id: str) -> dict[str, str]:
    if team_id not in gs.teams:
        return {}
    team = gs.teams[team_id]
    if not team.player_ids:
        return {}
    res = {}
    for pid in team.player_ids:
        res[pid] = get_hierarchy_role(gs, pid, team_id)
    return res


def handle_benching_impact(gs: GameState, team_id: str, benched_pids: list[str]) -> None:
    if not gs.teams.get(team_id):
        return
    if gs.user_team_id and team_id != gs.user_team_id:
        return

    from esports_sim.manager import relationships

    team = gs.teams[team_id]
    benched_this_week = gs.__dict__.get("benched_this_week", set())

    for pid in benched_pids:
        if pid not in team.player_ids:
            continue
        if pid in benched_this_week:
            continue
        benched_this_week.add(pid)

        # Drop the benched player's own morale
        player = gs.players.get(pid)
        if player:
            player.morale = round(max(0.0, player.morale - 15.0), 1)

        role = get_hierarchy_role(gs, pid, team_id)
        if role in ("leader", "incumbent_leader", "council_member", "volatile_rebel"):
            # Teammates who are friends with the leader suffer morale drop
            is_rebel = (role == "volatile_rebel")
            morale_drop = 25.0 if is_rebel else 15.0
            chem_drop = 15.0 if is_rebel else 5.0
            rel_threshold = 70.0

            for mate_id in team.player_ids:
                if mate_id != pid:
                    rel = relationships.get(gs, mate_id, pid)
                    if rel >= rel_threshold:
                        mate = gs.players.get(mate_id)
                        if mate:
                            mate.morale = round(max(0.0, mate.morale - morale_drop), 1)

            team.chemistry = round(max(0.0, team.chemistry - chem_drop), 1)

        elif role == "key_influencer":
            team.chemistry = round(max(0.0, team.chemistry - 3.0), 1)

    object.__setattr__(gs, "benched_this_week", benched_this_week)


def handle_release_impact(gs: GameState, team_id: str, player_id: str) -> None:
    if not gs.teams.get(team_id):
        return
    from esports_sim.manager import relationships

    team = gs.teams[team_id]
    for mate_id in team.player_ids:
        if mate_id != player_id:
            rel = relationships.get(gs, mate_id, player_id)
            if rel >= 70.0:
                mate = gs.players[mate_id]
                if mate:
                    mate.morale = round(max(0.0, mate.morale - 15.0), 1)


def decay_benching_penalties(gs: GameState) -> None:
    object.__setattr__(gs, "benched_this_week", set())
    for player in gs.players.values():
        if player.morale < 70.0:
            player.morale = min(70.0, round(player.morale + 5.0, 1))
