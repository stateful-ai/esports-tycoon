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


def test_all_time_records_keeps_a_retired_kill_leader():
    # Codex review: a retired player is removed from gs.players, but their
    # lifetime record must survive in the record book via the stored handle.
    gs = GameState(seed=1, season=6, week=1, user_team_id="a",
                   teams={"a": _team("a")}, players={})  # nobody active
    gs.career_stats["ghost"] = CareerStats(
        handle="Ghost", maps=200, kills=4200, deaths=3000, seasons=8
    )
    gs.season = 6
    rec = analytics.all_time_records(gs)
    by = {r["label"]: r for r in rec["records"]}
    assert by["Most career kills"]["count"] == 4200
    assert by["Most career kills"]["handle"] == "Ghost"  # not the raw id
    assert by["Most career kills"]["player_id"] == "ghost"


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
    assert pt["seasons_played"] == 2  # two seasons crowned (season 3 in progress)
    assert [c["season"] for c in pt["champions_timeline"]] == [1, 2]
    assert len(pt["award_timeline"]) == 2
    assert pt["top_career_arcs"][0]["player_id"] == "p1"
    assert pt["top_career_arcs"][0]["honours"] == 2
    assert pt["parity"]["distinct_champions"] == 2
    assert analytics.playtest_summary(gs) == analytics.playtest_summary(gs)


# ---------------------------------------------------------------------------
# Pass-8 readers: power rankings + award races


def test_power_rankings_orders_and_movement():
    teams = {"a": _team("a", 3), "b": _team("b", 1)}  # world_rank a=3, b=1
    gs = GameState(seed=1, season=1, week=5, user_team_id="a", teams=teams, fixtures=[],
                   standings={"a": TeamRecord(wins=8, losses=1),
                              "b": TeamRecord(wins=2, losses=7)})
    pr = analytics.power_rankings(gs)
    assert [r["team_id"] for r in pr] == ["a", "b"]
    assert pr[0]["rank"] == 1 and pr[0]["movement"] == 2  # 1st in form, world #3


def test_award_races_leaderboards():
    teams = {"nxs": _team("nxs")}
    teams["nxs"].player_ids = ["a", "b"]
    gs = GameState(seed=1, season=1, week=5, user_team_id="nxs", teams=teams,
                   players={"a": _player("a"), "b": _player("b")},
                   player_stats={
                       "a": PlayerSeasonStats(maps=5, rating_sum=6.0, kills=100,
                                              first_kills=30, clutches=4),
                       "b": PlayerSeasonStats(maps=5, rating_sum=5.0, kills=120,
                                              first_kills=10, clutches=1),
                   })
    races = analytics.award_races(gs)
    assert races["Season MVP"][0]["player_id"] == "a"    # 1.20 > 1.00
    assert races["Top Fragger"][0]["player_id"] == "b"   # 120 > 100
    assert races["Opening King"][0]["player_id"] == "a"
    assert races["Clutch Merchant"][0]["player_id"] == "a"


# ---------------------------------------------------------------------------
# Pass-9: on_this_day living-history callbacks


def test_on_this_day_pulls_landmarks_from_past_seasons():
    gs = GameState(seed=1, season=5, week=1, user_team_id="a",
                   teams={"a": _team("a")}, players={})
    _title(gs, 4, "champions_title", "a")   # 1 season ago
    _title(gs, 2, "regional_title", "a")    # 3 seasons ago (importance 70 >= 60)
    gs.season = 5
    otd = analytics.on_this_day(gs)
    ago = {o["seasons_ago"] for o in otd}
    assert 1 in ago and 3 in ago
    first = next(o for o in otd if o["seasons_ago"] == 1)
    assert first["season"] == 4 and "champions_title" in first["text"]


def test_on_this_day_empty_without_landmarks():
    gs = GameState(seed=1, season=2, week=1, user_team_id="a",
                   teams={"a": _team("a")}, players={})
    assert analytics.on_this_day(gs) == []


def test_objective_status_champions_goal_survives_the_regional_final():
    # Codex review: a Champions goal must stay live through the playoffs — the
    # regional final only settles regional goals, Champions resolves later.
    teams, standings = _league(8)
    final = Fixture(id="s2t0final", week=13, stage="final", tier=1,
                    team_a="t0", team_b="t1", maps=["ascent"], played=True,
                    winner_id="t0")
    gs = GameState(seed=1, season=2, week=14, user_team_id="t0", phase="playoffs",
                   teams=teams, standings=standings, fixtures=[final])
    assert career.objective_status(gs, "t0", "win_split")["state"] == "achieved"
    # win_champions is NOT missed just because the regional final is done...
    assert career.objective_status(gs, "t0", "win_champions")["state"] != "missed"
    # ...but IS once the Champions final is played without t0 lifting it.
    gs.fixtures.append(Fixture(id="s2champ", week=16, stage="champ_final", tier=1,
                               team_a="t2", team_b="t3", maps=["ascent"],
                               played=True, winner_id="t2"))
    assert career.objective_status(gs, "t0", "win_champions")["state"] == "missed"


