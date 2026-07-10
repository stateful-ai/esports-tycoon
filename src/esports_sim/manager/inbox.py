"""Weekly inbox — the campaign's notification feed.

At the end of every tick (see campaign.advance_week / _run_offseason) this
module aggregates the week's most important outcomes and open decisions
into a small, bounded, deterministic list of InboxItems. It does NOT run a
parallel simulation: it reads the artifacts the subsystems already produced
this week and only synthesises detection where nothing else does (contract
countdowns, player-wellbeing nudges).

Sources wired (module/state -> item category):
  WeekReport.fixtures + match_stats     -> match   (your result + top line)
  gs.transfer_offers                    -> transfer (incoming bids to answer)
  gs.roster contract countdowns          -> board    (renewals coming up)
  player morale/form/stamina (talk)      -> talk     (who needs a 1:1)
  gs.sponsor_market + weekly news        -> sponsor  (offers + objective outcomes)
  scouting-complete news line            -> scouting (report cards ready)
  gs.retired / rookie-class news         -> development (careers end, class arrives)
  curated broadcast news + gs.awards      -> news      (upsets, titles, milestones)

Determinism: every item id is a blake2 hash of stable strings
(season, week, category, subject) — never Python's salted hash(), never
wall-clock. All iteration is over sorted collections, and no RNG is drawn:
each title/body is a direct format of real GameState data, so the same
seed replays a byte-identical inbox.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from esports_sim.manager import development, sponsors, talk

if TYPE_CHECKING:  # avoid import cycle at runtime (campaign imports this)
    from esports_sim.manager.campaign import WeekReport
    from esports_sim.manager.state import GameState, InboxItem

CATEGORIES = (
    "news", "talk", "transfer", "sponsor",
    "scouting", "development", "match", "board",
)

MAX_ITEMS = 200          # rolling cap on the whole feed
PER_WEEK_CAP = 10        # keep at most this many of a single week's items
CONTRACT_MILESTONES = (12, 8, 4, 2, 1)  # weeks-left values worth a reminder

# Per-category ceilings so no single beat floods a week.
_CAT_CAP = {
    "match": 1, "transfer": 3, "board": 3, "talk": 2,
    "sponsor_offer": 3, "sponsor_obj": 2, "scouting": 2,
    "development": 3, "news": 3,
}

# Priority: lower number == more important/actionable (kept when a week
# overflows PER_WEEK_CAP, and shown first within a week).
_P_TRANSFER = 0
_P_BOARD = 1
_P_SPONSOR_OFFER = 2
_P_TALK = 3
_P_DEV_URGENT = 3
_P_SCOUTING = 4
_P_MATCH = 5
_P_DEV = 6
_P_SPONSOR_OBJ = 6
_P_NEWS = 7


# ---------------------------------------------------------------------------
# Item construction


def _hash_id(*parts: object) -> str:
    """Stable id from stable strings (blake2b, never Python hash())."""
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()


def _make(
    season: int, week: int, category: str, subject: str,
    title: str, body: str, tab: str | None,
) -> "InboxItem":
    from esports_sim.manager.state import InboxItem

    return InboxItem(
        id=_hash_id(season, week, category, subject),
        season=season,
        week=week,
        category=category,
        title=title[:70],
        body=body,
        unread=True,
        tab=tab,
    )


def _week_news(gs: "GameState", season: int, week: int) -> list[str]:
    """This week's news lines with the "[Sx Wy] " label stripped. push_news
    stamps the current (season, week), so a prefix match isolates the lines
    pushed during this very tick."""
    label = f"[S{season} W{week}] "
    return [n[len(label):] for n in gs.news if n.startswith(label)]


def _week_private_news(gs: "GameState", season: int, week: int) -> list[str]:
    """This week's PRIVATE news for the ACTING manager (scout reports, sponsor
    objectives, roster retirements). Used instead of the shared feed for
    owner-specific items so a rival's private events never leak into this
    manager's inbox in a shared world (see GameState.push_private_news)."""
    label = f"[S{season} W{week}] "
    return [n[len(label):] for n in gs.private_news if n.startswith(label)]


