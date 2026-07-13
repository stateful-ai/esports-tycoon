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

from esports_sim.manager import (
    chronicle, development, economy, market_history, memories, relationships,
)
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
# Churn damping: an AI org gives a new arrival this long before they can be
# auto-dropped for the next shiny thing (poach swaps, buyer auto-release).
NEW_SIGNING_PROTECT_WEEKS = 12
# The AI transfer window stays quiet while the season settles.
TRANSFER_QUIET_WEEKS = 4


def market_window_status(gs: GameState) -> dict[str, object]:
    """The shared roster calendar. Free-agent signings and contracted-player
    moves use the same opening and mid-split windows; renewals remain open all
    year. An under-five roster always receives an emergency exception."""
    if gs.phase == "offseason":
        return {
            "open": True, "kind": "offseason", "label": "Offseason market",
            "detail": "All signings and transfers are open.",
        }
    if gs.phase == "playoffs":
        return {
            "open": False, "kind": "roster_lock", "label": "Tournament lock",
            "detail": "Playoff rosters are frozen until the offseason.",
        }
    last_week = max(
        (f.week for f in gs.fixtures if f.stage == "regular" and f.tier == 1),
        default=max(gs.week, 7),
    )
    opening_end = min(TRANSFER_QUIET_WEEKS + 1, last_week)
    mid_start = max(opening_end + 1, last_week // 2)
    mid_end = min(last_week, mid_start + 1)
    if gs.week <= opening_end:
        return {
            "open": True, "kind": "opening", "label": "Opening window",
            "detail": f"Closes after week {opening_end}.",
            "closes_week": opening_end,
        }
    if mid_start <= gs.week <= mid_end:
        return {
            "open": True, "kind": "mid_split", "label": "Mid-split window",
            "detail": f"Final roster moves close after week {mid_end}.",
            "closes_week": mid_end,
        }
    next_open = mid_start if gs.week < mid_start else None
    detail = (
        f"Closed until the mid-split window in week {next_open}."
        if next_open is not None
        else "The transfer deadline has passed; only emergency free agents are available."
    )
    return {
        "open": False, "kind": "closed", "label": "Window closed",
        "detail": detail, "next_open_week": next_open,
    }


def market_move_allowed(
    gs: GameState, team_id: str, *, emergency_ok: bool = False
) -> tuple[bool, str]:
    status = market_window_status(gs)
    if bool(status["open"]):
        return True, ""
    if emergency_ok and len(gs.teams[team_id].player_ids) < ROSTER_MIN:
        return True, "emergency roster exception"
    return False, str(status["detail"])


def roster_cap(gs: GameState, team_id: str) -> int:
    """How many players this org may carry. Everyone may hold a bench up to
    ROSTER_MAX — for AI orgs that headroom only ever fills through trades
    (their weekly market logic still targets the lean ROSTER_SIZE and never
    signs above it), so a 2-for-1 package no longer bounces off a full AI
    five while their economy stays effectively unchanged; surplus fringe
    players shed naturally as their contracts lapse."""
    return ROSTER_MAX


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
    allowed, why = market_move_allowed(gs, team_id, emergency_ok=True)
    if not allowed:
        return False, why
    if player_id not in gs.free_agent_ids:
        return False, "player is not a free agent"
    veto = relationships.signing_veto(gs, player_id, team_id)
    if veto:
        return False, veto
    cap = roster_cap(gs, team_id)
    if len(team.player_ids) >= cap:
        return False, f"roster is full ({cap}); release someone first"
    p = gs.players[player_id]
    ask = asking_salary(p)
    if team.balance < ask * 8:
        return False, f"need {ask * 8:,} cr in the bank to cover the deal"
    return True, ""


def _apply_contract_terms(
    gs: GameState, team_id: str, p: Player, terms: dict | None
) -> None:
    """Persist a negotiated contract and reflect its squad promise in the
    default lineup. AI/default contracts use the league-standard split and
    protection, preserving parity with human negotiation."""
    terms = terms or {}
    p.stream_revenue_share = float(np.clip(
        terms.get("stream_share", 70) / 100.0, 0.0, 1.0
    ))
    p.release_fee = max(0, int(terms.get("release_fee", p.salary * SEVERANCE_WEEKS)))
    p.no_transfer_clause = bool(terms.get("no_transfer", False))
    role = str(terms.get("role", "starter" if len(gs.teams[team_id].player_ids) < 5 else "bench"))
    p.roster_role = role if role in ("starter", "bench", "academy") else "bench"
    if "buyout" in terms:
        p.buyout_clause = max(0, int(terms["buyout"]))
    elif gs.teams[team_id].tier != 2:
        p.buyout_clause = 0
    team = gs.teams[team_id]
    lineup = [pid for pid in team.lineup_ids if pid != p.id and pid in team.player_ids]
    if p.roster_role == "starter":
        supporting = sorted(
            lineup, key=lambda pid: (-player_quality(gs.players[pid]), pid)
        )[:4]
        lineup = supporting + [p.id]
    team.lineup_ids = lineup


def seed_existing_contract_terms(
    gs: GameState, team_id: str, p: Player, role: str
) -> None:
    """Give an opening-world player a plausible complete contract. Pure and
    draw-free: the authored roster, salary, audience and club tier are the
    inputs. Existing players never receive a no-transfer clause."""
    team = gs.teams[team_id]
    role = role if role in ("starter", "bench", "academy") else "bench"
    p.roster_role = role
    audience_bonus = min(15, p.followers // 250_000)
    personality_bonus = 5 if "streamer" in p.personality_tags else 0
    role_share = {"starter": 70, "bench": 68, "academy": 66}[role]
    keep_pct = int(np.clip(
        role_share + audience_bonus + personality_bonus, 65, 90
    ))
    p.stream_revenue_share = keep_pct / 100.0
    release_weeks = {"starter": 12, "bench": 8, "academy": 4}[role]
    if p.age >= 28:
        release_weeks += 2
    p.release_fee = max(1_000, int(round(
        p.salary * release_weeks / 1000
    ) * 1000))
    mult = (
        {"starter": 2.2, "bench": 1.6, "academy": 1.25}[role]
        if team.tier == 2
        else {"starter": 3.0, "bench": 2.2, "academy": 1.6}[role]
    )
    p.buyout_clause = max(15_000, int(round(
        transfer_value(p) * mult / 1000
    ) * 1000))
    p.no_transfer_clause = False


def sign_player(
    gs: GameState, team_id: str, player_id: str, weeks: int = 40,
    salary: int | None = None, *, contract_terms: dict | None = None,
) -> tuple[bool, str]:
    """`salary` overrides the default asking-salary deal — the negotiated
    number (see open_negotiation / negotiate_offer). AI callers leave it
    None and pay the ask, exactly as before."""
    ok, why = can_sign(gs, team_id, player_id)
    if not ok:
        return False, why
    team = gs.teams[team_id]
    p = gs.players[player_id]
    negotiated_salary = asking_salary(p) if salary is None else max(800, int(salary))
    if team.balance < negotiated_salary * 8:
        return False, (
            f"need {negotiated_salary * 8:,} cr in the bank to cover the negotiated deal"
        )
    p.salary = negotiated_salary
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    _apply_contract_terms(gs, team_id, p, contract_terms)
    p.morale = min(100.0, p.morale + 8.0)
    p.tenure_weeks = 0  # fresh club, fresh loyalty clock
    team.player_ids.append(player_id)
    gs.free_agent_ids.remove(player_id)
    if team.captain_id is None:
        team.captain_id = player_id
    gs.push_news(f"{team.name} sign {p.handle} ({p.playstyle}) for {p.salary:,}/wk.")
    chronicle.record(
        gs, "signing",
        f"{team.name} sign {p.handle}.",
        team_id=team_id,
        player_id=player_id,
    )
    _record_value_decision(gs, "sign", "completed", player_id, team_id,
                           context="buy", reason="free-agent signing")
    return True, f"signed {p.handle} at {p.salary:,}/wk for {p.contract_weeks_left} weeks"


def release_player(gs: GameState, team_id: str, player_id: str) -> tuple[bool, str]:
    allowed, why = market_move_allowed(gs, team_id)
    if not allowed:
        return False, why
    team = gs.teams[team_id]
    if player_id not in team.player_ids:
        return False, "player is not on this roster"
    p = gs.players[player_id]
    effects = _departure_consequences(gs, team_id, player_id)
    _record_value_decision(gs, "release", "completed", player_id, team_id,
                           reason="roster release", effects=effects)
    severance = p.release_fee or p.salary * SEVERANCE_WEEKS
    team.balance -= severance
    relationships.on_departure(gs, player_id, team_id)
    team.player_ids.remove(player_id)
    team.lineup_ids = [pid for pid in team.lineup_ids if pid != player_id]
    if team.captain_id == player_id:
        team.captain_id = team.player_ids[0] if team.player_ids else None
    p.contract_weeks_left = 0
    p.morale = max(0.0, p.morale - 15.0)
    p.tenure_weeks = 0
    gs.free_agent_ids.append(player_id)
    gs.push_news(f"{team.name} release {p.handle} (severance {severance:,} cr).")
    chronicle.record(
        gs, "release",
        f"{team.name} release {p.handle}.",
        team_id=team_id,
        player_id=player_id,
    )
    return True, f"released {p.handle}, severance {severance:,} cr"


def renew_contract(
    gs: GameState, team_id: str, player_id: str, weeks: int = 48,
    salary: int | None = None, *, contract_terms: dict | None = None,
) -> tuple[bool, str]:
    """`salary` overrides the auto-computed number with a NEGOTIATED one
    (see open_negotiation / negotiate_offer). AI renewals leave it None —
    the pre-negotiation formula, unchanged."""
    team = gs.teams[team_id]
    if player_id not in team.player_ids:
        return False, "player is not on this roster"
    veto = relationships.renewal_veto(gs, player_id, team_id)
    if veto:
        return False, veto
    p = gs.players[player_id]
    # Memory moves the table a nudge: a player whose career was MADE here
    # (debut, milestones, a title run) re-signs a shade under market; one
    # this org once released wants it back in salary. +/-10% at the caps.
    # (Also warms the re-signing morale bump below, negotiated or not.)
    from esports_sim.manager import memories

    loyalty = memories.loyalty_bias(gs, player_id, team_id)
    if salary is not None:
        new_salary = max(800, int(salary))
    else:
        new_salary = max(asking_salary(p), int(p.salary * 1.1 / 100) * 100)
        new_salary = max(800, int(new_salary * (1.0 - loyalty / 100.0) / 100) * 100)
    p.salary = new_salary
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    # A direct/AI renewal preserves the player's existing negotiated clauses
    # and role. Only an explicit negotiation package rewrites those promises.
    if contract_terms is not None:
        _apply_contract_terms(gs, team_id, p, contract_terms)
    p.morale = min(100.0, p.morale + 5.0 + loyalty * 0.2)
    gs.push_news(f"{p.handle} re-signs with {team.name} at {new_salary:,}/wk.")
    chronicle.record(
        gs, "renewal",
        f"{p.handle} re-signs with {team.name}.",
        team_id=team_id,
        player_id=player_id,
    )
    _record_value_decision(gs, "renew", "completed", player_id, team_id,
                           reason="contract renewed")
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
    allowed, why = market_move_allowed(gs, team_id)
    if not allowed:
        return False, why
    if drop_id not in team.player_ids:
        return False, "the player to drop is not on this roster"
    if sign_id not in gs.free_agent_ids:
        return False, "the player to sign is not a free agent"
    if sign_id == drop_id:
        return False, "cannot swap a player for themselves"
    fa = gs.players[sign_id]
    dropped = gs.players[drop_id]
    severance = dropped.release_fee or dropped.salary * SEVERANCE_WEEKS
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
    # Negotiation deadlines are real calendar pressure. Expire them before the
    # roster contract pass so the inbox/news for this tick reflects the missed
    # table even if the player's underlying deal also reaches zero.
    for owner in sorted(gs.negotiations_by):
        live = gs.negotiations_by[owner]
        for pid in sorted(list(live)):
            neg = live[pid]
            if neg.deadline_week and gs.week > neg.deadline_week:
                player = gs.players.get(pid)
                del live[pid]
                if player is not None:
                    if neg.kind == "renew":
                        player.morale = round(max(0.0, player.morale - 3.0), 1)
                    gs.push_private_news(
                        f"Contract talks with {player.handle} expire; their agent "
                        "moves on to other options.",
                        owner=owner,
                    )
    for tid in sorted(gs.teams):
        team = gs.teams[tid]
        is_ai = not gs.is_human(tid)
        for pid in list(team.player_ids):
            p = gs.players[pid]
            p.contract_weeks_left = max(0, p.contract_weeks_left - 1)
            p.tenure_weeks += 1  # the loyalty clock (resets on any move)
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
                replacement_bar = transfer_value(p, ca=52.0, pa=55.0)
                wants = (
                    retention_value(gs, tid, pid) >= replacement_bar
                    or len(team.player_ids) <= ROSTER_SIZE
                )
                if affordable and wants and rng.random() < 0.6:
                    renew_contract(gs, tid, pid, weeks=int(rng.integers(32, 64)))
            if p.contract_weeks_left == 0:
                effects = _departure_consequences(gs, tid, pid)
                _record_value_decision(
                    gs, "expire", "expired", pid, tid,
                    reason="contract reached zero without renewal", effects=effects,
                )
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
                if (
                    team.balance >= asking_salary(cand) * 8
                    and relationships.signing_veto(gs, cand.id, tid) is None
                ):
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
    chronicle.mark_debut_pending(gs, pid)
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
    if not bool(market_window_status(gs)["open"]):
        return
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
            if relationships.signing_veto(gs, cand.id, tid) is not None:
                continue
            if len(team.player_ids) < ROSTER_SIZE:
                if team.balance >= asking_salary(cand) * 8:
                    suitors.append((tid, None))
                continue
            same = [
                gs.players[pid]
                for pid in team.player_ids
                if str(gs.players[pid].playstyle) == str(cand.playstyle)
                # Churn damping: fresh arrivals get a real look before the
                # org flips them for the next shiny free agent.
                and gs.players[pid].tenure_weeks >= NEW_SIGNING_PROTECT_WEEKS
            ]
            if not same:
                continue
            weakest = min(
                same, key=lambda p: (retention_value(gs, tid, p.id), p.id)
            )
            # Reserve the dropped player's severance too: release_player
            # charges it before sign_player re-checks affordability, so
            # without this the swap can strand the roster at four players.
            severance = weakest.release_fee or weakest.salary * SEVERANCE_WEEKS
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


def transfer_value(p: Player, ca: float | None = None, pa: float | None = None) -> int:
    """What a contracted player is worth on the market. Youth with a big
    CA->PA gap carries a premium; expiring contracts sell at a discount
    (why pay full freight for someone who walks in two months?).
    `ca`/`pa` override the true numbers so a viewer can price a player at
    their PERCEIVED ability (see perceived_value)."""
    ca = player_quality(p) if ca is None else ca
    pa = development.potential_of(p) if pa is None else pa
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


def _hash01(*parts: object) -> float:
    """Stable uniform in [0, 1) — draw-free, never Python hash()."""
    import hashlib

    b = hashlib.blake2b("|".join(str(x) for x in parts).encode(), digest_size=8)
    return int.from_bytes(b.digest(), "big") / 2**64


# How far (in ability points) an org's read of a RIVAL player can sit from
# the truth. Human broad/deep scouting shrinks it toward a player-specific
# residual floor; AI orgs carry the full blur — they run their own flawed
# models.
VALUATION_BLUR = 6.0


def scouting_progress_for(gs: GameState, viewer_id: str, p: Player) -> float:
    """Best information depth VIEWER has on ``p`` across broad and deep work."""
    progress = gs.scout_progress_by.get(viewer_id, {})
    owner = team_of(gs, p.id)
    broad_key = owner if owner is not None else "market"
    return max(
        0.0,
        min(
            1.0,
            max(
                progress.get(broad_key, 0.0),
                progress.get(f"player:{p.id}", 0.0),
            ),
        ),
    )


def scout_uncertainty_floor(gs: GameState, viewer_id: str, p: Player) -> float:
    """Residual fraction of fog left at a 100% information book.

    External evaluation never becomes own-roster knowledge.  The floor varies
    stably by player and rises for cross-region players, Challengers players,
    and free agents whose day-to-day context is harder to observe.
    """
    owner = team_of(gs, p.id)
    if owner == viewer_id:
        return 0.0
    floor = 0.14 + 0.08 * _hash01(gs.seed, viewer_id, p.id, "scout-opacity")
    viewer = gs.teams.get(viewer_id)
    observed = gs.teams.get(owner) if owner else None
    if observed is None:
        floor += 0.14
    else:
        if viewer is not None and observed.region != viewer.region:
            floor += 0.10
        if observed.tier == 2:
            floor += 0.12
    return min(0.50, floor)


def scout_uncertainty_factor(gs: GameState, viewer_id: str, p: Player) -> float:
    """Fog multiplier after applying information depth and its residual floor."""
    progress = scouting_progress_for(gs, viewer_id, p)
    floor = scout_uncertainty_floor(gs, viewer_id, p)
    return floor + (1.0 - floor) * (1.0 - progress)


def perceived_quality(gs: GameState, viewer_id: str | None, p: Player) -> float:
    """How good VIEWER thinks `p` is. Own players are known exactly; anyone
    else carries a stable per-(viewer, player) bias — two orgs genuinely
    disagree about the same player, and that disagreement is per-save
    deterministic (seed + ids), not a dice roll."""
    q = player_quality(p)
    if viewer_id is None:
        return q
    owner = team_of(gs, p.id)
    if owner == viewer_id:
        return q
    blur = VALUATION_BLUR
    if gs.is_human(viewer_id):
        blur *= scout_uncertainty_factor(gs, viewer_id, p)
    bias = (_hash01(gs.seed, viewer_id, p.id, "val") * 2.0 - 1.0) * blur
    return q + bias


def perceived_value(gs: GameState, viewer_id: str | None, p: Player) -> int:
    """`transfer_value` through the viewer's eyes: their (possibly wrong)
    read of both current ability and ceiling, plus what the player's audience
    is worth to THEM. The asymmetry between two orgs' perceived values is what
    makes a trade a bargain — or a fleecing."""
    q = player_quality(p)
    pq = perceived_quality(gs, viewer_id, p)
    # The same bias colours their read of the ceiling.
    ppa = max(pq, development.potential_of(p) + (pq - q))
    base = transfer_value(p, ca=pq, pa=ppa)
    # A player's streaming revenue is worth more to a viewer for whom it is a
    # bigger slice of income — so a cash-rich club sees a smaller premium than
    # a hungry one on the exact same audience (the asymmetry that makes these
    # trades live). No viewer (a neutral market quote) => intrinsic value only.
    if viewer_id is not None and viewer_id in gs.teams:
        share = economy.player_stream_income(p) / max(
            economy.org_weekly_income(gs, viewer_id), 1
        )
        prem = min(STREAM_PERC_CAP, share * STREAM_PERC_K)
        base = int(round(base * (1.0 + prem) / 1000) * 1000)
    return base


def _round_value(value: float) -> int:
    return int(round(value / 1000.0) * 1000)


def org_player_valuation(
    gs: GameState, team_id: str, pid: str, context: str = "retain"
) -> dict[str, object]:
    """How one org values a player, with an auditable additive breakdown.

    ``retain``/``sell`` include club-specific attachment and replacement
    pain. ``buy`` uses the buyer's imperfect scouting read and only portable
    fame/revenue. Keeping these contexts separate is intentional: a pillar can
    be worth far more to their home than any rational rival should pay.
    """
    p = gs.players[pid]
    own = team_of(gs, pid) == team_id and context != "buy"
    base = transfer_value(p) if own else perceived_value(gs, team_id, p)
    parts: dict[str, int] = {"base value": base}
    tags = set(p.personality_tags)
    badge_ids = {b.id for b in p.badges}

    if own:
        roster = sorted(gs.roster(team_id), key=lambda q: (-player_quality(q), q.id))
        rank = next((i for i, q in enumerate(roster) if q.id == pid), len(roster))
        if rank == 0:
            parts["sporting importance"] = _round_value(base * 0.50)
        elif rank == 1:
            parts["sporting importance"] = _round_value(base * 0.20)
        replacements = [q for q in roster if q.id != pid and q.playstyle == p.playstyle]
        gap = player_quality(p) - max((player_quality(q) for q in replacements), default=35.0)
        if gap > 4:
            parts["replacement scarcity"] = _round_value(
                base * min(0.30, 0.08 + gap / 80.0)
            )

    fame = 0.0
    if "superstar" in badge_ids:
        fame += 0.28
    if "star_player" in tags:
        fame += 0.18
    if fame:
        parts["superstar status"] = _round_value(base * min(0.35, fame))

    # A season of actual org streaming income is a concrete portable asset.
    stream_asset = min(base * 0.40, economy.player_stream_income(p) * 52)
    if stream_asset >= 1000:
        parts["audience revenue"] = _round_value(stream_asset)
    if own:
        dependence = stream_ask_premium(gs, pid, team_id)
        if dependence > 0:
            parts["revenue dependence"] = _round_value(base * dependence)

    if "fan_favorite" in tags:
        parts["supporter favorite"] = _round_value(base * (0.35 if own else 0.12))

    if own:
        pillar = 0.0
        if p.tenure_weeks >= 156:
            pillar += 0.30
        elif p.tenure_weeks >= 104:
            pillar += 0.22
        elif p.tenure_weeks >= 52:
            pillar += 0.12
        if gs.teams[team_id].captain_id == pid:
            pillar += 0.20
        loyalty = max(0.0, memories.loyalty_bias(gs, pid, team_id))
        pillar += loyalty / 100.0
        if pillar:
            parts["club pillar"] = _round_value(base * min(0.55, pillar))

    total = min(sum(parts.values()), _round_value(base * 3.5))
    # If the cap trims an extreme icon, keep the components reconcilable.
    trim = sum(parts.values()) - total
    if trim > 0:
        parts["valuation cap"] = -trim
    ratio = total / max(base, 1)
    if context == "buy":
        stance = "target"
    elif ratio >= 2.30:
        stance = "not for sale"
    elif ratio >= 1.75:
        stance = "club pillar"
    elif ratio >= 1.30:
        stance = "reluctant"
    else:
        stance = "available"
    return {
        "value": int(total), "market_value": int(base),
        "stance": stance, "components": parts,
    }


def retention_value(gs: GameState, team_id: str, pid: str) -> int:
    return int(org_player_valuation(gs, team_id, pid, "retain")["value"])


def _record_value_decision(
    gs: GameState, kind: str, outcome: str, pid: str, actor: str,
    *, counterparty: str = "", context: str = "retain", fee: int = 0,
    reason: str = "", effects: dict[str, int] | None = None,
) -> None:
    view = org_player_valuation(gs, actor, pid, context)
    market_history.record(
        gs, kind, outcome, pid, actor_team_id=actor,
        counterparty_team_id=counterparty, context=context,
        stance=str(view["stance"]), fee=fee, salary=gs.players[pid].salary,
        market_value=int(view["market_value"]), org_value=int(view["value"]),
        components=view["components"], reason=reason,
        effects=effects,
    )


def _departure_consequences(gs: GameState, team_id: str, pid: str) -> dict[str, int]:
    """Apply bounded supporter and locker-room cost before a player leaves.
    Ordinary departures are neutral; icons make an org feel their absence."""
    view = org_player_valuation(gs, team_id, pid, "retain")
    stance = str(view["stance"])
    if stance not in ("club pillar", "not for sale"):
        return {"fans_lost": 0, "sentiment_lost": 0}
    p = gs.players[pid]
    team = gs.teams[team_id]
    severe = stance == "not for sale"
    fan_rate = 0.035 if severe else 0.015
    if "fan_favorite" in p.personality_tags:
        fan_rate += 0.015
    fans_lost = min(75_000, int(team.fan_count * fan_rate))
    team.fan_count = max(0, team.fan_count - fans_lost)
    sentiment_lost = 6 if severe else 3
    gs.team_sentiment[team_id] = max(
        0.0, round(gs.sentiment(team_id) - sentiment_lost, 1)
    )
    morale_hit = 5.0 if severe else 2.0
    for teammate_id in team.player_ids:
        if teammate_id != pid:
            mate = gs.players[teammate_id]
            mate.morale = max(0.0, round(mate.morale - morale_hit, 1))
    return {"fans_lost": fans_lost, "sentiment_lost": sentiment_lost}


def valuation_opinions(
    gs: GameState, viewer_id: str | None, p: Player
) -> dict[str, int]:
    """Coach/analyst reads of a player, centred on the org's established
    perceived value.  Staff quality narrows disagreement; stable id hashes
    decide which evaluator is higher.  The consensus deliberately remains the
    number used by package evaluation, so the trade-room bar and AI decisions
    cannot drift apart."""
    consensus = perceived_value(gs, viewer_id, p)
    hired = gs.staff_by.get(viewer_id or "", {})
    coach_q = hired.get("coach").quality if hired.get("coach") else 50.0
    analyst_q = hired.get("analyst").quality if hired.get("analyst") else 50.0
    quality = (coach_q + analyst_q) / 2.0
    spread = 0.035 + (100.0 - quality) / 100.0 * 0.065
    direction = 1.0 if _hash01(gs.seed, viewer_id, p.id, "staff-value") >= 0.5 else -1.0
    delta = int(round(consensus * spread * direction / 1000) * 1000)
    return {
        "coach": max(0, consensus + delta),
        "analyst": max(0, consensus - delta),
        "consensus": consensus,
    }

# Streaming as a trade-value lever (GDD: audiences are assets). A player who
# generates a big share of their org's income is worth more to that org than
# their play alone — the more so when the club is cash-strapped and leans on
# the revenue. The buyer, in turn, values that audience relative to ITS OWN
# books, so a rich club sees a smaller premium than a poor one: a strapped
# seller prices high, a flush buyer won't match it, and the gap is where the
# interesting deals live. All deterministic (followers/load/balances are all
# state) and campaign-only — the match gates never price a transfer.
STREAM_ASK_PREMIUM_K = 2.0        # owner ask premium per unit of income-share
STREAM_ASK_PREMIUM_CAP = 0.6      # ...capped at +60% of market value
STREAM_STRAPPED_CASH = 250_000    # balance below which a club leans harder
STREAM_CASH_MAX_AMP = 2.0         # ...up to a 2x amplifier when broke / in the red
STREAM_PERC_K = 1.5               # buyer premium per unit of THEIR income-share
STREAM_PERC_CAP = 0.4             # ...capped at +40%


def _cash_amp(balance: int) -> float:
    """A club poorer than STREAM_STRAPPED_CASH values steady revenue more:
    1.0 at the threshold, ramping up to STREAM_CASH_MAX_AMP when broke or in
    the red."""
    if balance >= STREAM_STRAPPED_CASH:
        return 1.0
    short = (STREAM_STRAPPED_CASH - balance) / STREAM_STRAPPED_CASH
    return float(min(STREAM_CASH_MAX_AMP, 1.0 + short))


def stream_ask_premium(gs: GameState, pid: str, owner_id: str) -> float:
    """The fractional bump `transfer_ask` adds for a player's streaming
    revenue: the share of the owner's income it represents, amplified when the
    club is cash-strapped, capped. 0 when the player barely streams."""
    share = economy.player_stream_income(gs.players[pid]) / max(
        economy.org_weekly_income(gs, owner_id), 1
    )
    return min(
        STREAM_ASK_PREMIUM_CAP,
        share * STREAM_ASK_PREMIUM_K * _cash_amp(gs.teams[owner_id].balance),
    )


def transfer_ask(gs: GameState, pid: str) -> int:
    """Seller's price: market value, plus a scarcity premium when the
    player is the seller's best (nobody sells their franchise cheap), a
    loyalty premium — a tenured, in-form fixture of the club costs real
    money to pry away — and a streaming premium when the player is a big
    slice of the club's income (bigger still for a cash-strapped org that
    can't afford to lose the revenue)."""
    seller_id = team_of(gs, pid)
    if seller_id is None:
        return transfer_value(gs.players[pid])
    return int(org_player_valuation(gs, seller_id, pid, "sell")["value"])


def transfer_ask_breakdown(gs: GameState, pid: str) -> list[dict[str, int | str]]:
    """Currency deltas that reconcile exactly to ``transfer_ask``."""
    p = gs.players[pid]
    seller_id = team_of(gs, pid)
    if seller_id is None:
        return [{"label": "base value", "delta": transfer_value(p)}]
    view = org_player_valuation(gs, seller_id, pid, "sell")
    return [
        {"label": label, "delta": delta}
        for label, delta in view["components"].items()
    ]
    # Loyalty: the club digs in for players who've been part of the
    # furniture — more so when they're playing well right now.
    # Streaming: a revenue engine costs more to prise away, cash-amplified.


# ---------------------------------------------------------------------------
# Contract negotiation: renewals and free-agent signings are a TABLE, not a
# button. The player opens with demands, concedes a little per round, runs
# out of patience after a few, and walks entirely on an insulting number.
# Deterministic end to end: demands and concessions are pure functions of
# GameState + stable hashes — no rng at the table.

NEGOTIATION_MAX_ROUNDS = 3  # rejected offers before they walk
NEGOTIATION_INSULT_RATIO = 0.70  # offer under this share of the ask = walkout
NEGOTIATION_COOLDOWN_RENEW = 6  # weeks before a walked renewal talks again
NEGOTIATION_COOLDOWN_SIGN = 4  # ...and a walked free agent
# How far they move toward your last offer with each counter.
NEGOTIATION_CONCESSION = 0.35


def _negotiation_leverage(
    gs: GameState, pid: str, kind: str
) -> tuple[int, int, int, list[str]]:
    """Snapshot alternatives and club interest so leverage is visible and
    causally changes patience and concessions."""
    p = gs.players[pid]
    team = gs.teams[gs.acting_team_id]
    q = player_quality(p)
    leverage = 42.0 + (q - 55.0) * 1.15
    reasons: list[str] = []
    if p.form >= 60:
        leverage += 8.0
        reasons.append("strong recent form")
    if p.followers >= 300_000:
        leverage += min(10.0, p.followers / 150_000)
        reasons.append("commercial pull")
    if kind == "renew" and p.contract_weeks_left <= 8:
        leverage += 12.0
        reasons.append("contract close to expiry")
    if q >= 72:
        reasons.append("elite market level")

    competing = 0
    ask = asking_salary(p)
    for rival in sorted(gs.teams.values(), key=lambda t: t.id):
        if rival.id == team.id or rival.tier != team.tier or rival.balance < ask * 10:
            continue
        weakest = min(
            (player_quality(x) for x in gs.roster(rival.id)), default=0.0
        )
        if q >= weakest + 3.0:
            competing += 1
    competing = min(3, competing)
    if competing:
        leverage += competing * 6.0
        reasons.append(
            f"{competing} credible alternative{'s' if competing != 1 else ''}"
        )

    interest = 45.0 + (team.reputation - 50.0) * 0.45
    if p.region == team.region:
        interest += 8.0
        reasons.append("regional fit")
    fit = relationships.locker_room_fit(gs, pid, team.id)
    interest += (float(fit["average"]) - 50.0) * 0.25
    if kind == "renew":
        interest += memories.loyalty_bias(gs, pid, team.id) * 0.6
        interest += min(10.0, p.tenure_weeks / 20.0)
        if p.morale < 45:
            interest -= 12.0
            reasons.append("unhappy at the club")
    interest_i = int(np.clip(round(interest), 5, 95))
    leverage -= (interest_i - 50) * 0.15
    return int(np.clip(round(leverage), 5, 95)), interest_i, competing, reasons


def negotiation_round_limit(neg) -> int:
    # The UI promise remains three formal offers. Leverage changes the deadline,
    # acceptance threshold, and concession rate rather than hiding a different
    # click budget behind the same negotiation room.
    return NEGOTIATION_MAX_ROUNDS


def contract_demands(gs: GameState, pid: str, kind: str) -> tuple[int, int]:
    """The player's OPENING ask: (salary/wk, contract weeks). Form and
    confidence inflate it; loyalty (memories) and long tenure soften a
    renewal; age shapes the term (kids take prove-it deals, veterans want
    security). A stable per-player-per-season hash adds texture so no two
    negotiations feel identical."""
    from esports_sim.manager import memories

    p = gs.players[pid]
    base = asking_salary(p)
    mult = 1.0
    if p.form >= 60:
        mult += 0.08
    if p.confidence >= 65:
        mult += 0.05
    if kind == "renew":
        # Renewals anchor on the current deal — nobody re-signs for less
        # than they're on without a reason.
        base = max(base, int(p.salary * 1.05))
        loyalty = memories.loyalty_bias(gs, pid, gs.acting_team_id)
        mult -= loyalty / 100.0 * 0.8
        if p.tenure_weeks >= 104:
            mult -= 0.05  # part of the furniture: friendlier table
        if p.morale <= 40:
            mult += 0.10  # unhappy: pay me to stay
    # Existing relationships travel with a player. A friendly reunion takes
    # a little heat out of the table; a frosty room makes the player charge
    # for the risk. Hard feuds are handled as vetoes before talks open.
    mult *= relationships.contract_fit_multiplier(gs, pid, gs.acting_team_id)
    jitter = (_hash01(gs.seed, pid, gs.season, "negsal") - 0.5) * 0.10
    salary = max(1_000, int(round(base * (mult + jitter) / 100) * 100))
    if p.age <= 20:
        weeks = 40  # prove-it: back at the table sooner
    elif p.age >= 27:
        weeks = 64  # security
    else:
        weeks = 52
    weeks += int((_hash01(gs.seed, pid, gs.season, "negwk") - 0.5) * 16)
    return salary, int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))


