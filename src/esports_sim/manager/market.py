"""Transfer market: free-agent signings, releases, renewals — and real
transfers: contracted players moving between orgs for a fee.

Roster rules: rosters are exactly five when healthy — to upgrade a slot
you release first (paying severance), then sign or buy. AI teams keep
themselves legal automatically; the user does it from the roster/market
screens. AI↔AI transfers resolve instantly (news only); bids for USER
players become TransferOffers the user answers.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import development, relationships
from esports_sim.manager.gen import generate_player, _FA_SLOTS  # noqa: F401
from esports_sim.manager.state import GameState, TransferOffer
from esports_sim.schemas import Player
from esports_sim.schemas.common import Playstyle

# Five dress for any single map, so ROSTER_SIZE stays the "field size" and the
# AI's target roster. Human orgs may carry a bench up to ROSTER_MAX; every team
# needs at least ROSTER_MIN to field a map (enforced by the advance gate), and a
# tournament roster is nominally TOURNAMENT_REGISTER deep (soft/advisory).
ROSTER_SIZE = 5
ROSTER_MIN = 5
ROSTER_MAX = 10
TOURNAMENT_REGISTER = 6
SEVERANCE_WEEKS = 6
MIN_CONTRACT_WEEKS = 16
MAX_CONTRACT_WEEKS = 80


def roster_cap(gs: GameState, team_id: str) -> int:
    """How many players this org may carry. Humans build a bench (up to
    ROSTER_MAX); AI orgs stay lean at the field size so their economy and
    roster upkeep are unchanged."""
    return ROSTER_MAX if gs.is_human(team_id) else ROSTER_SIZE


def roster_ready(gs: GameState, team_id: str) -> tuple[bool, str]:
    """A team must be able to dress five for a map, so it needs at least
    ROSTER_MIN players before the week can tick. Returns (ok, reason)."""
    n = len(gs.teams[team_id].player_ids)
    if n < ROSTER_MIN:
        short = ROSTER_MIN - n
        return False, (
            f"you need {ROSTER_MIN} players to advance — "
            f"sign {short} more"
        )
    return True, ""


def player_quality(p: Player) -> float:
    """Scouting shorthand: mean attribute, condition-agnostic."""
    if not p.attributes:
        return 50.0
    return sum(p.attributes.values()) / len(p.attributes)


def asking_salary(p: Player) -> int:
    """What a free agent wants per week. Age discounts the very young
    (prove-it deals) and the old (last contracts); mercenaries charge a
    premium, loyal players take a hometown number."""
    q = player_quality(p)
    # Same curve gen.py uses for initial contracts (q=70 → ~5,400/wk).
    base = (q ** 1.6) * 6 / 100
    if p.age <= 19:
        base *= 0.8
    elif p.age >= 29:
        base *= 0.75
    base *= development.trait_value(p, "salary_mult", 1.0)
    return max(1_200, int(np.round(base) * 100))


def can_sign(gs: GameState, team_id: str, player_id: str) -> tuple[bool, str]:
    team = gs.teams[team_id]
    # Rosters lock for a human org during the playoffs. AI upkeep still fills
    # (it never runs "signings" the user sees) so tier-1 sides stay legal.
    if gs.phase == "playoffs" and gs.is_human(team_id):
        return False, "rosters are locked during the playoffs"
    if player_id not in gs.free_agent_ids:
        return False, "player is not a free agent"
    cap = roster_cap(gs, team_id)
    if len(team.player_ids) >= cap:
        return False, f"roster is full ({cap}); release someone first"
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
    relationships.on_departure(gs, player_id, team_id)
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


def can_swap(
    gs: GameState, team_id: str, sign_id: str, drop_id: str
) -> tuple[bool, str]:
    """A swap drops one rostered player and signs one free agent in a single
    move — the way to refresh a full roster in-place. Legal exactly when the
    drop is on the roster and, with that slot freed, the signing clears
    `can_sign` (free agent, phase, funds). Affordability is checked on the net:
    the drop's severance is spent before the new wage commitment."""
    team = gs.teams[team_id]
    if gs.phase == "playoffs" and gs.is_human(team_id):
        return False, "rosters are locked during the playoffs"
    if drop_id not in team.player_ids:
        return False, "the player to drop is not on this roster"
    if sign_id not in gs.free_agent_ids:
        return False, "the player to sign is not a free agent"
    if sign_id == drop_id:
        return False, "cannot swap a player for themselves"
    fa = gs.players[sign_id]
    dropped = gs.players[drop_id]
    severance = dropped.salary * SEVERANCE_WEEKS
    ask = asking_salary(fa)
    # Net cash the club must have on hand: severance now + wage cushion after.
    if team.balance < severance + ask * 8:
        need = severance + ask * 8
        return False, f"need {need:,} cr to cover severance + the new deal"
    return True, ""


