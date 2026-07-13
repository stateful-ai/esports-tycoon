"""Locker-room culture and player leadership.

Culture is deliberately a thin campaign layer over facts the save already
owns: player attributes and tenure, pairwise relationships, personality, and
the designated captain.  It does not add a second hidden chemistry model.

The captain remains ``Team.captain_id``.  ``GameState.leadership_groups``
stores up to two additional council members per team, while
``culture_principles`` stores the manager's operating principle.  All effects
are small and bounded; culture should colour a roster, not decide matches by
itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from esports_sim.manager import personality, relationships

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np

    from esports_sim.manager.state import GameState


PRINCIPLES = ("balanced", "accountability", "player_led", "development")
SESSION_ACTIONS = ("accountability", "player_led", "reset", "welcome")
COUNCIL_MAX = 2
SESSION_COOLDOWN_WEEKS = 4


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, value))


def _roster_ids(gs: "GameState", team_id: str) -> list[str]:
    team = gs.teams.get(team_id)
    if team is None:
        return []
    return sorted(pid for pid in team.player_ids if pid in gs.players)


def _mean_relationship(gs: "GameState", ids: list[str]) -> float:
    if len(ids) < 2:
        return 100.0
    values = [
        relationships.get(gs, a, b)
        for i, a in enumerate(ids)
        for b in ids[i + 1 :]
    ]
    return sum(values) / len(values)


def _relationship_standing(gs: "GameState", team_id: str, player_id: str) -> float:
    mates = [pid for pid in _roster_ids(gs, team_id) if pid != player_id]
    if not mates:
        return 50.0
    return sum(relationships.get(gs, player_id, pid) for pid in mates) / len(mates)


def leadership_score(gs: "GameState", team_id: str, player_id: str) -> float:
    """Return a public 0-100 leadership read for one rostered player.

    Match communication and reads carry most of the score.  Professionalism,
    resilience, sociability, club tenure, and standing with teammates make up
    the rest.  The formula contains no role or incumbent-captain bonus, so it
    is useful for comparing genuine alternatives.
    """
    if team_id not in gs.teams:
        raise ValueError("unknown team")
    if player_id not in _roster_ids(gs, team_id):
        raise ValueError("player is not on that roster")

    player = gs.players[player_id]
    axes = personality.axes(player)
    tenure = min(100.0, player.tenure_weeks * 100.0 / 156.0)
    standing = _relationship_standing(gs, team_id, player_id)
    score = (
        player.attr("comms_quality") * 0.31
        + player.attr("game_sense") * 0.27
        + axes["professionalism"] * 0.14
        + axes["resilience"] * 0.08
        + axes["sociability"] * 0.07
        + tenure * 0.07
        + standing * 0.06
    )
    return round(_clamp(score), 1)


def _ranked_leaders(gs: "GameState", team_id: str) -> list[str]:
    return sorted(
        _roster_ids(gs, team_id),
        key=lambda pid: (-leadership_score(gs, team_id, pid), pid),
    )


def _default_starters(gs: "GameState", team_id: str) -> list[str]:
    roster = _roster_ids(gs, team_id)
    chosen = [
        pid for pid in gs.teams[team_id].lineup_ids if pid in roster
    ]
    for pid in sorted(
        roster,
        key=lambda q: (
            -sum(gs.players[q].attributes.values())
            / max(len(gs.players[q].attributes), 1),
            q,
        ),
    ):
        if pid not in chosen:
            chosen.append(pid)
    return chosen[:5]


def ensure_leadership(gs: "GameState") -> None:
    """Repair stale captains and councils for every organization.

    Existing valid choices are respected, including human choices.  Missing
    positions are filled from the same score for human and AI teams, which
    gives AI organizations parity without silently undoing a player's call.
    """
    for team_id in sorted(gs.teams):
        team = gs.teams[team_id]
        roster = _roster_ids(gs, team_id)
        if not roster:
            team.captain_id = None
            gs.leadership_groups[team_id] = []
            gs.culture_principles.setdefault(team_id, "balanced")
            continue

        ranked = _ranked_leaders(gs, team_id)
        if team.captain_id not in roster:
            team.captain_id = ranked[0]

        clean: list[str] = []
        for pid in gs.leadership_groups.get(team_id, []):
            if pid in roster and pid != team.captain_id and pid not in clean:
                clean.append(pid)
            if len(clean) == COUNCIL_MAX:
                break
        for pid in ranked:
            if pid != team.captain_id and pid not in clean:
                clean.append(pid)
            if len(clean) == min(COUNCIL_MAX, len(roster) - 1):
                break
        gs.leadership_groups[team_id] = clean
        if gs.culture_principles.get(team_id) not in PRINCIPLES:
            gs.culture_principles[team_id] = "balanced"


def _principle_morale_delta(player: object, principle: str, scale: float) -> float:
    axes = personality.axes(player)
    if principle == "accountability":
        fit = (axes["professionalism"] + axes["resilience"] - 100.0) / 100.0
    elif principle == "player_led":
        fit = (axes["sociability"] - 50.0) / 50.0
        fit -= max(0.0, axes["ego"] - 70.0) / 100.0
    elif principle == "development":
        fit = (axes["ambition"] - 50.0) / 50.0
        if getattr(player, "age", 20) <= 22:
            fit += 0.2
    else:
        fit = 0.0
    return max(-scale, min(scale, fit * scale))


def set_leadership(
    gs: "GameState",
    team_id: str,
    captain_id: str,
    council_ids: list[str],
    principle: str,
) -> tuple[bool, str]:
    """Set a captain, two-person council, and culture principle.

    A change carries a modest transition cost and personality-shaped response.
    This is a manager choice, so it is rng-free and chronicles the appointment.
    """
    if team_id not in gs.teams:
        return False, "unknown team"
    roster = _roster_ids(gs, team_id)
    if captain_id not in roster:
        return False, "captain must be on the roster"
    if principle not in PRINCIPLES:
        return False, "unknown culture principle"
    if len(council_ids) > COUNCIL_MAX:
        return False, f"the leadership council has at most {COUNCIL_MAX} players"
    if len(set(council_ids)) != len(council_ids):
        return False, "leadership council contains a duplicate"
    if captain_id in council_ids:
        return False, "the captain is not also listed on the council"
    if any(pid not in roster for pid in council_ids):
        return False, "every council member must be on the roster"

    ensure_leadership(gs)
    team = gs.teams[team_id]
    old_captain = team.captain_id
    old_council = list(gs.leadership_groups.get(team_id, []))
    old_principle = gs.culture_principles.get(team_id, "balanced")
    council = list(council_ids)
    changed = (
        old_captain != captain_id
        or old_council != council
        or old_principle != principle
    )
    if not changed:
        return True, "leadership group unchanged"
    now = _week_stamp(gs)
    if gs.leadership_last_change.get(team_id) == now:
        return False, "leadership can only be changed once per week"

    team.captain_id = captain_id
    gs.leadership_groups[team_id] = council
    gs.culture_principles[team_id] = principle

    if old_captain != captain_id:
        new_captain = gs.players[captain_id]
        new_captain.morale = round(_clamp(new_captain.morale + 3.0), 1)
        if old_captain in roster:
            old = gs.players[old_captain]
            old.morale = round(_clamp(old.morale - 2.0), 1)
        # Acceptance reflects both the new captain's standing and each
        # teammate's appetite for hierarchy.  Individual movement stays tiny.
        authority = (leadership_score(gs, team_id, captain_id) - 50.0) / 25.0
        for pid in roster:
            if pid == captain_id:
                continue
            ego_tax = max(0.0, personality.axes(gs.players[pid])["ego"] - 65.0) / 25.0
            relationships.nudge(
                gs, captain_id, pid, max(-1.0, min(1.5, authority - ego_tax))
            )
        team.chemistry = round(_clamp(team.chemistry - 1.5), 1)

    entered = sorted(set(council) - set(old_council))
    removed = sorted(set(old_council) - set(council))
    for pid in entered:
        player = gs.players[pid]
        player.morale = round(_clamp(player.morale + 1.0), 1)
    for pid in removed:
        if pid in gs.players and pid in roster:
            player = gs.players[pid]
            player.morale = round(_clamp(player.morale - 0.5), 1)

    if old_principle != principle:
        for pid in roster:
            player = gs.players[pid]
            delta = _principle_morale_delta(player, principle, 0.8)
            player.morale = round(_clamp(player.morale + delta), 1)
        team.chemistry = round(_clamp(team.chemistry - 0.5), 1)

    from esports_sim.manager import chronicle

    captain = gs.players[captain_id]
    council_names = [gs.players[pid].handle for pid in council]
    suffix = f" Council: {', '.join(council_names)}." if council_names else ""
    chronicle.record(
        gs,
        "leadership",
        f"{captain.handle} is named captain of {team.name}.{suffix}",
        team_id=team_id,
        player_id=captain_id,
        data={"principle": principle, "council": ",".join(council)},
    )
    gs.leadership_last_change[team_id] = now
    return True, f"{captain.handle} will lead a {principle.replace('_', ' ')} group"


def _principle_fit(gs: "GameState", team_id: str, principle: str) -> float:
    roster = _roster_ids(gs, team_id)
    if not roster or principle == "balanced":
        return 50.0
    deltas = [
        _principle_morale_delta(gs.players[pid], principle, 50.0) for pid in roster
    ]
    return round(_clamp(50.0 + sum(deltas) / len(deltas)), 1)


def culture_snapshot(gs: "GameState", team_id: str) -> dict[str, object]:
    """Return the serializer-ready culture read for one organization."""
    if team_id not in gs.teams:
        raise ValueError("unknown team")
    roster = _roster_ids(gs, team_id)
    team = gs.teams[team_id]
    captain_id = team.captain_id if team.captain_id in roster else None
    council = [
        pid
        for pid in gs.leadership_groups.get(team_id, [])
        if pid in roster and pid != captain_id
    ][:COUNCIL_MAX]
    cohesion = round(_mean_relationship(gs, roster), 1)

    if captain_id is None:
        leadership = 0.0
        captain_standing = 50.0
    else:
        captain_score = leadership_score(gs, team_id, captain_id)
        council_scores = [leadership_score(gs, team_id, pid) for pid in council]
        leadership = (
            captain_score
            if not council_scores
            else captain_score * 0.70 + sum(council_scores) / len(council_scores) * 0.30
        )
        captain_standing = _relationship_standing(gs, team_id, captain_id)
    leadership = round(_clamp(leadership), 1)

    if roster:
        avg_tenure = sum(gs.players[pid].tenure_weeks for pid in roster) / len(roster)
        captain_tenure = gs.players[captain_id].tenure_weeks if captain_id else 0
        stability = min(100.0, avg_tenure * 100.0 / 104.0) * 0.75
        stability += min(100.0, captain_tenure * 100.0 / 104.0) * 0.25
    else:
        stability = 0.0
    stability = round(_clamp(stability), 1)
    principle = gs.culture_principles.get(team_id, "balanced")
    if principle not in PRINCIPLES:
        principle = "balanced"
    fit = _principle_fit(gs, team_id, principle)
    overall = round(cohesion * 0.40 + leadership * 0.35 + stability * 0.25, 1)

    flags: list[str] = []
    if cohesion < 40.0:
        flags.append("fractured")
    if leadership < 50.0:
        flags.append("leadership_gap")
    if stability < 30.0:
        flags.append("new_group")
    if captain_id and captain_standing < 42.0:
        flags.append("captain_isolated")
    if fit < 44.0:
        flags.append("principle_tension")
    if cohesion >= 70.0 and leadership >= 65.0:
        flags.append("mentorship_ready")
    if cohesion >= 65.0 and leadership >= 65.0 and stability >= 60.0:
        flags.append("aligned")
    starters = set(_default_starters(gs, team_id))
    if any(
        gs.players[pid].roster_role == "starter" and pid not in starters
        for pid in roster
    ):
        flags.append("broken_role_promises")

    return {
        "team_id": team_id,
        "captain_id": captain_id,
        "council_ids": council,
        "principle": principle,
        "cohesion": cohesion,
        "leadership": leadership,
        "stability": stability,
        "principle_fit": fit,
        "overall": overall,
        "flags": flags,
    }


def ai_manage(gs: "GameState") -> None:
    """Give AI organizations deterministic access to leadership and sessions.

    The AI reads only its own public roster/personality state and uses the same
    action functions, cooldowns, and transition costs as a human manager.
    """
    ensure_leadership(gs)
    for team_id in sorted(gs.teams):
        if gs.is_human(team_id):
            continue
        roster = _roster_ids(gs, team_id)
        if not roster:
            continue

        mean_age = sum(gs.players[pid].age for pid in roster) / len(roster)
        mean_professionalism = sum(
            personality.axes(gs.players[pid])["professionalism"] for pid in roster
        ) / len(roster)
        mean_sociability = sum(
            personality.axes(gs.players[pid])["sociability"] for pid in roster
        ) / len(roster)
        if mean_age <= 22.0:
            principle = "development"
        elif mean_professionalism >= 58.0:
            principle = "accountability"
        elif mean_sociability >= 58.0:
            principle = "player_led"
        else:
            principle = "balanced"

        team = gs.teams[team_id]
        if gs.culture_principles.get(team_id, "balanced") != principle:
            assert team.captain_id is not None
            set_leadership(
                gs,
                team_id,
                team.captain_id,
                list(gs.leadership_groups.get(team_id, [])),
                principle,
            )

        status = session_status(gs, team_id)
        available = set(status["available_actions"])
        if not available:
            continue
        snapshot = culture_snapshot(gs, team_id)
        flags = set(snapshot["flags"])
        welcome_ids = list(status["welcome_player_ids"])
        if flags & {"fractured", "leadership_gap", "captain_isolated"}:
            action = "reset"
            player_id = None
        elif "new_group" in flags and "welcome" in available and welcome_ids:
            action = "welcome"
            player_id = min(
                welcome_ids,
                key=lambda pid: (gs.players[pid].tenure_weeks, pid),
            )
        elif principle == "accountability":
            action, player_id = "accountability", None
        else:
            action, player_id = "player_led", None
        culture_session(gs, team_id, action, player_id)


def weekly_tick(
    gs: "GameState", rng: "np.random.Generator | None" = None
) -> None:
    """Apply small weekly culture effects to every organization.

    ``rng`` is accepted so campaign.py can dedicate a culture stream without
    later changing this API.  The current system intentionally consumes no
    draw: relationship arcs select stable lowest/highest candidates.
    """
    del rng
    ensure_leadership(gs)
    for team_id in sorted(gs.teams):
        roster = _roster_ids(gs, team_id)
        if not roster:
            continue
        snapshot = culture_snapshot(gs, team_id)
        overall = float(snapshot["overall"])
        principle = str(snapshot["principle"])
        base = 0.3 if overall >= 75.0 else (-0.4 if overall < 42.0 else 0.0)
        starters = set(_default_starters(gs, team_id))
        for pid in roster:
            player = gs.players[pid]
            delta = base + _principle_morale_delta(player, principle, 0.15)
            # Contract role promises have a locker-room consequence. A starter
            # left outside the default five loses trust gradually rather than
            # exploding from one rotated map.
            if player.roster_role == "starter" and pid not in starters:
                delta -= 0.6
            delta = max(-0.6, min(0.6, delta))
            player.morale = round(_clamp(player.morale + delta), 1)

        pairs = [
            (relationships.get(gs, a, b), a, b)
            for i, a in enumerate(roster)
            for b in roster[i + 1 :]
        ]
        if pairs and float(snapshot["cohesion"]) < 42.0:
            _value, a, b = min(pairs, key=lambda item: (item[0], item[1], item[2]))
            relationships.nudge(gs, a, b, -0.3)
        elif (
            len(roster) >= 2
            and float(snapshot["cohesion"]) >= 70.0
            and float(snapshot["leadership"]) >= 65.0
        ):
            leaders = [
                pid
                for pid in [snapshot["captain_id"], *snapshot["council_ids"]]
                if pid in roster
            ]
            mentor = min(
                leaders,
                key=lambda pid: (-leadership_score(gs, team_id, pid), pid),
            )
            candidates = [pid for pid in roster if pid not in leaders]
            if candidates:
                protege = min(
                    candidates,
                    key=lambda pid: (
                        gs.players[pid].tenure_weeks,
                        gs.players[pid].age,
                        pid,
                    ),
                )
                relationships.nudge(gs, mentor, protege, 0.3)


def _week_stamp(gs: "GameState") -> int:
    # Campaign seasons are much shorter than 100 weeks.  Leaving a wide gap
    # also makes the offseason count as enough time for a fresh session.
    return gs.season * 100 + gs.week


def session_status(gs: "GameState", team_id: str) -> dict[str, object]:
    """Non-mutating availability shared by UI, headless masks, and actions."""
    now = _week_stamp(gs)
    last = gs.culture_last_action.get(team_id, -10_000)
    remaining = max(0, SESSION_COOLDOWN_WEEKS - (now - last))
    roster = _roster_ids(gs, team_id)
    welcome_ids = [
        pid for pid in roster if gs.players[pid].tenure_weeks <= 26
    ]
    actions = [] if remaining else ["accountability", "player_led", "reset"]
    if not remaining and welcome_ids:
        actions.append("welcome")
    return {
        "available_actions": actions,
        "welcome_player_ids": welcome_ids,
        "cooldown_weeks": remaining,
    }


def culture_session(
    gs: "GameState",
    team_id: str,
    action: str,
    player_id: str | None = None,
) -> tuple[bool, str, dict[str, float]]:
    """Hold one deliberate culture session, limited to once per four weeks."""
    if team_id not in gs.teams:
        return False, "unknown team", {}
    if action not in SESSION_ACTIONS:
        return False, "unknown culture session", {}
    roster = _roster_ids(gs, team_id)
    if not roster:
        return False, "the roster is empty", {}
    status = session_status(gs, team_id)
    if int(status["cooldown_weeks"]) > 0:
        return False, (
            f"the group needs {status['cooldown_weeks']} more week(s) before another session"
        ), {}
    if action not in status["available_actions"]:
        return False, "that culture session is not currently available", {}
    if action == "welcome":
        if player_id not in status["welcome_player_ids"]:
            return False, "choose a rostered player to welcome", {}

    now = _week_stamp(gs)

    ensure_leadership(gs)
    team = gs.teams[team_id]
    morale_before = sum(gs.players[pid].morale for pid in roster)
    chemistry_before = team.chemistry
    relationship_shift = 0.0

    if action == "accountability":
        for pid in roster:
            player = gs.players[pid]
            delta = _principle_morale_delta(player, "accountability", 1.5)
            player.morale = round(_clamp(player.morale + delta), 1)
        professional = sum(
            personality.axes(gs.players[pid])["professionalism"] for pid in roster
        ) / len(roster)
        pair_delta = 0.8 if professional >= 50.0 else -0.5
        for i, a in enumerate(roster):
            for b in roster[i + 1 :]:
                relationships.nudge(gs, a, b, pair_delta)
                relationship_shift += pair_delta
        team.chemistry = round(_clamp(team.chemistry + (0.5 if pair_delta > 0 else -0.5)), 1)
        message = "The group reviewed standards and named what has slipped."

    elif action == "player_led":
        captain_id = team.captain_id
        for pid in roster:
            player = gs.players[pid]
            delta = 1.0 + _principle_morale_delta(player, "player_led", 0.8)
            if pid == captain_id:
                # Sharing the room costs a little formal authority, especially
                # for a less sociable captain, while the group gains ownership.
                delta -= 1.2
            player.morale = round(_clamp(player.morale + delta), 1)
        for i, a in enumerate(roster):
            for b in roster[i + 1 :]:
                relationships.nudge(gs, a, b, 0.4)
                relationship_shift += 0.4
        team.chemistry = round(_clamp(team.chemistry + 0.5), 1)
        message = "The players ran the review and set the next block's priorities."

    elif action == "reset":
        for pid in roster:
            player = gs.players[pid]
            morale_delta = 2.0 if player.morale < 70.0 else 0.5
            player.morale = round(_clamp(player.morale + morale_delta), 1)
            player.confidence = round(_clamp(player.confidence - 1.0), 1)
        for i, a in enumerate(roster):
            for b in roster[i + 1 :]:
                current = relationships.get(gs, a, b)
                delta = max(-1.5, min(1.5, (50.0 - current) * 0.10))
                relationships.nudge(gs, a, b, delta)
                relationship_shift += delta
        team.chemistry = round(_clamp(team.chemistry - 1.0), 1)
        message = "The group cleared the board; old grudges and old momentum both lose weight."

    else:  # welcome
        assert player_id is not None
        newcomer = gs.players[player_id]
        newcomer.morale = round(_clamp(newcomer.morale + 3.0), 1)
        for pid in roster:
            if pid == player_id:
                continue
            teammate = gs.players[pid]
            teammate.morale = round(_clamp(teammate.morale - 0.2), 1)
            delta = 2.0 if pid == team.captain_id else 1.5
            relationships.nudge(gs, player_id, pid, delta)
            relationship_shift += delta
        team.chemistry = round(_clamp(team.chemistry + 0.3), 1)
        message = f"{newcomer.handle} was given a proper first week with the group."

    gs.culture_last_action[team_id] = now
    morale_after = sum(gs.players[pid].morale for pid in roster)
    effects = {
        "morale": round(morale_after - morale_before, 1),
        "chemistry": round(team.chemistry - chemistry_before, 1),
        "relationships": round(relationship_shift, 1),
    }

    from esports_sim.manager import chronicle

    chronicle.record(
        gs,
        "culture",
        f"{team.name} held a {action.replace('_', ' ')} culture session.",
        team_id=team_id,
        player_id=player_id or "",
        data={"action": action},
    )
    return True, message, effects
