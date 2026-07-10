"""FastAPI backend for the campaign hub + match viewer.

Every endpoint is a thin serializer over GameState or a call into the same
campaign/market/training functions the CLI uses. Match replays are served
from event logs captured at sim time (rosters move on immediately after a
week advances, so re-simulating a stored seed later would not reproduce
the same match).

Run: python -m esports_sim --web
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import random
import re
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from esports_sim.manager import (
    analytics,
    career,
    chronicle,
    development,
    economy,
    inbox as inbox_mod,
    knowledge as knowledge_mod,
    market,
    memories as memories_mod,
    narrative,
    relationships,
    rivalries as rivalries_mod,
    social,
    sponsors,
    staff as staff_mod,
    talk,
)
from esports_sim.manager.campaign import (
    PREP_EDGE_BASE,
    PREP_EDGE_SPAN,
    WeekReport,
    advance_week,
    default_five,
    dressed_for,
    new_campaign,
)
from esports_sim.manager.state import GamePlan, GameState, PlayerSeasonStats
from esports_sim.manager.training import (
    DEV_FOCUS_OPTIONS,
    FOCUS_OPTIONS,
    INTENSITY_OPTIONS,
)
from esports_sim.registry.loader import GameData, load_all, load_geometry
from esports_sim.registry.rosters import list_roster_packs, load_roster_pack
from esports_sim.schemas import Event, Player, Team
from esports_sim.sim import constants as C
from esports_sim.sim import lineup as lineup_resolve
from esports_sim.sim import tactics_fit
from esports_sim.web import llm_social

_REPO_ROOT = Path(__file__).resolve().parents[3]
SAVE_DIR = Path("saves")
STATIC_DIR = Path(__file__).parent / "static"
DS_DIR = _REPO_ROOT / "ui" / "design-system"

# A browser is identified by an opaque `esports_sid` cookie; a shared campaign
# world is identified by a short game CODE that players share to join. The
# save file is keyed by the game code (one save per world), so several humans'
# state persists together. Session->game membership is persisted separately so
# a browser rejoins its game after a server restart.
COOKIE_NAME = "esports_sid"
_SID_RE = re.compile(r"^[0-9a-f]{32}$")
_CODE_RE = re.compile(r"^[A-Z0-9]{5}$")
# Unambiguous alphabet (no O/0, I/1) for human-typable join codes.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_SESSIONS_PATH = SAVE_DIR / "sessions.json"


def _save_path_for(code: str) -> Path:
    digest = hashlib.blake2b(code.encode(), digest_size=8).hexdigest()
    return SAVE_DIR / f"campaign_{digest}.json"


def _meta_path_for(code: str) -> Path:
    digest = hashlib.blake2b(code.encode(), digest_size=8).hexdigest()
    return SAVE_DIR / f"campaign_{digest}.meta.json"


class _Game:
    """One shared campaign world. Every human manager (LAN player) controls one
    of its teams; the set of humans is `gs.human_team_ids`. A solo game is just
    a world with a single human. Guarded by a lock (endpoints are sync `def`s
    run in a threadpool); all mutation of the shared GameState — including the
    per-request acting-manager binding — happens under it.

    `gd` (the immutable YAML registries) is shared across all games."""

    def __init__(self, gd: GameData, code: str, gs: GameState | None = None) -> None:
        self.lock = threading.Lock()
        self.gd: GameData = gd
        self.code = code
        self.mode = "solo"  # "solo" | "shared" (set by the lobby)
        self.save_path = _save_path_for(code)
        if gs is None and self.save_path.exists():
            gs = GameState.load(self.save_path)
        self.gs: GameState | None = gs
        self.last_report: WeekReport | None = None
        # A human's team id, marked when they've hit "advance"; the week only
        # ticks once every human is ready.
        self.ready: set[str] = set()
        # fixture id -> one event list per map, captured at sim time.
        self.event_logs: dict[str, list[list[Event]]] = {}

    def require_gs(self) -> GameState:
        if self.gs is None:
            raise HTTPException(409, "no campaign — create one first")
        # Bind the acting manager for this request (we're under self.lock).
        self.gs.set_acting(_ctx.get().team_id)
        return self.gs

    def save(self) -> None:
        if self.gs is not None:
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            self.gs.save(self.save_path)


class Lobby:
    """Registry of shared campaign worlds + which team each browser controls.
    GameData loads once and is shared. Games load lazily from disk (so a world
    survives a server restart), and the session->membership map is persisted."""

    def __init__(self) -> None:
        self.gd: GameData = load_all()
        self.games: dict[str, _Game] = {}
        self.sessions: dict[str, tuple[str, str]] = {}  # sid -> (code, team_id)
        # Every world a browser has ever created/joined (newest first):
        # sid -> [[code, team_id, team_name, mode], ...]. Lets a browser leave
        # a world (to start another) and later resume any of its old seats.
        self.history: dict[str, list[list[str]]] = {}
        self._lock = threading.Lock()
        self._load_sessions()

    # -- persistence of the sid -> (code, team) map --------------------------
    def _load_sessions(self) -> None:
        if _SESSIONS_PATH.exists():
            try:
                raw = json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))
                if "sessions" in raw:
                    self.sessions = {
                        k: tuple(v) for k, v in raw["sessions"].items()
                    }
                    self.history = raw.get("history", {})
                else:  # pre-history flat format
                    self.sessions = {k: tuple(v) for k, v in raw.items()}
            except (ValueError, OSError):
                self.sessions = {}

    def _save_sessions(self) -> None:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        _SESSIONS_PATH.write_text(
            json.dumps(
                {
                    "sessions": {
                        k: list(v) for k, v in self.sessions.items()
                    },
                    "history": self.history,
                }
            ),
            encoding="utf-8",
        )

    def _remember(
        self, sid: str, code: str, team_id: str, team_name: str, mode: str
    ) -> None:
        """Upsert a world into this browser's resumable history (newest
        first). Caller must hold `self._lock` and follow with a save."""
        rows = [r for r in self.history.get(sid, []) if r[0] != code]
        self.history[sid] = [[code, team_id, team_name, mode], *rows][:12]

    def _seat_holder(self, code: str, team_id: str) -> str | None:
        """The sid currently attached to (code, team_id), if any."""
        for other_sid, m in sorted(self.sessions.items()):
            if m == (code, team_id):
                return other_sid
        return None

    def _get_game(self, code: str) -> _Game | None:
        """Return a loaded game, lazily loading its save from disk if needed.
        Caller must hold `self._lock` (mutates the games cache)."""
        game = self.games.get(code)
        if game is None:
            path = _save_path_for(code)
            if path.exists():
                game = _Game(self.gd, code)
                game.mode = self._read_mode(code, game.gs)
                self.games[code] = game
        return game

    @staticmethod
    def _read_mode(code: str, gs: GameState | None) -> str:
        """Restore a world's solo/shared mode from its sidecar, falling back to
        an inference (>1 human == shared) for saves written before the sidecar."""
        meta = _meta_path_for(code)
        if meta.exists():
            try:
                return json.loads(meta.read_text(encoding="utf-8")).get("mode", "solo")
            except (ValueError, OSError):
                pass
        return "shared" if gs is not None and len(gs.human_team_ids) > 1 else "solo"

    @staticmethod
    def _write_mode(code: str, mode: str) -> None:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        _meta_path_for(code).write_text(json.dumps({"mode": mode}), encoding="utf-8")

    def _new_code(self, rng: random.Random) -> str:
        for _ in range(50):
            code = "".join(rng.choice(_CODE_ALPHABET) for _ in range(5))
            if code not in self.games and not _save_path_for(code).exists():
                return code
        raise HTTPException(503, "could not allocate a game code — try again")

    # -- request-time lookups -------------------------------------------------
    def membership(self, sid: str) -> tuple[str, str] | None:
        return self.sessions.get(sid)

    def game_for(self, sid: str) -> tuple[_Game | None, str | None]:
        """(game, team_id) for a browser, or (None, None) if it hasn't joined
        one. Drops a stale membership whose world no longer exists on disk."""
        with self._lock:
            m = self.sessions.get(sid)
            if m is None:
                return None, None
            code, team_id = m
            game = self._get_game(code)
            if game is None:
                del self.sessions[sid]
                self._save_sessions()
                return None, None
            return game, team_id

    # -- mutations ------------------------------------------------------------
    def create_game(
        self,
        sid: str,
        team_id: str,
        seed: int,
        shared: bool,
        pack_id: str | None = None,
        game_mode: str = "sandbox",
        manager_name: str = "",
    ) -> _Game:
        with self._lock:
            # Code allocation must not depend on wall-clock/hash() (determinism
            # habit); seed a local RNG from the campaign seed + live game count.
            rng = random.Random(f"{seed}|{len(self.games)}|{sid}")
            code = self._new_code(rng)
            pack = None
            if pack_id:
                try:
                    pack = load_roster_pack(pack_id)
                except FileNotFoundError:
                    raise HTTPException(
                        422, f"unknown roster pack '{pack_id}'"
                    ) from None
            offer = None
            if game_mode == "legacy":
                # Re-derive the founding seat's offer slate server-side and
                # demand the pick comes from it — the lobby showed exactly
                # this set (same seed, seat 0), so nothing can drift.
                preview = new_campaign(
                    self.gd, seed=seed, pack=pack, mode="sandbox"
                )
                offers = career.new_game_offers(preview, 0)
                offer = next(
                    (o for o in offers if o.team_id == team_id), None
                )
                if offer is None:
                    raise HTTPException(
                        422, "pick one of the offered clubs to start a career"
                    )
            gs = new_campaign(
                self.gd, seed=seed, user_team_id=team_id, pack=pack,
                mode=game_mode, manager_name=manager_name,
                career_offer=offer,
            )
            if team_id not in gs.teams:
                raise HTTPException(422, f"unknown team '{team_id}'")
            game = _Game(self.gd, code, gs=gs)
            game.mode = "shared" if shared else "solo"
            self.games[code] = game
            self.sessions[sid] = (code, team_id)
            self._remember(
                sid, code, team_id, gs.teams[team_id].name, game.mode
            )
            self._save_sessions()
            self._write_mode(code, game.mode)
            game.save()
            return game

    def join_game(
        self, sid: str, code: str, team_id: str
    ) -> tuple[_Game | None, str | None]:
        with self._lock:
            game = self._get_game(code)
            if game is None or game.gs is None:
                return None, "no game with that code"
            if game.mode != "shared":
                return None, "that game isn't open to other managers"
            gs = game.gs
            if team_id not in gs.teams:
                return None, "unknown team"
            # A human seat is claimable unless another browser session is
            # CURRENTLY attached to it — so leaving a world and rejoining
            # your old seat (same or different browser) just works.
            holder = self._seat_holder(code, team_id)
            if team_id in gs.human_team_ids and holder not in (None, sid):
                return None, "another manager already controls that team"
            if team_id not in gs.human_team_ids:
                offer = None
                if gs.game_mode == "legacy" and gs.manager_for(team_id) is None:
                    # A joining career manager picks from THEIR offer
                    # slate (seat index = managers so far, taken = seats
                    # already held) — the lobby offers endpoint showed
                    # exactly this derivation.
                    offers = career.new_game_offers(
                        gs, len(gs.managers), taken=set(gs.human_team_ids)
                    )
                    offer = next(
                        (o for o in offers if o.team_id == team_id), None
                    )
                    if offer is None:
                        return None, "pick one of the clubs offering you the job"
                gs.human_team_ids.append(team_id)
                if gs.manager_for(team_id) is None:
                    career.create_seat(gs, team_id, offer=offer)
            self.sessions[sid] = (code, team_id)
            self._remember(
                sid, code, team_id, gs.teams[team_id].name, game.mode
            )
            self._save_sessions()
            game.save()
            return game, None

    def leave(self, sid: str) -> str | None:
        """Detach this browser from its current world (the save stays on
        disk and in this browser's resumable history). Returns the code
        left, or None if it wasn't in a world."""
        with self._lock:
            m = self.sessions.pop(sid, None)
            if m is not None:
                code, team_id = m
                # Worlds created before the history list existed need an
                # entry NOW, or leaving would orphan them.
                game = self._get_game(code)
                if game is not None and game.gs is not None:
                    team = game.gs.teams.get(team_id)
                    self._remember(
                        sid, code, team_id,
                        team.name if team else team_id, game.mode,
                    )
                self._save_sessions()
            return m[0] if m else None

    def resume(self, sid: str, code: str) -> tuple[_Game | None, str | None]:
        """Re-attach this browser to a world from its own history — the only
        way back into a SOLO world, and a code-free way back into a shared
        one. The old seat must not have been claimed by someone else."""
        with self._lock:
            row = next(
                (r for r in self.history.get(sid, []) if r[0] == code), None
            )
            if row is None:
                return None, "that world isn't in this browser's history"
            game = self._get_game(code)
            if game is None or game.gs is None:
                return None, "that world's save no longer exists"
            team_id = row[1]
            holder = self._seat_holder(code, team_id)
            if holder not in (None, sid):
                return None, "another manager now controls that team"
            seat = game.gs.seat_for_session(team_id)
            if team_id not in game.gs.human_team_ids:
                if seat is not None and not seat.team_id:
                    # A dismissed legacy manager resuming: the session
                    # re-binds (they land on the job market), but their
                    # old org stays AI-run.
                    pass
                else:
                    game.gs.human_team_ids.append(team_id)
                    if game.gs.manager_for(team_id) is None:
                        career.create_seat(game.gs, team_id)
            self.sessions[sid] = (code, team_id)
            self._remember(
                sid, code, team_id, game.gs.teams[team_id].name, game.mode
            )
            self._save_sessions()
            return game, None

    def worlds_for(self, sid: str) -> list[dict]:
        """This browser's resumable worlds (history entries whose save still
        exists), newest first. No save-loading — history carries the label."""
        with self._lock:
            out = []
            for code, team_id, team_name, mode in self.history.get(sid, []):
                if code in self.games or _save_path_for(code).exists():
                    out.append(
                        {
                            "code": code,
                            "team_id": team_id,
                            "team_name": team_name,
                            "mode": mode,
                        }
                    )
            return out


_LOBBY = Lobby()


class _ReqCtx:
    """The game + acting team bound to the request currently being handled."""

    __slots__ = ("game", "team_id")

    def __init__(self, game: _Game | None, team_id: str | None) -> None:
        self.game = game
        self.team_id = team_id


# Set by SessionMiddleware before routing; read through the `S` proxy so the
# existing endpoint bodies (`S.gs`, `S.lock`, `S.gd`, ...) keep working.
_ctx: contextvars.ContextVar[_ReqCtx] = contextvars.ContextVar("req_ctx")
# The requesting browser's cookie id — lobby endpoints (create/join) need it to
# record membership. Set alongside `_ctx`.
_sid_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("req_sid")


def _current_sid() -> str:
    return _sid_ctx.get()


class _GameProxy:
    """Forwards attribute access to the `_Game` bound to this request. A browser
    that hasn't joined a game yet has no game, so gameplay endpoints (which all
    touch `S.lock` / `S.gs`) cleanly 409 — the lobby endpoints don't use `S`."""

    def __getattr__(self, name: str):
        game = _ctx.get().game
        if game is None:
            raise HTTPException(409, "no game — create or join one first")
        return getattr(game, name)

    def __setattr__(self, name: str, value) -> None:
        game = _ctx.get().game
        if game is None:
            raise HTTPException(409, "no game — create or join one first")
        setattr(game, name, value)


S = _GameProxy()
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
        "confidence": _fogged(gs, p.id, "confidence", p.confidence, fog),
        # Follower counts are public by nature; dev plans are the owning
        # manager's knobs (the UI only renders them for the user's team).
        "followers": p.followers,
        "dev_focus": p.dev_focus,
        "training_intensity": p.training_intensity,
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
        "starter_ids": default_five(gs, t.id),
        "record": {"wins": rec.wins, "losses": rec.losses, "diff": rec.diff}
        if rec
        else None,
    }


