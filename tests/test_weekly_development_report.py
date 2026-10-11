"""Full week reports read only the attribution belonging to that report."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import new_campaign
from esports_sim.manager.development_path import report_view
from esports_sim.manager.state import DevSnap, GameState
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Role, Playstyle
from esports_sim.schemas.player import DevelopmentWeek
from esports_sim.web import server


def world():
    p = Player(id="p", handle="Recovery", role=Role.DUELIST, playstyle=Playstyle.ENTRY,
               attributes={"comms": 74.5, "aim": 74.5})
    gs = GameState(seed=1, season=1, week=3, user_team_id="nxs",
                   teams={"nxs": Team(id="nxs", name="Nexus", tag="NXS", player_ids=["p"])},
                   players={"p": p})
    p.development_progress.latest = DevelopmentWeek(
        season=1, week=2, focus="rest", intensity="normal", maps=1,
        match_gains={"comms": 0.04},
        factors=["Individual recovery: practice paused, match experience retained"],
    )
    return gs, p


def snap(season, week, ca):
    return DevSnap(season=season, week=week, ca=ca, confidence=50, form=50,
                   morale=50, followers=0)


def test_rest_report_reuses_measured_sources_with_unchanged_display_rating():
    gs, p = world()
    gs.dev_history[p.id] = [snap(1, 1, 74.5), snap(1, 2, 74.5)]
    before = gs.model_dump_json()
    report = server._weekly_development_report(gs, "nxs", 1, 2)
    row = report["players"][0]
    assert row["attribution"] == report_view(p)
    assert row["attribution"]["sources"]["match_gains"]["overall_gain"] == 0.02
    assert row["attribution"]["sources"]["practice_gains"]["skills"] == {}
    assert row["attribution"]["factors"] == [
        "Individual recovery: practice paused, match experience retained"]
    assert row["measured"] == {
        "overall_start": 74.5, "overall_current": 74.5, "overall_delta": 0.0}
    assert gs.model_dump_json() == before


@pytest.mark.parametrize("snaps", [[], [snap(1, 2, 74.5)],
    [snap(1, 0, 74.0), snap(1, 2, 74.5)], [snap(0, 1, 70), snap(1, 2, 74.5)]])
def test_sparse_tracking_never_invents_a_weekly_delta(snaps):
    gs, p = world()
    gs.dev_history[p.id] = snaps
    row = server._weekly_development_report(gs, "nxs", 1, 2)["players"][0]
    assert row["measured"] is None
    assert row["attribution"]["sources"]["match_gains"]["skills"] == {"comms": 0.04}


@pytest.mark.parametrize("season,week", [(1, 1), (1, 3), (2, 2)])
def test_report_excludes_latest_attribution_from_other_weeks_or_seasons(season, week):
    gs, p = world()
    gs.dev_history[p.id] = [snap(season, week - 1, 70), snap(season, week, 71)]
    assert server._weekly_development_report(gs, "nxs", season, week) == {
        "season": season, "week": week, "players": []}


def test_sparse_player_without_attribution_does_not_hide_other_players():
    gs, _ = world()
    gs.players["new"] = Player(id="new", handle="New", role=Role.DUELIST,
                               playstyle=Playstyle.ENTRY, attributes={"aim": 70})
    gs.teams["nxs"].player_ids.extend(["new", "missing"])
    assert [r["id"] for r in server._weekly_development_report(gs, "nxs", 1, 2)["players"]] == ["p"]
    assert server._weekly_development_report(gs, "missing", 1, 2)["players"] == []


def test_report_payload_keeps_resolved_membership_after_transactions_and_multiple_advances(
    game_data, monkeypatch, tmp_path,
):
    from esports_sim.web import review_history

    gs = new_campaign(game_data, seed=2038, user_team_id="team_nexus")
    gs.autosave_enabled = False
    game = server._Game(game_data, "WEEKDEV", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(server.llm_social, "enqueue", lambda *_a, **_k: None)
    try:
        first = server.advance()
        old_report = game.last_report
        first_development = first["development"]
        original = list(gs.teams[gs.user_team_id].player_ids)
        assert [r["id"] for r in first_development["players"]] == original
        # Releasing a resolved participant and acquiring a rival whose own
        # latest attribution has the same week must not rewrite provenance.
        rival = next(t for t in gs.teams.values() if t.id != gs.user_team_id and t.player_ids)
        newcomer = rival.player_ids.pop()
        released = gs.teams[gs.user_team_id].player_ids.pop()
        gs.teams[gs.user_team_id].player_ids.append(newcomer)
        gs.players.pop(released)
        assert (gs.players[newcomer].development_progress.latest.season,
                gs.players[newcomer].development_progress.latest.week) == (
                    first["season"], first["week"])
        reopened = server.last_week_report()["report"]["development"]
        assert reopened == first_development
        assert released in [r["id"] for r in reopened["players"]]
        assert newcomer not in [r["id"] for r in reopened["players"]]
        # Sim-ahead refreshes the presentation snapshot per tick, and its
        # response and /api/report agree on the last completed week.
        batch = server.sim_ahead_action(server.SimAheadBody(max_weeks=2))
        current = batch["report"]["development"]
        last = game.last_report
        assert (current["season"], current["week"]) == (last.season, last.week)
        assert [r["id"] for r in current["players"]] == gs.teams[gs.user_team_id].player_ids
        assert server.last_week_report()["report"]["development"] == current
        assert all((r["attribution"]["season"], r["attribution"]["week"]) ==
                   (last.season, last.week) for r in current["players"])
        assert server._report_view(old_report, gs, gs.user_team_id, current)["development"]["players"] == []
    finally:
        server._ctx.reset(token)
