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

from esports_sim.labels import humanize_phrase
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

    from esports_sim.manager import promises
    for promise in gs.promises:
        if (
            promise.status == "active"
            and promise.promise_type == "make_captain"
            and promise.player_id == captain_id
            and promise.team_id == team_id
        ):
            promises.resolve_promise(gs, promise, success=True)

    return True, f"{captain.handle} will lead a {humanize_phrase(principle)} group"


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

    committed = gs.culture_committed_since_by.get(team_id) is not None
    violations = recent_violations(gs, team_id, limit=3)
    last_violation = gs.culture_last_violation_by.get(team_id)
    identity_betrayed = bool(
        committed
        and last_violation is not None
        and _week_stamp(gs) - last_violation < VIOLATION_MEMORY_WEEKS
    )
    if identity_betrayed:
        flags.append("identity_betrayed")

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
        "commitment": {
            "principle": principle,
            "conviction": conviction(gs, team_id),
            "committed": committed,
        },
        "recent_violations": violations,
        "identity_betrayed": identity_betrayed,
    }


# ---------------------------------------------------------------------------
# F8 — culture principles as an IDENTITY COMMITMENT.
#
# A committed principle stops being a passive flavour dial and becomes a public
# promise the room can watch you keep or break. The media/flavor event streams
# already surface week-to-week choices; principle_alignment scores each resolved
# choice against the committed identity, and register_choice turns a betrayal
# into bounded trust/chemistry/morale damage plus a chronicle entry.
#
# Everything here is gate-safe by construction: only commit_principle (a human
# action) writes culture_committed_since_by, and register_choice returns None
# with NO mutation for any team that lacks that stamp. AI/uncommitted teams are
# therefore inert, so the snowball/dynasty/golden sims stay byte-identical.

# Baseline conviction stamped when a principle becomes a stated commitment.
_COMMIT_CONVICTION = 60.0
# How recently a violation still flags the identity as "betrayed" (weeks).
VIOLATION_MEMORY_WEEKS = 6

# Static alignment map in [-1, +1]: how a resolved public choice reads against
# each non-neutral principle. Positive honors the identity, negative violates
# it; anything absent (and everything under "balanced") is 0/neutral. Authored
# beside media_events._EFFECTS and flavor_events._TEMPLATES — the single source
# of truth for BOTH seams so the two can never drift.
_ALIGNMENT: dict[tuple[str, str, str], dict[str, float]] = {
    # -- media_events ------------------------------------------------------
    ("media", "defend_player", "defend_publicly"): {
        "player_led": 1.0, "development": 0.5, "accountability": -0.5,
    },
    ("media", "defend_player", "demand_response"): {
        "accountability": 1.0, "player_led": -1.0, "development": -0.5,
    },
    ("media", "defend_player", "keep_internal"): {"player_led": 0.3},
    ("media", "protect_rookie", "take_responsibility"): {
        "development": 1.0, "player_led": 1.0, "accountability": -0.5,
    },
    ("media", "protect_rookie", "standards_apply"): {
        "accountability": 1.0, "development": -1.0, "player_led": -1.0,
    },
    ("media", "protect_rookie", "redirect_to_team"): {
        "player_led": 0.3, "development": 0.3,
    },
    ("media", "roster_rumor", "deny_and_back"): {
        "player_led": 1.0, "development": 0.3,
    },
    ("media", "roster_rumor", "acknowledge_market"): {
        "player_led": -1.0, "development": -0.3,
    },
    ("media", "roster_rumor", "no_comment"): {"player_led": -0.3},
    ("media", "derby_expectations", "set_high_bar"): {
        "accountability": 0.5, "player_led": -0.3,
    },
    ("media", "derby_expectations", "respect_rival"): {"player_led": 0.5},
    ("media", "derby_expectations", "shield_group"): {
        "player_led": 0.5, "accountability": -0.5,
    },
    # -- flavor_events -----------------------------------------------------
    ("flavor", "press_scrum", "team_first"): {"player_led": 0.5},
    ("flavor", "press_scrum", "swing_big"): {
        "accountability": 0.5, "player_led": -0.3, "development": -0.3,
    },
    ("flavor", "press_scrum", "keep_private"): {
        "player_led": 0.3, "development": 0.3,
    },
    ("flavor", "behind_the_scenes", "film_grind"): {"development": 0.5},
    ("flavor", "behind_the_scenes", "let_loose"): {
        "player_led": 0.3, "development": -0.3,
    },
    ("flavor", "community_clinic", "full_roster"): {
        "player_led": 0.3, "development": 0.3,
    },
    ("flavor", "community_clinic", "decline"): {
        "player_led": -0.3, "development": -0.3,
    },
    ("flavor", "brand_shoot", "take_shoot"): {"development": -0.3},
    ("flavor", "brand_shoot", "pass"): {"development": 0.3},
    ("flavor", "rival_quote", "measured"): {"player_led": 0.2},
    ("flavor", "rival_quote", "fire_back"): {
        "player_led": -0.3, "accountability": -0.2,
    },
    ("flavor", "rival_quote", "no_comment"): {"player_led": 0.2},
}


