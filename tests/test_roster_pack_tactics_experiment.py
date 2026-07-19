from scripts.roster_pack_tactics_experiment import (
    _fit_edges,
    mirrored_pack_game_data,
)


def test_real_roster_experiment_mirrors_mechanics_and_keeps_identity() -> None:
    gd, real_id, mirror_id = mirrored_pack_game_data(
        "vct-2021", "team_sentinels"
    )
    real = gd.teams[real_id]
    mirror = gd.teams[mirror_id]

    assert real.id != mirror.id
    assert real.chemistry == mirror.chemistry
    assert real.tactics.model_dump() == mirror.tactics.model_dump()
    assert len(real.player_ids) == len(mirror.player_ids) == 5
    for real_pid, mirror_pid in zip(real.player_ids, mirror.player_ids):
        left = gd.players[real_pid]
        right = gd.players[mirror_pid]
        assert left.id != right.id
        assert left.attributes == right.attributes
        assert left.role == right.role
        assert left.playstyle == right.playstyle
        assert left.agent_pool == right.agent_pool
        assert left.map_pool == right.map_pool

    low, high = _fit_edges(gd, real_id, "aggression")
    assert isinstance(low, float) and isinstance(high, float)
    assert low != high
