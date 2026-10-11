"""Badge reporting uses measured bounded deltas and honest save provenance."""
import json
import numpy as np
import pytest
from esports_sim.manager import badges, development_path, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.schemas.badges import BADGES
from esports_sim.web import server

@pytest.mark.parametrize("bid,clutch,composure,expected", [
    ("clutch_master", 98.5, 98.8, {"clutch_factor": 0.5, "composure": 0.2}),
    ("choker", 2.0, 1.5, {"clutch_factor": -1.0, "composure": -0.5}),
])
def test_earn_report_matches_clamped_changes_and_decay(game_data, bid, clutch, composure, expected):
    gs = new_campaign(game_data, seed=777)
    tid = gs.user_team_id
    p = gs.roster(tid)[0]
    p.attributes.update(clutch_factor=clutch, composure=composure)
    development_path.begin_week(gs)
    before = dict(p.attributes)
    badges._earn(gs, tid, p, bid)
    report = development_path.report_view(p)
    assert report["sources"]["badge_gains"]["skills"] == expected
    assert report["sources"]["event_gains"]["skills"] == {}
    assert report["badge_events"][0]["skills"] == expected
    assert report["badge_events"][0]["overall_gain"] == round(sum(expected.values()) / len(p.attributes), 2)
    view = server._badge_views(p)[0]
    assert f'{abs(expected["clutch_factor"]):g}' in view["impact"]
    assert not badges.roll(gs, np.random.default_rng(0), tid, p, bid, 1)
    assert len(p.development_progress.latest.badge_events) == 1
    gs.season += BADGES[bid]["decay_seasons"]
    development_path.begin_week(gs)
    badges.decay(gs)
    event = development_path.report_view(p)["badge_events"][0]
    assert event["action"] == "lost"
    assert event["skills"] == {a: -d for a, d in expected.items()}
    assert p.attributes == before


def test_no_badge_and_legacy_save_do_not_invent_provenance(game_data, tmp_path):
    gs = new_campaign(game_data, seed=2026)
    p = gs.roster(gs.user_team_id)[0]
    development_path.begin_week(gs)
    assert development_path.report_view(p)["badge_tracking"] is True
    assert development_path.report_view(p)["badge_events"] == []
    data = gs.model_dump(mode="json")
    data["schema_version"] = 36
    for player in data["players"].values():
        latest = player["development_progress"]["latest"]
        for field in ("badge_tracking", "badge_events", "badge_gains"):
            latest.pop(field)
    path = tmp_path / "old.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == 37
    assert development_path.report_view(loaded.players[p.id])["badge_tracking"] is False
    loaded.save(path)
    assert GameState.load(path).model_dump_json() == loaded.model_dump_json()


def test_report_reads_badge_provenance_without_mutation(game_data):
    gs = new_campaign(game_data, seed=31337)
    p = gs.roster(gs.user_team_id)[0]
    development_path.begin_week(gs)
    badges._earn(gs, gs.user_team_id, p, "clutch_master")
    before = gs.model_dump_json()
    result = server._weekly_development_report(gs, gs.user_team_id, gs.season, gs.week)
    row = next(r for r in result["players"] if r["id"] == p.id)
    assert row["attribution"]["badge_events"][0]["name"] == "Clutch Master"
    assert gs.model_dump_json() == before

