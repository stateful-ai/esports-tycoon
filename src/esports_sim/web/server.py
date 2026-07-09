"""FastAPI backend for the campaign hub + match viewer.

Every endpoint is a thin serializer over GameState or a call into the same
campaign/market/training functions the CLI uses. Match replays are served
from event logs captured at sim time (rosters move on immediately after a
week advances, so re-simulating a stored seed later would not reproduce
the same match).

Run: python -m esports_sim --web
"""

from __future__ import annotations

import hashlib
import random
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from esports_sim.manager import (
    development,
    economy,
    inbox as inbox_mod,
    market,
    relationships,
    sponsors,
    staff as staff_mod,
    talk,
)
from esports_sim.manager.campaign import WeekReport, advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.manager.training import FOCUS_OPTIONS
from esports_sim.registry.loader import GameData, load_all, load_geometry
from esports_sim.schemas import Event, Player, Team

_REPO_ROOT = Path(__file__).resolve().parents[3]
SAVE_PATH = Path("saves") / "campaign.json"  # same file the CLI uses
STATIC_DIR = Path(__file__).parent / "static"
DS_DIR = _REPO_ROOT / "ui" / "design-system"


class _Session:
    """Server-side campaign session. One campaign at a time, guarded by a
    lock (endpoints are sync `def`s — FastAPI runs them in a threadpool)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.gd: GameData = load_all()
        self.gs: GameState | None = None
        self.last_report: WeekReport | None = None
        # fixture id -> one event list per map, captured at sim time.
        self.event_logs: dict[str, list[list[Event]]] = {}
        if SAVE_PATH.exists():
            self.gs = GameState.load(SAVE_PATH)

    def require_gs(self) -> GameState:
        if self.gs is None:
            raise HTTPException(409, "no campaign — POST /api/new first")
        return self.gs

    def save(self) -> None:
        if self.gs is not None:
            self.gs.save(SAVE_PATH)


S = _Session()
app = FastAPI(title="esports-sim", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# View serializers


N_LOGOS = 8
PORTRAITS_PER_ROLE = 2


def _stable_idx(key: str, n: int) -> int:
    """Deterministic id->index (python's hash() is salted per process)."""
    return int(hashlib.blake2b(key.encode(), digest_size=4).hexdigest(), 16) % n


def _logo_url(team_id: str) -> str:
    return f"/assets/logos/logo_{_stable_idx(team_id, N_LOGOS)}.webp"


def _portrait_url(pid: str, role: str) -> str:
    return f"/assets/portraits/{role}_{_stable_idx(pid, PORTRAITS_PER_ROLE)}.webp"


def _agent_icon_url(agent_id: str) -> str:
    return f"/assets/agents/{agent_id}.webp"


def _map_thumb_url(map_id: str) -> str:
    return f"/assets/maps/{map_id}.webp"


def _pick_agent_id(p: Player, gd: GameData) -> str:
    """Highest-mastery agent the player knows; fall back to a role default.
    Mirrors sim.engine.MatchEngine._pick_agent (kept in sync manually — the
    web layer doesn't import sim internals) so the icon shown in a replay
    matches the agent that was actually played."""
    pool = sorted(p.agent_pool, key=lambda m: (-m.mastery, m.agent_id))
    for m in pool:
        if m.agent_id in gd.agents:
            return m.agent_id
    by_role = sorted(a.id for a in gd.agents.values() if a.role == p.role)
    return by_role[0] if by_role else sorted(gd.agents)[0]


def _fogged(gs: GameState, pid: str, attr: str, true_val: float, sigma: float) -> float:
    """Scout-noised attribute. Deterministic per (campaign, player, attr):
    the same fog level always shows the same guess — reports don't jitter."""
    if sigma <= 0:
        return true_val
    r = random.Random(f"{gs.seed}|{pid}|{attr}")
    return float(min(99.0, max(1.0, round(true_val + r.uniform(-1, 1) * sigma))))


def _player_view(p: Player, gs: GameState, fog: float = 0.0) -> dict:
    attrs = {
        k: _fogged(gs, p.id, k, v, fog) for k, v in sorted(p.attributes.items())
    }
    overall = (
        round(sum(attrs.values()) / len(attrs), 1)
        if attrs
        else round(market.player_quality(p), 1)
    )
    return {
        "id": p.id,
        "handle": p.handle,
        "real_name": p.real_name,
        "age": p.age,
        "role": str(p.role),
        "playstyle": str(p.playstyle),
        "region": str(p.region),
        "salary": p.salary,
        "contract_weeks_left": p.contract_weeks_left,
        "morale": _fogged(gs, p.id, "morale", p.morale, fog),
        "stamina": _fogged(gs, p.id, "stamina", p.stamina, fog),
        "form": _fogged(gs, p.id, "form", p.form, fog),
        "attributes": attrs,
        "overall": overall,
        "fog": round(fog, 1),
        "agents": [
            {"agent_id": m.agent_id, "mastery": m.mastery}
            for m in sorted(p.agent_pool, key=lambda m: -m.mastery)
        ],
        "personality": (
            [
                {"id": t, "blurb": development.TRAITS.get(t, {}).get("blurb", "")}
                for t in p.personality_tags
            ]
            if fog <= 0
            else [{"id": "?", "blurb": "scout to reveal"}]
        ),
        # Own club knows its players' ceilings; rivals' PA stays scouted-only.
        "potential_stars": (
            development.stars(development.potential_of(p)) if fog <= 0 else None
        ),
        "ca_stars": development.stars(overall),
        "is_free_agent": p.id in gs.free_agent_ids,
        "asking_salary": market.asking_salary(p),
        "portrait": _portrait_url(p.id, str(p.role)),
    }


def _team_view(t: Team, gs: GameState) -> dict:
    rec = gs.standings.get(t.id)
    return {
        "id": t.id,
        "name": t.name,
        "tag": t.tag,
        "logo": _logo_url(t.id),
        "region": str(t.region),
        "balance": t.balance,
        "reputation": t.reputation,
        "fan_count": t.fan_count,
        "world_rank": t.world_rank,
        "chemistry": t.chemistry,
        "captain_id": t.captain_id,
        "player_ids": t.player_ids,
        "record": {"wins": rec.wins, "losses": rec.losses, "diff": rec.diff}
        if rec
        else None,
    }


def _fixture_view(f, gs: GameState) -> dict:
    return {
        "id": f.id,
        "week": f.week,
        "stage": f.stage,
        "best_of": f.best_of,
        "team_a": f.team_a,
        "team_b": f.team_b,
        "team_a_name": gs.teams[f.team_a].name,
        "team_b_name": gs.teams[f.team_b].name,
        "maps": f.maps,
        "map_thumbs": {mid: _map_thumb_url(mid) for mid in f.maps},
        "veto": f.veto,
        "played": f.played,
        "winner_id": f.winner_id,
        "map_score": list(f.map_score),
        "results": [
            {
                "map_id": r.map_id,
                "map_thumb": _map_thumb_url(r.map_id),
                "score_a": r.score_a,
                "score_b": r.score_b,
                "winner_id": r.winner_id,
                "has_replay": f.id in S.event_logs
                and len(S.event_logs[f.id]) > i,
                "lines": [line.model_dump() for line in r.lines],
            }
            for i, r in enumerate(f.results)
        ],
    }


# ---------------------------------------------------------------------------
# Bootstrap / new game


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    with S.lock:
        if S.gs is None:
            preview = new_campaign(S.gd, seed=2026)
            return {
                "campaign": False,
                "teams": [
                    _team_view(t, preview)
                    for t in sorted(preview.teams.values(), key=lambda t: t.id)
                ],
            }
        return {"campaign": True}


class NewGameBody(BaseModel):
    team_id: str = "team_nexus"
    seed: int = 2026


@app.post("/api/new")
def new_game(body: NewGameBody) -> dict:
    with S.lock:
        S.gs = new_campaign(S.gd, seed=body.seed, user_team_id=body.team_id)
        S.event_logs.clear()
        S.last_report = None
        S.save()
        return {"ok": True}


# ---------------------------------------------------------------------------
# State views


@app.get("/api/state")
def state() -> dict:
    with S.lock:
        gs = S.require_gs()
        user = gs.teams[gs.user_team_id]
        fixture = gs.team_fixture(gs.user_team_id)
        order = gs.standings_order(str(user.region))
        return {
            "season": gs.season,
            "week": gs.week,
            "phase": gs.phase,
            "user_team": _team_view(user, gs),
            "next_fixture": _fixture_view(fixture, gs) if fixture else None,
            "training_focus": gs.training_focus.get(gs.user_team_id, "tactical"),
            "focus_options": FOCUS_OPTIONS,
            "news": list(reversed(gs.news[-12:])),
            "scout": {
                "target": gs.scout_target,
                "target_name": (
                    "Free-agent market"
                    if gs.scout_target == "market"
                    else gs.teams[gs.scout_target].name
                    if gs.scout_target in gs.teams
                    else None
                ),
                "progress": gs.scout_progress.get(gs.scout_target or "", 0.0),
            },
            "standings_top": [
                {"team_id": tid, "name": gs.teams[tid].name, **gs.standings[tid].model_dump()}
                for tid in order[:4]
            ],
            "champions": [c.model_dump() for c in gs.champions],
            "transfer_offers": [
                {
                    "player_id": o.player_id,
                    "handle": gs.players[o.player_id].handle,
                    "to_team_name": gs.teams[o.to_team].name,
                    "fee": o.fee,
                    "expires_week": o.expires_week,
                }
                for o in gs.transfer_offers
                if o.player_id in gs.players and o.to_team in gs.teams
            ],
        }


@app.get("/api/inbox")
def inbox_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        return {
            "unread": inbox_mod.unread_count(gs),
            "items": [inbox_mod.to_api(it) for it in inbox_mod.sorted_items(gs)],
        }


class InboxReadBody(BaseModel):
    id: str | None = None
    all: bool = False


@app.post("/api/inbox/read")
def inbox_read(body: InboxReadBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.all:
            unread = inbox_mod.mark_all_read(gs)
        elif body.id is not None:
            unread = inbox_mod.mark_read(gs, body.id)  # unknown id: no-op
        else:
            unread = inbox_mod.unread_count(gs)
        S.save()
        return {"unread": unread}


FOG_BASE_SIGMA = 12.0


def _team_fog(gs: GameState, team_id: str) -> float:
    if team_id == gs.user_team_id:
        return 0.0
    return FOG_BASE_SIGMA * (1.0 - gs.scout_progress.get(team_id, 0.0))


@app.get("/api/roster/{team_id}")
def roster(team_id: str) -> dict:
    with S.lock:
        gs = S.require_gs()
        if team_id not in gs.teams:
            raise HTTPException(404, "unknown team")
        fog = _team_fog(gs, team_id)
        players = [_player_view(p, gs, fog) for p in gs.roster(team_id)]
        # Rival rosters are buyable: show the seller's ask per player.
        tendencies: list[str] = []
        if team_id != gs.user_team_id:
            for v in players:
                v["transfer_ask"] = market.transfer_ask(gs, v["id"])
            # Well-scouted rivals leak their coaching identity.
            if gs.scout_progress.get(team_id, 0.0) >= 0.5:
                tac = gs.teams[team_id].tactics
                if tac.aggression >= 62:
                    tendencies.append("swings angles aggressively")
                elif tac.aggression <= 38:
                    tendencies.append("holds passive angles")
                if tac.pace >= 62:
                    tendencies.append("hits sites fast")
                elif tac.pace <= 38:
                    tendencies.append("plays slow defaults")
                if tac.site_focus != "balanced":
                    tendencies.append(f"{tac.site_focus.upper()}-heavy attack")
                if tac.eco_greed >= 62:
                    tendencies.append("force-buys relentlessly")
        return {
            "team": _team_view(gs.teams[team_id], gs),
            "players": players,
            "is_user_team": team_id == gs.user_team_id,
            "fog": round(fog, 1),
            "scouting_this": gs.scout_target == team_id,
            "scout_progress": gs.scout_progress.get(team_id, 0.0),
            "tendencies": tendencies,
            "chemistry_pairs": {
                kind: [
                    [gs.players[a].handle, gs.players[b].handle]
                    for a, b in pairs
                    if a in gs.players and b in gs.players
                ]
                for kind, pairs in relationships.duos_and_feuds(gs, team_id).items()
            }
            if team_id == gs.user_team_id
            else {"duos": [], "feuds": []},
        }


@app.get("/api/standings")
def standings() -> dict:
    with S.lock:
        gs = S.require_gs()

        def rows_for(region: str | None, tier: int = 1) -> list[dict]:
            return [
                {
                    **_team_view(gs.teams[tid], gs),
                    **gs.standings[tid].model_dump(),
                    "diff": gs.standings[tid].diff,
                }
                for tid in gs.standings_order(region, tier=tier)
            ]

        user_region = str(gs.teams[gs.user_team_id].region)
        regions = sorted(gs.regions(), key=lambda r: (r != user_region, r))
        return {
            "regions": [
                {
                    "region": r,
                    "is_user": r == user_region,
                    "rows": rows_for(r),
                    "tier2_rows": rows_for(r, tier=2),
                }
                for r in regions
            ],
            # Kept for any consumer expecting the flat world table.
            "rows": rows_for(None),
        }


@app.get("/api/schedule")
def schedule() -> dict:
    with S.lock:
        gs = S.require_gs()
        return {
            "current_week": gs.week,
            # Tier 2 plays but isn't broadcast — its results live in
            # standings, stats, and scout reports, not the fixture list.
            "fixtures": [
                _fixture_view(f, gs)
                for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id))
                if f.tier == 1
            ],
        }


