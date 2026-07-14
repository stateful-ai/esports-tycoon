"""EHM layer: potential, traits, development curves, scout reports."""

from __future__ import annotations

import numpy as np

from esports_sim.manager import development, training
from esports_sim.manager.campaign import new_campaign
from esports_sim.registry import GameData
from esports_sim.schemas import Player
from esports_sim.schemas.common import Playstyle, Role


def _player(age: int, ca: float, tags: list[str], potential: float = 0.0) -> Player:
    return Player(
        id=f"t_{age}_{int(ca)}",
        handle="Test",
        age=age,
        role=Role.DUELIST,
        playstyle=Playstyle.ENTRY,
        attributes={a: ca for a in ("aim_precision", "aim_reactivity", "movement")},
        personality_tags=tags,
        potential=potential,
    )


def test_generated_players_have_potential(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=99)
    gen = [p for p in gs.players.values() if p.potential > 0]
    assert gen, "generated players must roll a potential"
    for p in gen:
        assert p.potential >= development.overall(p) - 1e-6


def test_headroom_gates_development() -> None:
    prospect = _player(18, 55.0, [], potential=85.0)
    ceilinged = _player(18, 55.0, [], potential=56.0)
    assert development.dev_multiplier(prospect) > development.dev_multiplier(ceilinged) * 3


def test_traits_shift_decline_age() -> None:
    assert development.decline_age(_player(20, 60, ["prodigy"])) == 26
    assert development.decline_age(_player(20, 60, ["late_bloomer"])) == 31


def test_hidden_curves_are_deterministic_and_diverse() -> None:
    players = [_full(18, 50.0, potential=90.0, pid=f"curve_{i}") for i in range(80)]
    curves = [development.development_curve(p) for p in players]
    assert {c.archetype for c in curves} == {"flash", "early", "steady", "late"}
    assert max(c.decline_age for c in curves) - min(c.decline_age for c in curves) >= 7
    assert max(c.peak_years for c in curves) - min(c.peak_years for c in curves) >= 4
    assert development.development_curve(players[0]) == curves[0]


def test_high_potential_does_not_guarantee_the_same_maximum() -> None:
    players = [
        _full(18, 50.0, potential=90.0, pid=f"realise_{i}")
        for i in range(100)
    ]
    outcomes = [development.natural_potential(p) for p in players]
    assert max(outcomes) - min(outcomes) >= 10.0
    assert min(outcomes) < 80.0 < max(outcomes)


def test_context_can_push_current_ability_past_potential() -> None:
    p = _full(20, 69.0, potential=70.0, pid="supported_outlier")
    p.morale, p.confidence, p.form = 100.0, 95.0, 90.0
    bonus = development.contextual_ceiling_bonus(
        p, mentor_strength=1.0, duo_affinity=96.0, team_chemistry=95.0
    )
    assert development.development_ceiling(p, "aim_precision", bonus) > p.potential
    team = _fake_team()
    for week in range(100):
        p.stamina = 100.0
        training.apply_training(
            team,
            [p],
            "mechanical",
            np.random.default_rng(week),
            support_bonuses={p.id: bonus},
        )
    assert development.overall(p) > p.potential


def test_workhorse_outgrows_lazy() -> None:
    rng = np.random.default_rng(7)
    horse = _player(19, 50.0, ["workhorse"], potential=90.0)
    slack = _player(19, 50.0, ["lazy"], potential=90.0)
    team_h = _fake_team()
    team_l = _fake_team()
    for _ in range(20):
        training.apply_training(team_h, [horse], "mechanical", rng)
        training.apply_training(team_l, [slack], "mechanical", rng)
    assert development.overall(horse) > development.overall(slack)


def _fake_team():
    from esports_sim.schemas import Team

    return Team(id="t", name="T", tag="T")


