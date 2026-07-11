"""Match-review synthesis: determinism, staff-tier gating, and edge cases."""

from __future__ import annotations

import pytest

from esports_sim.manager import advance_week, new_campaign
from esports_sim.manager.market import release_player
from esports_sim.manager.match_review import build_match_review
from esports_sim.manager.state import GameState, StaffMember
from esports_sim.registry import GameData


def _play(gd: GameData, seed: int, weeks: int = 4) -> GameState:
    gs = new_campaign(gd, seed=seed)
    for _ in range(weeks):
        advance_week(gs, gd)
    return gs


def test_review_present_and_grounded(game_data: GameData) -> None:
    gs = _play(game_data, seed=123)
    rv = gs.last_review_by.get(gs.user_team_id)
    assert rv is not None and rv.contested
    assert rv.team_id == gs.user_team_id
    # A real series has a scoreline and at least one diagnosed signal.
    assert rv.your_rounds + rv.their_rounds > 0
    assert rv.working or rv.breaking
    # Every point is well-formed and tagged with an unlock tier.
    for p in rv.working + rv.breaking:
        assert p.tone in ("good", "bad")
        assert 0 <= p.min_tier <= 2
        assert p.den >= 0
    # Won flag agrees with the map score.
    assert rv.won == (rv.your_maps > rv.their_maps)


def test_review_deterministic(game_data: GameData) -> None:
    a = _play(game_data, seed=77)
    b = _play(game_data, seed=77)
    da = {t: rv.model_dump_json() for t, rv in sorted(a.last_review_by.items())}
    db = {t: rv.model_dump_json() for t, rv in sorted(b.last_review_by.items())}
    assert da == db and da  # identical AND non-empty


def test_min_tier_gating_is_monotonic(game_data: GameData) -> None:
    """Filtering points by a higher analyst tier only ever ADDS signals."""
    gs = _play(game_data, seed=77)
    rv = gs.last_review_by[gs.user_team_id]
    seen = rv.working + rv.breaking

    def visible(tier: int) -> set[str]:
        return {p.code for p in seen if p.min_tier <= tier}

    assert visible(0) <= visible(1) <= visible(2)
    # There is genuinely tiered content to gate (tier-0 is a strict subset).
    assert any(p.min_tier > 0 for p in seen)


def test_serializer_respects_tier(game_data: GameData) -> None:
    from esports_sim.web import server

    gs = _play(game_data, seed=77)
    uid = gs.user_team_id
    gs.set_acting(uid)

    # Bare org (no analyst) -> tier 0: only tier-0 signals surface, locked hint.
    gs.staff.pop("analyst", None)
    low = server._last_match_review(gs)
    assert low["tier"] == 0
    assert all(
        p["code"] in {"atk_side", "def_side", "pistol", "player_std", "player_under"}
        for p in low["working"] + low["breaking"]
    )

    # Elite analyst -> tier 3: deeper signals become visible, nothing locked.
    gs.staff["analyst"] = StaffMember(
        id="an", name="Ana", role="analyst", quality=98.0, salary=1, specialty="data"
    )
    hi = server._last_match_review(gs)
    assert hi["tier"] == 3
    assert not hi["locked"]
    assert len(hi["working"]) + len(hi["breaking"]) >= len(low["working"]) + len(low["breaking"])


def test_levers_gated_by_coach(game_data: GameData) -> None:
    from esports_sim.web import server

    gs = _play(game_data, seed=77)
    uid = gs.user_team_id
    gs.set_acting(uid)
    gs.staff["analyst"] = StaffMember(
        id="an", name="Ana", role="analyst", quality=98.0, salary=1, specialty="data"
    )

    # No coach -> no levers.
    gs.staff.pop("coach", None)
    assert server._last_match_review(gs)["levers"] == []

    # A strong tactical coach -> up to 3 levers, tactical ones lead.
    gs.staff["coach"] = StaffMember(
        id="co", name="K", role="coach", quality=85.0, salary=1, specialty="tactical"
    )
    levers = server._last_match_review(gs)["levers"]
    assert 1 <= len(levers) <= 3
    if any(lv["specialty"] == "tactical" for lv in levers):
        assert levers[0]["specialty"] == "tactical"  # specialty floats to top


def test_forfeit_is_thin_review(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=123)
    tid = gs.user_team_id
    for pid in list(gs.teams[tid].player_ids):
        release_player(gs, tid, pid)
    advance_week(gs, game_data)
    rv = gs.last_review_by.get(tid)
    assert rv is not None
    assert rv.contested is False
    assert not rv.working and not rv.breaking


def test_build_empty_bundles() -> None:
    rv = build_match_review(1, 2, "fx", "A", "B", 1, [], {})
    assert rv.contested is False
    assert rv.fixture_id == "fx" and rv.season == 1 and rv.week == 2
    assert not rv.working and not rv.breaking