def swap_player(
    gs: GameState, team_id: str, sign_id: str, drop_id: str, weeks: int = 40
) -> tuple[bool, str]:
    """Release `drop_id` and sign free agent `sign_id` atomically. Because the
    release frees the slot first, the roster never dips below the cap between
    the two halves, so this works even from a full roster."""
    ok, why = can_swap(gs, team_id, sign_id, drop_id)
    if not ok:
        return False, why
    dropped = gs.players[drop_id]
    release_player(gs, team_id, drop_id)
    ok, msg = sign_player(gs, team_id, sign_id, weeks=weeks)
    if not ok:
        # Extremely defensive: can_swap already vetted this. If the signing
        # somehow fails, the drop stands (the release news is already out).
        return False, f"dropped {dropped.handle}, but signing failed: {msg}"
    signed = gs.players[sign_id]
    return True, f"swapped out {dropped.handle} for {signed.handle}"


# ---------------------------------------------------------------------------
# Weekly market upkeep (contracts tick, AI roster management)


CONTRACT_PRESSURE_WEEKS = 8


def tick_contracts(gs: GameState, rng: np.random.Generator) -> None:
    """Contracts count down weekly. AI teams renew their good players
    before expiry; anyone hitting zero walks to free agency. User players
    in form want an early extension — ignoring them costs morale weekly."""
    for tid in sorted(gs.teams):
        team = gs.teams[tid]
        is_ai = not gs.is_human(tid)
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
        if gs.is_human(tid):
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


# Free-agent competition: a marquee FA draws rival AI interest.
POACH_QUALITY = 60.0  # only genuinely desirable FAs draw competition
POACH_GAP = 8.0  # quality edge a full team needs over its weakest same-role
POACH_PROB = 0.5  # per week, once at least one suitor exists


def ai_poach_free_agents(gs: GameState, gd, rng: np.random.Generator) -> None:
    """Premium free agents don't sit uncontested. After AI teams fill open
    slots, a needy AI org may still move for a top FA — upgrading over its
    weakest same-role player — so the user competes for marquee talent
    instead of grabbing it for free. At most one poach per week keeps it
    measured; deterministic from the passed rng."""
    pool = sorted(
        (gs.players[pid] for pid in gs.free_agent_ids),
        key=lambda p: (player_quality(p), p.id),
        reverse=True,
    )
    for cand in pool:
        cq = player_quality(cand)
        if cq < POACH_QUALITY:
            return  # nothing premium left in the pool
        suitors: list[tuple[str, str | None]] = []  # (team, player_to_drop)
        for tid in sorted(gs.teams):
            if gs.is_human(tid):
                continue
            team = gs.teams[tid]
            if len(team.player_ids) < ROSTER_SIZE:
                if team.balance >= asking_salary(cand) * 8:
                    suitors.append((tid, None))
                continue
            same = [
                gs.players[pid]
                for pid in team.player_ids
                if str(gs.players[pid].playstyle) == str(cand.playstyle)
            ]
            if not same:
                continue
            weakest = min(same, key=lambda p: (player_quality(p), p.id))
            # Reserve the dropped player's severance too: release_player
            # charges it before sign_player re-checks affordability, so
            # without this the swap can strand the roster at four players.
            severance = weakest.salary * SEVERANCE_WEEKS
            if (
                cq - player_quality(weakest) >= POACH_GAP
                and team.balance >= asking_salary(cand) * 12 + severance
            ):
                suitors.append((tid, weakest.id))
        if not suitors:
            continue
        if rng.random() >= POACH_PROB:
            return  # the league lets this one sit this week
        tid, drop = suitors[int(rng.integers(0, len(suitors)))]
        if drop is not None:
            release_player(gs, tid, drop)
        sign_player(gs, tid, cand.id, weeks=int(rng.integers(32, 64)))
        return  # one measured move per week


