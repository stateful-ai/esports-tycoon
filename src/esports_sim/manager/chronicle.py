"""The Chronicle — the campaign's append-only career history.

The match layer has one doctrine: the event log is the only truth, and
everything downstream is a pure reader. The chronicle is that doctrine
lifted to career scale. Titles, awards, retirements, market moves,
debuts, and development milestones are recorded here as typed entries at
the moment they happen; career profiles, manager reputation, memories,
the Hall of Fame, rivalries, and narrative callbacks are all READERS of
this list and hold no history of their own.

Rules:
- Emission is rng-free: an entry is a pure function of a state
  transition that already happened. Call sites iterate sorted
  structures, so the chronicle is campaign-deterministic.
- Nothing is ever pruned (owner call, 2026-07-09): decades-long saves
  keep their whole past. `importance` exists so readers can SELECT, not
  so a writer can drop.
- Entry ids are blake2 of stable parts — never Python hash().
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import ChronicleEntry, GameState

# Default importance per kind (0-100). A reader slicing "landmarks" at
# >= 60 gets titles, big awards, and notable retirements; memories and
# profile timelines read lower.
KIND_IMPORTANCE: dict[str, float] = {
    "champions_title": 95.0,
    "masters_title": 85.0,
    "regional_title": 70.0,
    "challengers_title": 30.0,
    "award": 60.0,
    "retirement": 40.0,
    "signing": 25.0,
    "release": 25.0,
    "renewal": 15.0,
    "transfer": 35.0,
    "poach": 30.0,
    "debut": 20.0,
    "milestone": 30.0,
    "dismissal": 80.0,
    "appointment": 65.0,
    "hall_of_fame": 90.0,
    "rivalry": 45.0,
    "meta_shift": 35.0,
    "all_star": 50.0,
    "badge": 55.0,
    "badge_lost": 30.0,
    "media": 30.0,
}


def _entry_id(season: int, week: int, kind: str, *parts: object) -> str:
    key = "|".join(str(x) for x in (season, week, kind, *parts))
    return hashlib.blake2b(key.encode("utf-8"), digest_size=8).hexdigest()


def record(
    gs: "GameState",
    kind: str,
    text: str,
    *,
    team_id: str = "",
    player_id: str = "",
    manager_id: str = "",
    importance: float | None = None,
    data: dict[str, str] | None = None,
) -> "ChronicleEntry | None":
    """Append one entry (dedup-safe: an identical (season, week, kind,
    subject) tuple records once, so a re-entrant call site can't double-
    write). Returns the entry, or None when deduped."""
    from esports_sim.manager.state import ChronicleEntry

    eid = _entry_id(gs.season, gs.week, kind, team_id, player_id, text)
    if gs.chronicle and any(e.id == eid for e in gs.chronicle[-64:]):
        # Same tick, same fact — only same-tick duplicates are possible
        # (the id embeds season+week), so a bounded tail scan suffices.
        return None
    entry = ChronicleEntry(
        id=eid,
        season=gs.season,
        week=gs.week,
        kind=kind,
        importance=(
            KIND_IMPORTANCE.get(kind, 20.0) if importance is None else importance
        ),
        team_id=team_id,
        player_id=player_id,
        manager_id=manager_id or _manager_of(gs, team_id),
        text=text,
        data=dict(data or {}),
    )
    gs.chronicle.append(entry)
    return entry


def _manager_of(gs: "GameState", team_id: str) -> str:
    """The human manager seat currently running a team ("" = AI org).
    The seat id follows the person across orgs in legacy mode, so a
    chronicle entry credits the manager who was actually there."""
    if not team_id or not gs.is_human(team_id):
        return ""
    seat = gs.manager_for(team_id)
    return seat.id if seat is not None else team_id


# -- readers ------------------------------------------------------------------


def entries_for_player(gs: "GameState", pid: str) -> list["ChronicleEntry"]:
    return [e for e in gs.chronicle if e.player_id == pid]


def entries_for_team(gs: "GameState", tid: str) -> list["ChronicleEntry"]:
    return [e for e in gs.chronicle if e.team_id == tid]


def entries_for_manager(gs: "GameState", mid: str) -> list["ChronicleEntry"]:
    return [e for e in gs.chronicle if e.manager_id == mid]


def landmarks(gs: "GameState", floor: float = 60.0) -> list["ChronicleEntry"]:
    return [e for e in gs.chronicle if e.importance >= floor]


def of_kinds(gs: "GameState", kinds: Iterable[str]) -> list["ChronicleEntry"]:
    ks = set(kinds)
    return [e for e in gs.chronicle if e.kind in ks]


def title_history_line(gs: "GameState", tid: str, kind: str) -> str:
    """The living-history clause for a fresh title: "their first
    Masters", "back-to-back", "their first since S3" — or "" when the
    history has nothing worth saying (silence beats invented drama).
    Call BEFORE recording this season's entry."""
    prior = sorted(
        e.season
        for e in gs.chronicle
        if e.kind == kind and e.team_id == tid and e.season < gs.season
    )
    label = {
        "champions_title": "world title",
        "masters_title": "Masters",
        "regional_title": "regional crown",
    }.get(kind, "title")
    if not prior:
        # A first in season 1 isn't history yet — everyone's on zero.
        return f"their first {label}" if gs.season > 1 else ""
    if prior[-1] == gs.season - 1:
        return "back-to-back"
    return f"their first {label} since S{prior[-1]}"


