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


@pytest.mark.parametrize("action", [
    {"kind": "set_tactics", "params": {"pace": "fast"}},
    {"kind": "set_tactics", "params": {"pace": None}},
    {"kind": "set_lineup", "params": {"player_ids": None}},
    {"kind": "set_lineup", "params": {"player_ids": [{}, {}, {}, {}, {}]}},
    {"kind": "negotiate_offer", "params": {"salary": [], "weeks": 10}},
    {"kind": "advance", "params": []},
    None,
])
def test_malformed_direct_actions_reject_without_mutation(game_data, action):
    world = AgentWorld.create(game_data, seed=920, n_teams=2)
    before = world.gs.model_dump_json()
    with pytest.raises(InvalidManagerAction):
        world.act(world.team_ids[0], action)
    assert world.gs.model_dump_json() == before
    assert not world.ready
    assert not world.last_tick
    assert world.tick_seq == 0


@pytest.mark.parametrize("accept", ["false", "true", 0, 1, None, [], {}])
def test_direct_transfer_requires_boolean_and_retains_live_offer(game_data, accept):
    from esports_sim.manager.state import TransferOffer

    world = AgentWorld.create(game_data, seed=921, n_teams=2)
    seller, buyer = world.team_ids
    pid = world.gs.teams[seller].player_ids[0]
    world.gs.transfer_offers.append(TransferOffer(
        player_id=pid, from_team=seller, to_team=buyer,
        fee=10_000, expires_week=world.gs.week + 2,
    ))
    before = world.gs.model_dump_json()
    with pytest.raises(InvalidManagerAction, match="JSON boolean"):
        world.act(seller, {"kind": "transfer_offer", "params": {
            "player_id": pid, "to_team": buyer, "accept": accept,
        }})
    assert world.gs.model_dump_json() == before


@pytest.mark.parametrize("kind", ["sponsor_respond", "sponsor_demand_respond"])
@pytest.mark.parametrize("accept", ["false", "true", 0, 1, None, [], {}])
def test_direct_sponsor_decisions_reject_nonboolean_before_domain_mutation(game_data, monkeypatch, kind, accept):
    from esports_sim.manager import sponsors

    world = AgentWorld.create(game_data, seed=924, n_teams=2)
    called = []
    def domain_action(*args):
        called.append(args)
        world.gs.teams[world.team_ids[0]].balance += 1
        return True, "resolved"
    monkeypatch.setattr(sponsors, "sign_market_offer", domain_action)
    monkeypatch.setattr(sponsors, "decline_market_offer", domain_action)
    monkeypatch.setattr(sponsors, "respond_demand", domain_action)
    before = world.gs.model_dump_json()
    with pytest.raises(InvalidManagerAction, match="JSON boolean"):
        world.act(world.team_ids[0], {"kind": kind, "params": {"accept": accept}})
    assert not called
    assert world.gs.model_dump_json() == before


@pytest.mark.parametrize("kind", ["sponsor_respond", "sponsor_demand_respond"])
def test_sponsor_missing_accept_keeps_decline_default(kind):
    from esports_sim.manager.decision_env import validate_manager_action

    assert validate_manager_action({"kind": kind, "params": {}}) == (kind, {})
    for accept in (False, True):
        assert validate_manager_action({"kind": kind, "params": {"accept": accept}}) == (
            kind, {"accept": accept},
        )


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


@pytest.mark.parametrize("capture_events", [False, True])
def test_replays_retain_only_the_latest_resolved_week(game_data, monkeypatch, capture_events):
    from esports_sim.manager import agent_play
    from esports_sim.manager.campaign import WeekReport
    from esports_sim.schemas import Event

    world = AgentWorld.create(
        game_data, seed=911, n_teams=2, capture_events=capture_events,
    )
    a, b = world.team_ids
    for tid in (a, b):
        _clear_event_blockers(world, tid)
    tick_weeks = []

    def resolve_week(gs, gd, *, events_out):
        week = gs.week
        tick_weeks.append(week)
        report = WeekReport(season=gs.season, week=week, phase=gs.phase)
        # Reuse one fixture id and introduce another per week: both stale
        # keys and accumulated map logs must disappear. Week 3 has no match.
        if events_out is not None and week < 3:
            for fixture_id in ("shared_fixture", f"week_{week}_fixture"):
                events_out.setdefault(fixture_id, []).append([
                    Event(type="match.start", tick=week),
                ])
        gs.week += 1
        return report

    monkeypatch.setattr(agent_play, "advance_week", resolve_week)
    previous_replays = None if not capture_events else {}
    for week in range(1, 4):
        assert world.act(a, {"kind": "advance", "params": {}})["advanced"] is False
        assert world.event_logs == previous_replays
        assert world.act(a, {"kind": "advance", "params": {}})["advanced"] is False
        with pytest.raises(InvalidManagerAction):
            world.act(b, {"kind": "not_an_action", "params": {}})
        assert world.event_logs == previous_replays
        assert tick_weeks == list(range(1, week))

        assert world.act(b, {"kind": "advance", "params": {}})["advanced"] is True
        assert tick_weeks == list(range(1, week + 1))
        if capture_events:
            expected = (
                {fid: [[Event(type="match.start", tick=week)]] for fid in (
                    "shared_fixture", f"week_{week}_fixture",
                )}
                if week < 3 else {}
            )
            assert world.event_logs == expected
            previous_replays = {
                fid: [list(events) for events in maps]
                for fid, maps in world.event_logs.items()
            }
        else:
            assert world.event_logs is None


def test_rejected_ready_roster_keeps_previous_replays(game_data, monkeypatch):
    from esports_sim.manager import agent_play
    from esports_sim.schemas import Event

    world = AgentWorld.create(game_data, seed=911, n_teams=2, capture_events=True)
    a, b = world.team_ids
    for tid in (a, b):
        _clear_event_blockers(world, tid)
    previous_replays = {"previous_fixture": [[Event(type="match.start", tick=1)]]}
    world.event_logs.update(previous_replays)
    tick_calls = []

    def resolve_week(*args, **kwargs):
        tick_calls.append((args, kwargs))
        raise AssertionError("a rejected roster must not run the campaign tick")

    monkeypatch.setattr(agent_play, "advance_week", resolve_week)
    assert world.act(a, {"kind": "advance", "params": {}})["advanced"] is False
    # The waiting seat is blocked before voting.
    dropped_b = world.gs.teams[b].player_ids.pop()
    with pytest.raises(InvalidManagerAction):
        world.act(b, {"kind": "advance", "params": {}})
    assert world.event_logs == previous_replays
    world.gs.teams[b].player_ids.append(dropped_b)
    # A previously ready seat can become short while waiting. The final
    # vote must fail revalidation without discarding the last week's replay.
    world.gs.teams[a].player_ids.pop()
    with pytest.raises(InvalidManagerAction, match="re-ready once fixed"):
        world.act(b, {"kind": "advance", "params": {}})
    assert world.event_logs == previous_replays
    assert not tick_calls
    assert world.ready == {b}
    assert world.tick_seq == 0
    assert world.gs.week == 1


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
