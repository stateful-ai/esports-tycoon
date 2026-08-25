"""No two players in a world share a handle.

Two synthetic players, managing different clubs in different worlds, each
opened Club > Squad and found two starters on their own five-man roster called
Falconrush. It is not bad luck: the parts tables make 24 x 24 = 576 handles and
a world generates 228 players, so the birthday paradox puts ~30 collisions in
every world. Measured before the fix: 28/35/31 duplicated handles on seeds
2026/7/99, and at least one roster with an internal duplicate every time.

It is not only cosmetic. One Match Review printed "Standout: Falconrush (1.31).
Off-colour: Falconrush (0.84)" -- the same handle named as the player's best
and worst performer in one sentence -- and a contract warning named a handle
that two players answered to.

The fix resolves collisions without drawing from the rng (see gen._free_handle),
so a seed still reproduces its world byte for byte. The last test here is the
one that matters most: it pins that everything EXCEPT handles is unchanged.
"""

from __future__ import annotations

import collections

import numpy as np
import pytest

from esports_sim.manager import new_campaign
from esports_sim.manager.gen import (
    _HANDLE_PARTS_A,
    _HANDLE_PARTS_B,
    _free_handle,
    generate_league_teams,
)
from esports_sim.registry import GameData
from esports_sim.schemas.common import Region

SEEDS = (2026, 7, 99)


@pytest.mark.campaign
@pytest.mark.parametrize("seed", SEEDS)
def test_no_two_players_in_a_world_share_a_handle(game_data: GameData, seed: int) -> None:
    gs = new_campaign(game_data, seed=seed, user_team_id="team_nexus")
    counts = collections.Counter(p.handle for p in gs.players.values())
    dupes = {h: n for h, n in counts.items() if n > 1}
    assert not dupes, f"seed {seed} generated duplicate handles: {sorted(dupes)}"


@pytest.mark.campaign
@pytest.mark.parametrize("seed", SEEDS)
def test_no_roster_contains_the_same_handle_twice(game_data: GameData, seed: int) -> None:
    """The case a player actually sees: two identical names in one squad table."""
    gs = new_campaign(game_data, seed=seed, user_team_id="team_nexus")
    for team in sorted(gs.teams.values(), key=lambda t: t.id):
        handles = [gs.players[pid].handle for pid in team.player_ids]
        assert len(handles) == len(set(handles)), (
            f"{team.name} fields two players called "
            f"{[h for h, n in collections.Counter(handles).items() if n > 1]}"
        )


@pytest.mark.campaign
def test_free_agents_do_not_reuse_a_rostered_handle(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=2026, user_team_id="team_nexus")
    rostered = {
        gs.players[pid].handle for t in gs.teams.values() for pid in t.player_ids
    }
    clashes = sorted(
        gs.players[fa].handle for fa in gs.free_agent_ids
        if gs.players[fa].handle in rostered
    )
    assert not clashes, f"free agents reuse rostered handles: {clashes}"


def test_free_handle_is_pure_and_stable() -> None:
    """Same inputs, same answer, and it never returns something already taken."""
    taken = {"Nightwolf", "Nightbyte"}
    first = _free_handle("Nightwolf", set(taken))
    assert first == _free_handle("Nightwolf", set(taken))
    assert first not in taken
    assert _free_handle("Frostfade", taken) == "Frostfade"  # free: returned as-is


def test_free_handle_still_answers_when_every_combination_is_taken() -> None:
    """Past 576 players the tables are exhausted; it must not return a dupe."""
    everything = {
        a + b.lower() for a in _HANDLE_PARTS_A for b in _HANDLE_PARTS_B
    }
    out = _free_handle("Nightwolf", everything)
    assert out not in everything, "returned a handle that was already taken"


@pytest.mark.campaign
@pytest.mark.parametrize("seed", (2026, 7, 99))
def test_uniqueness_consumes_no_rng(game_data: GameData, seed: int) -> None:
    """Handle assignment must not disturb the draw sequence.

    `_free_handle` resolves a clash by walking the parts table, never by
    drawing, so a world generated WITH the registry must match one generated
    WITHOUT it in every field except the handles themselves.

    An earlier version of this test pinned a digest of the whole GameState
    captured from the pre-fix build. That was wrong in a way worth recording:
    it conflated "handle assignment moved nothing" with "GameState never grows
    a field", so adding `recovery_booked_by` for the recovery feature broke it
    on both seeds while the invariant it guards was perfectly intact. Compare
    the two generators directly instead — same rng seed, one registry, one
    none — and the assertion survives any unrelated schema change.
    """
    def build(with_registry: bool):
        rng = np.random.default_rng(seed)
        taken: set[str] | None = set() if with_registry else None
        teams, players = generate_league_teams(
            rng, game_data, n_teams=6, region=Region.EMEA,
            used_names=set(), taken_handles=taken,
        )
        return teams, players

    teams_a, players_a = build(True)
    teams_b, players_b = build(False)

    assert [t.model_dump() for t in teams_a] == [t.model_dump() for t in teams_b], (
        "team generation differs — handle assignment consumed rng"
    )
    assert len(players_a) == len(players_b)
    for a, b in zip(players_a, players_b):
        assert a.id == b.id
        pa, pb = a.model_dump(), b.model_dump()
        pa.pop("handle"), pb.pop("handle")
        assert pa == pb, (
            f"{a.id} differs beyond its handle — handle assignment must not "
            "consume the rng stream"
        )


@pytest.mark.campaign
@pytest.mark.parametrize("seed", (2026, 7, 99))
def test_the_registry_is_what_removes_the_duplicates(
    game_data: GameData, seed: int
) -> None:
    """The companion to the test above: without the registry, collisions are
    still there. Together they show the fix does exactly one thing.

    Sampled at WORLD scale on purpose. One 6-team region is 30 players against
    576 handles, which expects well under one collision — the first version of
    this test asserted on that and duly passed on seed 2026 and failed on 7
    and 99. A real world is 228 players, where the expected count is ~30 and
    seeing none would genuinely mean the fix had stopped mattering.
    """
    rng = np.random.default_rng(seed)
    handles: list[str] = []
    for region in (Region.AMERICAS, Region.EMEA, Region.PACIFIC):
        for _ in range(3):
            _, players = generate_league_teams(
                rng, game_data, n_teams=6, region=region,
                used_names=set(), taken_handles=None,
            )
            handles.extend(p.handle for p in players)
    assert len(handles) >= 200, f"sample too small to be meaningful: {len(handles)}"
    assert len(handles) != len(set(handles)), (
        f"{len(handles)} players drew {len(set(handles))} distinct handles with "
        "no registry — expected collisions at this scale; if the parts tables "
        "grew, the fix may be moot"
    )