# ---------------------------------------------------------------------------
# Transfers: contracted players moving for a fee


def transfer_value(p: Player) -> int:
    """What a contracted player is worth on the market. Youth with a big
    CA->PA gap carries a premium; expiring contracts sell at a discount
    (why pay full freight for someone who walks in two months?)."""
    ca = player_quality(p)
    pa = development.potential_of(p)
    # Curve calibrated so a 55-CA squaddie ≈ 95k, a 70-CA starter ≈ 240k,
    # an 85-CA star ≈ 420k before premiums.
    base = 800.0 * max(1.0, ca - 35.0) ** 1.6
    gap_premium = max(0.0, pa - ca) / 40.0 * (1.5 if p.age <= 21 else 0.8)
    base *= 1.0 + gap_premium
    if p.age >= 28:
        base *= 0.55
    elif p.age >= 26:
        base *= 0.8
    base *= 0.5 + min(p.contract_weeks_left, 60) / 80.0
    return max(10_000, int(round(base / 1000) * 1000))


def team_of(gs: GameState, pid: str) -> str | None:
    return next((t.id for t in gs.teams.values() if pid in t.player_ids), None)


def transfer_ask(gs: GameState, pid: str) -> int:
    """Seller's price: market value, plus a scarcity premium when the
    player is the seller's best (nobody sells their franchise cheap)."""
    p = gs.players[pid]
    seller_id = team_of(gs, pid)
    if seller_id is None:
        return transfer_value(p)
    roster = gs.roster(seller_id)
    ranked = sorted(roster, key=lambda q: -player_quality(q))
    mult = 1.0
    if ranked and ranked[0].id == pid:
        mult = 1.6
    elif len(ranked) > 1 and ranked[1].id == pid:
        mult = 1.25
    return int(round(transfer_value(p) * mult / 1000) * 1000)


def execute_transfer(
    gs: GameState, pid: str, buyer_id: str, fee: int, weeks: int = 52
) -> tuple[bool, str]:
    """Move a contracted player for money. The buyer must have roster
    space unless it's an AI org (which auto-releases its weakest)."""
    seller_id = team_of(gs, pid)
    if seller_id is None or seller_id == buyer_id:
        return False, "player is not transferable"
    seller, buyer = gs.teams[seller_id], gs.teams[buyer_id]
    p = gs.players[pid]
    if buyer.balance < fee:
        return False, "buyer cannot afford the fee"
    if len(buyer.player_ids) >= roster_cap(gs, buyer_id):
        if gs.is_human(buyer_id):
            cap = roster_cap(gs, buyer_id)
            return False, f"roster is full ({cap}); release someone first"
        weakest = min(
            (gs.players[q] for q in buyer.player_ids), key=player_quality
        )
        buyer.player_ids.remove(weakest.id)
        weakest.contract_weeks_left = 0
        gs.free_agent_ids.append(weakest.id)
        if buyer.captain_id == weakest.id:
            buyer.captain_id = buyer.player_ids[0] if buyer.player_ids else None
    buyer.balance -= fee
    seller.balance += fee
    relationships.on_departure(gs, pid, seller_id)
    seller.player_ids.remove(pid)
    buyer.player_ids.append(pid)
    if seller.captain_id == pid:
        seller.captain_id = seller.player_ids[0] if seller.player_ids else None
    if buyer.captain_id is None:
        buyer.captain_id = pid
    p.salary = max(1_200, int(asking_salary(p) * 1.1 / 100) * 100)
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    p.morale = round(min(100.0, p.morale + 6.0), 1)
    gs.push_news(
        f"TRANSFER: {p.handle} joins {buyer.name} from {seller.name} "
        f"for {fee:,} cr."
    )
    return True, f"{p.handle} joins {buyer.name} for {fee:,} cr"


# ---------------------------------------------------------------------------
# Package deals: players + cash both ways


def package_value(
    gs: GameState, out_pids: list[str], cash_to_seller: int, cash_to_buyer: int = 0
) -> int:
    """Net value the buyer is sending the seller: the market value of the
    players offered plus cash going out, minus any cash requested back. What an
    AI seller weighs against its asking price."""
    players = sum(transfer_value(gs.players[pid]) for pid in out_pids)
    return players + cash_to_seller - cash_to_buyer


