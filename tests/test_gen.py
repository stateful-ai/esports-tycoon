"""Player/team generation: regional name flavour, role-appropriate
attribute archetypes, and the team-name-pool guard.

All generation is deterministic off the campaign RNG tree and never runs
inside the match engine, so none of this touches the golden fixture.
"""

from __future__ import annotations

import numpy as np
import pytest

from esports_sim.manager import gen
from esports_sim.registry import load_all
from esports_sim.schemas.common import Playstyle, Region, Role


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_names_are_region_appropriate() -> None:
    """A player generated for a region draws from that region's name pool,
    not the mixed global list (no more 'Minho Nakamura' in EMEA)."""
    gd = load_all()
    rng = _rng(1)
    for region in (Region.AMERICAS, Region.EMEA, Region.PACIFIC):
        firsts = set(gen._REGION_FIRST_NAMES[region])
        lasts = set(gen._REGION_LAST_NAMES[region])
        for i in range(30):
            p = gen.generate_player(
                rng, f"p{region}{i}", Playstyle.ENTRY, Role.DUELIST, 70.0, gd,
                region=region,
            )
            first, last = p.real_name.split(" ", 1)
            assert first in firsts and last in lasts


def test_archetypes_are_role_appropriate() -> None:
    """Entries out-aim IGLs, IGLs out-think entries — the playstyle
    archetypes actually shape attributes."""
    gd = load_all()

    def avg(playstyle: Playstyle, role: Role, attr: str) -> float:
        rng = _rng(7)
        vals = [
            gen.generate_player(
                rng, f"x{i}", playstyle, role, 70.0, gd, region=Region.EMEA
            ).attr(attr)
            for i in range(40)
        ]
        return sum(vals) / len(vals)

    assert avg(Playstyle.ENTRY, Role.DUELIST, "aim_reactivity") > avg(
        Playstyle.IGL, Role.CONTROLLER, "aim_reactivity"
    )
    assert avg(Playstyle.IGL, Role.CONTROLLER, "game_sense") > avg(
        Playstyle.ENTRY, Role.DUELIST, "game_sense"
    )


def test_generation_is_deterministic() -> None:
    gd = load_all()
    a = gen.generate_player(_rng(3), "p", Playstyle.AWPER, Role.DUELIST, 68.0, gd)
    b = gen.generate_player(_rng(3), "p", Playstyle.AWPER, Role.DUELIST, 68.0, gd)
    assert a.model_dump_json() == b.model_dump_json()


def test_team_name_pool_exhaustion_raises() -> None:
    """Asking for more unique team names than the pool holds fails loudly
    instead of silently generating fewer teams."""
    gd = load_all()
    all_names = {n for n, _ in gen._TEAM_NAMES}
    # Leave only two names free, then ask for five.
    used = set(list(all_names)[:-2])
    with pytest.raises(ValueError):
        gen.generate_league_teams(
            _rng(0), gd, n_teams=5, region=Region.AMERICAS, used_names=used
        )
