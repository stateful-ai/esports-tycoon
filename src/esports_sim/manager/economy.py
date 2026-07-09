"""Org finances: weekly cash flow, facilities, and season prize money.

Tuned so a mid-table org roughly breaks even on base sponsorship vs
payroll — prize money, merch/ticket momentum, and smart signings are
where budgets are actually won.
"""

from __future__ import annotations

from esports_sim.manager.state import (
    PRIZE_CHAMPION,
    PRIZE_FINAL_LOSER,
    PRIZE_SEMI_LOSER,
    REGULAR_PRIZES,
    GameState,
)
from esports_sim.schemas import Player, Team

# ---------------------------------------------------------------------------
# Base sponsorship + revenue depth


def weekly_sponsor_income(team: Team) -> int:
    fans_component = min(team.fan_count, 2_000_000) * 0.012
    return int(8_000 + team.reputation * 550 + fans_component)


_MERCH_PER_FAN = 0.006
_TICKET_PER_FAN = 0.004
_FAN_CAP_FOR_REVENUE = 3_000_000


def merch_ticket_income(team: Team, win_rate: float = 0.5) -> tuple[int, int]:
    """Merch + ticket revenue, scaled by fan_count and recent win-rate
    momentum (0..1, 0.5 = neutral: fresh campaigns and AI teams without a
    tracked record use this). Returns (merch, tickets)."""
    fans = min(team.fan_count, _FAN_CAP_FOR_REVENUE)
    momentum = 0.6 + 1.4 * max(0.0, min(1.0, win_rate))
    merch = int(fans * _MERCH_PER_FAN * momentum)
    tickets = int(fans * _TICKET_PER_FAN * momentum)
    return merch, tickets


def apply_weekly_finance(
    team: Team,
    roster: list[Player],
    staff_cost: int = 0,
    win_rate: float | None = None,
    facility_upkeep: int = 0,
) -> tuple[int, int]:
    """Returns (income, expenses) after applying them to the balance.

    `win_rate` (0..1, recent win rate) drives merch/ticket momentum; it
    defaults to neutral (0.5) for callers without a standings record handy
    — notably campaign.py's per-team weekly loop, which calls this
    identically for every org and does not currently pass it. Wiring in
    the user org's real win rate there is an optional enhancement (see the
    parent session's hookup notes); the neutral default already keeps
    merch/ticket income live for every team without any campaign.py edit.

    `facility_upkeep` is a plain int (not a GameState) so the caller
    decides which team, if any, actually owns facilities — it defaults to
    0 so this is a no-op for every caller that doesn't pass it. In
    practice the user org's facility upkeep is charged automatically from
    `sponsors.weekly_tick` instead (see that function's docstring for why);
    this parameter exists so upkeep can also be exercised/tested directly
    against this function, and so a future campaign.py hookup can move the
    deduction here if desired.
    """
    merch, tickets = merch_ticket_income(team, 0.5 if win_rate is None else win_rate)
    income = weekly_sponsor_income(team) + merch + tickets
    expenses = sum(p.salary for p in roster) + staff_cost + facility_upkeep
    team.balance += income - expenses
    return income, expenses


# ---------------------------------------------------------------------------
# Facilities (user org only)

FACILITY_NAMES: tuple[str, ...] = (
    "training_center",
    "analytics_suite",
    "marketing_office",
)
FACILITY_MAX_LEVEL = 3
FACILITY_UPGRADE_COST: dict[int, int] = {1: 150_000, 2: 350_000, 3: 700_000}
FACILITY_UPKEEP_PER_LEVEL: dict[str, int] = {
    "training_center": 1_800,
    "analytics_suite": 2_200,
    "marketing_office": 1_500,
}


def facility_marketing_mult(gs: GameState) -> float:
    """Sponsor-offer money multiplier from the marketing_office: 1.0
    bare, +5%/level. Levels 1 and 2 also unlock the stream and apparel
    sponsor slots (see sponsors.SLOT_CONFIG)."""
    return 1.0 + 0.05 * gs.facilities.get("marketing_office", 0)


def facility_upgrade_cost(current_level: int) -> int | None:
    """One-time cost to go from `current_level` to `current_level + 1`, or
    None if already at FACILITY_MAX_LEVEL."""
    target = current_level + 1
    if target > FACILITY_MAX_LEVEL:
        return None
    return FACILITY_UPGRADE_COST[target]