def _relocate(gs: GameState, pid: str, from_id: str, to_id: str, weeks: int) -> None:
    """Move one contracted player between two rosters, refreshing their deal and
    repairing captaincy on both ends. Cash is the caller's job."""
    src, dst = gs.teams[from_id], gs.teams[to_id]
    p = gs.players[pid]
    relationships.on_departure(gs, pid, from_id)
    src.player_ids.remove(pid)
    dst.player_ids.append(pid)
    if src.captain_id == pid:
        src.captain_id = src.player_ids[0] if src.player_ids else None
    if dst.captain_id is None:
        dst.captain_id = pid
    p.salary = max(1_200, int(asking_salary(p) * 1.1 / 100) * 100)
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    p.morale = round(min(100.0, p.morale + 6.0), 1)


def execute_package(
    gs: GameState,
    target_pid: str,
    buyer_id: str,
    out_pids: list[str],
    cash_to_seller: int,
    cash_to_buyer: int,
    weeks: int = 52,
) -> tuple[bool, str]:
    """Settle a package: `target_pid` joins the buyer, `out_pids` go the other
    way, and cash flows per `cash_to_seller` / `cash_to_buyer`. Assumes the deal
    was already vetted (see `propose_package`) but re-checks ownership + funds
    defensively, since an offer can sit on a human's desk for weeks."""
    seller_id = team_of(gs, target_pid)
    if seller_id is None or seller_id == buyer_id:
        return False, "player is not transferable"
    seller, buyer = gs.teams[seller_id], gs.teams[buyer_id]
    for pid in out_pids:
        if pid not in buyer.player_ids:
            return False, "an offered player is no longer on the buyer's roster"
    # An offer can sit on a human seller's desk for weeks — either side may have
    # signed or released in the meantime. Revalidate the resulting roster sizes
    # (same rule as propose_package) so a stale deal can't strand a roster over
    # the cap or under the minimum.
    buyer_end = len(buyer.player_ids) - len(out_pids) + 1
    seller_end = len(seller.player_ids) - 1 + len(out_pids)
    if not (ROSTER_MIN <= buyer_end <= roster_cap(gs, buyer_id)):
        return False, f"{buyer.name} can no longer legally roster this deal"
    if not (ROSTER_MIN <= seller_end <= roster_cap(gs, seller_id)):
        return False, f"{seller.name} can no longer legally roster this deal"
    if buyer.balance + cash_to_buyer < cash_to_seller:
        return False, "buyer cannot afford the cash in this deal"
    if seller.balance + cash_to_seller < cash_to_buyer:
        return False, "seller cannot afford the cash in this deal"
    buyer.balance += cash_to_buyer - cash_to_seller
    seller.balance += cash_to_seller - cash_to_buyer
    target = gs.players[target_pid]
    _relocate(gs, target_pid, seller_id, buyer_id, weeks)
    for pid in out_pids:
        _relocate(gs, pid, buyer_id, seller_id, weeks)
    incoming = ", ".join(gs.players[pid].handle for pid in out_pids) or "cash"
    cash_note = ""
    if cash_to_seller:
        cash_note = f" + {cash_to_seller:,} cr"
    elif cash_to_buyer:
        cash_note = f" (with {cash_to_buyer:,} cr back)"
    gs.push_news(
        f"TRANSFER: {target.handle} joins {buyer.name} from {seller.name} "
        f"for {incoming}{cash_note}."
    )
    return True, f"{target.handle} joins {buyer.name} ({incoming}{cash_note})"


