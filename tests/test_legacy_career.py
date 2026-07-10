"""Phase 1 of Legacy Mode: game modes, career offers, manager contracts,
board reviews, dismissal, the job market, and derived reputation."""

from __future__ import annotations

import pytest

from esports_sim.manager import career, chronicle
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all


@pytest.fixture(scope="module")
def game_data():
    return load_all()


def _legacy(game_data, seed=101) -> GameState:
    offers = career.new_game_offers(new_campaign(game_data, seed=seed), 0)
    offer = offers[0]
    return new_campaign(
        game_data, seed=seed, user_team_id=offer.team_id,
        mode="legacy", career_offer=offer,
    )


def test_sandbox_is_default_and_contract_free(game_data):
    gs = new_campaign(game_data, seed=5)
    assert gs.game_mode == "sandbox"
    seat = gs.manager_for(gs.user_team_id)
    assert seat is not None and seat.contract is None
    # Sandbox boards never review, never fire.
    assert career.review_boards(gs) == []
    assert career.weekly_patience(gs) == []


def test_new_game_offers_are_deterministic_and_distinct(game_data):
    gs = new_campaign(game_data, seed=11)
    a = career.new_game_offers(gs, 0)
    b = career.new_game_offers(gs, 0)
    assert [o.model_dump() for o in a] == [o.model_dump() for o in b]
    assert len(a) == 4
    assert len({o.team_id for o in a}) == 4  # four different orgs
    assert {o.archetype for o in a} == {
        "dynasty", "sleeping_giant", "academy", "rebuilder",
    }
    # A different seat gets its own slate.
    c = career.new_game_offers(gs, 1)
    assert [o.model_dump() for o in c] != [o.model_dump() for o in a]


def test_legacy_campaign_has_contract(game_data):
    gs = _legacy(game_data)
    seat = gs.manager_for(gs.user_team_id)
    assert gs.game_mode == "legacy"
    assert seat is not None and seat.contract is not None
    assert seat.contract.goal in career.GOAL_LABELS
    appts = [e for e in gs.chronicle if e.kind == "appointment"]
    assert appts and appts[0].manager_id == seat.id


def test_board_review_moves_patience_and_fires(game_data):
    gs = _legacy(game_data)
    seat = gs.manager_for(gs.user_team_id)
    mid = seat.id
    tid = seat.team_id
    # Force the review to a miss with patience at the edge.
    seat.contract.goal = "win_champions"
    seat.contract.patience = 30.0
    dismissed = career.review_boards(gs)
    assert dismissed == [mid]
    assert gs.career_offers_by[mid]  # offers derived at review time
    assert all(o.team_id != tid for o in gs.career_offers_by[mid])
    # The seat keeps the team until apply (inboxes must generate first).
    assert seat.team_id == tid
    career.apply_dismissals(gs, dismissed)
    assert seat.team_id == "" and seat.last_team_id == tid
    assert tid not in gs.human_team_ids
    assert career.blocked_seats(gs) == [mid]
    assert gs.seat_for_session(tid) is seat  # old binding still resolves

    # Accepting an offer rebinds everything.
    offer = gs.career_offers_by[mid][0]
    ok, _ = career.accept_offer(gs, mid, offer.team_id)
    assert ok
    assert seat.team_id == offer.team_id
    assert offer.team_id in gs.human_team_ids
    assert gs.user_team_id == offer.team_id  # primary pointer follows
    assert career.blocked_seats(gs) == []
    assert seat.contract is not None and seat.contract.start_season == gs.season


def test_accept_offer_rejects_unoffered_org(game_data):
    gs = _legacy(game_data)
    seat = gs.manager_for(gs.user_team_id)
    seat.contract.goal = "win_champions"
    seat.contract.patience = 10.0
    career.apply_dismissals(gs, career.review_boards(gs))
    not_offered = next(
        t
        for t in sorted(gs.teams)
        if gs.teams[t].tier == 1
        and all(o.team_id != t for o in gs.career_offers_by[seat.id])
    )
    ok, why = career.accept_offer(gs, seat.id, not_offered)
    assert not ok and "not offering" in why


def test_goal_met_renews_or_pleases(game_data):
    gs = _legacy(game_data)
    seat = gs.manager_for(gs.user_team_id)
    seat.contract.goal = "top_half"
    seat.contract.patience = 60.0
    # Rig the table: user team top of its region.
    rec = gs.standings[seat.team_id]
    rec.wins, rec.rounds_won = 99, 999
    before = seat.contract.patience
    dismissed = career.review_boards(gs)
    assert dismissed == []
    assert seat.contract.patience > before


def test_full_legacy_season_ticks_clean(game_data):
    """A legacy campaign runs a whole season without the career layer
    breaking the tick — and stays deterministic."""
    a = _legacy(game_data, seed=31)
    b = _legacy(game_data, seed=31)
    for _ in range(40):
        advance_week(a, game_data)
        advance_week(b, game_data)
        if a.season >= 2:
            break
    assert a.season == b.season and a.week == b.week
    assert [e.model_dump() for e in a.chronicle] == [
        e.model_dump() for e in b.chronicle
    ]
    assert a.model_dump_json() == b.model_dump_json()


