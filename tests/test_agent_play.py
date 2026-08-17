"""Multi-agent shared worlds (manager/agent_play.py): the ready-vote week
barrier, per-seat tick digests, and the championship-objective serializers."""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import chronicle, flavor_events, media_events
from esports_sim.manager.agent_play import (
    AgentWorld,
    InvalidManagerAction,
    advance_blockers,
    league_view,
    objective_view,
    sync_view,
    titles_timeline,
)
from esports_sim.manager.state import ChampionRecord


def _clear_event_blockers(world: AgentWorld, team_id: str) -> None:
    """Resolve any pending flavor/media decision the cheap way (no full
    observation build) so a scripted seat can vote."""
    pending = flavor_events.pending_for(world.gs, team_id)
    if pending is not None:
        world.act(team_id, {
            "kind": "resolve_flavor",
            "params": {"event_id": pending.id, "choice_id": pending.choices[0].id},
        })
    pending = media_events.pending_for(world.gs, team_id)
    if pending is not None:
        world.act(team_id, {
            "kind": "resolve_media",
            "params": {"event_id": pending.id, "choice_id": pending.choices[0].id},
        })


def test_create_seats_every_team_and_validates_picks(game_data):
    world = AgentWorld.create(game_data, seed=910, n_teams=3)
    assert len(world.team_ids) == 3
    gs = world.gs
    assert sorted(gs.human_team_ids) == world.team_ids
    assert gs.user_team_id == world.team_ids[0]
    for tid in world.team_ids:
        assert gs.manager_for(tid) is not None

    with pytest.raises(ValueError):
        AgentWorld.create(game_data, seed=910)  # neither picker
    with pytest.raises(ValueError):
        AgentWorld.create(
            game_data, seed=910, team_ids=["x"], n_teams=1
        )  # both pickers
    with pytest.raises(ValueError):
        AgentWorld.create(game_data, seed=910, team_ids=["team_not_real"])
    first = world.team_ids[0]
    with pytest.raises(ValueError):
        AgentWorld.create(game_data, seed=910, team_ids=[first, first])
    with pytest.raises(ValueError):
        AgentWorld.create(game_data, seed=910, n_teams=0)


