"""Phase 0 of Legacy Mode: the career Chronicle — append-only history,
deterministic emission, milestone/debut bookkeeping, save migration."""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import chronicle, market
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import SCHEMA_VERSION, GameState
from esports_sim.registry import load_all


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=777)


def test_chronicle_deterministic(game_data):
    """Same seed, same ticks -> byte-identical chronicle."""
    a = new_campaign(game_data, seed=42)
    b = new_campaign(game_data, seed=42)
    for _ in range(3):
        advance_week(a, game_data)
        advance_week(b, game_data)
    assert [e.model_dump() for e in a.chronicle] == [
        e.model_dump() for e in b.chronicle
    ]


def test_market_moves_are_chronicled(campaign):
    gs = campaign
    fa = gs.free_agent_ids[0]
    ok, _ = market.sign_player(gs, gs.user_team_id, fa)
    assert ok
    signings = [e for e in gs.chronicle if e.kind == "signing"]
    assert signings and signings[-1].player_id == fa
    assert signings[-1].team_id == gs.user_team_id
    # The signing credits the human seat running the org.
    assert signings[-1].manager_id == f"mgr_{gs.user_team_id}"

    ok, _ = market.release_player(gs, gs.user_team_id, fa)
    assert ok
    releases = [e for e in gs.chronicle if e.kind == "release"]
    assert releases and releases[-1].player_id == fa


def test_record_dedups_same_fact_same_tick(campaign):
    gs = campaign
    e1 = chronicle.record(gs, "signing", "X sign Y.", team_id="t", player_id="p")
    e2 = chronicle.record(gs, "signing", "X sign Y.", team_id="t", player_id="p")
    assert e1 is not None and e2 is None
    assert sum(1 for e in gs.chronicle if e.text == "X sign Y.") == 1


def test_milestone_arms_then_fires_once(campaign):
    gs = campaign
    # First sight: everyone gets marked, nothing fires.
    assert chronicle.weekly_milestones(gs) == []
    p = gs.roster(gs.user_team_id)[0]
    # Push the player one full band up.
    for a in p.attributes:
        p.attributes[a] = min(99.0, p.attributes[a] + chronicle.MILESTONE_BAND)
    fired = chronicle.weekly_milestones(gs)
    assert len(fired) == 1
    owner, msg = fired[0]
    assert owner == gs.user_team_id
    assert "Milestone:" in msg and p.handle in msg
    assert "save" not in msg.lower()
    assert [e for e in gs.chronicle if e.kind == "milestone"]
    # Same state again: the band was celebrated, nothing re-fires.
    assert chronicle.weekly_milestones(gs) == []


def test_milestone_floor_suppresses_low_bands(campaign):
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    for a in p.attributes:
        p.attributes[a] = 30.0
    chronicle.weekly_milestones(gs)  # arm at the low band
    for a in p.attributes:
        p.attributes[a] = 36.0  # crosses a band, but under the floor
    assert chronicle.weekly_milestones(gs) == []


def test_debut_records_once_for_pending_only(campaign):
    gs = campaign
    rookie = gs.free_agent_ids[0]
    veteran = gs.roster(gs.user_team_id)[0].id
    chronicle.mark_debut_pending(gs, rookie)
    dressed = {gs.user_team_id: {rookie, veteran}}
    chronicle.record_debuts(gs, dressed)
    debuts = [e for e in gs.chronicle if e.kind == "debut"]
    assert [e.player_id for e in debuts] == [rookie]  # veteran never fires
    assert gs.debut_marks[rookie] == f"s{gs.season}w{gs.week}"
    chronicle.record_debuts(gs, dressed)  # replay: no duplicate
    assert len([e for e in gs.chronicle if e.kind == "debut"]) == 1


def test_full_season_chronicles_titles_awards_retirements(game_data):
    gs = new_campaign(game_data, seed=9)
    for _ in range(60):
        advance_week(gs, game_data)
        if gs.season >= 2:
            break
    assert gs.season >= 2, "campaign never reached season 2"
    kinds = {e.kind for e in gs.chronicle}
    for expected in (
        "regional_title",
        "masters_title",
        "champions_title",
        "challengers_title",
        "award",
    ):
        assert expected in kinds, f"missing {expected} in chronicle"
    # The Champions entry matches the champions record.
    champ = gs.champions[-1]
    entry = next(e for e in gs.chronicle if e.kind == "champions_title")
    assert entry.team_id == champ.team_id
    assert entry.season == champ.season


def test_save_roundtrip_and_v4_migration(tmp_path, campaign, game_data):
    gs = campaign
    advance_week(gs, game_data)
    path = tmp_path / "save.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert [e.model_dump() for e in loaded.chronicle] == [
        e.model_dump() for e in gs.chronicle
    ]
    assert loaded.dev_marks == gs.dev_marks

    # Fake a v4 save: strip the v5 fields, plant history records.
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("chronicle", "dev_marks", "debut_marks"):
        data.pop(key, None)
    data["schema_version"] = 4
    data["champions"] = [
        {"season": 1, "team_id": "team_nexus", "team_name": "Team Nexus"}
    ]
    data["awards"] = [
        {
            "season": 1,
            "award": "MVP",
            "player_id": "px",
            "handle": "Vortex",
            "team_name": "Team Nexus",
            "value": "1.31 rating",
        }
    ]
    data["retired"] = [
        {
            "season": 1,
            "handle": "OldGuard",
            "real_name": "",
            "age": 33,
            "team_name": "",
            "peak_note": "retired at 60 CA",
        }
    ]
    v4 = tmp_path / "v4.json"
    v4.write_text(json.dumps(data), encoding="utf-8")
    migrated = GameState.load(v4)
    assert migrated.schema_version == SCHEMA_VERSION
    kinds = [e.kind for e in migrated.chronicle]
    assert "champions_title" in kinds
    assert "award" in kinds
    assert "retirement" in kinds
    backfilled = next(e for e in migrated.chronicle if e.kind == "award")
    assert backfilled.week == 0  # marks a backfilled entry
    assert backfilled.player_id == "px"
