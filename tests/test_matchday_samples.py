"""Public season samples in the pre-match briefing, without simulation."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.state import GameState, PlayerSeasonStats
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role
from esports_sim.web import server


def _world(tier: int) -> GameState:
    players = {
        pid: Player(
            id=pid, handle=pid.title(), age=24, role=Role.DUELIST,
            playstyle=Playstyle.ENTRY, attributes={"aim_precision": 99},
        )
        for pid in ("hollowdash", "blitzsnap", "bench", "tie_a", "tie_b", "zero", "departed")
    }
    return GameState(
        seed=2071, season=1, week=3, user_team_id="azure",
        teams={
            "azure": Team(
                id="azure", name="Azure Vanta", tag="AZV", tier=tier,
                player_ids=["zero", "tie_b", "hollowdash", "bench", "tie_a", "missing"],
                lineup_ids=["hollowdash", "tie_a", "tie_b", "zero", "missing"],
            ),
            "patagonia": Team(
                id="patagonia", name="Patagonia Sur", tag="PTS", tier=tier,
                player_ids=["blitzsnap"],
            ),
        },
        players=players,
        player_stats={
            "hollowdash": PlayerSeasonStats(maps=2, rating_sum=2.34, kills=34, deaths=26),
            "blitzsnap": PlayerSeasonStats(maps=2, rating_sum=2.06, kills=21, deaths=18),
            "bench": PlayerSeasonStats(maps=1, rating_sum=1.5),
            "tie_b": PlayerSeasonStats(maps=3, rating_sum=3.3),
            "tie_a": PlayerSeasonStats(maps=3, rating_sum=3.3),
            "zero": PlayerSeasonStats(),
            "departed": PlayerSeasonStats(maps=8, rating_sum=16),
            "missing": PlayerSeasonStats(maps=8, rating_sum=16),
        },
    )


@pytest.mark.parametrize("tier", [1, 2])
def test_briefing_uses_positive_public_samples_and_current_roster(tier):
    gs = _world(tier)
    before = gs.model_dump_json()
    rows = server._danger_men(gs, "azure", n=10)
    # Preserve sampled bench players, exclude departed/missing/zero-map rows,
    # and break equal ratings by stable player ID rather than roster order.
    assert [row["player_id"] for row in rows] == ["bench", "hollowdash", "tie_a", "tie_b"]
    assert server._danger_men(gs, "azure") == rows[:3]
    for row in rows:
        stats_row = server._season_stat_row(gs, row["player_id"], gs.player_stats[row["player_id"]], 0)
        assert (row["rating"], row["maps"]) == (stats_row["rating"], stats_row["maps"])
        assert set(row) == {"player_id", "handle", "role", "rating", "maps", "sample_note"}
        assert row["sample_note"] == ("Early sample" if row["maps"] < 3 else None)
    assert server._danger_men(gs, "unknown") == []
    assert gs.model_dump_json() == before


@pytest.mark.parametrize("tier", [1, 2])
@pytest.mark.parametrize("scout_progress", [0.0, 0.5])
def test_matchday_shows_both_sides_two_map_samples_without_unlocking_tactics(
    game_data, monkeypatch, tier, scout_progress,
):
    gs = _world(tier)
    gs.scout_progress["patagonia"] = scout_progress
    gs.teams["patagonia"].tactics.aggression = 80
    board = {"id": "next", "team_a": "azure", "team_b": "patagonia", "tier": tier}
    monkeypatch.setattr(server, "_next_fixture_board", lambda state: (board, "patagonia"))
    monkeypatch.setattr(server, "_team_recent_form", lambda state, tid: [])
    token = server._ctx.set(server._ReqCtx(server._Game(game_data, "SAMPLE", gs=gs), "azure"))
    try:
        before = gs.model_dump_json()
        data = server.matchday()
        assert gs.model_dump_json() == before
    finally:
        server._ctx.reset(token)
    own = next(row for row in data["you"]["danger_men"] if row["player_id"] == "hollowdash")
    rival = data["them"]["danger_men"][0]
    assert (own["rating"], own["maps"], own["sample_note"]) == (1.17, 2, "Early sample")
    assert (rival["player_id"], rival["rating"], rival["maps"], rival["sample_note"]) == (
        "blitzsnap", 1.03, 2, "Early sample",
    )
    assert data["them"]["scouted"] == (scout_progress >= 0.5)
    if scout_progress < 0.5:
        assert data["them"]["identity"] is None
        assert data["them"]["tendencies"] == []
    else:
        assert data["them"]["identity"] == "Aggressive"
        assert data["them"]["tendencies"]


@pytest.mark.parametrize("tier", [1, 2])
def test_empty_or_zero_map_season_has_no_briefing_sample(tier):
    gs = _world(tier)
    gs.player_stats = {"hollowdash": PlayerSeasonStats(), "blitzsnap": PlayerSeasonStats()}
    assert server._danger_men(gs, "azure") == []
    assert server._danger_men(gs, "patagonia") == []
    gs.player_stats.clear()
    assert server._danger_men(gs, "azure") == []
    assert server._danger_men(gs, "patagonia") == []