def propose_package(
    gs: GameState,
    target_pid: str,
    out_pids: list[str],
    cash_out: int,
    cash_in: int,
) -> tuple[bool, str]:
    """The acting manager offers a package (their players in `out_pids` + up to
    `cash_out` cash, optionally asking `cash_in` back) for a rival's
    `target_pid`. AI sellers resolve instantly on value; a human seller gets the
    offer on their desk. Rosters lock in the playoffs (freeze both signings and
    transfers)."""
    buyer_id = gs.acting_team_id
    if gs.phase == "playoffs" and gs.is_human(buyer_id):
        return False, "rosters are locked during the playoffs"
    seller_id = team_of(gs, target_pid)
    if seller_id is None:
        return False, "player is a free agent — sign them instead"
    if seller_id == buyer_id:
        return False, "that's your own player"
    buyer, seller = gs.teams[buyer_id], gs.teams[seller_id]
    out_pids = list(dict.fromkeys(out_pids))  # de-dupe, preserve order
    if target_pid in out_pids:
        return False, "can't offer the player you're trying to sign"
    for pid in out_pids:
        if pid not in buyer.player_ids:
            return False, "you can only offer your own players"
    # Net the two cash directions so at most one is non-zero.
    cash_out = max(0, int(cash_out))
    cash_in = max(0, int(cash_in))
    if cash_out >= cash_in:
        cash_out, cash_in = cash_out - cash_in, 0
    else:
        cash_out, cash_in = 0, cash_in - cash_out
    # Resulting roster sizes: buyer gains the target and loses the offered
    # players; seller does the reverse. Both must stay legal.
    buyer_end = len(buyer.player_ids) - len(out_pids) + 1
    seller_end = len(seller.player_ids) - 1 + len(out_pids)
    if not (ROSTER_MIN <= buyer_end <= roster_cap(gs, buyer_id)):
        return False, (
            f"this deal would leave you at {buyer_end} players "
            f"(must be {ROSTER_MIN}-{roster_cap(gs, buyer_id)})"
        )
    if not (ROSTER_MIN <= seller_end <= roster_cap(gs, seller_id)):
        return False, (
            f"{seller.name} can't roster {seller_end} players — "
            "offer fewer of your own"
        )
    ask_wage = asking_salary(gs.players[target_pid])
    if buyer.balance + cash_in < cash_out + ask_wage * 8:
        return False, "you can't cover the cash and the new wages"
    if gs.is_human(seller_id):
        if any(
            o.player_id == target_pid and o.to_team == buyer_id
            for o in gs.transfer_offers
        ):
            return False, "you already have a bid in for that player"
        gs.transfer_offers.append(
            TransferOffer(
                player_id=target_pid,
                from_team=seller_id,
                to_team=buyer_id,
                fee=cash_out,
                expires_week=gs.week + 2,
                offer_player_ids=out_pids,
                cash_to_seller=cash_out,
                cash_to_buyer=cash_in,
            )
        )
        return True, (
            f"package offer sent to {seller.name} for "
            f"{gs.players[target_pid].handle}"
        )
    # AI seller: accept iff the package clears the asking price, and it can fund
    # any cash-back it's being asked for.
    value = package_value(gs, out_pids, cash_out, cash_in)
    ask = transfer_ask(gs, target_pid)
    if value < ask:
        return False, (
            f"{seller.name} reject the package — about {ask - value:,} cr "
            "short of value"
        )
    if seller.balance < cash_in:
        return False, f"{seller.name} can't fund the cash-back in this deal"
    return execute_package(gs, target_pid, buyer_id, out_pids, cash_out, cash_in)


def user_bid(gs: GameState, pid: str) -> tuple[bool, str]:
    """The acting manager buys a contracted player at the seller's ask. A bid
    for an AI org's player executes instantly; a bid for ANOTHER human's player
    lands on that manager's desk as a transfer offer they must accept."""
    buyer_id = gs.acting_team_id
    if gs.phase == "playoffs" and gs.is_human(buyer_id):
        return False, "rosters are locked during the playoffs"
    seller_id = team_of(gs, pid)
    if seller_id is None:
        return False, "player is a free agent — sign them instead"
    if seller_id == buyer_id:
        return False, "that's your own player"
    ask = transfer_ask(gs, pid)
    team = gs.teams[buyer_id]
    p = gs.players[pid]
    if team.balance < ask + asking_salary(p) * 8:
        return False, f"need {ask + asking_salary(p) * 8:,} cr to cover fee + wages"
    if gs.is_human(seller_id):
        if any(o.player_id == pid and o.to_team == buyer_id for o in gs.transfer_offers):
            return False, "you already have a bid in for that player"
        gs.transfer_offers.append(
            TransferOffer(
                player_id=pid,
                from_team=seller_id,
                to_team=buyer_id,
                fee=ask,
                expires_week=gs.week + 2,
            )
        )
        return True, f"bid sent to {gs.teams[seller_id].name} for {p.handle}"
    return execute_transfer(gs, pid, buyer_id, ask)