def _series_potm(f, gs: GameState) -> dict | None:
    """Player of the Match: the standout box-score line of a played series.
    Aggregates each player's mean rating across the series maps and prefers
    the winning side (identified by current roster membership), falling back
    to the overall top line if the winner's roster has since churned. A pure
    read of the stored per-map lines — no schema state, deterministic."""
    if not f.played or f.winner_id is None:
        return None
    agg: dict[str, list[float]] = {}  # pid -> [rating_sum, maps, kills]
    for r in f.results:
        for ln in r.lines:
            a = agg.setdefault(ln.player_id, [0.0, 0, 0])
            a[0] += ln.rating
            a[1] += 1
            a[2] += int(ln.kills)
    if not agg:
        return None
    winner_roster = (
        set(gs.teams[f.winner_id].player_ids) if f.winner_id in gs.teams else set()
    )

    def _mean(pid: str) -> float:
        rs, mp, _ = agg[pid]
        return rs / mp if mp else 0.0

    pool = [pid for pid in agg if pid in winner_roster] or list(agg)
    pid = max(sorted(pool), key=_mean)  # sorted -> deterministic tie-break
    p = gs.players.get(pid)
    rs, mp, kills = agg[pid]
    return {
        "player_id": pid,
        "handle": p.handle if p else pid,
        "rating": round(rs / mp, 2) if mp else 0.0,
        "kills": kills,
        "on_winner": pid in winner_roster,
    }


def _fixture_view(f, gs: GameState) -> dict:
    # A named rivalry between the two sides (symmetric pair heat), surfaced
    # only once it's genuinely hot — so the dashboard can flag a grudge
    # match before it's played. None when the pairing carries no history.
    riv = rivalries_mod.get(gs, f.team_a, f.team_b)
    return {
        "id": f.id,
        "week": f.week,
        "stage": f.stage,
        "best_of": f.best_of,
        "team_a": f.team_a,
        "team_b": f.team_b,
        "team_a_name": gs.teams[f.team_a].name,
        "team_b_name": gs.teams[f.team_b].name,
        "rivalry": round(riv, 1) if riv >= rivalries_mod.RIVALRY_BAR else None,
        "potm": _series_potm(f, gs),
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
# Lobby / game lifecycle


def _team_options(gs: GameState, taken: set[str]) -> list[dict]:
    return [
        {**_team_view(t, gs), "taken": t.id in taken}
        for t in sorted(gs.teams.values(), key=lambda t: t.id)
    ]


@app.get("/api/lobby")
def lobby() -> dict:
    """Pre-game screen. If this browser is already in a world, report it so the
    frontend jumps straight to the hub; otherwise return the team roster to
    pick from when starting a new (solo or shared) world."""
    ctx = _ctx.get()
    if ctx.game is not None and ctx.game.gs is not None:
        return {
            "in_game": True,
            "code": ctx.game.code,
            "team_id": ctx.team_id,
            "mode": ctx.game.mode,
            "humans": list(ctx.game.gs.human_team_ids),
        }
    preview = new_campaign(_LOBBY.gd, seed=2026)
    return {
        "in_game": False,
        "teams": _team_options(preview, taken=set()),
        "packs": _pack_options(),
        "worlds": _LOBBY.worlds_for(_current_sid()),
    }


_PACK_OPTIONS_CACHE: list[dict] | None = None


def _pack_options() -> list[dict]:
    """Installed roster packs with their pickable (tier-1) teams — straight
    from pack data, no campaign build needed. Cached for the process:
    packs are static data (rebuilding one means restarting the server)."""
    global _PACK_OPTIONS_CACHE
    if _PACK_OPTIONS_CACHE is not None:
        return _PACK_OPTIONS_CACHE
    out = []
    for meta in list_roster_packs():
        pack = load_roster_pack(meta.id)
        out.append(
            {
                "id": meta.id,
                "name": meta.name,
                "description": meta.description,
                "regions": [str(r) for r in meta.world.league_regions],
                "teams_per_region": meta.world.teams_per_region,
                "teams": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "tag": t.tag,
                        "region": str(t.region),
                    }
                    for t in sorted(
                        pack.teams.values(), key=lambda t: (str(t.region), t.id)
                    )
                    if t.tier == 1
                ],
            }
        )
    _PACK_OPTIONS_CACHE = out
    return out


@app.get("/api/lobby/teams")
def lobby_teams(code: str) -> dict:
    """Which teams are still free to claim in an existing shared world."""
    code = code.upper()
    with _LOBBY._lock:
        game = _LOBBY._get_game(code) if _CODE_RE.match(code) else None
    if game is None or game.gs is None:
        raise HTTPException(404, "no game with that code")
    with game.lock:
        return {
            "code": code,
            "mode": game.mode,
            "game_mode": game.gs.game_mode,
            "teams": _team_options(game.gs, taken=set(game.gs.human_team_ids)),
        }


class NewGameBody(BaseModel):
    team_id: str = "team_nexus"
    seed: int = 2026
    shared: bool = False  # True -> open the world for other managers to join
    pack: str | None = None  # roster pack id; None -> generated world
    game_mode: str = "sandbox"  # "sandbox" | "legacy"
    manager_name: str = ""


@app.post("/api/new")
def new_game(body: NewGameBody) -> dict:
    if body.game_mode not in ("sandbox", "legacy"):
        raise HTTPException(422, "game_mode must be 'sandbox' or 'legacy'")
    game = _LOBBY.create_game(
        _current_sid(), body.team_id, body.seed, body.shared,
        pack_id=body.pack, game_mode=body.game_mode,
        manager_name=body.manager_name,
    )
    return {
        "ok": True,
        "code": game.code,
        "team_id": body.team_id,
        "mode": game.mode,
    }


def _offer_view(gs: GameState, o) -> dict:
    t = gs.teams[o.team_id]
    return {
        "team_id": o.team_id,
        "team_name": t.name,
        "tag": t.tag,
        "region": str(t.region),
        "archetype": o.archetype,
        "seasons": o.seasons,
        "goal": career.GOAL_LABELS.get(o.goal, o.goal),
        "patience": o.patience,
        "blurb": o.blurb,
    }


@app.get("/api/lobby/offers")
def lobby_offers(
    seed: int = 2026, pack: str | None = None, code: str | None = None
) -> dict:
    """The legacy-mode career offers a manager starts from. Without
    `code`: the founding seat's slate for a new world (seed + pack).
    With `code`: the next joiner's slate for an existing shared world."""
    if code:
        code = code.upper()
        with _LOBBY._lock:
            game = _LOBBY._get_game(code) if _CODE_RE.match(code) else None
        if game is None or game.gs is None:
            raise HTTPException(404, "no game with that code")
        with game.lock:
            gs = game.gs
            if gs.game_mode != "legacy":
                raise HTTPException(409, "that world is a sandbox game")
            offers = career.new_game_offers(
                gs, len(gs.managers), taken=set(gs.human_team_ids)
            )
            return {"offers": [_offer_view(gs, o) for o in offers]}
    pk = None
    if pack:
        try:
            pk = load_roster_pack(pack)
        except FileNotFoundError:
            raise HTTPException(422, f"unknown roster pack '{pack}'") from None
    preview = new_campaign(_LOBBY.gd, seed=seed, pack=pk)
    offers = career.new_game_offers(preview, 0)
    return {"offers": [_offer_view(preview, o) for o in offers]}


class JoinBody(BaseModel):
    code: str
    team_id: str


@app.post("/api/join")
def join_game(body: JoinBody) -> dict:
    game, err = _LOBBY.join_game(
        _current_sid(), body.code.upper(), body.team_id
    )
    if err is not None:
        raise HTTPException(409, err)
    return {
        "ok": True,
        "code": game.code,
        "team_id": body.team_id,
        "mode": game.mode,
    }


@app.post("/api/leave")
def leave_game() -> dict:
    """Detach this browser from its world and return to the lobby. The world
    stays on disk and in this browser's resumable list."""
    code = _LOBBY.leave(_current_sid())
    return {"ok": True, "code": code}


class ResumeBody(BaseModel):
    code: str


@app.post("/api/resume")
def resume_game(body: ResumeBody) -> dict:
    game, err = _LOBBY.resume(_current_sid(), body.code.upper())
    if err is not None:
        raise HTTPException(409, err)
    m = _LOBBY.membership(_current_sid())
    return {
        "ok": True,
        "code": game.code,
        "team_id": m[1] if m else None,
        "mode": game.mode,
    }


# ---------------------------------------------------------------------------
# State views


def _career_state(gs: GameState) -> dict:
    """The acting session's career snapshot (both modes; sandbox seats
    just have no contract and can't be unemployed)."""
    seat = gs.seat_for_session(gs.acting_team_id)
    if seat is None:
        return {"mode": gs.game_mode, "seat": None}
    offers = gs.career_offers_by.get(seat.id) or []
    c = seat.contract
    return {
        "mode": gs.game_mode,
        "seat": {
            "id": seat.id,
            "name": seat.name,
            "team_id": seat.team_id,
            "archetype": seat.archetype,
            "unemployed": not seat.team_id,
        },
        "contract": (
            {
                "goal": career.GOAL_LABELS.get(c.goal, c.goal),
                "patience": round(c.patience, 1),
                "seasons": c.seasons,
                "start_season": c.start_season,
                "end_season": c.start_season + c.seasons - 1,
            }
            if c
            else None
        ),
        "offers": [_offer_view(gs, o) for o in offers],
        "blocked": bool(career.blocked_seats(gs)),
    }


@app.get("/api/career")
def career_profile() -> dict:
    """The acting manager's full career profile — a pure chronicle read."""
    with S.lock:
        gs = S.require_gs()
        seat = gs.seat_for_session(gs.acting_team_id)
        if seat is None:
            raise HTTPException(404, "no manager seat for this session")
        out = career.career_summary(gs, seat.id)
        out["team_name"] = (
            gs.teams[seat.team_id].name if seat.team_id in gs.teams else ""
        )
        return out