def test_objective_status_field_youth_matches_payout_rule():
    # Codex review: field_youth resolves the moment a sub-21 is on the ACTIVE
    # roster (sponsors._eval_objective), no maps required. The status reader
    # must not show 'at_risk' for a squad that already satisfies the payout.
    teams = {"a": _team("a")}
    teams["a"].player_ids = ["kid"]
    young = Player(id="kid", handle="Kid", age=19, role=Role.DUELIST,
                   playstyle=Playstyle.ENTRY, attributes={"aim_precision": 70})
    gs = GameState(seed=1, season=2, week=3, user_team_id="a", phase="regular",
                   teams=teams, players={"kid": young},
                   standings={"a": TeamRecord(wins=3, losses=1)})
    assert gs.player_stats == {}  # nobody has played
    assert career.objective_status(gs, "a", "field_youth")["state"] == "on_track"
    # Age the youngster out -> the objective is now at risk.
    gs.players["kid"].age = 25
    assert career.objective_status(gs, "a", "field_youth")["state"] == "at_risk"


def test_objective_status_top_half_missed_after_the_table_locks():
    # Codex review: once the regular season ends the table can't move, so a
    # side below the cut has already missed top_half — matching the offseason
    # _goal_met verdict. During the season it stays merely at_risk.
    teams, standings = _league(8)  # t0 best ... t7 worst
    gs = GameState(seed=1, season=2, week=13, user_team_id="t0", phase="regular",
                   teams=teams, standings=standings, fixtures=[])
    assert career.objective_status(gs, "t6", "top_half")["state"] == "at_risk"
    gs.phase = "playoffs"  # regular season over -> table locked
    assert career.objective_status(gs, "t6", "top_half")["state"] == "missed"
    # A top-half side is unaffected.
    assert career.objective_status(gs, "t1", "top_half")["state"] in (
        "on_track", "achieved",
    )


def test_objective_status_make_playoffs_missed_when_semis_are_seeded():
    # Codex review: make_playoffs is decided by the SEMIFINAL seeding (see
    # _goal_met), so a non-semifinalist has missed the cut the moment the semis
    # exist — no need to wait for the regional finals to be played.
    teams, standings = _league(8)
    semis = [
        Fixture(id="s2semi0", week=12, stage="semi", tier=1, team_a="t0",
                team_b="t3", maps=["ascent"]),
        Fixture(id="s2semi1", week=12, stage="semi", tier=1, team_a="t1",
                team_b="t2", maps=["ascent"]),
    ]
    gs = GameState(seed=1, season=2, week=12, user_team_id="t0", phase="playoffs",
                   teams=teams, standings=standings, fixtures=semis)
    # A semifinalist has achieved it; a team left out of the bracket has missed
    # it now, before any final is played.
    assert career.objective_status(gs, "t0", "make_playoffs")["state"] == "achieved"
    assert career.objective_status(gs, "t6", "make_playoffs")["state"] == "missed"


def test_objective_status_make_playoffs_live_before_bracket():
    # Still in the regular season (no semi fixtures) -> never prematurely missed.
    teams, standings = _league(8)
    gs = GameState(seed=1, season=2, week=5, user_team_id="t0", phase="regular",
                   teams=teams, standings=standings, fixtures=[])
    assert career.objective_status(gs, "t6", "make_playoffs")["state"] != "missed"


def test_objective_status_masters_goal_missed_only_when_seeds_exclude_you():
    teams, standings = _league(8)
    final = Fixture(id="s2f", week=13, stage="final", tier=1, team_a="t0",
                    team_b="t1", maps=["ascent"], played=True, winner_id="t0")
    gs = GameState(seed=1, season=2, week=14, user_team_id="t0", phase="playoffs",
                   teams=teams, standings=standings, fixtures=[final])
    # Seeds not set yet -> not missed.
    assert career.objective_status(gs, "t0", "make_masters")["state"] != "missed"
    gs.masters_seeds = ["t1", "t2"]  # t0 left out
    assert career.objective_status(gs, "t0", "make_masters")["state"] == "missed"