# ---------------------------------------------------------------------------
# Detectors (each returns a list of (priority, InboxItem))


def _user_score(f, uid: str) -> tuple[int, int]:
    """(user, opponent) score for a fixture — map wins for a series, round
    score for a single map."""
    a, b = f.map_score
    if f.best_of > 1:
        return (a, b) if f.team_a == uid else (b, a)
    if f.results:
        r = f.results[0]
        return (r.score_a, r.score_b) if f.team_a == uid else (r.score_b, r.score_a)
    return (a, b) if f.team_a == uid else (b, a)


def _user_star(gs: "GameState", f, report: "WeekReport") -> str:
    uid = gs.acting_team_id
    roster = set(gs.teams[uid].player_ids)
    best: tuple[str, float, int] | None = None
    for stats in report.match_stats.get(f.id, []):
        for pid, line in sorted(stats.lines.items()):
            if pid in roster and (best is None or line.rating > best[1]):
                best = (pid, line.rating, line.kills)
    if best is None:
        return ""
    pid, rating, kills = best
    p = gs.players.get(pid)
    if p is None:
        return ""
    return f"Top for you: {p.handle} ({kills} kills, {rating:.2f} rating)."


def _match_items(gs: "GameState", season: int, week: int, report: "WeekReport"):
    uid = gs.acting_team_id
    for f in sorted(report.fixtures, key=lambda x: x.id):
        if uid not in (f.team_a, f.team_b) or not f.played:
            continue
        opp_id = f.team_b if f.team_a == uid else f.team_a
        opp = gs.teams[opp_id].name if opp_id in gs.teams else opp_id
        won = f.winner_id == uid
        us, them = _user_score(f, uid)
        tag = "" if f.stage == "regular" else f"[{f.stage.upper()}] "
        title = f"{tag}{'Won' if won else 'Lost'} {us}-{them} {'vs' if won else 'to'} {opp}"
        maps_txt = ", ".join(r.map_id for r in f.results) or "-"
        body_lines = [
            f"Series {us}-{them} {'win over' if won else 'loss to'} {opp}.",
            f"Maps: {maps_txt}.",
        ]
        star = _user_star(gs, f, report)
        if star:
            body_lines.append(star)
        return [(
            _P_MATCH,
            _make(season, week, "match", f.id, title, "\n".join(body_lines), "standings"),
        )]
    return []


def _transfer_items(gs: "GameState", season: int, week: int):
    out = []
    uid = gs.acting_team_id
    for o in sorted(gs.transfer_offers, key=lambda o: (o.player_id, o.to_team)):
        # Only bids for THIS manager's players land on their desk.
        if o.from_team != uid:
            continue
        if o.player_id not in gs.players or o.to_team not in gs.teams:
            continue
        p = gs.players[o.player_id]
        buyer = gs.teams[o.to_team].name
        left = o.expires_week - week
        when = "this week" if left <= 0 else f"in {left} week(s)"
        title = f"{buyer} bid {o.fee:,} for {p.handle}"
        body = (
            f"{buyer} have tabled {o.fee:,} cr for {p.handle} "
            f"({p.playstyle}, age {p.age}).\n"
            f"The bid expires week {o.expires_week} ({when}).\n"
            f"Accept or decline from the market screen."
        )
        out.append((
            _P_TRANSFER,
            _make(season, week, "transfer", f"{o.player_id}|{o.to_team}", title, body, "market"),
        ))
    return out[: _CAT_CAP["transfer"]]


def _board_items(gs: "GameState", season: int, week: int):
    uid = gs.acting_team_id
    cands = []
    for pid in gs.teams[uid].player_ids:
        p = gs.players.get(pid)
        if p is None:
            continue
        n = p.contract_weeks_left
        if n in CONTRACT_MILESTONES:
            cands.append((n, pid, p))
    cands.sort(key=lambda c: (c[0], c[1]))  # most urgent first
    out = []
    for n, pid, p in cands[: _CAT_CAP["board"]]:
        when = "next week" if n == 1 else f"in {n} weeks"
        title = f"{p.handle}'s contract expires {when}"
        body = (
            f"{p.handle} ({p.playstyle}, age {p.age}) has {n} week(s) left on a "
            f"{p.salary:,}/wk deal.\n"
            f"Renew from the roster screen before they walk to free agency."
        )
        out.append((
            _P_BOARD,
            _make(season, week, "board", f"contract|{pid}", title, body, "roster"),
        ))
    return out


