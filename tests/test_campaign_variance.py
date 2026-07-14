from __future__ import annotations

import json
from esports_sim.manager.campaign import new_campaign
from esports_sim.registry import GameData
from esports_sim.manager import GameState


def test_campaign_variance_deterministic_and_stable(game_data: GameData) -> None:
    # 1. Create two campaigns with different seeds
    gs_a = new_campaign(game_data, seed=123)
    gs_b = new_campaign(game_data, seed=456)
    
    common_ids = set(gs_a.players.keys()) & set(gs_b.players.keys())
    assert common_ids, "Should have overlapping player IDs in different campaign seeds"
    
    # 2. Assert variance for young players/rookies
    # Young players: age <= 21 or prodigy/rookie personality tags.
    # Veterans: age >= 26 or veteran personality tag.
    young_count = 0
    young_varied = 0
    
    veteran_count = 0
    veteran_stable = 0

    for pid in sorted(common_ids):
        pa = gs_a.players[pid]
        pb = gs_b.players[pid]
        
        # Verify both players have same age and tags to be comparable
        if pa.age != pb.age or sorted(pa.personality_tags) != sorted(pb.personality_tags):
            continue
            
        is_young = pa.age <= 21 or "prodigy" in pa.personality_tags or "rookie" in pa.personality_tags
        is_vet = pa.age >= 26 or "veteran" in pa.personality_tags
        
        if is_young:
            young_count += 1
            if pa.potential != pb.potential:
                young_varied += 1

        elif is_vet:
            veteran_count += 1
            # Potential must be identical
            assert pa.potential == pb.potential, f"Veteran {pid} potential differed: {pa.potential} vs {pb.potential}"
            # Development curves must be identical
            if pa.development_curve is not None and pb.development_curve is not None:
                assert pa.development_curve.archetype == pb.development_curve.archetype
                assert pa.development_curve.growth_peak_age == pb.development_curve.growth_peak_age
                assert pa.development_curve.growth_width == pb.development_curve.growth_width
                assert pa.development_curve.peak_years == pb.development_curve.peak_years
                assert pa.development_curve.decline_age == pb.development_curve.decline_age
                assert pa.development_curve.realization == pb.development_curve.realization
                assert pa.development_curve.volatility == pb.development_curve.volatility
                veteran_stable += 1

    # Verify we actually tested a reasonable number of players
    assert young_count > 0, "No young players found to check variance"
    assert veteran_count > 0, "No veteran players found to check stability"
    # Ensure at least some young players had different potentials/curves due to campaign seed
    assert young_varied > 0, "Young players potentials did not vary across seeds"

    # 3. Test save/load cycles survival
    dump_a = gs_a.model_dump_json()
    loaded_a = GameState.model_validate_json(dump_a)
    
    assert loaded_a.model_dump_json() == gs_a.model_dump_json()
    
    for pid in common_ids:
        pa = gs_a.players[pid]
        pla = loaded_a.players[pid]
        
        assert pa.potential == pla.potential
        if pa.development_curve is not None:
            assert pla.development_curve is not None
            assert pa.development_curve.archetype == pla.development_curve.archetype
            assert pa.development_curve.growth_peak_age == pla.development_curve.growth_peak_age
            assert pa.development_curve.growth_width == pla.development_curve.growth_width
            assert pa.development_curve.peak_years == pla.development_curve.peak_years
            assert pa.development_curve.decline_age == pla.development_curve.decline_age
            assert pa.development_curve.realization == pla.development_curve.realization
            assert pa.development_curve.volatility == pla.development_curve.volatility