def test_scout_report_bands_contain_truth_and_tighten(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=5)
    pid = sorted(gs.free_agent_ids)[0]
    p = gs.players[pid]
    ca = development.stars(development.overall(p))
    pa = development.stars(development.potential_of(p))
    loose = development.scout_report(gs, p, 0.1)
    tight = development.scout_report(gs, p, 1.0)
    for rep in (loose, tight):
        assert rep["ca_stars"][0] <= ca <= rep["ca_stars"][1]
        assert rep["pa_stars"][0] <= pa <= rep["pa_stars"][1]
    assert (tight["ca_stars"][1] - tight["ca_stars"][0]) <= (
        loose["ca_stars"][1] - loose["ca_stars"][0]
    )
    # Determinism: same inputs, same report.
    assert development.scout_report(gs, p, 0.1) == loose
    # Full coverage reveals the whole character sheet.
    assert tight["traits_hidden"] == 0


# ---------------------------------------------------------------------------
# Per-skill potential, moving potential, mentorship, mentor_skill

_ALL_ATTRS = (
    "aim_precision", "aim_reactivity", "movement", "game_sense", "utility_usage",
    "positioning", "clutch_factor", "tilt_resistance", "composure", "comms_quality",
)


def _full(age, ca, tags=None, potential=0.0, pid=None):
    return Player(
        id=pid or f"f_{age}_{int(ca)}_{potential}",
        handle="F", age=age, role=Role.DUELIST, playstyle=Playstyle.ENTRY,
        attributes={a: float(ca) for a in _ALL_ATTRS},
        personality_tags=list(tags or []), potential=potential,
    )


def test_skill_ceiling_default_override_and_floor() -> None:
    p = _full(20, 60.0, potential=80.0)
    base = development.skill_ceiling(p, "aim_precision")
    assert base >= p.attr("aim_precision")            # never below current
    p.skill_potential["aim_precision"] = 88.0
    assert development.skill_ceiling(p, "aim_precision") == 88.0  # explicit wins
    p.skill_potential["movement"] = 10.0              # a low override can't drop it
    assert development.skill_ceiling(p, "movement") == p.attr("movement")


def test_adjust_potential_raises_and_soft_caps_without_rewriting_ca() -> None:
    p = _full(20, 60.0, potential=70.0)
    d = development.adjust_potential(p, 2.0, attrs=["aim_precision"])
    assert d > 0 and p.potential > 70.0
    assert "aim_precision" in p.skill_potential
    assert p.potential >= 70.0
    top = _full(20, 90.0, potential=94.0)
    development.adjust_potential(top, 12.0)
    assert top.potential <= 95.0                      # soft cap holds


def test_curve_shape_changes_when_growth_arrives() -> None:
    players = [_full(18, 55.0, potential=88.0, pid=f"timing_{i}") for i in range(100)]
    flash = next(p for p in players if development.development_curve(p).archetype == "flash")
    late = next(p for p in players if development.development_curve(p).archetype == "late")
    flash.age = late.age = 18
    assert development.curve_growth_multiplier(flash) > development.curve_growth_multiplier(late)
    flash.age = late.age = 25
    assert development.curve_growth_multiplier(late) > development.curve_growth_multiplier(flash)


def test_moment_bump_scales_down_with_age() -> None:
    young = development.moment_potential_bump(_full(19, 60.0, potential=70.0), 3.0)
    old = development.moment_potential_bump(_full(29, 60.0, potential=70.0), 3.0)
    assert young > old
    assert old == 0.0                                 # past the plasticity window


def test_mentor_skill_low_for_young_high_for_veteran() -> None:
    young = development.mentor_skill(_full(19, 65.0), 0)
    vet = development.mentor_skill(_full(30, 65.0, ["veteran", "leader"]), 8)
    assert young < 35.0                               # young almost never teach well
    assert vet > 70.0
    assert young < vet


def test_potential_projection_contains_truth_and_narrows_with_age() -> None:
    young = _full(18, 60.0, potential=82.0, pid="proj_young")
    old = _full(28, 78.0, potential=82.0, pid="proj_old")
    ylo, yhi = development.potential_projection(young, own=True)
    olo, ohi = development.potential_projection(old, own=True)
    assert ylo <= development.potential_of(young) <= yhi
    assert olo <= development.potential_of(old) <= ohi
    assert (yhi - ylo) > (ohi - olo)                  # youth reads wider


