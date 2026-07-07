"""Org finances: weekly cash flow and season prize money.

Tuned so a mid-table org roughly breaks even on sponsorship vs payroll —
prize money and smart signings are where budgets are actually won.
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


def weekly_sponsor_income(team: Team) -> int:
    fans_component = min(team.fan_count, 2_000_000) * 0.012
    return int(8_000 + team.reputation * 550 + fans_component)


def apply_weekly_finance(team: Team, roster: list[Player]) -> tuple[int, int]:
    """Returns (income, expenses) after applying them to the balance."""
    income = weekly_sponsor_income(team)
    expenses = sum(p.salary for p in roster)
    team.balance += income - expenses
    return income, expenses


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