def _talk_items(gs: "GameState", season: int, week: int):
    uid = gs.acting_team_id
    metric = {"morale": "morale", "workload": "stamina", "form": "form"}
    cands = []
    for pid in gs.teams[uid].player_ids:
        p = gs.players.get(pid)
        if p is None:
            continue
        topic = talk.topic_for(gs, pid)
        if topic.id in metric:
            sev = getattr(p, metric[topic.id])
            cands.append((sev, pid, p, topic))
    cands.sort(key=lambda c: (c[0], c[1]))  # lowest metric == most acute
    out = []
    for _sev, pid, p, topic in cands[: _CAT_CAP["talk"]]:
        title = f"{p.handle} could use a word"
        body = topic.text + "\nHold a 1:1 from the roster screen."
        out.append((
            _P_TALK,
            _make(season, week, "talk", f"talk|{pid}|{topic.id}", title, body, "roster"),
        ))
    return out


def _describe_offer(o, slot: str) -> str:
    parts = [f"{o.brand} are courting your {slot} slot for {o.weeks} weeks."]
    parts.append(f"Steady: {o.steady.weekly:,}/wk.")
    if o.upfront.signing_bonus:
        parts.append(f"Up front: {o.upfront.signing_bonus:,} + {o.upfront.weekly:,}/wk.")
    if o.performance.per_win:
        parts.append(
            f"Performance: {o.performance.weekly:,}/wk + {o.performance.per_win:,} per win."
        )
    if o.objectives:
        objs = "; ".join(
            sponsors.OBJECTIVE_LABELS.get(ob.kind, ob.kind) for ob in o.objectives
        )
        parts.append(f"Objectives on offer: {objs}.")
    parts.append(f"On the table until week {o.expires_week}. Decide on the finances screen.")
    return "\n".join(parts)


def _sponsor_items(gs: "GameState", season: int, week: int):
    out = []
    # Fresh market offers — surfaced only the week they appear (their shelf
    # life is fixed, so expires_week pins the arrival week).
    offers = []
    for slot in sponsors.SLOT_ORDER:
        for o in gs.sponsor_market.get(slot, []):
            if o.expires_week - week == sponsors.OFFER_SHELF_LIFE:
                title = f"{o.brand} want your {slot} slot"
                offers.append((
                    _P_SPONSOR_OFFER,
                    _make(season, week, "sponsor", f"offer|{slot}|{o.brand}",
                          title, _describe_offer(o, slot), "finances"),
                ))
    out.extend(offers[: _CAT_CAP["sponsor_offer"]])
    # Objective outcomes (paid or missed) — private to THIS manager's book.
    objs = []
    for msg in _week_private_news(gs, season, week):
        if msg.startswith("Objective met") or "missed objective" in msg:
            objs.append((
                _P_SPONSOR_OBJ,
                _make(season, week, "sponsor", f"obj|{_hash_id(msg)}",
                      "Sponsor objective update", msg, "finances"),
            ))
    out.extend(objs[: _CAT_CAP["sponsor_obj"]])
    return out


def _scouting_items(gs: "GameState", season: int, week: int):
    out = []
    # Scout completions are private to the manager whose desk finished — read
    # their own channel so a rival's report never appears here.
    for msg in _week_private_news(gs, season, week):
        if msg.startswith("Scouting report on") and msg.rstrip().endswith("complete."):
            out.append((
                _P_SCOUTING,
                _make(season, week, "scouting", f"scout|{_hash_id(msg)}",
                      "Scouting report complete", msg, "scouting"),
            ))
    return out[: _CAT_CAP["scouting"]]