def contract_term_demands(gs: GameState, pid: str, kind: str) -> dict:
    """The rest of the player's opening position. Role drives the economic
    package: starters want top money and protection; young academy players
    accept less cash in exchange for a reachable pathway and a low buyout."""
    p = gs.players[pid]
    team = gs.teams[gs.acting_team_id]
    roster_q = sorted((player_quality(q) for q in gs.roster(team.id)), reverse=True)
    starter_cut = roster_q[4] if len(roster_q) >= 5 else 0.0
    q = player_quality(p)
    if q >= starter_cut or q >= 68:
        role = "starter"
    elif p.age <= 20 and q < 58:
        role = "academy"
    else:
        role = "bench"
    role_salary = {"starter": 1.15, "bench": 0.92, "academy": 0.72}[role]
    salary, weeks = contract_demands(gs, pid, kind)
    salary = max(1_000, int(round(salary * role_salary / 100) * 100))
    fame = min(20, int(p.followers / 100_000))
    stream_share = int(np.clip(70 + fame + (5 if "streamer" in p.personality_tags else 0), 55, 95))
    release_fee = int(round(salary * ({"starter": 12, "bench": 7, "academy": 4}[role]) / 1000) * 1000)
    value = transfer_value(p)
    buyout_mult = {"starter": 2.5, "bench": 1.8, "academy": 1.25}[role]
    buyout = int(round(value * buyout_mult / 1000) * 1000)
    no_transfer = role == "starter" and (q >= 78 or p.age >= 28)
    return {
        "salary": salary, "weeks": weeks, "stream_share": stream_share,
        "release_fee": release_fee, "buyout": buyout,
        "no_transfer": no_transfer, "role": role,
    }


