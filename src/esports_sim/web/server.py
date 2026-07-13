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
import ipaddress
import json
import math
import random
import re
import secrets
import threading
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from esports_sim.manager import (
    academy,
    analytics,
    career,
    chronicle,
    culture,
    delegation,
    development,
    economy,
    flavor_events,
    inbox as inbox_mod,
    knowledge as knowledge_mod,
    market,
    media_events,
    match_review as match_review_mod,
    memories as memories_mod,
    meta as meta_mod,
    narrative,
    preparation,
    relationships,
    role_fit,
    rivalries as rivalries_mod,
    social,
    sponsors,
    staff as staff_mod,
    series_management,
    talk,
    telemetry,
    training,
)
from esports_sim.manager.campaign import (
    PREP_EDGE_BASE,
    PREP_EDGE_SPAN,
    SCOUT_DEEP_CAP,
    SCOUT_MATCH_CAP,
    SCOUT_SURVEY_CAP,
    TEAM_TALK_APPROACHES,
    WeekReport,
    advance_week,
    default_five,
    dressed_for,
    new_campaign,
)
from esports_sim import perf
from esports_sim.manager.state import GamePlan, GameState, PlayerSeasonStats
from esports_sim.manager.training import (
    DEV_FOCUS_OPTIONS,
    FOCUS_OPTIONS,
    INTENSITY_OPTIONS,
    LANGUAGE_OPTIONS,
)
from esports_sim.registry import roster_admin, roster_workbench
from esports_sim.registry.loader import GameData, load_all, load_geometry
from esports_sim.registry.rosters import list_roster_packs, load_roster_pack
from esports_sim.schemas import (
    AgentMastery,
    Event,
    LanguageSkill,
    MapMastery,
    Player,
    Playstyle,
    Role,
    Team,
)
from esports_sim.sim import constants as C
from esports_sim.sim import lineup as lineup_resolve
from esports_sim.sim import momentum as momentum_mod
from esports_sim.sim import tactics_fit
from esports_sim.web import llm_flavor, llm_social, review_history

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
        # (team_id, fixture_id) keys already written to the on-disk match-review
        # corpus this session — skips byes / re-appends (see web.review_history).
        self.review_seen: set[tuple[str, str]] = set()
        # Save policy runtime: actions only MARK the world dirty (the full
        # GameState serializing on every click was the biggest per-action
        # cost — see /api/perf save.write); disk writes happen on the
        # explicit Save button, on world lifecycle moments (create / join /
        # resume / leave), and on autosave every Nth week tick.
        self.dirty = False
        self.ticks_since_save = 0

    def require_gs(self) -> GameState:
        if self.gs is None:
            raise HTTPException(409, "no campaign — create one first")
        # Bind the acting manager for this request (we're under self.lock).
        self.gs.set_acting(_ctx.get().team_id)
        return self.gs

    def save(self, force: bool = False) -> None:
        """The single persistence choke point. Plain `save()` (what every
        action endpoint calls) only marks the world dirty; `force=True`
        actually writes — the explicit Save button, world lifecycle
        (create/join/resume/leave), and autosave_tick below."""
        if self.gs is None:
            return
        if not force:
            self.dirty = True
            return
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        # Save cost was the biggest per-action tax on deep saves (the
        # whole GameState serializes) — time it and gauge the file size
        # so /api/perf shows both growing.
        with perf.span("save.write"):
            self.gs.save(self.save_path)
        self.dirty = False
        try:
            perf.gauge("save.bytes", self.save_path.stat().st_size)
        except OSError:
            pass

    def autosave_tick(self) -> None:
        """Called after a week actually resolves: write every Nth tick per
        the world's policy (autosave off = only the Save button writes)."""
        self.dirty = True
        self.ticks_since_save += 1
        if (
            self.gs is not None
            and self.gs.autosave_enabled
            and self.ticks_since_save >= self.gs.autosave_every_weeks
        ):
            self.save(force=True)
            self.ticks_since_save = 0


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
            # Validate the pick BEFORE building the final world: new_campaign
            # creates the manager seat (indexing gs.teams[team_id]), so an
            # unknown id must 422 here, not 500 in there. Pack worlds carry
            # their ids in the pack data, but FICTIONAL worlds GENERATE their
            # teams from the seed (ids like team_adriatic_sirens that are NOT
            # in the static registry `self.gd.teams`), so validate those
            # against a same-seed preview — exactly the world this call will
            # build. user_team_id doesn't affect which ids get generated, so
            # any valid placeholder works; legacy reuses the same preview.
            preview = None
            if pack is not None:
                known = {t.id for t in pack.teams.values()}
            else:
                preview = new_campaign(
                    self.gd, seed=seed, mode="sandbox",
                    user_team_id=_preview_team(self.gd, None),
                )
                known = set(preview.teams)
            if team_id not in known:
                raise HTTPException(422, f"unknown team '{team_id}'")
            offer = None
            if game_mode == "legacy":
                # Re-derive the founding seat's offer slate server-side and
                # demand the pick comes from it — the lobby showed exactly
                # this set (same seed, seat 0), so nothing can drift. The
                # fictional-world preview above already used the same seed,
                # so reuse it; only pack worlds still need a build here.
                if preview is None:
                    preview = new_campaign(
                        self.gd, seed=seed, pack=pack, mode="sandbox",
                        user_team_id=_preview_team(self.gd, pack),
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
            game = _Game(self.gd, code, gs=gs)
            game.mode = "shared" if shared else "solo"
            self.games[code] = game
            self.sessions[sid] = (code, team_id)
            self._remember(
                sid, code, team_id, gs.teams[team_id].name, game.mode
            )
            self._save_sessions()
            self._write_mode(code, game.mode)
            game.save(force=True)  # the world must exist on disk from birth
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
            game.save(force=True)  # a claimed seat must survive a restart
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
                    # Walking away is a save point — never lose a session's
                    # work to the autosave interval.
                    game.save(force=True)
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

    def delete_world(self, sid: str, code: str) -> str | None:
        """Permanently remove one of this browser's saved worlds.

        A shared world cannot be removed while another browser has a seat in
        it. This prevents one manager from deleting an active campaign out
        from under the rest of the group.
        """
        with self._lock:
            if not any(row[0] == code for row in self.history.get(sid, [])):
                return "that world isn't in this browser's history"
            if any(world_code == code for world_code, _ in self.sessions.values()):
                return "leave the world before deleting it; shared worlds cannot be deleted while a manager is playing"

            game = self.games.get(code)
            if game is not None:
                # No session is bound to this game, but an in-flight request
                # may still be reading it. Wait before removing its files.
                with game.lock:
                    self.games.pop(code, None)

            try:
                _save_path_for(code).unlink(missing_ok=True)
                _meta_path_for(code).unlink(missing_ok=True)
                # This cache has no value without its campaign. Match-review
                # JSONL is intentionally retained as an offline corpus.
                llm_social._cache_path(code).unlink(missing_ok=True)
            except OSError:
                return "could not delete that world's saved files"

            for history_sid, rows in self.history.items():
                self.history[history_sid] = [row for row in rows if row[0] != code]
            self._save_sessions()
            return None

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
# The peer address comes from the ASGI server socket, not from a spoofable
# Host/X-Forwarded-For header.  Roster-pack correction mutates repository
# source files, so those routes must remain a host-machine-only tool even when
# the game itself is intentionally served to the LAN.
_client_host_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "req_client_host", default=""
)


def _current_sid() -> str:
    return _sid_ctx.get()


def _require_local_admin() -> None:
    """Reject repository-mutating roster tools from non-loopback peers."""
    try:
        is_loopback = ipaddress.ip_address(_client_host_ctx.get()).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(403, "roster-pack corrections are local-only")


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


_TEAM_LOGO_IDS: set[str] | None = None


def _team_logo_ids() -> set[str]:
    """Team ids with a generated org logo on disk (assets/logos/teams/<id>.webp).

    Cached on first call so lookups aren't a per-request disk hit; the set
    is only populated once per process (generated logos are added by the
    art pass, not at runtime).
    """
    global _TEAM_LOGO_IDS
    if _TEAM_LOGO_IDS is None:
        team_logo_dir = _REPO_ROOT / "assets" / "logos" / "teams"
        if team_logo_dir.is_dir():
            _TEAM_LOGO_IDS = {p.stem for p in team_logo_dir.glob("*.webp")}
        else:
            _TEAM_LOGO_IDS = set()
    return _TEAM_LOGO_IDS


def _logo_url(team_id: str) -> str:
    if team_id in _team_logo_ids():
        return f"/assets/logos/teams/{team_id}.webp"
    return f"/assets/logos/logo_{_stable_idx(team_id, N_LOGOS)}.webp"


_BADGE_ART_IDS: set[str] | None = None


def _badge_art_ids() -> set[str]:
    """Badge ids with generated emblem art on disk (assets/badges/<id>.webp),
    cached once per process (added by the art pass, not at runtime)."""
    global _BADGE_ART_IDS
    if _BADGE_ART_IDS is None:
        d = _REPO_ROOT / "assets" / "badges"
        _BADGE_ART_IDS = {p.stem for p in d.glob("*.webp")} if d.is_dir() else set()
    return _BADGE_ART_IDS


def _badge_views(p: Player) -> list[dict]:
    """A player's badges for the client (public info — earned at public
    moments): positives first, then by id. Carries emoji + optional art url."""
    from esports_sim.schemas.badges import BADGES

    out = []
    for pb in sorted(
        p.badges, key=lambda x: (-BADGES.get(x.id, {}).get("polarity", 1), x.id)
    ):
        b = BADGES.get(pb.id)
        if not b:
            continue
        bid = pb.id
        out.append({
            "id": bid, "name": b["name"], "emoji": b["emoji"],
            "polarity": b["polarity"], "blurb": b["blurb"],
            "art": (f"/assets/badges/{bid}.webp" if bid in _badge_art_ids() else None),
            "season": pb.season,
        })
    return out


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


def _language_views(p: Player) -> list[dict]:
    """A player's spoken tongues in the profile overlay's wire shape
    ({lang, level}) — public identity facts, reused by the market rows so
    comms fit is visible at the signing decision."""
    return [{"lang": l.lang, "level": round(l.level)} for l in p.languages]


def _roster_potential_projection(
    gs: GameState, p: Player, team_id: str | None = None
) -> tuple[float, float]:
    """Own-roster potential read, tightened by that org's performance coach."""
    tid = team_id or gs.acting_team_id
    performance_coach = gs.staff_by.get(tid, {}).get("performance_coach")
    return development.potential_projection(
        p,
        own=True,
        performance_coach_quality=(
            performance_coach.quality if performance_coach is not None else None
        ),
    )


