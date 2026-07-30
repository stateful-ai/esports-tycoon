"""Operations behind the play MCP — the whole campaign as an agent-playable API.

The manager-facing game already has a headless contract: ``decision_env``
publishes one manager's observation plus explicit legal-action masks, and
applies actions through the same manager-domain functions the web layer calls.
This module adds what a *playing* agent needs on top of that contract and
nothing more:

* **worlds** — create / load / list / save campaigns on the same
  ``saves/campaign_<digest>.json`` convention the web lobby uses, so a world
  started over MCP can be resumed in the browser and vice versa;
* **compact reads** — the raw observation is thousands of tokens; an agent
  playing turn by turn wants a dashboard, then the one section it cares about;
* **the week digest** — ``advance`` in the raw env returns only "week
  advanced". Here it returns what actually happened: results, standings
  movement, cash swing, and the inbox the tick generated;
* **the read screens the observation omits** — standings, schedule, results,
  season report, profiles, chronicle, finances, records;
* **the market actions that live in the web layer** — cash bids, buyouts,
  package proposals, and answering bids for your own players.

Everything mutating routes through ``HeadlessManagerEnv`` where the action
contract already covers it, so telemetry, reward, and the legality guards stay
identical to every other headless caller. Campaign determinism is unchanged:
same seed plus same action sequence still gives a byte-identical ``GameState``.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from esports_sim.manager import (
    analytics,
    career,
    chronicle,
    development,
    economy,
    facilities,
    flavor_events,
    inbox as inbox_mod,
    market,
    match_review,
    media_events,
    scouting,
    sponsors,
    staff_effects,
)
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import (
    HeadlessManagerEnv,
    InvalidManagerAction,
    manager_observation,
)
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData, load_all
from esports_sim.registry.rosters import list_roster_packs, load_roster_pack
from esports_sim.schemas.common import Role

SAVE_DIR = Path("saves")
# Exactly five characters, because the browser lobby's join field is a strict
# five-character match: a world this module creates under any other length
# exists on disk but can never be opened in the browser, which is the whole
# point of sharing the save convention.
CODE_LENGTH = 5
CODE_RE = re.compile(rf"^[A-Z0-9]{{{CODE_LENGTH}}}$")
# Unambiguous alphabet (no O/0, I/1), matching the web lobby's join codes.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
POLICY_VERSION = "play-mcp-v1"
# Roles a fill_gap sweep can name. scouting._build_shortlist compares these
# exactly against Player.role, so the vocabulary has to be published and
# enforced rather than passed through.
SCOUT_ROLES = frozenset(str(role) for role in Role)

# Observation sections an agent can ask for by name. "legal_actions" is served
# by get_legal_actions (enabled-only by default) because the full contract
# enumerates every signable free agent and every scouting target.
OBSERVATION_SECTIONS = (
    "features",
    "tactics",
    "training_focus",
    "lineup_ids",
    "club",
    "staff",
    "staff_candidates",
    "facilities",
    "sponsor_market",
    "negotiations",
    "game_plan",
    "career_offers",
    "roster",
    "free_agents",
    "upcoming_fixture",
    "opponent",
    "scout_target",
    "map_ids",
    "legal_actions",
)


class PlayError(RuntimeError):
    """A play request that is malformed or impossible in the current world."""


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@dataclass
class _Session:
    """One live campaign world plus the env bound to the managed seat."""

    code: str
    gs: GameState
    env: HeadlessManagerEnv
    path: Path
    # The seat id of the manager being played. Seat ids follow the PERSON
    # across dismissals and new posts, so this — not the club — is the durable
    # identity to re-find after another process moves the career.
    manager_id: str = ""
    # (mtime_ns, size) of the save as this process last left it. A world is
    # now browser-joinable, so another process can write it between our calls.
    stamp: tuple[int, int] | None = None


_SESSIONS: dict[str, _Session] = {}
_GAMEDATA: GameData | None = None


def _gamedata() -> GameData:
    """The immutable YAML registries, loaded once per server process."""
    global _GAMEDATA
    if _GAMEDATA is None:
        _GAMEDATA = load_all()
    return _GAMEDATA


def save_path_for(code: str) -> Path:
    """The web lobby's save convention, so both front ends see one world."""
    digest = hashlib.blake2b(code.encode(), digest_size=8).hexdigest()
    return SAVE_DIR / f"campaign_{digest}.json"


def _normalize_code(code: str) -> str:
    code = str(code or "").strip().upper()
    if not CODE_RE.match(code):
        raise PlayError(
            f"invalid world code {code!r} — use exactly {CODE_LENGTH} "
            "characters, A-Z and 0-9, so the world also opens in the browser"
        )
    return code


def _new_code(seed: int) -> str:
    """Derive a free world code from stable inputs.

    blake2 of (seed, attempt) rather than an RNG stream: the repo's rule is
    that anything stochastic comes from ``RngTree`` or a blake2 of stable ids,
    and a labelled hash is also the honest shape here — the attempt index, not
    a draw count, is what varies when a code is already taken.
    """
    for attempt in range(200):
        digest = hashlib.blake2b(
            f"play-mcp-world:{seed}:{attempt}".encode(), digest_size=CODE_LENGTH
        ).digest()
        code = "".join(CODE_ALPHABET[b % len(CODE_ALPHABET)] for b in digest)
        if code not in _SESSIONS and not save_path_for(code).exists():
            return code
    raise PlayError("could not allocate a world code — pass one explicitly")


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _follow_manager(gs: GameState, previous: str, manager_id: str = "") -> str:
    """The club this env should be bound to after reloading from disk.

    Follow the MANAGER's seat id, which is the only stable handle: it follows
    the person across a dismissal and a new post. Resolving by club instead
    strands the session — either at a former employer, or (once someone else
    occupies that club) inside a stranger's org, where the ownership mask then
    makes the real career unresumable from here.
    """
    seat = gs.managers.get(manager_id) if manager_id else None
    if seat is not None:
        # Employed somewhere: go there. Between jobs: stay on the club we were
        # last bound to, so accept_job still has a seat to act on.
        if seat.team_id in gs.teams:
            return seat.team_id
        return previous if previous in gs.teams else gs.user_team_id
    if not previous:
        return gs.user_team_id
    # No recorded identity (a world this process did not open): fall back to
    # resolving through the club, newest occupant last.
    by_club = gs.seat_for_session(previous)
    if by_club is not None and by_club.team_id in gs.teams:
        return by_club.team_id
    for mid in sorted(gs.managers):
        moved = gs.managers[mid]
        if moved.last_team_id == previous and moved.team_id in gs.teams:
            return moved.team_id
    return previous if previous in gs.teams else gs.user_team_id


def _played_seat(session: _Session):
    """The seat this session plays, by recorded identity.

    Every seat lookup in this module has to go through here. Resolving by club
    returns whoever is employed there, which is a different person the moment
    a career moves — the dismissal gate, the dashboard and the career screen
    each broke on that in turn.
    """
    gs = session.gs
    seat = gs.managers.get(session.manager_id) if session.manager_id else None
    return seat if seat is not None else gs.seat_for_session(session.env.team_id)


def _read_only_reason(
    session: _Session, *, between_jobs_ok: bool = False
) -> str | None:
    """Why this world cannot be written from here, or None if it can.

    The single source of truth for both the write gate and the published
    action mask. Keeping them apart is what let the mask go on advertising
    actions the gate refuses — first after a dismissal, then mid-draft, then
    under browser ownership. A mask that disagrees with the gate is worse than
    a narrow mask, so they now read the same function.
    """
    gs = session.gs
    seat = _dismissed_seat(gs, session.env.team_id, session.manager_id)
    if seat is not None and not between_jobs_ok:
        return (
            f"you were dismissed by {seat.last_team_id} — that club is back "
            "under AI control and is no longer yours to run. Accept one of "
            "the jobs in get_career().offers first (accept_job)."
        )
    if _draft_blocker(gs) is not None:
        return (
            "the fantasy draft is still running, and a world mid-draft cannot "
            "be changed from here at all — this server has no draft actions. "
            "Finish the draft in the browser, then resume over MCP."
        )
    held = _other_managers(session)
    if held:
        return (
            f"world {session.code} has other human managers "
            f"({', '.join(held)}) — writing from here could overwrite "
            "decisions the web layer has not saved, and advancing would tick "
            "the week without those managers, whose clubs the AI will not "
            "play either. Reads still work. Play this world in the browser."
        )
    return None


def _masked(
    session: _Session, contract: dict[str, Any]
) -> dict[str, Any]:
    """Disable everything the write gate would refuse, with the reason.

    Used by every surface that publishes an action mask — the observation
    carries its own copy alongside get_legal_actions — so a mask can never
    drift out of agreement with ``_read_only_reason`` again.
    """
    frozen = _read_only_reason(session)
    if frozen is None:
        return contract
    # accept_job is the one write a dismissed manager still has.
    still_legal = (
        {"accept_job"}
        if _read_only_reason(session, between_jobs_ok=True) is None
        else set()
    )
    return {
        name: (
            # Only entries that declare legality are actions; a contract also
            # carries informational blocks (the market window) that must not
            # be stamped with an "enabled" they never had.
            {**entry, "enabled": False, "reason": frozen}
            if isinstance(entry, dict)
            and "enabled" in entry
            and name not in still_legal
            else entry
        )
        for name, entry in contract.items()
    }