class AcceptJobBody(BaseModel):
    team_id: str


@app.post("/api/actions/accept_job")
def accept_job(body: AcceptJobBody) -> dict:
    """A dismissed legacy manager takes one of their offers. Rebinds the
    seat in GameState AND this browser session's team mapping."""
    ctx = _ctx.get()
    with S.lock:
        gs = S.require_gs()
        seat = gs.seat_for_session(gs.acting_team_id)
        if seat is None or seat.team_id:
            raise HTTPException(409, "you are not on the job market")
        ok, why = career.accept_offer(gs, seat.id, body.team_id)
        if not ok:
            raise HTTPException(409, why)
        game = ctx.game
        game.ready.discard(gs.acting_team_id)
        gs.set_acting(body.team_id)
        game.save()
    # Rebind the lobby session to the new club (outside the game lock;
    # the lobby has its own).
    with _LOBBY._lock:
        _LOBBY.sessions[_current_sid()] = (game.code, body.team_id)
        _LOBBY._remember(
            _current_sid(), game.code, body.team_id,
            game.gs.teams[body.team_id].name, game.mode,
        )
        _LOBBY._save_sessions()
    return {"ok": True, "team_id": body.team_id}


def _league_leaders(gs: GameState, n: int = 3) -> list[dict]:
    """This season's top tier-1 performers by rating (min 3 maps). A compact
    league-leaders read for the dashboard hub; pure gs.player_stats."""
    t1 = {pid for t in gs.teams.values() if t.tier == 1 for pid in t.player_ids}
    elig = [
        (pid, st) for pid, st in gs.player_stats.items()
        if st.maps >= 3 and pid in t1 and pid in gs.players
    ]
    top = sorted(elig, key=lambda kv: (-kv[1].rating, kv[0]))[:n]
    out = []
    for pid, st in top:
        team = next((t.name for t in gs.teams.values() if pid in t.player_ids), "")
        out.append({
            "pid": pid, "handle": gs.players[pid].handle, "team": team,
            "rating": round(st.rating, 2), "kills": st.kills,
        })
    return out


def _roster_movers(gs: GameState, tid: str, n: int = 4) -> list[dict]:
    """Your roster's biggest week-over-week current-ability movers (up or
    down), from the private dev-history series. Empty until two snapshots
    exist; sorted by absolute swing."""
    moves = []
    for pid in (gs.teams[tid].player_ids if tid in gs.teams else []):
        snaps = gs.dev_history.get(pid, [])
        if len(snaps) < 2:
            continue
        delta = round(snaps[-1].ca - snaps[-2].ca, 1)
        if abs(delta) >= 0.3 and pid in gs.players:
            moves.append({"pid": pid, "handle": gs.players[pid].handle, "delta": delta})
    moves.sort(key=lambda m: (-abs(m["delta"]), m["handle"]))
    return moves[:n]


@app.get("/api/state")
def state() -> dict:
    with S.lock:
        gs = S.require_gs()
        user = gs.teams[gs.acting_team_id]
        fixture = gs.team_fixture(gs.acting_team_id)
        order = gs.standings_order(str(user.region))
        # This-season head-to-head vs the upcoming opponent, from the acting
        # team's perspective. Attached only when they've met (silence beats a
        # "0-0" line); pure read of narrative.head_to_head.
        next_fixture = _fixture_view(fixture, gs) if fixture else None
        if next_fixture is not None:
            opp_id = (
                fixture.team_b if fixture.team_a == gs.acting_team_id
                else fixture.team_a
            )
            h = narrative.head_to_head(gs, gs.acting_team_id, opp_id)
            if h["meetings"]:
                next_fixture["h2h"] = {
                    "meetings": h["meetings"],
                    "wins": h["wins_a"],  # acting team's series wins
                    "losses": h["wins_b"],
                    "streak_team": h["streak_winner_id"],
                    "streak_len": h["streak_len"],
                    "you_lead": h["wins_a"] > h["wins_b"],
                }
        return {
            "season": gs.season,
            "week": gs.week,
            "phase": gs.phase,
            "user_team": _team_view(user, gs),
            "next_fixture": next_fixture,
            # Dashboard hub extras: this season's rating leaders (league-wide)
            # and your roster's biggest week-over-week ability movers.
            "leaders": _league_leaders(gs),
            "movers": _roster_movers(gs, gs.acting_team_id),
            "training_focus": gs.training_focus.get(gs.acting_team_id, "tactical"),
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
                    "to_team": o.to_team,
                    "to_team_name": gs.teams[o.to_team].name,
                    "fee": o.fee,
                    "expires_week": o.expires_week,
                    # Package extras (empty/zero for a plain cash bid).
                    "offer_players": [
                        {"id": pid, "handle": gs.players[pid].handle}
                        for pid in o.offer_player_ids
                        if pid in gs.players
                    ],
                    "cash_to_seller": o.cash_to_seller,
                    "cash_to_buyer": o.cash_to_buyer,
                }
                for o in gs.transfer_offers
                # Only bids for THIS manager's players (they answer them).
                if o.from_team == gs.acting_team_id
                and o.player_id in gs.players
                and o.to_team in gs.teams
            ],
            # Legacy-mode career state for the acting seat: contract +
            # patience while employed; pending offers while between jobs
            # (the dashboard renders the job market off this).
            "career": _career_state(gs),
            # Multiplayer ready-up: who shares this world, and who has hit
            # "advance". In a solo game humans == [you] so it's a no-op.
            "multiplayer": {
                "mode": S.mode,
                "code": S.code,
                "humans": [
                    {"team_id": tid, "name": gs.teams[tid].name, "is_you": tid == gs.acting_team_id}
                    for tid in gs.human_team_ids
                ],
                "ready": sorted(S.ready),
                "you_ready": gs.acting_team_id in S.ready,
            },
        }