def _player_view(p: Player, gs: GameState, fog: float = 0.0) -> dict:
    attrs = {
        k: _fogged(gs, p.id, k, v, fog) for k, v in sorted(p.attributes.items())
    }
    overall = (
        round(sum(attrs.values()) / len(attrs), 1)
        if attrs
        else round(market.player_quality(p), 1)
    )
    # One classification for the whole app: the profile's stream_status
    # helper decides what counts as "heavy" — the bool is just that read.
    stream_status = social.stream_status(p.stream_load)
    return {
        "id": p.id,
        "handle": p.handle,
        "real_name": p.real_name,
        "age": p.age,
        "role": str(p.role),
        "playstyle": str(p.playstyle),
        # IGL is a public player identity flag. Keep it explicit in views so
        # clients can filter without encoding roster semantics themselves.
        "is_igl": str(p.playstyle) == "igl",
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
        # Streaming (public, like followers): how much they stream, the org's
        # weekly cut, and the practice/growth cost of it.
        "stream_load": round(p.stream_load, 1),
        "stream_status": stream_status,
        "stream_heavy": stream_status == "heavy streamer",
        "stream_income": economy.player_stream_income(p),
        "stream_growth_mult": round(training.stream_practice_mult(p), 2),
        "dev_focus": p.dev_focus,
        "training_intensity": p.training_intensity,
        "learning_language": p.learning_language,
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
        # Even an own-club read is an outcome projection, not a revealed cap.
        "potential_stars": (
            development.stars(
                sum(
                    _roster_potential_projection(gs, p)
                    if market.team_of(gs, p.id) == gs.acting_team_id
                    else development.potential_projection(p, own=True)
                ) / 2.0
            ) if fog <= 0 else None
        ),
        "ca_stars": development.stars(overall),
        "is_free_agent": p.id in gs.free_agent_ids,
        "asking_salary": market.asking_salary(p),
        "portrait": _portrait_url(p.id, str(p.role)),
        # Badges are public (earned at public moments) — shown for any player.
        "badges": _badge_views(p),
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
        "series_notes": list(f.series_notes),
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
# Last-match review ("why you won/lost")
#
# The diagnosis engine (manager/match_review.py) stores numbers + a stable
# code; wording lives here (so it can change with no save migration) and depth
# is gated SERVER-SIDE by the analyst's analytics tier — the client renders
# whatever arrives. tone drives colour; lever_code maps a breaking point to a
# concrete fix, gated/ordered by the coach.

# code -> tone-specific headline + a detail template over {num}/{den}/{pct}/{val}.
_REVIEW_COPY = {
    "atk_side": ("Attack is clicking", "Attack is stalling",
                 "{num}/{den} attack rounds won ({pct}%)."),
    "def_side": ("Defense is a wall", "Defense is leaking",
                 "{num}/{den} defense rounds won ({pct}%)."),
    "pistol": ("Pistols won", "Pistols lost",
               "{num}/{den} pistol rounds ({pct}%)."),
    "player_std": ("{handle} carried", "{handle} carried",
                   "Team-high {val} average rating."),
    "player_under": ("{handle} off-colour", "{handle} off-colour",
                     "{val} average rating across the series."),
    "opening": ("Winning the opening duels", "Losing the opening duels",
                "{num}/{den} first bloods ({pct}%)."),
    "clutch": ("Clutch when it counts", "No clutches closed",
               "{num}/{den} last-alive rounds won."),
    "trades": ("Trading deaths well", "Deaths going untraded",
               "{num}/{den} deaths traded ({pct}%)."),
    "economy": ("Stealing gun rounds", "Eco rounds wasted",
                "{num}/{den} under-gunned rounds won."),
    "post_plant": ("Closing out post-plants", "Losing post-plants",
                   "{num}/{den} planted rounds won ({pct}%)."),
    "retake": ("Retakes landing", "Retakes failing",
               "{num}/{den} enemy plants retaken ({pct}%)."),
    "comms": ("Clean comms", "Crossed comms",
              "{num} miscalls in {den} rounds ({pct}%)."),
    "utility": ("Utility on point", "Utility whiffing",
                "{num}/{den} abilities whiffed ({pct}%)."),
}

# lever_code -> where the fix lives + the coach specialty that owns it + copy.
_REVIEW_LEVERS = {
    "atk_tempo": {"tab": "tactics", "specialty": "tactical",
                  "text": "Attack is stalling — raise pace/aggression or set a "
                          "defined default on the Tactics screen."},
    "def_setups": {"tab": "tactics", "specialty": "tactical",
                   "text": "Defense is leaking — tighten map control (stack) and "
                           "utility discipline in Tactics."},
    "pistol_prep": {"tab": "training", "specialty": "tactical",
                    "text": "Pistols are costing you — drill pistol setups "
                            "(tactical focus) and rein in eco greed."},
    "entry_support": {"tab": "tactics", "specialty": "mechanical",
                      "text": "Entries are losing first contact — trade tighter "
                              "(lower aggression) or sharpen aim (mechanical focus)."},
    "clutch_mental": {"tab": "training", "specialty": "mental",
                      "text": "No clutches are landing — mental training builds "
                              "composure in 1vX spots."},
    "aim_training": {"tab": "training", "specialty": "mechanical",
                     "text": "You're being out-fragged — mechanical training "
                             "closes the raw-aim gap."},
    "trade_discipline": {"tab": "tactics", "specialty": "tactical",
                         "text": "Deaths go untraded — spread less (map control) "
                                 "and drill trade pairs."},
    "eco_discipline": {"tab": "tactics", "specialty": "tactical",
                       "text": "Eco rounds are wasted — tune eco greed so "
                               "force-buys and saves line up."},
    "post_plant": {"tab": "training", "specialty": "tactical",
                   "text": "Post-plants are slipping — tactical training tightens "
                           "your post-plant setups."},
    "retake_util": {"tab": "tactics", "specialty": "tactical",
                    "text": "Retakes are failing — raise utility discipline to "
                            "coordinate the retake."},
    "comms_cohesion": {"tab": "roster", "specialty": "team",
                       "text": "Crossed comms stall rotations — build cohesion "
                               "(chemistry/lineup) on the Roster screen."},
    "util_discipline": {"tab": "tactics", "specialty": "tactical",
                        "text": "Utility is whiffing — raise utility discipline "
                                "so lineups land."},
    "player_form": {"tab": "roster", "specialty": "team",
                    "text": "{handle} is off-colour — consider a bench/agent swap "
                            "or set their dev focus on the Roster screen."},
}


def _player_developing(gs: GameState, pl: Player) -> tuple[bool, list[int]]:
    """Is this player still climbing toward a higher ceiling (so an off week is
    a development call, not a drop call)? Reads the potential PROJECTION band —
    young + real headroom == developing. Returns (developing, [lo, hi])."""
    lo, hi = (
        _roster_potential_projection(gs, pl)
        if market.team_of(gs, pl.id) == gs.acting_team_id
        else development.potential_projection(pl, own=True)
    )
    ovr = development.overall(pl)
    developing = pl.age <= 23 and (hi - ovr) >= 4.0
    return developing, [round(lo), round(hi)]


def _review_point_view(gs: GameState, p) -> dict:
    """Render one stored ReviewPoint into display copy (headline + detail).
    Player-scoped points carry the player's badges (clutch_master, choker, ...)
    and, for the off-colour flag, a potential-aware develop-vs-replace note."""
    handle = ""
    pl = None
    if p.player_id:
        pl = gs.players.get(p.player_id)
        handle = pl.handle if pl else p.player_id
    if p.code == "acs_gap":
        head = "Out-fragging the opponent" if p.tone == "good" else "Being out-fragged"
        detail = f"{p.num} ACS vs {p.den} — a {abs(int(round(p.value)))}-point gap."
    else:
        good_head, bad_head, tmpl = _REVIEW_COPY.get(
            p.code, (p.code, p.code, "{num}/{den}")
        )
        head = (good_head if p.tone == "good" else bad_head).format(handle=handle)
        pct = int(round(p.value * 100))
        detail = tmpl.format(
            num=p.num, den=p.den, pct=pct, val=round(p.value, 2), handle=handle
        )
    out = {
        "code": p.code,
        "category": p.category,
        "tone": p.tone,
        "headline": head,
        "detail": detail,
        "player_id": p.player_id or None,
        "handle": handle or None,
        # Badges are public — surface the relevant honours/stigmas on the line
        # (a Choker off-colour or a Clutch Master carry reads instantly).
        "badges": _badge_views(pl) if pl else [],
    }
    if p.code == "player_under" and pl is not None:
        developing, band = _player_developing(gs, pl)
        out["dev_note"] = (
            f"Young with room (proj. {band[0]}–{band[1]}) — a development call, "
            "not a bench."
            if developing
            else f"Near their ceiling (proj. {band[0]}–{band[1]}) — a lineup call."
        )
    return out


def _last_match_review(
    gs: GameState, event_logs: dict[str, list[list[Event]]] | None = None
) -> dict | None:
    """The acting team's most recent match diagnosis, depth-gated by the
    analyst's tier and given coach-gated 'what to tweak' levers. None when
    there's no review yet (first week / AI-only path)."""
    review = gs.last_review_by.get(gs.acting_team_id)
    if review is None:
        return None
    tier = staff_mod.analytics_tier(gs)
    opp = gs.teams.get(review.opp_id)
    potm = gs.players.get(review.potm_id) if review.potm_id else None

    out: dict = {
        "fixture_id": review.fixture_id,
        "won": review.won,
        "contested": review.contested,
        "best_of": review.best_of,
        "your_maps": review.your_maps,
        "their_maps": review.their_maps,
        "your_rounds": review.your_rounds,
        "their_rounds": review.their_rounds,
        "opp_id": review.opp_id,
        "opp_name": opp.name if opp else review.opp_id,
        "potm": (
            {
                "player_id": review.potm_id,
                "handle": potm.handle,
                "badges": _badge_views(potm),
            }
            if potm else None
        ),
        "tier": tier,
        "tier_label": staff_mod.ANALYTICS_TIER_LABEL.get(tier, ""),
        "momentum_beat": None,
    }
    logs = (event_logs or {}).get(review.fixture_id, [])
    if logs:
        team_of = {
            pid: tid
            for tid in (gs.acting_team_id, review.opp_id)
            if tid in gs.teams
            for pid in gs.teams[tid].player_ids
        }
        beats = [
            momentum_mod.momentum_beat(momentum_mod.momentum_trace(events, team_of))
            for events in logs
        ]
        beat = max(
            (b for b in beats if b is not None),
            key=lambda b: (b["rounds"], b["peak"], b["player_id"]),
            default=None,
        )
        if beat is not None:
            player = gs.players.get(beat["player_id"])
            handle = player.handle if player else beat["player_id"]
            out["momentum_beat"] = {
                **beat,
                "handle": handle,
                "text": f"got {beat['tone']} mid-map ({beat['rounds']}-round run).",
            }
    if not review.contested:
        out["working"] = []
        out["breaking"] = []
        out["levers"] = []
        out["locked"] = False
        return out

    vis_working = [p for p in review.working if p.min_tier <= tier]
    vis_breaking = [p for p in review.breaking if p.min_tier <= tier]
    out["working"] = [_review_point_view(gs, p) for p in vis_working[:4]]
    out["breaking"] = [_review_point_view(gs, p) for p in vis_breaking[:5]]

    # 'What to tweak' — levers from the visible breaking points, gated by the
    # coach's quality (how many) and ordered so the coach's specialty leads.
    coach = gs.staff.get("coach")
    levers: list[dict] = []
    if coach is not None:
        cap = 1 if coach.quality < 40 else 2 if coach.quality < 70 else 3
        seen: set[str] = set()
        cand = []
        for p in vis_breaking:
            spec = _REVIEW_LEVERS.get(p.lever_code)
            if not p.lever_code or spec is None or p.lever_code in seen:
                continue
            seen.add(p.lever_code)
            handle = ""
            pl = None
            if p.player_id:
                pl = gs.players.get(p.player_id)
                handle = pl.handle if pl else p.player_id
            text = spec["text"].format(handle=handle)
            # A high-ceiling youngster off-colour is a development call, not a
            # drop — steer the lever by the potential system when we can.
            if p.lever_code == "player_form" and pl is not None:
                developing, _band = _player_developing(gs, pl)
                text = (
                    f"{handle} is off-colour but still developing — set their "
                    "dev focus or pair a mentor on the Roster screen."
                    if developing
                    else f"{handle} is off-colour — consider a bench or agent "
                    "swap on the Roster screen."
                )
            adjustment = match_review_mod.tactic_adjustment(
                gs.teams[gs.acting_team_id].tactics,
                p.lever_code,
                coach.quality,
                tier,
            )
            if adjustment is not None:
                if adjustment["at_limit"]:
                    text = (
                        f"Keep {adjustment['label']} at {adjustment['target']} — "
                        "this slider is already at the coach's recommended limit. "
                        "If the issue persists, the remaining fix is execution or training."
                    )
                else:
                    text = (
                        f"Set {adjustment['label']} to {adjustment['target']} "
                        f"(currently {adjustment['current']}) — "
                        f"{adjustment['reason']}"
                    )
            cand.append((
                0 if spec["specialty"] == coach.specialty else 1,
                {
                    "code": p.lever_code,
                    "tab": "tactics" if adjustment is not None else spec["tab"],
                    "specialty": spec["specialty"],
                    "on_focus": spec["specialty"] == coach.specialty,
                    "text": text,
                    "adjustment": adjustment,
                },
            ))
        cand.sort(key=lambda t: t[0])  # specialty-matches first; stable otherwise
        # One clear target per slider. Several symptoms can diagnose the same
        # dial (e.g. weak trades and leaky setups both point to map control),
        # but repeating the same move is not additional coaching value.
        used_dials: set[str] = set()
        for _priority, item in cand:
            adjustment = item["adjustment"]
            dial = adjustment["dial"] if adjustment else ""
            if dial and dial in used_dials:
                continue
            if dial:
                used_dials.add(dial)
            levers.append(item)
            if len(levers) >= cap:
                break
    out["levers"] = levers
    out["coach"] = {
        "present": coach is not None,
        "specialty": coach.specialty if coach else "",
    }

    # Locked hint: higher-tier signals exist but the analyst can't surface them.
    hidden = [
        p for p in (review.working + review.breaking) if p.min_tier > tier
    ]
    out["locked"] = bool(hidden)
    if hidden and tier < 3:
        out["locked_hint"] = (
            f"A stronger analyst would surface {staff_mod.ANALYTICS_TIER_LABEL.get(tier + 1, '')}."
        )
    return out


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


@app.get("/api/lobby/preview")
def lobby_preview(seed: int = 2026) -> dict:
    """The fictional (non-pack) world's team roster for a given seed. The
    generated league changes with the seed, so the lobby re-fetches this
    whenever the seed box changes — otherwise a solo start at a random seed
    would build a different world than the teams shown, and the pick would
    422 in create_game. Roster-pack teams are static (seed-independent), so
    the client renders those straight from the packs payload."""
    return {"teams": _team_options(new_campaign(_LOBBY.gd, seed=seed), taken=set())}


_PACK_OPTIONS_CACHE: tuple[tuple[tuple[str, int], ...], list[dict]] | None = None


def _pack_options() -> list[dict]:
    """Installed roster packs with their pickable (tier-1) teams — straight
    from pack data, no campaign build needed. The filesystem revision makes
    writes from Roster Studio or the separate MCP process visible live."""
    global _PACK_OPTIONS_CACHE
    revision = roster_workbench.library_revision()
    if _PACK_OPTIONS_CACHE is not None and _PACK_OPTIONS_CACHE[0] == revision:
        return _PACK_OPTIONS_CACHE[1]
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
    _PACK_OPTIONS_CACHE = (revision, out)
    return out


# ---------------------------------------------------------------------------
# Roster Studio


_ROSTER_PACK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _roster_pack_id(pack_id: str) -> str:
    if not _ROSTER_PACK_ID_RE.fullmatch(pack_id):
        raise HTTPException(422, "invalid roster pack id")
    return pack_id


@app.get("/api/roster-studio/schema")
def roster_studio_schema() -> dict:
    """Frozen JSON Schema + game catalog for agent and UI clients."""
    return roster_workbench.schema_bundle(_LOBBY.gd)


@app.get("/api/roster-studio/packs")
def roster_studio_packs() -> dict:
    return {"packs": roster_workbench.list_documents()}


@app.get("/api/roster-studio/packs/{pack_id}")
def roster_studio_pack(pack_id: str) -> dict:
    pack_id = _roster_pack_id(pack_id)
    try:
        document = roster_workbench.load_document(pack_id)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown roster pack '{pack_id}'") from None
    except ValueError as exc:
        raise HTTPException(422, f"pack is not editable in Roster Studio: {exc}") from exc
    return {"document": document.model_dump(mode="json")}


@app.post("/api/roster-studio/validate")
def roster_studio_validate(body: dict) -> dict:
    # Deliberately returns a 200 with field errors: incomplete documents are a
    # normal state while the visual editor or an agent is drafting.
    return roster_workbench.validate_document(body, _LOBBY.gd)


@app.post("/api/roster-studio/parse")
def roster_studio_parse(body: dict) -> dict:
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(422, "text must be a YAML or JSON string")
    try:
        document = roster_workbench.parse_document(text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "document": document,
        "validation": roster_workbench.validate_document(document, _LOBBY.gd),
    }


@app.put("/api/roster-studio/packs/{pack_id}")
def roster_studio_save(pack_id: str, body: dict) -> dict:
    global _PACK_OPTIONS_CACHE
    _require_local_admin()
    pack_id = _roster_pack_id(pack_id)
    if body.get("id") != pack_id:
        raise HTTPException(422, "URL pack id must match document id")
    try:
        result = roster_workbench.install_document(body)
    except (ValueError, SystemExit) as exc:
        raise HTTPException(422, str(exc)) from exc
    # Roster Studio is a live authoring surface, so newly installed/updated
    # packs must appear in the Play lobby without restarting the server.
    _PACK_OPTIONS_CACHE = None
    return result


@app.get("/api/roster-studio/packs/{pack_id}/export")
def roster_studio_export(pack_id: str) -> Response:
    pack_id = _roster_pack_id(pack_id)
    try:
        text = roster_workbench.dump_document(
            roster_workbench.load_document(pack_id)
        )
    except FileNotFoundError:
        raise HTTPException(404, f"unknown roster pack '{pack_id}'") from None
    return Response(
        content=text,
        media_type="application/yaml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{pack_id}.roster-pack.yaml"'
            )
        },
    )


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
    preview = new_campaign(
        _LOBBY.gd, seed=seed, pack=pk, user_team_id=_preview_team(_LOBBY.gd, pk)
    )
    offers = career.new_game_offers(preview, 0)
    return {"offers": [_offer_view(preview, o) for o in offers]}


def _preview_team(gd: GameData, pack) -> str:
    """A team id that exists in the world being previewed. Roster packs
    replace the fictional starters, so 'team_nexus' isn't a safe default
    there — pick the pack's first tier-1 club, like the CLI preview."""
    if pack is not None:
        return sorted(t.id for t in pack.teams.values() if t.tier == 1)[0]
    return "team_nexus"


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


class DeleteWorldBody(BaseModel):
    code: str


