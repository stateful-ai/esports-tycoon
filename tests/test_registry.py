"""Registry load tests.

These exercise the authored YAML data. If someone typo's an attribute id or
drops a required field, these fail fast and point at the bad file.
"""

from __future__ import annotations

from esports_sim.registry import GameData
from esports_sim.schemas.common import Role


def test_attributes_loaded_with_expected_ids(game_data: GameData) -> None:
    ids = set(game_data.attributes.ids())
    expected = {
        "aim_precision",
        "aim_reactivity",
        "movement",
        "game_sense",
        "utility_usage",
        "positioning",
        "clutch_factor",
        "tilt_resistance",
        "composure",
        "comms_quality",
    }
    assert expected.issubset(ids), f"missing: {expected - ids}"
    assert len(ids) == 10, f"MVP expects exactly 10 attributes, got {len(ids)}"


def test_agents_cover_every_role(game_data: GameData) -> None:
    roles = {a.role for a in game_data.agents.values()}
    assert Role.DUELIST in roles
    assert Role.CONTROLLER in roles
    assert Role.INITIATOR in roles
    assert Role.SENTINEL in roles
    # Generated rosters need at least two agents per core role.
    for role in (Role.DUELIST, Role.CONTROLLER, Role.INITIATOR, Role.SENTINEL):
        n = sum(1 for a in game_data.agents.values() if a.role == role)
        assert n >= 2, f"need >= 2 {role} agents, got {n}"


def test_weapons_include_core_mvp_set(game_data: GameData) -> None:
    ids = set(game_data.weapons.keys())
    for required in ("classic", "sheriff", "spectre", "phantom", "vandal", "operator"):
        assert required in ids, f"missing weapon: {required}"


def test_maps_are_internally_consistent(game_data: GameData) -> None:
    for game_map in game_data.maps.values():
        assert game_map.attacker_spawn in game_map.callouts
        assert game_map.defender_spawn in game_map.callouts

        # Every adjacency target must be a real callout, and traversal must
        # be symmetric (you can walk back the way you came).
        for src, dests in game_map.adjacency.items():
            assert game_map.exists(src), f"adjacency src not a callout: {src}"
            for dst in dests:
                assert game_map.exists(dst), (
                    f"{game_map.id}: adjacency target not a callout: {dst}"
                )
                assert src in game_map.adjacency.get(dst, []), (
                    f"{game_map.id}: {src}->{dst} has no return edge"
                )

        # Every sightline must reference real callouts.
        for sl in game_map.sightlines:
            assert game_map.exists(sl.from_callout), sl.from_callout
            assert game_map.exists(sl.to_callout), sl.to_callout


def test_teams_have_five_players_each(game_data: GameData) -> None:
    for team in game_data.teams.values():
        assert len(team.player_ids) == 5, (
            f"{team.id} has {len(team.player_ids)} players; MVP roster is 5"
        )


def test_players_reference_valid_agents_and_maps(game_data: GameData) -> None:
    agent_ids = set(game_data.agents.keys())
    map_ids = set(game_data.maps.keys())
    for player in game_data.players.values():
        for am in player.agent_pool:
            assert am.agent_id in agent_ids, (
                f"{player.id} references unknown agent {am.agent_id}"
            )
        for mm in player.map_pool:
            assert mm.map_id in map_ids, (
                f"{player.id} references unknown map {mm.map_id}"
            )


def test_player_attributes_all_registered(game_data: GameData) -> None:
    """Every attribute key a player uses must exist in the registry."""
    registered = set(game_data.attributes.ids())
    for player in game_data.players.values():
        for attr_id in player.attributes:
            assert attr_id in registered, (
                f"{player.handle} uses unregistered attribute {attr_id}"
            )


def test_team_captains_are_on_roster(game_data: GameData) -> None:
    for team in game_data.teams.values():
        if team.captain_id is not None:
            assert team.captain_id in team.player_ids
