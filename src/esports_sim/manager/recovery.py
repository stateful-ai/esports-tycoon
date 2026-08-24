"""Paid recovery: buy your squad's condition back.

Three synthetic players, independently, drove a five-man roster to condition
zero and could not get out. Tom's report is the clearest: "the Squad screen
shows me the disaster and offers exactly three buttons per player: Talk, Renew,
Release. Nothing on this screen rests a player, lowers load, or signs a body."

Resting already existed — a team rest week or a per-player `dev_focus="rest"`
returns +18 condition in `training.py`. What did not exist was a way to spend
*money* on the problem, which is the lever a manager reaches for when the
squad is wrecked and the week still has a match in it. Resting costs you a
week of development; a recovery booking costs you cash instead. That is the
trade, and it is the whole point of this module: two different currencies for
the same problem, so being tired is a decision rather than a dead end.

Design notes:

* **Money is the limiter, not a cooldown.** An earlier sketch decayed the
  benefit on consecutive bookings. That re-creates the reported bug for anyone
  who is already in trouble — the state you most need the lever is the state it
  would have been weakest. Cost scales per player and the retreat is a real
  dent in a transfer budget; spending it every week is a choice with an
  opportunity cost, which is the honest constraint.
* **One booking per week per club.** Not an anti-exploit measure so much as a
  legibility one: "you already booked this week" is a sentence a player
  understands, and it keeps the effect a single readable step.
* **It applies the moment you book it**, rather than at the weekly tick, so the
  Squad screen shows the number move. A recovery you cannot see is a recovery
  the reporting personas would have missed exactly as they missed rest.
* **No rng anywhere.** Cost and effect are pure functions of the roster and the
  tier, so a seed still reproduces its campaign byte for byte.
"""

from __future__ import annotations

from typing import Any

# Tiers, cheapest first. `stamina` and `morale` are added to every rostered
# player and clamped at 100; `cost_per_player` is multiplied by the squad size
# so a ten-man roster genuinely costs more to look after than a five-man one.
RECOVERY_TIERS: dict[str, dict[str, Any]] = {
    "day": {
        "label": "Recovery day",
        "blurb": "A day off the server: physio, sleep, no scrims.",
        "stamina": 14.0,
        "morale": 1.0,
        "cost_per_player": 1800,
    },
    "retreat": {
        "label": "Recovery retreat",
        "blurb": "A full reset away from the facility. Expensive, and it shows.",
        "stamina": 30.0,
        "morale": 3.0,
        "cost_per_player": 5400,
    },
}

TIER_IDS: tuple[str, ...] = tuple(RECOVERY_TIERS)

#: Below this average condition the squad is treated as needing a break — the
#: threshold the dashboard warns on and the AI books against.
TIRED_THRESHOLD = 55.0

#: An AI org only spends on recovery when it can do so without going near the
#: bone; it keeps this much of its balance back.
_AI_RESERVE = 40_000


def tier_cost(gs, team_id: str, tier: str) -> int:
    """What `tier` costs `team_id` this week, scaled by squad size."""
    if tier not in RECOVERY_TIERS:
        raise KeyError(f"unknown recovery tier {tier!r}")
    squad = len(gs.teams[team_id].player_ids)
    return int(RECOVERY_TIERS[tier]["cost_per_player"]) * max(squad, 1)


def booked_week(gs, team_id: str) -> int | None:
    """The week `team_id` last booked recovery, or None if it never has."""
    week = gs.recovery_booked_by.get(team_id)
    return int(week) if week is not None else None


def already_booked(gs, team_id: str) -> bool:
    return booked_week(gs, team_id) == gs.week


def average_condition(gs, team_id: str) -> float:
    roster = gs.roster(team_id)
    if not roster:
        return 100.0
    return round(sum(p.stamina for p in roster) / len(roster), 1)


def squad_needs_a_break(gs, team_id: str) -> bool:
    """True when the squad is tired enough that the game should say so.

    Either the average has sagged or somebody is individually wrecked — a
    five-man roster with two players at zero can still average acceptably,
    which is exactly the state that went unwarned in the playtest.
    """
    roster = gs.roster(team_id)
    if not roster:
        return False
    return (
        average_condition(gs, team_id) < TIRED_THRESHOLD
        or any(p.stamina < 25.0 for p in roster)
    )