@app.post("/api/delete_world")
def delete_world(body: DeleteWorldBody) -> dict:
    """Delete a saved world from the requesting browser's lobby list."""
    err = _LOBBY.delete_world(_current_sid(), body.code.upper())
    if err is not None:
        raise HTTPException(409, err)
    return {"ok": True, "code": body.code.upper()}


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
        telemetry.record_action(
            gs, "accept_job", {"seat": seat.id}, team_id=body.team_id
        )
        game = ctx.game
        game.ready.discard(gs.acting_team_id)
        gs.set_acting(body.team_id)
        game.save(force=True)  # a career move must survive a restart
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
        team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
        out.append({
            "pid": pid, "handle": gs.players[pid].handle,
            "team": team.name if team else "",
            "team_id": team.id if team else None,
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
            # A grounded prose preview synthesising form / series / stakes.
            next_fixture["preview"] = narrative.match_preview(
                gs, fixture, gs.acting_team_id
            )
            # Map pool + a suggested veto vs this opponent (needs prior maps
            # from both sides; the board simply hides its veto until then).
            next_fixture["map_pool"] = _map_pool_board(
                gs, gs.acting_team_id, opp_id
            )
        pending_flavor = flavor_events.pending_for(gs)
        flavor_view = flavor_events.to_api(pending_flavor) if pending_flavor else None
        if flavor_view is not None:
            flavor_view = llm_flavor.overlay(S.code, flavor_view)
            llm_flavor.enqueue(S.code, flavor_view)
        scout_target = gs.scout_target
        scout_label = None
        scout_cap = SCOUT_DEEP_CAP
        if scout_target == "market":
            scout_label = "Free-agent market"
            scout_cap = SCOUT_SURVEY_CAP
        elif scout_target in gs.teams:
            scout_label = gs.teams[scout_target].name
            scout_cap = SCOUT_SURVEY_CAP
        elif scout_target and scout_target.startswith("player:"):
            watched = gs.players.get(scout_target[len("player:"):])
            scout_label = watched.handle if watched else "Player"
        elif scout_target and scout_target.startswith("match:"):
            scout_label = "Match assignment"
            scout_cap = SCOUT_MATCH_CAP
        return {
            "season": gs.season,
            "week": gs.week,
            "phase": gs.phase,
            "window": market.market_window_status(gs),
            "user_team": _team_view(user, gs),
            "next_fixture": next_fixture,
            # Dashboard hub extras: this season's rating leaders (league-wide)
            # and your roster's biggest week-over-week ability movers, plus
            # the upcoming run-in difficulty and living-history callbacks.
            "leaders": _league_leaders(gs),
            "movers": _roster_movers(gs, gs.acting_team_id),
            "run_in": _fixture_run_in(gs, gs.acting_team_id),
            "on_this_day": analytics.on_this_day(gs),
            # A debrief of the last result, the objectives to chase, and the
            # squad's rotation/burnout picture.
            "debrief": narrative.match_debrief(gs, gs.acting_team_id),
            # The "why you won/lost" synthesis of the last match — working vs
            # breaking signals + coach-gated fixes, depth-gated by the analyst.
            "last_match_review": _last_match_review(gs, S.event_logs),
            "press": narrative.press_reaction(gs, gs.acting_team_id),
            # A read-only 'best available five' suggestion + legacy job security.
            "suggested_lineup": _suggested_lineup(gs, gs.acting_team_id),
            "board": _board_standing(gs),
            # Season form trendline + squad age/contract profile.
            "form_trend": _form_trend(gs, gs.acting_team_id),
            "squad_profile": _squad_profile(gs, gs.acting_team_id),
            "objectives_hub": _objectives_hub(gs, gs.acting_team_id),
            "rotation": _rotation_usage(gs, gs.acting_team_id),
            "training_focus": gs.training_focus.get(gs.acting_team_id, "tactical"),
            "focus_options": FOCUS_OPTIONS,
            "news": list(reversed(gs.news[-12:])),
            "scout": {
                "target": scout_target,
                "target_name": scout_label,
                "progress": gs.scout_progress.get(scout_target or "", 0.0),
                "cap": scout_cap,
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
            # A queued flavor event is a real choice gate. Its server view
            # intentionally has no outcomes/effects until a choice resolves.
            "flavor_event": flavor_view,
            "media_event": (
                media_events.to_api(gs, media_events.pending_for(gs))
                if media_events.pending_for(gs) is not None else None
            ),
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
            # Save policy + dirty flag (the topbar Save button's state).
            "save": {
                "dirty": S.dirty,
                "autosave_enabled": gs.autosave_enabled,
                "autosave_every_weeks": gs.autosave_every_weeks,
            },
        }


def _club_view(gs: GameState) -> dict:
    tid = gs.acting_team_id
    team = gs.teams[tid]
    fixture = gs.team_fixture(tid)
    opponent = None
    if fixture is not None:
        opponent = fixture.team_b if fixture.team_a == tid else fixture.team_a
    prep = preparation.view(gs, tid)
    partners = [
        {"id": other, "name": gs.teams[other].name}
        for other in sorted(gs.teams)
        if other not in (tid, opponent) and gs.teams[other].player_ids
    ]
    culture_view = culture.culture_snapshot(gs, tid)
    culture_view["players"] = [
        {
            "id": pid,
            "handle": gs.players[pid].handle,
            "age": gs.players[pid].age,
            "tenure_weeks": gs.players[pid].tenure_weeks,
            "leadership": culture.leadership_score(gs, tid, pid),
        }
        for pid in sorted(team.player_ids)
    ]
    directive = gs.series_directives_by.get(tid)
    series_fixture = next(
        (
            f for f in sorted(gs.fixtures, key=lambda x: (x.week, x.id))
            if not f.played and f.best_of >= 3 and tid in (f.team_a, f.team_b)
        ),
        None,
    )
    registration = series_management.registration_for(gs, tid)
    if not registration:
        registration = series_management.auto_registration(gs, tid)
    series_starters = (
        series_management.starting_five(gs, tid, series_fixture)
        if series_fixture else []
    )
    academy_view = academy.academy_view(gs, tid)
    return {
        "market_window": market.market_window_status(gs),
        "academy": academy_view,
        "preparation": {
            **prep,
            "fixture": _fixture_view(fixture, gs) if fixture else None,
            "opponent_id": opponent,
            "maps": list(fixture.maps) if fixture else [],
            "partners": partners,
            "objectives": list(preparation.OBJECTIVES),
            "intensities": list(preparation.INTENSITIES),
        },
        "registration": {
            "player_ids": registration,
            "locked": gs.phase != "regular",
            "limit": market.TOURNAMENT_REGISTER,
            "players": [
                {
                    "id": pid,
                    "handle": gs.players[pid].handle,
                    "age": gs.players[pid].age,
                    "role": gs.players[pid].roster_role,
                }
                for pid in sorted(team.player_ids)
            ],
        },
        "series": {
            "fixture": _fixture_view(series_fixture, gs) if series_fixture else None,
            "directive": directive.model_dump(mode="json") if directive else None,
            "triggers": list(series_management.TRIGGERS),
            "responses": list(series_management.RESPONSES),
            "starter_ids": series_starters,
            "bench_ids": [pid for pid in registration if pid not in series_starters],
        },
        "culture": culture_view,
        "principles": list(culture.PRINCIPLES),
        "culture_sessions": culture.session_status(gs, tid),
        "delegation": delegation.view(gs, tid),
        "media": media_events.view(gs, tid),
    }


@app.get("/api/club")
def club_view() -> dict:
    with S.lock:
        return _club_view(S.require_gs())


class AcademyMoveBody(BaseModel):
    player_id: str
    direction: str


@app.post("/api/actions/academy_move")
def academy_move(body: AcademyMoveBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = academy.move_player(
            gs,
            gs.acting_team_id,
            body.player_id,
            body.direction,
            window_check=lambda state, team_id: market.market_move_allowed(
                state, team_id, emergency_ok=False
            ),
        )
        if not ok:
            raise HTTPException(422, msg)
        culture.ensure_leadership(gs)
        telemetry.record_action(
            gs, "academy_move", {"player_id": body.player_id, "direction": body.direction}
        )
        S.save()
        return {"ok": True, "message": msg}


@app.post("/api/actions/academy_upgrade")
def academy_upgrade() -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = academy.upgrade(gs, gs.acting_team_id)
        if not ok:
            raise HTTPException(422, msg)
        telemetry.record_action(gs, "academy_upgrade", {})
        S.save()
        return {"ok": True, "message": msg}


class DelegationPolicyBody(BaseModel):
    auto_renew_core: bool = False
    renewal_salary_min: int = 800
    renewal_salary_max: int = 8_000
    renewal_trigger_weeks: int = 8
    auto_scout: bool = False
    scout_region: str = "pacific"
    scout_roles: list[str] = ["initiator"]
    scout_max_age: int = 21
    alert_level: str = "tier1_ready"


@app.post("/api/actions/delegation_policy")
def delegation_policy_action(body: DelegationPolicyBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        try:
            policy = delegation.configure(
                gs, gs.acting_team_id, body.model_dump(mode="json")
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        telemetry.record_action(
            gs, "set_delegation", policy.model_dump(mode="json")
        )
        S.save()
        return {"ok": True, "message": "staff responsibilities updated"}


class PreparationBody(BaseModel):
    fixture_id: str
    partner_id: str
    map_id: str
    objective: str
    intensity: str


@app.post("/api/actions/preparation")
def preparation_action(body: PreparationBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        try:
            plan = preparation.schedule(
                gs, gs.acting_team_id, body.fixture_id, body.partner_id,
                body.map_id, body.objective, body.intensity,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        telemetry.record_action(gs, "set_preparation", plan.model_dump(mode="json"))
        S.save()
        return {"ok": True, "message": "preparation session booked"}


class RegistrationBody(BaseModel):
    player_ids: list[str]


@app.post("/api/actions/tournament_registration")
def tournament_registration(body: RegistrationBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = series_management.register_roster(
            gs, gs.acting_team_id, body.player_ids
        )
        if not ok:
            raise HTTPException(422, msg)
        telemetry.record_action(
            gs, "tournament_registration", {"player_ids": ",".join(body.player_ids)}
        )
        S.save()
        return {"ok": True, "message": msg}


class SeriesDirectiveBody(BaseModel):
    fixture_id: str = ""
    trigger: str = "trailing"
    response: str = "steady"
    substitute_in: str | None = None
    substitute_out: str | None = None
    clear: bool = False


@app.post("/api/actions/series_directive")
def series_directive(body: SeriesDirectiveBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        if body.clear:
            series_management.clear_directive(gs, gs.acting_team_id)
            msg = "between-map instruction cleared"
        else:
            ok, msg = series_management.set_directive(
                gs, gs.acting_team_id, body.fixture_id,
                trigger=body.trigger, response=body.response,
                substitute_in=body.substitute_in,
                substitute_out=body.substitute_out,
            )
            if not ok:
                raise HTTPException(422, msg)
        telemetry.record_action(
            gs, "series_directive",
            {"fixture_id": body.fixture_id, "trigger": body.trigger,
             "response": body.response,
             "substitute_in": body.substitute_in or "",
             "substitute_out": body.substitute_out or "",
             "clear": body.clear},
        )
        S.save()
        return {"ok": True, "message": msg}


class LeadershipBody(BaseModel):
    captain_id: str
    council_ids: list[str]
    principle: str


@app.post("/api/actions/leadership")
def leadership_action(body: LeadershipBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = culture.set_leadership(
            gs, gs.acting_team_id, body.captain_id,
            body.council_ids, body.principle,
        )
        if not ok:
            raise HTTPException(422, msg)
        telemetry.record_action(
            gs, "set_leadership",
            {"captain_id": body.captain_id,
             "council_ids": ",".join(body.council_ids),
             "principle": body.principle},
        )
        S.save()
        return {"ok": True, "message": msg}


class CultureSessionBody(BaseModel):
    action: str
    player_id: str | None = None


@app.post("/api/actions/culture_session")
def culture_session_action(body: CultureSessionBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg, effects = culture.culture_session(
            gs, gs.acting_team_id, body.action, body.player_id
        )
        if not ok:
            raise HTTPException(422, msg)
        telemetry.record_action(
            gs, "culture_session", {"action": body.action,
                                    "player_id": body.player_id or ""},
        )
        S.save()
        return {"ok": True, "message": msg, "effects": effects}


class SaveSettingsBody(BaseModel):
    autosave_enabled: bool
    autosave_every_weeks: int = 1


@app.post("/api/actions/save")
def save_now() -> dict:
    """The explicit Save button: persist the world to disk right now."""
    with S.lock:
        S.require_gs()
        game = _ctx.get().game
        game.save(force=True)
        game.ticks_since_save = 0
        return {"ok": True, "message": "world saved"}


@app.post("/api/actions/save_settings")
def save_settings(body: SaveSettingsBody) -> dict:
    """Autosave policy for this WORLD (one save file per world, so one
    policy — shared worlds share it). The setting itself persists
    immediately so it survives a restart either way."""
    with S.lock:
        gs = S.require_gs()
        gs.autosave_enabled = bool(body.autosave_enabled)
        gs.autosave_every_weeks = max(1, min(8, int(body.autosave_every_weeks)))
        telemetry.record_action(
            gs, "save_settings",
            {
                "autosave_enabled": gs.autosave_enabled,
                "every_weeks": gs.autosave_every_weeks,
            },
        )
        game = _ctx.get().game
        game.save(force=True)
        label = (
            f"autosave every {gs.autosave_every_weeks} week"
            + ("s" if gs.autosave_every_weeks != 1 else "")
            if gs.autosave_enabled else "autosave off — use the Save button"
        )
        return {"ok": True, "message": label}


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
        players = [
            _player_view(p, gs, _player_fog(gs, p.id)[0])
            for p in gs.roster(team_id)
        ]
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
        # Rival rosters are buyable: show the seller's ask per player, and
        # the buyout clause where one exists (tier-2 contracts) — the fast
        # lane that skips negotiation entirely.
        tendencies: list[str] = []
        identity: str | None = None
        if team_id != gs.acting_team_id:
            for v in players:
                v["transfer_ask"] = market.transfer_ask(gs, v["id"])
                v["seller_stance"] = market.org_player_valuation(
                    gs, team_id, v["id"], "sell"
                )["stance"]
                v["buyout"] = market.buyout_fee(gs, v["id"])
                v["ask_breakdown"] = (
                    market.buyout_breakdown(gs, v["id"])
                    if v["buyout"] is not None
                    else market.transfer_ask_breakdown(gs, v["id"])
                )
        # Coaching identity: always readable for your own club, and for a
        # rival once you've scouted them enough to read their style.
        if own or gs.scout_progress.get(team_id, 0.0) >= 0.5:
            tac = gs.teams[team_id].tactics
            tendencies = _team_tendencies(tac)
            identity = _team_identity_label(tac)
        # Own club: a quick-glance form/confidence trend per player, from the
        # private dev-history time series (empty -> None, no arrow shown),
        # plus who mentors them (if anyone) for the mentorship control.
        if own:
            for v in players:
                v["condition_trend"] = _condition_trend(gs, v["id"])
                v["mentor_id"] = gs.mentorships.get(v["id"])
                pv = gs.players.get(v["id"])
                if pv is not None:
                    _cs = gs.career_stats.get(v["id"])
                    # Hidden teaching ability, so the manager can spot which
                    # veteran is worth pairing with a prospect (grows with age
                    # + experience; young players almost never rate high).
                    v["mentor_skill"] = round(
                        development.mentor_skill(pv, _cs.seasons if _cs else 0)
                    )
        development_report = (
            _development_report(gs, team_id, S.gd.attributes.definitions)
            if own
            else None
        )
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
                    "opponent_id": opp,
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
        # Locker-room pairs (own club only): handle pairs for display plus the
        # matching player-id pairs so the UI can link the names — both views
        # come from the SAME duos_and_feuds read, so they can't drift.
        pair_map = (
            relationships.duos_and_feuds(gs, team_id)
            if team_id == gs.acting_team_id
            else {"duos": [], "feuds": []}
        )
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
            "language_options": LANGUAGE_OPTIONS,
            "has_language_coach": "language_coach" in gs.staff,
            "development_report": development_report,
            "fog": round(fog, 1),
            "lineup_revealed": lineup_revealed,
            "scouting_this": gs.scout_target == team_id,
            "scout_progress": gs.scout_progress.get(team_id, 0.0),
            "scout_cap": SCOUT_SURVEY_CAP,
            "tendencies": tendencies,
            "identity": identity,
            # Comms cohesion (0-100): how well this roster can actually
            # talk, from pairwise language overlap. Public — nationality
            # and languages are broadcast facts.
            "comms_cohesion": relationships.team_comms_cohesion(gs, team_id),
            "chemistry_pairs": {
                kind: [
                    [gs.players[a].handle, gs.players[b].handle]
                    for a, b in pairs
                    if a in gs.players and b in gs.players
                ]
                for kind, pairs in pair_map.items()
            },
            "chemistry_pair_ids": {
                kind: [
                    [a, b]
                    for a, b in pairs
                    if a in gs.players and b in gs.players
                ]
                for kind, pairs in pair_map.items()
            },
        }


def _fixture_run_in(gs: GameState, tid: str, n: int = 5) -> list[dict]:
    """The team's next `n` unplayed regular-season fixtures, rated by opponent
    strength (world rank) — a run-in difficulty read for planning. Pure read."""
    upcoming = [
        f for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id))
        if f.tier == 1 and not f.played and f.stage == "regular"
        and f.week >= gs.week and tid in (f.team_a, f.team_b)
    ]
    out = []
    for f in upcoming[:n]:
        opp = f.team_b if f.team_a == tid else f.team_a
        wr = gs.teams[opp].world_rank if opp in gs.teams else None
        diff = (
            "hard" if (wr is not None and wr <= 6)
            else "medium" if (wr is not None and wr <= 14)
            else "easy"
        )
        out.append({
            "week": f.week,
            "opponent": gs.teams[opp].name if opp in gs.teams else opp,
            "opponent_id": opp if opp in gs.teams else None,
            "opp_rank": wr,
            "difficulty": diff,
        })
    return out


def _wonderkid_watch(gs: GameState, n: int = 6) -> list[dict]:
    """League-wide young prospects by projected peak, never hidden PA."""
    cands = []
    for p in gs.players.values():
        if p.age <= 20:
            projection = development.potential_projection(p, own=True)
            cands.append((p, development.stars(sum(projection) / 2.0)))
    cands.sort(key=lambda pc: (-pc[1], pc[0].id))
    out = []
    for p, pot in cands[:n]:
        team = next((t for t in gs.teams.values() if p.id in t.player_ids), None)
        out.append({
            "id": p.id, "handle": p.handle, "age": p.age, "role": str(p.role),
            "potential_stars": round(pot, 1),
            "team": team.name if team else "free agent",
            "team_id": team.id if team else None,
        })
    return out


def _challengers_standouts(gs: GameState, tid: str, n: int = 5) -> list[dict]:
    """The user region's top Challengers (tier-2) performers by rating —
    tomorrow's signings. Pure read of gs.player_stats."""
    region = str(gs.teams[tid].region)
    t2 = {
        pid
        for t in gs.teams.values()
        if t.tier == 2 and str(t.region) == region
        for pid in t.player_ids
    }
    elig = [
        (pid, st) for pid, st in gs.player_stats.items()
        if st.maps >= 3 and pid in t2 and pid in gs.players
    ]
    top = sorted(elig, key=lambda kv: (-kv[1].rating, kv[0]))[:n]
    out = []
    for pid, st in top:
        p = gs.players[pid]
        team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
        out.append({
            "id": pid, "handle": p.handle, "age": p.age, "role": str(p.role),
            "team": team.name if team else "",
            "team_id": team.id if team else None,
            "rating": round(st.rating, 2),
        })
    return out


def _dev_progress(gs: GameState, tid: str) -> list[dict]:
    """Own roster: how close each player is to their (projected) ceiling and
    which way they're trending, from the private dev-history series. Even your
    own academy's ceiling is a PROJECTION band that firms up with age — never
    an exact number — and it moves on monumental moments and mentorship. Also
    carries each player's hidden mentor_skill so the manager can pick a teacher
    worth pairing a prospect with."""
    from esports_sim.manager.campaign import _development_support_bonuses

    supports = _development_support_bonuses(gs, tid) or {}
    out = []
    for pid in gs.teams[tid].player_ids:
        p = gs.players.get(pid)
        if p is None:
            continue
        ca = development.overall(p)
        lo, hi = _roster_potential_projection(gs, p, tid)
        est = round((lo + hi) / 2.0, 1)  # shown forecast, which CA may exceed
        pct = min(100, round(100.0 * ca / est)) if est > 0 else 100
        snaps = gs.dev_history.get(pid, [])
        traj = "steady"
        if len(snaps) >= 3:
            d = snaps[-1].ca - snaps[-3].ca
            traj = "climbing" if d > 0.3 else "declining" if d < -0.3 else "steady"
        cs = gs.career_stats.get(pid)
        overperforming = ca > development.potential_of(p) + 0.05
        out.append({
            "id": pid, "handle": p.handle, "age": p.age,
            "ca": round(ca), "potential": round(est),
            "potential_band": [round(lo), round(hi)], "progress_pct": pct,
            "trajectory": traj, "maxed": pct >= 97 and not overperforming,
            "overperforming": overperforming,
            "curve_read": development.curve_read(p),
            "support_bonus": supports.get(pid, 0.0),
            "mentor_skill": round(development.mentor_skill(p, cs.seasons if cs else 0)),
        })
    out.sort(key=lambda r: (-r["potential"], r["handle"]))
    return out


def _development_report(gs: GameState, tid: str, attr_defs: dict) -> dict:
    """Current-season growth report for the manager's present roster.

    This is a pure read of stored development snapshots. Attribute deltas are
    only emitted when both endpoints contain that attribute, which lets an old
    save begin tracking cleanly without pretending its current values were the
    season-opening baseline.
    """
    rows = []
    for pid in gs.teams[tid].player_ids:
        p = gs.players.get(pid)
        if p is None:
            continue
        snaps = [s for s in gs.dev_history.get(pid, []) if s.season == gs.season]
        if not snaps:
            continue
        first, last = snaps[0], snaps[-1]
        delta = round(last.ca - first.ca, 1)
        status = "grown" if delta >= 0.1 else "regressed" if delta <= -0.1 else "steady"
        changes = []
        for aid in sorted(set(first.attributes) & set(last.attributes)):
            change = round(last.attributes[aid] - first.attributes[aid], 1)
            if abs(change) < 0.1:
                continue
            definition = attr_defs.get(aid)
            changes.append({
                "id": aid,
                "name": definition.display_name if definition else aid.replace("_", " ").title(),
                "category": str(definition.category) if definition else None,
                "start": first.attributes[aid],
                "current": last.attributes[aid],
                "delta": change,
            })
        changes.sort(key=lambda item: (-abs(item["delta"]), item["name"]))
        rows.append({
            "id": pid,
            "handle": p.handle,
            "start_week": first.week,
            "end_week": last.week,
            "tracked_points": len(snaps),
            "overall_start": first.ca,
            "overall_current": last.ca,
            "overall_delta": delta,
            "status": status,
            "attribute_tracking": bool(first.attributes and last.attributes),
            "changes": changes,
        })
    rows.sort(key=lambda row: (-row["overall_delta"], row["handle"].lower(), row["id"]))
    deltas = [row["overall_delta"] for row in rows]
    return {
        "season": gs.season,
        "start_week": min((row["start_week"] for row in rows), default=None),
        "end_week": max((row["end_week"] for row in rows), default=None),
        "overall_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0.0,
        "grown": sum(row["status"] == "grown" for row in rows),
        "regressed": sum(row["status"] == "regressed" for row in rows),
        "steady": sum(row["status"] == "steady" for row in rows),
        "players": rows,
    }


def _signing_headroom(gs: GameState, tid: str) -> dict:
    """How much weekly wage the org can absorb at break-even, plus the current
    runway — a signing-budget aid. Pure read of the economy helpers."""
    staff_cost = staff_mod.weekly_cost(gs)
    net = economy.weekly_breakdown(gs, staff_cost)["net"]
    return {
        "weekly_net": net,
        "affordable_wage": max(0, net),
        "runway_weeks": economy.weeks_until_insolvent(gs, staff_cost),
        "balance": gs.teams[tid].balance,
    }


def _objectives_hub(gs: GameState, tid: str) -> list[dict]:
    """What this manager is chasing: the board season goal (legacy), active
    sponsor objectives, and any award race their players are contending —
    one consolidated 'what to chase' list. Pure read."""
    out: list[dict] = []
    seat = gs.seat_for_session(tid)
    if seat is not None and seat.contract is not None:
        st = career.objective_status(gs, tid, seat.contract.goal)
        out.append({
            "kind": "board",
            "label": career.GOAL_LABELS.get(seat.contract.goal, seat.contract.goal),
            "state": st["state"], "detail": st["detail"],
        })
    for slot, deal in sorted(gs.sponsor_slots.items()):
        if deal is None:
            continue
        for ob in deal.objectives:
            if ob.met is None:
                st = career.objective_status(gs, tid, ob.kind)
                out.append({
                    "kind": "sponsor",
                    "label": sponsors.OBJECTIVE_LABELS.get(ob.kind, ob.kind),
                    "state": st["state"], "detail": st["detail"],
                })
    own = set(gs.teams[tid].player_ids)
    for award, leaders in analytics.award_races(gs).items():
        for i, ldr in enumerate(leaders):
            if ldr["player_id"] in own:
                out.append({
                    "kind": "award",
                    "label": f"{ldr['handle']}: {award}",
                    "state": "leading" if i == 0 else "in contention",
                    "detail": f"{['1st', '2nd', '3rd'][i]} · {ldr['value']}",
                })
    return out


def _rotation_usage(gs: GameState, tid: str) -> list[dict]:
    """Per own-roster player: season maps played, starter/bench, and a
    burnout flag (heavy minutes on a low tank). Pure read."""
    starters = set(default_five(gs, tid))
    ids = gs.teams[tid].player_ids
    team_max = max(
        (gs.player_stats[p].maps for p in ids if p in gs.player_stats), default=0
    )
    out = []
    for pid in ids:
        p = gs.players.get(pid)
        if p is None:
            continue
        maps = gs.player_stats[pid].maps if pid in gs.player_stats else 0
        burnout = p.stamina < 40.0 and maps >= max(4, team_max * 0.6)
        out.append({
            "id": pid, "handle": p.handle, "maps": maps,
            "starter": pid in starters, "stamina": round(p.stamina),
            "burnout": burnout,
        })
    out.sort(key=lambda r: (-r["maps"], r["handle"]))
    return out


def _squad_chemistry(gs: GameState, tid: str) -> dict:
    """Roster chemistry: the strongest bonds and worst frictions among the
    team's players, plus overall cohesion (mean pair strength). Pure read of
    relationships.get; own-club intel."""
    ids = [pid for pid in gs.teams[tid].player_ids if pid in gs.players]
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pairs.append((a, b, relationships.get(gs, a, b)))
    if not pairs:
        return {"cohesion": None, "bonds": [], "frictions": []}

    def _view(a, b, s):
        return {
            "a": gs.players[a].handle, "a_id": a,
            "b": gs.players[b].handle, "b_id": b,
            "strength": round(s, 1),
        }

    bonds = [
        _view(a, b, s)
        for a, b, s in sorted(pairs, key=lambda t: (-t[2], t[0], t[1]))
        if s >= relationships.FRIEND_BAR
    ][:4]
    frictions = [
        _view(a, b, s)
        for a, b, s in sorted(pairs, key=lambda t: (t[2], t[0], t[1]))
        if s <= relationships.FEUD_BAR
    ][:4]
    cohesion = round(sum(s for _, _, s in pairs) / len(pairs), 1)
    return {"cohesion": cohesion, "bonds": bonds, "frictions": frictions}


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


def _team_map_record(gs: GameState, tid: str) -> dict[str, list[int]]:
    """{map_id: [played, wins]} for a team, from persisted map results."""
    agg: dict[str, list[int]] = {}
    for f in gs.fixtures:
        if not f.played or tid not in (f.team_a, f.team_b):
            continue
        for r in f.results:
            a = agg.setdefault(r.map_id, [0, 0])
            a[0] += 1
            if r.winner_id == tid:
                a[1] += 1
    return agg


def _map_pool_board(gs: GameState, tid: str, opp_id: str | None = None) -> dict:
    """A team's per-map win rates (the map pool) and — when an opponent is
    given — a suggested veto: ban where they hold the biggest edge, pick where
    you do. Pure read of persisted results."""
    mine = _team_map_record(gs, tid)

    def _name(mid: str) -> str:
        return S.gd.maps[mid].display_name if mid in S.gd.maps else mid

    def _wr(agg: dict[str, list[int]], mid: str) -> float | None:
        if mid in agg and agg[mid][0]:
            return agg[mid][1] / agg[mid][0]
        return None

    maps = [
        {
            "map": _name(mid), "map_id": mid,
            "played": played, "wins": wins,
            "win_rate": round(100 * wins / played) if played else None,
        }
        for mid, (played, wins) in mine.items()
    ]
    maps.sort(key=lambda m: (-(m["win_rate"] if m["win_rate"] is not None else -1), m["map"]))

    veto = None
    if opp_id and opp_id in gs.teams:
        opp = _team_map_record(gs, opp_id)
        # Shared universe: maps either side has actually played (real signal).
        universe = sorted(set(mine) | set(opp))
        ban_pick, pick_pick = None, None
        best_ban, best_pick = None, None
        for mid in universe:
            my, ot = _wr(mine, mid), _wr(opp, mid)
            if my is None or ot is None:
                continue
            edge_them = ot - my  # opponent's advantage -> ban candidate
            edge_me = my - ot    # our advantage -> pick candidate
            if best_ban is None or edge_them > best_ban:
                best_ban, ban_pick = edge_them, mid
            if best_pick is None or edge_me > best_pick:
                best_pick, pick_pick = edge_me, mid
        veto = {
            "opponent": gs.teams[opp_id].name,
            "ban": (
                {"map": _name(ban_pick), "map_id": ban_pick,
                 "their_wr": round(100 * _wr(opp, ban_pick)),
                 "our_wr": round(100 * _wr(mine, ban_pick))}
                if ban_pick else None
            ),
            "pick": (
                {"map": _name(pick_pick), "map_id": pick_pick,
                 "their_wr": round(100 * _wr(opp, pick_pick)),
                 "our_wr": round(100 * _wr(mine, pick_pick))}
                if pick_pick else None
            ),
        }
    return {"maps": maps, "veto": veto}


def _team_of_week(gs: GameState, n: int = 5) -> dict:
    """The best five players of the most recent completed match week, by mean
    rating across that week's maps. League-wide, pure read of stored lines."""
    played = [f for f in gs.fixtures if f.played]
    if not played:
        return {"week": None, "players": []}
    wk = max(f.week for f in played)
    agg: dict[str, list[float]] = {}  # pid -> [rating_sum, maps, kills, deaths]
    for f in played:
        if f.week != wk:
            continue
        for r in f.results:
            for ln in r.lines:
                a = agg.setdefault(ln.player_id, [0.0, 0, 0, 0])
                a[0] += ln.rating
                a[1] += 1
                a[2] += ln.kills
                a[3] += ln.deaths
    rows = []
    for pid, (rsum, maps, k, d) in agg.items():
        if maps == 0 or pid not in gs.players:
            continue
        p = gs.players[pid]
        team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
        rows.append({
            "id": pid, "handle": p.handle, "role": str(p.role),
            "team": team.name if team else "",
            "team_id": team.id if team else None,
            "rating": round(rsum / maps, 2),
            "kd": round(k / d, 2) if d else float(k),
            "maps": int(maps),
        })
    rows.sort(key=lambda r: (-r["rating"], r["id"]))
    return {"week": wk, "players": rows[:n]}


def _playoff_bracket(gs: GameState, region: str, tier: int = 1) -> list[dict]:
    """The current season's playoff tree: regional semis/final (this region)
    plus the global Champions final. Pure read of the bracket fixtures."""
    stages = [("semi", "Semifinals"), ("final", "Regional Final"),
              ("champ_final", "Champions Final")]
    out = []
    for stage, label in stages:
        matches = []
        fx = [f for f in gs.fixtures
              if f.stage == stage and f.id.startswith(f"s{gs.season}")]
        for f in sorted(fx, key=lambda f: f.id):
            ta, tb = f.team_a, f.team_b
            # Regional rounds are scoped to this region; champ_final is global.
            if stage in ("semi", "final"):
                if ta not in gs.teams or str(gs.teams[ta].region) != region:
                    continue
            a, b = f.map_score
            matches.append({
                "team_a": gs.teams[ta].name if ta in gs.teams else ta,
                "team_a_id": ta,
                "team_b": gs.teams[tb].name if tb in gs.teams else tb,
                "team_b_id": tb,
                "score_a": a, "score_b": b,
                "played": f.played, "winner_id": f.winner_id,
            })
        if matches:
            out.append({"stage": stage, "label": label, "matches": matches})
    return out


def _projected_standings(gs: GameState, region: str, tier: int = 1) -> list[dict]:
    """A simple 'if current form holds' projection of the final regional table:
    current wins + (win rate x remaining regular-season games). Deterministic,
    pure read — a manager aid, not the canonical result."""
    rows = []
    for tid in gs.standings_order(region, tier=tier):
        rec = gs.standings.get(tid)
        if rec is None:
            continue
        done = rec.wins + rec.losses
        win_rate = rec.wins / done if done else 0.5
        remaining = sum(
            1 for f in gs.fixtures
            if not f.played and f.stage == "regular"
            and tid in (f.team_a, f.team_b)
            and f.id.startswith(f"s{gs.season}")
        )
        rows.append({
            "team_id": tid, "name": gs.teams[tid].name,
            "wins": rec.wins, "losses": rec.losses,
            "remaining": remaining,
            "proj_wins": round(rec.wins + win_rate * remaining, 1),
        })
    rows.sort(key=lambda r: (-r["proj_wins"], r["name"]))
    for i, r in enumerate(rows):
        r["proj_pos"] = i + 1
    return rows


def _h2h_matrix(gs: GameState, region: str, tier: int = 1) -> dict:
    """A grid of every team's series record vs every other team in the region
    this season, reusing narrative.head_to_head (the canonical tally) so it
    can't drift. Cell [a][b] is a's wins-losses vs b."""
    order = gs.standings_order(region, tier=tier)
    teams = [{"team_id": t, "name": gs.teams[t].name} for t in order]
    rows = []
    for a in order:
        cells = []
        for b in order:
            if a == b:
                cells.append(None)
                continue
            h = narrative.head_to_head(gs, a, b)
            cells.append(
                {"w": h["wins_a"], "l": h["wins_b"], "played": h["meetings"]}
                if h["meetings"] else {"w": 0, "l": 0, "played": 0}
            )
        rows.append({"team_id": a, "cells": cells})
    return {"teams": teams, "rows": rows}


def _results_archive(gs: GameState, region: str, n: int = 24) -> list[dict]:
    """The region's most recent played fixtures, newest first — a results
    archive. Pure read of gs.fixtures."""
    played = [
        f for f in gs.fixtures
        if f.played and f.team_a in gs.teams
        and str(gs.teams[f.team_a].region) == region
    ]
    played.sort(key=lambda f: (f.week, f.id), reverse=True)
    out = []
    for f in played[:n]:
        a, b = f.map_score
        out.append({
            "week": f.week, "stage": f.stage,
            "team_a": gs.teams[f.team_a].name, "team_a_id": f.team_a,
            "team_b": gs.teams[f.team_b].name if f.team_b in gs.teams else f.team_b,
            "team_b_id": f.team_b,
            "score_a": a, "score_b": b, "winner_id": f.winner_id,
        })
    return out


def _form_trend(gs: GameState, tid: str) -> list[dict]:
    """Cumulative wins by week across the team's played regular-season
    fixtures — a season form trendline. Pure read."""
    fixtures = sorted(
        (
            f for f in gs.fixtures
            if f.played and tid in (f.team_a, f.team_b)
            and f.id.startswith(f"s{gs.season}")
        ),
        key=lambda f: (f.week, f.id),
    )
    trend, wins = [], 0
    for i, f in enumerate(fixtures, start=1):
        won = f.winner_id == tid
        if won:
            wins += 1
        trend.append({"n": i, "week": f.week, "wins": wins, "won": won})
    return trend


def _squad_profile(gs: GameState, tid: str) -> dict:
    """Own roster age mix + contract-expiry timeline. Pure read."""
    buckets = {"youth": 0, "prime": 0, "veteran": 0}
    ages, expiries = [], []
    for p in gs.roster(tid):
        ages.append(p.age)
        if p.age <= 21:
            buckets["youth"] += 1
        elif p.age <= 26:
            buckets["prime"] += 1
        else:
            buckets["veteran"] += 1
        expiries.append({
            "id": p.id, "handle": p.handle, "age": p.age,
            "weeks_left": p.contract_weeks_left,
        })
    expiries.sort(key=lambda e: (e["weeks_left"], e["handle"]))
    return {
        "avg_age": round(sum(ages) / len(ages), 1) if ages else 0.0,
        "buckets": buckets,
        "expiries": expiries,
    }


_IMPACT_CATS = (
    ("clutches", "Clutches", "clutches"),
    ("multikills", "Multikills", "multikills"),
    ("aces", "Aces", "aces"),
    ("first_kills", "First bloods", "first_kills"),
)


def _impact_leaders(gs: GameState, n: int = 5, league_tier: int = 1) -> dict:
    """League-wide highlight-stat leaderboards (clutches / multikills / aces /
    first bloods) from the stored season aggregates, filtered to one league
    tier so top-flight and Challengers boards stay separate. Pure read —
    these are summed at sim time by stats.py, never re-derived here."""
    out = {}
    for key, label, attr in _IMPACT_CATS:
        rows = []
        for pid, st in gs.player_stats.items():
            if pid not in gs.players or st.maps <= 0:
                continue
            if _player_league_tier(gs, pid) != league_tier:
                continue
            v = getattr(st, attr, 0)
            if v > 0:
                rows.append((v, pid))
        rows.sort(key=lambda kv: (-kv[0], kv[1]))
        out[key] = {
            "label": label,
            "leaders": [
                {
                    "player_id": pid, "value": v,
                    "handle": gs.players[pid].handle,
                    "team": next(
                        (t.name for t in gs.teams.values() if pid in t.player_ids), ""
                    ),
                }
                for v, pid in rows[:n]
            ],
        }
    return out


@app.get("/api/league")
def league() -> dict:
    """League-wide, forward-looking context for the standings screen: team of
    the week, the live playoff bracket, a form-hold projection, plus a
    head-to-head matrix and results archive. All pure reads."""
    with S.lock:
        gs = S.require_gs()
        region = str(gs.teams[gs.acting_team_id].region)
        tier = gs.teams[gs.acting_team_id].tier
        return {
            "team_of_week": _team_of_week(gs),
            "bracket": _playoff_bracket(gs, region, tier),
            "projection": _projected_standings(gs, region, tier),
            "h2h_matrix": _h2h_matrix(gs, region, tier),
            "results": _results_archive(gs, region),
            "in_regular_season": gs.phase == "regular",
        }


@app.get("/api/meta")
def meta_view() -> dict:
    """The live agent meta: the most recent balance patch, active buff/nerf
    standings, and a usage tier list (manager/meta.py). Pure read."""
    with S.lock:
        return meta_mod.meta_report(S.require_gs(), S.gd.agents)


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
    """The save's all-time record book, current top dynasties, and a league
    parity read (pure chronicle + career_stats; manager/analytics.py)."""
    with S.lock:
        gs = S.require_gs()
        return {**analytics.all_time_records(gs), "parity": analytics.parity(gs)}


@app.get("/api/report/season")
def season_report(season: int | None = None) -> dict:
    """A deterministic structured season summary — the headless analytics
    export (ROADMAP bet #2), also consumable by the web Season Review."""
    with S.lock:
        return analytics.season_report(S.require_gs(), season)


@app.get("/api/power")
def power_rankings() -> dict:
    """A global pundit power ranking across regions (record + form + diff),
    with movement vs world rank. Pure analytics read."""
    with S.lock:
        return {"rankings": analytics.power_rankings(S.require_gs())}


@app.get("/api/races")
def award_races() -> dict:
    """Mid-season award-race leaderboards (who's chasing MVP, Top Fragger,
    …) from the live season stats. Pure analytics read."""
    with S.lock:
        return {"races": analytics.award_races(S.require_gs())}


@app.get("/api/compare")
def compare(a: str, b: str) -> dict:
    """Two players side by side — attributes (scouting-fogged for rivals) and
    season stats — for the comparison overlay."""
    with S.lock:
        gs = S.require_gs()

        def side(pid: str) -> dict:
            p = gs.players.get(pid)
            if p is None:
                raise HTTPException(404, f"unknown player {pid}")
            fog, _progress, _is_fa = _player_fog(gs, pid)
            st = gs.player_stats.get(pid)
            has = st is not None and st.maps > 0
            team = market.team_of(gs, pid)
            return {
                "id": pid, "handle": p.handle, "age": p.age, "role": str(p.role),
                "team_name": gs.teams[team].name if team in gs.teams else None,
                "overall": None if fog > 0 else int(round(development.overall(p))),
                "attributes": _profile_attributes(gs, p, fog),
                "rating": round(st.rating, 2) if has else None,
                "kd": round(st.kd, 2) if has else None,
                "maps": st.maps if st else 0,
            }

        return {"a": side(a), "b": side(b)}


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
         "team": t.name, "team_id": t.id,
         "weeks_left": p.contract_weeks_left}
        for p, t in rivals[:n]
    ]
    return {"expiring_own": own, "market_watch": market_watch}


def _transfer_rumors(gs: GameState, tid: str, n: int = 5) -> list[dict]:
    """Deterministic transfer whispers: rival interest in your soon-to-be
    free-agent stars, and marquee free agents linked with a club that lacks
    their role. Pure read — the 'linked' club is a stable sorted pick, no
    rng, so the rumor mill is campaign-deterministic."""
    rumors: list[dict] = []
    for p in sorted(gs.roster(tid), key=lambda x: (-market.player_quality(x), x.id)):
        if 0 < p.contract_weeks_left <= 12 and market.player_quality(p) >= 70:
            rumors.append({
                "kind": "interest",
                "text": f"Rivals are circling {p.handle} with just "
                f"{p.contract_weeks_left}w left on his deal.",
            })
        if len([r for r in rumors if r["kind"] == "interest"]) >= 2:
            break
    fas = sorted(
        (gs.players[pid] for pid in gs.free_agent_ids),
        key=lambda x: (-market.player_quality(x), x.id),
    )[:3]
    for fa in fas:
        role = str(fa.role)
        needy = next(
            (
                t for t in sorted(gs.teams.values(), key=lambda t: t.id)
                if t.tier == 1
                and role not in {
                    str(gs.players[q].role) for q in t.player_ids if q in gs.players
                }
            ),
            None,
        )
        club = needy.name if needy else gs.teams[tid].name
        rumors.append({
            "kind": "link",
            "text": f"Free agent {fa.handle} ({role}) linked with a move to {club}.",
        })
    return rumors[:n]


@app.get("/api/market/search")
def market_search(q: str = "") -> dict:
    """League-wide player search by handle or real name — sign/trade targets.
    Fog mirrors the roster/market screens: a rival's exact rating hides
    behind their team's scout progress; free agents ride the market fog.
    Pure read; capped at 30 rows sorted by (visible) quality."""
    with S.lock:
        gs = S.require_gs()
        needle = q.strip().lower()
        if len(needle) < 2:
            return {"results": []}
        me = gs.acting_team_id
        rows = []
        for pid in sorted(gs.players):
            p = gs.players[pid]
            if (
                needle not in p.handle.lower()
                and needle not in (p.real_name or "").lower()
            ):
                continue
            is_fa = pid in gs.free_agent_ids
            team_id = None if is_fa else market.team_of(gs, pid)
            if not is_fa and team_id is None:
                continue  # unrostered mid-move: not a signable target
            fog, _progress, _ = _player_fog(gs, pid)
            fogged = fog > 0
            rival = team_id is not None and team_id != me
            rows.append({
                "id": pid,
                "handle": p.handle,
                "real_name": p.real_name,
                "role": str(p.role),
                "playstyle": str(p.playstyle),
                "age": p.age,
                "overall": round(development.overall(p)),
                "fogged": fogged,
                "team_id": team_id,
                "team_name": gs.teams[team_id].name if team_id else None,
                "is_free_agent": is_fa,
                "mine": team_id == me,
                "asking_salary": market.asking_salary(p) if is_fa else None,
                "transfer_ask": market.transfer_ask(gs, pid) if rival else None,
                "seller_stance": (
                    market.org_player_valuation(gs, team_id, pid, "sell")["stance"]
                    if rival else None
                ),
                "buyout": market.buyout_fee(gs, pid) if rival else None,
                "ask_breakdown": (
                    market.buyout_breakdown(gs, pid)
                    if rival and market.buyout_fee(gs, pid) is not None
                    else market.transfer_ask_breakdown(gs, pid) if rival else []
                ),
                "portrait": _portrait_url(pid, str(p.role)),
                "languages": _language_views(p),
            })
        rows.sort(key=lambda r: (-r["overall"], r["handle"]))
        return {"results": rows[:30]}


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
            view = _player_view(p, gs, fog=_player_fog(gs, p.id)[0])
            # Spoken languages: public facts, so the comms-fit read is
            # available at the decision point regardless of market fog.
            view["languages"] = _language_views(p)
            report = development.scout_report(gs, p, progress)
            view["scout"] = {
                "ca_stars": report["ca_stars"],
                "pa_stars": report["pa_stars"] if progress > 0 else None,
                "traits": report["traits"],
                "traits_hidden": report["traits_hidden"],
            }
            fit = relationships.locker_room_fit(gs, p.id, gs.acting_team_id)
            out.append({
                **view,
                "can_sign": ok,
                "block_reason": why,
                "locker_room_fit": {
                    "score": fit["average"],
                    "duos": len(fit["friends"]),
                    "feuds": len(fit["feuds"]),
                },
            })
        me = gs.acting_team_id
        needs = _squad_needs(gs, me)
        return {
            "free_agents": out,
            "roster_size": market.ROSTER_SIZE,
            "roster_min": market.ROSTER_MIN,
            "roster_max": market.roster_cap(gs, me),
            "roster_count": len(gs.roster(me)),
            "phase": gs.phase,
            "window": market.market_window_status(gs),
            # Decision aids: where the squad is thin, who to sign, and whose
            # contracts are running down (yours + rivals'). All pure reads.
            "squad_needs": needs,
            "target_suggestions": _target_suggestions(gs, me, needs),
            "contract_watch": _contract_watch(gs, me),
            "rumors": _transfer_rumors(gs, me),
            # Scouting/finance decision aids: league-wide young prospects, the
            # region's Challengers form book, and how much wage the org can
            # absorb before the runway floor. All pure reads.
            "wonderkids": _wonderkid_watch(gs),
            "challengers": _challengers_standouts(gs, me),
            "signing_headroom": _signing_headroom(gs, me),
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


def _trade_asset_view(gs: GameState, pid: str, viewer_id: str) -> dict:
    """One frozen trade-room row. All estimates and valuations are computed
    here; the browser only lays out the returned numbers."""
    p = gs.players[pid]
    owner = market.team_of(gs, pid)
    own = owner == viewer_id
    progress = 1.0 if own else max(
        gs.scout_progress.get(owner or "market", 0.0),
        gs.scout_progress.get(f"player:{pid}", 0.0),
    )
    performance_coach = gs.staff_by.get(viewer_id, {}).get("performance_coach")
    lo, hi = development.potential_projection(
        p,
        progress=progress,
        own=own,
        performance_coach_quality=(
            performance_coach.quality if own and performance_coach is not None else None
        ),
    )
    opinions = market.valuation_opinions(gs, viewer_id, p)
    return {
        "id": p.id,
        "handle": p.handle,
        "role": str(p.role),
        "age": p.age,
        "team_id": owner,
        "team_name": gs.teams[owner].name if owner else None,
        "overall": round(market.perceived_quality(gs, viewer_id, p)),
        "overall_estimated": not own,
        "potential": {
            "low": round(lo), "high": round(hi), "scouted": round(progress, 2)
        },
        "contract": {"salary": p.salary, "weeks_left": p.contract_weeks_left},
        "stream_revenue": economy.player_stream_income(p),
        "value": opinions,
        "portrait": _portrait_url(p.id, str(p.role)),
    }


class TradePreviewBody(BaseModel):
    target_pid: str
    out_pids: list[str] = []
    cash_out: int = 0
    cash_in: int = 0


@app.post("/api/trade/preview")
def trade_preview(body: TradePreviewBody) -> dict:
    """Live, read-only trade-room opinion for the acting org."""
    with S.lock:
        gs = S.require_gs()
        viewer = gs.acting_team_id
        if body.target_pid not in gs.players:
            raise HTTPException(404, "unknown player")
        target_owner = market.team_of(gs, body.target_pid)
        if target_owner is None or target_owner == viewer:
            raise HTTPException(422, "pick a rival contracted player")
        out_ids = list(dict.fromkeys(body.out_pids))
        if any(pid not in gs.teams[viewer].player_ids for pid in out_ids):
            raise HTTPException(422, "you can only offer your own players")
        cash_out = max(0, int(body.cash_out))
        cash_in = max(0, int(body.cash_in))
        if cash_out >= cash_in:
            cash_out, cash_in = cash_out - cash_in, 0
        else:
            cash_out, cash_in = 0, cash_in - cash_out
        incoming = market.valuation_opinions(
            gs, viewer, gs.players[body.target_pid]
        )
        outgoing_players = [
            market.valuation_opinions(gs, viewer, gs.players[pid])
            for pid in out_ids
        ]
        sides = {}
        for key in ("coach", "analyst", "consensus"):
            sides[key] = {
                "receive": incoming[key] + cash_in,
                "send": sum(v[key] for v in outgoing_players) + cash_out,
            }
            sides[key]["difference"] = sides[key]["receive"] - sides[key]["send"]
        receive, send = sides["consensus"]["receive"], sides["consensus"]["send"]
        total = max(receive + send, 1)
        balance_pct = round(send / total * 100, 1)
        coach = gs.staff_by.get(viewer, {}).get("coach")
        analyst = gs.staff_by.get(viewer, {}).get("analyst")
        return {
            "target": _trade_asset_view(gs, body.target_pid, viewer),
            "offered_players": [_trade_asset_view(gs, pid, viewer) for pid in out_ids],
            "cash": {"send": cash_out, "receive": cash_in},
            "opinions": sides,
            "balance_pct": balance_pct,
            "verdict": (
                "You are giving up more value" if send > receive * 1.08
                else "You are receiving more value" if receive > send * 1.08
                else "The deal looks balanced"
            ),
            "staff": {
                "coach": coach.name if coach else "Coaching staff",
                "analyst": analyst.name if analyst else "Analytics staff",
            },
        }


# ---------------------------------------------------------------------------
# Stats hub. Column depth is gated by the org's ANALYTICS department (the
# analyst's quality + the analytics-suite facility, see staff.analytics_tier):
# tier 0 reads box scores, tier 1 adds duel detail, tier 2 adds round
# context, tier 3 unlocks the full splits and trend charts. The gate lives
# HERE, server-side — the client renders whatever fields arrive.


def _season_stat_row(gs: GameState, pid: str, st: PlayerSeasonStats, tier: int) -> dict:
    p = gs.players[pid]
    _team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
    row = {
        "player_id": pid,
        "handle": p.handle,
        "team": _team.name if _team else "FA",
        "team_id": _team.id if _team else None,
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


def _player_league_tier(gs: GameState, pid: str) -> int:
    """Which league tier a player's stats belong to: their club's tier.
    Free agents read as tier 1 (they're targets for the top flight)."""
    team = next((t for t in gs.teams.values() if pid in t.player_ids), None)
    return team.tier if team else 1


@app.get("/api/stats")
def stats_view(
    split: str | None = None, key: str | None = None, league_tier: int = 1
) -> dict:
    """League stats. `split=map&key=<map_id>` or `split=agent&key=<agent_id>`
    swaps the player table for that split (analytics tier 3 only).
    `league_tier` (1 default, 2) filters the player tables so the top
    flight and the Challengers circuit read as separate groups."""
    with S.lock:
        gs = S.require_gs()
        analytics = _analytics_view(gs)
        tier = analytics["tier"]
        league_tier = 2 if league_tier == 2 else 1

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
            if _player_league_tier(gs, pid) != league_tier:
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
            # Highlight-stat leaderboards (clutches/multikills/aces/first
            # bloods) from the stored season aggregates. Public, never gated.
            "impact": _impact_leaders(gs, league_tier=league_tier),
            "league_tier": league_tier,
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
            # What's driving that number (single-source breakdown).
            "marketability_breakdown": sponsors.marketability_breakdown(gs),
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
        if ok:
            telemetry.record_action(
                gs, "sponsor_respond",
                {
                    "slot": body.slot,
                    "brand": body.brand or "",
                    "accept": body.accept,
                    "structure": body.structure or "",
                },
            )
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
        level = gs.facilities.get(body.facility, 0)
        cost = economy.facility_upgrade_cost(level)
        ok, message = economy.upgrade_facility(gs, body.facility)
        if not ok:
            raise HTTPException(409, message)
        telemetry.record_action(
            gs, "facility_upgrade",
            {"facility": body.facility, "level": level + 1, "cost": cost},
        )
        S.save()
        return {
            "ok": True,
            "message": message,
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
        telemetry.record_action(gs, "set_training", {"focus": body.focus})
        S.save()
        return {"ok": True, "focus": body.focus}


def _staff_member_view(gs: GameState, m, employer_id: str | None = None) -> dict:
    return {
        **m.model_dump(),
        "specialty_blurb": staff_mod.SPECIALTY_BLURB.get(m.specialty, ""),
        # Concrete contribution lines so hired staff show their impact inline
        # (not just on their profile overlay). Server-computed, never re-derived.
        "effects": _staff_effect_lines(m),
        "employer_id": employer_id,
        "employer_name": gs.teams[employer_id].name if employer_id else None,
    }


@app.get("/api/staff")
def staff_view() -> dict:
    with S.lock:
        gs = S.require_gs()
        if len(gs.staff_pool) < 20 or staff_mod.needs_real_vct_staff(gs):
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
    # Department roles each drive a DIFFERENT recovery axis — mirror the
    # canonical staff.py formulas so the hiring UI doesn't mislabel them.
    if m.role == "psychologist":
        return [
            f"+{m.quality / 60.0:.1f}/wk confidence recovery for shaken players "
            "(pull toward neutral, never a hype boost)"
        ]
    if m.role == "performance_coach":
        return [
            f"+{m.quality / 70.0:.1f}/wk form upkeep for out-of-form players "
            "(pull toward neutral)"
        ]
    if m.role == "language_coach":
        return [
            f"+{staff_mod.language_learning_rate_for_quality(m.quality):.1f} fluency "
            "per weekly language session"
        ]
    # physio (and any future recovery role): stamina.
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
                    "team_id": tid,
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
            # Latest 40 only — a feed should be a scroll, not an archive.
            "feed": llm_social.overlay(
                game.code, [p.model_dump() for p in reversed(gs.social_feed[-40:])]
            ),
            "leaderboard": leaderboard,
            "your_roster": [
                {
                    "player_id": p.id,
                    "handle": p.handle,
                    "followers": p.followers,
                    "stream_load": round(p.stream_load, 1),
                    "stream_status": social.stream_status(p.stream_load),
                    "stream_income": economy.player_stream_income(p),
                }
                for p in sorted(roster, key=lambda p: (-p.followers, p.id))
            ],
            "your_reach": social.roster_reach(gs, gs.acting_team_id),
            # Weekly streaming revenue the whole roster brings the org (its cut).
            "your_stream_income": economy.roster_stream_income(roster),
            "fan_count": gs.teams[gs.acting_team_id].fan_count,
            "sentiment": sent_rows,
            "your_sentiment": gs.sentiment(gs.acting_team_id),
            "your_mood": social.mood_view(gs.sentiment(gs.acting_team_id)),
            "movement": _movement_feed(gs),
        }


# Chronicle kinds that count as market movement, and how the tracker tags
# them. AI-to-AI moves show here too — that's the point (watch the league).
_MOVEMENT_KINDS = ("signing", "release", "renewal", "transfer", "poach")


def _movement_feed(gs: GameState, n: int = 40) -> list[dict]:
    """League-wide signings/releases/renewals/transfers, newest first — a
    pure read of the chronicle (the append-only truth for market moves)."""
    rows = []
    for e in reversed(gs.chronicle):
        if e.kind not in _MOVEMENT_KINDS:
            continue
        team = gs.teams.get(e.team_id)
        rows.append({
            "season": e.season,
            "week": e.week,
            "kind": e.kind,
            "text": e.text,
            "team_id": e.team_id or None,
            "team_tag": team.tag if team else None,
            "player_id": e.player_id or None,
            "mine": e.team_id == gs.acting_team_id,
        })
        if len(rows) >= n:
            break
    return rows


class DevPlanBody(BaseModel):
    player_id: str
    dev_focus: str | None = None
    training_intensity: str | None = None
    learning_language: str | None = None


class AssignmentBody(BaseModel):
    player_id: str
    role: Role
    playstyle: Playstyle


class IglBody(BaseModel):
    player_id: str


@app.post("/api/actions/assignment")
def assignment_action(body: AssignmentBody) -> dict:
    """Change an own player's role/style; comfort must then be rebuilt."""
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        if body.player_id not in team.player_ids:
            raise HTTPException(409, "player is not on your roster")
        p = gs.players[body.player_id]
        if p.role == body.role and p.playstyle == body.playstyle:
            return {"ok": True, "message": f"{p.handle} is already in that assignment"}
        role_fit.change_assignment(p, body.role, body.playstyle)
        telemetry.record_action(gs, "set_assignment", {
            "player_id": p.id, "role": str(p.role), "playstyle": str(p.playstyle),
        })
        S.save()
        return {
            "ok": True,
            "message": f"{p.handle} moved to {p.role}/{p.playstyle}; comfort must build over time.",
            "comfort": round(role_fit.assignment_comfort(p)),
        }


@app.post("/api/actions/igl")
def igl_action(body: IglBody) -> dict:
    """Assign the team's active IGL; shot-calling experience then builds in matches."""
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        if body.player_id not in team.player_ids:
            raise HTTPException(409, "player is not on your roster")
        p = gs.players[body.player_id]
        role_fit.assign_igl(team, p.id)
        experience = role_fit.igl_experience(team, p.id)
        telemetry.record_action(gs, "set_igl", {"player_id": p.id})
        S.save()
        return {
            "ok": True,
            "message": f"{p.handle} is now the IGL; calling experience starts at {experience:.0f}.",
            "experience": round(experience),
            "effectiveness": round(role_fit.igl_effectiveness(p, experience)),
        }


@app.post("/api/actions/dev_plan")
def dev_plan_action(body: DevPlanBody) -> dict:
    """Set a player's individual development plan (own roster only)."""
    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        if body.player_id not in team.player_ids:
            raise HTTPException(409, "player is not on your roster")
        p = gs.players[body.player_id]
        focus = body.dev_focus if body.dev_focus is not None else p.dev_focus
        language = body.learning_language if body.learning_language is not None else p.learning_language
        if body.dev_focus is not None:
            if focus not in DEV_FOCUS_OPTIONS:
                raise HTTPException(
                    422, f"dev_focus must be one of {DEV_FOCUS_OPTIONS}"
                )
        if body.learning_language is not None:
            if language not in LANGUAGE_OPTIONS:
                raise HTTPException(422, f"learning_language must be one of {LANGUAGE_OPTIONS}")
        if focus == "language":
            if "language_coach" not in gs.staff:
                raise HTTPException(409, "hire a language coach before assigning language practice")
            if not language:
                raise HTTPException(422, "choose a language for language practice")
        p.dev_focus = focus
        p.learning_language = language
        if body.training_intensity is not None:
            if body.training_intensity not in INTENSITY_OPTIONS:
                raise HTTPException(
                    422, f"training_intensity must be one of {INTENSITY_OPTIONS}"
                )
            p.training_intensity = body.training_intensity
        telemetry.record_action(
            gs, "set_dev_plan",
            {
                "player_id": body.player_id,
                "dev_focus": p.dev_focus,
                "intensity": p.training_intensity,
                "learning_language": p.learning_language,
            },
        )
        S.save()
        return {
            "ok": True,
            "message": f"{p.handle}: {p.dev_focus}{' (' + p.learning_language + ')' if p.dev_focus == 'language' else ''} focus, "
            f"{p.training_intensity} intensity",
        }


class MentorBody(BaseModel):
    protege_id: str
    mentor_id: str | None = None  # None clears the pairing


@app.post("/api/actions/mentor")
def mentor_action(body: MentorBody) -> dict:
    """Pair a young player with a veteran teammate (own roster), or clear the
    pairing when mentor_id is null. A protege under a mentor develops faster
    (training.MENTOR_GROWTH_MULT) AND, gated by the mentor's hidden mentor_skill,
    slowly gains a higher CEILING on the mentor's best skills
    (development.apply_mentorship_growth)."""
    from esports_sim.manager.campaign import mentorship_valid

    with S.lock:
        gs = S.require_gs()
        team = gs.teams[gs.acting_team_id]
        if body.protege_id not in team.player_ids:
            raise HTTPException(409, "player is not on your roster")
        pro = gs.players[body.protege_id]
        if body.mentor_id is None:
            gs.mentorships.pop(body.protege_id, None)
            telemetry.record_action(
                gs, "mentor", {"protege_id": body.protege_id, "mentor_id": ""}
            )
            S.save()
            return {"ok": True, "message": f"{pro.handle}'s mentorship cleared"}
        if body.mentor_id not in team.player_ids:
            raise HTTPException(409, "the mentor is not on your roster")
        if not mentorship_valid(gs, body.protege_id, body.mentor_id):
            raise HTTPException(
                409, "a mentor must be an older, higher-rated teammate"
            )
        gs.mentorships[body.protege_id] = body.mentor_id
        telemetry.record_action(
            gs, "mentor",
            {"protege_id": body.protege_id, "mentor_id": body.mentor_id},
        )
        S.save()
        men = gs.players[body.mentor_id]
        return {"ok": True, "message": f"{men.handle} now mentors {pro.handle}"}


class HireBody(BaseModel):
    candidate_id: str


@app.post("/api/actions/hire_staff")
def hire_staff(body: HireBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = staff_mod.hire(gs, body.candidate_id)
        if ok:
            telemetry.record_action(
                gs, "hire_staff", {"candidate_id": body.candidate_id}
            )
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
        if ok:
            telemetry.record_action(gs, "release_staff", {"role": body.role})
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
        if ok:
            telemetry.record_action(
                gs, "talk",
                {"player_id": body.player_id, "option_id": body.option_id},
            )
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg, "effects": effects}


class ReinStreamingBody(BaseModel):
    player_id: str


@app.post("/api/actions/rein_streaming")
def rein_streaming(body: ReinStreamingBody) -> dict:
    """Spend the week's 1:1 asking a player to cut back on streaming and
    grind (talk.rein_in_streaming): more practice, less revenue, some morale."""
    with S.lock:
        gs = S.require_gs()
        if body.player_id not in gs.players:
            raise HTTPException(404, "unknown player")
        ok, msg, effects = talk.rein_in_streaming(gs, body.player_id)
        if ok:
            telemetry.record_action(
                gs, "rein_streaming", {"player_id": body.player_id}
            )
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
            {"id": p.id, "handle": p.handle, "playstyle": str(p.playstyle),
             "score": round(pf)}
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
        telemetry.record_action(
            gs, "set_lineup",
            {
                "agents": bool(body.agents is not None),
                "default_five": bool(body.lineup_ids is not None),
                "per_map": bool(body.player_ids is not None),
                "fixture_id": body.fixture_id or "",
                "map_id": body.map_id or "",
            },
        )
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
        # Record the RESULTING book (not just the changed dial): the
        # behavior report reads identity distributions from these.
        telemetry.record_action(
            gs, "set_tactics",
            {
                "aggression": tac.aggression,
                "pace": tac.pace,
                "util_discipline": tac.util_discipline,
                "eco_greed": tac.eco_greed,
                "map_control": tac.map_control,
                "site_focus": tac.site_focus,
            },
        )
        S.save()
        return {"ok": True, "message": "tactics updated", "tactics": tac.model_dump()}


_PLAN_DIAL_FIELDS = (
    "aggression", "pace", "util_discipline", "eco_greed", "map_control",
)


def _gameplan_counter_reads(gs: GameState, fx, plan: GamePlan | None) -> dict:
    """Server-computed counter-strat reads without leaking private identity.

    The map-meta comparison is public. The opponent comparison stays hidden
    until the same 50% scouting threshold that reveals their standing tactics,
    and it deliberately compares against the standing book rather than a
    private one-match override another human manager may have committed.
    """
    tid = gs.acting_team_id
    opp_id = fx.team_b if fx.team_a == tid else fx.team_a
    overrides = {
        dial: getattr(plan, dial) if plan is not None else None
        for dial in _PLAN_DIAL_FIELDS
    }
    know = gs.scout_progress.get(opp_id, 0.0)
    opponent_edge = (
        tactics_fit.counter_strat_edge(overrides, gs.teams[opp_id].tactics)
        if know >= 0.5
        else None
    )

    tactic_sums = {dial: 0.0 for dial in tactics_fit.COUNTER_DIALS}
    team_maps = 0
    for map_id in fx.maps[: fx.best_of]:
        trend = gs.map_meta_stats.get(map_id)
        if trend is None or trend.team_maps <= 0:
            continue
        team_maps += trend.team_maps
        for dial in tactics_fit.COUNTER_DIALS:
            tactic_sums[dial] += trend.tactic_sums.get(dial, 0.0)
    meta_tactics = (
        {dial: tactic_sums[dial] / team_maps for dial in tactics_fit.COUNTER_DIALS}
        if team_maps
        else None
    )
    return {
        "opponent_edge": round(opponent_edge, 2) if opponent_edge is not None else None,
        "meta_edge": (
            round(tactics_fit.counter_strat_edge(overrides, meta_tactics), 2)
            if meta_tactics is not None
            else None
        ),
        "max_edge": C.COUNTER_STRAT_CAP,
        "opponent_revealed": know >= 0.5,
        "meta_team_maps": team_maps,
    }


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
            "counter": _gameplan_counter_reads(gs, fx, plan),
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
    team_talk: str | None = None


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
            telemetry.record_action(gs, "clear_game_plan")
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
        if body.team_talk is not None and body.team_talk not in TEAM_TALK_APPROACHES:
            raise HTTPException(
                422, f"team_talk must be one of {TEAM_TALK_APPROACHES}"
            )
        gs.game_plan = GamePlan(
            fixture_id=fx.id,
            site_focus=body.site_focus,
            focus_target=body.focus_target,
            starter_ids=starters,
            team_talk=body.team_talk,
            **dials,
        )
        telemetry.record_action(
            gs, "set_game_plan",
            {
                "fixture_id": fx.id,
                "opponent": opp_id,
                "n_dials": sum(1 for v in dials.values() if v is not None),
                "site_focus": body.site_focus or "",
                "focus_target": body.focus_target or "",
                "one_match_lineup": bool(starters),
            },
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
        if ok:
            telemetry.record_action(gs, "bid", {"player_id": body.player_id})
        S.save()
        if not ok:
            raise HTTPException(422, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/buyout")
def buyout(body: BidBody) -> dict:
    """Trigger a tier-2 player's buyout clause: pay the fee, they arrive
    this week — no negotiation, the selling org can't refuse."""
    with S.lock:
        gs = S.require_gs()
        if body.player_id not in gs.players:
            raise HTTPException(404, "unknown player")
        ok, msg = market.buy_out_player(gs, gs.acting_team_id, body.player_id)
        if ok:
            telemetry.record_action(gs, "buyout", {"player_id": body.player_id})
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
        if ok:
            telemetry.record_action(
                gs, "respond_offer",
                {
                    "player_id": body.player_id,
                    "accept": body.accept,
                    "to_team": body.to_team or "",
                },
            )
        S.save()
        if not ok:
            raise HTTPException(422, msg)
        return {"ok": True, "message": msg}


class ScoutBody(BaseModel):
    # Exactly one of these picks the assignment type.
    team_id: str | None = None  # rival team id, or "market"
    player_id: str | None = None  # deep-dive one player
    fixture_id: str | None = None  # attend one upcoming match


@app.post("/api/actions/scout")
def scout(body: ScoutBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        picked = [x for x in (body.team_id, body.player_id, body.fixture_id) if x]
        if len(picked) != 1:
            raise HTTPException(422, "pick exactly one scouting target")
        if body.player_id is not None:
            p = gs.players.get(body.player_id)
            if p is None:
                raise HTTPException(404, "unknown player")
            gs.scout_target = f"player:{body.player_id}"
            telemetry.record_action(
                gs, "set_scout", {"target": f"player:{body.player_id}"}
            )
            S.save()
            own = body.player_id in gs.teams[gs.acting_team_id].player_ids
            message = (
                f"scout is mapping {p.handle}'s development path"
                if own else f"scout is building the book on {p.handle}"
            )
            return {"ok": True, "message": message}
        if body.fixture_id is not None:
            fx = next((f for f in gs.fixtures if f.id == body.fixture_id), None)
            if fx is None:
                raise HTTPException(404, "unknown fixture")
            if fx.played:
                raise HTTPException(422, "that match has already been played")
            gs.scout_target = f"match:{body.fixture_id}"
            telemetry.record_action(
                gs, "set_scout", {"target": f"match:{body.fixture_id}"}
            )
            S.save()
            a = gs.teams[fx.team_a].name if fx.team_a in gs.teams else fx.team_a
            b = gs.teams[fx.team_b].name if fx.team_b in gs.teams else fx.team_b
            return {"ok": True, "message": f"scout will attend {a} vs {b}"}
        if body.team_id != "market" and body.team_id not in gs.teams:
            raise HTTPException(404, "unknown team")
        if body.team_id == gs.acting_team_id:
            raise HTTPException(422, "you already know your own team")
        gs.scout_target = body.team_id
        telemetry.record_action(gs, "set_scout", {"target": body.team_id})
        S.save()
        label = (
            "the free-agent market"
            if body.team_id == "market"
            else gs.teams[body.team_id].name
        )
        return {"ok": True, "message": f"scout assigned to {label}"}


@app.get("/api/scouting")
def scouting_view() -> dict:
    """The scout's desk: current assignment (team / market / one player /
    one match), progress, and report cards. A player deep-dive returns ONE
    rich report whose sections unlock with book depth (comfort picks at
    25%, style read at 50%, mental read at 75%, the verdict at ~100 —
    see development.scout_report); team/market return the classic table."""
    with S.lock:
        gs = S.require_gs()
        target = gs.scout_target
        reports: list[dict] = []
        target_kind = "none"
        target_name = None
        progress = 0.0
        if target == "market":
            target_kind = "market"
            target_name = "Free-agent market"
            progress = gs.scout_progress.get("market", 0.0)
            fas = sorted(
                (gs.players[pid] for pid in gs.free_agent_ids),
                key=lambda p: -development.potential_of(p),
            )
            reports = [development.scout_report(gs, p, progress) for p in fas]
        elif target and target.startswith("player:"):
            pid = target[len("player:"):]
            p = gs.players.get(pid)
            if p is not None:
                target_kind = "player"
                target_name = p.handle
                # The deep dive stacks with whatever team coverage exists.
                _fog, progress, _fa = _player_fog(gs, pid)
                own = pid in gs.teams[gs.acting_team_id].player_ids
                reports = [
                    development.scout_report(gs, p, progress, own_player=own)
                ]
        elif target and target.startswith("match:"):
            fid = target[len("match:"):]
            fx = next((f for f in gs.fixtures if f.id == fid), None)
            if fx is not None:
                target_kind = "match"
                a = gs.teams[fx.team_a].name if fx.team_a in gs.teams else fx.team_a
                b = gs.teams[fx.team_b].name if fx.team_b in gs.teams else fx.team_b
                target_name = f"{a} vs {b} (W{fx.week})"
        elif target and target in gs.teams:
            target_kind = "team"
            target_name = gs.teams[target].name
            progress = gs.scout_progress.get(target, 0.0)
            reports = [
                development.scout_report(gs, p, progress)
                for p in gs.roster(target)
            ]
        # Upcoming fixtures the scout could attend (next two weeks of
        # unplayed matches not involving your own club — you're there anyway).
        me = gs.acting_team_id
        upcoming = [
            {
                "id": f.id,
                "week": f.week,
                "stage": f.stage,
                "label": (
                    f"{gs.teams[f.team_a].name if f.team_a in gs.teams else f.team_a}"
                    f" vs "
                    f"{gs.teams[f.team_b].name if f.team_b in gs.teams else f.team_b}"
                ),
            }
            for f in sorted(gs.fixtures, key=lambda x: (x.week, x.id))
            if not f.played and me not in (f.team_a, f.team_b)
            and f.week <= gs.week + 1
        ][:14]
        completed = [
            f for f in gs.fixtures
            if f.played and gs.scout_progress.get(f"match:{f.id}", 0.0) > 0
        ]
        match_report = _match_scout_report(gs, max(
            completed, key=lambda f: (f.week, f.id), default=None
        ))
        # The quick assignment is preparation, not a post-match autopsy: point
        # it at the opponent AFTER the fixture currently being planned.  One
        # advance then lands the first week of coverage before that matchup.
        following = gs.team_fixture(gs.acting_team_id, gs.week + 1)
        planning_opponent = None
        if following is not None:
            opp_id = (
                following.team_b
                if following.team_a == gs.acting_team_id
                else following.team_a
            )
            if opp_id in gs.teams:
                planning_opponent = {
                    "id": opp_id,
                    "name": gs.teams[opp_id].name,
                    "week": following.week,
                    "fixture_id": following.id,
                }
        return {
            "target": target,
            "target_kind": target_kind,
            "target_name": target_name,
            "progress": round(progress, 2),
            "reports": reports,
            "match_report": match_report,
            "teams": [
                {"id": tid, "name": gs.teams[tid].name}
                for tid in sorted(gs.teams)
                if tid != gs.acting_team_id
            ],
            "upcoming": upcoming,
            "planning_opponent": planning_opponent,
            "caps": {
                "survey": SCOUT_SURVEY_CAP,
                "match": SCOUT_MATCH_CAP,
                "deep_dive": SCOUT_DEEP_CAP,
            },
        }


def _match_scout_report(gs: GameState, fixture) -> dict | None:
    """Latest attended-match payoff, derived only from the played fixture."""
    if fixture is None or not fixture.results:
        return None
    a = gs.teams.get(fixture.team_a)
    b = gs.teams.get(fixture.team_b)
    score_a, score_b = fixture.map_score
    lines: dict[str, list[float]] = {}
    for result in fixture.results:
        for line in result.lines:
            lines.setdefault(line.player_id, []).append(line.rating)
    danger_id = max(
        lines,
        key=lambda pid: (sum(lines[pid]) / len(lines[pid]), pid),
        default=None,
    )
    danger = gs.players.get(danger_id) if danger_id else None
    statement = "No clear veto lean from the played maps."
    if fixture.veto:
        statement = fixture.veto[-1]
    else:
        widest = max(
            fixture.results,
            key=lambda r: (abs(r.score_a - r.score_b), r.map_id),
        )
        winner = gs.teams.get(widest.winner_id)
        statement = f"{winner.name if winner else widest.winner_id} looked strongest on {widest.map_id}."
    return {
        "fixture_id": fixture.id,
        "week": fixture.week,
        "team_a_id": fixture.team_a,
        "team_a_name": a.name if a else fixture.team_a,
        "team_b_id": fixture.team_b,
        "team_b_name": b.name if b else fixture.team_b,
        "winner_id": fixture.winner_id,
        "score": f"{score_a}-{score_b}",
        "team_a_tendencies": _match_scout_tendencies(gs, fixture.id, fixture.team_a),
        "team_b_tendencies": _match_scout_tendencies(gs, fixture.id, fixture.team_b),
        "danger_man": (
            {"player_id": danger_id, "handle": danger.handle,
             "rating": round(sum(lines[danger_id]) / len(lines[danger_id]), 2)}
            if danger else None
        ),
        "veto_lean": statement,
    }


def _match_scout_tendencies(gs: GameState, fixture_id: str, team_id: str) -> list[str]:
    """Rebuild the tactic read captured when the attended match resolved."""
    prefix = f"matchobs:{fixture_id}:{team_id}:"
    values = {
        dial: gs.scout_progress.get(prefix + dial)
        for dial in ("aggression", "pace", "eco_greed", "map_control")
    }
    if any(value is None for value in values.values()):
        return []
    site = next(
        (key[len(prefix + "site:"):] for key in sorted(gs.scout_progress)
         if key.startswith(prefix + "site:")),
        "balanced",
    )
    return _team_tendencies(SimpleNamespace(**values, site_focus=site))


class PlayerBody(BaseModel):
    player_id: str


class NegotiationOfferBody(BaseModel):
    player_id: str
    salary: int
    weeks: int
    stream_share: int = 70
    release_fee: int = 0
    buyout: int = 0
    no_transfer: bool = False
    role: str = "bench"


def _negotiation_view(gs: GameState, neg) -> dict:
    p = gs.players[neg.player_id]
    fit = relationships.locker_room_fit(gs, neg.player_id, gs.acting_team_id)
    role_goals = {
        "starter": "Start most matches, compete now, and be paid as a core player.",
        "bench": "A real rotation path, useful minutes, and fair security.",
        "academy": "Development time, a reachable promotion path, and freedom to move.",
    }
    return {
        "player_id": neg.player_id,
        "handle": p.handle,
        "kind": neg.kind,
        "demand_salary": neg.demand_salary,
        "demand_weeks": neg.demand_weeks,
        "demand_stream_share": neg.demand_stream_share,
        "demand_release_fee": neg.demand_release_fee,
        "demand_buyout": neg.demand_buyout,
        "demand_no_transfer": neg.demand_no_transfer,
        "demand_role": neg.demand_role,
        "role_goal": role_goals[neg.demand_role],
        "opening_line": (
            f"I see myself as a {neg.demand_role}. {role_goals[neg.demand_role]} "
            f"I want to keep {neg.demand_stream_share}% of my streaming revenue."
        ),
        "rounds_used": neg.rounds,
        "rounds_left": market.negotiation_round_limit(neg) - neg.rounds,
        "leverage": neg.leverage,
        "interest": neg.interest,
        "competing_clubs": neg.competing_clubs,
        "deadline_week": neg.deadline_week,
        "leverage_reasons": list(neg.leverage_reasons),
        "current_salary": p.salary if neg.kind == "renew" else None,
        "contract_weeks_left": p.contract_weeks_left if neg.kind == "renew" else None,
        "locker_room_fit": {
            "score": fit["average"],
            "duos": len(fit["friends"]),
            "feuds": len(fit["feuds"]),
        },
        "current_terms": ({
            "stream_share": round(p.stream_revenue_share * 100),
            "release_fee": p.release_fee,
            "buyout": p.buyout_clause,
            "no_transfer": p.no_transfer_clause,
            "role": p.roster_role,
        } if neg.kind == "renew" else None),
    }


@app.post("/api/negotiation/open")
def negotiation_open(body: PlayerBody) -> dict:
    """Sit down with a player: their opening demands (or the live table)."""
    with S.lock:
        gs = S.require_gs()
        ok, why, neg = market.open_negotiation(gs, body.player_id)
        if ok:
            telemetry.record_action(
                gs, "negotiate_open", {"player_id": body.player_id}
            )
        S.save()
        if not ok:
            raise HTTPException(422, why)
        return {"ok": True, "negotiation": _negotiation_view(gs, neg)}


@app.post("/api/negotiation/offer")
def negotiation_offer(body: NegotiationOfferBody) -> dict:
    """Put an offer on the table: accepted / countered / collapsed."""
    with S.lock:
        gs = S.require_gs()
        status, msg, neg = market.negotiate_offer(
            gs, body.player_id, body.salary, body.weeks,
            stream_share=body.stream_share,
            release_fee=body.release_fee,
            buyout=body.buyout,
            no_transfer=body.no_transfer,
            role=body.role,
        )
        if status != "error":
            telemetry.record_action(
                gs, "negotiate_offer",
                {
                    "player_id": body.player_id,
                    "salary": body.salary,
                    "weeks": body.weeks,
                    "stream_share": body.stream_share,
                    "release_fee": body.release_fee,
                    "buyout": body.buyout,
                    "no_transfer": body.no_transfer,
                    "role": body.role,
                    "status": status,
                },
            )
        S.save()
        if status == "error":
            raise HTTPException(422, msg)
        return {
            "ok": True,
            "status": status,
            "message": msg,
            "negotiation": _negotiation_view(gs, neg) if neg is not None else None,
        }


@app.post("/api/negotiation/cancel")
def negotiation_cancel(body: PlayerBody) -> dict:
    """Leave the table yourself — no cooldown, reopen any time."""
    with S.lock:
        gs = S.require_gs()
        market.cancel_negotiation(gs, body.player_id)
        telemetry.record_action(
            gs, "negotiate_cancel", {"player_id": body.player_id}
        )
        S.save()
        return {"ok": True, "message": "you leave the table"}


@app.post("/api/actions/sign")
def sign(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.sign_player(gs, gs.acting_team_id, body.player_id)
        if ok:
            telemetry.record_action(gs, "sign", {"player_id": body.player_id})
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/release")
def release(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.release_player(gs, gs.acting_team_id, body.player_id)
        if ok:
            telemetry.record_action(gs, "release", {"player_id": body.player_id})
        S.save()
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True, "message": msg}


@app.post("/api/actions/renew")
def renew(body: PlayerBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        ok, msg = market.renew_contract(gs, gs.acting_team_id, body.player_id)
        if ok:
            telemetry.record_action(gs, "renew", {"player_id": body.player_id})
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
        if ok:
            telemetry.record_action(
                gs, "swap", {"sign_id": body.sign_id, "drop_id": body.drop_id}
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
        if ok:
            telemetry.record_action(
                gs, "propose_package",
                {
                    "target_pid": body.target_pid,
                    "n_out": len(body.out_pids),
                    "cash_out": max(0, int(body.cash_out)),
                    "cash_in": max(0, int(body.cash_in)),
                },
            )
        S.save()
        if not ok:
            raise HTTPException(422, msg)
        return {"ok": True, "message": msg}


class FlavorEventChoiceBody(BaseModel):
    event_id: str
    choice_id: str


@app.post("/api/actions/flavor_event")
def resolve_flavor_event(body: FlavorEventChoiceBody) -> dict:
    """Resolve the acting manager's one pending flavor choice."""
    with S.lock:
        gs = S.require_gs()
        event = flavor_events.pending_for(gs)
        if event is None or event.id != body.event_id:
            raise HTTPException(409, "That flavor event is no longer waiting.")
        ok, message, _effects = flavor_events.resolve(
            gs, gs.acting_team_id, body.choice_id
        )
        if not ok:
            raise HTTPException(422, message)
        telemetry.record_action(
            gs,
            "flavor_choice",
            {"event_id": body.event_id, "choice_id": body.choice_id},
        )
        S.save()
        return {"ok": True, "message": message}


class MediaEventChoiceBody(BaseModel):
    event_id: str
    choice_id: str


@app.post("/api/actions/media_event")
def resolve_media_event(body: MediaEventChoiceBody) -> dict:
    with S.lock:
        gs = S.require_gs()
        event = media_events.pending_for(gs)
        if event is None or event.id != body.event_id:
            raise HTTPException(409, "That media decision is no longer waiting.")
        ok, message, effects = media_events.resolve(
            gs, gs.acting_team_id, body.choice_id
        )
        if not ok:
            raise HTTPException(422, message)
        telemetry.record_action(
            gs,
            "media_choice",
            {"event_id": body.event_id, "choice_id": body.choice_id},
        )
        S.save()
        return {"ok": True, "message": message, "effects": effects}


@app.post("/api/actions/advance")
def advance() -> dict:
    """Ready-up: mark the acting manager ready to advance. The week only ticks
    once EVERY human in the world is ready (a solo game advances immediately).
    Returns either the resolved week's report, or a 'waiting' status listing who
    the world is still waiting on."""
    with S.lock:
        gs = S.require_gs()
        me = gs.acting_team_id
        pending = flavor_events.pending_for(gs, me)
        if pending is not None:
            raise HTTPException(
                409,
                "resolve the pending flavor event in Action required before advancing",
            )
        pending_media = media_events.pending_for(gs, me)
        if pending_media is not None:
            raise HTTPException(
                409,
                "resolve the pending media decision in Action required before advancing",
            )
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
        # Everyone's in — advance the shared world exactly once. Each
        # seat's ready-up is its own recorded decision (the advance is
        # the RL episode's step boundary).
        for t in sorted(game.ready):
            telemetry.record_action(gs, "advance", team_id=t)
        game.event_logs.clear()  # replays are for the freshly played week
        report = advance_week(gs, S.gd, events_out=game.event_logs)
        game.last_report = report
        game.ready.clear()
        # Append this week's fresh match reviews to the durable on-disk corpus
        # (serving-layer side effect, off the deterministic tick — see
        # web/review_history.py). Never fatal: the corpus is analysis-only.
        try:
            review_history.append_reviews(gs, game.code, game.review_seen)
        except Exception:
            pass
        # Hand the week's fresh posts to the LLM ghost-writer (async,
        # serving-layer only — see web/llm_social.py; no-op without a
        # configured provider).
        llm_social.enqueue(game)
        # Re-bind acting (advance_week churns the acting pointer internally).
        gs.set_acting(me)
        # Persistence follows the world's autosave policy (every Nth tick,
        # or never — the explicit Save button always works).
        game.autosave_tick()
        return _report_view(report, gs, me)


def _report_view(report, gs: GameState, me: str) -> dict:
    """The week-report payload — shared by the advance response and
    /api/report so a waiting shared-world manager sees the same report
    (incl. replay buttons) as the manager whose ready-up ticked the week."""
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


@app.get("/api/report")
def last_week_report() -> dict:
    """The most recently played week's report, for managers who were waiting
    on others when the world ticked (their own advance call returned
    'waiting'). In-memory only: after a server restart there's no report
    until a week is played, and clients treat {report: null} as 'nothing to
    show'."""
    with S.lock:
        gs = S.require_gs()
        report = S.last_report
        if report is None:
            return {"report": None}
        return {"report": _report_view(report, gs, gs.acting_team_id)}


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
    use the market survey as their broad information source. A player-targeted
    deep dive ("player:<pid>" progress) cuts through either broad source toward
    that player's residual uncertainty floor — never all the way to own-roster
    knowledge."""
    deep = gs.scout_progress.get(f"player:{pid}", 0.0)
    is_fa = pid in gs.free_agent_ids
    if is_fa:
        progress = market.scouting_progress_for(
            gs, gs.acting_team_id, gs.players[pid]
        )
        fog = FOG_BASE_SIGMA * market.scout_uncertainty_factor(
            gs, gs.acting_team_id, gs.players[pid]
        )
        return fog, progress, True
    team_id = market.team_of(gs, pid)
    if team_id is None:
        return 0.0, 1.0, False  # unrostered non-FA (e.g. mid-transfer): treat as known
    if team_id == gs.acting_team_id:
        # Own attributes are known, but the deep-dive book is a separate read
        # used for development guidance and its weekly practice bonus.
        return 0.0, deep, False
    progress = market.scouting_progress_for(
        gs, gs.acting_team_id, gs.players[pid]
    )
    fog = FOG_BASE_SIGMA * market.scout_uncertainty_factor(
        gs, gs.acting_team_id, gs.players[pid]
    )
    return fog, progress, False


def _player_scouting_context(
    gs: GameState, p: Player, own: bool, info_progress: float
) -> dict:
    """Assignment depth plus the own-player weekly development payoff."""
    key = f"player:{p.id}"
    progress = gs.scout_progress.get(key, 0.0)
    active = gs.scout_target == key
    guidance = None
    if own and progress >= training.SCOUT_GUIDANCE_UNLOCK:
        guidance = training.scouting_guidance(p)
        selected = (
            p.dev_focus
            if p.dev_focus in training.DEV_FOCUS_OPTIONS and p.dev_focus != "auto"
            else gs.training_focus.get(gs.acting_team_id, "tactical")
        )
        guidance = {
            **guidance,
            "selected_focus": selected,
            "bonus_mult": training.SCOUT_GUIDANCE_MULT,
            "bonus_active": active and selected == guidance["focus"],
        }
    return {
        "progress": round(progress if own else info_progress, 2),
        "active": active,
        "guidance": guidance,
        "guidance_unlock": training.SCOUT_GUIDANCE_UNLOCK,
        "bonus_mult": training.SCOUT_GUIDANCE_MULT,
        "report": (
            development.scout_report(gs, p, info_progress)
            if not own and info_progress > 0
            else None
        ),
    }


def _profile_overview(gs: GameState, p: Player, fog: float, progress: float) -> dict:
    fogged = fog > 0.0
    team_id = market.team_of(gs, p.id)
    team = gs.teams.get(team_id) if team_id else None
    is_igl = bool(team and team.captain_id == p.id)
    ovr = None if fogged else int(round(development.overall(p)))
    # The overall/peak forecast is the source of truth in the profile; the
    # star rating rides along only as a coarse quick-glance. A fogged rival
    # can't be read exactly, so their ceiling stays the scout's banded tier
    # text and the star sub is withheld.
    potential_band: list[int] | None = None
    skill_ceilings: dict[str, list[float]] | None = None
    if fogged:
        potential: int | str = _potential_text(gs, p, fogged, progress)
        pot_stars = None
    else:
        # Own club: peak ability remains a projection, not a measurement. Show
        # an outcome band and per-skill bands rather than hidden exact values.
        lo, hi = (
            _roster_potential_projection(gs, p)
            if market.team_of(gs, p.id) == gs.acting_team_id
            else development.potential_projection(p, own=True)
        )
        est = (lo + hi) / 2.0
        potential = int(round(est))
        pot_stars = development.stars(est)
        potential_band = [round(lo), round(hi)]
        skill_ceilings = {
            a: list(development.skill_potential_projection(p, a))
            for a in sorted(p.attributes)
        }
    return {
        "ovr": ovr,
        "ovr_stars": None if fogged else development.stars(development.overall(p)),
        # Role/style current ability is intentionally a range for everyone,
        # including your own roster. It is a hidden execution estimate rather
        # than the visible arithmetic overall.
        "current_ability_band": list(
            development.current_ability_projection(p, 1.0 if not fogged else progress)
        ),
        "comfort": None if fogged else round(role_fit.assignment_comfort(p)),
        "igl_experience": (
            round(role_fit.igl_experience(team, p.id)) if (not fogged and is_igl) else None
        ),
        "igl_effectiveness": (
            round(role_fit.igl_effectiveness(p, role_fit.igl_experience(team, p.id)))
            if (not fogged and is_igl) else None
        ),
        "potential": potential,
        "potential_stars": pot_stars,
        "potential_band": potential_band,
        "skill_ceilings": skill_ceilings,
        "form": None if fogged else round(p.form, 1),
        "morale": None if fogged else round(p.morale, 1),
        "condition": None if fogged else round(p.stamina, 1),
        # Value / salary / contract are public (rival transfer asks already
        # leak on the roster page), so they show regardless of fog.
        "market_value": market.transfer_value(p),
        "salary": p.salary,
        "contract_weeks": p.contract_weeks_left,
        "contract_terms": {
            "stream_share": round(p.stream_revenue_share * 100),
            "release_fee": p.release_fee,
            "buyout": p.buyout_clause,
            "no_transfer": p.no_transfer_clause,
            "roster_role": p.roster_role,
        },
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
                "role": str(agent.role) if agent else None,
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
                # Weeks at the current club (the loyalty clock; 0 for a free
                # agent). Season length varies with world shape, so there is
                # no honest weeks-per-season divisor — the raw weeks ship and
                # the UI renders them as-is.
                "tenure_weeks": p.tenure_weeks,
                # A rival's contracted player is biddable: the seller's ask, so
                # the profile overlay can open the package builder.
                "transfer_ask": (
                    market.transfer_ask(gs, pid)
                    if (not is_fa and team_id and team_id != gs.acting_team_id)
                    else None
                ),
                "seller_stance": (
                    market.org_player_valuation(gs, team_id, pid, "sell")["stance"]
                    if (not is_fa and team_id and team_id != gs.acting_team_id)
                    else None
                ),
                "ask_breakdown": (
                    market.transfer_ask_breakdown(gs, pid)
                    if (not is_fa and team_id and team_id != gs.acting_team_id)
                    else []
                ),
                "followers": p.followers,
                # Streaming: how much they stream, the org's weekly cut, the
                # growth cost, and whether the manager can rein it in this week
                # (own players only — the "rein it in" 1:1).
                "stream_load": round(p.stream_load, 1),
                "stream_status": social.stream_status(p.stream_load),
                "stream_income": economy.player_stream_income(p),
                "stream_growth_mult": round(training.stream_practice_mult(p), 2),
                "can_rein_streaming": (
                    talk.can_rein_streaming(gs, pid)[0] if own else False
                ),
                "can_change_assignment": own,
                "can_assign_igl": own,
                "is_igl": bool(team and team.captain_id == p.id),
                "confidence": None if fog > 0 else round(p.confidence, 1),
                "is_starter": (
                    pid in default_five(gs, team_id) if team_id else None
                ),
                "dev_focus": p.dev_focus if own else None,
                "training_intensity": p.training_intensity if own else None,
                # Identity: nationality + spoken tongues (public info —
                # shared languages drive the locker room's comms cohesion).
                "country": p.country or None,
                "languages": [
                    {"lang": l.lang, "level": round(l.level)} for l in p.languages
                ],
            },
            "overview": _profile_overview(gs, p, fog, progress),
            "traits": _profile_traits(p, fog, progress),
            "badges": _badge_views(p),
            "attributes": _profile_attributes(gs, p, fog),
            "agents": _profile_agents(p),
            "season": _profile_season(gs, pid),
            "weekly": _profile_weekly(gs, pid),
            "splits": _profile_splits(gs, pid),
            "charts": _profile_charts(gs, pid, own),
            "relationships": _profile_relationships(gs, pid),
            "scouting": _player_scouting_context(gs, p, own, progress),
            # No per-season career archive is persisted (player_stats reset
            # each offseason), so only the current season exists -> [].
            "career": [],
            # Lifetime totals (completed seasons + the current one in
            # progress): maps, kills, K/D, honours. None until they've
            # played a map. Reads gs.career_stats + the live season.
            "career_totals": _profile_career_totals(gs, pid),
            # The player's career as a per-season chronicle timeline (debut,
            # awards, milestones, moves), newest season first.
            "career_arc": analytics.career_arc(gs, pid),
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
        "all_stars": sum(1 for e in entries if e.kind == "all_star"),
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


_STRENGTH_AXES = ("mechanical", "tactical", "mental", "team")
_STRENGTH_LABEL = {
    "mechanical": "Aim & mechanics", "tactical": "Tactical IQ",
    "mental": "Mentals", "team": "Teamplay",
}


def _team_strength(gs: GameState, tid: str, fogged: bool = False) -> list[dict]:
    """A squad-strength profile: the dressed five's mean attribute per category
    (aim / tactical / mentals / teamplay). Own club shows exact means; a
    scouted rival shows only the band."""
    reg = S.gd.attributes.definitions
    by_axis: dict[str, list[str]] = {ax: [] for ax in _STRENGTH_AXES}
    for key, d in reg.items():
        if d.category in by_axis:
            by_axis[d.category].append(key)
    five = default_five(gs, tid)
    out = []
    for ax in _STRENGTH_AXES:
        vals = [
            p.attr(k, 50.0)
            for pid in five
            if (p := gs.players.get(pid)) is not None
            for k in by_axis[ax]
        ]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        out.append({
            "axis": ax, "label": _STRENGTH_LABEL[ax],
            "value": None if fogged else round(mean, 1),
            "band": _attr_band(mean),
        })
    return out


COMFORT_MASTERY = 60.0  # a pool entry only counts as "covers it" from here up


def _agent_pool_coverage(gs: GameState, tid: str) -> dict:
    """The roster's collective agent coverage (how many players run each agent
    comfortably and the best mastery), plus the meta staples they don't cover.
    Every player now carries a baseline on the whole cast, so coverage counts
    COMFORT picks (mastery >= COMFORT_MASTERY), not mere pool membership.
    Own-club roster intel; pure read."""
    cov: dict[str, dict] = {}
    for pid in gs.teams[tid].player_ids:
        p = gs.players.get(pid)
        if p is None:
            continue
        for m in p.agent_pool:
            if m.mastery < COMFORT_MASTERY:
                continue
            c = cov.setdefault(m.agent_id, {"count": 0, "best": 0.0})
            c["count"] += 1
            c["best"] = max(c["best"], m.mastery)
    usage = meta_mod._agent_usage(gs)
    top_meta = sorted(usage, key=lambda a: (-usage[a], a))[:8]
    covered = [
        {
            "agent_id": aid,
            "name": S.gd.agents[aid].display_name if aid in S.gd.agents else aid,
            "players": c["count"], "mastery": round(c["best"]),
        }
        for aid, c in sorted(cov.items(), key=lambda kv: (-kv[1]["best"], kv[0]))
    ][:10]
    gaps = [
        {"agent_id": a, "name": S.gd.agents[a].display_name if a in S.gd.agents else a}
        for a in top_meta if a not in cov
    ]
    return {"covered": covered, "meta_gaps": gaps}


def _suggested_lineup(gs: GameState, tid: str) -> dict | None:
    """A read-only 'best available five' by quality + current form/confidence,
    with a flag where it diverges from the dressed five. None when the roster
    is five or fewer (everyone plays — nothing to pick)."""
    roster = list(gs.teams[tid].player_ids)
    if len(roster) <= market.ROSTER_SIZE:
        return None
    current = set(default_five(gs, tid))
    scored = []
    for pid in roster:
        p = gs.players.get(pid)
        if p is None:
            continue
        q = market.player_quality(p)
        score = q + (p.form - 50.0) * 0.05 + (p.confidence - 50.0) * 0.05
        scored.append((score, pid, p.handle, round(q)))
    scored.sort(key=lambda s: (-s[0], s[1]))
    picks = scored[:market.ROSTER_SIZE]
    suggested_ids = {pid for _, pid, _, _ in picks}
    return {
        "players": [
            {"id": pid, "handle": handle, "quality": q, "dressed": pid in current}
            for _, pid, handle, q in picks
        ],
        "changed": suggested_ids != current,
    }


def _board_standing(gs: GameState) -> dict | None:
    """Legacy-mode job security: the board goal, patience band, seasons left on
    the deal, and how the goal is tracking. None in sandbox / when unemployed."""
    seat = gs.seat_for_session(gs.acting_team_id)
    if seat is None or seat.contract is None or not seat.team_id:
        return None
    c = seat.contract
    pat = c.patience
    band = (
        "secure" if pat >= 66 else "stable" if pat >= 45
        else "under pressure" if pat >= 25
        else "hot seat" if pat >= career.MIDSEASON_FLOOR else "on the brink"
    )
    status = career.objective_status(gs, seat.team_id, c.goal)
    return {
        "goal": career.GOAL_LABELS.get(c.goal, c.goal),
        "patience": round(pat, 1),
        "band": band,
        "seasons_left": max(0, c.start_season + c.seasons - 1 - gs.season),
        "goal_state": status.get("state"),
        "goal_detail": status.get("detail"),
    }


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
            # Squad chemistry (bonds, frictions, cohesion) — own club only.
            "chemistry": _squad_chemistry(gs, tid) if own_team else None,
            # Development headroom: each own player's CA vs ceiling and which
            # way they're trending. Private dev-history read → own club only.
            "dev_progress": _dev_progress(gs, tid) if own_team else None,
            # Squad strength radar (aim/tactical/mentals/teamplay): own club
            # exact, a well-scouted rival banded, hidden until then.
            "strength": (
                _team_strength(gs, tid, fogged=not own_team)
                if (own_team or gs.scout_progress.get(tid, 0.0) >= 0.5)
                else None
            ),
            # Collective agent coverage + meta gaps — own-club roster intel.
            "agent_pool": _agent_pool_coverage(gs, tid) if own_team else None,
        }


# ---------------------------------------------------------------------------
# Admin data-correction toggle. The client's toggle is purely a UI reveal, so
# these routes enforce a loopback peer at the server boundary. They only ever
# touch REAL players/teams that trace back to a
# roster pack's src/ sheet (see registry/roster_admin.py); generated fill
# entities 404 as not-editable. Persists to disk (the pack sheet, rebuilt)
# AND patches the live save's identity/skill fields — never the
# campaign-managed ones (salary, contract, morale, stamina, form,
# confidence, balance, reputation, fan_count, ...), so a correction can't
# reset progress already made in the running campaign.


def _sync_player_identity(p: Player, fresh: dict) -> None:
    p.handle = fresh["handle"]
    p.real_name = fresh["real_name"]
    p.country = fresh["country"]
    p.languages = [LanguageSkill(**entry) for entry in fresh["languages"]]
    p.age = fresh["age"]
    p.role = Role(fresh["role"])
    p.playstyle = Playstyle(fresh["playstyle"])
    p.attributes = dict(fresh["attributes"])
    p.agent_pool = [AgentMastery(**a) for a in fresh["agent_pool"]]
    p.map_pool = [MapMastery(**m) for m in fresh["map_pool"]]
    p.potential = fresh["potential"]
    p.personality_tags = list(fresh["personality_tags"])


class PlayerAdminEditBody(BaseModel):
    handle: str | None = None
    real_name: str | None = None
    age: int | None = None
    country: str | None = None
    languages: list[dict] | None = None
    role: str | None = None
    playstyle: str | None = None
    quality: float | None = None
    agents: list[str] | None = None


class TeamAdminEditBody(BaseModel):
    name: str | None = None
    tag: str | None = None
    tier: int | None = None
    prestige: float | None = None


@app.get("/api/admin/player/{pid}")
def admin_player_editable(pid: str) -> dict:
    _require_local_admin()
    with S.lock:
        gs = S.require_gs()
        p = gs.players.get(pid)
        if p is None:
            raise HTTPException(404, "unknown player")
        pack_id = gs.roster_pack
        if not pack_id:
            return {
                "editable": False,
                "reason": "this campaign wasn't seeded from a roster pack",
            }
        loc = roster_admin.find_player(pack_id, pid)
        if loc is None:
            return {
                "editable": False,
                "reason": "generated player — no roster-pack sheet to correct",
            }
        spec = loc.player_spec
        return {
            "editable": True,
            "pack_id": pack_id,
            "fields": {
                "handle": spec.get("handle", p.handle),
                "real_name": spec.get("real_name", p.real_name),
                "age": spec.get("age", p.age),
                "country": spec.get("country", p.country),
                "languages": spec.get("languages", []),
                "role": spec.get("role", str(p.role)),
                "playstyle": spec.get("playstyle", str(p.playstyle)),
                "quality": spec.get("quality"),
                "agents": spec.get("agents", []),
            },
        }


@app.post("/api/admin/player/{pid}")
def admin_edit_player(pid: str, body: PlayerAdminEditBody) -> dict:
    _require_local_admin()
    with S.lock:
        gs = S.require_gs()
        p = gs.players.get(pid)
        if p is None:
            raise HTTPException(404, "unknown player")
        pack_id = gs.roster_pack
        if not pack_id:
            raise HTTPException(
                409, "this campaign wasn't seeded from a roster pack"
            )
        edits = {k: v for k, v in body.model_dump().items() if v is not None}
        if not edits:
            raise HTTPException(422, "no edits supplied")
        try:
            fresh = roster_admin.edit_player(S.gd, pack_id, pid, edits)
        except roster_admin.RosterEditError as e:
            raise HTTPException(422, str(e)) from None
        _sync_player_identity(p, fresh)
        S.save()
        return {"ok": True, "message": f"{p.handle}'s sheet corrected", "player": {
            "id": p.id, "handle": p.handle, "real_name": p.real_name,
            "age": p.age, "country": p.country, "role": str(p.role),
            "playstyle": str(p.playstyle),
        }}


@app.get("/api/admin/team/{tid}")
def admin_team_editable(tid: str) -> dict:
    _require_local_admin()
    with S.lock:
        gs = S.require_gs()
        t = gs.teams.get(tid)
        if t is None:
            raise HTTPException(404, "unknown team")
        pack_id = gs.roster_pack
        if not pack_id:
            return {
                "editable": False,
                "reason": "this campaign wasn't seeded from a roster pack",
            }
        loc = roster_admin.find_team(pack_id, tid)
        if loc is None:
            return {
                "editable": False,
                "reason": "generated team — no roster-pack sheet to correct",
            }
        spec = loc.team_spec
        return {
            "editable": True,
            "pack_id": pack_id,
            "fields": {
                "name": spec.get("name", t.name),
                "tag": spec.get("tag", t.tag),
                "tier": spec.get("tier", t.tier),
                "prestige": spec.get("prestige"),
            },
            "note": (
                "Renaming only affects future new campaigns started from "
                "this pack; this world's team keeps its current id. "
                "Prestige only affects future new campaigns (this world's "
                "balance/reputation/fan count already evolved through play "
                "and are left untouched)."
            ),
        }


@app.post("/api/admin/team/{tid}")
def admin_edit_team(tid: str, body: TeamAdminEditBody) -> dict:
    _require_local_admin()
    with S.lock:
        gs = S.require_gs()
        t = gs.teams.get(tid)
        if t is None:
            raise HTTPException(404, "unknown team")
        pack_id = gs.roster_pack
        if not pack_id:
            raise HTTPException(
                409, "this campaign wasn't seeded from a roster pack"
            )
        edits = {k: v for k, v in body.model_dump().items() if v is not None}
        if not edits:
            raise HTTPException(422, "no edits supplied")
        try:
            roster_admin.edit_team(pack_id, tid, edits)
        except roster_admin.RosterEditError as e:
            raise HTTPException(422, str(e)) from None
        if "name" in edits:
            t.name = str(edits["name"])
        if "tag" in edits:
            t.tag = str(edits["tag"]).upper()
        S.save()
        return {"ok": True, "message": f"{t.name}'s sheet corrected", "team": {
            "id": t.id, "name": t.name, "tag": t.tag, "tier": t.tier,
        }}


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


@app.get("/api/perf")
def perf_view() -> dict:
    """This process's performance sink (see esports_sim.perf): tick-phase
    timings paired with state-size gauges (the slowdown-over-weeks view),
    save cost, and per-endpoint latency aggregates. In-memory only —
    resets on restart; never part of the save."""
    return perf.snapshot()


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
        dumped = [e.model_dump() for e in events]
        team_of = {pid: p["team_id"] for pid, p in players.items()}
        momentum = momentum_mod.momentum_trace(events, team_of)
        # Post-match box score (top performers + MVP) from the stored map
        # lines — the viewer's match-summary panel. Pure read.
        box = sorted(
            (
                {
                    "player_id": ln.player_id,
                    "handle": (
                        gs.players[ln.player_id].handle
                        if ln.player_id in gs.players else ln.player_id
                    ),
                    "team_id": players.get(ln.player_id, {}).get("team_id"),
                    "kills": ln.kills, "deaths": ln.deaths,
                    "rating": round(ln.rating, 2),
                }
                for ln in fixture.results[map_index].lines
            ),
            key=lambda r: (-r["rating"], r["player_id"]),
        )
        return {
            "fixture": _fixture_view(fixture, gs),
            "map": map_geometry(map_id),
            "team_a": fixture.team_a,
            "team_b": fixture.team_b,
            "players": players,
            "abilities": abilities,
            "events": dumped,
            # Per-round result strip for the viewer timeline (winner, running
            # score, whether the spike went down). Derived from the log.
            "round_summaries": _round_summaries(dumped, fixture.team_a),
            "momentum": [
                {"round_num": row.round_num, "values": row.values}
                for row in momentum
            ],
            "box_score": box,
            "mvp": box[0] if box else None,
        }


def _round_summaries(events: list[dict], team_a: str) -> list[dict]:
    """A compact per-round result list from a map's event log: round number,
    the attacking side, whether the spike was planted, the winner, and the
    running score. Pure read of the log — the viewer renders it as a
    round-by-round timeline strip."""
    out: list[dict] = []
    cur: dict | None = None
    sa = sb = 0
    for d in events:
        t = d.get("type")
        if t == "round.start":
            cur = {
                "num": d.get("round_num"),
                "attacker": d.get("attacking_team_id"),
                "plant": False, "winner_id": None,
            }
        elif t == "round.spike_plant" and cur is not None:
            cur["plant"] = True
        elif t == "round.end" and cur is not None:
            w = d.get("winner_id")
            cur["winner_id"] = w
            if w == team_a:
                sa += 1
            else:
                sb += 1
            cur["score_a"], cur["score_b"] = sa, sb
            out.append(cur)
            cur = None
    return out


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
        client = scope.get("client")
        client_host_token = _client_host_ctx.set(client[0] if client else "")
        try:
            if path.startswith("/api/"):
                # Per-endpoint latency: bucket by the first two path
                # segments so dynamic ids collapse into one series
                # ("/api/roster/team_x" -> "api./api/roster").
                route = "/".join(path.split("/", 3)[:3])
                with perf.span(f"api.{route}"):
                    await self.app(scope, receive, send_wrapper)
            else:
                await self.app(scope, receive, send_wrapper)
        finally:
            _ctx.reset(ctx_token)
            _sid_ctx.reset(sid_token)
            _client_host_ctx.reset(client_host_token)


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