@app.get("/api/market")
def market_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        fas = sorted(
            (gs.players[pid] for pid in gs.free_agent_ids),
            key=lambda p: -market.player_quality(p),
        )
        out = []
        # Market fog: without market scouting you shop on rumor — banded
        # ability, unknown ceiling. Reports tighten the view.
        progress = gs.scout_progress.get("market", 0.0)
        for p in fas:
            ok, why = market.can_sign(gs, gs.user_team_id, p.id)
            view = _player_view(p, gs, fog=6.0 * (1.0 - progress))
            report = development.scout_report(gs, p, progress)
            view["scout"] = {
                "ca_stars": report["ca_stars"],
                "pa_stars": report["pa_stars"] if progress > 0 else None,
                "traits": report["traits"],
                "traits_hidden": report["traits_hidden"],
            }
            out.append({**view, "can_sign": ok, "block_reason": why})
        return {
            "free_agents": out,
            "roster_size": market.ROSTER_SIZE,
            "market_scouting": round(progress, 2),
        }


@app.get("/api/stats")
def stats_view() -> dict:
    with S.lock:
        gs = S.require_gs()

        def team_of(pid: str) -> str:
            return next(
                (t.name for t in gs.teams.values() if pid in t.player_ids), "FA"
            )

        players = []
        for pid in sorted(gs.player_stats):
            st = gs.player_stats[pid]
            p = gs.players.get(pid)
            if p is None or st.maps == 0:
                continue
            players.append(
                {
                    "player_id": pid,
                    "handle": p.handle,
                    "team": team_of(pid),
                    "maps": st.maps,
                    "kills": st.kills,
                    "deaths": st.deaths,
                    "kd": round(st.kd, 2),
                    "rating": round(st.rating, 2),
                    "first_kills": st.first_kills,
                    "trade_kills": st.trade_kills,
                    "hs_pct": round(st.hs_pct, 1),
                    "plants": st.plants,
                    "defuses": st.defuses,
                    "is_user": pid in gs.teams[gs.user_team_id].player_ids,
                }
            )
        players.sort(key=lambda r: (-r["rating"], -r["kills"]))

        teams = []
        for tid in gs.standings_order():
            ts = gs.team_stats.get(tid)
            if ts is None or ts.maps == 0:
                continue
            teams.append(
                {
                    "team_id": tid,
                    "name": gs.teams[tid].name,
                    "maps": ts.maps,
                    "atk_pct": round(100 * ts.atk_won / max(ts.atk_rounds, 1), 1),
                    "def_pct": round(100 * ts.def_won / max(ts.def_rounds, 1), 1),
                    "pistol_pct": round(
                        100 * ts.pistols_won / max(ts.pistols, 1), 1
                    ),
                    "is_user": tid == gs.user_team_id,
                }
            )

        return {
            "players": players,
            "teams": teams,
            "awards": [a.model_dump() for a in reversed(gs.awards)],
        }


