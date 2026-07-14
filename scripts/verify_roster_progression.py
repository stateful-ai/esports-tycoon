import sys
import os
import math
import numpy as np
import yaml
from pathlib import Path

# Add 'src' to python path to import packages correctly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from esports_sim.registry import load_all
from esports_sim.registry.rosters import load_roster_pack
from esports_sim.manager import development, training
from esports_sim.schemas import Player

def main():
    print("Loading Baseline GameData...")
    gd = load_all()
    print("Loading VCT 2021 Roster Pack...")
    pack = load_roster_pack("vct-2021")

    # Collect all players: rostered, free agents, prospects
    all_players = []
    for pid, p in pack.players.items():
        all_players.append(p)
    for pid, p in pack.free_agents.items():
        all_players.append(p)
    for pid, prospect in pack.future_prospects.items():
        all_players.append(prospect.player)

    print(f"Total players found in VCT 2021 pack: {len(all_players)}")

    # Seeds to evaluate potential variance
    seeds = list(range(200, 250)) # 50 seeds for robust validation
    print(f"Evaluating across {len(seeds)} campaign seeds...")

    # Categorize players based on their baseline stats
    young_players = []
    veteran_players = []
    pure_aimers = []

    # Map player ID -> base potential (calculated before seed variance)
    base_potentials = {}
    for p in all_players:
        base_pot = p.potential if p.potential > 0.0 else development.potential_of(p)
        base_potentials[p.id] = base_pot

        is_young = p.age <= 21 or "prodigy" in p.personality_tags or "rookie" in p.personality_tags
        is_vet = p.age >= 26 or "veteran" in p.personality_tags
        
        if is_young:
            young_players.append(p)
        if is_vet:
            veteran_players.append(p)
        if "pure_aimer" in p.personality_tags:
            pure_aimers.append(p)

    print(f"Categorized players:")
    print(f"  - Young/Rookie: {len(young_players)}")
    print(f"  - Veteran: {len(veteran_players)}")
    print(f"  - Pure Aimers: {len(pure_aimers)}")

    # ----------------------------------------------------
    # Verification 1 & 2: Young/Rookie Potential Variance
    # ----------------------------------------------------
    print("\n--- Verifying Young/Rookie Potential Variance ---")
    young_results = []
    young_passed = True
    for p in young_players:
        base_pa = base_potentials[p.id]
        p_pots = []
        p_swings = []
        for seed in seeds:
            p_copy = p.model_copy(deep=True)
            development.initialize_player_seed_variance(p_copy, seed)
            p_pots.append(p_copy.potential)
            p_swings.append(p_copy.potential - base_pa)
        
        min_pot = min(p_pots)
        max_pot = max(p_pots)
        max_swing_obs = max(abs(s) for s in p_swings)
        std_pot = np.std(p_pots)
        
        # Check constraints: swing must not exceed 6.0 (using epsilon for rounding checks)
        # and standard deviation must be > 0.0 (must exhibit variance across seeds)
        exceeds_swing = max_swing_obs > 6.01
        has_variance = std_pot > 0.0
        
        player_pass = (not exceeds_swing) and has_variance
        if not player_pass:
            young_passed = False
            
        young_results.append({
            "id": p.id,
            "handle": p.handle,
            "age": p.age,
            "tags": p.personality_tags,
            "base_pa": base_pa,
            "min_pa": min_pot,
            "max_pa": max_pot,
            "max_swing": round(max_swing_obs, 2),
            "std": round(std_pot, 3),
            "pass": player_pass
        })

    print(f"Young/Rookie potential variance checks passed: {young_passed}")
    for r in young_results[:10]: # Print first 10 for review
        print(f"  Player: {r['handle']} (Age {r['age']}), Base: {r['base_pa']}, Min: {r['min_pa']}, Max: {r['max_pa']}, Max Swing: {r['max_swing']}, Std: {r['std']}, Pass: {r['pass']}")
    if len(young_results) > 10:
        print(f"  ... and {len(young_results) - 10} more players verified.")

    # ----------------------------------------------------
    # Verification 3: Veteran Stability (Zero Variance)
    # ----------------------------------------------------
    print("\n--- Verifying Veteran Potential Stability ---")
    vet_results = []
    vet_passed = True
    for p in veteran_players:
        p_ref = p.model_copy(deep=True)
        development.initialize_player_seed_variance(p_ref, seeds[0])
        ref_pa = p_ref.potential

        p_pots = []
        p_swings = []
        for seed in seeds:
            p_copy = p.model_copy(deep=True)
            development.initialize_player_seed_variance(p_copy, seed)
            p_pots.append(p_copy.potential)
            p_swings.append(p_copy.potential - ref_pa)
        
        min_pot = min(p_pots)
        max_pot = max(p_pots)
        max_swing_obs = max(abs(s) for s in p_swings)
        std_pot = np.std(p_pots)
        
        player_pass = (std_pot < 1e-9) and (max_swing_obs < 1e-9)
        if not player_pass:
            vet_passed = False
            
        vet_results.append({
            "id": p.id,
            "handle": p.handle,
            "age": p.age,
            "tags": p.personality_tags,
            "base_pa": ref_pa,
            "min_pa": min_pot,
            "max_pa": max_pot,
            "max_swing": round(max_swing_obs, 2),
            "std": round(std_pot, 3),
            "pass": player_pass
        })

    print(f"Veteran stability checks passed: {vet_passed}")
    for r in vet_results[:10]:
        print(f"  Player: {r['handle']} (Age {r['age']}), Base: {r['base_pa']}, Min: {r['min_pa']}, Max: {r['max_pa']}, Max Swing: {r['max_swing']}, Std: {r['std']}, Pass: {r['pass']}")
    if len(vet_results) > 10:
        print(f"  ... and {len(vet_results) - 10} more players verified.")

    # ----------------------------------------------------
    # Verification 4: Pure Aimer Curve & Asymmetric Decay
    # ----------------------------------------------------
    print("\n--- Verifying Pure Aimer Early Peak, Early Decline & Asymmetric Decay ---")
    aimer_results = []
    aimer_passed = True
    for p in pure_aimers:
        # Check Curve Properties (requires seed initialization to assign development_curve)
        # Check for multiple seeds
        curve_checks_passed = True
        curve_archetypes = set()
        curve_peaks = set()
        curve_declines = set()
        
        for seed in seeds:
            p_copy = p.model_copy(deep=True)
            development.initialize_player_seed_variance(p_copy, seed)
            curve = development.development_curve(p_copy)
            curve_archetypes.add(curve.archetype)
            curve_peaks.add(curve.growth_peak_age)
            curve_declines.add(curve.decline_age)
            
            # 1. Early peak check: archetype = "flash", peak between 18 and 20
            if curve.archetype != "flash":
                print(f"    FAIL: Seed {seed} for {p.handle} archetype is {curve.archetype} instead of flash")
                curve_checks_passed = False
            if not (18 <= curve.growth_peak_age <= 20):
                print(f"    FAIL: Seed {seed} for {p.handle} peak age is {curve.growth_peak_age} instead of 18..20")
                curve_checks_passed = False
            
            # 2. Early decline check: decline_age is 23 or 24
            if curve.decline_age not in (23, 24):
                print(f"    FAIL: Seed {seed} for {p.handle} decline age is {curve.decline_age} instead of 23..24")
                curve_checks_passed = False
                
        # 3. Asymmetric Decay check: aim decays at 0.15x, other attributes at 1.5x
        # We initialize the player with seed 200, force their age to decline_age - 1, and age them once.
        p_decay = p.model_copy(deep=True)
        development.initialize_player_seed_variance(p_decay, 200) # Choose a stable seed
        curve = development.development_curve(p_decay)
        
        # Set all attributes to a high baseline (e.g. 70.0) to avoid hitting the 1.0 floor
        aim_attrs = ["aim_precision", "aim_reactivity"]
        other_attrs = [
            "movement", "game_sense", "positioning", "utility_usage",
            "clutch_factor", "tilt_resistance", "composure", "comms_quality"
        ]
        all_attrs = aim_attrs + other_attrs
        for attr_id in all_attrs:
            p_decay.attributes[attr_id] = 70.0
            
        p_decay.age = curve.decline_age - 1
        
        # Run offseason aging
        rng = np.random.default_rng(200)
        training.apply_offseason_aging(p_decay, rng)
        
        # Verify age ticked
        if p_decay.age != curve.decline_age:
            print(f"    FAIL: Age did not advance correctly to {curve.decline_age}")
            curve_checks_passed = False
            
        # Verify decline multiplier and decline calculation
        # decline = (p.age - (turn - 1)) * 0.8 * curve_decline_multiplier(p) = 0.8 * decline_mult
        decline_mult = development.curve_decline_multiplier(p_decay)
        decline = 0.8 * decline_mult
        
        decay_checks_passed = True
        aim_decays = []
        other_decays = []
        
        # Check Aim attributes (decay = base_decay * 0.15)
        # where base_decay = decline * uniform(0.7, 1.3)
        for attr_id in aim_attrs:
            decay = 70.0 - p_decay.attr(attr_id)
            aim_decays.append(decay)
            # base_decay_est = decay / 0.15
            base_decay_est = decay / 0.15
            ratio = base_decay_est / decline
            if not (0.7 - 0.05 <= ratio <= 1.3 + 0.05):
                print(f"    FAIL: Aim attribute {attr_id} decay ratio {ratio:.3f} outside [0.7, 1.3] (decay: {decay})")
                decay_checks_passed = False
                
        # Check Other attributes (decay = base_decay * 1.5)
        # where base_decay = decline * uniform(0.7, 1.3)
        for attr_id in other_attrs:
            decay = 70.0 - p_decay.attr(attr_id)
            other_decays.append(decay)
            base_decay_est = decay / 1.5
            ratio = base_decay_est / decline
            if not (0.7 - 0.05 <= ratio <= 1.3 + 0.05):
                print(f"    FAIL: Other attribute {attr_id} decay ratio {ratio:.3f} outside [0.7, 1.3] (decay: {decay})")
                decay_checks_passed = False
                
        player_pass = curve_checks_passed and decay_checks_passed
        if not player_pass:
            aimer_passed = False
            
        aimer_results.append({
            "id": p.id,
            "handle": p.handle,
            "archetypes": sorted(list(curve_archetypes)),
            "peaks": sorted(list(curve_peaks)),
            "declines": sorted(list(curve_declines)),
            "avg_aim_decay": round(float(np.mean(aim_decays)), 4),
            "avg_other_decay": round(float(np.mean(other_decays)), 4),
            "pass": player_pass
        })

    print(f"Pure Aimer checks passed: {aimer_passed}")
    for r in aimer_results:
        print(f"  Player: {r['handle']}")
        print(f"    Archetypes: {r['archetypes']}")
        print(f"    Peak Ages: {r['peaks']}")
        print(f"    Decline Ages: {r['declines']}")
        print(f"    Decays (Aim/Other): {r['avg_aim_decay']} / {r['avg_other_decay']}")
        print(f"    Pass: {r['pass']}")

    # Write report file to agents directory
    report_path = Path("c:/Users/aidan/workspace/esports-simulator/ESports Simulator/.agents/challenger_roster_verification/verification_report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Roster progression and Volatility Verification Report\n\n")
        f.write(f"This report documents the verification of the VCT 2021 roster pack progression systems.\n\n")
        
        f.write("## Overview\n")
        f.write(f"- **Seeds Tested**: {len(seeds)} (seeds {min(seeds)}-{max(seeds)})\n")
        f.write(f"- **Total Players Analyzed**: {len(all_players)}\n")
        f.write(f"- **Young/Rookie Players (Age <= 21 or tags 'prodigy'/'rookie')**: {len(young_players)}\n")
        f.write(f"- **Veteran Players (Age >= 26 or tag 'veteran')**: {len(veteran_players)}\n")
        f.write(f"- **Pure Aimer Players**: {len(pure_aimers)}\n\n")
        
        f.write("## Verification Results\n\n")
        
        # Young/Rookie table
        f.write("### 1. Young/Rookie Player Potential Variance (Requirement 2)\n")
        f.write("Young and rookie players are expected to exhibit potential variance of up to +/- 6.0 across seeds.\n\n")
        status = "PASSED" if young_passed else "FAILED"
        f.write(f"**Status**: {status}\n\n")
        f.write("| Handle | Age | Tags | Base PA | Min PA | Max PA | Max Swing | Std Dev | Pass |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for r in young_results:
            f.write(f"| {r['handle']} | {r['age']} | {', '.join(r['tags'])} | {r['base_pa']} | {r['min_pa']} | {r['max_pa']} | {r['max_swing']} | {r['std']} | {r['pass']} |\n")
        f.write("\n")
        
        # Veteran table
        f.write("### 2. Veteran Player Potential Stability (Requirement 3)\n")
        f.write("Veteran players are expected to exhibit zero potential variance (max swing = 0.0) across seeds.\n\n")
        status = "PASSED" if vet_passed else "FAILED"
        f.write(f"**Status**: {status}\n\n")
        f.write("| Handle | Age | Tags | Base PA | Min PA | Max PA | Max Swing | Std Dev | Pass |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for r in vet_results:
            f.write(f"| {r['handle']} | {r['age']} | {', '.join(r['tags'])} | {r['base_pa']} | {r['min_pa']} | {r['max_pa']} | {r['max_swing']} | {r['std']} | {r['pass']} |\n")
        f.write("\n")
        
        # Pure Aimer table
        f.write("### 3. Pure Aimer Curve and Asymmetric Decay (Requirement 4)\n")
        f.write("Pure aimers must follow an early peak (archetype 'flash', peak age 18-20), early decline (decline age 23-24), and asymmetric aim-resilient decay (aim attributes decay at 0.15x, other attributes decay at 1.5x).\n\n")
        status = "PASSED" if aimer_passed else "FAILED"
        f.write(f"**Status**: {status}\n\n")
        f.write("| Handle | Archetypes | Peak Ages | Decline Ages | Avg Aim Decay | Avg Other Decay | Pass |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for r in aimer_results:
            f.write(f"| {r['handle']} | {', '.join(r['archetypes'])} | {', '.join(map(str, r['peaks']))} | {', '.join(map(str, r['declines']))} | {r['avg_aim_decay']} | {r['avg_other_decay']} | {r['pass']} |\n")
        f.write("\n")
        
        f.write("## Conclusion\n")
        if young_passed and vet_passed and aimer_passed:
            f.write("All career progression and volatility hooks operate in complete compliance with specified requirements.\n")
        else:
            f.write("Some requirements did not pass verification. Please check the logs above.\n")

    print(f"Verification report written to {report_path}")

    # Exit with code if any fail
    if not (young_passed and vet_passed and aimer_passed):
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
