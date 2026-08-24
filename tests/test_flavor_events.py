"""Regression coverage for choice-gated campaign flavor events."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from esports_sim.manager import flavor_events, new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv, InvalidManagerAction
from esports_sim.manager.state import SCHEMA_VERSION, GameState
from esports_sim.rng.tree import RngTree
import esports_sim.web.server as server_mod


@pytest.fixture()
def campaign(game_data):
    return new_campaign(game_data, seed=123)


def _pending(campaign) -> object:
    tid = campaign.user_team_id
    event = flavor_events._build_event(
        campaign,
        tid,
        RngTree(campaign.seed).derive("test", "flavor", campaign.week, tid),
    )
    campaign.flavor_events_by[tid] = event
    return event


def test_pending_event_hides_outcomes_and_resolves_deterministically(campaign) -> None:
    event = _pending(campaign)
    wire = flavor_events.to_api(event)
    assert set(wire) == {
        "id", "season", "week", "team_id", "player_id", "type_id",
        "title", "prompt", "choices",
    }
    assert wire["choices"]
    assert all(set(choice) == {"id", "label"} for choice in wire["choices"])
    assert "outcomes" not in json.dumps(wire)
    assert "effects" not in json.dumps(wire)

    choice_id = event.choices[0].id
    before = campaign.model_copy(deep=True)
    _pending(before)
    ok, text, effects = flavor_events.resolve(campaign, campaign.user_team_id, choice_id)
    ok2, text2, effects2 = flavor_events.resolve(before, before.user_team_id, choice_id)
    assert ok and ok2
    assert text == text2
    assert effects == effects2
    assert campaign.flavor_events_by == {}
    assert event.type_id in campaign.flavor_event_recent_by[campaign.user_team_id]


def test_pending_event_blocks_headless_advance_until_resolved(campaign, game_data) -> None:
    event = _pending(campaign)
    env = HeadlessManagerEnv(campaign, game_data)
    legal = env.observe()["legal_actions"]
    assert legal["advance"]["enabled"] is False
    assert legal["resolve_flavor"]["enabled"] is True
    with pytest.raises(InvalidManagerAction, match="flavor"):
        env.step({"kind": "advance", "params": {}})

    result = env.step({
        "kind": "resolve_flavor",
        "params": {"event_id": event.id, "choice_id": event.choices[0].id},
    })
    assert not result.advanced
    assert campaign.user_team_id not in campaign.flavor_events_by


def test_web_state_hides_outcomes_and_advance_requires_resolution(campaign, game_data, monkeypatch) -> None:
    event = _pending(campaign)
    monkeypatch.setattr(server_mod.llm_flavor, "enqueue", lambda *_args: None)
    game = server_mod._Game(game_data, "FLAVORTEST", gs=campaign)
    server_mod._ctx.set(server_mod._ReqCtx(game, campaign.user_team_id))

    view = server_mod.state()["flavor_event"]
    assert view is not None and view["id"] == event.id
    assert "outcomes" not in json.dumps(view)
    assert "effects" not in json.dumps(view)
    # The refusal is player-facing: it must name a screen they can open, and
    # must not leak "flavor event", which is our word for what a player
    # experiences as a decision. A synthetic player hit this message and could
    # not act on it -- it named a section the UI had already deleted.
    with pytest.raises(HTTPException, match="Needs You") as refusal:
        server_mod.advance()
    assert refusal.value.status_code == 409
    assert "flavor" not in str(refusal.value.detail).lower()

    result = server_mod.resolve_flavor_event(server_mod.FlavorEventChoiceBody(
        event_id=event.id, choice_id=event.choices[0].id,
    ))
    assert result["ok"] is True
    assert server_mod.state()["flavor_event"] is None


def test_flavor_fields_migrate_from_v17_and_round_trip(campaign, tmp_path) -> None:
    event = _pending(campaign)
    path = tmp_path / "flavor.json"
    campaign.save(path)
    loaded = GameState.load(path)
    assert loaded.flavor_events_by[campaign.user_team_id].id == event.id

    old = json.loads(campaign.model_dump_json())
    old["schema_version"] = 17
    old.pop("flavor_events_by")
    old.pop("flavor_event_recent_by")
    old_path = tmp_path / "v17.json"
    old_path.write_text(json.dumps(old), encoding="utf-8")
    migrated = GameState.load(old_path)
    assert migrated.schema_version == SCHEMA_VERSION
    assert migrated.flavor_events_by == {}
    assert migrated.flavor_event_recent_by == {}


def test_same_seed_and_same_choices_keep_flavor_state_identical(game_data) -> None:
    a = new_campaign(game_data, seed=987)
    b = new_campaign(game_data, seed=987)
    for gs in (a, b):
        pending = flavor_events.pending_for(gs)
        if pending is not None:
            ok, _text, _effects = flavor_events.resolve(
                gs, gs.user_team_id, pending.choices[1].id
            )
            assert ok
    assert a.model_dump_json() == b.model_dump_json()
