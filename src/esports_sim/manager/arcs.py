"""Relationship arcs — the locker room's few stories that matter right now.

The chemistry graph, mentorship contracts, promises and lineup history all
already exist; what a manager lacks is a SCARCE, readable list of the arcs
that are live this week. This module derives that list — it stores nothing
and draws no rng, so it is a pure deterministic reader over GameState:

  mentor_bond — a manager-registered mentorship (gs.mentorships) whose pair
                relationship has grown past MENTOR_BOND_BAR: the contract
                turned into trust.
  friction    — a pair at/below FEUD_BAR (the existing pairwise arc), or two
                players chasing the same spotlight role (entry/awper/igl)
                while both trend downward — one slot, two slumps.
  grudge      — a pair at/below GRUDGE_BAR (existing), or a grudge AGAINST
                THE ORG: a recently broken manager promise, or a starter-
                quality regular benched for BENCH_ARC_WEEKS straight
                matchweeks despite belonging in the best five.

`team_arcs` caps the list at MAX_ARCS in a deterministic priority order
(grudges first — they cost you contracts; bonds last — they're good news).
The cap is presentational: EFFECTS key off the underlying conditions so a
fourth simultaneous arc doesn't silently lose its teeth.

Effects are bounded and ride EXISTING channels only:
  - renewal_bias() nudges the opening renewal ask in market.contract_demands
    (+8% for an org grudge, -4% inside a bonded mentorship). That seam is
    only reached by an opened negotiation (web/CLI), so AI renewals and
    hands-off sims are byte-identical.
  - MENTOR_BOND_STEP_MULT deepens development.apply_mentorship_growth's
    ceiling step for bonded pairs. gs.mentorships is empty without human
    action, so hands-off sims are untouched.
  - Chemistry/confidence pressure already flows through the existing graph
    (feuds drag the mean relationship chemistry chases) and through
    promises.resolve_promise (a broken promise hits morale, confidence and
    chemistry). Arcs add no second meter on top.

Inbox: weekly_moments() reports org-grudge formation/cooling for the rare
one-item beat (inbox._arc_items). Pairwise arc formation already reaches
the inbox through the chronicle (_relationship_items), so this only covers
the new org-level signals — no double reporting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from esports_sim.manager import relationships

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState

MAX_ARCS = 3  # the scarce list: at most this many active arcs per team

# A starter-quality regular becomes resentful after sitting out this many
# consecutive matchweeks their team actually played.
BENCH_ARC_WEEKS = 4

# A break from a STATED culture identity (culture.register_choice) stays a live
# locker-room arc for this many weeks after it was chronicled.
CULTURE_ARC_WEEKS = 6

# Bounded effect sizes (see module docstring for the channels).
GRUDGE_RENEWAL_BIAS = 0.08        # org grudge: the player charges to stay
MENTOR_BOND_RENEWAL_BIAS = -0.04  # bonded pair: a friendlier table
MENTOR_BOND_STEP_MULT = 1.25      # bonded mentorship teaches deeper

# Deterministic priority: lower ranks sort (and survive the cap) first.
# identity_betrayal shares the grudge tier — a broken public identity costs the
# room as much as a broken promise.
_KIND_RANK = {"identity_betrayal": 0, "grudge": 0, "friction": 1, "mentor_bond": 2}
_SOURCE_RANK = {
    "culture": 0, "promise": 0, "bench": 1, "pair": 2, "form": 3, "mentorship": 0,
}

_PROMISE_LABEL = {
    "play_time": "playing-time",
    "make_captain": "captaincy",
    "renew_contract": "contract-renewal",
}


def _row(kind: str, source: str, pids: list[str], handles: list[str], text: str) -> dict:
    return {
        "kind": kind,
        "source": source,
        "pids": pids,
        "handles": handles,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Signal reads (each one a pure derivation from stored state)


def _played_weeks(gs: "GameState", team_id: str) -> list[int]:
    """Weeks this season the team actually played, ascending (gs.fixtures
    holds the current season only)."""
    return sorted({
        f.week for f in gs.fixtures
        if f.played and team_id in (f.team_a, f.team_b)
    })


def _trailing_missed(gs: "GameState", pid: str, played: list[int]) -> int:
    """How many of the team's most recent played weeks (newest backwards,
    stopping at a week they dressed or a week before they joined) this
    player sat out entirely."""
    p = gs.players.get(pid)
    if p is None:
        return 0
    snap_weeks = {
        s.week for s in gs.stat_history.get(pid, []) if s.season == gs.season
    }
    count = 0
    for w in reversed(played):
        if w in snap_weeks:
            break
        if gs.week - w > max(p.tenure_weeks, 0):
            break  # predates their arrival — not a benching
        count += 1
    return count


def bench_grudge_weeks(gs: "GameState", team_id: str, pid: str) -> int:
    """Consecutive recent matchweeks a starter-quality regular sat out.

    Only counts when there is a REAL bench (roster > 5 — on a five-man
    roster a missed week means injury/unavailability, not a call), the
    player has dressed before (any stat snap), and they belong in the best
    five by quality (campaign.suggested_five). 0 otherwise.
    """
    from esports_sim.manager import campaign, market

    team = gs.teams.get(team_id)
    if team is None or pid not in team.player_ids:
        return 0
    if len(team.player_ids) <= market.ROSTER_SIZE:
        return 0
    if not gs.stat_history.get(pid):
        return 0  # never dressed anywhere — a prospect, not a benched starter
    if pid not in campaign.suggested_five(gs, team_id):
        return 0
    return _trailing_missed(gs, pid, _played_weeks(gs, team_id))


def org_grudges(gs: "GameState", team_id: str) -> list[dict]:
    """Grudges held against the ORG (not a teammate): a recently broken
    manager promise, or a long-benched starter. One row per player —
    the promise flavour wins when both apply."""
    team = gs.teams.get(team_id)
    if team is None:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    broken = sorted(
        (
            pr for pr in gs.promises
            if pr.status == "broken" and pr.team_id == team_id
            and pr.player_id in gs.players and pr.player_id in team.player_ids
        ),
        key=lambda pr: (pr.player_id, pr.promise_type),
    )
    for pr in broken:
        if pr.player_id in seen:
            continue
        seen.add(pr.player_id)
        p = gs.players[pr.player_id]
        label = _PROMISE_LABEL.get(pr.promise_type, pr.promise_type)
        out.append(_row(
            "grudge", "promise", [pr.player_id], [p.handle],
            f"{p.handle} has not forgotten the broken {label} promise.",
        ))
    for pid in sorted(team.player_ids):
        if pid in seen or pid not in gs.players:
            continue
        weeks = bench_grudge_weeks(gs, team_id, pid)
        if weeks >= BENCH_ARC_WEEKS:
            p = gs.players[pid]
            out.append(_row(
                "grudge", "bench", [pid], [p.handle],
                f"{p.handle} has watched the last {weeks} matchweeks "
                f"from the bench despite a starter's level.",
            ))
    return out


def culture_betrayal_arcs(gs: "GameState", team_id: str) -> list[dict]:
    """A live arc for a recently broken STATED culture identity.

    Pure read over the append-only chronicle: empty unless the team is
    committed (culture.commit_principle stamped it) AND a culture_violation was
    recorded within CULTURE_ARC_WEEKS. Uncommitted/AI teams never produce a
    violation, so this is inert for them and for every pre-F8 save.
    """
    from esports_sim.manager import chronicle

    team = gs.teams.get(team_id)
    if team is None:
        return []
    if gs.culture_committed_since_by.get(team_id) is None:
        return []
    now = gs.season * 100 + gs.week
    out: list[dict] = []
    seen: set[str] = set()
    for entry in reversed(chronicle.of_kinds(gs, {"culture_violation"})):
        if entry.team_id != team_id:
            continue
        if now - (entry.season * 100 + entry.week) >= CULTURE_ARC_WEEKS:
            break  # the chronicle is chronological; older ones only get older
        principle = str(entry.data.get("principle", "identity")).replace("_", " ")
        pid = entry.player_id
        if pid and pid in gs.players and pid in team.player_ids:
            if pid in seen:
                continue
            seen.add(pid)
            handle = gs.players[pid].handle
            out.append(_row(
                "identity_betrayal", "culture", [pid], [handle],
                f"{handle} is still weighing the club's break from its "
                f"{principle} identity.",
            ))
        else:
            if "" in seen:
                continue
            seen.add("")
            out.append(_row(
                "identity_betrayal", "culture", [], [],
                f"{team.name}'s break from its {principle} identity still "
                f"hangs over the room.",
            ))
    return out


def _trending_down(gs: "GameState", pid: str) -> bool:
    """Two consecutive weekly performance points sliding, the latest below
    the league-average 1.0 line. Pure gs.stat_history read."""
    snaps = [s for s in gs.stat_history.get(pid, []) if s.season == gs.season]
    if len(snaps) < 2:
        return False
    return snaps[-1].rating < snaps[-2].rating and snaps[-1].rating < 1.0


def _spotlight_friction(gs: "GameState", team_id: str, roster: list[str]) -> list[dict]:
    """Two players who both want the same spotlight role (entry/awper/igl)
    while both trend downward — and who aren't friends about it."""
    out: list[dict] = []
    for i, a in enumerate(roster):
        for b in roster[i + 1:]:
            pa, pb = gs.players[a], gs.players[b]
            style = str(pa.playstyle)
            if style != str(pb.playstyle) or style not in relationships._SPOTLIGHT_STYLES:
                continue
            if relationships.arc_for_pair(gs, a, b) is not None:
                continue  # the pair already carries a stronger arc
            if relationships.get(gs, a, b) >= 50.0:
                continue  # friendly rivals handle it
            if _trending_down(gs, a) and _trending_down(gs, b):
                out.append(_row(
                    "friction", "form", [a, b], [pa.handle, pb.handle],
                    f"{pa.handle} and {pb.handle} both chase the {style} "
                    f"spotlight and both are sliding.",
                ))
    return out