# -- development milestones ---------------------------------------------------
#
# The manager-facing "your player crossed a line" feature. Human rosters
# only (this is the manager's own longitudinal view, mirroring
# dev_history). `dev_marks` holds the last celebrated 5-point overall
# band per player; a player unseen before is marked without firing, so
# loading an old save never floods week one with milestones.

MILESTONE_BAND = 5.0
# Bands worth a headline at all (below ~55 CA a band crossing is noise).
MILESTONE_FLOOR_BAND = 11  # 11 * 5 = 55 CA


def weekly_milestones(gs: "GameState") -> list[tuple[str, str]]:
    """Detect overall-ability band crossings for human rosters. Returns
    (owner team id, message) pairs; chronicle entries are recorded here.
    Runs late in the tick, after training/dev/mental effects have landed
    (a crossing produced by a heater must not be missed)."""
    from esports_sim.manager import development

    out: list[tuple[str, str]] = []
    for tid in sorted(gs.human_team_ids):
        for p in sorted(gs.roster(tid), key=lambda x: x.id):
            band = int(development.overall(p) // MILESTONE_BAND)
            prev = gs.dev_marks.get(p.id)
            if prev is None:
                gs.dev_marks[p.id] = band
                continue
            if band > prev and band >= MILESTONE_FLOOR_BAND:
                ca = int(band * MILESTONE_BAND)
                msg = (
                    f"Milestone: {p.handle} breaks the {ca} CA barrier "
                    "for the first time."
                )
                record(
                    gs,
                    "milestone",
                    f"{p.handle} reaches {ca} CA.",
                    team_id=tid,
                    player_id=p.id,
                    data={"ca": str(ca)},
                )
                out.append((tid, msg))
            if band != prev:
                # Celebrate rises once; falling re-arms the mark so a
                # decline-then-recovery fires again (it IS news again).
                gs.dev_marks[p.id] = band
    return out


def mark_debut_pending(gs: "GameState", pid: str) -> None:
    """Flag a newly generated player (rookie class / market prospect) so
    their first dressed appearance records a debut. Players who entered
    the world before this system never fire (absent = not pending)."""
    gs.debut_marks.setdefault(pid, "")


def record_debuts(gs: "GameState", week_dressed: dict[str, set[str]]) -> None:
    """First professional appearance for pending rookies. Reads the
    dressed sets the week loop already builds; deterministic order."""
    for tid in sorted(week_dressed):
        for pid in sorted(week_dressed[tid]):
            if gs.debut_marks.get(pid) == "" and pid in gs.players:
                p = gs.players[pid]
                gs.debut_marks[pid] = f"s{gs.season}w{gs.week}"
                team = gs.teams.get(tid)
                record(
                    gs,
                    "debut",
                    f"{p.handle} makes their professional debut"
                    + (f" for {team.name}." if team else "."),
                    team_id=tid,
                    player_id=pid,
                )
