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
    assert development.decline_age(_player(20, 60, [])) == 28


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


def test_adjust_potential_raises_capped_and_never_below_ca() -> None:
    p = _full(20, 60.0, potential=70.0)
    d = development.adjust_potential(p, 2.0, attrs=["aim_precision"])
    assert d > 0 and p.potential > 70.0
    assert "aim_precision" in p.skill_potential
    assert p.potential >= development.overall(p)
    top = _full(20, 90.0, potential=94.0)
    development.adjust_potential(top, 12.0)
    assert top.potential <= 95.0                      # soft cap holds


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
