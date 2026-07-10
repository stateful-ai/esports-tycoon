"""Season & all-time analytics (manager/analytics.py) — deterministic
readers over a hand-built GameState (chronicle + career_stats + standings).
No engine, no registry: the readers only touch fields already on GameState.
"""

from __future__ import annotations

from esports_sim.manager import analytics, career, chronicle
from esports_sim.manager.state import (
    CareerStats,
    ChampionRecord,
    Fixture,
    GameState,
    PlayerSeasonStats,
    TeamRecord,
)
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role


def _team(tid: str, wr: int | None = None) -> Team:
    return Team(id=tid, name=tid.title(), tag=tid.upper()[:3], tier=1, world_rank=wr)


def _player(pid: str) -> Player:
    return Player(id=pid, handle=pid.title(), age=24, role=Role.DUELIST,
                  playstyle=Playstyle.ENTRY, attributes={"aim_precision": 80})


def _title(gs: GameState, season: int, kind: str, tid: str) -> None:
    gs.season = season
    chronicle.record(gs, kind, f"{tid} wins {kind}.", team_id=tid,
                     data={"title": f"S{season} {kind}"})


def _award(gs: GameState, season: int, pid: str, award: str) -> None:
    gs.season = season
    chronicle.record(gs, "award", f"{gs.players[pid].handle} wins {award} (1.2).",
                     player_id=pid, data={"award": award, "value": "1.2 rating"})


def test_dynasty_index_weights_recent_titles_over_none():
    gs = GameState(seed=1, season=5, week=1, user_team_id="a",
                   teams={"a": _team("a", 1), "b": _team("b")}, players={})
    _title(gs, 5, "champions_title", "a")
    gs.season = 5
    idx_a = analytics.dynasty_index(gs, "a")
    idx_b = analytics.dynasty_index(gs, "b")
    assert idx_a > idx_b == 0.0
    assert analytics.dynasty_label(idx_a) == "Dynasty"  # 5*8 + rank(1) bonus


def test_dynasty_index_decays_with_age_and_drops_old_titles():
    gs = GameState(seed=1, season=10, week=1, user_team_id="a",
                   teams={"a": _team("a")}, players={})
    _title(gs, 2, "champions_title", "a")  # 8 seasons ago, outside the window
    gs.season = 10
    assert analytics.dynasty_index(gs, "a") == 0.0


def test_all_time_records_counts_titles_awards_kills():
    gs = GameState(seed=1, season=6, week=1, user_team_id="a",
                   teams={"a": _team("a"), "b": _team("b")},
                   players={"p1": _player("p1")})
    _title(gs, 3, "regional_title", "a")
    _title(gs, 4, "champions_title", "a")
    _title(gs, 5, "regional_title", "b")
    _award(gs, 4, "p1", "Season MVP")
    _award(gs, 5, "p1", "Clutch Merchant")
    gs.career_stats["p1"] = CareerStats(maps=100, kills=2000, deaths=1500, seasons=5)
    gs.season = 6
    rec = analytics.all_time_records(gs)
    by = {r["label"]: r for r in rec["records"]}
    assert by["Most titles"]["team_id"] == "a" and by["Most titles"]["count"] == 2
    assert by["Most world titles"]["team_id"] == "a"
    assert by["Most MVP awards"]["player_id"] == "p1" and by["Most MVP awards"]["count"] == 1
    assert by["Most individual honours"]["count"] == 2
    assert by["Most career kills"]["count"] == 2000


def test_all_time_records_empty_on_a_blank_save():
    gs = GameState(seed=1, season=1, week=1, user_team_id="a",
                   teams={"a": _team("a")}, players={})
    rec = analytics.all_time_records(gs)
    assert rec["records"] == [] and rec["dynasties"] == []


def test_season_report_is_grounded_and_structured():
    teams = {"a": _team("a"), "b": _team("b")}
    teams["a"].player_ids = ["p1"]
    gs = GameState(
        seed=1, season=4, week=14, user_team_id="a", teams=teams,
        players={"p1": _player("p1")},
        standings={"a": TeamRecord(wins=10, losses=4), "b": TeamRecord(wins=6, losses=8)},
        player_stats={"p1": PlayerSeasonStats(maps=14, rating_sum=17.5, kills=250,
                                              first_kills=40)},
        champions=[ChampionRecord(season=4, team_id="a", team_name="A")],
    )
    _title(gs, 4, "champions_title", "a")
    _award(gs, 4, "p1", "Season MVP")
    gs.season = 4
    rep = analytics.season_report(gs)
    assert rep["season"] == 4
    assert rep["champion"]["team_id"] == "a"
    assert any(aw["award"] == "Season MVP" for aw in rep["awards"])
    assert rep["standings"], "current-season standings present"
    assert rep["leaders"] and rep["leaders"][0]["player_id"] == "p1"
    assert isinstance(rep["storylines"], list) and rep["storylines"]


