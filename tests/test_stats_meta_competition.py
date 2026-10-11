"""Authored competition-meta contracts. UNRUN under the explicit user waiver."""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import advance_week, meta, new_campaign
from esports_sim.manager.campaign import _record_map_meta
from esports_sim.manager.state import (
    Fixture, GameState, MapMetaStats, MapResult, PatchChange, PatchNote,
    SCHEMA_VERSION, TeamSeasonStats,
)
from esports_sim.schemas.team import TeamTactics
import esports_sim.web.server as server


def record(gs, tier, mid, aids, aggression, pace):
    stats = SimpleNamespace(map_id=mid, lines={
        f"p{i}": SimpleNamespace(agent_id=aid) for i, aid in enumerate(aids)
    })
    # Both sides, deliberately different dials: mean must include each once.
    tactics = {
        "side_b": TeamTactics(aggression=aggression + 10, pace=pace + 10),
        "side_a": TeamTactics(aggression=aggression, pace=pace),
    }
    _record_map_meta(gs, stats, tactics, league_tier=tier)


@pytest.fixture
def sample(game_data):
    gs = new_campaign(game_data, seed=2026)
    aids = sorted(game_data.agents)[:2]
    record(gs, 1, "lotus", [aids[0]] * 10, 20, 30)
    record(gs, 2, "lotus", [aids[1]] * 10, 70, 80)
    record(gs, 2, "bind", [aids[1]] * 10, 60, 70)
    return gs, game_data, aids


def test_tier_isolation_both_sides_maps_and_public_read_purity(sample):
    gs, gd, aids = sample
    before = gs.model_dump_json()
    one = meta.meta_report(gs, gd.agents, league_tier=1)
    two = meta.meta_report(gs, gd.agents, league_tier=2)
    assert [(r["agent_id"], r["maps"], r["pick_rate"]) for r in one["tier_list"]] == [(aids[0], 10, 100.0)]
    assert [(r["agent_id"], r["maps"], r["pick_rate"]) for r in two["tier_list"]] == [(aids[1], 20, 100.0)]
    assert [r["map_id"] for r in one["map_trends"]] == ["lotus"]
    assert [r["map_id"] for r in two["map_trends"]] == ["bind", "lotus"]
    lotus = two["map_trends"][1]
    assert lotus["team_maps"] == lotus["recorded_team_maps"] == 2
    assert {r["key"]: r["average"] for r in lotus["tactics"]}["aggression"] == 75.0
    assert {r["key"]: r["average"] for r in lotus["tactics"]}["pace"] == 85.0
    assert gs.model_dump_json() == before
    # The view consumes captured records, not current tactics or player homes.
    for team in gs.teams.values():
        team.tactics = TeamTactics(aggression=0, pace=0)
        team.player_ids = []
    assert meta.meta_report(gs, gd.agents, league_tier=2) == two


def test_global_record_and_patch_contract_unchanged(sample):
    gs, gd, aids = sample
    global_lotus = gs.map_meta_stats["lotus"]
    assert global_lotus.team_maps == 4
    assert global_lotus.agent_picks == {aids[0]: 10, aids[1]: 10}
    assert global_lotus.tactic_sums["aggression"] == 200.0
    gs.agent_patches = [PatchChange(agent_id=aids[0], ability_id="x", field="cost", delta=-50)]
    gs.patch_history = [PatchNote(season=1, week=3, version="1.03", lines=["global"])]
    before = gs.model_dump_json()
    reports = [meta.meta_report(gs, gd.agents, league_tier=t) for t in (None, 1, 2)]
    assert set(reports[0]) == {"latest_patch", "patched_agents", "tier_list", "map_trends"}
    assert all(r["latest_patch"] == reports[0]["latest_patch"] for r in reports)
    assert all(r["patched_agents"] == reports[0]["patched_agents"] for r in reports)
    assert reports[1]["patch_scope"] == reports[2]["patch_scope"] == "global"
    assert gs.model_dump_json() == before