def facility_weekly_upkeep(facilities: dict[str, int]) -> int:
    return sum(
        FACILITY_UPKEEP_PER_LEVEL.get(name, 0) * level
        for name, level in facilities.items()
    )


def facility_training_mult(gs: GameState) -> float:
    """Training growth multiplier from the training_center facility: 1.0
    bare, +6%/level, up to 1.18 at level 3. Consumed in campaign.py's
    weekly training step (multiplied onto the user org's growth alongside
    the coach multiplier)."""
    return 1.0 + 0.06 * gs.facilities.get("training_center", 0)


def facility_scout_mult(gs: GameState) -> float:
    """Scouting speed multiplier from the analytics_suite facility: 1.0
    bare, +8%/level, up to 1.24 at level 3. Consumed in campaign.py's
    weekly scouting step (multiplied onto the scout-progress gain alongside
    the analyst multiplier)."""
    return 1.0 + 0.08 * gs.facilities.get("analytics_suite", 0)


# ---------------------------------------------------------------------------
# Itemized breakdown + projection (user org only; feeds the finances tab)

_SLOTS: tuple[str, ...] = ("title", "jersey", "peripheral")


def _user_win_rate(gs: GameState) -> float:
    record = gs.standings.get(gs.user_team_id)
    if not record or (record.wins + record.losses) == 0:
        return 0.5
    return record.wins / (record.wins + record.losses)


def weekly_breakdown(gs: GameState, staff_cost: int = 0) -> dict:
    """Itemized income/expense snapshot for the user's org, computed live
    from current state (roster, sponsor slots, facilities, standings).

    This is a run-rate *projection* for display, not a literal ledger of a
    past week: some pieces (win-rate momentum, facility upkeep) are
    applied automatically today via `sponsors.weekly_tick` rather than
    through campaign.py's per-team call into `apply_weekly_finance` — see
    that function's docstring. Every component here matches what actually
    lands on the user's balance each week either way.
    """
    team = gs.teams[gs.user_team_id]
    roster = gs.roster(gs.user_team_id)
    win_rate = _user_win_rate(gs)

    salaries = sum(p.salary for p in roster)
    base_sponsor = weekly_sponsor_income(team)
    merch, tickets = merch_ticket_income(team, win_rate)
    sponsors_by_slot = {
        slot: (
            deal.weekly + int(deal.per_win * win_rate)
            if (deal := gs.sponsor_slots.get(slot))
            else 0
        )
        for slot in _SLOTS
    }
    sponsors_total = base_sponsor + sum(sponsors_by_slot.values())
    upkeep = facility_weekly_upkeep(gs.facilities)

    income_total = sponsors_total + merch + tickets
    expense_total = salaries + staff_cost + upkeep

    return {
        "salaries": salaries,
        "staff": staff_cost,
        "sponsors_base": base_sponsor,
        "sponsors_by_slot": sponsors_by_slot,
        "sponsors_total": sponsors_total,
        "merch": merch,
        "tickets": tickets,
        "facility_upkeep": upkeep,
        "prizes": 0,  # episodic (season/playoff payouts), not a weekly run-rate item
        "income_total": income_total,
        "expense_total": expense_total,
        "net": income_total - expense_total,
    }


def cash_projection(gs: GameState, staff_cost: int = 0, weeks: int = 8) -> list[dict]:
    """Simple week-by-week balance projection: salaries/staff/merch/tickets/
    facility upkeep held flat at current levels; active sponsor slot deals
    pay out and drop off as their `weeks_left` counts down. No charting
    lib — this feeds a plain table. Prize money and roster/contract churn
    aren't modeled (keeps the projection honest about its own simplicity)."""
    team = gs.teams[gs.user_team_id]
    roster = gs.roster(gs.user_team_id)
    win_rate = _user_win_rate(gs)

    salaries = sum(p.salary for p in roster)
    base_sponsor = weekly_sponsor_income(team)
    merch, tickets = merch_ticket_income(team, win_rate)
    upkeep = facility_weekly_upkeep(gs.facilities)
    flat_net = (base_sponsor + merch + tickets) - (salaries + staff_cost + upkeep)

    remaining = {slot: deal.weeks_left for slot, deal in gs.sponsor_slots.items()}
    weekly_amounts = {
        slot: deal.weekly + int(deal.per_win * win_rate)
        for slot, deal in gs.sponsor_slots.items()
    }

    balance = team.balance
    rows = []
    for w in range(1, weeks + 1):
        slot_income = 0
        for slot in list(remaining):
            if remaining[slot] <= 0:
                continue
            slot_income += weekly_amounts[slot]
            remaining[slot] -= 1
        net = flat_net + slot_income
        balance += net
        rows.append({"week": gs.week + w, "net": net, "balance": balance})
    return rows