@app.get("/api/finances")
def finances() -> dict:
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.user_team_id]
        payroll = sum(p.salary for p in gs.roster(gs.user_team_id))
        staff_cost = staff_mod.weekly_cost(gs)
        rep = S.last_report

        slots = {}
        for slot in sponsors.SLOT_ORDER:
            cfg = sponsors.SLOT_CONFIG[slot]
            deal = gs.sponsor_slots.get(slot)
            offer = gs.sponsor_slot_offers.get(slot)
            facility_ok = sponsors._slot_unlocked(gs, slot)
            slots[slot] = {
                "deal": deal.model_dump() if deal else None,
                "offer": offer.model_dump() if offer else None,  # legacy
                "market": [
                    {
                        **o.model_dump(),
                        "relation": sponsors.relation(gs, o.brand),
                        "objective_labels": [
                            {
                                "kind": ob.kind,
                                "bonus": ob.bonus,
                                "label": sponsors.OBJECTIVE_LABELS.get(ob.kind, ob.kind),
                            }
                            for ob in o.objectives
                        ],
                    }
                    for o in gs.sponsor_market.get(slot, [])
                ],
                "rep_gate": cfg["rep_gate"],
                "unlocked": facility_ok and team.reputation >= cfg["rep_gate"],
                "locked_reason": (
                    f"requires Marketing Office level {cfg['unlock']}"
                    if not facility_ok
                    else f"requires reputation {cfg['rep_gate']:.0f}"
                    if team.reputation < cfg["rep_gate"]
                    else None
                ),
                "objective_labels_deal": [
                    {
                        "kind": ob.kind,
                        "bonus": ob.bonus,
                        "met": ob.met,
                        "label": sponsors.OBJECTIVE_LABELS.get(ob.kind, ob.kind),
                    }
                    for ob in (deal.objectives if deal else [])
                ],
            }

        facilities = {}
        for name in economy.FACILITY_NAMES:
            level = gs.facilities.get(name, 0)
            facilities[name] = {
                "level": level,
                "max_level": economy.FACILITY_MAX_LEVEL,
                "next_cost": economy.facility_upgrade_cost(level),
                "upkeep": economy.FACILITY_UPKEEP_PER_LEVEL.get(name, 0) * level,
            }

        return {
            "balance": team.balance,
            "weekly_payroll": payroll,
            "marketability": round(sponsors.marketability(gs), 2),
            "last_week_income": rep.user_income if rep else None,
            "last_week_expenses": rep.user_expenses if rep else None,
            # Legacy (pre-M4) fields, kept for saves with an in-flight deal.
            "sponsor": gs.sponsor.model_dump() if gs.sponsor else None,
            "sponsor_offer": gs.sponsor_offer.model_dump()
            if gs.sponsor_offer
            else None,
            "slots": slots,
            "facilities": facilities,
            "breakdown": economy.weekly_breakdown(gs, staff_cost=staff_cost),
            "projection": economy.cash_projection(gs, staff_cost=staff_cost),
        }