def _development_items(gs: "GameState", season: int, week: int):
    """Careers ending and beginning — the pipeline the user recruits from.
    (Trait reveals ride scouting progress and potential is fixed at
    generation, so neither produces a discrete weekly event to surface.)"""
    out = []
    # A retirement on THIS manager's roster is private (opens a seat only they
    # fill) — read the owner channel first so it isn't attributed to everyone,
    # and keep it ahead of the public notices so the per-category cap never
    # drops the urgent one.
    for msg in _week_private_news(gs, season, week):
        if "open seat" in msg and "retire" in msg:
            out.append((
                _P_DEV_URGENT,
                _make(season, week, "development", f"retire_seat|{_hash_id(msg)}",
                      "A player on your roster retires", msg, "roster"),
            ))
        elif "Milestone:" in msg:
            # A chronicle development milestone on THIS manager's roster
            # (a player crossed an ability band for the first time).
            out.append((
                _P_DEV,
                _make(season, week, "development", f"milestone|{_hash_id(msg)}",
                      "Development milestone", msg, "roster"),
            ))
        elif any(m in msg for m in development.DEV_EVENT_MARKERS):
            # A development event on THIS manager's roster (breakthrough,
            # slump, injury scare, viral clip, ...).
            out.append((
                _P_DEV,
                _make(season, week, "development", f"devev|{_hash_id(msg)}",
                      "Player development", msg, "roster"),
            ))
    # Retirement classes and rookie classes are public broadcast news.
    for msg in _week_news(gs, season, week):
        if msg.startswith("Retirements:") or msg.endswith("call it a career.") \
                or "quietly retire" in msg:
            out.append((
                _P_DEV,
                _make(season, week, "development", f"retire_class|{_hash_id(msg)}",
                      "Retirements", msg, None),
            ))
        elif "rookie class" in msg:
            out.append((
                _P_DEV,
                _make(season, week, "development", f"rookies|{_hash_id(msg)}",
                      "New rookie class", msg, "market"),
            ))
    return out[: _CAT_CAP["development"]]


def _rotation_items(gs: "GameState", season: int, week: int):
    """Coach's desk: a gassed starter with a fresh body on the bench is a
    rotation decision waiting to happen. Live-state read (no rng), only
    for rosters that actually carry a bench."""
    from esports_sim.manager.campaign import default_five

    team = gs.teams[gs.acting_team_id]
    if len(team.player_ids) <= 5:
        return []
    active = set(default_five(gs, team.id))
    gassed = sorted(
        (p for p in gs.roster(team.id) if p.id in active and p.stamina < 30.0),
        key=lambda p: (p.stamina, p.id),
    )
    fresh = sorted(
        (p for p in gs.roster(team.id) if p.id not in active and p.stamina >= 70.0),
        key=lambda p: (-p.stamina, p.id),
    )
    if not gassed or not fresh:
        return []
    body = (
        "Running on fumes: "
        + ", ".join(f"{p.handle} ({p.stamina:.0f} stamina)" for p in gassed[:3])
        + ".\nFresh on the bench: "
        + ", ".join(f"{p.handle} ({p.stamina:.0f})" for p in fresh[:3])
        + ".\nSet a one-match lineup in the game plan, or rotate the starting five."
    )
    return [(
        _P_DEV,
        _make(season, week, "development",
              f"rotation|{'|'.join(p.id for p in gassed[:3])}",
              "Rotation: fresh legs available", body, "tactics"),
    )]