def test_web_career_state_and_profile(game_data):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    import esports_sim.web.server as server_mod

    gs = _legacy(game_data, seed=61)
    game = server_mod._Game(game_data, "TESTC", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))
    st = server_mod.state()
    assert st["career"]["mode"] == "legacy"
    assert st["career"]["seat"]["unemployed"] is False
    assert st["career"]["contract"] is not None
    assert st["career"]["contract"]["patience"] > 0
    prof = server_mod.career_profile()
    assert set(prof["reputation"]) >= {
        "player_development",
        "international_success",
        "pressure_handling",
    }
    # The unemployed state serializes offers for the dashboard takeover.
    seat = gs.manager_for(gs.user_team_id)
    seat.contract.goal = "win_champions"
    seat.contract.patience = 1.0
    career.apply_dismissals(gs, career.review_boards(gs))
    st2 = server_mod.state()
    assert st2["career"]["seat"]["unemployed"] is True
    assert st2["career"]["offers"]
    assert st2["career"]["blocked"] is True


def test_unemployment_survives_save_load(tmp_path, game_data):
    """PR #200 review (P1): a dismissed SOLO manager empties
    human_team_ids while user_team_id still names the old org; the
    back-compat default must not resurrect that org as human-run on
    load — it froze the club's AI upkeep."""
    gs = _legacy(game_data, seed=71)
    seat = gs.manager_for(gs.user_team_id)
    old_tid = seat.team_id
    seat.contract.goal = "win_champions"
    seat.contract.patience = 1.0
    career.apply_dismissals(gs, career.review_boards(gs))
    assert gs.human_team_ids == []
    path = tmp_path / "fired.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert loaded.human_team_ids == []  # old org stays AI-run
    assert not loaded.is_human(old_tid)
    assert career.blocked_seats(loaded)  # still on the job market
    # Accepting a job on the LOADED state rebinds cleanly.
    offer = loaded.career_offers_by[seat.id][0]
    ok, _ = career.accept_offer(loaded, seat.id, offer.team_id)
    assert ok and loaded.human_team_ids == [offer.team_id]
    # A blank-slate old save still gets the back-compat default.
    fresh = new_campaign(game_data, seed=71)
    fresh.human_team_ids = []
    refreshed = GameState.model_validate(fresh.model_dump())
    assert refreshed.human_team_ids == [fresh.user_team_id]


def test_patience_only_drifts_on_new_results(game_data):
    """PR #200 review (P2): a split-ending loss streak must not be
    re-penalized every playoff week the team doesn't play."""
    gs = _legacy(game_data, seed=73)
    seat = gs.manager_for(gs.user_team_id)
    tid = seat.team_id
    other = next(
        t for t in sorted(gs.teams) if t != tid and gs.teams[t].tier == 1
    )
    from esports_sim.manager.state import Fixture

    gs.fixtures = [
        Fixture(
            id=f"s1w{w}loss", week=w, stage="regular", team_a=tid,
            team_b=other, played=True, winner_id=other,
        )
        for w in range(1, 6)
    ]
    gs.week = 5  # the last loss happened THIS week -> drift applies
    before = seat.contract.patience
    career.weekly_patience(gs)
    after_hit = seat.contract.patience
    assert after_hit < before
    gs.week = 8  # a playoff week with no new result -> no re-penalty
    career.weekly_patience(gs)
    assert seat.contract.patience == after_hit


def test_lobby_offers_work_with_roster_pack(game_data):
    """PR #200 review (P2): the legacy offer preview must not index
    'team_nexus' into a roster-pack world that doesn't contain it."""
    pytest.importorskip("fastapi")
    from esports_sim.registry.rosters import list_roster_packs

    import esports_sim.web.server as server_mod

    packs = list_roster_packs()
    if not packs:
        pytest.skip("no roster packs installed")
    out = server_mod.lobby_offers(seed=2026, pack=packs[0].id)
    assert out["offers"], "pack preview produced no career offers"
    assert all(o["team_id"] for o in out["offers"])


def test_reputation_reads_chronicle(game_data):
    gs = _legacy(game_data)
    seat = gs.manager_for(gs.user_team_id)
    base = career.reputation(gs, seat.id)
    assert base["international_success"] == 50.0
    chronicle.record(
        gs, "champions_title", "X win Champions.",
        team_id=seat.team_id, manager_id=seat.id,
        data={"title": "S1 Champions"},
    )
    rep = career.reputation(gs, seat.id)
    assert rep["international_success"] > 50.0
    assert rep["pressure_handling"] > 50.0
    summary = career.career_summary(gs, seat.id)
    assert summary["titles"] == ["S1 Champions"]
