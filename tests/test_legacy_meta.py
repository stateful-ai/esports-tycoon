"""Phase 5 of Legacy Mode: strategy diffusion (winners get copied) and
chronicled meta eras."""

from __future__ import annotations

import numpy as np
import pytest

from esports_sim.manager import campaign as camp
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState, TeamSeasonStats
from esports_sim.registry import load_all
from esports_sim.rng.tree import RngTree


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=666)


def _stats(maps=6, atk=60, atk_w=40, deff=60, def_w=40) -> TeamSeasonStats:
    return TeamSeasonStats(
        maps=maps, atk_rounds=atk, atk_won=atk_w,
        def_rounds=deff, def_won=def_w, pistols=4, pistols_won=2,
    )


def test_meta_identity_reads_the_winners(campaign):
    gs = campaign
    tier1 = [t for t in sorted(gs.teams) if gs.teams[t].tier == 1]
    hot, cold = tier1[0], tier1[1]
    gs.team_stats[hot] = _stats(atk_w=40, def_w=40)  # 67% rwr
    gs.team_stats[cold] = _stats(atk_w=20, def_w=20)  # 33% rwr
    gs.teams[hot].tactics.aggression = 80.0
    meta = camp._meta_identity(gs)
    assert meta is not None
    assert meta["aggression"] == 80.0  # only the winner defines the meta


def test_strugglers_copy_the_meta(campaign):
    gs = campaign
    ai = [
        t for t in sorted(gs.teams)
        if gs.teams[t].tier == 1 and not gs.is_human(t)
    ]
    winner, loser = ai[0], ai[1]
    gs.team_stats[winner] = _stats(atk_w=40, def_w=40)
    gs.team_stats[loser] = _stats(atk_w=20, def_w=20)
    gs.teams[winner].tactics.aggression = 85.0
    gs.teams[loser].tactics.aggression = 30.0
    before = gs.teams[loser].tactics.aggression
    rng = RngTree(1).derive("t")
    camp._adapt_ai_tactics(gs, rng)
    after = gs.teams[loser].tactics.aggression
    # The struggler moved TOWARD the aggressive meta (target ~67), i.e.
    # decisively up from 30 — not back toward plain 50 and not away.
    assert after > before + 0.3


def test_meta_era_chronicled(campaign):
    gs = campaign
    for t in gs.teams.values():
        if t.tier == 1:
            t.tactics.aggression = 62.0
    camp._record_meta_era(gs)
    eras = [e for e in gs.chronicle if e.kind == "meta_shift"]
    assert eras and "aggression era" in eras[0].text
    assert eras[0].data["dial"] == "aggression"


def test_no_era_when_league_is_neutral(campaign):
    gs = campaign
    for t in gs.teams.values():
        if t.tier == 1:
            t.tactics.aggression = 50.0
            t.tactics.pace = 50.0
            t.tactics.util_discipline = 50.0
            t.tactics.map_control = 50.0
    camp._record_meta_era(gs)
    assert not [e for e in gs.chronicle if e.kind == "meta_shift"]


def test_multiseason_diffusion_stays_bounded(game_data):
    """Two seasons of diffusion never push the league outside the dial
    clamp or destabilize the campaign determinism contract."""
    a = new_campaign(game_data, seed=99)
    b = new_campaign(game_data, seed=99)
    for _ in range(55):
        advance_week(a, game_data)
        advance_week(b, game_data)
        if a.season >= 3:
            break
    assert a.model_dump_json() == b.model_dump_json()
    for t in a.teams.values():
        for dial in camp._ADAPT_DIALS:
            assert 15.0 <= getattr(t.tactics, dial) <= 85.0