def negotiation_kind(gs: GameState, pid: str) -> tuple[str | None, str]:
    """What kind of table this manager can open with `pid`: "renew" for
    their own roster, "sign" for a free agent, None otherwise."""
    if pid in gs.teams[gs.acting_team_id].player_ids:
        return "renew", ""
    if pid in gs.free_agent_ids:
        return "sign", ""
    return None, "player is under contract elsewhere — bid or buy out instead"


def can_open_negotiation(gs: GameState, pid: str) -> tuple[bool, str, str | None]:
    p = gs.players.get(pid)
    if p is None:
        return False, "unknown player", None
    kind, why = negotiation_kind(gs, pid)
    if kind is None:
        return False, why, None
    veto = (
        relationships.renewal_veto(gs, pid, gs.acting_team_id)
        if kind == "renew"
        else relationships.signing_veto(gs, pid, gs.acting_team_id)
    )
    if veto:
        return False, veto, kind
    if kind == "sign":
        allowed, why = market_move_allowed(
            gs, gs.acting_team_id, emergency_ok=True
        )
        if not allowed:
            return False, why, kind
    until = gs.talks_cooldown.get(pid, 0)
    if until > gs.week:
        return False, (
            f"{p.handle} isn't taking your calls after the last talks "
            f"collapsed (week {until})"
        ), kind
    return True, "", kind


