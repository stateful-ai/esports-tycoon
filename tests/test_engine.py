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


def test_aim_is_the_primary_individual_duel_separator(game_data: GameData) -> None:
    """Aim precision must outweigh movement in a like-for-like raw duel.

    Movement still matters substantially to routing, peeking, and getting
    into cover; this keeps the roster promise clear that an aim upgrade is
    the larger direct mechanical upgrade once the duel has begun.
    """
    from esports_sim.sim import constants as C
    from esports_sim.sim.engine import _MatchSim

    sim = _MatchSim(game_data, "team_nexus", "team_vanguard", "haven", 1)
    pid = sorted(game_data.teams["team_nexus"].player_ids)[0]
    player = game_data.players[pid]
    args = (False, False, False, 0, 5, 5)
    base = sim._duel_score(pid, *args)

    old_precision = player.attributes["aim_precision"]
    player.attributes["aim_precision"] = old_precision + 10.0
    precise = sim._duel_score(pid, *args)
    player.attributes["aim_precision"] = old_precision

    old_movement = player.attributes["movement"]
    player.attributes["movement"] = old_movement + 10.0
    mobile = sim._duel_score(pid, *args)
    player.attributes["movement"] = old_movement

    assert precise - base == pytest.approx(10.0 * C.DUEL_AIM_PRECISION_WEIGHT)
    assert mobile - base == pytest.approx(10.0 * C.DUEL_MOVEMENT_WEIGHT)
    assert precise - base > 3.0 * (mobile - base)


def test_weapon_classes_have_distinct_range_profiles(game_data: GameData) -> None:
    """Short-range guns, rifles, and snipers should want different fights."""
    from esports_sim.sim.engine import _MatchSim

    sim = _MatchSim(game_data, "team_nexus", "team_vanguard", "haven", 1)
    weapons = game_data.weapons.values()
    pistol = next(w for w in weapons if str(w.weapon_class) == "pistol")
    smg = next(w for w in weapons if str(w.weapon_class) == "smg")
    rifle = next(w for w in weapons if str(w.weapon_class) == "rifle")
    sniper = next(w for w in weapons if str(w.weapon_class) == "sniper")

    assert sim._range_mod(pistol, 4.0) > sim._range_mod(pistol, 32.0)
    assert sim._range_mod(smg, 4.0) > sim._range_mod(smg, 32.0)
    assert sim._range_mod(rifle, 4.0) == sim._range_mod(rifle, 32.0) == 0.0
    assert sim._range_mod(sniper, 32.0) > sim._range_mod(sniper, 4.0)


def test_composure_reduces_but_never_removes_day_form(game_data: GameData) -> None:
    """Form creates upsets, while composure makes that variance smaller."""
    from esports_sim.sim import constants as C
    from esports_sim.sim.engine import _MatchSim

    pid = sorted(game_data.teams["team_nexus"].player_ids)[0]
    low_composure = game_data.model_copy(deep=True)
    high_composure = game_data.model_copy(deep=True)
    low_composure.players[pid].attributes["composure"] = 0.0
    high_composure.players[pid].attributes["composure"] = 100.0

    cold = _MatchSim(low_composure, "team_nexus", "team_vanguard", "haven", 1)
    steady = _MatchSim(high_composure, "team_nexus", "team_vanguard", "haven", 1)

    assert abs(steady.day_form[pid]) < abs(cold.day_form[pid])
    assert all(abs(form) <= C.DAY_FORM_CAP for form in cold.day_form.values())
    assert all(abs(form) <= C.TEAM_FORM_CAP for form in cold.tactic_form.values())
