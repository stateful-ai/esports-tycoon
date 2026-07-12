"""Regression coverage for site-scoped, context-aware utility resolution."""

from __future__ import annotations

from esports_sim.registry import load_all
from esports_sim.sim import engine as eng


def _sim(seed: int = 1) -> eng._MatchSim:
    gd = load_all()
    return eng._MatchSim(gd, "team_nexus", "team_vanguard", "haven", seed)


def _pid_with_agent(sim: eng._MatchSim, agent_id: str) -> str:
    return next(pid for pid, ps in sim.p.items() if ps.agent_id == agent_id)


def test_smoke_is_scoped_to_its_called_site_and_logged() -> None:
    sim = _sim()
    omen = _pid_with_agent(sim, "omen")
    sim.p[omen].charges = {"omen_dark_cover": 1}

    sim._execute_utility(
        [omen], 10, ("test",), flash_side="defense",
        target_site="a", intent="execute",
    )

    assert sim._smoke_until_by_site.get("a", -1) >= 10
    assert "b" not in sim._smoke_until_by_site
    utility = [event for event in sim.log if event.type == "round.utility_used"]
    assert len(utility) == 1
    assert utility[0].ability_id == "omen_dark_cover"
    assert utility[0].target_callout == "a_site"


def test_flash_waits_for_a_duel_at_its_target_site() -> None:
    sim = _sim()
    omen = _pid_with_agent(sim, "omen")
    sim.p[omen].charges = {"omen_paranoia": 1}
    sim._execute_utility(
        [omen], 10, ("test",), flash_side="defense",
        target_site="a", intent="execute",
    )
    assert len(sim._pending_flashes) == 1

    attacker = sim.p[_pid_with_agent(sim, "raze")]
    defender = sim.p[omen]
    sim._apply_pending_flashes(attacker, defender, "b", 11)
    assert defender.flash_until == -1
    assert len(sim._pending_flashes) == 1

    sim._apply_pending_flashes(attacker, defender, "a", 11)
    assert defender.flash_until == 11 + eng.C.FLASH_TICKS
    assert defender.flashed_by == omen
    assert not sim._pending_flashes


def test_mobility_ability_shortens_the_move_it_opens() -> None:
    normal = _sim(2)
    normal_jett = _pid_with_agent(normal, "jett")
    normal._place(normal_jett, normal.map.attacker_spawn, "enter", ("test",))
    normal._begin_move(
        normal.p[normal_jett], "a_lobby", 1, ("test",), "enter"
    )
    normal_eta = normal.p[normal_jett].move_eta

    dashed = _sim(2)
    dashed_jett = _pid_with_agent(dashed, "jett")
    dashed._place(dashed_jett, dashed.map.attacker_spawn, "enter", ("test",))
    dashed.p[dashed_jett].charges = {"jett_tailwind": 1}
    dashed._execute_utility(
        [dashed_jett], 1, ("test",), flash_side="defense",
        target_site="a", intent="execute",
    )
    dashed._begin_move(
        dashed.p[dashed_jett], "a_lobby", 1, ("test",), "enter"
    )

    assert dashed.p[dashed_jett].mobility_until == -1
    assert dashed.p[dashed_jett].move_eta < normal_eta