def is_mentor_bond(gs: "GameState", mentee_id: str, mentor_id: str) -> bool:
    """A manager-registered mentorship whose relationship crossed the bar:
    the contract became trust."""
    return (
        gs.mentorships.get(mentee_id) == mentor_id
        and relationships.get(gs, mentee_id, mentor_id)
        >= relationships.MENTOR_BOND_BAR
    )


# ---------------------------------------------------------------------------
# The scarce list


def team_arcs(gs: "GameState", team_id: str) -> list[dict]:
    """The team's active arcs, at most MAX_ARCS, in deterministic priority
    order (grudge < friction < mentor_bond; org-level sources before pair
    reads; then by player id). Pure derived read — calling it twice, or on
    a reloaded save, returns the same rows."""
    team = gs.teams.get(team_id)
    if team is None:
        return []
    roster = sorted(pid for pid in team.player_ids if pid in gs.players)
    rows: list[dict] = []
    rows += culture_betrayal_arcs(gs, team_id)
    rows += org_grudges(gs, team_id)
    # Pairwise grudge/friction from the existing single source of truth
    # (relationships.arc_for_pair — the same label the profile pair chips
    # show). mentor_bond is intentionally NOT taken from the pair label:
    # the team list reserves it for the registered mentorship contract.
    for i, a in enumerate(roster):
        for b in roster[i + 1:]:
            label = relationships.arc_for_pair(gs, a, b)
            if label not in ("grudge", "friction"):
                continue
            pa, pb = gs.players[a], gs.players[b]
            text = (
                f"{pa.handle} and {pb.handle} carry a real locker-room grudge."
                if label == "grudge"
                else f"Friction between {pa.handle} and {pb.handle} is shaping the room."
            )
            rows.append(_row(label, "pair", [a, b], [pa.handle, pb.handle], text))
    rows += _spotlight_friction(gs, team_id, roster)
    for mentee_id in sorted(gs.mentorships):
        mentor_id = gs.mentorships[mentee_id]
        if mentee_id not in team.player_ids or mentor_id not in team.player_ids:
            continue
        if mentee_id not in gs.players or mentor_id not in gs.players:
            continue
        if is_mentor_bond(gs, mentee_id, mentor_id):
            men, pro = gs.players[mentor_id], gs.players[mentee_id]
            rows.append(_row(
                "mentor_bond", "mentorship", [mentor_id, mentee_id],
                [men.handle, pro.handle],
                f"{men.handle} has taken {pro.handle} under their wing - "
                f"the trust shows.",
            ))
    rows.sort(key=lambda r: (
        _KIND_RANK.get(r["kind"], 9), _SOURCE_RANK.get(r["source"], 9), r["pids"],
    ))
    return rows[:MAX_ARCS]