def principle_alignment(
    source: str, type_id: str, choice_id: str, principle: str
) -> float:
    """Score a resolved public choice against a committed principle in
    [-1, +1]. Positive honors the identity, negative betrays it, 0 is neutral
    (or principle=='balanced'). Pure static lookup — the single source of truth
    shared by the media and flavor seams."""
    if principle == "balanced" or principle not in PRINCIPLES:
        return 0.0
    return _ALIGNMENT.get((source, type_id, choice_id), {}).get(principle, 0.0)


def conviction(gs: "GameState", team_id: str) -> float:
    """Read the team's 0-100 conviction in its committed principle. Absent
    reads as 50 (uncommitted / no stated identity yet)."""
    return float(gs.culture_conviction_by.get(team_id, 50.0))


def commit_principle(
    gs: "GameState", team_id: str, principle: str
) -> tuple[bool, str]:
    """Promote a principle to a STATED identity commitment.

    This is what arms the whole F8 loop: it stamps culture_committed_since_by
    (the gate register_choice checks) and seeds a conviction baseline. Manager
    action only, rng-free, and it chronicles the commitment. 'balanced' is not
    a commitment — it stays inert so uncommitted teams never trip the gates.
    """
    if team_id not in gs.teams:
        return False, "unknown team"
    if principle not in PRINCIPLES:
        return False, "unknown culture principle"
    if principle == "balanced":
        return False, "a balanced culture is not a stated commitment"

    ensure_leadership(gs)
    team = gs.teams[team_id]
    old_principle = gs.culture_principles.get(team_id, "balanced")
    gs.culture_principles[team_id] = principle
    already = gs.culture_committed_since_by.get(team_id)
    if already is not None and old_principle == principle:
        return True, f"{team.name} remains committed to a {humanize_phrase(principle)} identity"

    gs.culture_committed_since_by[team_id] = _week_stamp(gs)
    gs.culture_conviction_by[team_id] = _COMMIT_CONVICTION

    from esports_sim.manager import chronicle

    chronicle.record(
        gs,
        "culture_commitment",
        f"{team.name} publicly commits to a {humanize_phrase(principle)} identity.",
        team_id=team_id,
        data={"principle": principle},
    )
    return True, f"{team.name} commits to a {humanize_phrase(principle)} identity"


