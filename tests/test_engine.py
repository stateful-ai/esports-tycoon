"""Match-engine invariants beyond determinism."""

from __future__ import annotations

import pytest

from esports_sim.registry import GameData
from esports_sim.sim import simulate_match_result
from esports_sim.sim.stats import compute_match_stats


@pytest.mark.parametrize("map_id", ["haven", "ascent", "bind"])
def test_match_completes_on_every_map(game_data: GameData, map_id: str) -> None:
    res = simulate_match_result(
        game_data, "team_nexus", "team_vanguard", map_id, seed=3
    )
    assert res.winner_id in ("team_nexus", "team_vanguard")
    hi, lo = max(res.score_a, res.score_b), min(res.score_a, res.score_b)
    assert hi >= 13
    assert hi > lo


def test_score_matches_round_events(game_data: GameData) -> None:
    res = simulate_match_result(game_data, "team_nexus", "team_vanguard", "haven", 5)
    stats = compute_match_stats(res.events)
    a = sum(1 for r in stats.rounds if r.winner_id == "team_nexus")
    b = sum(1 for r in stats.rounds if r.winner_id == "team_vanguard")
    assert (a, b) == (res.score_a, res.score_b)
    assert [r.round_num for r in stats.rounds] == list(range(1, len(stats.rounds) + 1))


def test_no_player_dies_twice_in_a_round(game_data: GameData) -> None:
    res = simulate_match_result(game_data, "team_nexus", "team_vanguard", "haven", 9)
    dead: set[str] = set()
    for e in res.events:
        if e.type == "round.start":
            dead = set()
        elif e.type == "round.kill":
            assert e.victim_id not in dead, f"{e.victim_id} died twice"
            assert e.killer_id not in dead, f"{e.killer_id} killed while dead"
            dead.add(e.victim_id)


def test_kills_and_buys_are_plausible(game_data: GameData) -> None:
    res = simulate_match_result(game_data, "team_nexus", "team_vanguard", "haven", 11)
    stats = compute_match_stats(res.events)
    n_rounds = len(stats.rounds)
    kills = sum(line.kills for line in stats.lines.values())
    # Some rounds end on the spike, but a round should average >=3 kills.
    assert kills >= 3 * n_rounds
    for e in res.events:
        if e.type == "round.buy":
            assert e.spent >= 0


def test_stronger_roster_wins_majority(game_data: GameData) -> None:
    """The management promise: better players must actually matter.

    Tested with a synthetic +12-across-the-board clone of Nexus rather
    than the two authored rosters: Nexus and Vanguard are deliberately
    close in quality (a bo1 between them is ~55-65%, upsets intended),
    which makes them a noisy probe for attribute monotonicity.
    """
    boosted = game_data.model_copy(deep=True)
    for pid in boosted.teams["team_vanguard"].player_ids:
        p = boosted.players[pid]
        p.attributes = {
            k: min(99.0, v + 12.0) for k, v in p.attributes.items()
        }
    wins = 0
    n = 20
    for seed in range(n):
        res = simulate_match_result(
            boosted, "team_nexus", "team_vanguard", "haven", seed
        )
        wins += res.winner_id == "team_vanguard"
    assert wins > n * 0.65, f"clearly better roster only won {wins}/{n} matches"
