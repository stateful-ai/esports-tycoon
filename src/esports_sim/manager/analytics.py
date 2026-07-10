"""Season & all-time analytics — deterministic readers over GameState.

Everything here is a pure SELECTION over the chronicle, career_stats, and
the current standings/stats (the same doctrine as manager/memories.py and
season stats). No RNG, no writes, sorted iteration throughout, so a report
is byte-stable for a given GameState.

This is the groundwork for the headless LLM-playtest / world-model export
(ROADMAP north-star bet #2): one structured, grounded season summary an
external reader can consume, plus the save's record book.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from esports_sim.manager import narrative

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState

_TITLE_KINDS = ("champions_title", "masters_title", "regional_title")
_TITLE_WEIGHT = {"champions_title": 5.0, "masters_title": 3.0, "regional_title": 1.0}
DYNASTY_WINDOW = 5  # seasons of recent titles that feed the index


def dynasty_index(gs: "GameState", tid: str, window: int = DYNASTY_WINDOW) -> float:
    """A 0-100 dominance score for a team from its recent titles (weighted by
    prestige, decaying with age) plus a nudge from a current top-8 world
    rank. Pure chronicle + rank read."""
    score = 0.0
    for e in gs.chronicle:
        if e.team_id != tid or e.kind not in _TITLE_WEIGHT:
            continue
        age = gs.season - e.season
        if 0 <= age < window:
            score += _TITLE_WEIGHT[e.kind] * (1.0 - age / (window + 1))
    rank = gs.teams[tid].world_rank if tid in gs.teams else None
    rank_bonus = (9 - rank) * 0.5 if (rank is not None and rank <= 8) else 0.0
    return round(min(100.0, score * 8.0 + rank_bonus), 1)


def dynasty_label(index: float) -> str:
    if index >= 30.0:
        return "Dynasty"
    if index >= 15.0:
        return "Powerhouse"
    if index >= 6.0:
        return "Contender"
    return ""


def _leaders(gs: "GameState", n: int = 5) -> list[dict]:
    """This season's top tier-1 performers by rating (min 3 maps). Live
    season only — player_stats resets each offseason."""
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
            "player_id": pid, "handle": gs.players[pid].handle, "team": team,
            "rating": round(st.rating, 2), "kills": st.kills,
        })
    return out


def _handle_of(gs: "GameState", pid: str) -> str:
    """Display handle for a player id that survives retirement: the live roster
    first, then the persisted CareerStats handle (kept for retirees), else the
    raw id. Used by every record/summary reader so a retired leader never shows
    an internal id."""
    if pid in gs.players:
        return gs.players[pid].handle
    cs = gs.career_stats.get(pid)
    if cs and cs.handle:
        return cs.handle
    return pid


def all_time_records(gs: "GameState") -> dict:
    """The save's record book — most-titled team, most-decorated player,
    the career-kill leader — plus the current top dynasties. Pure chronicle
    + career_stats selection."""
    team_titles: dict[str, int] = {}
    team_champs: dict[str, int] = {}
    player_awards: dict[str, int] = {}
    player_mvps: dict[str, int] = {}
    for e in gs.chronicle:
        if e.kind in _TITLE_KINDS and e.team_id:
            team_titles[e.team_id] = team_titles.get(e.team_id, 0) + 1
            if e.kind == "champions_title":
                team_champs[e.team_id] = team_champs.get(e.team_id, 0) + 1
        elif e.kind == "award" and e.player_id:
            player_awards[e.player_id] = player_awards.get(e.player_id, 0) + 1
            if "MVP" in e.data.get("award", ""):
                player_mvps[e.player_id] = player_mvps.get(e.player_id, 0) + 1

    def _team_rec(counts: dict[str, int], label: str) -> dict | None:
        if not counts:
            return None
        tid = max(sorted(counts), key=lambda t: counts[t])
        return {
            "team_id": tid, "name": gs.teams[tid].name if tid in gs.teams else tid,
            "count": counts[tid], "label": label,
        }

    def _player_rec(counts: dict[str, int], label: str) -> dict | None:
        if not counts:
            return None
        pid = max(sorted(counts), key=lambda p: counts[p])
        return {
            "player_id": pid,
            "handle": _handle_of(gs, pid),  # survives retirement (award leaders too)
            "count": counts[pid], "label": label,
        }

    kills_rec = None
    if gs.career_stats:
        pid = max(sorted(gs.career_stats), key=lambda p: gs.career_stats[p].kills)
        cs = gs.career_stats[pid]
        if cs.kills > 0:
            kills_rec = {
                "player_id": pid, "handle": _handle_of(gs, pid),
                "count": cs.kills, "label": "Most career kills",
            }

    records = [
        _team_rec(team_titles, "Most titles"),
        _team_rec(team_champs, "Most world titles"),
        _player_rec(player_mvps, "Most MVP awards"),
        _player_rec(player_awards, "Most individual honours"),
        kills_rec,
    ]
    ranked = sorted(
        ((tid, dynasty_index(gs, tid)) for tid in gs.teams if gs.teams[tid].tier == 1),
        key=lambda kv: (-kv[1], kv[0]),
    )
    dynasties = [
        {
            "team_id": tid, "name": gs.teams[tid].name,
            "index": idx, "label": dynasty_label(idx),
        }
        for tid, idx in ranked[:3] if idx > 0
    ]
    return {"records": [r for r in records if r], "dynasties": dynasties}


def season_report(gs: "GameState", season: int | None = None) -> dict:
    """A deterministic structured summary of a season: champion + Masters,
    the award slate, final standings, statistical leaders, storylines, and
    the current top dynasties. Titles/awards read from the chronicle (any
    season); standings + leaders reflect live state, so a full leaders block
    only appears while the reported season is the current one."""
    season = gs.season if season is None else season

    def _title_team(kind: str) -> dict | None:
        e = next(
            (
                x for x in reversed(gs.chronicle)
                if x.kind == kind and x.season == season and x.team_id
            ),
            None,
        )
        if e is None:
            return None
        return {
            "team_id": e.team_id,
            "name": gs.teams[e.team_id].name if e.team_id in gs.teams else e.team_id,
        }

    awards: list[dict] = []
    seen: set[str] = set()
    for a in gs.awards:
        if a.season == season and a.award not in seen:
            awards.append({
                "award": a.award, "handle": a.handle,
                "team": a.team_name, "value": a.value,
            })
            seen.add(a.award)
    for e in gs.chronicle:
        if e.kind == "award" and e.season == season and e.data.get("award") not in seen:
            name = e.data.get("award", "Award")
            awards.append({
                "award": name, "handle": e.text.split(" wins", 1)[0],
                "team": "", "value": e.data.get("value", ""),
            })
            seen.add(name)

    standings: dict[str, list] = {}
    leaders: list[dict] = []
    if season == gs.season:
        for region in sorted(gs.regions()):
            standings[region] = [
                {
                    "team_id": tid, "name": gs.teams[tid].name,
                    "wins": gs.standings[tid].wins, "losses": gs.standings[tid].losses,
                    "diff": gs.standings[tid].diff,
                }
                for tid in gs.standings_order(region, tier=1)
            ]
        leaders = _leaders(gs)

    return {
        "season": season,
        "champion": _title_team("champions_title"),
        "masters_champion": _title_team("masters_title"),
        "awards": awards,
        "standings": standings,
        "leaders": leaders,
        "storylines": narrative.season_storylines(gs, season),
        "dynasties": all_time_records(gs)["dynasties"],
    }


def career_arc(gs: "GameState", pid: str) -> list[dict]:
    """A player's career as a per-season timeline from the chronicle — their
    debut, awards, milestones, and moves grouped by season, newest first.
    Pure chronicle read (team titles carry a team_id not a player_id, so they
    live on the team timeline, not here)."""
    by_season: dict[int, list[dict]] = {}
    for e in gs.chronicle:
        if e.player_id != pid:
            continue
        by_season.setdefault(e.season, []).append({"kind": e.kind, "text": e.text})
    return [
        {"season": s, "events": by_season[s]}
        for s in sorted(by_season, reverse=True)
    ]


def parity(gs: "GameState") -> dict:
    """Competitive parity of the save from the world-title record: how many
    distinct teams have won, and the most-titled team's share (higher
    distinct / lower share = more open competition)."""
    champs = [
        e.team_id for e in gs.chronicle
        if e.kind == "champions_title" and e.team_id
    ]
    if not champs:
        return {"titles": 0, "distinct_champions": 0, "top_share": 0.0}
    counts: dict[str, int] = {}
    for tid in champs:
        counts[tid] = counts.get(tid, 0) + 1
    return {
        "titles": len(champs),
        "distinct_champions": len(counts),
        "top_share": round(max(counts.values()) / len(champs), 2),
    }


def playtest_summary(gs: "GameState") -> dict:
    """A multi-season summary of a played save — the artifact a headless
    playtest / world-model pipeline consumes. All chronicle + career_stats,
    so it survives the per-season stat reset: title timelines, the award
    slate over time, meta eras, parity, the record book, and the most
    decorated career arcs."""

    def _title_line(kind: str) -> list[dict]:
        return [
            {
                "season": e.season,
                "team": gs.teams[e.team_id].name if e.team_id in gs.teams else e.team_id,
            }
            for e in sorted(
                (x for x in gs.chronicle if x.kind == kind and x.team_id),
                key=lambda x: x.season,
            )
        ]

    awards_tl = [
        {
            "season": e.season, "award": e.data.get("award", "Award"),
            "handle": e.text.split(" wins", 1)[0],
        }
        for e in sorted(
            (x for x in gs.chronicle if x.kind == "award"),
            key=lambda x: (x.season, x.data.get("award", "")),
        )
    ]

    honours: dict[str, int] = {}
    for e in gs.chronicle:
        if e.kind == "award" and e.player_id:
            honours[e.player_id] = honours.get(e.player_id, 0) + 1
    top_arcs = []
    for pid in sorted(honours, key=lambda p: (-honours[p], p))[:5]:
        cs = gs.career_stats.get(pid)
        top_arcs.append({
            "player_id": pid,
            "handle": _handle_of(gs, pid),
            "honours": honours[pid],
            "career_kills": cs.kills if cs else None,
            "seasons": cs.seasons if cs else None,
        })

    meta_eras = [
        {"season": e.season, "text": e.text}
        for e in sorted(
            (x for x in gs.chronicle if x.kind == "meta_shift" and not x.team_id),
            key=lambda x: x.season,
        )
    ]
    recs = all_time_records(gs)
    champions_tl = _title_line("champions_title")
    return {
        # Completed seasons = those already crowned. The --playtest loop
        # advances into season N+1 after the Nth offseason, so gs.season
        # overcounts by one; the champions timeline is the true tally.
        "seasons_played": len(champions_tl),
        "champions_timeline": champions_tl,
        "masters_timeline": _title_line("masters_title"),
        "award_timeline": awards_tl,
        "meta_eras": meta_eras,
        "parity": parity(gs),
        "dynasties": recs["dynasties"],
        "records": recs["records"],
        "top_career_arcs": top_arcs,
    }


def _recent_form_score(gs: "GameState", tid: str, n: int = 5) -> float:
    """Win fraction over the team's last `n` played fixtures (0.5 when none)."""
    games = sorted(
        (
            f for f in gs.fixtures
            if f.played and f.winner_id is not None and tid in (f.team_a, f.team_b)
        ),
        key=lambda f: (f.week, f.id),
    )[-n:]
    if not games:
        return 0.5
    return sum(1 for f in games if f.winner_id == tid) / len(games)


