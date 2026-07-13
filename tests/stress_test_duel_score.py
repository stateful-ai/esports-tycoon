import random
import sys
import numpy as np

from esports_sim.sim import constants as C
from esports_sim.sim.engine import _MatchSim
from esports_sim.registry import GameData

def original_duel_score(
    sim: _MatchSim,
    pid: str,
    holder: bool,
    advantaged: bool,
    same_callout: bool,
    tick: int,
    n_alive_own: int,
    n_alive_opp: int,
    duel_range: float = 20.0,
    height_delta: float = 0.0,
    in_cover: bool = False,
    facing: float = 0.0,
    peeking: bool = False,
    opp_pid: str | None = None,
) -> float:
    ps = sim.p[pid]
    pl = sim._player(pid)
    
    s = (
        C.DUEL_AIM_PRECISION_WEIGHT * pl.attr("aim_precision")
        + C.DUEL_AIM_REACTIVITY_WEIGHT * pl.attr("aim_reactivity")
        + C.DUEL_MOVEMENT_WEIGHT * pl.attr("movement")
        + (
            C.DUEL_POSITIONING_WEIGHT * pl.attr("positioning")
            if holder
            else C.DUEL_GAME_SENSE_WEIGHT * pl.attr("game_sense")
        )
    )
    s += sim._condition(pid, pl)
    weapon = sim.gd.weapons[ps.weapon]
    s += (weapon.accuracy_base - 0.6) * C.WEAPON_ACCURACY_SCORE
    s += max(
        -C.WEAPON_DAMAGE_CAP,
        min(
            C.WEAPON_DAMAGE_CAP,
            (weapon.dmg_body - C.WEAPON_DAMAGE_PIVOT)
            * C.WEAPON_DAMAGE_SCORE,
        ),
    )
    s += (pl.agent_mastery(ps.agent_id, 50.0) - 50.0) / 25.0
    for m in pl.map_pool:
        if m.map_id == sim.map.id:
            s += (m.mastery - 50.0) / 25.0
            break
    if ps.weapon == "operator":
        agent = sim.gd.agents.get(ps.agent_id)
        if agent is not None and agent.op_affinity:
            s += C.OPERATOR_AGENT_AFFINITY
    if ps.weapon == "operator" and holder and advantaged:
        s += C.OPERATOR_HOLD_BONUS
    s += sim._range_mod(weapon, duel_range)
    if height_delta > 0:
        s += min(C.HEIGHT_CAP, height_delta * C.HEIGHT_PER_Z)
    if in_cover:
        s += C.COVER_BONUS
    if holder and advantaged:
        s += C.HOLD_ADVANTAGE
    if holder and not same_callout:
        if facing >= C.PREAIM_FACING_COS:
            s += C.HOLDER_BONUS
        elif facing <= C.FLANK_FACING_COS:
            s -= C.FLANK_MALUS
    if peeking:
        s += C.PEEK_INITIATIVE
    if ps.flash_until >= tick:
        s -= C.FLASH_DEBUFF
    if ps.bonus_until >= tick:
        s += ps.bonus
    if n_alive_own == 1 and n_alive_opp >= 2:
        s += ((pl.attr("clutch_factor") - 50.0) / 5.0) * (
            1.0 + sim._conf_dev(pid) / C.CONFIDENCE_CLUTCH_DIV
        )
    if sim.loss_streak[ps.team_id] >= C.TILT_STREAK:
        s -= (100.0 - pl.attr("tilt_resistance")) / 15.0
    if ps.armor > 0:
        s += 2.0
    s += sim.day_form[pid] + sim.tactic_form[ps.team_id]
    s += sim.exec_mod[ps.team_id]
    s += sim._prep[ps.team_id]
    s += sim._counter[ps.team_id]
    plan = sim._plans.get(ps.team_id)
    if plan is not None and plan.focus_target is not None and opp_pid is not None:
        if opp_pid == plan.focus_target:
            s += C.FOCUS_TARGET_EDGE
        else:
            s -= C.FOCUS_OFF_MALUS
    return s