@app.get("/api/inbox")
def inbox_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        return {
            "unread": inbox_mod.unread_count(gs),
            # Pass gs so offer items whose offer is still live carry Accept/
            # Decline actions (existing mutation endpoints) inline in the feed.
            "items": [inbox_mod.to_api(it, gs) for it in inbox_mod.sorted_items(gs)],
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
# Scout coverage that unlocks a rival's committed lineup (their per-player agent
# locks) — same tier as reading their coaching identity.
LINEUP_REVEAL_PROGRESS = 0.5


def _team_fog(gs: GameState, team_id: str) -> float:
    if team_id == gs.acting_team_id:
        return 0.0
    return FOG_BASE_SIGMA * (1.0 - gs.scout_progress.get(team_id, 0.0))


def _trend_dir(now: float, then: float, eps: float) -> str:
    d = now - then
    return "up" if d > eps else "down" if d < -eps else "flat"


def _condition_trend(gs: GameState, pid: str) -> dict | None:
    """Direction of a player's CA / form / confidence over the last couple
    of weeks, from their private dev-history series (human rosters only).
    None until there are two points to compare."""
    snaps = gs.dev_history.get(pid, [])
    if len(snaps) < 2:
        return None
    last = snaps[-1]
    prev = snaps[-min(3, len(snaps))]  # ~2 weeks back when available
    return {
        "ca": _trend_dir(last.ca, prev.ca, 0.3),
        "form": _trend_dir(last.form, prev.form, 1.5),
        "confidence": _trend_dir(last.confidence, prev.confidence, 2.0),
    }


def _team_tendencies(tac) -> list[str]:
    """Plain-language reads of a team's coaching dials, off their poles.
    The single source for the scouting-report tendency list (own club or a
    well-scouted rival)."""
    out: list[str] = []
    if tac.aggression >= 62:
        out.append("swings angles aggressively")
    elif tac.aggression <= 38:
        out.append("holds passive angles")
    if tac.pace >= 62:
        out.append("hits sites fast")
    elif tac.pace <= 38:
        out.append("plays slow defaults")
    if tac.site_focus != "balanced":
        out.append(f"{tac.site_focus.upper()}-heavy attack")
    if tac.eco_greed >= 62:
        out.append("force-buys relentlessly")
    if tac.map_control >= 62:
        out.append("spreads wide and lurks for picks")
    elif tac.map_control <= 38:
        out.append("stacks tight and hits as five")
    return out


# Bipolar identity words per dial (value>50 -> first, <50 -> second).
_IDENTITY_POLES: tuple[tuple[str, str, str], ...] = (
    ("aggression", "Aggressive", "Passive"),
    ("pace", "Fast-paced", "Methodical"),
    ("map_control", "Map-spreading", "Compact"),
    ("eco_greed", "Big-spending", "Thrifty"),
    ("utility_discipline", "Disciplined", "Loose"),
)


def _team_identity_label(tac) -> str:
    """A one-word coaching identity from the single most-committed dial, or
    'Balanced' when nothing is off neutral. Same neutral-50 vocabulary the
    tactics system uses, so the label never contradicts the tendencies."""
    best_dev, best = 0.0, "Balanced"
    for dial, hi, lo in _IDENTITY_POLES:
        val = getattr(tac, dial, 50.0)
        dev = abs(val - 50.0)
        if dev > best_dev:
            best_dev, best = dev, (hi if val > 50.0 else lo)
    return best if best_dev >= 12.0 else "Balanced"


@app.get("/api/roster/{team_id}")
def roster(team_id: str) -> dict:
    with S.lock:
        gs = S.require_gs()
        if team_id not in gs.teams:
            raise HTTPException(404, "unknown team")
        fog = _team_fog(gs, team_id)
        players = [_player_view(p, gs, fog) for p in gs.roster(team_id)]
        team = gs.teams[team_id]
        own = team_id == gs.acting_team_id
        # Own club always sees its locks; a rival's leak once you've scouted them
        # far enough to read their strategy. Below that, the agent column fogs.
        lineup_revealed = own or gs.scout_progress.get(team_id, 0.0) >= LINEUP_REVEAL_PROGRESS
        if lineup_revealed:
            for v in players:
                pl = gs.players[v["id"]]
                aid = lineup_resolve.resolve_agent(team, pl, S.gd.agents)
                v["planned_agent"] = S.gd.agents[aid].display_name
                v["planned_agent_id"] = aid
                # Distinguish a committed lock from the engine's likely auto-pick.
                locked = team.lineup.agents.get(v["id"])
                v["planned_locked"] = bool(locked and locked in S.gd.agents)
        # Rival rosters are buyable: show the seller's ask per player.
        tendencies: list[str] = []
        identity: str | None = None
        if team_id != gs.acting_team_id:
            for v in players:
                v["transfer_ask"] = market.transfer_ask(gs, v["id"])
        # Coaching identity: always readable for your own club, and for a
        # rival once you've scouted them enough to read their style.
        if own or gs.scout_progress.get(team_id, 0.0) >= 0.5:
            tac = gs.teams[team_id].tactics
            tendencies = _team_tendencies(tac)
            identity = _team_identity_label(tac)
        # Own club: a quick-glance form/confidence trend per player, from the
        # private dev-history time series (empty -> None, no arrow shown).
        if own:
            for v in players:
                v["condition_trend"] = _condition_trend(gs, v["id"])
        # Starter flags + (for a deep own roster) the upcoming fixture's per-map
        # dressed lineups, so the UI can pick who plays each map.
        starters = set(default_five(gs, team_id))
        for v in players:
            v["starter"] = v["id"] in starters
        upcoming = None
        is_user = team_id == gs.acting_team_id
        if is_user and len(gs.roster(team_id)) > market.ROSTER_SIZE:
            fx = next(
                (
                    f
                    for f in sorted(gs.fixtures, key=lambda x: (x.week, x.id))
                    if f.tier == 1
                    and not f.played
                    and team_id in (f.team_a, f.team_b)
                    and f.week >= gs.week
                ),
                None,
            )
            if fx is not None:
                opp = fx.team_a if fx.team_b == team_id else fx.team_b
                upcoming = {
                    "fixture_id": fx.id,
                    "opponent": gs.teams[opp].name,
                    "best_of": fx.best_of,
                    "maps": [
                        {
                            "map_id": m,
                            "dressed": dressed_for(gs, team_id, fx, m),
                            "has_override": f"{team_id}|{fx.id}|{m}"
                            in gs.map_lineups,
                        }
                        for m in fx.maps
                    ],
                }
        return {
            "team": _team_view(gs.teams[team_id], gs),
            "players": players,
            "is_user_team": team_id == gs.acting_team_id,
            "lineup_ids": list(gs.teams[team_id].lineup_ids),
            "roster_min": market.ROSTER_MIN,
            "roster_max": market.roster_cap(gs, team_id),
            "upcoming": upcoming,
            "dev_focus_options": DEV_FOCUS_OPTIONS,
            "intensity_options": INTENSITY_OPTIONS,
            "fog": round(fog, 1),
            "lineup_revealed": lineup_revealed,
            "scouting_this": gs.scout_target == team_id,
            "scout_progress": gs.scout_progress.get(team_id, 0.0),
            "tendencies": tendencies,
            "identity": identity,
            "chemistry_pairs": {
                kind: [
                    [gs.players[a].handle, gs.players[b].handle]
                    for a, b in pairs
                    if a in gs.players and b in gs.players
                ]
                for kind, pairs in relationships.duos_and_feuds(gs, team_id).items()
            }
            if team_id == gs.acting_team_id
            else {"duos": [], "feuds": []},
        }


def _team_recent_form(gs: GameState, tid: str, n: int = 5) -> list[dict]:
    """The team's last `n` played fixtures as compact W/L chips (oldest
    first, so the table reads left-to-right up to the most recent). Pure
    read of gs.fixtures — the same source the recap and streak use."""
    played = sorted(
        (
            f for f in gs.fixtures
            if f.played and f.winner_id is not None and tid in (f.team_a, f.team_b)
        ),
        key=lambda f: (f.week, f.id),
    )[-n:]
    out = []
    for f in played:
        opp = f.team_b if tid == f.team_a else f.team_a
        a, b = f.map_score
        score = f"{a}-{b}" if tid == f.team_a else f"{b}-{a}"
        out.append(
            {
                "result": "W" if f.winner_id == tid else "L",
                "opponent": gs.teams[opp].name if opp in gs.teams else opp,
                "score": score,
                "week": f.week,
            }
        )
    return out


PLAYOFF_CUT = 4  # regional playoffs take the top four of the regular season


def _eliminated_teams(gs: GameState, region: str) -> set[str]:
    """Tier-1 teams in `region` that can no longer reach the top-4 playoff
    cut, however every remaining regular-season game falls. Correct
    regardless of tiebreakers — it uses only strict win comparisons: a team
    X is out when at least four rivals already have more wins than X could
    reach by winning out. Empty outside the regular season."""
    if gs.phase != "regular":
        return set()
    tids = [
        t.id for t in gs.teams.values()
        if str(t.region) == region and t.tier == 1
    ]
    wins = {tid: (gs.standings[tid].wins if tid in gs.standings else 0) for tid in tids}
    remaining = {tid: 0 for tid in tids}
    for f in gs.fixtures:
        if f.tier != 1 or f.stage != "regular" or f.played:
            continue
        if f.team_a in remaining:
            remaining[f.team_a] += 1
        if f.team_b in remaining:
            remaining[f.team_b] += 1
    out: set[str] = set()
    for x in tids:
        x_ceiling = wins[x] + remaining[x]
        certainly_ahead = sum(1 for y in tids if y != x and wins[y] > x_ceiling)
        if certainly_ahead >= PLAYOFF_CUT:
            out.add(x)
    return out


@app.get("/api/standings")
def standings() -> dict:
    with S.lock:
        gs = S.require_gs()

        def rows_for(region: str | None, tier: int = 1) -> list[dict]:
            elim = _eliminated_teams(gs, region) if (region and tier == 1) else set()
            rows = []
            for tid in gs.standings_order(region, tier=tier):
                idx = analytics.dynasty_index(gs, tid) if tier == 1 else 0.0
                rows.append({
                    **_team_view(gs.teams[tid], gs),
                    **gs.standings[tid].model_dump(),
                    "diff": gs.standings[tid].diff,
                    "recent_form": _team_recent_form(gs, tid),
                    "eliminated": tid in elim,
                    "dynasty": analytics.dynasty_label(idx),
                })
            return rows

        user_region = str(gs.teams[gs.acting_team_id].region)
        regions = sorted(gs.regions(), key=lambda r: (r != user_region, r))
        return {
            "playoff_cut": PLAYOFF_CUT,  # rows above this line are in the hunt
            "in_regular_season": gs.phase == "regular",
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


@app.get("/api/records")
def records() -> dict:
    """The save's all-time record book + current top dynasties (pure
    chronicle + career_stats read; manager/analytics.py)."""
    with S.lock:
        return analytics.all_time_records(S.require_gs())


@app.get("/api/report/season")
def season_report(season: int | None = None) -> dict:
    """A deterministic structured season summary — the headless analytics
    export (ROADMAP bet #2), also consumable by the web Season Review."""
    with S.lock:
        return analytics.season_report(S.require_gs(), season)


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


_CORE_ROLES = ("duelist", "controller", "initiator", "sentinel", "flex")


def _squad_needs(gs: GameState, tid: str) -> dict:
    """Role balance of the squad + the biggest gap and weakest position, to
    steer the market. Pure read of the roster's roles + quality."""
    counts = {r: 0 for r in _CORE_ROLES}
    quality: dict[str, list[float]] = {r: [] for r in _CORE_ROLES}
    for p in gs.roster(tid):
        r = str(p.role)
        if r in counts:
            counts[r] += 1
            quality[r].append(market.player_quality(p))
    # A gap is a CORE role (not flex) nobody covers.
    gaps = [r for r in _CORE_ROLES if r != "flex" and counts[r] == 0]
    present = [(r, sum(q) / len(q)) for r, q in quality.items() if q]
    weakest = min(present, key=lambda rc: (rc[1], rc[0])) if present else None
    return {
        "role_counts": counts,
        "gaps": gaps,
        "weakest_role": (
            {"role": weakest[0], "quality": round(weakest[1], 1)} if weakest else None
        ),
    }


def _target_suggestions(gs: GameState, tid: str, needs: dict, n: int = 3) -> list[dict]:
    """The best free agents that address the squad's priority role (a gap
    first, else its weakest position), affordability flagged. Pure read."""
    want = set(needs["gaps"])
    if not want and needs["weakest_role"]:
        want = {needs["weakest_role"]["role"]}
    cands = []
    for pid in gs.free_agent_ids:
        p = gs.players.get(pid)
        if p is None or (want and str(p.role) not in want):
            continue
        ok, _ = market.can_sign(gs, tid, pid)
        cands.append((p, ok))
    cands.sort(key=lambda pc: (-market.player_quality(pc[0]), pc[0].id))
    return [
        {
            "id": p.id, "handle": p.handle, "role": str(p.role),
            "quality": round(market.player_quality(p), 1), "affordable": ok,
        }
        for p, ok in cands[:n]
    ]


def _contract_watch(gs: GameState, tid: str, weeks: int = 8, n: int = 5) -> dict:
    """Your players entering their final weeks (renewal urgency) plus notable
    tier-1 rivals nearing free agency (signing opportunities). Pure read."""
    own = sorted(
        (
            {"id": p.id, "handle": p.handle, "role": str(p.role),
             "weeks_left": p.contract_weeks_left}
            for p in gs.roster(tid)
            if 0 < p.contract_weeks_left <= weeks
        ),
        key=lambda x: (x["weeks_left"], x["handle"]),
    )
    rivals = []
    for t in gs.teams.values():
        if t.tier != 1 or t.id == tid:
            continue
        for pid in t.player_ids:
            p = gs.players.get(pid)
            if p and 0 < p.contract_weeks_left <= weeks:
                rivals.append((p, t))
    rivals.sort(key=lambda pt: (-market.player_quality(pt[0]), pt[0].id))
    market_watch = [
        {"id": p.id, "handle": p.handle, "role": str(p.role),
         "team": t.name, "weeks_left": p.contract_weeks_left}
        for p, t in rivals[:n]
    ]
    return {"expiring_own": own, "market_watch": market_watch}


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
            ok, why = market.can_sign(gs, gs.acting_team_id, p.id)
            view = _player_view(p, gs, fog=6.0 * (1.0 - progress))
            report = development.scout_report(gs, p, progress)
            view["scout"] = {
                "ca_stars": report["ca_stars"],
                "pa_stars": report["pa_stars"] if progress > 0 else None,
                "traits": report["traits"],
                "traits_hidden": report["traits_hidden"],
            }
            out.append({**view, "can_sign": ok, "block_reason": why})
        me = gs.acting_team_id
        needs = _squad_needs(gs, me)
        return {
            "free_agents": out,
            "roster_size": market.ROSTER_SIZE,
            "roster_min": market.ROSTER_MIN,
            "roster_max": market.roster_cap(gs, me),
            "roster_count": len(gs.roster(me)),
            "phase": gs.phase,
            # Decision aids: where the squad is thin, who to sign, and whose
            # contracts are running down (yours + rivals'). All pure reads.
            "squad_needs": needs,
            "target_suggestions": _target_suggestions(gs, me, needs),
            "contract_watch": _contract_watch(gs, me),
            # Own roster, for the "swap" (sign + drop in one) control.
            "my_roster": [
                {
                    "id": p.id,
                    "handle": p.handle,
                    "overall": int(round(development.overall(p))),
                    "value": market.transfer_value(p),
                }
                for p in gs.roster(me)
            ],
            "market_scouting": round(progress, 2),
        }


# ---------------------------------------------------------------------------
# Stats hub. Column depth is gated by the org's ANALYTICS department (the
# analyst's quality + the analytics-suite facility, see staff.analytics_tier):
# tier 0 reads box scores, tier 1 adds duel detail, tier 2 adds round
# context, tier 3 unlocks the full splits and trend charts. The gate lives
# HERE, server-side — the client renders whatever fields arrive.


def _season_stat_row(gs: GameState, pid: str, st: PlayerSeasonStats, tier: int) -> dict:
    p = gs.players[pid]
    row = {
        "player_id": pid,
        "handle": p.handle,
        "team": next(
            (t.name for t in gs.teams.values() if pid in t.player_ids), "FA"
        ),
        "maps": st.maps,
        "rounds": st.rounds,
        "kills": st.kills,
        "deaths": st.deaths,
        "kd": round(st.kd, 2),
        "rating": round(st.rating, 2),
        "plants": st.plants,
        "defuses": st.defuses,
        "is_user": pid in gs.teams[gs.acting_team_id].player_ids,
    }
    if tier >= 1:
        row.update(
            first_kills=st.first_kills,
            first_deaths=st.first_deaths,
            fk_fd=round(st.fk_fd, 2),
            hs_pct=round(st.hs_pct, 1),
            acs=round(st.acs, 1),
            multikills=st.multikills,
            aces=st.aces,
            clutches=st.clutch_1v1 + st.clutch_1v2 + st.clutch_1v3,
            pistol_kills=st.pistol_kills,
        )
    if tier >= 2:
        row.update(
            assists=st.assists,
            kast_pct=round(st.kast_pct, 1),
            trade_kills=st.trade_kills,
            clutch_1v1=st.clutch_1v1,
            clutch_1v2=st.clutch_1v2,
            clutch_1v3=st.clutch_1v3,
            eco_kills=st.eco_kills,
            save_kills=st.save_kills,
            kills_by_weapon=dict(
                sorted(
                    st.kills_by_weapon.items(), key=lambda kv: (-kv[1], kv[0])
                )
            ),
        )
    return row


def _analytics_view(gs: GameState) -> dict:
    tier = staff_mod.analytics_tier(gs)
    nxt = (
        None
        if tier >= 3
        else staff_mod.ANALYTICS_TIER_LABEL[tier + 1]
    )
    return {
        "tier": tier,
        "label": staff_mod.ANALYTICS_TIER_LABEL[tier],
        "next_unlock": nxt,
    }


@app.get("/api/stats")
def stats_view(split: str | None = None, key: str | None = None) -> dict:
    """League stats. `split=map&key=<map_id>` or `split=agent&key=<agent_id>`
    swaps the player table for that split (analytics tier 3 only)."""
    with S.lock:
        gs = S.require_gs()
        analytics = _analytics_view(gs)
        tier = analytics["tier"]

        source: dict[str, PlayerSeasonStats] = gs.player_stats
        if split in ("map", "agent") and key:
            if tier < 3:
                raise HTTPException(
                    409, "per-map and per-agent splits need an elite analytics "
                    "department (tier 3)"
                )
            table = gs.player_map_stats if split == "map" else gs.player_agent_stats
            source = {
                pid: by_key[key]
                for pid, by_key in table.items()
                if key in by_key
            }

        players = []
        for pid in sorted(source):
            st = source[pid]
            if pid not in gs.players or st.maps == 0:
                continue
            players.append(_season_stat_row(gs, pid, st, tier))
        players.sort(key=lambda r: (-r["rating"], -r["kills"]))

        teams = []
        for tid in gs.standings_order():
            ts = gs.team_stats.get(tid)
            if ts is None or ts.maps == 0:
                continue
            row = {
                "team_id": tid,
                "name": gs.teams[tid].name,
                "maps": ts.maps,
                "atk_pct": round(100 * ts.atk_won / max(ts.atk_rounds, 1), 1),
                "def_pct": round(100 * ts.def_won / max(ts.def_rounds, 1), 1),
                "pistol_pct": round(100 * ts.pistols_won / max(ts.pistols, 1), 1),
                "is_user": tid == gs.acting_team_id,
            }
            if tier >= 2:
                row["maps_detail"] = [
                    {
                        "map_id": mid,
                        "map_thumb": _map_thumb_url(mid),
                        "maps": tm.maps,
                        "wins": tm.wins,
                        "win_pct": round(100 * tm.wins / max(tm.maps, 1), 1),
                        "atk_pct": round(
                            100 * tm.atk_won / max(tm.atk_rounds, 1), 1
                        ),
                        "def_pct": round(
                            100 * tm.def_won / max(tm.def_rounds, 1), 1
                        ),
                    }
                    for mid, tm in sorted(gs.team_map_stats.get(tid, {}).items())
                ]
            teams.append(row)

        # Split pickers (which maps/agents have data) — tier 3 only.
        split_keys = None
        if tier >= 3:
            maps_seen: set[str] = set()
            agents_seen: set[str] = set()
            for by_key in gs.player_map_stats.values():
                maps_seen.update(by_key)
            for by_key in gs.player_agent_stats.values():
                agents_seen.update(by_key)
            split_keys = {"maps": sorted(maps_seen), "agents": sorted(agents_seen)}

        return {
            "analytics": analytics,
            "split": {"kind": split, "key": key} if split and key else None,
            "split_keys": split_keys,
            "players": players,
            "teams": teams,
            "awards": [a.model_dump() for a in reversed(gs.awards)],
            # Patch notes are public information — never tier-gated.
            "patches": [n.model_dump() for n in reversed(gs.patch_history[-6:])],
            # The Hall of Fame — public history, never tier-gated.
            "hall_of_fame": [
                h.model_dump() for h in reversed(gs.hall_of_fame)
            ],
        }


@app.get("/api/finances")
def finances() -> dict:
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        payroll = sum(p.salary for p in gs.roster(gs.acting_team_id))
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
                        # Live in-season progress toward this bonus (read-only).
                        "status": career.objective_status(
                            gs, gs.acting_team_id, ob.kind
                        ),
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
            # Per-manager: the shared report carries every human's income/
            # expenses, so read the acting manager's slice.
            "last_week_income": rep.income_by.get(gs.acting_team_id) if rep else None,
            "last_week_expenses": rep.expenses_by.get(gs.acting_team_id)
            if rep
            else None,
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
        team = gs.teams[gs.acting_team_id]
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
        gs.training_focus[gs.acting_team_id] = body.focus
        S.save()
        return {"ok": True, "focus": body.focus}


def _staff_member_view(gs: GameState, m, employer_id: str | None = None) -> dict:
    return {
        **m.model_dump(),
        "specialty_blurb": staff_mod.SPECIALTY_BLURB.get(m.specialty, ""),
        "employer_id": employer_id,
        "employer_name": gs.teams[employer_id].name if employer_id else None,
    }


@app.get("/api/staff")
def staff_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        if len(gs.staff_pool) < 20:
            # Pre-v3 saves arrive with a near-empty market: build it lazily
            # (each member is a pure function of seed + id, so no drift).
            # A healthy pool thins as managers hire and replenishes at the
            # offseason churn — hiring is not instantly backfilled.
            staff_mod.seed_pool(gs)
            S.save()
        pool = sorted(gs.staff_pool, key=lambda m: (m.role, -m.quality, m.id))
        return {
            "hired": {
                r: _staff_member_view(gs, m, gs.acting_team_id)
                for r, m in sorted(gs.staff.items())
            },
            "pool": [_staff_member_view(gs, m) for m in pool],
            "roles": staff_mod.ROLES,
            "blurbs": staff_mod.ROLE_BLURB,
            "weekly_cost": staff_mod.weekly_cost(gs),
            "analytics": _analytics_view(gs),
        }


def _staff_effect_lines(m) -> list[str]:
    """What this member does for the org, in plain lines (server-computed —
    the client never re-derives an effect formula)."""
    if m.role == "coach":
        lines = [f"+{m.quality / 2:.0f}% weekly training growth"]
        if m.specialty:
            lines.append(
                f"+{int(staff_mod.SPECIALTY_GROWTH_BONUS * 100)}% extra on "
                f"{m.specialty} weeks (their specialty)"
            )
        return lines
    if m.role == "analyst":
        return [
            f"+{m.quality:.0f}% scouting speed",
            "deeper stat views (analytics tier, with the analytics suite)",
        ]
    return [f"+{m.quality / 18.0:.1f} stamina per player per week"]


@app.get("/api/staff/{staff_id}/profile")
def staff_profile(staff_id: str) -> dict:
    """A coach/analyst/physio profile page — the staff analogue of the
    player profile overlay."""
    with S.lock:
        gs = S.require_gs()
        m, employer = staff_mod.find_member(gs, staff_id)
        if m is None:
            raise HTTPException(404, "unknown staff member")
        return {
            "member": _staff_member_view(gs, m, employer),
            "effects": _staff_effect_lines(m),
            "role_blurb": staff_mod.ROLE_BLURB.get(m.role, ""),
            "hire_cost_note": f"{m.salary * 8:,} cr banked to hire",
            "is_yours": employer == gs.acting_team_id,
            "in_pool": employer is None,
        }


@app.get("/api/social")
def social_view() -> dict:
    """The feed plus follower leaderboards. World-visible by design.

    When an LLM provider is configured (OpenRouter key in .env or a
    local OpenAI-compatible server; see web/llm_social.py), post text is
    overlaid from the sidecar rewrite cache — the deterministic template
    text stays in the save and serves as the grounded fallback."""
    game = _ctx.get().game
    with S.lock:
        gs = S.require_gs()
        # Catch-up pass: worlds resumed on a fresh process (or with a
        # freshly configured provider) get their recent posts written.
        llm_social.enqueue(game)

        def team_of(pid: str) -> tuple[str | None, str]:
            t = next((t for t in gs.teams.values() if pid in t.player_ids), None)
            return (t.id, t.tag) if t else (None, "FA")

        top = sorted(
            (p for p in gs.players.values()),
            key=lambda p: (-p.followers, p.id),
        )[:15]
        leaderboard = []
        for p in top:
            tid, tag = team_of(p.id)
            leaderboard.append(
                {
                    "player_id": p.id,
                    "handle": p.handle,
                    "team_tag": tag,
                    "followers": p.followers,
                    "is_user": tid == gs.acting_team_id,
                }
            )
        roster = gs.roster(gs.acting_team_id)
        # Community mood board: hottest and coldest fanbases (tier-1 orgs).
        sent_rows = sorted(
            (
                {
                    "team_id": t.id,
                    "name": t.name,
                    "tag": t.tag,
                    "sentiment": gs.sentiment(t.id),
                    # Mood word/tone computed HERE from the sim's own
                    # thresholds — the client renders, never re-derives.
                    **social.mood_view(gs.sentiment(t.id)),
                    "is_user": t.id == gs.acting_team_id,
                }
                for t in gs.teams.values()
                if t.tier == 1
            ),
            key=lambda r: (-r["sentiment"], r["team_id"]),
        )
        return {
            "feed": llm_social.overlay(
                game.code, [p.model_dump() for p in reversed(gs.social_feed)]
            ),
            "leaderboard": leaderboard,
            "your_roster": [
                {
                    "player_id": p.id,
                    "handle": p.handle,
                    "followers": p.followers,
                }
                for p in sorted(roster, key=lambda p: (-p.followers, p.id))
            ],
            "your_reach": social.roster_reach(gs, gs.acting_team_id),
            "fan_count": gs.teams[gs.acting_team_id].fan_count,
            "sentiment": sent_rows,
            "your_sentiment": gs.sentiment(gs.acting_team_id),
            "your_mood": social.mood_view(gs.sentiment(gs.acting_team_id)),
        }


class DevPlanBody(BaseModel):
    player_id: str
    dev_focus: str | None = None
    training_intensity: str | None = None


@app.post("/api/actions/dev_plan")
def dev_plan_action(body: DevPlanBody) -> dict:
    """Set a player's individual development plan (own roster only)."""
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        if body.player_id not in team.player_ids:
            raise HTTPException(409, "player is not on your roster")
        p = gs.players[body.player_id]
        if body.dev_focus is not None:
            if body.dev_focus not in DEV_FOCUS_OPTIONS:
                raise HTTPException(
                    422, f"dev_focus must be one of {DEV_FOCUS_OPTIONS}"
                )
            p.dev_focus = body.dev_focus
        if body.training_intensity is not None:
            if body.training_intensity not in INTENSITY_OPTIONS:
                raise HTTPException(
                    422, f"training_intensity must be one of {INTENSITY_OPTIONS}"
                )
            p.training_intensity = body.training_intensity
        S.save()
        return {
            "ok": True,
            "message": f"{p.handle}: {p.dev_focus} focus, "
            f"{p.training_intensity} intensity",
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


def _tactics_fit(gs: GameState, team: Team) -> dict:
    """Per-dial roster-fit data for the tactics screen. The match modifier is
    computed HERE, on the server, from the same code the engine runs
    (sim/tactics_fit.py) — the UI never recomputes a sim term. Each dial's
    duel impact is exactly piecewise-linear in the dial value with its knot at
    the neutral 50, so we hand the client the two endpoint impacts (`impact_lo`
    at value 0, `impact_hi` at value 100) and it does nothing but linearly
    interpolate between them and the neutral zero."""
    roster = [gs.players[pid] for pid in team.player_ids if pid in gs.players]
    reg = S.gd.attributes.definitions
    chem_edge = tactics_fit.chem_edge(team.chemistry)
    dials = []
    for key, attr_ids in tactics_fit.DIAL_FIT_ATTRS.items():
        names = [reg[a].display_name if a in reg else a for a in attr_ids]
        pfits = [tactics_fit.player_fit(p.attr(a) for a in attr_ids) for p in roster]
        scored = [
            {"handle": p.handle, "playstyle": str(p.playstyle), "score": round(pf)}
            for p, pf in zip(roster, pfits)
        ]
        scored.sort(key=lambda s: -s["score"])
        fit = sum(pfits) / len(pfits) if pfits else 50.0
        # Fit term is symmetric about 50; the chemistry term rides only the
        # HIGH side of the coordination-heavy dials — so the two poles differ.
        edge = tactics_fit.fit_edge(pfits)
        gated = key in tactics_fit.CHEM_GATED
        dials.append(
            {
                "key": key,
                "attrs": names,
                "fit": round(fit, 1),
                "impact_lo": round(edge, 4),
                "impact_hi": round(edge + (chem_edge if gated else 0.0), 4),
                "chem_gated": gated,
                "players": scored,
            }
        )
    return {
        "chemistry": round(team.chemistry, 1),
        "mod_cap": C.EXEC_MOD_CAP,
        "dials": dials,
    }


def _lineup_view(gs: GameState, team: Team) -> dict:
    """The week's lineup for the tactics screen: every starter with the full
    agent menu, the coach's current lock (if any), and the automatic pick. The
    resolved agent comes from sim/lineup.py — the same code the engine fields —
    so the preview can't drift from what actually gets played."""
    agents = S.gd.agents
    players = []
    for pid in team.player_ids:
        if pid not in gs.players:
            continue
        pl = gs.players[pid]
        # Every agent is offerable; mastery (0 off-pool) is the honest cost cue.
        options = sorted(
            (
                {
                    "id": a.id,
                    "name": a.display_name,
                    "role": str(a.role),
                    "mastery": round(pl.agent_mastery(a.id, 0.0)),
                }
                for a in agents.values()
            ),
            key=lambda o: (-o["mastery"], o["name"]),
        )
        assigned = team.lineup.agents.get(pid)
        assigned = assigned if (assigned and assigned in agents) else None
        auto = lineup_resolve.auto_pick_agent(pl, agents)
        resolved = assigned or auto
        players.append(
            {
                "id": pid,
                "handle": pl.handle,
                "role": str(pl.role),
                "playstyle": str(pl.playstyle),
                "options": options,
                "assigned": assigned,
                "auto_id": auto,
                "auto_name": agents[auto].display_name,
                "resolved_id": resolved,
                "resolved_name": agents[resolved].display_name,
            }
        )
    return {"players": players}


@app.get("/api/tactics")
def tactics_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        return {
            "tactics": team.tactics.model_dump(),
            "fit": _tactics_fit(gs, team),
            "lineup": _lineup_view(gs, team),
        }


class LineupBody(BaseModel):
    """One endpoint for every lineup lever; any subset may be set per call.
    (Two same-path routes used to coexist here — Starlette serves the FIRST
    match, so the second was silently dead. Unified so default-lineup saves
    actually land.)"""

    # player_id -> agent_id lock. An empty/absent value clears that player
    # back to the automatic pick.
    agents: dict[str, str] | None = None
    # The team's default starting five (order = dressing preference).
    lineup_ids: list[str] | None = None
    # A per-map override: dress exactly five for (fixture_id, map_id).
    fixture_id: str | None = None
    map_id: str | None = None
    player_ids: list[str] | None = None


@app.post("/api/actions/lineup")
def set_lineup(body: LineupBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        me = gs.acting_team_id
        team = gs.teams[me]
        roster = set(team.player_ids)
        if body.agents is not None:
            new: dict[str, str] = {}
            for pid, aid in body.agents.items():
                if pid not in roster:
                    raise HTTPException(422, f"{pid} is not on your roster")
                if not aid:  # "" / null → auto-pick (leave unset)
                    continue
                if aid not in S.gd.agents:
                    raise HTTPException(422, f"unknown agent {aid}")
                new[pid] = aid
            team.lineup.agents = new
        if body.lineup_ids is not None:
            picks = [pid for pid in body.lineup_ids if pid in roster]
            if len(picks) > market.ROSTER_SIZE:
                raise HTTPException(
                    422, f"a lineup is at most {market.ROSTER_SIZE}"
                )
            team.lineup_ids = picks
        if body.player_ids is not None:
            if not (body.fixture_id and body.map_id):
                raise HTTPException(
                    422, "a per-map lineup needs fixture_id + map_id"
                )
            picks = [pid for pid in body.player_ids if pid in roster]
            if len(picks) != market.ROSTER_SIZE:
                raise HTTPException(
                    422, f"dress exactly {market.ROSTER_SIZE} players for a map"
                )
            gs.map_lineups[f"{me}|{body.fixture_id}|{body.map_id}"] = picks
        S.save()
        return {
            "ok": True,
            "message": "lineup saved",
            "lineup": _lineup_view(gs, team),
        }


class TacticsBody(BaseModel):
    aggression: float | None = None
    pace: float | None = None
    util_discipline: float | None = None
    eco_greed: float | None = None
    map_control: float | None = None
    site_focus: str | None = None


@app.post("/api/actions/tactics")
def set_tactics(body: TacticsBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        tac = gs.teams[gs.acting_team_id].tactics
        for field in ("aggression", "pace", "util_discipline", "eco_greed", "map_control"):
            v = getattr(body, field)
            if v is not None:
                setattr(tac, field, float(min(100.0, max(0.0, v))))
        if body.site_focus is not None:
            if body.site_focus not in ("balanced", "a", "b", "c"):
                raise HTTPException(422, "site_focus must be balanced/a/b/c")
            tac.site_focus = body.site_focus
        S.save()
        return {"ok": True, "message": "tactics updated", "tactics": tac.model_dump()}


_PLAN_DIAL_FIELDS = (
    "aggression", "pace", "util_discipline", "eco_greed", "map_control",
)


@app.get("/api/gameplan")
def gameplan_view() -> dict:
    """The coach's desk for the NEXT fixture: opponent intel (fogged by
    scout knowledge — same fog the roster screen uses), the current plan,
    the server-computed prep edge, a suggested target once scouting can
    actually name one, and rotation hints for the one-match lineup. All
    numbers computed here; the client only renders."""
    with S.lock:
        gs = S.require_gs()
        tid = gs.acting_team_id
        team = gs.teams[tid]
        fx = gs.team_fixture(tid)
        if fx is None or fx.played:
            return {"fixture": None, "plan": None}
        opp_id = fx.team_b if fx.team_a == tid else fx.team_a
        opp = gs.teams[opp_id]
        know = gs.scout_progress.get(opp_id, 0.0)
        fog = _team_fog(gs, opp_id)

        opp_rows = []
        active = set(default_five(gs, opp_id))
        for p in sorted(gs.roster(opp_id), key=lambda q: q.id):
            # Fogged overall = mean of the per-attribute fogged draws —
            # the SAME draws the roster screen shows, so the two surfaces
            # can never disagree about who the weak link looks like.
            fogged_attrs = [
                _fogged(gs, p.id, k, v, fog)
                for k, v in sorted(p.attributes.items())
            ]
            overall = (
                round(sum(fogged_attrs) / len(fogged_attrs), 1)
                if fogged_attrs
                else round(market.player_quality(p), 1)
            )
            opp_rows.append(
                {
                    "player_id": p.id,
                    "handle": p.handle,
                    "role": str(p.role),
                    "playstyle": str(p.playstyle),
                    "overall": overall,
                    "form": _fogged(gs, p.id, "form", p.form, fog),
                    "is_starter": p.id in active,
                    "fogged": fog > 0,
                }
            )
        # A target suggestion only once the scout can actually name the
        # weak link (the fogged view IS the manager's knowledge).
        suggested = None
        if know >= 0.35:
            starters = [r for r in opp_rows if r["is_starter"]]
            if starters:
                suggested = min(starters, key=lambda r: (r["overall"], r["player_id"]))[
                    "player_id"
                ]

        plan = gs.game_plan
        if plan is not None and plan.fixture_id != fx.id:
            plan = None  # stale plan for a past fixture; the tick will sweep it

        own_rows = []
        starters_own = set(default_five(gs, tid))
        for p in sorted(gs.roster(tid), key=lambda q: q.id):
            own_rows.append(
                {
                    "player_id": p.id,
                    "handle": p.handle,
                    "role": str(p.role),
                    "playstyle": str(p.playstyle),
                    "overall": round(market.player_quality(p), 1),
                    "stamina": p.stamina,
                    "form": p.form,
                    "confidence": p.confidence,
                    "is_starter": p.id in starters_own,
                }
            )
        gassed = [r for r in own_rows if r["is_starter"] and r["stamina"] < 30.0]
        fresh = [r for r in own_rows if not r["is_starter"] and r["stamina"] >= 70.0]
        hints = [
            f"{g['handle']} is running on fumes ({g['stamina']:.0f} stamina)"
            for g in sorted(gassed, key=lambda r: r["stamina"])[:2]
        ]
        if gassed and fresh:
            names = ", ".join(r["handle"] for r in fresh[:2])
            hints.append(f"Fresh on the bench: {names}")

        rec = gs.standings.get(opp_id)
        return {
            "fixture": {
                "id": fx.id,
                "week": fx.week,
                "stage": fx.stage,
                "best_of": fx.best_of,
                "maps": fx.maps[: fx.best_of],
                "opponent": {
                    "id": opp_id,
                    "name": opp.name,
                    "tag": opp.tag,
                    "world_rank": opp.world_rank,
                    "record": (
                        f"{rec.wins}-{rec.losses}" if rec is not None else ""
                    ),
                },
            },
            "plan": plan.model_dump() if plan is not None else None,
            "tactics": team.tactics.model_dump(),
            "scout_knowledge": round(know, 2),
            "prep_edge": round(PREP_EDGE_BASE + PREP_EDGE_SPAN * know, 2),
            "prep_edge_max": round(
                min(PREP_EDGE_BASE + PREP_EDGE_SPAN, C.PREP_EDGE_CAP), 2
            ),
            "opponent_roster": opp_rows,
            "suggested_target": suggested,
            "own_roster": own_rows,
            "rotation_hints": hints,
            "site_options": ["balanced", "a", "b", "c"],
        }


class GamePlanBody(BaseModel):
    clear: bool = False
    aggression: float | None = None
    pace: float | None = None
    util_discipline: float | None = None
    eco_greed: float | None = None
    map_control: float | None = None
    site_focus: str | None = None
    focus_target: str | None = None
    starter_ids: list[str] = []


@app.post("/api/actions/gameplan")
def set_gameplan(body: GamePlanBody) -> dict:
    """Set (or clear) the pre-match plan for the acting manager's next
    fixture. Everything is validated against live state — a plan is a
    claim about THIS match, not a standing setting."""
    with S.lock:
        gs = S.require_gs()
        tid = gs.acting_team_id
        if body.clear:
            gs.game_plan = None
            S.save()
            return {"ok": True, "message": "game plan cleared — playing the book"}
        fx = gs.team_fixture(tid)
        if fx is None or fx.played:
            raise HTTPException(409, "no upcoming fixture to plan for")
        opp_id = fx.team_b if fx.team_a == tid else fx.team_a
        if body.site_focus is not None and body.site_focus not in (
            "balanced", "a", "b", "c",
        ):
            raise HTTPException(422, "site_focus must be balanced/a/b/c")
        if (
            body.focus_target is not None
            and body.focus_target not in gs.teams[opp_id].player_ids
        ):
            raise HTTPException(422, "focus target is not on the opponent's roster")
        starters = list(body.starter_ids)
        if starters:
            team = gs.teams[tid]
            if len(starters) != 5 or len(set(starters)) != 5:
                raise HTTPException(422, "a one-match lineup names exactly 5 players")
            if any(pid not in team.player_ids for pid in starters):
                raise HTTPException(422, "lineup includes players not on your roster")
        dials = {}
        for k in _PLAN_DIAL_FIELDS:
            v = getattr(body, k)
            if v is not None and not math.isfinite(v):
                raise HTTPException(422, f"{k} must be a finite number")
            dials[k] = None if v is None else float(min(100.0, max(0.0, v)))
        gs.game_plan = GamePlan(
            fixture_id=fx.id,
            site_focus=body.site_focus,
            focus_target=body.focus_target,
            starter_ids=starters,
            **dials,
        )
        S.save()
        return {"ok": True, "message": "game plan locked in for the next match"}


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
    # Which buyer's bid to resolve (a manager may hold several for one player).
    to_team: str | None = None


@app.post("/api/actions/transfer_offer")
def transfer_offer(body: OfferBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.respond_offer(
            gs, body.player_id, body.accept, body.to_team
        )
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
        if body.team_id == gs.acting_team_id:
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
                if tid != gs.acting_team_id
            ],
        }


class PlayerBody(BaseModel):
    player_id: str


@app.post("/api/actions/sign")
def sign(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.sign_player(gs, gs.acting_team_id, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/release")
def release(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.release_player(gs, gs.acting_team_id, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/renew")
def renew(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.renew_contract(gs, gs.acting_team_id, body.player_id)
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


class SwapBody(BaseModel):
    sign_id: str  # free agent to sign
    drop_id: str  # rostered player to release


@app.post("/api/actions/swap")
def swap(body: SwapBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.swap_player(
            gs, gs.acting_team_id, body.sign_id, body.drop_id
        )
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


class PackageBody(BaseModel):
    target_pid: str  # the rival player you want
    out_pids: list[str] = []  # your players you're offering
    cash_out: int = 0  # cash you send
    cash_in: int = 0  # cash you ask back


@app.post("/api/actions/package")
def package(body: PackageBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.target_pid not in gs.players:
            raise HTTPException(404, "unknown player")
        ok, msg = market.propose_package(
            gs,
            body.target_pid,
            list(body.out_pids),
            max(0, int(body.cash_out)),
            max(0, int(body.cash_in)),
        )
        S.save()
        if not ok:
            raise HTTPException(422, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/advance")
def advance() -> dict:
    """Ready-up: mark the acting manager ready to advance. The week only ticks
    once EVERY human in the world is ready (a solo game advances immediately).
    Returns either the resolved week's report, or a 'waiting' status listing who
    the world is still waiting on."""
    with S.lock:
        gs = S.require_gs()
        me = gs.acting_team_id
        # Legacy mode: a dismissed manager must take a job before anyone
        # advances — the world doesn't move while a seat is empty.
        blocked = career.blocked_seats(gs)
        if blocked:
            names = ", ".join(gs.managers[m].name for m in blocked)
            raise HTTPException(
                409,
                f"waiting on a manager to accept a new post ({names})",
            )
        # A manager can't tick the week without a legal (five-deep) roster.
        ok, why = market.roster_ready(gs, me)
        if not ok:
            raise HTTPException(409, why)
        game = _ctx.get().game
        game.ready.add(me)
        waiting_on = [t for t in gs.human_team_ids if t not in game.ready]
        if waiting_on:
            game.save()  # persist the ready flag isn't needed, but the join is
            return {
                "advanced": False,
                "waiting_on": [gs.teams[t].name for t in waiting_on],
                "ready": sorted(game.ready),
            }
        # Everyone's in — but a manager may have released or sold a player
        # AFTER readying up, while waiting on the others. Revalidate every human
        # roster right before the tick so a ready-but-now-short team can't slip
        # the week through. Offenders lose their ready flag and must re-ready.
        short = [t for t in gs.human_team_ids if not market.roster_ready(gs, t)[0]]
        if short:
            for t in short:
                game.ready.discard(t)
            game.save()
            names = ", ".join(gs.teams[t].name for t in short)
            raise HTTPException(
                409,
                f"can't advance — {names} need {market.ROSTER_MIN} players "
                "(re-ready once fixed)",
            )
        # Everyone's in — advance the shared world exactly once.
        game.event_logs.clear()  # replays are for the freshly played week
        report = advance_week(gs, S.gd, events_out=game.event_logs)
        game.last_report = report
        game.ready.clear()
        # Hand the week's fresh posts to the LLM ghost-writer (async,
        # serving-layer only — see web/llm_social.py; no-op without a
        # configured provider).
        llm_social.enqueue(game)
        # Re-bind acting (advance_week churns the acting pointer internally).
        gs.set_acting(me)
        game.save()
        return {
            "advanced": True,
            "season": report.season,
            "week": report.week,
            "phase": report.phase,
            "fixtures": [_fixture_view(f, gs) for f in report.fixtures],
            "user_income": report.income_by.get(me, 0),
            "user_expenses": report.expenses_by.get(me, 0),
            "notes": report.notes,
        }


# ---------------------------------------------------------------------------
# Profile screens (player / team read-only aggregation)
#
# Pure read-only views over GameState. Fog mirrors the roster/scouting
# rules already in this file: the user's own club is exact; rivals are
# scout-banded (value hidden, qualitative band shown) until fully scouted;
# the free-agent market carries its own lighter fog. Season/box-score
# aggregates (kills, deaths, ratings, per-map records) are public broadcast
# data — never fogged. Anything the save simply does not persist (ACS,
# assists, clutches, per-season career archive) comes back null / [].


# Qualitative attribute band, 1-99 scale. Used both to describe an exact
# value (own club) and to convey a scouted, number-hidden read (rivals).
def _attr_band(v: float) -> str:
    if v >= 80:
        return "elite"
    if v >= 68:
        return "strong"
    if v >= 55:
        return "solid"
    if v >= 42:
        return "average"
    if v >= 30:
        return "weak"
    return "poor"


def _tier_from_stars(s: float) -> str:
    """Coarse ceiling tier from a 0.5-5.0 star rating."""
    if s >= 4.5:
        return "elite"
    if s >= 3.5:
        return "star"
    if s >= 2.5:
        return "starter"
    if s >= 1.5:
        return "rotation"
    return "depth"


def _potential_text(gs: GameState, p: Player, fogged: bool, progress: float) -> str:
    """Banded ceiling text 'as scouting knows it'. Own club knows the
    tier exactly; a rival/free agent reads as the scout's (possibly wide)
    star band, collapsed to a tier or a tier range."""
    if not fogged:
        return _tier_from_stars(development.stars(development.potential_of(p)))
    report = development.scout_report(gs, p, progress)
    lo, hi = report["pa_stars"]
    tlo, thi = _tier_from_stars(lo), _tier_from_stars(hi)
    return tlo if tlo == thi else f"{tlo}-{thi}"


def _player_fog(gs: GameState, pid: str) -> tuple[float, float, bool]:
    """Return (sigma, scout_progress, is_free_agent) for a player. Own-team
    players get sigma 0; rivals scale with team scout progress; free agents
    ride the lighter market fog (matching /api/market)."""
    if pid in gs.free_agent_ids:
        progress = gs.scout_progress.get("market", 0.0)
        return 6.0 * (1.0 - progress), progress, True
    team_id = market.team_of(gs, pid)
    if team_id is None:
        return 0.0, 1.0, False  # unrostered non-FA (e.g. mid-transfer): treat as known
    if team_id == gs.acting_team_id:
        return 0.0, 1.0, False
    return _team_fog(gs, team_id), gs.scout_progress.get(team_id, 0.0), False


def _profile_overview(gs: GameState, p: Player, fog: float, progress: float) -> dict:
    fogged = fog > 0.0
    ovr = None if fogged else int(round(development.overall(p)))
    return {
        "ovr": ovr,
        "potential": _potential_text(gs, p, fogged, progress),
        "form": None if fogged else round(p.form, 1),
        "morale": None if fogged else round(p.morale, 1),
        "condition": None if fogged else round(p.stamina, 1),
        # Value / salary / contract are public (rival transfer asks already
        # leak on the roster page), so they show regardless of fog.
        "market_value": market.transfer_value(p),
        "salary": p.salary,
        "contract_weeks": p.contract_weeks_left,
        "playstyle": str(p.playstyle),
        "fogged": fogged,
    }


def _profile_traits(p: Player, fog: float, progress: float) -> list[dict]:
    """Own club: every trait revealed. Rival/FA: only the scout's revealed
    traits are listed (progress * count, same math as scout_report);
    unrevealed traits are OMITTED entirely."""
    tags = sorted(p.personality_tags)
    if fog <= 0.0:
        shown = tags
    else:
        known_n = int(round(progress * len(tags) + 1e-9))
        shown = tags[:known_n]
    return [
        {
            "name": t,
            "desc": development.TRAITS.get(t, {}).get("blurb", ""),
            "revealed": True,
        }
        for t in shown
    ]


def _profile_attributes(gs: GameState, p: Player, fog: float) -> list[dict]:
    fogged = fog > 0.0
    reg = S.gd.attributes.definitions
    out = []
    for key in sorted(p.attributes):
        true_val = p.attributes[key]
        label = reg[key].display_name if key in reg else key
        if fogged:
            shown = _fogged(gs, p.id, key, true_val, fog)
            out.append({"key": key, "label": label, "value": None, "band": _attr_band(shown)})
        else:
            out.append(
                {
                    "key": key,
                    "label": label,
                    "value": round(true_val, 1),
                    "band": _attr_band(true_val),
                }
            )
    return out


def _profile_agents(p: Player) -> list[dict]:
    out = []
    for m in sorted(p.agent_pool, key=lambda m: (-m.mastery, m.agent_id)):
        agent = S.gd.agents.get(m.agent_id)
        out.append(
            {
                "agent_id": m.agent_id,
                "name": agent.display_name if agent else m.agent_id,
                "icon": _agent_icon_url(m.agent_id),
                "mastery": m.mastery,
            }
        )
    return out


def _profile_season(gs: GameState, pid: str) -> dict:
    """Season totals from the box-score aggregates. Depth follows the
    org's analytics tier (same gate as the stats hub): gated fields come
    back null, and the client renders them as locked."""
    st = gs.player_stats.get(pid)
    tier = staff_mod.analytics_tier(gs)
    empty = st is None or st.maps == 0
    if empty:
        st = PlayerSeasonStats()
    out = {
        "matches": st.maps,
        "kills": st.kills,
        "deaths": st.deaths,
        "kd": round(st.kd, 2) if not empty else None,
        "first_kills": st.first_kills,
        "rating": round(st.rating, 2) if not empty else None,
        "analytics_tier": tier,
        # Tier-gated depth (null = locked or no data).
        "assists": None,
        "acs": None,
        "hs_pct": None,
        "first_deaths": None,
        "fk_fd": None,
        "clutches": None,
        "clutch_1v1": None,
        "clutch_1v2": None,
        "clutch_1v3": None,
        "kast_pct": None,
        "trade_kills": None,
        "eco_kills": None,
        "save_kills": None,
        "pistol_kills": None,
        "multikills": None,
        "aces": None,
        "kills_by_weapon": None,
    }
    if empty:
        return out
    if tier >= 1:
        out.update(
            acs=round(st.acs, 1),
            hs_pct=round(st.hs_pct, 1),
            first_deaths=st.first_deaths,
            fk_fd=round(st.fk_fd, 2),
            clutches=st.clutch_1v1 + st.clutch_1v2 + st.clutch_1v3,
            multikills=st.multikills,
            aces=st.aces,
            pistol_kills=st.pistol_kills,
        )
    if tier >= 2:
        out.update(
            assists=st.assists,
            kast_pct=round(st.kast_pct, 1),
            trade_kills=st.trade_kills,
            clutch_1v1=st.clutch_1v1,
            clutch_1v2=st.clutch_1v2,
            clutch_1v3=st.clutch_1v3,
            eco_kills=st.eco_kills,
            save_kills=st.save_kills,
            kills_by_weapon=dict(
                sorted(st.kills_by_weapon.items(), key=lambda kv: (-kv[1], kv[0]))
            ),
        )
    return out


def _profile_splits(gs: GameState, pid: str) -> dict | None:
    """Per-map and per-agent season lines (analytics tier 3)."""
    if staff_mod.analytics_tier(gs) < 3:
        return None

    def rows(table: dict[str, PlayerSeasonStats], is_agent: bool) -> list[dict]:
        out = []
        for key, st in sorted(table.items()):
            if st.maps == 0:
                continue
            agent = S.gd.agents.get(key) if is_agent else None
            out.append(
                {
                    "key": key,
                    "label": agent.display_name if agent else key,
                    "icon": _agent_icon_url(key) if is_agent else _map_thumb_url(key),
                    "maps": st.maps,
                    "rating": round(st.rating, 2),
                    "acs": round(st.acs, 1),
                    "kd": round(st.kd, 2),
                    "kast_pct": round(st.kast_pct, 1),
                }
            )
        out.sort(key=lambda r: (-r["maps"], r["key"]))
        return out

    return {
        "maps": rows(gs.player_map_stats.get(pid, {}), is_agent=False),
        "agents": rows(gs.player_agent_stats.get(pid, {}), is_agent=True),
    }


def _profile_charts(gs: GameState, pid: str, own: bool) -> dict:
    """Time-series for the profile trend charts. Performance series needs
    an analytics department (tier 2+); the development series (ability,
    confidence, condition, reach) is the manager's own private view."""
    tier = staff_mod.analytics_tier(gs)
    perf = (
        [s.model_dump() for s in gs.stat_history.get(pid, [])]
        if tier >= 2
        else None
    )
    dev = (
        [s.model_dump() for s in gs.dev_history.get(pid, [])] if own else None
    )
    return {"performance": perf, "development": dev, "analytics_tier": tier}


def _profile_weekly(gs: GameState, pid: str) -> list[dict]:
    """Per-match line derived from the persisted box-score lines
    (Fixture.results[*].lines). Only fixtures the player actually featured
    in, for the side they currently sit on, are derivable — transfers move
    rosters and the lines carry no historical team, so ambiguous games are
    dropped rather than guessed. ACS is not stored -> null."""
    out = []
    for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id)):
        if not f.played:
            continue
        if pid in gs.teams[f.team_a].player_ids:
            side, opp = f.team_a, f.team_b
        elif pid in gs.teams[f.team_b].player_ids:
            side, opp = f.team_b, f.team_a
        else:
            continue
        kills = deaths = 0
        played_any = False
        for r in f.results:
            for ln in r.lines:
                if ln.player_id == pid:
                    kills += ln.kills
                    deaths += ln.deaths
                    played_any = True
        if not played_any:
            continue
        out.append(
            {
                "season": gs.season,
                "week": f.week,
                "opponent": gs.teams[opp].name,
                "result": "W" if f.winner_id == side else "L",
                "kills": kills,
                "deaths": deaths,
                "acs": None,
            }
        )
    return out


def _profile_relationships(gs: GameState, pid: str) -> list[dict]:
    """The locker-room graph for this player. Mirrors the roster page,
    which only exposes chemistry pairs for the user's own club, so rival /
    free-agent profiles return []."""
    if pid not in gs.teams[gs.acting_team_id].player_ids:
        return []
    out = []
    for k in sorted(gs.relationships):
        parts = k.split("|")
        if pid not in parts:
            continue
        other = parts[1] if parts[0] == pid else parts[0]
        op = gs.players.get(other)
        if op is None:
            continue
        v = gs.relationships[k]
        if v >= relationships.FRIEND_BAR:
            kind = "duo"
        elif v <= relationships.FEUD_BAR:
            kind = "feud"
        else:
            kind = "neutral"
        out.append({"pid": other, "handle": op.handle, "kind": kind, "strength": round(v, 1)})
    out.sort(key=lambda r: (-r["strength"], r["pid"]))
    return out


@app.get("/api/players/{pid}/profile")
def player_profile(pid: str) -> dict:
    with S.lock:
        gs = S.require_gs()
        p = gs.players.get(pid)
        if p is None:
            raise HTTPException(404, "unknown player")
        fog, progress, is_fa = _player_fog(gs, pid)
        team_id = None if is_fa else market.team_of(gs, pid)
        team = gs.teams.get(team_id) if team_id else None
        own = team_id == gs.acting_team_id
        return {
            "player": {
                "id": p.id,
                "handle": p.handle,
                "age": p.age,
                "role": str(p.role),
                "team_id": team_id,
                "team_name": team.name if team else None,
                "team_logo": _logo_url(team_id) if team_id else None,
                "portrait": _portrait_url(p.id, str(p.role)),
                "is_user_team": own,
                "is_free_agent": is_fa,
                # A rival's contracted player is biddable: the seller's ask, so
                # the profile overlay can open the package builder.
                "transfer_ask": (
                    market.transfer_ask(gs, pid)
                    if (not is_fa and team_id and team_id != gs.acting_team_id)
                    else None
                ),
                "followers": p.followers,
                "confidence": None if fog > 0 else round(p.confidence, 1),
                "is_starter": (
                    pid in default_five(gs, team_id) if team_id else None
                ),
                "dev_focus": p.dev_focus if own else None,
                "training_intensity": p.training_intensity if own else None,
            },
            "overview": _profile_overview(gs, p, fog, progress),
            "traits": _profile_traits(p, fog, progress),
            "attributes": _profile_attributes(gs, p, fog),
            "agents": _profile_agents(p),
            "season": _profile_season(gs, pid),
            "weekly": _profile_weekly(gs, pid),
            "splits": _profile_splits(gs, pid),
            "charts": _profile_charts(gs, pid, own),
            "relationships": _profile_relationships(gs, pid),
            # No per-season career archive is persisted (player_stats reset
            # each offseason), so only the current season exists -> [].
            "career": [],
            # Lifetime totals (completed seasons + the current one in
            # progress): maps, kills, K/D, honours. None until they've
            # played a map. Reads gs.career_stats + the live season.
            "career_totals": _profile_career_totals(gs, pid),
            # The trophy cabinet: individual season awards this player has
            # won, newest first. A clean structured read of the chronicle's
            # award entries (the cleanly player-attributable honours; team
            # titles carry a team_id, not a player_id, so they stay in the
            # broader "memories" list rather than this personal cabinet).
            "honours": _profile_honours(gs, pid),
            # A one-line earned epithet ("League MVP", "Clutch merchant"),
            # derived from the honours above — None until they've won
            # something, so it's always grounded, never a hollow label.
            "epithet": _player_epithet(gs, pid),
            # What this player remembers — their defining chronicle
            # entries (debut, titles, milestones, moves), newest-important
            # first. Pure chronicle read (manager/memories.py).
            "memories": memories_mod.memory_lines(gs, pid),
        }


# Earned epithets, best-first: a player's headline honour becomes their
# label. Award names match narrative.season_awards exactly.
_EPITHETS: tuple[tuple[str, str], ...] = (
    ("Season MVP", "League MVP"),
    ("Clutch Merchant", "Clutch merchant"),
    ("Opening King", "Opening specialist"),
    ("Top Fragger", "Star fragger"),
    ("Most Improved", "Breakout riser"),
    ("Challengers MVP", "Challengers standout"),
    ("Rookie of the Season", "Standout rookie"),
)


def _profile_career_totals(gs: GameState, pid: str) -> dict | None:
    """Lifetime box-score totals for the profile's Career section: the
    rolled-up gs.career_stats plus the current in-progress season, with
    honours/MVP counts from the chronicle. None until the player has a map
    to their name (a debutant with nothing to show yet)."""
    cs = gs.career_stats.get(pid)
    cur = gs.player_stats.get(pid)
    cur_maps = cur.maps if cur else 0
    maps = (cs.maps if cs else 0) + cur_maps
    if maps <= 0:
        return None
    kills = (cs.kills if cs else 0) + (cur.kills if cur else 0)
    deaths = (cs.deaths if cs else 0) + (cur.deaths if cur else 0)
    entries = chronicle.entries_for_player(gs, pid)
    return {
        "maps": maps,
        "kills": kills,
        "deaths": deaths,
        "kd": round(kills / max(deaths, 1), 2),
        "first_kills": (cs.first_kills if cs else 0) + (cur.first_kills if cur else 0),
        "clutches": (cs.clutches if cs else 0) + (cur.clutches if cur else 0),
        "seasons": (cs.seasons if cs else 0) + (1 if cur_maps > 0 else 0),
        "honours": sum(1 for e in entries if e.kind == "award"),
        "mvps": sum(
            1 for e in entries
            if e.kind == "award" and "MVP" in e.data.get("award", "")
        ),
    }


def _player_epithet(gs: GameState, pid: str) -> str | None:
    """The player's headline earned label, or None if they've won nothing
    yet. Pure chronicle read; priority follows _EPITHETS (MVP outranks the
    rest, a bare honour still earns 'Decorated pro')."""
    won = {
        e.data.get("award", "")
        for e in chronicle.entries_for_player(gs, pid)
        if e.kind == "award"
    }
    for key, label in _EPITHETS:
        if key in won:
            return label
    return "Decorated pro" if won else None


def _profile_honours(gs: GameState, pid: str) -> list[dict]:
    """The player's individual season awards, newest first. Pure chronicle
    read; the value string was frozen into the award entry at win time, so
    the detail is grounded, not re-derived."""
    out = [
        {
            "season": e.season,
            "award": e.data.get("award", "Award"),
            "detail": e.data.get("value", ""),
        }
        for e in chronicle.entries_for_player(gs, pid)
        if e.kind == "award"
    ]
    out.sort(key=lambda h: (-h["season"], h["award"]))
    return out


def _team_streak(gs: GameState, tid: str) -> str | None:
    played = sorted(
        (f for f in gs.fixtures if f.played and tid in (f.team_a, f.team_b)),
        key=lambda f: (f.week, f.id),
    )
    if not played:
        return None
    last_won = played[-1].winner_id == tid
    n = 0
    for f in reversed(played):
        if (f.winner_id == tid) == last_won:
            n += 1
        else:
            break
    return f"{'W' if last_won else 'L'}{n}"


@app.get("/api/teams/{tid}/profile")
def team_profile(tid: str) -> dict:
    with S.lock:
        gs = S.require_gs()
        if tid not in gs.teams:
            raise HTTPException(404, "unknown team")
        t = gs.teams[tid]
        rec = gs.standings.get(tid)
        region = str(t.region)
        order = gs.standings_order(region, tier=t.tier)
        position = order.index(tid) + 1 if tid in order else None

        ts = gs.team_stats.get(tid)
        splits = {
            "attack_round_rate": round(100 * ts.atk_won / ts.atk_rounds, 1)
            if ts and ts.atk_rounds
            else None,
            "defense_round_rate": round(100 * ts.def_won / ts.def_rounds, 1)
            if ts and ts.def_rounds
            else None,
        }

        # Per-map record from persisted results.
        map_agg: dict[str, list[int]] = {}
        team_fixtures = [
            f for f in gs.fixtures if f.played and tid in (f.team_a, f.team_b)
        ]
        for f in team_fixtures:
            for r in f.results:
                agg = map_agg.setdefault(r.map_id, [0, 0, 0])
                agg[0] += 1
                if r.winner_id == tid:
                    agg[1] += 1
                else:
                    agg[2] += 1
        maps = [
            {
                "map": S.gd.maps[mid].display_name if mid in S.gd.maps else mid,
                "played": agg[0],
                "wins": agg[1],
                "losses": agg[2],
            }
            for mid, agg in sorted(map_agg.items())
        ]

        # Roster with public season aggregates. ACS is untracked, so the
        # contract's acs-desc order falls back to rating then handle.
        own_team = tid == gs.acting_team_id
        players = []
        for pid in t.player_ids:
            p = gs.players.get(pid)
            if p is None:
                continue
            st = gs.player_stats.get(pid)
            has = st is not None and st.maps > 0
            players.append(
                {
                    "pid": pid,
                    "handle": p.handle,
                    "role": str(p.role),
                    "matches": st.maps if st else 0,
                    "kd": round(st.kd, 2) if has else None,
                    "acs": None,
                    # Farewell-tour watch: a veteran carrying real offseason
                    # retirement odds. Own club only — the odds read true CA,
                    # which stays fogged for rivals.
                    "retirement_risk": (
                        own_team and development.retirement_prob(p) >= 0.15
                    ),
                    "_rating": st.rating if has else 0.0,
                }
            )
        players.sort(key=lambda r: (-r["_rating"], r["handle"]))
        for r in players:
            del r["_rating"]

        form = []
        for f in sorted(team_fixtures, key=lambda f: (f.week, f.id))[-20:]:
            opp = f.team_b if tid == f.team_a else f.team_a
            a, b = f.map_score
            score = f"{a}-{b}" if tid == f.team_a else f"{b}-{a}"
            form.append(
                {
                    "season": gs.season,
                    "week": f.week,
                    "opponent": gs.teams[opp].name,
                    "result": "W" if f.winner_id == tid else "L",
                    "score": score,
                }
            )

        # Full honours board from the chronicle: world/Masters/regional
        # titles, newest first (a dynasty's cabinet, not just its world
        # crowns). memories.team_titles is the canonical team-title reader.
        _TITLE_LABEL = {
            "champions_title": "World Champion",
            "masters_title": "Masters",
            "regional_title": "Regional title",
        }
        honors = [
            f"S{e.season} {_TITLE_LABEL.get(e.kind, 'Title')}"
            for e in sorted(
                memories_mod.team_titles(gs, tid),
                key=lambda e: (-e.season, e.kind),
            )
        ]

        return {
            "team": {
                "id": t.id,
                "name": t.name,
                "logo": _logo_url(t.id),
                "region": region,
                "league_tier": t.tier,
                "is_user_team": tid == gs.acting_team_id,
            },
            "record": {
                "wins": rec.wins if rec else 0,
                "losses": rec.losses if rec else 0,
                "round_diff": rec.diff if rec else 0,
                "position": position,
                "streak": _team_streak(gs, tid),
            },
            "splits": splits,
            "maps": maps,
            "players": players,
            "form": form,
            "honors": honors,
            # Coaching identity + tendencies: own club always, a rival once
            # scouted (>=0.5). None/[] hides the badge until it's earned.
            "identity": (
                _team_identity_label(t.tactics)
                if (own_team or gs.scout_progress.get(tid, 0.0) >= 0.5)
                else None
            ),
            "tendencies": (
                _team_tendencies(t.tactics)
                if (own_team or gs.scout_progress.get(tid, 0.0) >= 0.5)
                else []
            ),
            # Named rivalries (manager/rivalries.py), hottest first.
            "rivals": [
                {
                    "team_id": rid,
                    "name": gs.teams[rid].name if rid in gs.teams else rid,
                    "intensity": round(heat, 1),
                }
                for rid, heat in rivalries_mod.top_rivals(gs, tid)
                if heat >= rivalries_mod.RIVALRY_BAR / 2
            ],
            # Institutional knowledge is private intel: own org only.
            "knowledge": (
                knowledge_mod.org_summary(gs, tid)
                if tid == gs.acting_team_id
                else None
            ),
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
                    # Honour the coach's agent lock so a replay's icon matches
                    # the agent the engine actually fielded (shared resolver).
                    agent_id = lineup_resolve.resolve_agent(
                        gs.teams[tid], p, S.gd.agents
                    )
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


def _cookie_sid(scope) -> str | None:
    """Pull a valid `esports_sid` out of the request's Cookie header."""
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for part in value.decode("latin-1").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE_NAME and _SID_RE.match(v):
                    return v
    return None


_NO_CACHE_SUFFIXES = (".js", ".css", ".html")


class SessionMiddleware:
    """Pure-ASGI middleware: identifies the browser by its `esports_sid` cookie
    (minting one for first-time visitors), resolves which shared game + team it
    controls, and binds that to the request via the `_ctx` / `_sid_ctx`
    contextvars. Also stamps `Cache-Control: no-cache` on frontend assets so a
    server restart never pairs a fresh backend with a stale cached page.

    Deliberately pure ASGI rather than `BaseHTTPMiddleware`: the latter runs the
    downstream app in a separate anyio task, and the contextvars we set here do
    not reliably reach the sync endpoint threadpool across that hop. Keeping the
    whole chain pure-ASGI means the values flow straight into the endpoint's
    context copy."""

    def __init__(self, app, lobby: Lobby) -> None:
        self.app = app
        self.lobby = lobby

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sid = _cookie_sid(scope)
        fresh = sid is None
        if fresh:
            sid = secrets.token_hex(16)  # 128-bit opaque id; not a sim draw
        game, team_id = self.lobby.game_for(sid)
        path = scope.get("path", "")
        no_cache = path == "/" or path.endswith(_NO_CACHE_SUFFIXES)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if fresh:
                    cookie = (
                        f"{COOKIE_NAME}={sid}; Path=/; HttpOnly; SameSite=Lax; "
                        f"Max-Age=31536000"
                    )
                    headers.append((b"set-cookie", cookie.encode("latin-1")))
                if no_cache:
                    headers.append((b"cache-control", b"no-cache"))
            await send(message)

        ctx_token = _ctx.set(_ReqCtx(game, team_id))
        sid_token = _sid_ctx.set(sid)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _ctx.reset(ctx_token)
            _sid_ctx.reset(sid_token)


app.add_middleware(SessionMiddleware, lobby=_LOBBY)


# Static frontend + design system + art (mounted last so /api wins).
app.mount("/assets", StaticFiles(directory=str(_REPO_ROOT / "assets")), name="assets")
app.mount("/ds", StaticFiles(directory=str(DS_DIR)), name="ds")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def _lan_ip() -> str | None:
    """Best-effort primary LAN IPv4 (no traffic actually sent)."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def run(port: int = 8420, open_browser: bool = True, host: str = "0.0.0.0") -> None:
    import uvicorn

    local = f"http://127.0.0.1:{port}"
    lines = [f"esports-sim web UI (this PC):  {local}"]
    if host == "0.0.0.0":
        lan = _lan_ip()
        if lan:
            lines.append(f"esports-sim web UI (LAN):      http://{lan}:{port}")
        lines.append("Share the LAN URL - each player gets an independent session.")
    # flush now: stdout is block-buffered when not a TTY, and uvicorn.run below
    # blocks, so without a flush the launcher never sees the LAN URL.
    print("\n".join(lines), flush=True)
    if open_browser:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(local)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