def _news_items(gs: "GameState", season: int, week: int):
    """Curated broadcast storylines — grounded, high-signal news lines the
    other detectors don't already own, plus the end-of-season award slate."""
    out = []
    # Balance patches read from durable state, not the news ticker — the
    # patch ships at the START of the tick and a busy week's 60-line news
    # cap can evict the line before the inbox is generated.
    for note in gs.patch_history:
        if note.season == season and note.week == week and note.lines:
            out.append((
                _P_NEWS,
                _make(season, week, "news", f"patch|{note.version}",
                      f"Patch {note.version} shakes the meta",
                      "\n".join(note.lines), "stats"),
            ))
    for msg in _week_news(gs, season, week):
        title: str | None = None
        tab: str | None = None
        if msg.startswith("Upset:"):
            title, tab = "Upset in the league", "standings"
        elif "kills this season" in msg:
            title, tab = "Kill milestone", "stats"
        elif "win MASTERS" in msg or "win CHAMPIONS" in msg or "world champions" in msg:
            title, tab = "Champions crowned", "standings"
        elif "field set" in msg:
            title, tab = "International field set", "standings"
        elif "playoffs set" in msg:
            title, tab = "Playoff field set", "standings"
        elif "top the" in msg and "regular season" in msg:
            title, tab = "Regular-season leaders", "standings"
        elif "Challengers season" in msg:
            title, tab = "Challengers champions", "standings"
        if title is not None:
            out.append((
                _P_NEWS,
                _make(season, week, "news", f"news|{_hash_id(msg)}", title, msg, tab),
            ))
    out = out[: _CAT_CAP["news"]]
    # Season award slate (offseason): one tidy summary from real records.
    slate = [a for a in gs.awards if a.season == season]
    if slate:
        body = "\n".join(
            f"{a.award}: {a.handle} ({a.team_name}) — {a.value}" for a in slate
        )
        out.append((
            _P_NEWS,
            _make(season, week, "news", f"awards|{season}",
                  f"Season {season} award winners", body, "stats"),
        ))
    return out


# ---------------------------------------------------------------------------
# Generation + rolling cap


def _enforce_cap(items: list, cap: int = MAX_ITEMS) -> None:
    """Trim `items` (oldest-first) to `cap`, dropping oldest READ items
    before falling back to oldest overall. Mutates in place."""
    overflow = len(items) - cap
    if overflow <= 0:
        return
    to_remove: set[int] = set()
    for i, it in enumerate(items):          # oldest read first
        if len(to_remove) >= overflow:
            break
        if not it.unread:
            to_remove.add(i)
    for i in range(len(items)):             # then oldest overall
        if len(to_remove) >= overflow:
            break
        to_remove.add(i)
    items[:] = [it for i, it in enumerate(items) if i not in to_remove]


def generate_inbox(gs: "GameState", report: "WeekReport") -> list["InboxItem"]:
    """Append this tick's inbox items and enforce the rolling cap. Called at
    the very end of a tick, after every subsystem has run, so items reflect
    the week that just resolved. Returns the items added (for callers/tests).

    `report.season` / `report.week` identify the tick (in the offseason path
    the live gs counters have already rolled to the next season, so the
    report is the source of truth for stamping and news lookup)."""
    season, week = report.season, report.week
    in_season = report.phase != "offseason"

    candidates: list[tuple[int, "InboxItem"]] = []
    if in_season:
        candidates += _match_items(gs, season, week, report)
        candidates += _transfer_items(gs, season, week)
        candidates += _board_items(gs, season, week)
        candidates += _talk_items(gs, season, week)
        candidates += _sponsor_items(gs, season, week)
        candidates += _scouting_items(gs, season, week)
        candidates += _rotation_items(gs, season, week)
    # Careers and storylines fire in every phase (including the offseason).
    candidates += _development_items(gs, season, week)
    candidates += _news_items(gs, season, week)

    # Dedupe by id (against the batch and the existing feed), then keep the
    # highest-priority PER_WEEK_CAP. Stable sort preserves detector order
    # within a priority tier, so insertion order stays deterministic.
    seen = {it.id for it in gs.inbox}
    deduped: list[tuple[int, "InboxItem"]] = []
    for prio, it in candidates:
        if it.id in seen:
            continue
        seen.add(it.id)
        deduped.append((prio, it))
    deduped.sort(key=lambda pi: pi[0])
    chosen = [it for _prio, it in deduped[:PER_WEEK_CAP]]

    gs.inbox.extend(chosen)
    _enforce_cap(gs.inbox, MAX_ITEMS)
    return chosen


# ---------------------------------------------------------------------------
# Read API (server.py delegates here; keeps the web layer a thin serializer)