def player_arcs(gs: "GameState", team_id: str, pid: str) -> list[dict]:
    """The capped team list filtered to arcs involving one player — the
    profile overlay's chips."""
    return [r for r in team_arcs(gs, team_id) if pid in r["pids"]]


# ---------------------------------------------------------------------------
# Bounded effects (existing channels only — see module docstring)


def renewal_bias(gs: "GameState", pid: str, team_id: str) -> float:
    """Additive multiplier nudge for the opening renewal ask
    (market.contract_demands). Org grudges make staying expensive; a
    bonded mentorship softens the table. Pair feuds are deliberately
    excluded — relationships.renewal_veto / contract_fit_multiplier
    already own that channel. 0.0 whenever no arc condition holds."""
    team = gs.teams.get(team_id)
    if team is None or pid not in team.player_ids:
        return 0.0
    for g in org_grudges(gs, team_id):
        if pid in g["pids"]:
            return GRUDGE_RENEWAL_BIAS
    for mentee_id in sorted(gs.mentorships):
        mentor_id = gs.mentorships[mentee_id]
        if pid not in (mentee_id, mentor_id):
            continue
        if mentee_id in team.player_ids and mentor_id in team.player_ids \
                and is_mentor_bond(gs, mentee_id, mentor_id):
            return MENTOR_BOND_RENEWAL_BIAS
    return 0.0