def test_legacy_public_counts_no_fabricated_agents_or_tactics(sample, tmp_path):
    gs, gd, aids = sample
    tids = sorted(gs.teams)[:2]
    gs.fixtures = [Fixture(id="old", week=1, tier=2, team_a=tids[0], team_b=tids[1], played=True,
        results=[MapResult(map_id="lotus", seed=1, score_a=13, score_b=8, winner_id=tids[0])])]
    data = gs.model_dump(mode="json")
    data["schema_version"] = 37
    data.pop("map_meta_stats_by_tier")
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == SCHEMA_VERSION
    assert loaded.map_meta_stats_by_tier == {}
    assert loaded.map_meta_stats == gs.map_meta_stats
    report = meta.meta_report(loaded, gd.agents, league_tier=2)
    assert report["tier_list"] == []
    assert report["sample"] == {"completed_team_maps": 2, "recorded_team_maps": 0, "legacy_team_maps": 2}
    row = report["map_trends"][0]
    assert row["team_maps"] == 2
    assert row["agents"] == row["tactics"] == []
    assert row["site_focus"] is None
    record(loaded, 2, "lotus", [aids[1]] * 10, 60, 70)
    loaded.fixtures.append(Fixture(id="new", week=2, tier=2, team_a=tids[0], team_b=tids[1], played=True,
        results=[MapResult(map_id="lotus", seed=2, score_a=13, score_b=8, winner_id=tids[0])]))
    report = meta.meta_report(loaded, gd.agents, league_tier=2)
    assert report["sample"] == {"completed_team_maps": 4, "recorded_team_maps": 2, "legacy_team_maps": 2}
    assert report["map_trends"][0]["agents"][0]["pick_rate"] == 100.0
    assert {r["key"]: r["average"] for r in report["map_trends"][0]["tactics"]}["aggression"] == 65.0


def test_deterministic_record_order_and_save_roundtrip(game_data, tmp_path):
    first = new_campaign(game_data, seed=2026)
    second = new_campaign(game_data, seed=2026)
    aids = sorted(game_data.agents)[:2]
    for gs in (first, second):
        record(gs, 2, "lotus", aids, 60, 70)
    assert first.model_dump_json() == second.model_dump_json()
    path = tmp_path / "scoped.json"
    first.save(path)
    loaded = GameState.load(path)
    assert loaded.model_dump_json() == first.model_dump_json()
    assert meta.meta_report(loaded, game_data.agents, league_tier=2) == meta.meta_report(first, game_data.agents, league_tier=2)


def test_actual_completed_fixture_path_records_each_competition(game_data):
    # Authored UNRUN simulation regression: verifies the call site threads f.tier,
    # rather than merely testing the pure accumulator with hand-picked tiers.
    first = new_campaign(game_data, seed=2026)
    second = new_campaign(game_data, seed=2026)
    for gs in (first, second):
        advance_week(gs, game_data)
        for tier in (1, 2):
            expected = {}
            for fixture in gs.fixtures:
                if fixture.played and fixture.tier == tier:
                    for result in fixture.results:
                        expected[result.map_id] = expected.get(result.map_id, 0) + 2
            assert expected, "fixture regression must exercise both competitions"
            recorded = gs.map_meta_stats_by_tier[str(tier)]
            assert {mid: trend.team_maps for mid, trend in recorded.items()} == expected
            for trend in recorded.values():
                assert sum(trend.agent_picks.values()) == 5 * trend.team_maps
            report = meta.meta_report(gs, game_data.agents, league_tier=tier)
            assert report["sample"]["legacy_team_maps"] == 0
        for mid, global_trend in gs.map_meta_stats.items():
            assert global_trend.team_maps == sum(
                by_map.get(mid, MapMetaStats()).team_maps
                for by_map in gs.map_meta_stats_by_tier.values()
            )
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.parametrize("value", [0, -1, 3, 100])
def test_invalid_integer_tier_matches_stats_fallback(sample, value):
    gs, gd, _ = sample
    assert meta.meta_report(gs, gd.agents, league_tier=value) == meta.meta_report(gs, gd.agents, league_tier=1)


def test_no_sample_and_endpoint_team_scope(game_data):
    gs = new_campaign(game_data, seed=2026)
    tids = sorted(gs.teams)[:4]
    for i, tid in enumerate(tids):
        gs.teams[tid].tier = 1 if i < 2 else 2
        gs.team_stats[tid] = TeamSeasonStats(maps=2)
    game = server._Game(game_data, "TESTC", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    try:
        before = gs.model_dump_json()
        for tier, expected in ((1, tids[:2]), (2, tids[2:])):
            report = server.meta_view(tier)
            assert report["league_tier"] == tier
            assert report["tier_list"] == report["map_trends"] == []
            assert report["sample"] == {"completed_team_maps": 0, "recorded_team_maps": 0, "legacy_team_maps": 0}
            assert {r["team_id"] for r in server.stats_view(league_tier=tier)["teams"]} == set(expected)
        assert server.meta_view() == server.meta_view(1)
        assert server.meta_view(42) == server.meta_view(1)
        assert gs.model_dump_json() == before
    finally:
        server._ctx.reset(token)


def test_stats_frontend_actual_queries_and_selection():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node unavailable")
    subprocess.run([node, "tests/stats_meta_competition_check.cjs"], check=True, capture_output=True)