class SponsorBody(BaseModel):
    slot: str
    accept: bool
    # Market offers (new): identify the brand; choose a structure to sign.
    brand: str | None = None
    structure: str | None = None


@app.post("/api/actions/sponsor")
def sponsor_action(body: SponsorBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.slot not in sponsors.SLOT_ORDER:
            raise HTTPException(422, f"slot must be one of {sponsors.SLOT_ORDER}")
        if body.brand is not None:
            if body.accept:
                ok, msg = sponsors.sign_market_offer(
                    gs, body.slot, body.brand, body.structure or "steady"
                )
            else:
                ok, msg = sponsors.decline_market_offer(gs, body.slot, body.brand)
        else:
            # Legacy single-offer path (pre-market saves).
            fn = (
                sponsors.accept_slot_offer
                if body.accept
                else sponsors.decline_slot_offer
            )
            ok, msg = fn(gs, body.slot)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


class FacilityBody(BaseModel):
    facility: str


@app.post("/api/actions/facility_upgrade")
def facility_upgrade(body: FacilityBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.facility not in economy.FACILITY_NAMES:
            raise HTTPException(422, f"facility must be one of {economy.FACILITY_NAMES}")
        team = gs.teams[gs.user_team_id]
        level = gs.facilities.get(body.facility, 0)
        cost = economy.facility_upgrade_cost(level)
        if cost is None:
            raise HTTPException(409, "already at max level")
        if team.balance < cost:
            raise HTTPException(409, f"need {cost:,} cr banked for the upgrade")
        team.balance -= cost
        gs.facilities[body.facility] = level + 1
        gs.push_news(
            f"{team.name} upgrade {body.facility.replace('_', ' ')} to "
            f"level {level + 1} ({cost:,} cr)."
        )
        S.save()
        return {
            "ok": True,
            "message": f"{body.facility.replace('_', ' ')} upgraded to level {level + 1}",
            "level": level + 1,
        }


# ---------------------------------------------------------------------------
# Actions


class TrainingBody(BaseModel):
    focus: str


@app.post("/api/actions/training")
def set_training(body: TrainingBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.focus not in FOCUS_OPTIONS:
            raise HTTPException(422, f"focus must be one of {FOCUS_OPTIONS}")
        gs.training_focus[gs.user_team_id] = body.focus
        S.save()
        return {"ok": True, "focus": body.focus}


@app.get("/api/staff")
def staff_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        if not gs.staff_candidates:
            # Saves from before the staff feature: build the market lazily
            # (deterministic from seed+season, so no drift).
            staff_mod.refresh_candidates(gs)
            S.save()
        return {
            "hired": {r: m.model_dump() for r, m in sorted(gs.staff.items())},
            "candidates": {
                r: [m.model_dump() for m in pool]
                for r, pool in sorted(gs.staff_candidates.items())
            },
            "roles": staff_mod.ROLES,
            "blurbs": staff_mod.ROLE_BLURB,
            "weekly_cost": staff_mod.weekly_cost(gs),
        }


class HireBody(BaseModel):
    candidate_id: str


@app.post("/api/actions/hire_staff")
def hire_staff(body: HireBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = staff_mod.hire(gs, body.candidate_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


class ReleaseStaffBody(BaseModel):
    role: str


@app.post("/api/actions/release_staff")
def release_staff(body: ReleaseStaffBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = staff_mod.release(gs, body.role)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.get("/api/talk/{player_id}")
def talk_topic(player_id: str) -> dict:
    with S.lock:
        gs = S.require_gs()
        if player_id not in gs.players:
            raise HTTPException(404, "unknown player")
        ok, why = talk.can_talk(gs, player_id)
        if not ok:
            return {"available": False, "reason": why}
        t = talk.topic_for(gs, player_id)
        return {
            "available": True,
            "topic": {"id": t.id, "text": t.text},
            "options": [{"id": o.id, "label": o.label} for o in t.options],
        }


class TalkBody(BaseModel):
    player_id: str
    option_id: str


@app.post("/api/actions/talk")
def talk_resolve(body: TalkBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.player_id not in gs.players:
            raise HTTPException(404, "unknown player")
        ok, msg, effects = talk.resolve(gs, body.player_id, body.option_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg, "effects": effects}


@app.get("/api/tactics")
def tactics_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        tac = gs.teams[gs.user_team_id].tactics
        return {"tactics": tac.model_dump()}


class TacticsBody(BaseModel):
    aggression: float | None = None
    pace: float | None = None
    util_discipline: float | None = None
    eco_greed: float | None = None
    site_focus: str | None = None


@app.post("/api/actions/tactics")
def set_tactics(body: TacticsBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        tac = gs.teams[gs.user_team_id].tactics
        for field in ("aggression", "pace", "util_discipline", "eco_greed"):
            v = getattr(body, field)
            if v is not None:
                setattr(tac, field, float(min(100.0, max(0.0, v))))
        if body.site_focus is not None:
            if body.site_focus not in ("balanced", "a", "b", "c"):
                raise HTTPException(422, "site_focus must be balanced/a/b/c")
            tac.site_focus = body.site_focus
        S.save()
        return {"ok": True, "message": "tactics updated", "tactics": tac.model_dump()}


class BidBody(BaseModel):
    player_id: str


@app.post("/api/actions/bid")
def bid(body: BidBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.player_id not in gs.players:
            raise HTTPException(404, "unknown player")
        ok, msg = market.user_bid(gs, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(422, msg)
        return {"ok": True, "message": msg}


class OfferBody(BaseModel):
    player_id: str
    accept: bool


@app.post("/api/actions/transfer_offer")
def transfer_offer(body: OfferBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.respond_offer(gs, body.player_id, body.accept)
        S.save()
        if not ok:
            raise HTTPException(422, msg)
        return {"ok": True, "message": msg}


class ScoutBody(BaseModel):
    team_id: str


@app.post("/api/actions/scout")
def scout(body: ScoutBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.team_id != "market" and body.team_id not in gs.teams:
            raise HTTPException(404, "unknown team")
        if body.team_id == gs.user_team_id:
            raise HTTPException(422, "you already know your own team")
        gs.scout_target = body.team_id
        S.save()
        label = (
            "the free-agent market"
            if body.team_id == "market"
            else gs.teams[body.team_id].name
        )
        return {"ok": True, "message": f"scout assigned to {label}"}


@app.get("/api/scouting")
def scouting_view() -> dict:
    """The scout's desk: current assignment, progress, and report cards
    (banded CA/PA stars, progressively revealed traits)."""
    with S.lock:
        gs = S.require_gs()
        target = gs.scout_target
        reports: list[dict] = []
        if target == "market":
            progress = gs.scout_progress.get("market", 0.0)
            fas = sorted(
                (gs.players[pid] for pid in gs.free_agent_ids),
                key=lambda p: -development.potential_of(p),
            )
            reports = [development.scout_report(gs, p, progress) for p in fas]
        elif target and target in gs.teams:
            progress = gs.scout_progress.get(target, 0.0)
            reports = [
                development.scout_report(gs, p, progress)
                for p in gs.roster(target)
            ]
        else:
            progress = 0.0
        return {
            "target": target,
            "target_name": (
                "Free-agent market"
                if target == "market"
                else gs.teams[target].name if target in gs.teams else None
            ),
            "progress": round(progress, 2),
            "reports": reports,
            "teams": [
                {"id": tid, "name": gs.teams[tid].name}
                for tid in sorted(gs.teams)
                if tid != gs.user_team_id
            ],
        }


class PlayerBody(BaseModel):
    player_id: str


@app.post("/api/actions/sign")
def sign(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.sign_player(gs, gs.user_team_id, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/release")
def release(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.release_player(gs, gs.user_team_id, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/renew")
def renew(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.renew_contract(gs, gs.user_team_id, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/advance")
def advance() -> dict:
    with S.lock:
        gs = S.require_gs()
        S.event_logs.clear()  # replays are for the freshly played week
        report = advance_week(gs, S.gd, events_out=S.event_logs)
        S.last_report = report
        S.save()
        return {
            "season": report.season,
            "week": report.week,
            "phase": report.phase,
            "fixtures": [_fixture_view(f, gs) for f in report.fixtures],
            "user_income": report.user_income,
            "user_expenses": report.user_expenses,
            "notes": report.notes,
        }


# ---------------------------------------------------------------------------
# Match viewer data


@app.get("/api/map/{map_id}")
def map_geometry(map_id: str) -> dict:
    if map_id not in S.gd.maps:
        raise HTTPException(404, "unknown map")
    m = S.gd.maps[map_id]
    geo = load_geometry(map_id)
    floor = None
    if geo is not None:
        paths: dict[str, list[list[float]]] = {}
        for a, nbrs in m.adjacency.items():
            for b in nbrs:
                paths[f"{a}|{b}"] = [[round(px, 2), round(py, 2)] for px, py in geo.path(a, b)]
        floor = {
            "regions": {
                rid: {"x": r.x, "y": r.y, "w": r.w, "h": r.h, "z": r.z}
                for rid, r in geo.regions.items()
            },
            "paths": paths,
            "props": [p.model_dump() for p in geo.props],
        }
    gimmicks = []
    for g in m.gimmicks:
        a, b = g.between
        if geo is not None and geo.portal(a, b) is not None:
            gx, gy = geo.portal(a, b)
        elif geo is not None and a in geo.regions and b in geo.regions:
            ra, rb = geo.regions[a], geo.regions[b]
            gx, gy = (ra.cx + rb.cx) / 2, (ra.cy + rb.cy) / 2
        else:
            ca, cb = m.callouts[a], m.callouts[b]
            gx, gy = (ca.x + cb.x) / 2, (ca.y + cb.y) / 2
        gimmicks.append(
            {
                "id": g.id,
                "type": str(g.type),
                "between": list(g.between),
                "x": round(gx, 1),
                "y": round(gy, 1),
                "noise_radius": g.noise_radius,
            }
        )
    return {
        "floor": floor,
        "gimmicks": gimmicks,
        "id": m.id,
        "display_name": m.display_name,
        "sites": [str(s) for s in m.sites],
        "attacker_spawn": m.attacker_spawn,
        "defender_spawn": m.defender_spawn,
        "callouts": {
            cid: {
                "name": c.display_name,
                "site": str(c.site),
                "zone": str(c.zone),
                "x": c.x,
                "y": c.y,
            }
            for cid, c in m.callouts.items()
        },
        "edges": sorted(
            {
                tuple(sorted((a, b)))
                for a, nbrs in m.adjacency.items()
                for b in nbrs
            }
        ),
    }


@app.get("/api/replay/{fixture_id}/{map_index}")
def replay(fixture_id: str, map_index: int) -> dict:
    with S.lock:
        gs = S.require_gs()
        logs = S.event_logs.get(fixture_id)
        if logs is None or map_index >= len(logs):
            raise HTTPException(
                404,
                "replay unavailable — full logs are only kept for the most "
                "recently played week (rosters have moved on since).",
            )
        fixture = next(f for f in gs.fixtures if f.id == fixture_id)
        events = logs[map_index]
        map_id = fixture.results[map_index].map_id
        players = {}
        for tid in (fixture.team_a, fixture.team_b):
            for pid in gs.teams[tid].player_ids:
                p = gs.players.get(pid)
                if p:
                    agent_id = _pick_agent_id(p, S.gd)
                    players[pid] = {
                        "handle": p.handle,
                        "team_id": tid,
                        "agent_id": agent_id,
                        "agent_icon": _agent_icon_url(agent_id),
                    }
        # Ability flags so the viewer can render utility (smoke vs flash…).
        abilities = {
            ab.id: {
                "name": ab.name,
                "smoke": ab.blocks_sight,
                "flash": ab.flashes,
                "damage": ab.damages,
                "info": ab.info,
                "ult": str(ab.type) == "ultimate",
            }
            for agent in S.gd.agents.values()
            for ab in agent.abilities
        }
        return {
            "fixture": _fixture_view(fixture, gs),
            "map": map_geometry(map_id),
            "team_a": fixture.team_a,
            "team_b": fixture.team_b,
            "players": players,
            "abilities": abilities,
            "events": [e.model_dump() for e in events],
        }


# Local app: force revalidation on scripts/styles so a server restart
# never pairs a fresh backend with a stale cached frontend.
@app.middleware("http")
async def _no_stale_frontend(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


# Static frontend + design system + art (mounted last so /api wins).
app.mount("/assets", StaticFiles(directory=str(_REPO_ROOT / "assets")), name="assets")
app.mount("/ds", StaticFiles(directory=str(DS_DIR)), name="ds")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def run(port: int = 8420, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{port}"
    print(f"esports-sim web UI: {url}")
    if open_browser:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