def respond_offer(
    gs: GameState, player_id: str, accept: bool, to_team: str | None = None
) -> tuple[bool, str]:
    """The acting manager (the SELLER) answers a bid for one of their players.
    Only offers whose `from_team` is the acting manager can be resolved here, so
    in a shared world a rival can never accept/decline a bid that isn't theirs.
    `to_team` disambiguates when several buyers have bid for the same player."""
    seller_id = gs.acting_team_id
    candidates = [
        o
        for o in gs.transfer_offers
        if o.player_id == player_id
        and o.from_team == seller_id
        and (to_team is None or o.to_team == to_team)
    ]
    if not candidates:
        return False, "no live offer for that player"
    # Deterministic pick when the buyer is unspecified and several exist.
    offer = min(candidates, key=lambda o: o.to_team)
    # Rosters lock in the playoffs: a human seller can't complete a sale (they'd
    # drop a player they then can't replace under the advance gate). Accepting is
    # refused and the offer stays live; declining is still allowed.
    if accept and gs.phase == "playoffs" and gs.is_human(seller_id):
        return False, "rosters are locked during the playoffs"
    gs.transfer_offers = [o for o in gs.transfer_offers if o is not offer]
    p = gs.players[player_id]
    if not accept:
        # Mercenaries wanted the move; everyone else shrugs.
        if "mercenary" in p.personality_tags:
            p.morale = round(max(0.0, p.morale - 4.0), 1)
            gs.push_news(f"{p.handle} wanted the {gs.teams[offer.to_team].name} move.")
        return True, f"declined {gs.teams[offer.to_team].name}'s bid for {p.handle}"
    if offer.offer_player_ids or offer.cash_to_buyer:
        return execute_package(
            gs,
            player_id,
            offer.to_team,
            offer.offer_player_ids,
            offer.cash_to_seller,
            offer.cash_to_buyer,
        )
    return execute_transfer(gs, player_id, offer.to_team, offer.fee)


def ai_transfer_window(gs: GameState, gd, rng: np.random.Generator) -> None:
    """Weekly AI transfer activity: a couple of orgs go shopping. Tier-1
    money raids tier-2 breakouts (the promotion pipeline) and makes the
    occasional lateral move; bids for user players land on the user's
    desk instead of resolving."""
    # Expire stale offers first.
    gs.transfer_offers = [
        o for o in gs.transfer_offers if o.expires_week > gs.week
    ]
    if gs.phase != "regular":
        return
    moves = 0
    buyers = sorted(
        (t for t in gs.teams.values() if t.tier == 1 and not gs.is_human(t.id)),
        key=lambda t: t.id,
    )
    for buyer in buyers:
        if moves >= 2:
            break
        if rng.random() > 0.15:
            continue
        roster = gs.roster(buyer.id)
        if len(roster) < ROSTER_SIZE:
            continue  # holes get filled from free agency, not transfers
        weakest_q = min(player_quality(p) for p in roster)
        best: tuple[float, int, str, str] | None = None
        for seller in sorted(gs.teams.values(), key=lambda t: t.id):
            if seller.id == buyer.id:
                continue
            for pid in seller.player_ids:
                p = gs.players[pid]
                q = player_quality(p)
                upgrade = q - weakest_q
                # Tier-2 targets: buy the future, not just the present.
                if seller.tier == 2:
                    upgrade += max(0.0, development.potential_of(p) - q) * 0.5
                if upgrade < 5.0:
                    continue
                fee = transfer_ask(gs, pid)
                if buyer.balance < fee + asking_salary(p) * 10:
                    continue
                key = (upgrade, -fee, pid, seller.id)
                if best is None or key > (best[0], -best[1], best[2], best[3]):
                    best = (upgrade, fee, pid, seller.id)
        if best is None:
            continue
        _, fee, pid, seller_id = best
        if gs.is_human(seller_id):
            if any(o.player_id == pid for o in gs.transfer_offers):
                continue
            gs.transfer_offers.append(
                TransferOffer(
                    player_id=pid,
                    from_team=seller_id,
                    to_team=buyer.id,
                    fee=fee,
                    expires_week=gs.week + 2,
                )
            )
            gs.push_news(
                f"{buyer.name} bid {fee:,} cr for {gs.players[pid].handle}."
            )
        else:
            execute_transfer(gs, pid, buyer.id, fee)
        moves += 1
