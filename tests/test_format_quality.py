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
