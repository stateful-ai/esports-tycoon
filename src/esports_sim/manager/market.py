"""Transfer market: free-agent signings, releases, contract renewals.

MVP rules: rosters are exactly five when healthy — to upgrade a slot you
release first (paying severance), then sign. AI teams keep themselves
legal automatically; the user does it from the roster/market screens.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.gen import generate_player, _FA_SLOTS  # noqa: F401
from esports_sim.manager.state import GameState
from esports_sim.schemas import Player
from esports_sim.schemas.common import Playstyle

ROSTER_SIZE = 5
SEVERANCE_WEEKS = 6
MIN_CONTRACT_WEEKS = 16
MAX_CONTRACT_WEEKS = 80


def player_quality(p: Player) -> float:
    """Scouting shorthand: mean attribute, condition-agnostic."""
    if not p.attributes:
        return 50.0
    return sum(p.attributes.values()) / len(p.attributes)


def asking_salary(p: Player) -> int:
    """What a free agent wants per week. Age discounts the very young
    (prove-it deals) and the old (last contracts)."""
    q = player_quality(p)
    base = (q ** 1.6) * 6 / 100
    if p.age <= 19:
        base *= 0.8
    elif p.age >= 29:
        base *= 0.75
    return max(1_200, int(np.round(base / 100) * 100))


def can_sign(gs: GameState, team_id: str, player_id: str) -> tuple[bool, str]:
    team = gs.teams[team_id]
    if player_id not in gs.free_agent_ids:
        return False, "player is not a free agent"
    if len(team.player_ids) >= ROSTER_SIZE:
        return False, f"roster is full ({ROSTER_SIZE}); release someone first"
    p = gs.players[player_id]
    ask = asking_salary(p)
    if team.balance < ask * 8:
        return False, f"need {ask * 8:,} cr in the bank to cover the deal"
    return True, ""


def sign_player(
    gs: GameState, team_id: str, player_id: str, weeks: int = 40
) -> tuple[bool, str]:
    ok, why = can_sign(gs, team_id, player_id)
    if not ok:
        return False, why
    team = gs.teams[team_id]
    p = gs.players[player_id]
    p.salary = asking_salary(p)
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    p.morale = min(100.0, p.morale + 8.0)
    team.player_ids.append(player_id)
    gs.free_agent_ids.remove(player_id)
    if team.captain_id is None:
        team.captain_id = player_id
    gs.push_news(f"{team.name} sign {p.handle} ({p.playstyle}) for {p.salary:,}/wk.")
    return True, f"signed {p.handle} at {p.salary:,}/wk for {p.contract_weeks_left} weeks"


def release_player(gs: GameState, team_id: str, player_id: str) -> tuple[bool, str]:
    team = gs.teams[team_id]
    if player_id not in team.player_ids:
        return False, "player is not on this roster"
    p = gs.players[player_id]
    severance = p.salary * SEVERANCE_WEEKS
    team.balance -= severance
    team.player_ids.remove(player_id)
    if team.captain_id == player_id:
        team.captain_id = team.player_ids[0] if team.player_ids else None
    p.contract_weeks_left = 0
    p.morale = max(0.0, p.morale - 15.0)
    gs.free_agent_ids.append(player_id)
    gs.push_news(f"{team.name} release {p.handle} (severance {severance:,} cr).")
    return True, f"released {p.handle}, severance {severance:,} cr"


def renew_contract(
    gs: GameState, team_id: str, player_id: str, weeks: int = 48
) -> tuple[bool, str]:
    team = gs.teams[team_id]
    if player_id not in team.player_ids:
        return False, "player is not on this roster"
    p = gs.players[player_id]
    new_salary = max(asking_salary(p), int(p.salary * 1.1 / 100) * 100)
    p.salary = new_salary
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    p.morale = min(100.0, p.morale + 5.0)
    gs.push_news(f"{p.handle} re-signs with {team.name} at {new_salary:,}/wk.")
    return True, f"renewed {p.handle} at {new_salary:,}/wk for {p.contract_weeks_left} weeks"


# ---------------------------------------------------------------------------
# Weekly market upkeep (contracts tick, AI roster management)


CONTRACT_PRESSURE_WEEKS = 8


def tick_contracts(gs: GameState, rng: np.random.Generator) -> None:
    """Contracts count down weekly. AI teams renew their good players
    before expiry; anyone hitting zero walks to free agency. User players
    in form want an early extension — ignoring them costs morale weekly."""
    for tid in sorted(gs.teams):
        team = gs.teams[tid]
        is_ai = tid != gs.user_team_id
        for pid in list(team.player_ids):
            p = gs.players[pid]
            p.contract_weeks_left = max(0, p.contract_weeks_left - 1)
            if (
                not is_ai
                and 0 < p.contract_weeks_left <= CONTRACT_PRESSURE_WEEKS
                and p.form >= 55
            ):
                if p.contract_weeks_left == CONTRACT_PRESSURE_WEEKS:
                    gs.push_news(
                        f"{p.handle} wants a new deal ({p.contract_weeks_left} "
                        f"weeks left) — morale suffers until renewed."
                    )
                p.morale = max(0.0, round(p.morale - 2.0, 1))
            if is_ai and 0 < p.contract_weeks_left <= 6:
                affordable = team.balance > p.salary * 20
                wants = player_quality(p) >= 52 or len(team.player_ids) <= ROSTER_SIZE
                if affordable and wants and rng.random() < 0.6:
                    renew_contract(gs, tid, pid, weeks=int(rng.integers(32, 64)))
            if p.contract_weeks_left == 0:
                team.player_ids.remove(pid)
                if team.captain_id == pid:
                    team.captain_id = team.player_ids[0] if team.player_ids else None
                gs.free_agent_ids.append(pid)
                gs.push_news(
                    f"{p.handle}'s contract with {team.name} expires — free agent."
                )


def ai_fill_rosters(gs: GameState, gd, rng: np.random.Generator) -> None:
    """Every AI team below five players signs the best-fitting free agent
    it can afford. If the pool runs dry, a fresh prospect is generated."""
    for tid in sorted(gs.teams):
        if tid == gs.user_team_id:
            continue
        team = gs.teams[tid]
        while len(team.player_ids) < ROSTER_SIZE:
            have_styles = {gs.players[pid].playstyle for pid in team.player_ids}
            pool = [gs.players[pid] for pid in gs.free_agent_ids]
            pool.sort(
                key=lambda p: (
                    p.playstyle not in have_styles,  # missing style first
                    player_quality(p),
                ),
                reverse=True,
            )
            picked = None
            for cand in pool:
                if team.balance >= asking_salary(cand) * 8:
                    picked = cand
                    break
            if picked is None:
                picked = _generate_rookie(gs, gd, rng)
            sign_player(gs, tid, picked.id, weeks=int(rng.integers(32, 64)))


def _generate_rookie(gs: GameState, gd, rng: np.random.Generator) -> Player:
    style, role = _FA_SLOTS[gs.fa_counter % len(_FA_SLOTS)]
    gs.fa_counter += 1
    pid = f"fa_gen_{gs.fa_counter}"
    quality = float(rng.uniform(42, 60))
    p = generate_player(rng, pid, style, role, quality, gd)
    p.contract_weeks_left = 0
    gs.players[pid] = p
    gs.free_agent_ids.append(pid)
    gs.push_news(f"Prospect {p.handle} ({p.playstyle}) enters free agency.")
    return p