# ---------------------------------------------------------------------------
# Weekly beats for the inbox


def weekly_moments(gs: "GameState", team_id: str, season: int, week: int) -> list[dict]:
    """Org-grudge arcs that FORMED or COOLED on this exact tick, for the
    rare inbox moment. Formation weeks are re-derivable without stored
    arc state: a broken promise still carries resolve_promise's fresh
    weeks_left stamp, and a benching streak crosses BENCH_ARC_WEEKS on
    exactly one played week. Pair-arc formation already reaches the inbox
    via the chronicle, so it is intentionally absent here."""
    from esports_sim.manager import market

    team = gs.teams.get(team_id)
    if team is None or season != gs.season:
        return []
    out: list[dict] = []
    for pr in sorted(gs.promises, key=lambda pr: (pr.player_id, pr.promise_type)):
        # resolve_promise stamps weeks_left=4 at resolution and the weekly
        # tick decrements before resolving, so 4 == broken THIS tick.
        if (
            pr.status == "broken" and pr.team_id == team_id
            and pr.weeks_left == 4 and pr.player_id in gs.players
            and pr.player_id in team.player_ids
        ):
            p = gs.players[pr.player_id]
            label = _PROMISE_LABEL.get(pr.promise_type, pr.promise_type)
            out.append({
                "phase": "formed", "pid": pr.player_id,
                "title": "A grudge against the club is forming",
                "text": (
                    f"{p.handle} feels betrayed over the broken {label} "
                    f"promise. It will weigh on renewal talks until it heals."
                ),
            })
    played = _played_weeks(gs, team_id)
    if played and played[-1] == week and len(team.player_ids) > market.ROSTER_SIZE:
        from esports_sim.manager import campaign

        best_five = set(campaign.suggested_five(gs, team_id))
        for pid in sorted(team.player_ids):
            if pid not in gs.players:
                continue
            if bench_grudge_weeks(gs, team_id, pid) == BENCH_ARC_WEEKS:
                p = gs.players[pid]
                out.append({
                    "phase": "formed", "pid": pid,
                    "title": "A grudge against the club is forming",
                    "text": (
                        f"{p.handle} has now sat out {BENCH_ARC_WEEKS} straight "
                        f"matchweeks despite a starter's level. The benching "
                        f"is turning into a grudge."
                    ),
                })
            elif pid in best_five:
                # Cooled: a starter-quality player dressed this week after
                # a grudge-length streak of watching from the bench.
                snaps = gs.stat_history.get(pid, [])
                dressed_now = any(
                    s.season == season and s.week == week for s in snaps
                )
                if dressed_now and _trailing_missed(
                    gs, pid, played[:-1]
                ) >= BENCH_ARC_WEEKS:
                    p = gs.players[pid]
                    out.append({
                        "phase": "resolved", "pid": pid,
                        "title": "A grudge against the club cools",
                        "text": (
                            f"{p.handle} is back in the lineup after the long "
                            f"benching; the grudge starts to fade."
                        ),
                    })
    out.sort(key=lambda m: (m["phase"], m["pid"]))
    return out
