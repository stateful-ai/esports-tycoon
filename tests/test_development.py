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