def open_negotiation(gs: GameState, pid: str) -> tuple[bool, str, "object"]:
    """Sit down with a player (or return the live table). Returns
    (ok, why, Negotiation | None)."""
    from esports_sim.manager.state import Negotiation

    p = gs.players.get(pid)
    ok, why, kind = can_open_negotiation(gs, pid)
    if not ok:
        return False, why, None
    assert p is not None and kind is not None
    live = gs.negotiations.get(pid)
    if live is not None and live.kind == kind:
        if live.deadline_week and gs.week > live.deadline_week:
            del gs.negotiations[pid]
            return False, f"{p.handle}'s deadline passed; their agent closed talks", None
        return True, "", live
    terms = contract_term_demands(gs, pid, kind)
    leverage, interest, competing, reasons = _negotiation_leverage(gs, pid, kind)
    neg = Negotiation(
        player_id=pid, kind=kind,
        demand_salary=terms["salary"], demand_weeks=terms["weeks"],
        demand_stream_share=terms["stream_share"],
        demand_release_fee=terms["release_fee"],
        demand_buyout=terms["buyout"],
        demand_no_transfer=terms["no_transfer"],
        demand_role=terms["role"],
        leverage=leverage,
        interest=interest,
        competing_clubs=competing,
        deadline_week=gs.week + (2 if leverage >= 75 else 3 if leverage >= 45 else 4),
        leverage_reasons=reasons,
    )
    gs.negotiations[pid] = neg
    return True, "", neg