def test_potential_projection_uses_center_upper_and_lower_anchors() -> None:
    modes = set()
    for i in range(100):
        p = _full(24, 60.0, potential=75.0, pid=f"projection_anchor_{i}")
        pa = development.potential_of(p)
        lo, hi = development.potential_projection(p, own=True)
        if lo == pa:
            modes.add("lower")
        elif hi == pa:
            modes.add("upper")
        elif round(pa - lo, 1) == round(hi - pa, 1):
            modes.add("center")
    assert modes == {"center", "upper", "lower"}


def test_good_performance_coach_tightens_own_roster_projection() -> None:
    p = _full(21, 60.0, potential=75.0, pid="coach_projection")
    baseline = development.potential_projection(p, own=True)
    coached = development.potential_projection(
        p, own=True, performance_coach_quality=90.0
    )
    assert coached[1] - coached[0] < baseline[1] - baseline[0]
    assert coached[0] <= development.potential_of(p) <= coached[1]
    # Performance staff do not improve reads of players outside their roster.
    assert development.potential_projection(
        p, progress=0.5, own=False, performance_coach_quality=90.0
    ) == development.potential_projection(p, progress=0.5, own=False)


def test_scout_verdict_projects_a_band_not_a_number(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=5)
    p = gs.players[sorted(gs.free_agent_ids)[0]]
    rep = development.scout_report(gs, p, 1.0)
    assert rep["verdict"] and "projects to" in rep["verdict"]
    lo, hi = rep["pa_projection"]
    assert lo < hi                                    # always a range, never exact


def test_mentorship_raises_protege_ceiling_on_mentor_best_skill(game_data: GameData) -> None:
    from esports_sim.manager.state import CareerStats

    gs = new_campaign(game_data, seed=11)
    tid = sorted(gs.teams)[0]
    roster = sorted(gs.roster(tid), key=lambda q: q.id)
    pro, men = roster[0], roster[1]
    pro.age, men.age = 19, 29
    for a in _ALL_ATTRS:
        men.attributes[a] = 70.0
        pro.attributes[a] = 55.0
    men.attributes["aim_precision"] = 92.0            # a great aimer
    men.personality_tags = sorted({*men.personality_tags, "veteran", "leader"})
    pro.potential, pro.skill_potential = 75.0, {}
    gs.career_stats[men.id] = CareerStats(seasons=8)

    # No-op with no mentorship set (gate-safety).
    gs.mentorships = {}
    development.apply_mentorship_growth(gs)
    assert pro.skill_potential == {}

    gs.mentorships = {pro.id: men.id}
    before = development.skill_ceiling(pro, "aim_precision")
    for _ in range(20):
        development.apply_mentorship_growth(gs)
    after = development.skill_ceiling(pro, "aim_precision")
    assert after > before                             # aim ceiling lifted
    assert after <= men.attributes["aim_precision"] + 1e-6  # never past the mentor


def test_offseason_trait_unlock_fires_once(game_data: GameData) -> None:
    from esports_sim.manager.state import CareerStats

    gs = new_campaign(game_data, seed=3)
    tid = sorted(gs.teams)[0]
    p = sorted(gs.roster(tid), key=lambda q: q.id)[0]
    p.personality_tags = [t for t in p.personality_tags if t != "clutch_gene"]
    gs.career_stats[p.id] = CareerStats(clutches=30)
    development.offseason_trait_unlocks(gs)
    assert "clutch_gene" in p.personality_tags
    pa1 = p.potential
    development.offseason_trait_unlocks(gs)            # idempotent
    assert p.personality_tags.count("clutch_gene") == 1
    assert p.potential == pa1                          # no second ceiling bump


