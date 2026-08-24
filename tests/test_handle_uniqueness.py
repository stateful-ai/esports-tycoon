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
import hashlib
import json

import pytest

from esports_sim.manager import new_campaign
from esports_sim.manager.gen import _HANDLE_PARTS_A, _HANDLE_PARTS_B, _free_handle
from esports_sim.registry import GameData

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
@pytest.mark.slow
@pytest.mark.parametrize("seed", (2026, 7))
def test_only_handles_changed(game_data: GameData, seed: int) -> None:
    """Uniqueness must not perturb the world.

    `_free_handle` draws nothing from the rng, so every other field a seed
    produces has to be exactly what it was before. These digests were taken
    from the pre-fix build (handles stripped); if a future change to handle
    assignment consumes rng, these break and tell you it moved the world.
    """
    expected = {
        2026: "c334553a8a3aae939f90",
        7: "97d61eb4e5cae7cf7efb",
    }[seed]
    gs = new_campaign(game_data, seed=seed, user_team_id="team_nexus")
    payload = json.loads(gs.model_dump_json())
    for player in payload.get("players", {}).values():
        player.pop("handle", None)
    digest = hashlib.blake2b(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()[:20]
    assert digest == expected, (
        "handle uniqueness moved something other than handles — it must not "
        "consume the rng stream"
    )