def can_book(gs, team_id: str, tier: str) -> tuple[bool, str]:
    """Whether `team_id` may book `tier` right now, and why not if it may not.

    The refusal text is player-facing: it names the money or the week, never a
    field or a tier id.
    """
    if tier not in RECOVERY_TIERS:
        return False, f"unknown recovery option {tier!r}"
    if team_id not in gs.teams:
        return False, f"unknown club {team_id!r}"
    if already_booked(gs, team_id):
        return False, "you have already booked recovery this week"
    if not gs.roster(team_id):
        return False, "there is nobody on the roster to rest"
    cost = tier_cost(gs, team_id, tier)
    balance = gs.teams[team_id].balance
    if balance < cost:
        short = cost - balance
        return False, f"{cost:,} cr needed - you are {short:,} cr short"
    return True, ""


def view(gs, team_id: str) -> dict[str, Any]:
    """Everything the UI needs to draw the booking panel, server-computed.

    The client renders what arrives and owns no cost or eligibility maths, the
    same contract the facilities screen already follows.
    """
    options = []
    for tier in TIER_IDS:
        spec = RECOVERY_TIERS[tier]
        ok, reason = can_book(gs, team_id, tier)
        options.append({
            "id": tier,
            "label": spec["label"],
            "blurb": spec["blurb"],
            "condition_gain": spec["stamina"],
            "morale_gain": spec["morale"],
            "cost": tier_cost(gs, team_id, tier),
            "affordable": gs.teams[team_id].balance >= tier_cost(gs, team_id, tier),
            "enabled": ok,
            "blocked_reason": reason,
        })
    return {
        "options": options,
        "booked_this_week": already_booked(gs, team_id),
        "average_condition": average_condition(gs, team_id),
        "needs_a_break": squad_needs_a_break(gs, team_id),
        "tired_threshold": TIRED_THRESHOLD,
        # Named so the panel can point at the free alternative rather than
        # pretending cash is the only way out.
        "free_alternative": "Set a player's training to Rest on Development, "
        "or run a team Rest week - both recover condition without spending.",
    }


def book(gs, team_id: str, tier: str) -> tuple[bool, str]:
    """Charge `team_id` for `tier` and restore the squad. Deterministic.

    Returns (ok, message); the message is shown to the player either way.
    """
    ok, reason = can_book(gs, team_id, tier)
    if not ok:
        return False, reason

    spec = RECOVERY_TIERS[tier]
    cost = tier_cost(gs, team_id, tier)
    team = gs.teams[team_id]
    team.balance -= cost

    before = average_condition(gs, team_id)
    # Sorted so the mutation order never depends on dict/set iteration.
    for player in sorted(gs.roster(team_id), key=lambda p: p.id):
        player.stamina = round(min(100.0, player.stamina + float(spec["stamina"])), 1)
        player.morale = round(min(100.0, player.morale + float(spec["morale"])), 1)
    after = average_condition(gs, team_id)

    gs.recovery_booked_by[team_id] = gs.week
    gs.push_news(
        f"{team.name} book a {spec['label'].lower()} ({cost:,} cr). "
        f"Squad condition {before:.0f} -> {after:.0f}."
    )
    return True, (
        f"{spec['label']} booked for {cost:,} cr. "
        f"Squad condition {before:.0f} -> {after:.0f}."
    )


def ai_weekly_booking(gs) -> None:
    """Let AI clubs buy condition too, so this is not a player-only lever.

    Deterministic and rng-free: a club books the cheapest tier it can afford
    when its squad is tired and its balance stays comfortable afterwards. AI
    orgs deliberately never book the retreat — the expensive tier is a judgement
    call about a specific week, and an AI spending five times as much every time
    it dips below the threshold would quietly drain the league's transfer money.
    """
    for team_id in sorted(gs.teams):
        if gs.is_human(team_id):
            continue
        if already_booked(gs, team_id):
            continue
        if not squad_needs_a_break(gs, team_id):
            continue
        cost = tier_cost(gs, team_id, "day")
        if gs.teams[team_id].balance - cost < _AI_RESERVE:
            continue
        book(gs, team_id, "day")
