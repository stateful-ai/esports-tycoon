"""Named rival managers: persona lifecycle, board reviews, migration,
manager-vs-manager heat, and the web surfaces.

Everything here is blake2-derived (no rng stream), so the assertions are
mostly about determinism and the append-only chronicle trail.
"""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import (
    advance_week,
    career,
    new_campaign,
    rival_managers,
)
from esports_sim.manager.state import SCHEMA_VERSION, GameState

SEED = 424242


@pytest.fixture(scope="module")
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=SEED, user_team_id="team_nexus")


# -- creation ------------------------------------------------------------------


def test_every_ai_tier1_org_gets_a_persona(campaign: GameState) -> None:
    ai_t1 = {
        tid
        for tid, t in campaign.teams.items()
        if t.tier == 1 and not campaign.is_human(tid)
    }
    assert set(campaign.rival_managers) == ai_t1
    assert campaign.user_team_id not in campaign.rival_managers
    for tid in sorted(ai_t1):
        rm = campaign.rival_managers[tid]
        assert rm.team_id == tid
        assert rm.id.startswith("rm_")
        assert len(rm.name.split()) == 2
        assert rm.tenure_start == 1
        assert rm.stint == 0
        assert 0.0 <= rm.patience <= 100.0
    # Founding managers just exist — no appointment flood at new game.
    assert not [
        e for e in campaign.chronicle
        if e.kind == "appointment" and e.data.get("rm")
    ]


def test_personas_are_pure_functions_of_seed_and_org(game_data) -> None:
    a = new_campaign(game_data, seed=SEED, user_team_id="team_nexus")
    b = new_campaign(game_data, seed=SEED, user_team_id="team_nexus")
    assert {t: rm.model_dump() for t, rm in a.rival_managers.items()} == {
        t: rm.model_dump() for t, rm in b.rival_managers.items()
    }
    # A different seed meets different people (compare the orgs that exist
    # in both worlds — generated org ids themselves vary with the seed).
    c = new_campaign(game_data, seed=SEED + 1, user_team_id="team_nexus")
    shared = sorted(set(a.rival_managers) & set(c.rival_managers))
    assert shared
    assert any(
        c.rival_managers[t].name != a.rival_managers[t].name for t in shared
    )


def test_identity_word_is_pure_and_from_the_vocabulary() -> None:
    word = rival_managers.identity_for_id("rm_deadbeef")
    assert word == rival_managers.identity_for_id("rm_deadbeef")
    assert word in set(rival_managers._IDENTITY.values())


# -- offseason board review ----------------------------------------------------


def _region_order(gs: GameState):
    region = str(gs.teams[gs.user_team_id].region)
    return region, gs.standings_order(region, tier=1)


def _stack_table(gs: GameState, order: list[str]) -> None:
    """Make the current order the FINAL table: descending wins."""
    for i, tid in enumerate(order):
        rec = gs.standings[tid]
        rec.wins = len(order) - i
        rec.losses = i
        rec.rounds_won = 13 * rec.wins
        rec.rounds_lost = 13 * rec.losses


def test_struggling_org_replaces_its_manager(campaign: GameState) -> None:
    gs = campaign.model_copy(deep=True)
    gs.season = 3  # every founder has served >= MIN_SEASONS
    region, order = _region_order(gs)
    order = [t for t in order if not gs.is_human(t)] + [
        t for t in order if gs.is_human(t)
    ]
    _stack_table(gs, order)
    _, final = _region_order(gs)
    bottom = next(t for t in reversed(final) if not gs.is_human(t))
    top = next(t for t in final if not gs.is_human(t))
    old = gs.rival_managers[bottom].model_copy(deep=True)
    gs.rival_managers[bottom].patience = rival_managers.FIRE_BAR + 1.0
    top_before = gs.rival_managers[top].patience

    lines = rival_managers.offseason_tick(gs)

    new = gs.rival_managers[bottom]
    assert new.id != old.id
    assert new.stint == old.stint + 1
    assert new.tenure_start == gs.season + 1
    kinds = [
        (e.kind, e.team_id)
        for e in gs.chronicle
        if e.data.get("rm") in (old.id, new.id)
    ]
    assert ("dismissal", bottom) in kinds
    assert ("appointment", bottom) in kinds
    assert any(old.name in line and new.name in line for line in lines)
    # The table-topper's board warmed instead.
    assert gs.rival_managers[top].patience > top_before
    assert gs.rival_managers[top].id == campaign.rival_managers[top].id


def test_offseason_review_is_deterministic(campaign: GameState) -> None:
    runs = []
    for _ in range(2):
        gs = campaign.model_copy(deep=True)
        gs.season = 3
        _, order = _region_order(gs)
        _stack_table(gs, order)
        for tid in sorted(gs.rival_managers):
            gs.rival_managers[tid].patience = 26.0
        rival_managers.offseason_tick(gs)
        runs.append(
            (
                {t: rm.model_dump() for t, rm in gs.rival_managers.items()},
                [e.model_dump() for e in gs.chronicle],
                list(gs.news),
            )
        )
    assert runs[0] == runs[1]