def test_observation_is_json_safe_and_carries_sync_and_objective(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    a, b = world.team_ids
    obs = world.observe(a)
    json.dumps(obs, sort_keys=True)
    assert obs["team_id"] == a
    assert obs["legal_actions"]["advance"]["enabled"]
    assert obs["sync"]["you_ready"] is False
    assert obs["sync"]["waiting_on"] == [a, b]
    assert [s["team_id"] for s in obs["sync"]["seats"]] == [a, b]
    assert obs["sync"]["last_tick"] is None
    assert obs["objective"]["titles"]["total"] == 0
    assert obs["objective"]["regular_season"]["position"] >= 1
    assert [r["team_id"] for r in obs["objective"]["rival_seats"]] == [b]


def test_advance_is_a_vote_and_other_actions_resolve_immediately(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    a, b = world.team_ids

    r = world.act(a, {"kind": "advance", "params": {}})
    assert r["advanced"] is False
    assert r["waiting_on"] == [b]
    assert world.gs.week == 1  # the world did not move

    # The voted seat's flag holds while the other seat keeps deciding.
    step = world.act(b, {"kind": "set_training", "params": {"focus": "mental"}})
    assert step["ok"] and step["advanced"] is False
    assert world.gs.week == 1
    sync = sync_view(world.gs, world.ready, b, tick_seq=world.tick_seq)
    assert sync["you_ready"] is False
    assert sync["waiting_on"] == [b]

    # Re-voting is idempotent, not an error.
    again = world.act(a, {"kind": "advance", "params": {}})
    assert again["advanced"] is False and again["waiting_on"] == [b]


def test_illegal_actions_raise_with_the_reason(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    a = world.team_ids[0]
    with pytest.raises(InvalidManagerAction):
        world.act(a, {"kind": "not_an_action", "params": {}})
    with pytest.raises(InvalidManagerAction, match="not a free agent"):
        world.act(a, {"kind": "sign", "params": {"player_id": "ghost"}})
    with pytest.raises(KeyError):
        world.act("team_not_seated", {"kind": "advance", "params": {}})


def test_short_roster_blocks_that_seat_only(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    a, b = world.team_ids
    team = world.gs.teams[b]
    dropped = sorted(team.player_ids)[0]
    team.player_ids.remove(dropped)

    assert world.act(a, {"kind": "advance", "params": {}})["advanced"] is False
    assert advance_blockers(world.gs, b) != ""
    with pytest.raises(InvalidManagerAction):
        world.act(b, {"kind": "advance", "params": {}})
    assert world.gs.week == 1


def test_last_vote_ticks_once_and_every_seat_gets_a_digest(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    a, b = world.team_ids
    for tid in (a, b):
        _clear_event_blockers(world, tid)
    assert world.act(a, {"kind": "advance", "params": {}})["advanced"] is False
    r = world.act(b, {"kind": "advance", "params": {}})

    assert r["advanced"] is True
    assert world.gs.week == 2
    assert world.tick_seq == 1
    assert world.ready == set()
    assert r["tick"] is world.last_tick[b]
    for tid in (a, b):
        digest = world.last_tick[tid]
        assert digest["season"] == 1 and digest["week"] == 1
        assert digest["now_week"] == 2
        assert isinstance(digest["reward"], float)
        assert isinstance(digest["reward_components"], dict)
        assert digest["position"]["position"] >= 1
        for row in digest["results"]:
            assert row["opponent_id"] != tid
            assert isinstance(row["won"], bool)
            assert len(row["score"]) == 2
    # The next observation surfaces the digest and a reset vote board.
    obs = world.observe(a)
    assert obs["sync"]["last_tick"] == world.last_tick[a]
    assert obs["sync"]["you_ready"] is False
    assert obs["sync"]["tick_seq"] == 1


def test_objective_counts_titles_and_sees_rival_trophy_cases(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    gs = world.gs
    a, b = world.team_ids
    chronicle.record(
        gs, "champions_title", f"{gs.teams[a].name} win Champions.",
        team_id=a, data={"title": "S1 Champions"},
    )
    chronicle.record(
        gs, "regional_title", f"{gs.teams[a].name} win the split.", team_id=a
    )
    chronicle.record(
        gs, "masters_title", f"{gs.teams[b].name} win Masters.", team_id=b
    )
    # Champions is ALSO tracked on the dedicated record list; counting must
    # not double it when both sources know the same title.
    gs.champions.append(
        ChampionRecord(season=gs.season, team_id=a, team_name=gs.teams[a].name)
    )

    obj = objective_view(gs, a)
    assert obj["titles"] == {
        "champions": 1, "masters": 0, "regional": 1, "challengers": 0,
        "total": 2,
    }
    assert [t["kind"] for t in obj["titles_won"]] == [
        "champions_title", "regional_title",
    ]
    rival = obj["rival_seats"][0]
    assert rival["team_id"] == b
    assert rival["titles"]["masters"] == 1
    assert rival["head_to_head_this_season"] == {"wins": 0, "losses": 0}
    assert obj["champions_history"] == [
        {"season": 1, "team_id": a, "team_name": gs.teams[a].name}
    ]

    # A champion known only to the record list (pre-chronicle save) still
    # counts and still appears on the timeline.
    gs.champions.append(
        ChampionRecord(season=2, team_id=b, team_name=gs.teams[b].name)
    )
    assert objective_view(gs, b)["titles"]["champions"] == 1
    rows = titles_timeline(gs)
    assert {(r["season"], r["kind"], r["team_id"]) for r in rows} == {
        (1, "champions_title", a),
        (1, "regional_title", a),
        (1, "masters_title", b),
        (2, "champions_title", b),
    }


def test_league_view_marks_agent_seats_in_the_tables(game_data):
    world = AgentWorld.create(game_data, seed=911, n_teams=2)
    gs = world.gs
    a, b = world.team_ids
    view = league_view(gs)
    json.dumps(view, sort_keys=True)
    assert [s["team_id"] for s in view["seats"]] == [a, b]
    rows = [r for region in view["regions"].values() for r in region]
    humans = {r["team_id"] for r in rows if r["human"]}
    assert humans == {a, b}
    assert all(r["position"] >= 1 for r in rows)


def test_two_identical_runs_are_byte_identical(game_data):
    """The multiplayer determinism contract: seed + the same global action
    order (across all seats) reproduces the world exactly."""

    def run() -> str:
        world = AgentWorld.create(game_data, seed=912, n_teams=2)
        a, b = world.team_ids
        for _ in range(2):
            world.act(a, {"kind": "set_training", "params": {"focus": "mental"}})
            world.act(b, {"kind": "set_tactics", "params": {"pace": 61.0}})
            for tid in (a, b):
                _clear_event_blockers(world, tid)
            world.act(b, {"kind": "advance", "params": {}})
            r = world.act(a, {"kind": "advance", "params": {}})
            assert r["advanced"] is True
        return world.gs.model_dump_json()

    assert run() == run()