def _codes_from_lobby() -> dict[str, str]:
    """save filename -> world code, recovered from the browser's own history.

    A world the BROWSER created gets a mode-only sidecar, so the code this
    module records is absent — and the filename is a one-way hash, which would
    leave exactly the cross-surface worlds unselectable in list_games. The
    lobby's sessions.json keeps its resumable history (rows of
    [code, team_id, team_name, mode]), and a code hashes back to its filename,
    so the mapping is recoverable without the web layer changing anything.
    """
    try:
        raw = json.loads(
            (SAVE_DIR / "sessions.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    codes: set[str] = set()
    for rows in (raw.get("history") or {}).values():
        for row in rows or []:
            if isinstance(row, (list, tuple)) and row:
                codes.add(str(row[0]))
    for seat in (raw.get("sessions") or {}).values():
        if len(seat) == 2:
            codes.add(str(seat[0]))
    found: dict[str, str] = {}
    for code in sorted(codes):
        if CODE_RE.match(code):
            found[save_path_for(code).name] = code
    return found


def _read_meta(save_path: Path) -> dict[str, Any]:
    """The world's sidecar, or an empty dict when there isn't a readable one."""
    try:
        data = json.loads(
            save_path.with_suffix(".meta.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _attached_browsers(code: str) -> set[str]:
    """Teams a browser session is attached to right now, per the lobby sidecar."""
    try:
        raw = json.loads(
            (SAVE_DIR / "sessions.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return set()
    return {
        seat[1]
        for seat in (raw.get("sessions") or {}).values()
        if len(seat) == 2 and seat[0] == code
    }


def _other_managers(session: _Session) -> list[str]:
    """Teams in this world that belong to someone other than this module.

    Two signals, and the durable one leads. ``gs.human_team_ids`` is written
    into the save when a browser claims a club and is NEVER removed —
    ``Lobby.leave`` only detaches the session — so a club stays human-managed
    long after the browser walks away. That is the signal that matters,
    because the danger is not the browser being *open*: it is that advancing
    from here bypasses the shared world's ready-up protocol and sims a human
    club's week without its manager, while the AI leaves that club alone.

    The session sidecar adds the one case the save cannot show: a browser
    sitting in OUR seat, holding a copy of the world with unsaved decisions.
    """
    gs = session.gs
    ours = session.env.team_id
    others = {tid for tid in gs.human_team_ids if tid != ours}
    if ours in _attached_browsers(session.code):
        others.add(ours)
    return sorted(others)


def _session(
    code: str, *, mutating: bool = False, between_jobs_ok: bool = False
) -> _Session:
    """Return a live session, reloading if another process moved the world.

    Worlds are browser-joinable, so the web server can be holding the same
    save. Two guards, because neither is sufficient alone:

    * **the disk stamp** catches a world the browser has written, so this
      process reads the newest state instead of stamping a stale one over it;
    * **the seat claim** catches what the stamp cannot. The web layer defers
      its writes — an ordinary browser action only marks its ``_Game`` dirty —
      so a browser can be several decisions ahead with the file untouched. No
      amount of disk watching sees that.

    So once a browser has claimed the seat this module plays, this module
    stops writing and says so. That is a real handoff rather than a race: the
    reader stays available, and the last writer is whoever the human is
    actually sitting in front of.
    """
    code = _normalize_code(code)
    session = _SESSIONS.get(code)
    if session is None or _stamp(session.path) != session.stamp:
        path = save_path_for(code)
        if not path.exists():
            raise PlayError(
                f"no world {code!r} — call list_games to see saved worlds, "
                "or new_game to start one"
            )
        gs = GameState.load(path)
        previous = (
            session.env.team_id if session is not None else gs.user_team_id
        )
        manager_id = session.manager_id if session is not None else ""
        session = _bind(
            code, gs, path,
            _follow_manager(gs, previous, manager_id), manager_id,
        )
        session.stamp = _stamp(path)
        _SESSIONS[code] = session
    if mutating:
        # One check, at the one place every write funnels through. Per-route
        # guards grew holes three separate times in this module's history.
        frozen = _read_only_reason(session, between_jobs_ok=between_jobs_ok)
        if frozen is not None:
            raise PlayError(frozen)
    return session


def _bind(
    code: str, gs: GameState, path: Path, team_id: str, manager_id: str = ""
) -> _Session:
    env = HeadlessManagerEnv(
        gs, _gamedata(), team_id, policy_version=POLICY_VERSION
    )
    if not manager_id:
        seat = gs.seat_for_session(team_id)
        manager_id = seat.id if seat is not None else ""
    return _Session(
        code=code, gs=gs, env=env, path=path, manager_id=manager_id
    )


@contextmanager
def _acting(session: _Session) -> Iterator[GameState]:
    """Bind private state (inbox, staff, facilities, ...) to the played seat."""
    gs = session.gs
    previous = gs.acting_team_id
    gs.set_acting(session.env.team_id)
    try:
        yield gs
    finally:
        gs.set_acting(previous)


def _write(session: _Session) -> None:
    """Persist the world.

    Every mutating operation writes. The web layer can afford to defer saves
    because it is one long-lived process with explicit save points; an MCP
    client is a separate process that may disconnect after any single tool
    call, and silently losing a decision the caller was told had landed is
    worse than the write.
    """
    session.path.parent.mkdir(parents=True, exist_ok=True)
    session.gs.save(session.path)
    meta = session.path.with_suffix(".meta.json")
    if _read_meta(session.path).get("code") != session.code:
        # The save filename is a one-way hash of the code, so without this the
        # code is unrecoverable once this process exits — and list_games could
        # not offer the resume flow it advertises. The web lobby reads only
        # "mode" from this sidecar, so the extra key is inert there.
        meta.write_text(
            json.dumps({"mode": _read_meta(session.path).get("mode", "shared"),
                        "code": session.code}),
            encoding="utf-8",
        )
    elif not meta.exists():
        # "shared", not "solo", is what actually makes the browser-compat
        # claim true. The lobby only lets a browser back into a SOLO world
        # through its own per-browser history, which an MCP-created world can
        # never be in; a shared world is reachable by typing the code. The
        # seat this module plays is left claimable — the lobby releases a
        # human seat whenever no browser session is attached to it — so
        # joining with the same team id is a hand-off, not a conflict.
        meta.write_text(json.dumps({"mode": "shared"}), encoding="utf-8")
    # Remember the world exactly as we left it, so the next call can tell our
    # own write apart from another process's.
    session.stamp = _stamp(session.path)


# ---------------------------------------------------------------------------
# Small shared views
# ---------------------------------------------------------------------------


def _record(gs: GameState, team_id: str) -> dict[str, Any]:
    rec = gs.standings.get(team_id)
    if rec is None:
        return {"wins": 0, "losses": 0, "round_diff": 0}
    return {"wins": rec.wins, "losses": rec.losses, "round_diff": rec.diff}


def _position(gs: GameState, team_id: str) -> dict[str, Any]:
    region = str(gs.teams[team_id].region)
    order = gs.standings_order(region, tier=gs.teams[team_id].tier)
    return {
        "region": region,
        "place": order.index(team_id) + 1 if team_id in order else None,
        "of": len(order),
    }


def _fixture_view(gs: GameState, f, team_id: str | None = None) -> dict[str, Any]:
    a, b = gs.teams.get(f.team_a), gs.teams.get(f.team_b)
    view: dict[str, Any] = {
        "fixture_id": f.id,
        "week": f.week,
        "stage": f.stage,
        "bracket": f.bracket,
        "tier": f.tier,
        "best_of": f.best_of,
        "team_a": {"id": f.team_a, "name": a.name if a else f.team_a},
        "team_b": {"id": f.team_b, "name": b.name if b else f.team_b},
        "maps": list(f.maps),
        "played": f.played,
    }
    if f.played:
        score_a, score_b = f.map_score
        view["map_score"] = [score_a, score_b]
        view["winner_id"] = f.winner_id
        view["results"] = [
            {
                "map_id": r.map_id,
                "score_a": r.score_a,
                "score_b": r.score_b,
                "winner_id": r.winner_id,
            }
            for r in f.results
        ]
        if f.series_notes:
            view["series_notes"] = list(f.series_notes)
    if team_id is not None and team_id in (f.team_a, f.team_b):
        opponent = f.team_b if f.team_a == team_id else f.team_a
        view["opponent"] = {
            "id": opponent,
            "name": gs.teams[opponent].name if opponent in gs.teams else opponent,
        }
        if f.played:
            view["result"] = (
                "win" if f.winner_id == team_id
                else "loss" if f.winner_id else "draw"
            )
    return view


def _inbox_view(gs: GameState, item) -> dict[str, Any]:
    view = inbox_mod.to_api(item, gs)
    actions = inbox_mod.actions_for(gs, item)
    if actions:
        view["actions"] = actions
    return view


def _pending_events(gs: GameState, team_id: str) -> list[dict[str, Any]]:
    """Blocking events WITH their copy.

    The action contract publishes only the choice ids, which asks a manager to
    decide blind; these are narrative choices whose whole content is the text.
    """
    events: list[dict[str, Any]] = []
    flavor = flavor_events.pending_for(gs, team_id)
    if flavor is not None:
        events.append({
            "action": "resolve_flavor",
            "event": flavor_events.to_api(flavor),
        })
    media = media_events.pending_for(gs, team_id)
    if media is not None:
        events.append({
            "action": "resolve_media",
            "event": media_events.to_api(gs, media),
        })
    for demand in sponsors.demand_views(gs, team_id):
        if demand.get("status") == "pending":
            events.append({
                "action": "sponsor_demand_respond",
                "event": demand,
            })
    return events


# A contract this close to running out is a deadline, not a nudge: one more
# tick and the player can walk.
URGENT_CONTRACT_WEEKS = 1


def _dismissed_seat(gs: GameState, team_id: str, manager_id: str = ""):
    """The seat this env plays if it has been fired, else None.

    ``career.apply_dismissals`` clears the seat's team and hands the club back
    to the AI, but the env stays bound to that club until ``accept_job``. So
    without this check a dismissed manager keeps running an org that is no
    longer theirs — setting its tactics, releasing its players, spending its
    money.

    Resolved through the recorded seat id, for the same reason the reload is:
    ``seat_for_session`` answers with whoever is employed at the club, so once
    somebody else moves into the club we were fired from, it stops reporting
    OUR dismissal — the gate opens and the writes land on the new manager's
    org instead.
    """
    seat = gs.managers.get(manager_id) if manager_id else None
    if seat is None:
        seat = gs.seat_for_session(team_id)
    return seat if seat is not None and not seat.team_id else None


def _draft_blocker(gs: GameState) -> str | None:
    """Why the season cannot start yet, if a fantasy draft is still running.

    The headless env has no notion of the draft: five picks in, a squad is
    ``ROSTER_SIZE`` and reads as ready, so advancing would start the season
    with a half-built roster and forfeit the rest of the picks for every club.
    The browser refuses the same state. Drafting itself is not exposed here,
    so this points at the surface that can finish it.
    """
    draft = gs.fantasy_draft
    if draft is None or not draft.active:
        return None
    return (
        "the fantasy draft is still running — finish it in the browser "
        "before the season can start"
    )


def _needs_you(
    gs: GameState, team_id: str, legal: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """What is waiting on this manager, split by whether it can wait.

    Returns (every call, the subset with a deadline). The distinction matters
    because a fast-forward has to stop for anything that expires — a bid, a
    pending event, a contract in its last week — but must NOT stop for a
    standing advisory. "A contract expires within six weeks" is true for six
    consecutive weeks, so halting on it would make sim_ahead a permanent
    no-op, which is a worse failure than the one it prevents.
    """
    calls: list[str] = []
    urgent: list[str] = []

    def add(text: str, deadline: bool = True) -> None:
        calls.append(text)
        if deadline:
            urgent.append(text)

    if legal["resolve_flavor"]["enabled"]:
        add("a squad event is waiting on your choice (resolve_flavor)")
    if legal["resolve_media"]["enabled"]:
        add("a media decision is waiting on you (resolve_media)")
    if legal["accept_job"]["enabled"]:
        add("you have a job offer to answer (accept_job)")
    if legal["sponsor_respond"]["enabled"]:
        add("sponsor offers are on the table (sponsor_respond)")
    if legal["sponsor_demand_respond"]["enabled"]:
        add("a sponsor has made a demand (sponsor_demand_respond)")
    if legal["negotiate_offer"]["enabled"]:
        add("contract talks are open (negotiate_offer)")
    if _draft_blocker(gs) is not None:
        add(f"advance is blocked: {_draft_blocker(gs)}")
    elif not legal["advance"]["enabled"]:
        add(f"advance is blocked: {legal['advance']['reason']}")
    incoming = [o for o in gs.transfer_offers if o.from_team == team_id]
    if incoming:
        add(
            f"{len(incoming)} bid(s) for your players await an answer "
            "(transfer_respond)"
        )
    roster = [gs.players[pid] for pid in gs.teams[team_id].player_ids]
    last_call = [p for p in roster if p.contract_weeks_left <= URGENT_CONTRACT_WEEKS]
    if last_call:
        add(
            f"{len(last_call)} contract(s) expire this week — "
            f"{', '.join(sorted(p.handle for p in last_call))} (renew)"
        )
    soon = [
        p for p in roster
        if URGENT_CONTRACT_WEEKS < p.contract_weeks_left <= 6
    ]
    if soon:
        add(f"{len(soon)} contract(s) expiring within 6 weeks (renew)", False)
    return calls, urgent


# ---------------------------------------------------------------------------
# Lobby — worlds
# ---------------------------------------------------------------------------


def list_packs() -> dict[str, Any]:
    """Roster packs (importable worlds) installed alongside the fictional one."""
    packs = [
        {
            "pack_id": meta.id,
            "name": meta.name,
            "description": meta.description,
            "start_year": meta.start_year,
            "regions": list(meta.world.league_regions),
            "teams_per_region": meta.world.teams_per_region,
        }
        for meta in list_roster_packs()
    ]
    return {
        "packs": packs,
        "default": None,
        "note": (
            "Pass pack_id=null to new_game for the generated fictional world, "
            "or a pack id to play an authored league."
        ),
    }


def _preview_world(seed: int, pack) -> GameState:
    """A throwaway world on this seed, for previews and offer slates.

    Roster packs replace the fictional starters, so ``team_nexus`` is not a
    safe default there — mirror the lobby and take the pack's first tier-1
    club.
    """
    user = (
        sorted(t.id for t in pack.teams.values() if t.tier == 1)[0]
        if pack is not None else "team_nexus"
    )
    return new_campaign(
        _gamedata(), seed=int(seed), pack=pack, mode="sandbox",
        user_team_id=user,
    )


def _career_offer_slate(seed: int, pack) -> list[Any]:
    """The founding seat's job offers, derived exactly as the lobby does."""
    return career.new_game_offers(_preview_world(seed, pack), 0)


def list_career_offers(seed: int = 1, pack_id: str | None = None) -> dict[str, Any]:
    """The clubs that would offer you a legacy career on this seed.

    A legacy start is a choice between board offers, not a free pick of any
    club: each archetype sets the contract's goal and patience, so the offer
    IS the difficulty and the brief. Pass one of these team ids, and the same
    seed, to new_game(mode="legacy").
    """
    pack = load_roster_pack(pack_id) if pack_id else None
    world = _preview_world(seed, pack)
    return {
        "seed": int(seed),
        "pack_id": pack_id,
        "offers": [
            {
                **offer.model_dump(mode="json"),
                "team_name": world.teams[offer.team_id].name
                if offer.team_id in world.teams else offer.team_id,
            }
            for offer in career.new_game_offers(world, 0)
        ],
        "note": (
            "Sandbox mode ignores this — any tier-1 club is playable there, "
            "and you are never dismissed."
        ),
    }


def list_scenarios() -> dict[str, Any]:
    """The sandbox opening presets new_game(scenario=...) accepts.

    Each one reshapes the user's own org before week 1 — a wage bill it cannot
    afford, a squad of teenagers — and nothing else in the world. Published
    because the parameter is otherwise an invitation to guess at internal ids.
    """
    from esports_sim.manager import scenarios

    return {
        "scenarios": scenarios.options(),
        "note": (
            "Sandbox only: a legacy career starts from the board's offer "
            "slate instead (list_career_offers). Omit scenario for the "
            "classic start."
        ),
    }


def list_playable_teams(
    seed: int = 1, pack_id: str | None = None, tier: int = 1
) -> dict[str, Any]:
    """Teams you can manage in the world this seed builds.

    Squad quality, balance, and even which clubs sit in tier 1 are functions
    of the seed, so this previews the world at the SAME seed you will pass to
    ``new_game`` — a listing from another seed describes a different league.
    """
    pack = load_roster_pack(pack_id) if pack_id else None
    # Through _preview_world, because a pack replaces the fictional starters:
    # new_campaign's "team_nexus" default does not exist in a pack world, so
    # building the preview directly made the documented pack path raise.
    gs = _preview_world(seed, pack)
    teams = [
        {
            "team_id": t.id,
            "name": t.name,
            "tag": t.tag,
            "region": str(t.region),
            "tier": t.tier,
            "reputation": round(float(t.reputation), 1),
            "balance": t.balance,
            "roster_size": len(t.player_ids),
            "squad_quality": round(
                sum(market.player_quality(gs.players[pid]) for pid in t.player_ids)
                / max(1, len(t.player_ids)),
                1,
            ),
        }
        for t in sorted(gs.teams.values(), key=lambda t: (t.tier, str(t.region), t.name))
        if tier == 0 or t.tier == tier
    ]
    return {
        "seed": int(seed),
        "pack_id": pack_id,
        "tier": tier,
        "teams": teams,
        "note": (
            "Pass this same seed to new_game — team tiers and squad quality "
            "are seed-dependent. Tier 1 is the franchised league; tier 2 is "
            "Challengers."
        ),
    }


def new_game(
    team_id: str,
    seed: int = 1,
    code: str | None = None,
    pack_id: str | None = None,
    mode: str = "sandbox",
    manager_name: str = "",
    scenario: str | None = None,
) -> dict[str, Any]:
    """Start a campaign and return the world code plus the opening dashboard.

    ``mode`` is "sandbox" (never fired) or "legacy" (board goals, contracts,
    dismissal). ``scenario`` applies one sandbox-only opening preset.
    """
    if mode not in ("sandbox", "legacy"):
        raise PlayError("mode must be 'sandbox' or 'legacy'")
    if scenario:
        from esports_sim.manager import scenarios

        if scenario not in scenarios.SCENARIOS:
            raise PlayError(
                f"unknown scenario {scenario!r} — choose from "
                f"{sorted(scenarios.SCENARIOS)} (see list_scenarios)"
            )
    code = _normalize_code(code) if code else _new_code(seed)
    path = save_path_for(code)
    if path.exists() or code in _SESSIONS:
        raise PlayError(f"world {code!r} already exists — load_game it instead")
    pack = load_roster_pack(pack_id) if pack_id else None
    offer = None
    if mode == "legacy":
        # A legacy career starts from a board OFFER, not a free pick of any
        # club: the archetype carries the contract's goal and patience. Derive
        # the founding seat's slate from a preview world on the same seed —
        # exactly what the browser lobby shows and validates against — so a
        # career started here gets the same contract it would there, instead
        # of the fabricated sleeping_giant fallback in career.create_seat.
        offers = _career_offer_slate(int(seed), pack)
        offer = next((o for o in offers if o.team_id == team_id), None)
        if offer is None:
            raise PlayError(
                f"{team_id!r} is not offering you a job — a legacy career "
                "starts from the board's slate. Offered: "
                + ", ".join(f"{o.team_id} ({o.archetype})" for o in offers)
            )
    try:
        gs = new_campaign(
            _gamedata(),
            seed=int(seed),
            user_team_id=team_id,
            pack=pack,
            mode=mode,
            manager_name=manager_name,
            career_offer=offer,
            scenario=scenario,
        )
    except (KeyError, ValueError) as exc:
        raise PlayError(f"could not start that campaign: {exc}") from exc
    if team_id not in gs.teams:
        raise PlayError(
            f"unknown team {team_id!r} — call list_playable_teams first"
        )
    session = _bind(code, gs, path, team_id)
    if scenario:
        # Picking a scenario is a human decision like any other, and the
        # action log is the replay record — seed plus action_log is meant to
        # determine a whole career. The mutation itself is chronicled inside
        # new_campaign; recording the pick is the caller's job (see
        # manager/scenarios.py), which the web lobby also does.
        from esports_sim.manager import telemetry

        telemetry.record_action(
            gs, "scenario_start", {"scenario": scenario},
            team_id=team_id, source="agent",
        )
    warnings = []
    if gs.teams[team_id].tier != 1:
        warnings.append(
            f"{gs.teams[team_id].name} is a tier-{gs.teams[team_id].tier} "
            "(Challengers) club at this seed — playable, but it sits outside "
            "the franchised league. list_playable_teams(seed) shows tiers."
        )
    _SESSIONS[code] = session
    _write(session)
    return {
        "code": code,
        "seed": int(seed),
        "mode": mode,
        "pack_id": pack_id,
        "warnings": warnings,
        "state": get_state(code),
        "note": (
            "Play loop: get_state -> get_legal_actions -> act(...) -> "
            "advance_week. Every decision is saved as it lands."
        ),
    }


def list_games() -> dict[str, Any]:
    """Saved worlds this server can load, newest save first."""
    worlds = []
    from_lobby = _codes_from_lobby()
    for path in sorted(SAVE_DIR.glob("campaign_*.json")):
        if path.name.endswith(".meta.json"):
            continue
        loaded = next(
            (c for c, s in _SESSIONS.items() if s.path == path), None
        )
        # The sidecar is the durable source: a fresh stdio process has an empty
        # session cache, and the filename hash cannot be reversed, so without
        # it every world here would come back uncodeable and unloadable.
        code = (
            loaded
            or _read_meta(path).get("code")
            or from_lobby.get(path.name)
        )
        entry: dict[str, Any] = {
            "file": path.name,
            "code": code,
            "loaded": loaded is not None,
            "modified_bytes": path.stat().st_size,
        }
        if code is not None:
            try:
                view = _session(code)
            except PlayError:
                view = None
            if view is not None:
                entry.update(
                    season=view.gs.season,
                    week=view.gs.week,
                    team_id=view.env.team_id,
                    team_name=view.gs.teams[view.env.team_id].name,
                )
        worlds.append(entry)
    return {
        "worlds": worlds,
        "note": (
            "Pass a world's code to load_game. Codes come from this server's "
            "own record and, for browser-created worlds, from the lobby's "
            "resumable history. A null code means neither knows it: the save "
            "filename is a one-way hash, so only someone who still has the "
            "code can open that world."
        ),
    }


def load_game(code: str) -> dict[str, Any]:
    """Load a saved world and return its dashboard."""
    session = _session(code)
    return {"code": session.code, "state": get_state(session.code)}


def save_game(code: str) -> dict[str, Any]:
    """Force a write of the world to disk."""
    session = _session(code, mutating=True)
    _write(session)
    return {"code": session.code, "saved_to": str(session.path)}


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


def get_state(code: str) -> dict[str, Any]:
    """The compact dashboard: where the season is and what needs you now."""
    session = _session(code)
    with _acting(session) as gs:
        team_id = session.env.team_id
        team = gs.teams[team_id]
        legal = get_legal_actions(session.code, enabled_only=False)["actions"]
        dismissed = _dismissed_seat(gs, team_id, session.manager_id)
        calls, urgent = _needs_you(gs, team_id, legal)
        fixture = gs.team_fixture(team_id)
        unread = sum(1 for it in gs.inbox if it.unread)
        seat = _played_seat(session)
        return {
            "code": session.code,
            "season": gs.season,
            "week": gs.week,
            "phase": gs.phase,
            "game_mode": gs.game_mode,
            "team": {
                "id": team_id,
                "name": team.name,
                "tag": team.tag,
                "region": str(team.region),
                "tier": team.tier,
                "balance": team.balance,
                "reputation": round(float(team.reputation), 1),
                "roster_size": len(team.player_ids),
            },
            # Between jobs the club above is a former employer, not yours.
            "dismissed": dismissed is not None,
            "manager": (
                {
                    "name": seat.name,
                    "reputation": career.reputation(gs, seat.id),
                    "contract": (
                        seat.contract.model_dump(mode="json")
                        if seat.contract is not None else None
                    ),
                }
                if seat is not None else None
            ),
            "record": _record(gs, team_id),
            "position": _position(gs, team_id),
            "next_fixture": (
                _fixture_view(gs, fixture, team_id)
                if fixture is not None and not fixture.played else None
            ),
            "unread_inbox": unread,
            # On the dashboard because it silently gates every market plan:
            # a closed window makes bids, buyouts and releases impossible and
            # nothing else on this screen would say so.
            "market_window": market.market_window_status(gs),
            "pending_events": _pending_events(gs, team_id),
            "can_advance": (
                legal["advance"]["enabled"] and _draft_blocker(gs) is None
            ),
            "advance_blocked_by": (
                _draft_blocker(gs) or legal["advance"]["reason"]
            ),
            "needs_you": calls,
            # The subset that expires if you tick past it — what sim_ahead
            # halts for, and what to answer before advancing by hand.
            "deadlines": urgent,
            "enabled_actions": sorted(
                kind for kind, c in legal.items() if c.get("enabled")
            ),
        }


def get_observation(
    code: str, sections: list[str] | None = None
) -> dict[str, Any]:
    """The raw manager observation, optionally narrowed to named sections.

    With no sections this returns the full decision-time contract — large, but
    exactly what the headless env and every learned policy see.
    """
    session = _session(code)
    observation = manager_observation(
        session.gs, _gamedata(), session.env.team_id
    )
    # The observation carries its own legal_actions, so it is a second copy of
    # the mask and has to agree with the gate for the same reasons
    # get_legal_actions does — a learned policy consuming this contract would
    # otherwise be handed impossible moves.
    observation["legal_actions"] = _masked(
        session, observation["legal_actions"]
    )
    if not sections:
        return observation
    unknown = [s for s in sections if s not in OBSERVATION_SECTIONS]
    if unknown:
        raise PlayError(
            f"unknown observation section(s) {unknown} — "
            f"choose from {list(OBSERVATION_SECTIONS)}"
        )
    keep = {"observation_version", "team_id", "season", "week", "phase"}
    return {
        key: value for key, value in observation.items()
        if key in keep or key in sections
    }


def get_legal_actions(
    code: str, kinds: list[str] | None = None, enabled_only: bool = True
) -> dict[str, Any]:
    """The action contract: every legal action kind and its legal parameters."""
    session = _session(code)
    legal = manager_observation(
        session.gs, _gamedata(), session.env.team_id
    )["legal_actions"]
    # Both halves through the same overlay the observation uses, which reads
    # the same predicate as the write gate.
    legal = _masked(session, legal)
    extra = _masked(session, _extra_action_contract(session))
    if kinds:
        # Filter across BOTH halves. The direct tools live in extras, so
        # validating names against the headless contract alone rejected every
        # one of them as unknown — the client could not even ask.
        unknown = [k for k in kinds if k not in legal and k not in extra]
        if unknown:
            raise PlayError(
                f"unknown action kind(s) {unknown} — "
                f"choose from {sorted(set(legal) | set(extra))}"
            )
        legal = {k: v for k, v in legal.items() if k in kinds}
        extra = {k: v for k, v in extra.items() if k in kinds}
    elif enabled_only:
        legal = {k: v for k, v in legal.items() if v.get("enabled")}
    return {
        "season": session.gs.season,
        "week": session.gs.week,
        "actions": legal,
        "extra_actions": extra,
    }


def _extra_action_contract(session: _Session) -> dict[str, Any]:
    """Market actions that live in the web layer, not the headless contract."""
    with _acting(session) as gs:
        team_id = session.env.team_id
        window = market.market_window_status(gs)
        incoming = []
        for offer in gs.transfer_offers:
            if offer.from_team != team_id:
                continue
            view = {
                "player_id": offer.player_id,
                "handle": gs.players[offer.player_id].handle,
                # Named for the transfer_respond parameter it feeds. Two clubs
                # can bid for the same player, and respond_offer falls back to
                # the lexicographically first bidder when the buyer is not
                # named — so publishing this under any other key invites
                # answering a deal the manager never looked at.
                "to_team": offer.to_team,
                "buyer_name": gs.teams[offer.to_team].name
                if offer.to_team in gs.teams else offer.to_team,
                "fee": offer.fee,
                "expires_week": offer.expires_week,
                # Exactly market.respond_offer's own predicate. Checking only
                # the players called a cash-BACK offer (no players, cash owed
                # to the buyer) a plain cash bid and showed fee 0 — so the
                # seller could accept, lose the player AND pay, having been
                # shown nothing at all.
                "kind": (
                    "package"
                    if offer.offer_player_ids or offer.cash_to_buyer
                    else "cash"
                ),
            }
            if view["kind"] == "package":
                # transfer_respond is irreversible, so the whole consideration
                # has to be visible before it: a package's value is the
                # players and the direction of the cash, not the headline fee.
                view["offered_players"] = [
                    {
                        "player_id": pid,
                        "handle": gs.players[pid].handle,
                        "perceived_quality": round(
                            market.perceived_quality(gs, team_id, gs.players[pid]), 3
                        ),
                    }
                    for pid in offer.offer_player_ids if pid in gs.players
                ]
                view["cash_to_seller"] = offer.cash_to_seller
                view["cash_to_buyer"] = offer.cash_to_buyer
            incoming.append(view)

        team = gs.teams[team_id]
        # Every cash acquisition ends in market.execute_transfer, which refuses
        # a human buyer with no roster space. Without this the contract offers
        # bids and a list of clause targets that are all guaranteed refusals.
        cap = market.roster_cap(gs, team_id)
        has_room = len(team.player_ids) < cap
        # Per-map overrides only mean anything for a fixture that has not been
        # played, so publish the (fixture, map) pairs that can take one.
        # Every unplayed pair, uncapped: set_map_lineup accepts any of them, so
        # a truncated list is a contract that hides legal parameters — the
        # client would have to invent ids until earlier fixtures fell off. The
        # size is bounded by what remains of this team's own schedule.
        map_lineup_slots = [
            {"fixture_id": f.id, "map_id": map_id, "week": f.week}
            for f in sorted(gs.fixtures, key=lambda x: (x.week, x.id))
            if not f.played and team_id in (f.team_a, f.team_b)
            for map_id in f.maps
        ]
        # Buyout clauses are a tier-1 privilege (market.buy_out_player), and
        # the buyer must cover the clause AND a wage reserve. Advertising the
        # action without both makes every target a guaranteed rejection.
        can_buy_out = team.tier == 1 and has_room
        buyout_targets = []
        if can_buy_out:
            for pid, player in sorted(gs.players.items()):
                owner = market.team_of(gs, pid)
                if owner is None or owner == team_id:
                    continue
                fee = market.buyout_fee(gs, pid)
                if fee is None:
                    continue
                reserve = market.asking_salary(player) * 8
                if team.balance >= fee + reserve:
                    buyout_targets.append({
                        "player_id": pid,
                        "handle": player.handle,
                        "fee": fee,
                        "wage_reserve": reserve,
                    })
        return {
            "transfer_bid": {
                "enabled": bool(window["open"]) and has_room,
                "roster_space": cap - len(team.player_ids),
                "reason": (
                    "" if has_room
                    else f"roster is full ({cap}) — release or sell first"
                ),
                "note": (
                    "Cash bid at the seller's ask. Use get_transfer_target for "
                    "the fee and the selling club's stance first."
                ),
            },
            "transfer_respond": {
                "enabled": bool(incoming),
                "offers": incoming,
                "note": (
                    "Pass to_team from the offer you mean. Several clubs can "
                    "bid for one player, and omitting it answers whichever "
                    "bid sorts first, not the one you read."
                ),
            },
            "transfer_package": {
                # Published because how_to_play promises every action and its
                # parameters come from the contract; a tool the mask never
                # mentions can only be reached by guessing.
                "enabled": bool(window["open"]) and len(team.player_ids) > 1,
                "offerable_player_ids": sorted(team.player_ids),
                "note": (
                    "Players plus cash for one target. cash_to_seller is what "
                    "you pay, cash_to_buyer what you ask back. Find targets "
                    "with get_scouting/get_market and price them with "
                    "get_transfer_target — a package still has to clear the "
                    "selling club's valuation."
                ),
            },
            "transfer_buyout": {
                "enabled": bool(window["open"]) and bool(buyout_targets),
                "reason": (
                    "" if can_buy_out
                    else "only a tier-1 org can trigger a buyout clause"
                    if team.tier != 1
                    else f"roster is full ({cap}) — release or sell first"
                ),
                # Every affordable clause, uncapped. transfer_buyout accepts
                # any of them, and a contract that counts targets it will not
                # name forces the client to source ids from outside it. The
                # list is bounded by who actually has a clause this club can
                # cover.
                "targets": buyout_targets,
                "target_count": len(buyout_targets),
            },
            "market_window": window,
            # The direct tools. They bypass `act`, so without an entry here a
            # client following get_legal_actions cannot see that they exist,
            # let alone whether they are usable right now.
            "set_agent_lock": {
                "enabled": bool(team.player_ids),
                "player_ids": sorted(team.player_ids),
                "note": (
                    "Lock one starter to an agent; omit agent_id to restore "
                    "the auto pick. Every agent is legal — get_tactics().lineup "
                    "ranks each player's options by mastery and duel edge."
                ),
            },
            "set_map_lineup": {
                "enabled": bool(map_lineup_slots),
                "slots": map_lineup_slots,
                "count": market.ROSTER_SIZE,
                "player_ids": sorted(team.player_ids),
                "note": (
                    "Dress a specific five for one map of one fixture; it "
                    "overrides the default lineup. Pass no player_ids to "
                    "clear the override."
                ),
            },
            "set_scout_directive": {
                "enabled": True,
                "lanes": ["pro", "amateur"],
                "pro_directives": list(scouting.PRO_DIRECTIVES),
                "amateur_directives": list(scouting.AMATEUR_DIRECTIVES),
                "roles": sorted(SCOUT_ROLES),
                "role_wildcard": "any",
                "calibers": sorted(scouting.CALIBER_FLOOR),
                "note": (
                    "A standing directive replaces re-picking a scout target "
                    "every week. Pass an empty directive to clear the lane and "
                    "fall back to the single act(kind='set_scout') slot."
                ),
            },
        }


def act(code: str, kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply one manager action through the shared headless action contract."""
    # "advance" is in the action contract, so a client following the contract
    # will reach the tick through here. Send it down the one path that snapshots
    # the pre-tick world, or the digest it gets back has no cash swing, no table
    # move, every inbox item marked new, and a mislabelled week after a season
    # rollover.
    if kind == "advance":
        return advance_week(code)
    # Taking a new post is the one move a dismissed manager still has.
    session = _session(
        code, mutating=True, between_jobs_ok=(kind == "accept_job")
    )
    try:
        step = session.env.step({"kind": kind, "params": dict(params or {})})
    except InvalidManagerAction as exc:
        # A rejected action must leave no trace. Some manager helpers mutate
        # before reporting failure — negotiate_offer deletes a negotiation the
        # roster has moved out from under before returning "error" — and that
        # residue would otherwise be persisted by the next successful action
        # with no action-log entry to explain it, or lost on process exit.
        # Every accepted mutation is already on disk, so dropping the cached
        # world rolls back to exactly the last accepted action. This differs
        # from a market REFUSAL, which the game records deliberately as
        # history (see _market_action) rather than incidentally.
        _SESSIONS.pop(session.code, None)
        raise PlayError(f"illegal action: {exc}") from exc
    _write(session)
    return {
        "ok": True,
        "kind": kind,
        "message": step.message,
        "state": get_state(session.code),
    }


def advance_week(code: str) -> dict[str, Any]:
    """Tick the world one week and report what actually happened."""
    # The draft gate lives in _session(mutating=True) now — one source of
    # truth for every write, not a check per route.
    session = _session(code, mutating=True)
    with _acting(session) as gs:
        team_id = session.env.team_id
        before = {
            "week": gs.week,
            "season": gs.season,
            "balance": gs.teams[team_id].balance,
            "position": _position(gs, team_id),
            "inbox_ids": {it.id for it in gs.inbox},
        }
    try:
        step = session.env.step({"kind": "advance", "params": {}})
    except InvalidManagerAction as exc:
        raise PlayError(
            f"cannot advance: {exc} — check get_state().needs_you"
        ) from exc
    return _week_digest(session, step, before)


def _week_digest(
    session: _Session, step, before: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What the tick did: results, table movement, cash swing, new mail."""
    with _acting(session) as gs:
        team_id = session.env.team_id
        played_week = before["week"] if before else gs.week - 1
        played_season = before["season"] if before else gs.season
        # Scope the digest to the week that just resolved. A "fixtures I have
        # not shown yet" set would live only in this process, so a client that
        # reconnects between weeks would be re-told about old matches.
        fresh = [f for f in gs.fixtures if f.played and f.week == played_week]
        ours = [f for f in fresh if team_id in (f.team_a, f.team_b)]
        new_mail = [
            it for it in gs.inbox
            if before is None or it.id not in before["inbox_ids"]
        ]
        digest: dict[str, Any] = {
            "ok": True,
            "advanced": True,
            "played": {"season": played_season, "week": played_week},
            "your_matches": [_fixture_view(gs, f, team_id) for f in ours],
            "other_results": [
                _fixture_view(gs, f) for f in fresh if f not in ours
            ][:12],
            "inbox": [_inbox_view(gs, it) for it in new_mail],
            "reward": round(step.reward, 4),
            "reward_components": step.reward_components,
            "season_rolled": played_season != gs.season,
            "state": get_state(session.code),
        }
        if before is not None:
            digest["cash_change"] = gs.teams[team_id].balance - before["balance"]
            after = _position(gs, team_id)
            if after["place"] != before["position"]["place"]:
                digest["table_move"] = {
                    "from": before["position"]["place"],
                    "to": after["place"],
                }
        if step.done:
            digest["done"] = True
            digest["note"] = "your seat ended — check get_career for offers"
    _write(session)
    return digest


def sim_ahead_weeks(code: str, max_weeks: int = 6) -> dict[str, Any]:
    """Advance until something needs you, or the cap — the fast-forward button.

    The stop condition is checked BEFORE the first tick as well as after each
    one. Plenty of things make ``needs_you`` non-empty without blocking the
    advance — an incoming bid, a contract in its last week — so the entry
    check is the only thing between a fast-forward and a week that silently
    expires the very offer the caller was promised a stop for.
    """
    session = _session(code, mutating=True)
    if max_weeks < 1:
        raise PlayError("max_weeks must be positive")
    digests: list[dict[str, Any]] = []
    reason = f"reached the requested cap of {max_weeks} week(s)"
    for _ in range(int(max_weeks)):
        state = get_state(session.code)
        if state["deadlines"]:
            reason = f"something needs you: {state['deadlines'][0]}"
            break
        if not state["can_advance"]:
            reason = f"cannot advance: {state['advance_blocked_by']}"
            break
        digests.append(advance_week(session.code))
        if digests[-1].get("done"):
            reason = "your seat ended"
            break
    return {
        "weeks_advanced": len(digests),
        # Reported by the loop that stopped, not re-derived afterwards: a
        # recomputed reason cannot tell "your seat ended" from "the cap".
        "stopped_because": reason,
        "weeks": digests,
        "state": get_state(session.code),
    }


# ---------------------------------------------------------------------------
# Read screens
# ---------------------------------------------------------------------------


def get_inbox(
    code: str, unread_only: bool = False, limit: int = 20
) -> dict[str, Any]:
    """This manager's weekly feed, newest first."""
    session = _session(code)
    with _acting(session) as gs:
        items = list(reversed(inbox_mod.sorted_items(gs)))
        if unread_only:
            items = [it for it in items if it.unread]
        return {
            "unread": inbox_mod.unread_count(gs),
            "by_category": inbox_mod.unread_counts(gs),
            "items": [_inbox_view(gs, it) for it in items[: max(1, limit)]],
        }


def mark_inbox_read(code: str, item_id: str = "") -> dict[str, Any]:
    """Mark one item read, or the whole feed when no id is given."""
    session = _session(code, mutating=True)
    with _acting(session) as gs:
        n = (
            inbox_mod.mark_read(gs, item_id) if item_id
            else inbox_mod.mark_all_read(gs)
        )
        _write(session)
        return {"marked_read": n, "unread": inbox_mod.unread_count(gs)}


def get_standings(code: str, region: str | None = None) -> dict[str, Any]:
    """League tables — your region first unless one is named."""
    session = _session(code)
    with _acting(session) as gs:
        team_id = session.env.team_id
        user_region = str(gs.teams[team_id].region)
        regions = (
            [region] if region
            else sorted(gs.regions(), key=lambda r: (r != user_region, r))
        )

        def rows(reg: str, tier: int) -> list[dict[str, Any]]:
            return [
                {
                    "place": i + 1,
                    "team_id": tid,
                    "name": gs.teams[tid].name,
                    "is_you": tid == team_id,
                    **_record(gs, tid),
                }
                for i, tid in enumerate(gs.standings_order(reg, tier=tier))
            ]

        return {
            "phase": gs.phase,
            "week": gs.week,
            "regions": [
                {
                    "region": reg,
                    "is_yours": reg == user_region,
                    "tier1": rows(reg, 1),
                    "tier2": rows(reg, 2),
                }
                for reg in regions
            ],
        }


def get_schedule(code: str, weeks: int = 4, all_teams: bool = False) -> dict[str, Any]:
    """Upcoming fixtures — yours by default, or the whole league."""
    session = _session(code)
    with _acting(session) as gs:
        team_id = session.env.team_id
        upcoming = [
            f for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id))
            if not f.played
            and f.week < gs.week + max(1, weeks)
            and (all_teams or team_id in (f.team_a, f.team_b))
        ]
        return {
            "from_week": gs.week,
            "fixtures": [_fixture_view(gs, f, team_id) for f in upcoming],
        }


def get_results(
    code: str, team_id: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Played fixtures, most recent first."""
    session = _session(code)
    with _acting(session) as gs:
        target = team_id or session.env.team_id
        played = [
            f for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id), reverse=True)
            if f.played and (target == "*" or target in (f.team_a, f.team_b))
        ]
        return {
            "team_id": None if target == "*" else target,
            "results": [
                _fixture_view(gs, f, None if target == "*" else target)
                for f in played[: max(1, limit)]
            ],
        }


def get_match(code: str, fixture_id: str) -> dict[str, Any]:
    """One fixture in full: per-map scores and the player lines that survived."""
    session = _session(code)
    with _acting(session) as gs:
        fixture = next((f for f in gs.fixtures if f.id == fixture_id), None)
        if fixture is None:
            raise PlayError(f"no fixture {fixture_id!r} in this world")
        view = _fixture_view(gs, fixture, session.env.team_id)
        view["maps_detail"] = [
            {
                "map_id": r.map_id,
                "score_a": r.score_a,
                "score_b": r.score_b,
                "winner_id": r.winner_id,
                "lines": [
                    {
                        "player_id": line.player_id,
                        "handle": gs.players[line.player_id].handle
                        if line.player_id in gs.players else line.player_id,
                        **line.model_dump(exclude={"player_id"}),
                    }
                    for line in r.lines
                ],
            }
            for r in fixture.results
        ]
        return view


def get_season_report(code: str, season: int | None = None) -> dict[str, Any]:
    """Champions, awards, and the season's headline numbers."""
    session = _session(code)
    with _acting(session) as gs:
        return analytics.season_report(gs, season)


def get_player(code: str, player_id: str) -> dict[str, Any]:
    """One player, fogged exactly as the scouting system allows."""
    session = _session(code)
    with _acting(session) as gs:
        if player_id not in gs.players:
            raise PlayError(f"no player {player_id!r} in this world")
        team_id = session.env.team_id
        owner = market.team_of(gs, player_id)
        observation = manager_observation(gs, _gamedata(), team_id)
        pool = (
            observation["roster"] if owner == team_id
            else observation["free_agents"]
        )
        # The two pools key their id differently — an own player is "id", a
        # scouting report is "player_id" — so matching only one silently drops
        # every free agent into the rival fallback, losing the asking salary
        # and season stats a signing decision actually turns on.
        view = next(
            (
                p for p in pool
                if player_id in (p.get("id"), p.get("player_id"))
            ),
            None,
        )
        if view is None:
            # A rival's player: the same scouted read the market screens use.
            player = gs.players[player_id]
            progress = max(
                gs.scout_progress.get(owner or "market", 0.0),
                gs.scout_progress.get(f"player:{player_id}", 0.0),
            )
            view = development.scout_report(gs, player, progress)
            view["perceived_quality"] = round(
                market.perceived_quality(gs, team_id, player), 3
            )
        view["owner"] = (
            {"team_id": owner, "name": gs.teams[owner].name}
            if owner in gs.teams else None
        )
        view["is_yours"] = owner == team_id
        view["chronicle"] = [
            e.model_dump(mode="json")
            for e in chronicle.entries_for_player(gs, player_id)[-10:]
        ]
        return view


def get_team(code: str, team_id: str) -> dict[str, Any]:
    """One club: record, roster (scout-fogged for rivals), and honours."""
    session = _session(code)
    with _acting(session) as gs:
        if team_id not in gs.teams:
            raise PlayError(f"no team {team_id!r} in this world")
        team = gs.teams[team_id]
        yours = team_id == session.env.team_id
        return {
            "team_id": team_id,
            "name": team.name,
            "tag": team.tag,
            "region": str(team.region),
            "tier": team.tier,
            "reputation": round(float(team.reputation), 1),
            "is_yours": yours,
            "balance": team.balance if yours else None,
            "record": _record(gs, team_id),
            "position": _position(gs, team_id),
            "tactics": team.tactics.model_dump() if yours else None,
            "roster": [
                get_player(session.code, pid) for pid in sorted(team.player_ids)
            ],
            "chronicle": [
                e.model_dump(mode="json")
                for e in chronicle.entries_for_team(gs, team_id)[-10:]
            ],
        }


def get_market(code: str, limit: int = 25) -> dict[str, Any]:
    """The free-agent pool plus the live contract talks on your desk."""
    session = _session(code)
    observation = manager_observation(
        session.gs, _gamedata(), session.env.team_id
    )
    with _acting(session) as gs:
        free_agents = sorted(
            observation["free_agents"],
            key=lambda p: -float(p.get("perceived_quality", 0.0)),
        )
        return {
            "window": market.market_window_status(gs),
            "roster_cap": market.roster_cap(gs, session.env.team_id),
            "balance": gs.teams[session.env.team_id].balance,
            "free_agents": free_agents[: max(1, limit)],
            "free_agent_count": len(free_agents),
            "negotiations": observation["negotiations"],
            "incoming_offers": _extra_action_contract(session)[
                "transfer_respond"
            ]["offers"],
        }


def get_transfer_target(code: str, player_id: str) -> dict[str, Any]:
    """What a contracted rival player would actually cost, and whether they sell."""
    session = _session(code)
    with _acting(session) as gs:
        if player_id not in gs.players:
            raise PlayError(f"no player {player_id!r} in this world")
        owner = market.team_of(gs, player_id)
        if owner is None:
            raise PlayError(
                f"{gs.players[player_id].handle} is a free agent — "
                "use act(kind='sign') or negotiate_open"
            )
        if owner == session.env.team_id:
            raise PlayError("that is your own player")
        fee = market.transfer_ask(gs, player_id)
        stance = market.org_player_valuation(gs, owner, player_id, "sell")
        return {
            "player": get_player(session.code, player_id),
            "owner": {"team_id": owner, "name": gs.teams[owner].name},
            "transfer_ask": fee,
            "ask_breakdown": market.transfer_ask_breakdown(gs, player_id),
            "buyout_fee": market.buyout_fee(gs, player_id),
            "seller_stance": stance,
            "your_balance": gs.teams[session.env.team_id].balance,
            "wage_reserve_needed": market.asking_salary(gs.players[player_id]) * 8,
        }


def get_tactics(code: str) -> dict[str, Any]:
    """The dials with their roster fit, and the agent menu for every starter.

    Dial impact is computed here from ``sim/tactics_fit.py`` — the same code
    the match engine runs — so this preview cannot drift from what a match
    actually applies. Each dial is piecewise linear in its value with the knot
    at the neutral 50, so ``impact_lo`` (value 0) and ``impact_hi`` (value 100)
    bracket everything in between; at 50 the impact is exactly zero.

    Fit is measured over the five who will actually DRESS, not the whole
    roster: past a squad of five the engine only ever sees
    ``campaign.dressed_for``'s five, so a bench-inclusive average would
    quietly describe a team that never takes the server. A series resolves
    that five per MAP, so when per-map lineups make the maps disagree this
    also returns a ``per_map`` preview rather than passing the first map's
    numbers off as the series'.
    """
    from esports_sim.manager.campaign import dressed_for
    from esports_sim.sim import constants as sim_constants
    from esports_sim.sim import lineup as lineup_resolve
    from esports_sim.sim import tactics_fit

    session = _session(code)
    with _acting(session) as gs:
        team = gs.teams[session.env.team_id]
        fixture = gs.team_fixture(session.env.team_id)
        per_map: dict[str, list[str]] = {}
        if fixture is not None and not fixture.played and fixture.maps:
            per_map = {
                map_id: dressed_for(gs, session.env.team_id, fixture, map_id)
                for map_id in fixture.maps
            }
            dressed = per_map[fixture.maps[0]]
            dressed_from = f"the five dressing on {fixture.maps[0]} ({fixture.id})"
        else:
            # No fixture to resolve against: the default lineup is the best
            # available statement of intent, topped up in roster order.
            picked = [
                pid for pid in team.lineup_ids if pid in team.player_ids
            ]
            picked += [pid for pid in team.player_ids if pid not in picked]
            dressed = picked[:market.ROSTER_SIZE]
            dressed_from = "your default lineup (no fixture to resolve against)"
        definitions = _gamedata().attributes.definitions
        chem_edge = tactics_fit.chem_edge(team.chemistry)

        def named(attrs) -> list[str]:
            return [
                definitions[a].display_name if a in definitions else a
                for a in attrs
            ]

        def dials_for(five: list[str]) -> list[dict[str, Any]]:
            """Every dial's fit and both pole impacts for one dressed five."""
            roster = [gs.players[pid] for pid in five if pid in gs.players]

            def scored(dial: str, pole: str) -> list[dict[str, Any]]:
                fits = tactics_fit.dial_pole_player_fits(roster, dial, pole)
                return sorted(
                    (
                        {"handle": p.handle, "playstyle": str(p.playstyle),
                         "score": round(fit)}
                        for p, fit in zip(roster, fits)
                    ),
                    key=lambda s: -s["score"],
                )

            out = []
            for dial, poles in tactics_fit.DIAL_POLE_FIT_ATTRS.items():
                fits_lo = tactics_fit.dial_pole_player_fits(roster, dial, "low")
                fits_hi = tactics_fit.dial_pole_player_fits(roster, dial, "high")
                gated = dial in tactics_fit.CHEM_GATED
                out.append({
                    "dial": dial,
                    "value": getattr(team.tactics, dial),
                    "low_means": named(poles["low"]),
                    "high_means": named(poles["high"]),
                    "fit_low": round(
                        sum(fits_lo) / len(fits_lo) if fits_lo else 50.0, 1
                    ),
                    "fit_high": round(
                        sum(fits_hi) / len(fits_hi) if fits_hi else 50.0, 1
                    ),
                    "impact_at_0": round(
                        tactics_fit.dial_pole_edge(roster, dial, "low"), 4
                    ),
                    "impact_at_100": round(
                        tactics_fit.dial_pole_edge(roster, dial, "high")
                        + (chem_edge if gated else 0.0), 4
                    ),
                    "chemistry_gated": gated,
                    "best_at_low": scored(dial, "low")[:3],
                    "best_at_high": scored(dial, "high")[:3],
                })
            return out

        dials = dials_for(dressed)
        # Only worth the extra payload when the maps actually disagree.
        map_previews = None
        if len({tuple(sorted(five)) for five in per_map.values()}) > 1:
            map_previews = [
                {
                    "map_id": map_id,
                    "player_ids": list(five),
                    "dials": dials_for(five),
                }
                for map_id, five in per_map.items()
            ]

        agents = _gamedata().agents
        lineup = []
        for pid in team.player_ids:
            if pid not in gs.players:
                continue
            player = gs.players[pid]
            auto = lineup_resolve.auto_pick_agent(player, agents)
            locked = team.lineup.agents.get(pid)
            locked = locked if locked in agents else None
            options = sorted(
                (
                    {
                        "agent_id": a.id,
                        "name": a.display_name,
                        "role": str(a.role),
                        "mastery": round(player.agent_mastery(a.id, 0.0)),
                        "duel_edge": development.agent_pick_edge(player, a.id),
                    }
                    for a in agents.values()
                ),
                key=lambda o: (-o["mastery"], o["name"]),
            )
            lineup.append({
                "player_id": pid,
                "handle": player.handle,
                "dressing": pid in dressed,
                "role": str(player.role),
                "playstyle": str(player.playstyle),
                "locked_agent": locked,
                "auto_agent": auto,
                "resolved_agent": locked or auto,
                # Every agent, mastery-ordered — not a top-N slice. Any of
                # them is a legal lock, and an option the contract never names
                # can only be reached by guessing an id. Mastery 0 off-pool is
                # the honest cost cue, which is why the web publishes the full
                # menu too rather than hiding the bad picks.
                "agents": options,
            })

        return {
            "tactics": team.tactics.model_dump(),
            "chemistry": round(team.chemistry, 1),
            "impact_cap": sim_constants.EXEC_MOD_CAP,
            # Name the five the numbers describe: with a bench, changing the
            # lineup changes every fit figure on this screen.
            "measured_over": {
                "player_ids": list(dressed),
                "source": dressed_from,
                # Overrides beat the default five, so name the ones in force —
                # otherwise a stale one silently outranks every lineup change.
                "map_overrides": {
                    map_id: list(five) for map_id, five in per_map.items()
                    if f"{team.id}|{fixture.id}|{map_id}" in gs.map_lineups
                } if fixture is not None else {},
                "benched": [
                    gs.players[pid].handle
                    for pid in team.player_ids
                    if pid not in dressed and pid in gs.players
                ],
            },
            "dials": dials,
            # Present only when per-map lineups make the maps of this series
            # dress different fives; `dials` above is then the first map's.
            "per_map": map_previews,
            "lineup": lineup,
            "note": (
                "Every dial is an exact no-op at 50. A dial your roster does "
                "not fit still moves the match — against you. Set dials with "
                "act(kind='set_tactics'); lock an agent with set_agent_lock."
            ),
        }


def set_map_lineup(
    code: str, fixture_id: str, map_id: str, player_ids: list[str] | None = None
) -> dict[str, Any]:
    """Dress a specific five for one map of one fixture, or clear the override.

    ``campaign.dressed_for`` reads these per-map overrides BEFORE the team's
    default lineup, so an override left in place silently wins over any
    default five set here — including one a browser left behind. Passing no
    player_ids clears it and hands the map back to the default.
    """
    from esports_sim.manager import telemetry

    session = _session(code, mutating=True)
    with _acting(session) as gs:
        team_id = session.env.team_id
        fixture = next((f for f in gs.fixtures if f.id == fixture_id), None)
        if fixture is None or team_id not in (fixture.team_a, fixture.team_b):
            raise PlayError(f"no fixture {fixture_id!r} of yours in this world")
        if fixture.played:
            raise PlayError("that fixture has already been played")
        if map_id not in fixture.maps:
            raise PlayError(
                f"{map_id!r} is not on that fixture — maps are {list(fixture.maps)}"
            )
        key = f"{team_id}|{fixture_id}|{map_id}"
        picks: list[str] = []
        if not player_ids:
            gs.map_lineups.pop(key, None)
            message = f"{map_id} back to your default lineup"
        else:
            picks = list(player_ids)
            roster = set(gs.teams[team_id].player_ids)
            if len(picks) != market.ROSTER_SIZE or len(set(picks)) != len(picks):
                raise PlayError(
                    f"dress exactly {market.ROSTER_SIZE} different players"
                )
            outside = [pid for pid in picks if pid not in roster]
            if outside:
                raise PlayError(f"not on your roster: {outside}")
            gs.map_lineups[key] = picks
            message = f"{map_id} lineup set for {fixture_id}"
        if gs.is_human(team_id):
            telemetry.record_action(
                gs, "set_lineup",
                {
                    "agents": False,
                    "default_five": False,
                    "per_map": True,
                    "fixture_id": fixture_id,
                    "map_id": map_id,
                    # The five itself, empty when clearing. Without it every
                    # per-map decision on one map records identically, so a
                    # replay of seed + action_log cannot tell which players
                    # were dressed — and the dressed five changes results.
                    "player_ids": picks,
                },
                team_id=team_id, source="agent",
            )
    _write(session)
    return {"ok": True, "kind": "set_map_lineup", "message": message}


def set_agent_lock(
    code: str, player_id: str, agent_id: str = ""
) -> dict[str, Any]:
    """Lock one starter onto an agent, or clear the lock back to the auto pick."""
    from esports_sim.manager import telemetry

    session = _session(code, mutating=True)
    with _acting(session) as gs:
        team = gs.teams[session.env.team_id]
        if player_id not in team.player_ids:
            raise PlayError(f"{player_id!r} is not on your roster")
        if agent_id and agent_id not in _gamedata().agents:
            raise PlayError(
                f"unknown agent {agent_id!r} — see get_tactics().lineup"
            )
        if agent_id:
            team.lineup.agents[player_id] = agent_id
            message = (
                f"{gs.players[player_id].handle} locked to "
                f"{_gamedata().agents[agent_id].display_name}"
            )
        else:
            team.lineup.agents.pop(player_id, None)
            message = (
                f"{gs.players[player_id].handle} back to the automatic pick"
            )
        if gs.is_human(session.env.team_id):
            # "set_assignment" is the web's kind for changing a player's
            # ROLE/PLAYSTYLE; agent locks ride the lineup endpoint and record
            # "set_lineup". Recording the wrong kind hands replay consumers an
            # action whose params do not belong to it, and skews the
            # feature-usage report. Same shape the web writes, plus the lock
            # itself, which the web leaves in the lineup payload.
            telemetry.record_action(
                gs, "set_lineup",
                {
                    "agents": True,
                    "default_five": False,
                    "per_map": False,
                    "player_id": player_id,
                    "agent_id": agent_id,
                },
                team_id=session.env.team_id, source="agent",
            )
    _write(session)
    return {"ok": True, "kind": "set_agent_lock", "message": message}


def get_scouting(code: str) -> dict[str, Any]:
    """The scout desk: who you're watching and what the intel has bought you."""
    session = _session(code)
    with _acting(session) as gs:
        view = scouting.scout_desk_view(gs, session.env.team_id)
        # The desk publishes directives and calibers but not the roles a
        # fill_gap sweep can name, which leaves a contract-driven client
        # guessing at a value the weekly consumer matches exactly.
        view["directives"] = dict(view.get("directives", {}))
        view["directives"]["roles"] = sorted(SCOUT_ROLES)
        view["directives"]["role_wildcard"] = "any"
        return view


def set_scout_directive(
    code: str,
    lane: str,
    directive: str = "",
    role: str = "any",
    caliber: str = "any",
) -> dict[str, Any]:
    """Give a scouting lane a STANDING directive instead of a weekly re-pick.

    ``lane`` is "pro" or "amateur". An empty ``directive`` clears the lane and
    the department falls back to the single ``set_scout`` slot. ``role`` and
    ``caliber`` only apply to the pro lane's "fill_gap" directive.
    """
    from esports_sim.manager import telemetry

    session = _session(code, mutating=True)
    if lane not in ("pro", "amateur"):
        raise PlayError("lane must be 'pro' or 'amateur'")
    with _acting(session) as gs:
        stored: str | None = directive or None
        if stored is not None:
            if lane == "pro":
                if stored == "fill_gap":
                    if caliber not in scouting.CALIBER_FLOOR:
                        raise PlayError(
                            f"unknown caliber {caliber!r} — choose from "
                            f"{sorted(scouting.CALIBER_FLOOR)}"
                        )
                    # The weekly consumer matches a non-empty role EXACTLY
                    # (scouting._build_shortlist), so anything it cannot match
                    # sweeps up nobody, week after week, while still reporting
                    # success. The wildcard has to be the empty string, and a
                    # named role has to be canonical and lower-case — "any",
                    # "Duelist" and a typo all fail the same silent way.
                    wanted = (role or "").strip().lower()
                    if wanted in ("", "any"):
                        wanted = ""
                    elif wanted not in SCOUT_ROLES:
                        raise PlayError(
                            f"unknown role {role!r} — choose from "
                            f"{sorted(SCOUT_ROLES)}, or 'any' for every role"
                        )
                    stored = f"fill_gap:{wanted}:{caliber}"
                elif stored not in scouting.PRO_DIRECTIVES:
                    raise PlayError(
                        f"unknown pro directive {stored!r} — choose from "
                        f"{list(scouting.PRO_DIRECTIVES)}"
                    )
            elif stored not in scouting.AMATEUR_DIRECTIVES:
                raise PlayError(
                    f"unknown amateur directive {stored!r} — choose from "
                    f"{list(scouting.AMATEUR_DIRECTIVES)}"
                )
        team_id = session.env.team_id
        lanes = gs.scout_lanes_by.setdefault(team_id, {})
        if stored is None:
            lanes.pop(lane, None)
        else:
            lanes[lane] = stored
        # A stored fill_gap shortlist only means anything while the pro lane is
        # actually running fill_gap; drop it otherwise so the desk stops
        # surfacing a stale list.
        if lane == "pro" and not (lanes.get("pro") or "").startswith("fill_gap"):
            gs.scout_shortlist_by.pop(team_id, None)
        if gs.is_human(team_id):
            telemetry.record_action(
                gs, "set_scout_directive",
                {"lane": lane, "directive": stored or ""},
                team_id=team_id, source="agent",
            )
    _write(session)
    return {
        "ok": True,
        "kind": "set_scout_directive",
        "message": f"{lane} scouting directive: {stored or 'cleared'}",
    }


def get_finances(code: str) -> dict[str, Any]:
    """Weekly income/expenses, cash projection, and live sponsor deals.

    The signed deals matter as much as the totals: an objective bonus or an
    expiring slot is what makes a wage or transfer decision affordable. The
    raw observation only carries UNSIGNED market offers, so without this an
    agent can see what it might sign and never what it already has.
    """
    session = _session(code)
    with _acting(session) as gs:
        team_id = session.env.team_id
        staff_cost = sum(m.salary for m in gs.staff.values())
        return {
            "balance": gs.teams[team_id].balance,
            "weekly": economy.weekly_breakdown(gs, staff_cost),
            "projection": economy.cash_projection(gs, staff_cost),
            "sponsors": {
                "signed": {
                    slot: gs.sponsor_slots[slot].model_dump(mode="json")
                    for slot in sponsors.SLOT_ORDER
                    if slot in gs.sponsor_slots
                },
                "open_slots": [
                    slot for slot in sponsors.SLOT_ORDER
                    if slot not in gs.sponsor_slots
                ],
                "commitments": sponsors.commitment_views(gs, team_id),
                "demands": sponsors.demand_views(gs, team_id),
                "marketability": sponsors.marketability_breakdown(gs),
            },
        }


def get_club(code: str) -> dict[str, Any]:
    """Staff, facilities, academy, culture — the org behind the five players."""
    session = _session(code)
    observation = manager_observation(
        session.gs, _gamedata(), session.env.team_id
    )
    with _acting(session) as gs:
        return {
            "staff": {
                role: {
                    "id": m.id,
                    "name": m.name,
                    "role": m.role,
                    "salary": m.salary,
                    "overall": staff_effects.overall(m),
                }
                for role, m in sorted(gs.staff.items())
            },
            "facilities": facilities.menu_view(gs),
            "academy": observation["club"]["academy"],
            "culture": observation["club"]["culture"],
            "preparation": observation["club"]["preparation"],
            "delegation": observation["club"]["delegation"],
        }


def get_analyst_digest(code: str) -> dict[str, Any]:
    """The coaching read on your last series — why you won or lost."""
    session = _session(code)
    with _acting(session) as gs:
        digest = match_review.analyst_digest(gs, session.env.team_id)
        if digest is None:
            return {
                "digest": None,
                "note": "no reviewed series yet — play a match first",
            }
        return {"digest": digest}


def get_chronicle(code: str, limit: int = 25, kinds: list[str] | None = None) -> dict[str, Any]:
    """The append-only career history every legacy system reads."""
    session = _session(code)
    with _acting(session) as gs:
        entries = (
            chronicle.of_kinds(gs, kinds) if kinds else list(gs.chronicle)
        )
        return {
            "entries": [
                e.model_dump(mode="json") for e in entries[-max(1, limit):]
            ],
            "total": len(gs.chronicle),
        }


def get_league(code: str) -> dict[str, Any]:
    """Power rankings, award races, and all-time records in one call."""
    session = _session(code)
    with _acting(session) as gs:
        return {
            "power_rankings": analytics.power_rankings(gs),
            "award_races": analytics.award_races(gs),
            "records": analytics.all_time_records(gs),
            "parity": analytics.parity(gs),
        }


def get_career(code: str) -> dict[str, Any]:
    """Your seat: contract, board patience, reputation, and job offers."""
    session = _session(code)
    with _acting(session) as gs:
        seat = _played_seat(session)
        if seat is None:
            return {"seat": None, "note": "no manager seat controls this club"}
        offers = gs.career_offers_by.get(seat.id, [])
        return {
            "seat": seat.model_dump(mode="json"),
            # A sandbox seat exists and carries the career history; what it
            # lacks is a contract, which is what makes dismissal possible.
            "note": (
                "sandbox seat — no contract, so you are never dismissed"
                if seat.contract is None else
                f"legacy seat — the board wants {seat.contract.goal}"
            ),
            "offers": [o.model_dump(mode="json") for o in offers],
            "chronicle": [
                e.model_dump(mode="json")
                for e in chronicle.entries_for_manager(gs, seat.id)[-10:]
            ],
        }


def get_playtest_summary(code: str) -> dict[str, Any]:
    """The designer's-eye read of this campaign — what the systems produced."""
    session = _session(code)
    with _acting(session) as gs:
        return {
            "summary": analytics.playtest_summary(gs),
            "legibility": analytics.decision_legibility(gs),
        }


# ---------------------------------------------------------------------------
# Market actions the headless contract does not carry
# ---------------------------------------------------------------------------


def transfer_bid(code: str, player_id: str) -> dict[str, Any]:
    """Bid the asking fee for a contracted player at another club."""
    return _market_action(
        code, "bid", {"player_id": player_id},
        lambda gs: market.user_bid(gs, player_id),
    )


def transfer_buyout(code: str, player_id: str) -> dict[str, Any]:
    """Trigger a release clause — instant, no negotiation, premium price."""
    return _market_action(
        code, "buyout", {"player_id": player_id},
        lambda gs: market.buy_out_player(gs, gs.acting_team_id, player_id),
    )


def transfer_respond(
    code: str, player_id: str, accept: bool, to_team: str | None = None
) -> dict[str, Any]:
    """Answer a bid another manager has made for one of your players."""
    return _market_action(
        code, "respond_offer",
        {"player_id": player_id, "accept": accept, "to_team": to_team},
        lambda gs: market.respond_offer(gs, player_id, accept, to_team),
    )


def transfer_package(
    code: str,
    player_id: str,
    offer_player_ids: list[str] | None = None,
    cash_to_seller: int = 0,
    cash_to_buyer: int = 0,
) -> dict[str, Any]:
    """Offer players plus cash for a target instead of a straight fee."""
    return _market_action(
        code, "propose_package",
        {
            "player_id": player_id,
            "offer_player_ids": list(offer_player_ids or []),
            "cash_to_seller": int(cash_to_seller),
            "cash_to_buyer": int(cash_to_buyer),
        },
        lambda gs: market.propose_package(
            gs, player_id, list(offer_player_ids or []),
            int(cash_to_seller), int(cash_to_buyer),
        ),
    )


def _market_action(code: str, kind: str, params: dict[str, Any], fn) -> dict[str, Any]:
    """Apply a web-layer market action and record it like any human decision."""
    from esports_sim.manager import telemetry

    session = _session(code, mutating=True)
    # A refusal is not a no-op here: several market helpers write real state
    # before returning False — a rejected bid is appended to market_history,
    # a stale package can drop the pending offer before settlement fails. So
    # the write is unconditional, exactly as the browser endpoints save on
    # these paths. Leaving it out meant a refusal lived only in memory: saved
    # later by an unrelated action, or lost if the process exited first.
    try:
        with _acting(session) as gs:
            result = fn(gs)
            ok, message = result[0], result[1]
            # Record the call whether or not it succeeded. A refusal can still
            # write state (a rejected bid appends to market_decisions), and
            # persisting that while logging nothing leaves a save the action
            # log cannot rebuild — the two halves of the replay contract have
            # to agree. Replaying a rejected call is safe: same state in, same
            # refusal and same side effects out.
            if gs.is_human(session.env.team_id):
                telemetry.record_action(
                    gs, kind,
                    {**params, "outcome": "accepted" if ok else "rejected"},
                    team_id=session.env.team_id, source="agent",
                )
            if not ok:
                raise PlayError(f"illegal action: {message}")
    finally:
        _write(session)
    return {
        "ok": True,
        "kind": kind,
        "message": message,
        "state": get_state(session.code),
    }


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------


def how_to_play() -> dict[str, Any]:
    """The rules of the game as an agent needs them, in one call."""
    return {
        "goal": (
            "Manage an esports org through a multi-region season: win your "
            "region, reach the playoffs and internationals, develop players, "
            "and stay solvent. In legacy mode the board can also fire you."
        ),
        "loop": [
            "get_state — where the season is and what needs you",
            "get_legal_actions — the exact legal parameters for every action",
            "act — one decision at a time (tactics, lineup, market, staff...)",
            "advance_week — tick the world and read the digest it returns",
        ],
        "week_rhythm": [
            "Match weeks: set a game plan and lineup, book preparation, then advance.",
            "The advance gate blocks on roster legality and pending events; "
            "get_state().advance_blocked_by names the blocker.",
            "Development, finances, scouting and morale all resolve on the tick, "
            "so decisions made after an advance apply to the NEXT week.",
        ],
        "key_systems": {
            "tactics": (
                "Five 0-100 dials plus site focus. 50 is exactly neutral; the "
                "further from 50, the stronger the effect and the more it "
                "depends on whether your roster fits it."
            ),
            "game_plan": (
                "A per-match override of tactics, a focus target on the "
                "opponent, a one-match lineup, and a team talk. Consumed at "
                "sim time — set it before you advance."
            ),
            "development": (
                "set_dev_plan per player (focus + intensity), mentorships, and "
                "the training focus for the squad. Growth is slow and "
                "compounding; potential is a scouted range, not a number."
            ),
            "market": (
                "Free agents are signed directly; contracted players need a "
                "cash bid, a buyout, or a package. Windows close in playoffs."
            ),
            "scouting": (
                "set_scout aims one scout at the market, a rival club, one "
                "player, or one upcoming match. Progress narrows the fog on "
                "attributes and potential — you cannot buy well while blind."
            ),
            "economy": (
                "Sponsors, merch, and stream income fund wages, staff, and "
                "facility upgrades. Insolvency is real; check get_finances."
            ),
        },
        "gotchas": [
            "Actions are legal-or-rejected: read get_legal_actions rather than "
            "guessing ids. Every id in the contract is exactly what act wants.",
            "A no-op action (setting a dial to its current value) returns a "
            "message saying so — it is not an error, but it wastes a decision.",
            "Every decision is written to disk as it lands, so a dropped "
            "connection never loses work; save_game is only there if you want "
            "to force a write.",
        ],
    }
