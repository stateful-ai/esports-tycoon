"""Public league tables cover Challengers without changing policy observations."""

import json

from esports_sim.manager.agent_play import AgentWorld, league_view
from esports_sim.manager.decision_env import OBSERVATION_VERSION
from esports_sim.manager.state import GameState, TeamRecord
from esports_sim.schemas import Team


def _two_tier_state() -> GameState:
    # Intentionally reverse insertion and record order. EMEA has only tier two.
    specs = [
        ("t2_z", "americas", 2, 0, 0),
        ("t2_a", "americas", 2, 0, 0),
        ("t2_only", "emea", 2, 1, 4),
        ("t1_z", "americas", 1, 1, 8),
        ("t1_a", "americas", 1, 2, 2),
    ]
    return GameState(
        seed=941, user_team_id="t2_z", human_team_ids=["t2_z", "t1_a"],
        teams={tid: Team(id=tid, name=tid, tag=tid, region=region, tier=tier)
               for tid, region, tier, _, _ in specs},
        standings={tid: TeamRecord(wins=wins, rounds_won=diff)
                   for tid, _, _, wins, diff in reversed(specs)},
    )


def test_league_tables_keep_tiers_separate_and_legacy_regions_exact(game_data):
    gs = _two_tier_state()
    world = AgentWorld(gs, game_data)
    view = world.league()
    assert [(t["tier"], t["region"], t["competition"]) for t in view["tables"]] == [
        (1, "americas", "regional"),
        (2, "americas", "challengers"),
        (2, "emea", "challengers"),
    ]
    assert [[r["team_id"] for r in t["rows"]] for t in view["tables"]] == [
        ["t1_a", "t1_z"], ["t2_a", "t2_z"], ["t2_only"],
    ]
    assert view["regions"] == {"americas": [
        {"position": 1, "team_id": "t1_a", "team_name": "t1_a",
         "wins": 2, "losses": 0, "round_diff": 2, "human": True},
        {"position": 2, "team_id": "t1_z", "team_name": "t1_z",
         "wins": 1, "losses": 0, "round_diff": 8, "human": False},
    ]}
    rows = [r for t in view["tables"] for r in t["rows"]]
    assert {r["team_id"] for r in rows if r["human"]} == {"t2_z", "t1_a"}
    assert all(set(r) == {"position", "team_id", "team_name", "wins", "losses",
                          "round_diff", "human"} for r in rows)
    assert view["tables"][1]["rows"][0]["human"] is False  # AI rival exposed
    for table in view["tables"]:
        assert [r["position"] for r in table["rows"]] == list(range(1, len(table["rows"]) + 1))


def test_league_tables_are_pure_and_independent_of_mapping_insertion():
    gs = _two_tier_state()
    gs.set_acting("t1_a")
    before = gs.model_dump_json()
    expected = json.dumps(league_view(gs))
    assert json.dumps(league_view(gs)) == expected
    assert gs.model_dump_json() == before
    assert gs.acting_team_id == "t1_a"
    reversed_state = gs.model_copy(deep=True)
    reversed_state.teams = dict(reversed(list(reversed_state.teams.items())))
    reversed_state.standings = dict(reversed(list(reversed_state.standings.items())))
    reversed_state.human_team_ids.reverse()
    assert json.dumps(league_view(reversed_state)) == expected
    assert OBSERVATION_VERSION == 8


def test_explicit_challengers_agent_seat_finds_own_competition(game_data):
    probe = AgentWorld.create(game_data, seed=941, n_teams=1)
    tid = next(t for t in sorted(probe.gs.teams) if probe.gs.teams[t].tier == 2)
    world = AgentWorld.create(game_data, seed=941, team_ids=[tid])
    before = world.gs.model_dump_json()
    table = next(t for t in world.league()["tables"]
                 if any(r["team_id"] == tid for r in t["rows"]))
    assert table["tier"] == 2 and table["competition"] == "challengers"
    assert any(r["human"] and r["team_id"] == tid for r in table["rows"])
    assert any(not r["human"] for r in table["rows"])
    assert world.gs.model_dump_json() == before