def negotiate_offer(
    gs: GameState, pid: str, salary: int, weeks: int, *,
    stream_share: int | None = None, release_fee: int | None = None,
    buyout: int | None = None, no_transfer: bool | None = None,
    role: str | None = None,
) -> tuple[str, str, "object"]:
    """Put an offer on the table. Returns (status, message, negotiation):
    status is "accepted" | "countered" | "collapsed" | "error".
    Acceptance weighs salary (mostly) and term fit; each rejection burns
    patience and softens their ask a little; an insulting number — or
    running out of rounds — collapses the talks with a cooldown (and a
    morale knock on a renewal: they know you tried to lowball them)."""
    neg = gs.negotiations.get(pid)
    if neg is None:
        return "error", "no talks are open with this player", None
    p = gs.players.get(pid)
    kind, why = negotiation_kind(gs, pid)
    if p is None or kind != neg.kind:
        del gs.negotiations[pid]
        return "error", "the situation changed — talks are off", None
    if neg.deadline_week and gs.week > neg.deadline_week:
        del gs.negotiations[pid]
        return "collapsed", f"{p.handle}'s deadline passed; they pursue other options", None
    salary = max(0, int(salary))
    weeks = int(np.clip(int(weeks), MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    stream_share = int(np.clip(
        neg.demand_stream_share if stream_share is None else stream_share, 0, 100
    ))
    release_fee = max(0, int(
        neg.demand_release_fee if release_fee is None else release_fee
    ))
    buyout = max(0, int(neg.demand_buyout if buyout is None else buyout))
    no_transfer = neg.demand_no_transfer if no_transfer is None else bool(no_transfer)
    role = neg.demand_role if role is None else str(role)
    if role not in ("starter", "bench", "academy"):
        return "error", "unknown roster role", neg
    ratio = salary / max(neg.demand_salary, 1)
    term_gap = abs(weeks - neg.demand_weeks) / max(neg.demand_weeks, 1)
    # Overpaying can buy term flexibility (capped), and meeting their
    # number with a term in the same neighbourhood is simply a deal.
    stream_gap = (stream_share - neg.demand_stream_share) / 100.0
    release_ratio = min(release_fee / max(neg.demand_release_fee, 1), 1.25)
    buyout_score = min(neg.demand_buyout / max(buyout, 1), 1.25) if buyout else 1.25
    protection = 0.08 if no_transfer else (-0.08 if neg.demand_no_transfer else 0.0)
    role_gap = {"academy": 0, "bench": 1, "starter": 2}[role] - {
        "academy": 0, "bench": 1, "starter": 2
    }[neg.demand_role]
    score = (
        min(ratio, 1.15) - 0.18 * min(term_gap, 0.6)
        + 0.22 * stream_gap + 0.08 * (release_ratio - 1.0)
        + 0.08 * (buyout_score - 1.0) + protection + 0.10 * role_gap
    )
    exact_terms = (
        stream_share >= neg.demand_stream_share
        and release_fee >= neg.demand_release_fee
        and (buyout == 0 or buyout <= neg.demand_buyout)
        and (not neg.demand_no_transfer or no_transfer)
        and role == neg.demand_role
    )
    if ratio >= 1.0 and abs(weeks - neg.demand_weeks) <= 8 and exact_terms:
        score = 2.0  # their ask, their term (near enough): done

    def _collapse(msg: str) -> tuple[str, str, "object"]:
        del gs.negotiations[pid]
        cooldown = (
            NEGOTIATION_COOLDOWN_RENEW if neg.kind == "renew"
            else NEGOTIATION_COOLDOWN_SIGN
        )
        gs.talks_cooldown[pid] = gs.week + cooldown
        if neg.kind == "renew":
            p.morale = round(max(0.0, p.morale - 5.0), 1)
        return "collapsed", msg, None

    if ratio < NEGOTIATION_INSULT_RATIO:
        return _collapse(
            f"{p.handle}'s agent hangs up — that number was an insult. "
            "They won't talk to you for a while."
        )
    threshold = (
        0.97 - 0.02 * neg.rounds
        + (neg.leverage - 50) / 500.0
        - (neg.interest - 50) / 700.0
    )
    if score >= threshold:
        # Deal. Settle it through the normal channels with the NEGOTIATED
        # terms; the affordability rules still apply.
        if neg.kind == "renew":
            ok, msg = renew_contract(
                gs, gs.acting_team_id, pid, weeks=weeks, salary=salary,
                contract_terms={"stream_share": stream_share, "release_fee": release_fee,
                                "buyout": buyout, "no_transfer": no_transfer,
                                "role": role},
            )
        else:
            ok, msg = sign_player(
                gs, gs.acting_team_id, pid, weeks=weeks, salary=salary,
                contract_terms={"stream_share": stream_share, "release_fee": release_fee,
                                "buyout": buyout, "no_transfer": no_transfer,
                                "role": role},
            )
        if not ok:
            return "error", msg, neg  # e.g. can't afford it: table stays open
        del gs.negotiations[pid]
        gs.talks_cooldown.pop(pid, None)
        return "accepted", msg, None
    neg.rounds += 1
    round_limit = negotiation_round_limit(neg)
    if neg.rounds >= round_limit:
        return _collapse(
            f"{p.handle} is done negotiating — {round_limit} offers, no deal. "
            "They walk away from the table."
        )
    # Counter: concede toward the offer, never below it.
    concession = float(np.clip(
        NEGOTIATION_CONCESSION + (50 - neg.leverage) / 250.0,
        0.18, 0.52,
    ))
    neg.demand_salary = max(
        salary,
        int(round(
            (neg.demand_salary - (neg.demand_salary - salary) * concession)
            / 100
        ) * 100),
    )
    neg.demand_weeks = int(np.clip(
        round(neg.demand_weeks + (weeks - neg.demand_weeks) * 0.3),
        MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS,
    ))
    neg.demand_stream_share = round(
        neg.demand_stream_share + (stream_share - neg.demand_stream_share) * 0.25
    )
    neg.demand_release_fee = int(round(
        (neg.demand_release_fee + (release_fee - neg.demand_release_fee) * 0.25)
        / 1000
    ) * 1000)
    neg.demand_buyout = int(round(
        (neg.demand_buyout + (buyout - neg.demand_buyout) * 0.2) / 1000
    ) * 1000)
    left = round_limit - neg.rounds
    return "countered", (
        f"{p.handle} counters: {neg.demand_salary:,}/wk on "
        f"{neg.demand_weeks} weeks, {neg.demand_stream_share}% stream share, "
        f"{neg.demand_role} role ({left} more offer{'s' if left != 1 else ''} "
        "before they walk)."
    ), neg


def cancel_negotiation(gs: GameState, pid: str) -> None:
    """Walk away yourself — no cooldown, no hard feelings (you can reopen)."""
    gs.negotiations.pop(pid, None)


# ---------------------------------------------------------------------------
# Tier-2 buyout clauses: the promotion pipeline's fast lane


def buyout_fee(gs: GameState, pid: str) -> int | None:
    """The player's stored buyout clause. Opening-world contracts at every
    tier carry a role-scaled clause; legacy tier-2 deals without a stored
    value retain the old deterministic fallback. No-transfer protection wins
    over a clause."""
    owner = team_of(gs, pid)
    if owner is None or gs.players[pid].no_transfer_clause:
        return None
    p = gs.players[pid]
    if p.buyout_clause > 0:
        return p.buyout_clause
    if gs.teams[owner].tier != 2:
        return None
    mult = 1.5 + _hash01(pid, "buyout") * 1.0
    return max(15_000, int(round(transfer_value(p) * mult / 1000) * 1000))


def buyout_breakdown(gs: GameState, pid: str) -> list[dict[str, int | str]]:
    """Base value plus the player's negotiated clause premium."""
    fee = buyout_fee(gs, pid)
    if fee is None:
        return []
    base = transfer_value(gs.players[pid])
    return [
        {"label": "base value", "delta": base},
        {"label": "contract buyout clause", "delta": fee - base},
    ]


def buy_out_player(gs: GameState, buyer_id: str, pid: str) -> tuple[bool, str]:
    """A tier-1 org triggers a tier-2 player's buyout clause: pay the fee,
    the player moves this week. The selling org has no say — the clause was
    the price of signing the player to a tier-2 deal in the first place."""
    allowed, why = market_move_allowed(gs, buyer_id)
    if not allowed:
        return False, why
    if gs.teams[buyer_id].tier != 1:
        return False, "only a tier-1 org can trigger a buyout clause"
    fee = buyout_fee(gs, pid)
    if fee is None:
        return False, "no buyout clause — negotiate a transfer instead"
    p = gs.players[pid]
    buyer = gs.teams[buyer_id]
    if buyer.balance < fee + asking_salary(p) * 8:
        return False, f"need {fee + asking_salary(p) * 8:,} cr to cover clause + wages"
    seller = gs.teams[team_of(gs, pid)]
    ok, msg = execute_transfer(gs, pid, buyer_id, fee)
    if not ok:
        return False, msg
    gs.push_news(
        f"{buyer.name} trigger {p.handle}'s buyout clause at {seller.name} "
        f"({fee:,} cr) — the clause leaves no room to argue."
    )
    return True, f"bought out {p.handle} for {fee:,} cr"


def execute_transfer(
    gs: GameState, pid: str, buyer_id: str, fee: int, weeks: int = 52
) -> tuple[bool, str]:
    """Move a contracted player for money. The buyer must have roster
    space unless it's an AI org (which auto-releases its weakest)."""
    seller_id = team_of(gs, pid)
    if seller_id is None or seller_id == buyer_id:
        return False, "player is not transferable"
    allowed, why = market_move_allowed(gs, buyer_id)
    if not allowed:
        return False, why
    seller, buyer = gs.teams[seller_id], gs.teams[buyer_id]
    p = gs.players[pid]
    if p.no_transfer_clause:
        return False, f"{p.handle} has a no-transfer clause"
    if buyer.balance < fee:
        return False, "buyer cannot afford the fee"
    if gs.is_human(buyer_id):
        if len(buyer.player_ids) >= roster_cap(gs, buyer_id):
            cap = roster_cap(gs, buyer_id)
            return False, f"roster is full ({cap}); release someone first"
    elif len(buyer.player_ids) >= ROSTER_SIZE:
        # An AI BUYER stays lean at the field size: it sheds its weakest to
        # make room, so AI-window trades never grow AI rosters (their bench
        # headroom up to roster_cap only ever fills via human-offered
        # packages — see roster_cap). Fresh arrivals are protected — the
        # org won't flip a player it just signed/bought (falls back to the
        # overall weakest only if the WHOLE roster is new).
        settled = [
            gs.players[q] for q in buyer.player_ids
            if gs.players[q].tenure_weeks >= NEW_SIGNING_PROTECT_WEEKS
        ]
        weakest = min(
            settled or (gs.players[q] for q in buyer.player_ids),
            key=lambda q: (retention_value(gs, buyer_id, q.id), q.id),
        )
        effects = _departure_consequences(gs, buyer_id, weakest.id)
        _record_value_decision(
            gs, "release", "completed", weakest.id, buyer_id,
            reason=f"made room for transfer target {pid}", effects=effects,
        )
        buyer.player_ids.remove(weakest.id)
        buyer.lineup_ids = [q for q in buyer.lineup_ids if q != weakest.id]
        buyer.lineup.starters = [q for q in buyer.lineup.starters if q != weakest.id]
        buyer.lineup.agents.pop(weakest.id, None)
        weakest.contract_weeks_left = 0
        gs.free_agent_ids.append(weakest.id)
        if buyer.captain_id == weakest.id:
            buyer.captain_id = buyer.player_ids[0] if buyer.player_ids else None
    seller_view = org_player_valuation(gs, seller_id, pid, "sell")
    effects = _departure_consequences(gs, seller_id, pid)
    _record_value_decision(
        gs, "transfer", "completed", pid, seller_id,
        counterparty=buyer_id, context="sell", fee=fee,
        reason="transfer completed", effects=effects,
    )
    market_history.record(
        gs, "transfer", "completed", pid, actor_team_id=buyer_id,
        counterparty_team_id=seller_id, context="buy", fee=fee,
        salary=p.salary,
        market_value=int(org_player_valuation(gs, buyer_id, pid, "buy")["market_value"]),
        org_value=int(org_player_valuation(gs, buyer_id, pid, "buy")["value"]),
        components=org_player_valuation(gs, buyer_id, pid, "buy")["components"],
        reason=f"seller stance: {seller_view['stance']}",
    )
    buyer.balance -= fee
    seller.balance += fee
    relationships.on_departure(gs, pid, seller_id)
    seller.player_ids.remove(pid)
    buyer.player_ids.append(pid)
    seller.lineup_ids = [q for q in seller.lineup_ids if q != pid]
    if p.roster_role == "starter":
        buyer.lineup_ids = [
            q
            for q in buyer.lineup_ids
            if q != pid and q in buyer.player_ids and q in gs.players
        ] + [pid]
        buyer.lineup_ids = sorted(
            buyer.lineup_ids,
            key=lambda q: (-player_quality(gs.players[q]), q),
        )[:5]
    if seller.captain_id == pid:
        seller.captain_id = seller.player_ids[0] if seller.player_ids else None
    if buyer.captain_id is None:
        buyer.captain_id = pid
    p.salary = max(1_200, int(asking_salary(p) * 1.1 / 100) * 100)
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    reaction = relationships.transfer_reaction(gs, pid, seller_id, buyer_id)
    p.tenure_weeks = 0
    news = f"TRANSFER: {p.handle} joins {buyer.name} from {seller.name} for {fee:,} cr."
    if reaction:
        news += f" {p.handle} {reaction}."
    gs.push_news(news)
    chronicle.record(
        gs, "transfer",
        f"{p.handle} joins {buyer.name} from {seller.name}.",
        team_id=buyer_id,
        player_id=pid,
        data={"from": seller_id, "fee": str(fee)},
    )
    return True, f"{p.handle} joins {buyer.name} for {fee:,} cr"


# ---------------------------------------------------------------------------
# Package deals: players + cash both ways


def package_value(
    gs: GameState,
    out_pids: list[str],
    cash_to_seller: int,
    cash_to_buyer: int = 0,
    viewer_id: str | None = None,
) -> int:
    """Net value the buyer is sending the seller: the market value of the
    players offered plus cash going out, minus any cash requested back.
    With `viewer_id` the players are priced at THAT org's perception
    (see perceived_value) — an AI seller weighs your package with its own
    flawed read of your players, so the same offer can be a steal to one
    club and an insult to another. Cash is cash to everyone."""
    # The consensus is the coach/analyst number shown in that org's trade
    # room. AI sellers therefore accept or reject against the same valuation
    # model a human staff room would expose, while keeping their exact read
    # private from the bidder.
    players = sum(
        valuation_opinions(gs, viewer_id, gs.players[pid])["consensus"]
        for pid in out_pids
    )
    return players + cash_to_seller - cash_to_buyer


def _relocate(gs: GameState, pid: str, from_id: str, to_id: str, weeks: int) -> None:
    """Move one contracted player between two rosters, refreshing their deal and
    repairing captaincy on both ends. Cash is the caller's job."""
    src, dst = gs.teams[from_id], gs.teams[to_id]
    p = gs.players[pid]
    effects = _departure_consequences(gs, from_id, pid)
    _record_value_decision(
        gs, "package", "completed", pid, from_id,
        counterparty=to_id, context="sell", reason="package exchange",
        effects=effects,
    )
    relationships.on_departure(gs, pid, from_id)
    src.player_ids.remove(pid)
    dst.player_ids.append(pid)
    src.lineup_ids = [q for q in src.lineup_ids if q != pid]
    if p.roster_role == "starter":
        dst.lineup_ids = [
            q
            for q in dst.lineup_ids
            if q != pid and q in dst.player_ids and q in gs.players
        ] + [pid]
        dst.lineup_ids = sorted(
            dst.lineup_ids,
            key=lambda q: (-player_quality(gs.players[q]), q),
        )[:5]
    if src.captain_id == pid:
        src.captain_id = src.player_ids[0] if src.player_ids else None
    if dst.captain_id is None:
        dst.captain_id = pid
    p.salary = max(1_200, int(asking_salary(p) * 1.1 / 100) * 100)
    p.contract_weeks_left = int(np.clip(weeks, MIN_CONTRACT_WEEKS, MAX_CONTRACT_WEEKS))
    relationships.transfer_reaction(gs, pid, from_id, to_id)
    p.tenure_weeks = 0


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
    allowed, why = market_move_allowed(gs, buyer_id)
    if not allowed:
        return False, why
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
    # Chronicle every player who moved — the movement feed and career
    # profiles read these (the cash path records the same way).
    chronicle.record(
        gs, "transfer",
        f"{target.handle} joins {buyer.name} from {seller.name}.",
        team_id=buyer_id,
        player_id=target_pid,
        data={"from": seller_id, "package": incoming},
    )
    for pid in out_pids:
        chronicle.record(
            gs, "transfer",
            f"{gs.players[pid].handle} joins {seller.name} from {buyer.name}.",
            team_id=seller_id,
            player_id=pid,
            data={"from": buyer_id, "package": target.handle},
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
    allowed, why = market_move_allowed(gs, buyer_id)
    if not allowed:
        return False, why
    seller_id = team_of(gs, target_pid)
    if seller_id is None:
        return False, "player is a free agent — sign them instead"
    if seller_id == buyer_id:
        return False, "that's your own player"
    if gs.players[target_pid].no_transfer_clause:
        return False, f"{gs.players[target_pid].handle} has a no-transfer clause"
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
    # AI seller: accept iff the package clears the asking price BY THEIR OWN
    # NUMBERS — they price your players at their perception, not yours, so
    # the rejection note deliberately doesn't say how short you really are.
    value = package_value(gs, out_pids, cash_out, cash_in, viewer_id=seller_id)
    ask = transfer_ask(gs, target_pid)
    if value < ask:
        _record_value_decision(
            gs, "package", "rejected", target_pid, seller_id,
            counterparty=buyer_id, context="sell", fee=cash_out,
            reason=f"package valued at {value}, below {ask}",
        )
        return False, (
            f"{seller.name} reject the package — they don't rate it "
            "against their asking price"
        )
    if seller.balance < cash_in:
        return False, f"{seller.name} can't fund the cash-back in this deal"
    return execute_package(gs, target_pid, buyer_id, out_pids, cash_out, cash_in)


def user_bid(gs: GameState, pid: str) -> tuple[bool, str]:
    """The acting manager buys a contracted player at the seller's ask. A bid
    for an AI org's player executes instantly; a bid for ANOTHER human's player
    lands on that manager's desk as a transfer offer they must accept."""
    buyer_id = gs.acting_team_id
    allowed, why = market_move_allowed(gs, buyer_id)
    if not allowed:
        return False, why
    seller_id = team_of(gs, pid)
    if seller_id is None:
        return False, "player is a free agent — sign them instead"
    if seller_id == buyer_id:
        return False, "that's your own player"
    ask = transfer_ask(gs, pid)
    team = gs.teams[buyer_id]
    p = gs.players[pid]
    if p.no_transfer_clause:
        return False, f"{p.handle} has a no-transfer clause"
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
    stance = str(org_player_valuation(gs, seller_id, pid, "sell")["stance"])
    if stance == "not for sale":
        _record_value_decision(
            gs, "bid", "rejected", pid, seller_id,
            counterparty=buyer_id, context="sell", fee=ask,
            reason="cash bid refused for an organisational icon",
        )
        return False, (
            f"{gs.teams[seller_id].name} will not sell {p.handle} for cash - "
            "they see them as a pillar of the organisation"
        )
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
    if accept:
        allowed, why = market_move_allowed(gs, offer.to_team)
        if not allowed:
            return False, why
    gs.transfer_offers = [o for o in gs.transfer_offers if o is not offer]
    p = gs.players[player_id]
    if not accept:
        _record_value_decision(
            gs, "bid", "rejected", player_id, seller_id,
            counterparty=offer.to_team, context="sell", fee=offer.fee,
            reason="human manager declined offer",
        )
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
    if not bool(market_window_status(gs)["open"]):
        return
    moves = 0
    # Rosters settle before the wheeling starts: the opening weeks see
    # almost no AI shopping, and never more than one move league-wide per
    # week after that (transfers should read as events, not noise).
    quiet = gs.week <= TRANSFER_QUIET_WEEKS
    appetite = 0.04 if quiet else 0.12
    buyers = sorted(
        (t for t in gs.teams.values() if t.tier == 1 and not gs.is_human(t.id)),
        key=lambda t: t.id,
    )
    for buyer in buyers:
        if moves >= 1:
            break
        if rng.random() > appetite:
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
                if p.no_transfer_clause:
                    continue
                # The buyer shops on ITS OWN read of the player — an org
                # that over-rates someone will overpay for them (and one
                # that under-rates a gem walks right past).
                q = perceived_quality(gs, buyer.id, p)
                upgrade = q - weakest_q
                # Tier-2 targets: buy the future, not just the present.
                if seller.tier == 2:
                    upgrade += max(0.0, development.potential_of(p) - q) * 0.5
                if upgrade < 5.0:
                    continue
                seller_view = org_player_valuation(gs, seller.id, pid, "sell")
                if seller.tier == 1 and seller_view["stance"] == "not for sale":
                    continue
                # Tier-2 contracts settle at the buyout clause — no
                # negotiation. Tier-1 targets pay the seller's ask.
                fee = (
                    buyout_fee(gs, pid) if seller.tier == 2 else None
                ) or transfer_ask(gs, pid)
                if buyer.balance < fee + asking_salary(p) * 10:
                    continue
                buyer_view = org_player_valuation(gs, buyer.id, pid, "buy")
                # Commercial stars can justify a smaller pure-ability upgrade,
                # but an AI never pays above its own total valuation.
                if int(buyer_view["value"]) < fee:
                    continue
                surplus = int(buyer_view["value"]) - fee
                key = (upgrade + surplus / 100_000.0, -fee, pid, seller.id)
                if best is None or key > (best[0], -best[1], best[2], best[3]):
                    best = (upgrade, fee, pid, seller.id)
        if best is None:
            continue
        _, fee, pid, seller_id = best
        # A tier-2 buyout executes against ANY owner (a clause is a clause —
        # human tier-2 managers lose players to it too, with the news to
        # show for it); only tier-1 bids land on a human seller's desk.
        if gs.teams[seller_id].tier == 2:
            buyer_name = buyer.name
            target = gs.players[pid]
            seller_name = gs.teams[seller_id].name
            execute_transfer(gs, pid, buyer.id, fee)
            gs.push_news(
                f"{buyer_name} trigger {target.handle}'s buyout clause at "
                f"{seller_name} ({fee:,} cr)."
            )
            moves += 1
            continue
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
