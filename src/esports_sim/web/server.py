"""FastAPI backend for the campaign hub + match viewer.

Every endpoint is a thin serializer over GameState or a call into the same
campaign/market/training functions the CLI uses. Match replays are served
from event logs captured at sim time (rosters move on immediately after a
week advances, so re-simulating a stored seed later would not reproduce
the same match).

Run: python -m esports_sim --web
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from esports_sim.manager import market
from esports_sim.manager.campaign import WeekReport, advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.manager.training import FOCUS_OPTIONS
from esports_sim.registry.loader import GameData, load_all
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


def _player_view(p: Player, gs: GameState) -> dict:
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
        "morale": p.morale,
        "stamina": p.stamina,
        "form": p.form,
        "attributes": p.attributes,
        "overall": round(market.player_quality(p), 1),
        "agents": [
            {"agent_id": m.agent_id, "mastery": m.mastery}
            for m in sorted(p.agent_pool, key=lambda m: -m.mastery)
        ],
        "personality": p.personality_tags,
        "is_free_agent": p.id in gs.free_agent_ids,
        "asking_salary": market.asking_salary(p),
    }


def _team_view(t: Team, gs: GameState) -> dict:
    rec = gs.standings.get(t.id)
    return {
        "id": t.id,
        "name": t.name,
        "tag": t.tag,
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
        "played": f.played,
        "winner_id": f.winner_id,
        "map_score": list(f.map_score),
        "results": [
            {
                "map_id": r.map_id,
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
        order = gs.standings_order()
        return {
            "season": gs.season,
            "week": gs.week,
            "phase": gs.phase,
            "user_team": _team_view(user, gs),
            "next_fixture": _fixture_view(fixture, gs) if fixture else None,
            "training_focus": gs.training_focus.get(gs.user_team_id, "tactical"),
            "focus_options": FOCUS_OPTIONS,
            "news": list(reversed(gs.news[-12:])),
            "standings_top": [
                {"team_id": tid, "name": gs.teams[tid].name, **gs.standings[tid].model_dump()}
                for tid in order[:4]
            ],
            "champions": [c.model_dump() for c in gs.champions],
        }


@app.get("/api/roster/{team_id}")
def roster(team_id: str) -> dict:
    with S.lock:
        gs = S.require_gs()
        if team_id not in gs.teams:
            raise HTTPException(404, "unknown team")
        return {
            "team": _team_view(gs.teams[team_id], gs),
            "players": [_player_view(p, gs) for p in gs.roster(team_id)],
            "is_user_team": team_id == gs.user_team_id,
        }


@app.get("/api/standings")
def standings() -> dict:
    with S.lock:
        gs = S.require_gs()
        return {
            "rows": [
                {
                    **_team_view(gs.teams[tid], gs),
                    **gs.standings[tid].model_dump(),
                    "diff": gs.standings[tid].diff,
                }
                for tid in gs.standings_order()
            ]
        }


@app.get("/api/schedule")
def schedule() -> dict:
    with S.lock:
        gs = S.require_gs()
        return {
            "current_week": gs.week,
            "fixtures": [
                _fixture_view(f, gs)
                for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id))
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
        for p in fas:
            ok, why = market.can_sign(gs, gs.user_team_id, p.id)
            out.append({**_player_view(p, gs), "can_sign": ok, "block_reason": why})
        return {"free_agents": out, "roster_size": market.ROSTER_SIZE}


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
        rep = S.last_report
        return {
            "balance": team.balance,
            "weekly_payroll": payroll,
            "last_week_income": rep.user_income if rep else None,
            "last_week_expenses": rep.user_expenses if rep else None,
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
    return {
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
                    players[pid] = {"handle": p.handle, "team_id": tid}
        # Players may have been transferred since; backfill from events.
        return {
            "fixture": _fixture_view(fixture, gs),
            "map": map_geometry(map_id),
            "team_a": fixture.team_a,
            "team_b": fixture.team_b,
            "players": players,
            "events": [e.model_dump() for e in events],
        }


# Static frontend + design system (mounted last so /api wins).
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