def run_stress_test():
    from esports_sim.registry import load_all
    game_data = load_all()
    
    # Choose a team and match sim context
    sim = _MatchSim(game_data, "team_nexus", "team_vanguard", "haven", 1)
    
    pid = sorted(game_data.teams["team_nexus"].player_ids)[0]
    opp_pid = sorted(game_data.teams["team_vanguard"].player_ids)[0]
    team_id = "team_nexus"
    
    # We will run 10,000 trials with completely randomized parameters
    random.seed(42)
    np.random.seed(42)
    
    max_diff = 0.0
    mismatch_count = 0
    breakdown_mismatch_count = 0
    
    for i in range(10000):
        # Randomize inputs
        holder = random.choice([True, False])
        advantaged = random.choice([True, False])
        same_callout = random.choice([True, False])
        tick = random.randint(1, 100)
        n_alive_own = random.randint(1, 5)
        n_alive_opp = random.randint(1, 5)
        duel_range = random.uniform(5.0, 50.0)
        height_delta = random.uniform(-10.0, 10.0)
        in_cover = random.choice([True, False])
        facing = random.uniform(-1.0, 1.0)
        peeking = random.choice([True, False])
        opp = random.choice([opp_pid, None])
        
        # Randomize player/team/match states to cover all paths
        ps = sim.p[pid]
        pl = sim._player(pid)
        
        # randomize attributes
        pl.attributes["aim_precision"] = random.uniform(0, 100)
        pl.attributes["aim_reactivity"] = random.uniform(0, 100)
        pl.attributes["movement"] = random.uniform(0, 100)
        pl.attributes["positioning"] = random.uniform(0, 100)
        pl.attributes["game_sense"] = random.uniform(0, 100)
        pl.attributes["clutch_factor"] = random.uniform(0, 100)
        pl.attributes["tilt_resistance"] = random.uniform(0, 100)
        
        # randomize state
        ps.weapon = random.choice(["vandal", "phantom", "operator", "classic"])
        ps.agent_id = random.choice(["jett", "chamber", "sage", "sova"])
        ps.armor = random.choice([0, 25, 50])
        ps.flash_until = random.choice([0, tick + 5])
        ps.bonus_until = random.choice([0, tick + 5])
        ps.bonus = random.uniform(-5.0, 5.0)
        
        sim.loss_streak[team_id] = random.randint(0, 5)
        sim.day_form[pid] = random.uniform(-3.0, 3.0)
        sim.tactic_form[team_id] = random.uniform(-2.0, 2.0)
        sim.exec_mod[team_id] = random.uniform(-2.0, 2.0)
        sim._prep[team_id] = random.uniform(-1.0, 1.0)
        sim._counter[team_id] = random.uniform(-1.0, 1.0)
        
        # plans and focus target
        from esports_sim.sim.engine import TeamMatchPlan
        if random.choice([True, False]):
            sim._plans[team_id] = TeamMatchPlan(focus_target=opp_pid)
        else:
            sim._plans[team_id] = TeamMatchPlan(focus_target=None)
            
        # Get refactored score
        res_refactored = sim._duel_score(
            pid, holder, advantaged, same_callout, tick, n_alive_own, n_alive_opp,
            duel_range, height_delta, in_cover, facing, peeking, opp, return_breakdown=True
        )
        score_refactored, breakdown = res_refactored
        
        # Get original score using correct original logic
        score_original = original_duel_score(
            sim, pid, holder, advantaged, same_callout, tick, n_alive_own, n_alive_opp,
            duel_range, height_delta, in_cover, facing, peeking, opp
        )
        
        diff = abs(score_refactored - score_original)
        max_diff = max(max_diff, diff)
        
        # 1. Equivalence check
        if diff > 1e-12:
            mismatch_count += 1
            if mismatch_count <= 5:
                print(f"Mismatch at iteration {i}: Refactored = {score_refactored}, Original = {score_original}, Diff = {diff}")
                
        # 2. Breakdown sum check
        breakdown_sum = sum(breakdown.values())
        sum_diff = abs(breakdown_sum - score_refactored)
        if sum_diff != 0.0:
            breakdown_mismatch_count += 1
            if breakdown_mismatch_count <= 5:
                print(f"Breakdown sum mismatch at iteration {i}: Sum = {breakdown_sum}, Score = {score_refactored}, Diff = {sum_diff}")
                
    print("\n--- RESULTS ---")
    print(f"Max difference between original and refactored: {max_diff}")
    print(f"Equivalence mismatches (>1e-12): {mismatch_count} / 10000")
    print(f"Breakdown sum exact mismatches (!= 0.0): {breakdown_mismatch_count} / 10000")

if __name__ == "__main__":
    run_stress_test()
