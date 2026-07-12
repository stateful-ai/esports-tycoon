"""Role/style current ability is hidden, deterministic, and comfort-aware."""

from esports_sim.manager import development, role_fit
from esports_sim.schemas import Player, Playstyle, Role, Team


def _player() -> Player:
    return Player(
        id="role_test", handle="RoleTest", age=23,
        role=Role.DUELIST, playstyle=Playstyle.ENTRY,
        attributes={
            "aim_precision": 80, "aim_reactivity": 82, "movement": 76,
            "game_sense": 55, "utility_usage": 52, "positioning": 54,
            "clutch_factor": 68, "tilt_resistance": 60, "composure": 62,
            "comms_quality": 58,
        },
    )


def test_overall_remains_plain_attribute_mean_but_assignment_changes_ca():
    p = _player()
    overall = development.overall(p)
    duelist_ca = role_fit.current_ability(p)
    role_fit.change_assignment(p, Role.CONTROLLER, Playstyle.IGL)
    controller_ca = role_fit.current_ability(p)
    assert development.overall(p) == overall
    assert duelist_ca > controller_ca
    assert role_fit.assignment_comfort(p) == role_fit.NEW_ASSIGNMENT_COMFORT


def test_comfort_builds_and_hidden_current_ability_stays_a_band():
    p = _player()
    role_fit.change_assignment(p, Role.SENTINEL, Playstyle.ANCHOR)
    before = role_fit.current_ability(p)
    for _ in range(8):
        role_fit.build_comfort(p)
    assert role_fit.assignment_comfort(p) == 100.0
    assert role_fit.current_ability(p) > before
    lo, hi = development.current_ability_projection(p, 1.0)
    assert lo < role_fit.current_ability(p) < hi


def test_returning_to_an_old_assignment_keeps_earned_comfort():
    p = _player()
    role_fit.change_assignment(p, Role.SENTINEL, Playstyle.ANCHOR)
    role_fit.build_comfort(p)
    role_fit.change_assignment(p, Role.DUELIST, Playstyle.ENTRY)
    role_fit.change_assignment(p, Role.SENTINEL, Playstyle.ANCHOR)
    assert role_fit.assignment_comfort(p) == 48.0


def test_igl_assignment_uses_calling_skills_and_builds_match_experience():
    caller = _player()
    teammate = _player().model_copy(update={"id": "teammate"})
    team = Team(id="t", name="Test", tag="T", player_ids=[caller.id, teammate.id])
    role_fit.assign_igl(team, caller.id)
    low_exp = role_fit.igl_effectiveness(caller, role_fit.igl_experience(team, caller.id))
    for _ in range(8):
        role_fit.build_igl_experience(team, {caller.id})
    assert role_fit.igl_experience(team, caller.id) == 100.0
    assert role_fit.igl_effectiveness(caller, 100.0) > low_exp
    assert role_fit.igl_effectiveness(caller, 100.0) == round(
        (caller.attr("game_sense") + caller.attr("comms_quality")) / 2.0, 2
    )