def test_pure_aimer_development_curve_and_offseason_aging() -> None:
    # 1. Curve Parameters
    for seed in range(50):
        p = _full(18, 60.0, tags=["pure_aimer"], potential=85.0, pid=f"pa_{seed}")
        
        # Test development_curve function directly
        dc = development.development_curve(p)
        assert dc.archetype == "flash"
        assert 18 <= dc.growth_peak_age <= 20
        assert dc.realization >= 0.9
        assert dc.decline_age in (23, 24)
        
        # Test initialize_player_seed_variance
        development.initialize_player_seed_variance(p, campaign_seed=seed)
        dc2 = p.development_curve
        assert dc2.archetype == "flash"
        assert 18 <= dc2.growth_peak_age <= 20
        assert dc2.realization >= 0.9
        assert dc2.decline_age in (23, 24)

        # Test assign_development_curve
        p3 = _full(18, 60.0, tags=["pure_aimer"], potential=85.0, pid=f"pa3_{seed}")
        rng = np.random.default_rng(seed)
        development.assign_development_curve(p3, rng)
        dc3 = p3.development_curve
        assert dc3.archetype == "flash"
        assert 18 <= dc3.growth_peak_age <= 20
        assert dc3.realization >= 0.9
        assert dc3.decline_age in (23, 24)

    # 2. Offseason aging decay
    p = _full(22, 80.0, tags=["pure_aimer"], potential=95.0, pid="pa_decay")
    dc = development.development_curve(p)
    turn = dc.decline_age
    p.age = turn - 1  # will become turn during apply_offseason_aging
    
    original_attrs = {a: p.attr(a) for a in _ALL_ATTRS}
    
    rng = np.random.default_rng(42)
    training.apply_offseason_aging(p, rng)
    
    assert p.age == turn
    decline_val = (p.age - (turn - 1)) * 0.8 * development.curve_decline_multiplier(p)
    
    aim_attrs = ["aim_precision", "aim_reactivity"]
    other_attrs = [
        "movement", "game_sense", "positioning", "utility_usage",
        "clutch_factor", "tilt_resistance", "composure", "comms_quality"
    ]
    
    for a in aim_attrs:
        decay = original_attrs[a] - p.attr(a)
        base_decay = decay / 0.15
        ratio = base_decay / decline_val
        assert 0.7 - 1e-5 <= ratio <= 1.3 + 1e-5
        
    for a in other_attrs:
        decay = original_attrs[a] - p.attr(a)
        base_decay = decay / 1.5
        ratio = base_decay / decline_val
        assert 0.7 - 1e-5 <= ratio <= 1.3 + 1e-5


def test_seed_based_volatility_distribution() -> None:
    # Young players: +/- 6 swing
    young_swings = []
    for seed in range(200):
        p = _full(20, 50.0, potential=80.0, pid=f"young_{seed}")
        development.initialize_player_seed_variance(p, campaign_seed=seed)
        swing = p.potential - 80.0
        assert -6.0 - 1e-5 <= swing <= 6.0 + 1e-5
        young_swings.append(swing)
        
    # Rookie players: +/- 6 swing
    rookie_swings = []
    for seed in range(200):
        p = _full(24, 50.0, tags=["rookie"], potential=80.0, pid=f"rookie_{seed}")
        development.initialize_player_seed_variance(p, campaign_seed=seed)
        swing = p.potential - 80.0
        assert -6.0 - 1e-5 <= swing <= 6.0 + 1e-5
        rookie_swings.append(swing)
        
    # Prodigy players: +/- 6 swing
    prodigy_swings = []
    for seed in range(200):
        p = _full(25, 50.0, tags=["prodigy"], potential=80.0, pid=f"prodigy_{seed}")
        development.initialize_player_seed_variance(p, campaign_seed=seed)
        swing = p.potential - 80.0
        assert -6.0 - 1e-5 <= swing <= 6.0 + 1e-5
        prodigy_swings.append(swing)
        
    # Verify they actually vary (are not all 0)
    assert len(set(young_swings)) > 10
    assert len(set(rookie_swings)) > 10
    assert len(set(prodigy_swings)) > 10
    
    # Veteran players: 0 swing
    for seed in range(50):
        p = _full(26, 50.0, potential=80.0, pid=f"vet_{seed}")
        development.initialize_player_seed_variance(p, campaign_seed=seed)
        swing = p.potential - 80.0
        assert abs(swing) < 1e-5

    # Player with veteran tag: 0 swing
    for seed in range(50):
        p = _full(22, 50.0, tags=["veteran"], potential=80.0, pid=f"vet_tag_{seed}")
        development.initialize_player_seed_variance(p, campaign_seed=seed)
        swing = p.potential - 80.0
        assert abs(swing) < 1e-5