def register_choice(
    gs: "GameState",
    team_id: str,
    source: str,
    type_id: str,
    choice_id: str,
    player_id: str,
) -> dict | None:
    """Score one resolved public choice against the committed identity.

    Returns None immediately — with NO mutation and NO rng — for any team that
    is not committed (no culture_committed_since_by stamp). This is the property
    that keeps AI and gate sims byte-identical, because register_choice fires
    for AI teams too via media/flavor queue_weekly_events.

    On a violation: bounded chemistry/trust/relationship/morale hits weighted by
    per-player principle fit, a conviction drop, and a chronicle 'culture_
    violation'. On an honor: a small conviction bump. Fully deterministic with
    sorted roster iteration.
    """
    if gs.culture_committed_since_by.get(team_id) is None:
        return None
    if team_id not in gs.teams:
        return None
    principle = gs.culture_principles.get(team_id, "balanced")
    if principle == "balanced" or principle not in PRINCIPLES:
        return None
    align = principle_alignment(source, type_id, choice_id, principle)
    if align == 0.0:
        return None
    roster = _roster_ids(gs, team_id)
    if not roster:
        return None

    team = gs.teams[team_id]
    conv_before = conviction(gs, team_id)

    if align > 0.0:
        # Honoring the identity firms up conviction — a bounded, cheap reward.
        bump = round(min(6.0, 2.0 + 4.0 * align), 1)
        gs.culture_conviction_by[team_id] = round(_clamp(conv_before + bump), 1)
        return {
            "outcome": "honored",
            "principle": principle,
            "source": source,
            "type_id": type_id,
            "choice_id": choice_id,
            "conviction_delta": round(gs.culture_conviction_by[team_id] - conv_before, 1),
        }

    # Violation. Severity in (0, 1]; players who BELIEVE in the principle feel
    # the betrayal more (their fit is positive), indifferent ones barely notice.
    severity = -align
    trust_book = gs.manager_player_trust_by.setdefault(team_id, {})
    morale_shift = 0.0
    trust_shift = 0.0
    for pid in sorted(roster):
        p = gs.players[pid]
        fit = _principle_morale_delta(p, principle, 1.0)  # [-1, +1]
        weight = max(0.3, min(1.6, 1.0 + fit))
        morale_hit = round(min(1.6, 1.1 * severity * weight), 2)
        trust_hit = round(min(3.5, 2.2 * severity * weight), 2)
        p.morale = round(_clamp(p.morale - morale_hit), 1)
        trust_book[pid] = round(_clamp(trust_book.get(pid, 50.0) - trust_hit), 1)
        morale_shift -= morale_hit
        trust_shift -= trust_hit

    chem_hit = round(min(1.5, 1.2 * severity), 2)
    team.chemistry = round(_clamp(team.chemistry - chem_hit), 1)

    # A betrayal that singled out one player strains their standing in the room.
    if player_id and player_id in roster:
        for pid in sorted(roster):
            if pid == player_id:
                continue
            relationships.nudge(gs, player_id, pid, max(-0.6, -0.5 * severity))

    conv_drop = round(min(22.0, 8.0 * severity + 10.0 * severity * severity), 1)
    gs.culture_conviction_by[team_id] = round(_clamp(conv_before - conv_drop), 1)
    gs.culture_last_violation_by[team_id] = _week_stamp(gs)

    from esports_sim.manager import chronicle

    label = humanize_phrase(principle)
    chronicle.record(
        gs,
        "culture_violation",
        f"{team.name} broke from its {label} identity ({source}: {type_id}/{choice_id}).",
        team_id=team_id,
        player_id=player_id or "",
        data={
            "principle": principle,
            "source": source,
            "type_id": type_id,
            "choice_id": choice_id,
            "severity": f"{severity:.2f}",
        },
    )
    return {
        "outcome": "violated",
        "principle": principle,
        "source": source,
        "type_id": type_id,
        "choice_id": choice_id,
        "severity": round(severity, 2),
        "morale": round(morale_shift, 1),
        "trust": round(trust_shift, 1),
        "chemistry": round(-chem_hit, 1),
        "conviction_delta": round(gs.culture_conviction_by[team_id] - conv_before, 1),
    }


def recent_violations(
    gs: "GameState", team_id: str, limit: int = 5
) -> list[dict[str, object]]:
    """The team's most recent identity betrayals (newest first) read from the
    append-only chronicle — no parallel mutable state."""
    from esports_sim.manager import chronicle

    out: list[dict[str, object]] = []
    for entry in reversed(chronicle.of_kinds(gs, {"culture_violation"})):
        if entry.team_id != team_id:
            continue
        out.append({
            "season": entry.season,
            "week": entry.week,
            "text": entry.text,
            "principle": entry.data.get("principle", ""),
            "source": entry.data.get("source", ""),
            "type_id": entry.data.get("type_id", ""),
            "choice_id": entry.data.get("choice_id", ""),
            "severity": float(entry.data.get("severity", 0.0) or 0.0),
        })
        if len(out) >= limit:
            break
    return out


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

        # F8: conviction in a STATED identity drifts with how well the roster
        # fits it and how healthy the room is. Committed teams only, so this is
        # a no-op for AI/uncommitted rosters (gate-safe). rng-free, bounded.
        if gs.culture_committed_since_by.get(team_id) is not None:
            conv = conviction(gs, team_id)
            fit = float(snapshot["principle_fit"])
            target = _clamp(40.0 + (fit - 50.0) * 0.8 + (overall - 50.0) * 0.4)
            if "identity_betrayed" in snapshot["flags"]:
                # A fresh betrayal keeps the wound open — no healing this week.
                target = min(target, conv)
            step = max(-1.0, min(1.0, (target - conv) * 0.15))
            gs.culture_conviction_by[team_id] = round(_clamp(conv + step), 1)


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
        f"{team.name} held a {humanize_phrase(action)} culture session.",
        team_id=team_id,
        player_id=player_id or "",
        data={"action": action},
    )
    return True, message, effects
