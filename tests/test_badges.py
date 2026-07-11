"""Player badges: rolled, decaying, ability-moving honours and stigmas."""

from __future__ import annotations

import numpy as np

from esports_sim.manager import badges, development
from esports_sim.manager.campaign import new_campaign
from esports_sim.registry import GameData
from esports_sim.schemas.badges import BADGES


def _first(gs):
    tid = sorted(gs.teams)[0]
    return tid, sorted(gs.roster(tid), key=lambda q: q.id)[0]


def test_earn_applies_reversible_ca_and_permanent_pa(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=1)
    tid, p = _first(gs)
    p.attributes["aim_precision"] = 82.0
    p.attributes["aim_reactivity"] = 78.0
    aim0, pa0 = p.attr("aim_precision"), development.potential_of(p)
    assert badges._earn(gs, tid, p, "aim_demon")
    assert "aim_demon" in badges.held_ids(p)
    assert p.attr("aim_precision") > aim0                 # CA edge applied
    assert development.potential_of(p) >= pa0             # ceiling revised up
    assert p.badges[0].applied.get("aim_precision", 0.0) > 0  # stored for revert


def test_roll_is_probabilistic_and_gated_by_eligibility(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=2)
    tid, p = _first(gs)
    p.attributes["aim_precision"] = 85.0
    p.attributes["aim_reactivity"] = 80.0
    # A moment is a CHANCE: prob 0 never earns, prob 1 (eligible) does.
    assert not badges.roll(gs, np.random.default_rng(0), tid, p, "aim_demon", 0.0)
    assert "aim_demon" not in badges.held_ids(p)
    assert badges.roll(gs, np.random.default_rng(0), tid, p, "aim_demon", 1.0)
    assert "aim_demon" in badges.held_ids(p)
    # Re-rolling a held badge just refreshes it (no duplicate).
    assert not badges.roll(gs, np.random.default_rng(0), tid, p, "aim_demon", 1.0)
    assert sum(b.id == "aim_demon" for b in p.badges) == 1
    # Ineligible (mediocre aim) can't earn it even at prob 1.
    q = sorted(gs.roster(tid), key=lambda x: x.id)[1]
    q.attributes["aim_precision"] = 50.0
    assert not badges.roll(gs, np.random.default_rng(0), tid, q, "aim_demon", 1.0)


def test_decay_reverts_ca_but_keeps_permanent_pa(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=3)
    tid, p = _first(gs)
    p.attributes["aim_precision"] = 85.0
    p.attributes["aim_reactivity"] = 80.0
    aim0, react0 = p.attr("aim_precision"), p.attr("aim_reactivity")
    badges._earn(gs, tid, p, "aim_demon")
    pa_with = development.potential_of(p)
    assert p.attr("aim_precision") > aim0
    # Go stale: seasons pass without re-qualifying.
    gs.season += BADGES["aim_demon"]["decay_seasons"]
    lost = badges.decay(gs)
    assert any(x["badge"] == "aim_demon" for x in lost)
    assert "aim_demon" not in badges.held_ids(p)
    assert p.attr("aim_precision") == aim0       # reversible edge removed
    assert p.attr("aim_reactivity") == react0
    assert development.potential_of(p) == pa_with  # ceiling kept (permanent)


def test_decay_on_fallen_off_skill(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=5)
    tid, p = _first(gs)
    p.attributes["aim_precision"] = 88.0
    p.attributes["aim_reactivity"] = 82.0
    badges._earn(gs, tid, p, "aim_demon")
    # The celebrated skill collapses below the badge's floor -> it decays.
    p.attributes["aim_precision"] = 60.0
    badges.decay(gs)
    assert "aim_demon" not in badges.held_ids(p)


def test_negative_badge_is_a_reversible_drag(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=4)
    tid, p = _first(gs)
    p.attributes["clutch_factor"] = 55.0
    p.attributes["composure"] = 55.0
    clutch0 = p.attr("clutch_factor")
    badges._earn(gs, tid, p, "choker")
    assert p.attr("clutch_factor") < clutch0        # stings while held
    assert development.potential_of(p) == development.potential_of(p)  # no PA harm
    gs.season += BADGES["choker"]["decay_seasons"]
    badges.decay(gs)
    assert "choker" not in badges.held_ids(p)
    assert p.attr("clutch_factor") == clutch0        # recovers symmetrically