# ---------------------------------------------------------------------------
# Solvency: running an org into the red now has teeth

# Debt below this floor triggers the board's patience running out (a hard,
# escalating consequence rather than an unbounded slow bleed).
INSOLVENCY_FLOOR = -250_000
# Per-week penalties while in the red, scaled by how deep the debt is.
_DEBT_REP_PER = 1.0 / 200_000.0  # reputation lost per credit of debt/week
_DEBT_REP_CAP = 2.5
_DEBT_MORALE_PER = 1.0 / 120_000.0  # morale lost per player per credit/week
_DEBT_MORALE_CAP = 3.5


def check_solvency(gs: GameState) -> None:
    """Debt bites. Every org running a negative balance takes an escalating
    weekly reputation + squad-morale hit (a struggling org can't pay bonuses
    and the locker room feels it); the user also gets a board warning, and a
    harsher one once debt crosses INSOLVENCY_FLOOR. Deterministic and
    manager-only — the match engine never runs the campaign, so this never
    touches the golden/balance gates."""
    for tid in sorted(gs.teams):
        team = gs.teams[tid]
        if team.balance >= 0:
            continue
        debt = -team.balance
        rep_hit = min(_DEBT_REP_CAP, debt * _DEBT_REP_PER)
        morale_hit = min(_DEBT_MORALE_CAP, debt * _DEBT_MORALE_PER)
        team.reputation = round(max(0.0, team.reputation - rep_hit), 1)
        for p in gs.roster(tid):
            p.morale = round(max(0.0, p.morale - morale_hit), 1)
        if tid != gs.user_team_id:
            continue
        if team.balance <= INSOLVENCY_FLOOR:
            gs.push_news(
                f"BOARD WARNING: {team.name} are {debt:,} cr in the red — "
                f"the board demand the books are balanced immediately."
            )
        else:
            gs.push_news(
                f"Finances: {team.name} are running a {debt:,} cr deficit."
            )


def weeks_until_insolvent(gs: GameState, staff_cost: int = 0) -> int | None:
    """Run-rate weeks until the user org's balance would cross the
    insolvency floor at the current flat net (None if the net is
    non-negative — the org isn't heading for trouble). Display helper for
    the finances tab; never mutates state."""
    net = weekly_breakdown(gs, staff_cost)["net"]
    if net >= 0:
        return None
    bal = gs.teams[gs.user_team_id].balance
    runway = bal - INSOLVENCY_FLOOR  # cushion above the floor
    return max(0, int(runway // -net))


# ---------------------------------------------------------------------------
# Season prize money


def pay_regular_season_prizes(gs: GameState) -> None:
    order = gs.standings_order()
    for placement, tid in enumerate(order):
        prize = REGULAR_PRIZES[placement] if placement < len(REGULAR_PRIZES) else 20_000
        gs.teams[tid].balance += prize
    if order:
        top = gs.teams[order[0]]
        gs.push_news(f"{top.name} top the regular season table.")


def pay_playoff_prizes(gs: GameState, champion_id: str, runner_up_id: str,
                       semi_losers: list[str]) -> None:
    gs.teams[champion_id].balance += PRIZE_CHAMPION
    gs.teams[runner_up_id].balance += PRIZE_FINAL_LOSER
    for tid in semi_losers:
        gs.teams[tid].balance += PRIZE_SEMI_LOSER
    champ = gs.teams[champion_id]
    champ.reputation = min(100.0, champ.reputation + 6.0)
    champ.fan_count = int(champ.fan_count * 1.15)
