"""Loop iteration 4: competition-format depth and persistence/infra.

All manager/persistence-layer — the match engine is untouched, so the
golden fixture is unaffected.
"""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import new_campaign
from esports_sim.manager.schedule import build_semifinals, veto_bo3
from esports_sim.manager.state import SCHEMA_VERSION, GameState, TeamRecord
from esports_sim.registry import load_all


# -- head-to-head standings tiebreaker ---------------------------------------

def test_head_to_head_breaks_a_dead_tie() -> None:
    """Two teams level on wins and round differential are separated by their
    head-to-head result."""
    gd = load_all()
    gs = new_campaign(gd, seed=5)
    region = gs.regions()[0]
    order = gs.standings_order(region)
    x, y = order[0], order[1]
    # Force an exact tie on wins and differential.
    for t in (x, y):
        gs.standings[t] = TeamRecord(
            wins=6, losses=2, rounds_won=104, rounds_lost=96
        )
    # A played meeting where x beat y (winner_id is all _h2h_series reads).
    meeting = next(
        f for f in gs.fixtures if {f.team_a, f.team_b} == {x, y}
    )
    meeting.played = True
    meeting.winner_id = x
    ordered = gs.standings_order(region)
    assert ordered.index(x) < ordered.index(y)


def test_head_to_head_ignores_playoff_rematches() -> None:
    """Only regular-season meetings count: a playoff rematch must not
    reorder the league table (playoff results never touch TeamRecord)."""
    gd = load_all()
    gs = new_campaign(gd, seed=5)
    region = gs.regions()[0]
    x, y = gs.standings_order(region)[:2]
    for t in (x, y):
        gs.standings[t] = TeamRecord(
            wins=6, losses=2, rounds_won=104, rounds_lost=96
        )
    # A regular meeting x beat y, plus a playoff rematch y beat x. The
    # playoff game must be ignored, so x still ranks above y.
    reg = next(f for f in gs.fixtures if {f.team_a, f.team_b} == {x, y})
    reg.stage = "regular"
    reg.played = True
    reg.winner_id = x
    from esports_sim.manager.state import Fixture

    gs.fixtures.append(Fixture(
        id="s1semi_rematch", week=99, stage="semi", best_of=3,
        team_a=y, team_b=x, played=True, winner_id=y,
    ))
    ordered = gs.standings_order(region)
    assert ordered.index(x) < ordered.index(y)


def test_three_way_tie_is_transitive_and_insertion_order_independent() -> None:
    """A rock-paper-scissors H2H cycle (x>y>z>x) among three teams tied on
    wins and differential must NOT depend on standings insertion order — the
    mini-table resolves it deterministically (here all net margins are 0, so
    it falls to rounds-won then id)."""
    gd = load_all()
    gs = new_campaign(gd, seed=8)
    region = gs.regions()[0]
    x, y, z = gs.standings_order(region)[:3]
    for t in (x, y, z):
        gs.standings[t] = TeamRecord(
            wins=6, losses=2, rounds_won=100, rounds_lost=100
        )

    def beat(a: str, b: str) -> None:
        f = next(fx for fx in gs.fixtures if {fx.team_a, fx.team_b} == {a, b})
        f.played = True
        f.winner_id = a

    beat(x, y)
    beat(y, z)
    beat(z, x)  # the cycle
    base = gs.standings_order(region)
    # The three tied teams take the top three slots, in id order (margins 0).
    assert base[:3] == sorted([x, y, z])
    # Re-inserting the three teams in a different dict order changes nothing.
    reordered = {k: v for k, v in gs.standings.items() if k not in (x, y, z)}
    for k in (z, y, x):
        reordered[k] = gs.standings[k]
    gs.standings = reordered
    assert gs.standings_order(region) == base


# -- veto balance + semifinal guard ------------------------------------------

def _ban_counts(log: list[str], tag_a: str, tag_b: str) -> tuple[int, int]:
    a = sum(1 for line in log if line.startswith(f"{tag_a} ban"))
    b = sum(1 for line in log if line.startswith(f"{tag_b} ban"))
    return a, b


def test_veto_bans_are_balanced_across_pool_sizes() -> None:
    mastery = {}  # neutral: score falls back to map id ordering, still valid
    # Five-map pool: exactly one ban each, three maps returned.
    maps5, log5 = veto_bo3(list("abcde"), mastery, mastery, "AA", "BB")
    assert len(maps5) == 3 and len(set(maps5)) == 3
    assert _ban_counts(log5, "AA", "BB") == (1, 1)
    # Seven-map pool: four bans, split evenly (was 3/1 skewed to A before).
    _maps7, log7 = veto_bo3(list("abcdefg"), mastery, mastery, "AA", "BB")
    a, b = _ban_counts(log7, "AA", "BB")
    assert a + b == 4 and abs(a - b) <= 1


def test_semifinal_needs_four_qualifiers() -> None:
    with pytest.raises(ValueError):
        build_semifinals(["only", "three", "teams"], season=1, week=15,
                         veto_for=lambda a, b: ([], []))


# -- schema-version migration hook -------------------------------------------

def test_load_rejects_a_future_schema_version(tmp_path) -> None:
    gd = load_all()
    gs = new_campaign(gd, seed=1)
    path = tmp_path / "save.json"
    gs.save(path)
    # A save written by a newer build must fail loudly, not silently corrupt.
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = SCHEMA_VERSION + 5
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        GameState.load(path)


def test_load_roundtrips_current_version(tmp_path) -> None:
    gd = load_all()
    gs = new_campaign(gd, seed=1)
    path = tmp_path / "save.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert loaded.model_dump_json() == gs.model_dump_json()
