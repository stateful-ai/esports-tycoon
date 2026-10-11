"""Resolved-report result digests survive replacement of the season schedule."""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import agent_play, chronicle
from esports_sim.manager.agent_play import AgentWorld, seat_week_results
from esports_sim.manager.campaign import WeekReport
from esports_sim.manager.state import ChampionRecord, Fixture, MapResult


@pytest.mark.parametrize("rollover", [False, True])
def test_shared_tick_results_use_resolved_report_for_every_seat(
    game_data, monkeypatch, rollover,
):
    def run():
        world = AgentWorld.create(game_data, seed=928, n_teams=3)
        gs = world.gs
        a, b, idle = world.team_ids
        gs.week = 34 if rollover else 1
        gs.phase = "offseason" if rollover else "regular"
        season, week = gs.season, gs.week
        final = Fixture(
            id=f"s{season}_champions_final", week=week,
            team_a=a, team_b=b, played=True, winner_id=b,
            stage="champions_final", bracket="champions", best_of=3,
            results=[
                MapResult(map_id="ascent", seed=101, score_a=8, score_b=13, winner_id=b),
                MapResult(map_id="bind", seed=102, score_a=13, score_b=11, winner_id=a),
                MapResult(map_id="haven", seed=103, score_a=10, score_b=13, winner_id=b),
            ],
        )
        # A same-week played fixture outside this report must not be mistaken
        # for a result of the resolved tick (including after season reset).
        decoy = final.model_copy(update={"id": f"s{season + 1}_decoy"}, deep=True)
        gs.fixtures = [decoy]
        report = WeekReport(season=season, week=week, phase=gs.phase, fixtures=[final])

        def resolve(state, gd, *, events_out=None):
            assert state is gs and gd is game_data
            if rollover:
                chronicle.record(
                    state, "champions_title", "Champions won.", team_id=b,
                    data={"title": f"S{season} Champions"},
                )
                state.champions.append(ChampionRecord(
                    season=season, team_id=b, team_name=state.teams[b].name,
                ))
                state.season += 1
                state.week = 1
                state.phase = "regular"
                state.fixtures = [decoy.model_copy(deep=True)]
            else:
                state.week += 1
            return report

        monkeypatch.setattr(agent_play, "advance_week", resolve)
        # Both AgentWorld and HTTP advance use this exact shared builder.
        tick = agent_play.tick_shared_week(gs, game_data, set(world.team_ids))
        assert tick.report is report
        for tid, opponent, score, won, map_scores in (
            (a, b, [1, 2], False, [[8, 13], [13, 11], [10, 13]]),
            (b, a, [2, 1], True, [[13, 8], [11, 13], [13, 10]]),
        ):
            digest = tick.summaries[tid]
            assert (digest["season"], digest["week"]) == (season, week)
            assert digest["now_season"] == season + int(rollover)
            assert digest["now_week"] == (1 if rollover else week + 1)
            assert digest["season_rolled"] is rollover
            assert len(digest["results"]) == 1
            row = digest["results"][0]
            assert row["fixture_id"] == final.id
            assert row["stage"] == "champions_final"
            assert row["bracket"] == "champions" and row["best_of"] == 3
            assert row["opponent_id"] == opponent
            assert row["opponent_name"] == gs.teams[opponent].name
            assert row["score"] == score and row["won"] is won
            assert [m["map_id"] for m in row["maps"]] == ["ascent", "bind", "haven"]
            assert [m["score"] for m in row["maps"]] == map_scores
            assert [m["won"] for m in row["maps"]] == (
                [False, True, False] if tid == a else [True, False, True]
            )
            if rollover:
                assert digest["season_champion"]["team_id"] == b
                assert digest["season_champion"]["yours"] is (tid == b)
                assert agent_play.title_counts(gs, b)["champions"] == 1
        assert tick.summaries[idle]["results"] == []
        assert gs.fixtures[0].id == decoy.id
        before = gs.model_dump_json()
        # Read-only serialization must not add state or mutate the report.
        assert seat_week_results(gs, a, week, fixtures=[]) == []
        assert seat_week_results(gs, a, week)[0]["fixture_id"] == decoy.id
        assert seat_week_results(gs, a, week, fixtures=report.fixtures) == tick.summaries[a]["results"]
        assert gs.model_dump_json() == before
        assert report.fixtures[0].model_dump() == final.model_dump()
        return before, json.dumps(tick.summaries, sort_keys=True)

    assert run() == run()