def power_rankings(gs: "GameState", tier: int = 1) -> list[dict]:
    """A pundit-style GLOBAL team ranking (across regions) blending record,
    recent form, and round differential — distinct from the per-region
    table and from world_rank. Each row carries its movement vs world_rank
    (positive = the form book rates them higher than their standing). Pure
    read of standings + fixtures, deterministic."""
    scored = []
    for t in gs.teams.values():
        if t.tier != tier:
            continue
        rec = gs.standings.get(t.id)
        wins = rec.wins if rec else 0
        diff = rec.diff if rec else 0
        form = _recent_form_score(gs, t.id)
        score = wins * 3.0 + diff * 0.15 + form * 6.0
        scored.append((t.id, round(score, 2)))
    scored.sort(key=lambda x: (-x[1], x[0]))
    out = []
    for i, (tid, score) in enumerate(scored):
        wr = gs.teams[tid].world_rank
        out.append({
            "rank": i + 1,
            "team_id": tid,
            "name": gs.teams[tid].name,
            "region": str(gs.teams[tid].region),
            "score": score,
            "world_rank": wr,
            "movement": (wr - (i + 1)) if wr else None,
        })
    return out


def award_races(gs: "GameState", top: int = 3) -> dict:
    """Mid-season leaderboards for the season awards, from the live
    player_stats (min 3 maps). Lets a manager see who's in contention (and
    chase a sponsor/board objective). Pure read; Most Improved needs the
    season-start CA baseline and is omitted before it exists."""
    from esports_sim.manager import development

    t1 = {pid for t in gs.teams.values() if t.tier == 1 for pid in t.player_ids}
    elig = [
        (pid, st) for pid, st in gs.player_stats.items()
        if st.maps >= 3 and pid in t1 and pid in gs.players
    ]

    def team_of(pid: str) -> str:
        return next((t.name for t in gs.teams.values() if pid in t.player_ids), "")

    def board(key, label, fmt):
        ranked = sorted(elig, key=lambda kv: (-key(kv[1]), kv[0]))[:top]
        return [
            {"player_id": pid, "handle": gs.players[pid].handle,
             "team": team_of(pid), "value": fmt(st)}
            for pid, st in ranked if key(st) > 0
        ]

    races = {
        "Season MVP": board(lambda s: s.rating, "rating", lambda s: f"{s.rating:.2f}"),
        "Top Fragger": board(lambda s: s.kills, "kills", lambda s: f"{s.kills}"),
        "Opening King": board(
            lambda s: s.first_kills, "opening kills", lambda s: f"{s.first_kills}"
        ),
        "Clutch Merchant": board(
            lambda s: s.clutches, "clutches", lambda s: f"{s.clutches}"
        ),
    }
    if gs.season_start_ca:
        risers = [
            (pid, development.overall(gs.players[pid]) - gs.season_start_ca[pid])
            for pid, _ in elig
            if pid in gs.season_start_ca
        ]
        risers.sort(key=lambda kv: (-kv[1], kv[0]))
        races["Most Improved"] = [
            {"player_id": pid, "handle": gs.players[pid].handle,
             "team": team_of(pid), "value": f"+{d:.0f} CA"}
            for pid, d in risers[:top] if d > 0
        ]
    return {k: v for k, v in races.items() if v}


def on_this_day(gs: "GameState", n: int = 3) -> list[dict]:
    """Living-history callbacks: the standout chronicle landmark from each of
    a few seasons ago (1/2/3/5), newest lookback first. A dry 'remember
    when' for the dashboard, straight from the chronicle."""
    out = []
    for back in (1, 2, 3, 5):
        s = gs.season - back
        if s < 1:
            continue
        cands = [e for e in gs.chronicle if e.season == s and e.importance >= 60.0]
        if not cands:
            continue
        top = max(cands, key=lambda e: (e.importance, e.id))
        out.append({"seasons_ago": back, "season": s, "text": top.text})
        if len(out) >= n:
            break
    return out