# ---------------------------------------------------------------------------
# Actionable items — Accept/Decline wired to the app's EXISTING mutation
# endpoints (/api/actions/transfer_offer, /api/actions/sponsor). Actions are
# NOT stored on the item; they are derived live from current GameState by
# reconstructing the item's deterministic id from each still-live offer and
# matching. Consequences:
#   * an offer that has expired/resolved reproduces no id match, so its item
#     quietly carries no actions on the next serve (backward compatible);
#   * the only stale window is between serving an item and clicking it, and
#     the underlying endpoint rejects a vanished offer at click time (4xx),
#     which the frontend surfaces — no new business logic lives here.
# Derivation walks sorted GameState (transfer_offers list order, SLOT_ORDER),
# so the actions attached to a given feed are deterministic for a seed.


def _transfer_actions(gs: "GameState", it: "InboxItem") -> list[dict]:
    for o in gs.transfer_offers:
        if o.player_id not in gs.players or o.to_team not in gs.teams:
            continue
        subject = f"{o.player_id}|{o.to_team}"
        if _hash_id(it.season, it.week, "transfer", subject) != it.id:
            continue
        return [
            # to_team pins WHICH buyer's bid this resolves (a manager may hold
            # several bids for one player) and is validated server-side.
            {"id": "accept", "label": "Accept",
             "endpoint": "/api/actions/transfer_offer",
             "payload": {"player_id": o.player_id, "to_team": o.to_team, "accept": True}},
            {"id": "decline", "label": "Decline",
             "endpoint": "/api/actions/transfer_offer",
             "payload": {"player_id": o.player_id, "to_team": o.to_team, "accept": False}},
        ]
    return []


def _sponsor_actions(gs: "GameState", it: "InboxItem") -> list[dict]:
    for slot in sponsors.SLOT_ORDER:
        for o in gs.sponsor_market.get(slot, []):
            # Only the market-offer items are actionable; objective-outcome
            # items share the "sponsor" category but reconstruct no id match.
            if o.expires_week - sponsors.OFFER_SHELF_LIFE != it.week:
                continue
            subject = f"offer|{slot}|{o.brand}"
            if _hash_id(it.season, it.week, "sponsor", subject) != it.id:
                continue
            return [
                {"id": "accept", "label": "Accept",
                 "endpoint": "/api/actions/sponsor",
                 "payload": {"slot": slot, "accept": True,
                             "brand": o.brand, "structure": "steady"}},
                {"id": "decline", "label": "Decline",
                 "endpoint": "/api/actions/sponsor",
                 "payload": {"slot": slot, "accept": False, "brand": o.brand}},
            ]
    return []


def actions_for(gs: "GameState", it: "InboxItem") -> list[dict]:
    """Accept/Decline actions for an item whose underlying offer is still live.
    Only transfer-offer and sponsor-offer items ever carry actions; every other
    category (and any item whose offer has expired/resolved) returns []."""
    if it.category == "transfer":
        return _transfer_actions(gs, it)
    if it.category == "sponsor":
        return _sponsor_actions(gs, it)
    return []


def to_api(it: "InboxItem", gs: "GameState | None" = None) -> dict:
    """The wire shape for one item. When `gs` is supplied, offer items whose
    underlying offer is still live also carry an `actions` list (Accept /
    Decline, each an existing endpoint + verbatim payload). The key is omitted
    otherwise, so non-actionable items keep the original frozen 8-field shape."""
    d = {
        "id": it.id,
        "season": it.season,
        "week": it.week,
        "category": it.category,
        "title": it.title,
        "body": it.body,
        "unread": it.unread,
        "tab": it.tab,
    }
    if gs is not None:
        acts = actions_for(gs, it)
        if acts:
            d["actions"] = acts
    return d


def sorted_items(gs: "GameState") -> list["InboxItem"]:
    """Newest first: season desc, week desc, then stable insertion order
    within a week (Python's sort is stable and gs.inbox is insertion-order)."""
    return sorted(gs.inbox, key=lambda it: (-it.season, -it.week))


def unread_count(gs: "GameState") -> int:
    return sum(1 for it in gs.inbox if it.unread)


def mark_read(gs: "GameState", item_id: str) -> int:
    """Mark one item read (unknown id is a no-op). Returns the unread count."""
    for it in gs.inbox:
        if it.id == item_id:
            it.unread = False
    return unread_count(gs)


def mark_all_read(gs: "GameState") -> int:
    for it in gs.inbox:
        it.unread = False
    return 0