def test_season_report_is_deterministic():
    teams = {"a": _team("a", 2), "b": _team("b", 1)}
    gs = GameState(seed=1, season=3, week=1, user_team_id="a", teams=teams, players={},
                   standings={"a": TeamRecord(wins=5, losses=2),
                              "b": TeamRecord(wins=6, losses=1)})
    _title(gs, 3, "regional_title", "a")
    gs.season = 3
    assert analytics.season_report(gs) == analytics.season_report(gs)


# ---------------------------------------------------------------------------
# career.objective_status — read-only in-season board/sponsor goal progress


def _league(n: int = 8):
    teams, standings = {}, {}
    for i in range(n):
        tid = f"t{i}"
        teams[tid] = Team(id=tid, name=tid, tag=f"T{i}", tier=1)
        standings[tid] = TeamRecord(wins=n - i, losses=i)  # t0 best -> t{n-1} worst
    return teams, standings


def test_objective_status_on_track_vs_at_risk_by_position():
    teams, standings = _league(8)
    gs = GameState(seed=1, season=2, week=5, user_team_id="t0", phase="regular",
                   teams=teams, standings=standings, fixtures=[])
    top = career.objective_status(gs, "t0", "make_playoffs")   # 1st
    assert top["state"] == "on_track" and "1st of 8" in top["detail"]
    low = career.objective_status(gs, "t6", "make_playoffs")   # 7th
    assert low["state"] == "at_risk"


def test_objective_status_achieved_and_missed_after_the_final():
    teams, standings = _league(8)
    final = Fixture(id="s2t0final", week=13, stage="final", tier=1,
                    team_a="t0", team_b="t1", maps=["ascent"], played=True,
                    winner_id="t1")
    gs = GameState(seed=1, season=2, week=14, user_team_id="t0", phase="playoffs",
                   teams=teams, standings=standings, fixtures=[final])
    assert career.objective_status(gs, "t1", "win_split")["state"] == "achieved"
    # t0 reached the final but lost it -> the split goal is now missed.
    assert career.objective_status(gs, "t0", "win_split")["state"] == "missed"


def test_objective_status_beat_top4_is_incremental():
    teams, standings = _league(8)
    gs = GameState(seed=1, season=2, week=5, user_team_id="t0", phase="regular",
                   teams=teams, standings=standings, fixtures=[])
    assert career.objective_status(gs, "t3", "beat_top4")["state"] == "in_progress"


# ---------------------------------------------------------------------------
# Pass-7 multi-season readers: career arc, parity, playtest summary


def test_career_arc_groups_by_season_newest_first():
    gs = GameState(seed=1, season=5, week=1, user_team_id="a",
                   teams={"a": _team("a")}, players={"p1": _player("p1")})
    gs.season = 2
    chronicle.record(gs, "debut", "P1 debuts.", player_id="p1")
    gs.season = 4
    chronicle.record(gs, "award", "P1 wins Season MVP (1.2).", player_id="p1",
                     data={"award": "Season MVP"})
    gs.season = 5
    arc = analytics.career_arc(gs, "p1")
    assert [y["season"] for y in arc] == [4, 2]  # newest first
    assert arc[0]["events"][0]["kind"] == "award"


def test_parity_counts_distinct_champions_and_top_share():
    gs = GameState(seed=1, season=4, week=1, user_team_id="a",
                   teams={"a": _team("a"), "b": _team("b")}, players={})
    _title(gs, 1, "champions_title", "a")
    _title(gs, 2, "champions_title", "a")
    _title(gs, 3, "champions_title", "b")
    gs.season = 4
    assert analytics.parity(gs) == {
        "titles": 3, "distinct_champions": 2, "top_share": round(2 / 3, 2),
    }


def test_playtest_summary_multiseason_shape_and_determinism():
    gs = GameState(seed=1, season=3, week=1, user_team_id="a",
                   teams={"a": _team("a"), "b": _team("b")},
                   players={"p1": _player("p1")})
    _title(gs, 1, "champions_title", "a")
    _title(gs, 2, "champions_title", "b")
    _award(gs, 1, "p1", "Season MVP")
    _award(gs, 2, "p1", "Clutch Merchant")
    gs.career_stats["p1"] = CareerStats(maps=30, kills=500, deaths=400, seasons=2)
    gs.season = 3
    pt = analytics.playtest_summary(gs)
    assert pt["seasons_played"] == 3
    assert [c["season"] for c in pt["champions_timeline"]] == [1, 2]
    assert len(pt["award_timeline"]) == 2
    assert pt["top_career_arcs"][0]["player_id"] == "p1"
    assert pt["top_career_arcs"][0]["honours"] == 2
    assert pt["parity"]["distinct_champions"] == 2
    assert analytics.playtest_summary(gs) == analytics.playtest_summary(gs)
