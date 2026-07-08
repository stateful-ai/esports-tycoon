"""Map gimmicks: rotating doors, teleporters, breakable doors.

These tests double as the acceptance contract for map authoring: Lotus
carries rotating doors, Bind carries teleporters, Ascent carries
breakable site doors — and all of them must actually fire in play.
"""

from __future__ import annotations

from esports_sim.registry import GameData
from esports_sim.sim import simulate_match


def _events(game_data: GameData, map_id: str, seed: int):
    return simulate_match(
        game_data, "team_nexus", "team_vanguard", map_id, seed
    )


def test_lotus_rotating_doors_fire_and_are_loud(game_data: GameData) -> None:
    events = _events(game_data, "lotus", 7)
    doors = [e for e in events if e.type == "round.gimmick"]
    assert doors, "a full Lotus match should swing a rotating door at least once"
    for e in doors:
        assert e.kind == "rotating_door"
        assert e.action == "used"
        assert e.x is not None and e.y is not None


def test_bind_teleporters_get_used(game_data: GameData) -> None:
    """TP usage is a "sometimes" mechanic (~35-65% of matches in sweeps),
    so sample a handful of seeds rather than pinning one — a single-seed
    assertion made map authoring hostage to unrelated RNG-cascade shifts."""
    gd = game_data
    assert any(
        g.type == "teleporter" for g in gd.maps["bind"].gimmicks
    ), "Bind's identity is its teleporters — the map must declare them"
    for seed in (11, 12, 13, 14):
        events = _events(gd, "bind", seed)
        if any(
            e.type == "round.gimmick" and e.kind == "teleporter" for e in events
        ):
            return
    raise AssertionError(
        "no teleporter take across four full Bind matches — the TP edges "
        "are probably unreachable or never route-preferred"
    )


def test_ascent_doors_close_and_break(game_data: GameData) -> None:
    gd = game_data
    assert any(
        g.type == "breakable_door" for g in gd.maps["ascent"].gimmicks
    ), "Ascent must declare its mechanical site doors"
    events = _events(gd, "ascent", 13)
    starts = [e for e in events if e.type == "round.start"]
    assert any(e.closed_doors for e in starts), (
        "with start_closed_prob defaults, some rounds should start with a "
        "door shut"
    )
    # Over a full match, somebody should have shot one open.
    broken = [
        e
        for e in events
        if e.type == "round.gimmick" and e.action == "broken"
    ]
    assert broken, "a shut door on a main path should get broken eventually"


def test_gimmick_edges_are_real_adjacency(game_data: GameData) -> None:
    """A gimmick on a non-edge would never fire — catch authoring slips."""
    for m in game_data.maps.values():
        for g in m.gimmicks:
            a, b = g.between
            assert b in m.adjacency.get(a, []) and a in m.adjacency.get(b, []), (
                f"{m.id}: gimmick {g.id} sits on ({a}, {b}) which is not a "
                f"two-way adjacency edge"
            )