def test_tenure_milestones_are_chronicled(campaign: GameState) -> None:
    gs = campaign.model_copy(deep=True)
    gs.season = 5  # founders (tenure_start=1) hit the 5-season mark
    _, order = _region_order(gs)
    _stack_table(gs, order)
    survivor = next(t for t in order[: len(order) // 2] if not gs.is_human(t))
    rival_managers.offseason_tick(gs)
    rm = gs.rival_managers[survivor]
    assert any(
        e.kind == "milestone" and e.data.get("rm") == rm.id
        for e in gs.chronicle
    )


# -- human handovers -----------------------------------------------------------


def test_human_takeover_drops_persona_and_vacancy_refills(
    campaign: GameState,
) -> None:
    gs = campaign.model_copy(deep=True)
    tid = sorted(gs.rival_managers)[0]
    founder = gs.rival_managers[tid]
    # A human takes over (the real flow chronicles their appointment).
    gs.human_team_ids.append(tid)
    career.create_seat(gs, tid, "Ada Test")
    rival_managers.ensure_personas(gs)
    assert tid not in gs.rival_managers
    # ...and later leaves: the org appoints a NEW named manager (never the
    # founder again — the chronicle remembers the era in between).
    gs.human_team_ids.remove(tid)
    seat = gs.manager_for(tid)
    seat.team_id = ""
    rival_managers.ensure_personas(gs)
    successor = gs.rival_managers[tid]
    assert successor.id != founder.id
    assert successor.stint >= 1
    assert any(
        e.kind == "appointment" and e.data.get("rm") == successor.id
        for e in gs.chronicle
    )


# -- heat + readers --------------------------------------------------------------


def test_manager_heat_rides_org_rivalry_scaled_by_tenure_overlap(
    campaign: GameState,
) -> None:
    gs = campaign.model_copy(deep=True)
    a = gs.user_team_id
    b = sorted(gs.rival_managers)[0]
    key = "|".join(sorted((a, b)))
    gs.rivalries[key] = 60.0
    gs.season = 4  # both in post since S1 -> full overlap
    assert rival_managers.manager_heat(gs, a, b) == 60.0
    gs.rival_managers[b].tenure_start = gs.season  # fresh hire across the aisle
    assert rival_managers.manager_heat(gs, a, b) == 20.0
    gs.rivalries[key] = 0.0
    assert rival_managers.manager_heat(gs, a, b) == 0.0


def test_profile_view_shapes(campaign: GameState) -> None:
    gs = campaign
    keys = {"name", "human", "identity", "since", "seasons", "honours", "heat"}
    ai = sorted(gs.rival_managers)[0]
    view = rival_managers.profile_view(gs, ai)
    assert set(view) == keys
    assert view["human"] is False
    own = rival_managers.profile_view(gs, gs.user_team_id)
    assert own is not None and own["human"] is True and own["heat"] is None
    tier2 = next(t for t in sorted(gs.teams) if gs.teams[t].tier == 2)
    assert rival_managers.profile_view(gs, tier2) is None
    spot = rival_managers.spotlight_view(gs, ai)
    assert set(spot) == {"name", "identity"}


# -- persistence ---------------------------------------------------------------


def test_v31_save_backfills_personas(campaign: GameState, tmp_path) -> None:
    old = json.loads(campaign.model_dump_json())
    old["schema_version"] = 31
    old.pop("rival_managers")
    path = tmp_path / "v31.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == SCHEMA_VERSION
    ai_t1 = {
        tid
        for tid, t in loaded.teams.items()
        if t.tier == 1 and not loaded.is_human(tid)
    }
    assert set(loaded.rival_managers) == ai_t1
    for tid in sorted(ai_t1):
        rm = loaded.rival_managers[tid]
        assert rm.name and rm.id.startswith("rm_")
        assert 1 <= rm.tenure_start <= loaded.season
    # The backfill is a pure function of the save: load twice, same league.
    again = GameState.load(path)
    assert {t: rm.model_dump() for t, rm in again.rival_managers.items()} == {
        t: rm.model_dump() for t, rm in loaded.rival_managers.items()
    }


def test_save_roundtrip_keeps_personas(campaign: GameState, tmp_path) -> None:
    path = tmp_path / "current.json"
    campaign.save(path)
    loaded = GameState.load(path)
    assert {t: rm.model_dump() for t, rm in loaded.rival_managers.items()} == {
        t: rm.model_dump() for t, rm in campaign.rival_managers.items()
    }


# -- hands-off determinism -------------------------------------------------------


def test_hands_off_weeks_stay_byte_identical(game_data) -> None:
    dumps = []
    for _ in range(2):
        gs = new_campaign(game_data, seed=97, user_team_id="team_nexus")
        for _ in range(2):
            advance_week(gs, game_data)
        dumps.append(gs.model_dump_json())
    assert dumps[0] == dumps[1]
