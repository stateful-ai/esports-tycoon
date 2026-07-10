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
            "handle": gs.players[pid].handle if pid in gs.players else pid,
            "count": counts[pid], "label": label,
        }

    kills_rec = None
    if gs.career_stats:
        pid = max(sorted(gs.career_stats), key=lambda p: gs.career_stats[p].kills)
        cs = gs.career_stats[pid]
        if cs.kills > 0 and pid in gs.players:
            kills_rec = {
                "player_id": pid, "handle": gs.players[pid].handle,
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
