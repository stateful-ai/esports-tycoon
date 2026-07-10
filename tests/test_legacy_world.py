"""Phase 3 of Legacy Mode: rivalries, the Hall of Fame, living-history
callbacks, and per-save media voices."""

from __future__ import annotations

import pytest

from esports_sim.manager import chronicle, hof, rivalries, social
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=888)


# -- rivalries ----------------------------------------------------------------


def test_rivalry_heats_and_names_itself(campaign):
    gs = campaign
    a, b = sorted(gs.teams)[:2]
    for _ in range(5):
        rivalries._add(gs, a, b, 9.0)
    assert rivalries.get(gs, a, b) >= rivalries.RIVALRY_BAR
    # The crossing chronicled exactly once.
    entries = [e for e in gs.chronicle if e.kind == "rivalry"]
    assert len(entries) == 1
    assert entries[0].data["other"] in (a, b)


def test_rivalry_offseason_decay_and_floor(campaign):
    gs = campaign
    a, b = sorted(gs.teams)[:2]
    c, d = sorted(gs.teams)[2:4]
    gs.rivalries[rivalries.key(a, b)] = 60.0
    gs.rivalries[rivalries.key(c, d)] = 5.0
    rivalries.offseason_decay(gs)
    assert gs.rivalries[rivalries.key(a, b)] == 45.0
    assert rivalries.key(c, d) not in gs.rivalries  # faint grudges forgotten


def test_playoffs_build_rivalries(game_data):
    gs = new_campaign(game_data, seed=17)
    for _ in range(60):
        advance_week(gs, game_data)
        if gs.season >= 2:
            break
    assert gs.rivalries, "a full season of playoffs left no rivalry heat"
    assert all(0.0 < v <= 100.0 for v in gs.rivalries.values())


# -- hall of fame -------------------------------------------------------------


def test_hof_scores_awards_heavily(campaign):
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    lo, _ = hof.score_career(gs, p, ca=60.0)
    for i in range(3):
        chronicle.record(
            gs, "award", f"{p.handle} wins the S{i} MVP.", player_id=p.id,
            data={"award": f"S{i} MVP"},
        )
    hi, lines = hof.score_career(gs, p, ca=60.0)
    assert hi > lo + 2 * hof.AWARD_POINTS
    assert any("honours" in ln for ln in lines)


def test_hof_induction_records(campaign):
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    for i in range(3):
        chronicle.record(
            gs, "award", f"{p.handle} wins the S{i} MVP.", player_id=p.id,
            data={"award": f"S{i} MVP"},
        )
    assert hof.consider_at_retirement(gs, p, ca=75.0, team_name="Team Nexus")
    assert gs.hall_of_fame and gs.hall_of_fame[-1].handle == p.handle
    assert any(e.kind == "hall_of_fame" for e in gs.chronicle)
    # A journeyman doesn't get in.
    q = gs.roster(gs.user_team_id)[1]
    assert not hof.consider_at_retirement(gs, q, ca=55.0, team_name="X")


# -- living history -----------------------------------------------------------


def test_title_history_line(campaign):
    gs = campaign
    tid = sorted(gs.teams)[0]
    assert chronicle.title_history_line(gs, tid, "masters_title") == ""  # S1
    gs.season = 5
    assert "first" in chronicle.title_history_line(gs, tid, "masters_title")
    chronicle.record(
        gs, "masters_title", "x", team_id=tid, data={"title": "S5 Masters"}
    )
    gs.season = 6
    assert chronicle.title_history_line(gs, tid, "masters_title") == "back-to-back"
    gs.season = 9
    assert "since S5" in chronicle.title_history_line(gs, tid, "masters_title")


# -- media voices -------------------------------------------------------------


def test_media_voices_deterministic_per_save(game_data):
    a = new_campaign(game_data, seed=1)
    b = new_campaign(game_data, seed=1)
    assert social.media_voices(a) == social.media_voices(b)
    assert set(social.media_voices(a)) == {"wire", "clips", "patch"}


def test_feed_uses_this_saves_voices(game_data):
    gs = new_campaign(game_data, seed=3)
    voices = social.media_voices(gs)
    for _ in range(4):
        advance_week(gs, game_data)
    authors = {p.author for p in gs.social_feed if p.author_kind == "media"}
    assert authors, "no media posts after four weeks"
    allowed = set(voices.values()) | {""}
    assert authors <= allowed, f"off-brand voices: {authors - allowed}"
