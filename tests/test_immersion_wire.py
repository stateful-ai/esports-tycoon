"""Wire-shape checks for the PR #315 immersion surfaces.

The underlying campaign logic is covered by campaign-marked tests; these pin
the SERIALIZED shape the browser actually reads (the seam where the last
three Codex review rounds found integration bugs). Serializer-only: no HTTP,
no browser — the in-process ``_Game``/``_ReqCtx`` pattern from
``test_next_pass.py``.
"""

from __future__ import annotations

import pytest

from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.registry import GameData


@pytest.fixture()
def campaign(game_data: GameData):
    gs = new_campaign(game_data, seed=321)
    # A few played weeks so weekly systems (digest cadence, prep proposals,
    # scouting progress) have real state behind the serializers.
    for _ in range(3):
        advance_week(gs, game_data)
    return gs


@pytest.fixture()
def ctx(campaign, game_data):
    import esports_sim.web.server as server_mod

    game = server_mod._Game(game_data, "WIRET", gs=campaign)
    server_mod._ctx.set(server_mod._ReqCtx(game, campaign.user_team_id))
    return server_mod, campaign


def test_roster_payload_carries_dev_digest_pipeline_and_dev_warning(ctx):
    server_mod, gs = ctx
    out = server_mod.roster(gs.user_team_id)

    assert "dev_digest" in out, "F1 digest key missing from own-roster payload"
    assert "pipeline" in out, "F1 pipeline key missing from own-roster payload"
    pipeline = out["pipeline"]
    assert set(pipeline) >= {"youth", "academy", "bench", "starters"}
    for row in pipeline["starters"]:
        assert set(row) >= {"id", "handle", "age", "ability", "series"}
    # F2: every own-club player row carries the not-developing signal key
    # (None when the player IS developing) so the chip can render server-side.
    for player in out["players"]:
        assert "not_developing" in player


def test_scouting_payload_exposes_lanes_shortlist_and_recommendations(ctx):
    server_mod, gs = ctx
    out = server_mod.scouting_view()

    assert "lanes" in out and set(out["lanes"]) >= {"amateur", "pro"}
    assert "role_options" in out["lanes"]["pro"]
    assert "caliber_options" in out["lanes"]["pro"]
    assert "shortlist" in out
    assert "deep_dive_recommendations" in out


def test_gameplan_payload_exposes_prep_breakdown_scrim_and_artifact(ctx):
    server_mod, gs = ctx
    out = server_mod.gameplan_view()

    assert set(out["prep_edge_breakdown"]) >= {"scout", "book", "coach", "total", "cap"}
    assert "scrim_proposal" in out
    assert "last_artifact" in out


def test_tactics_lineup_serializes_agent_mastery_edge(ctx):
    server_mod, gs = ctx
    out = server_mod.tactics_view()

    players = out["lineup"]["players"]
    assert players, "lineup serializer returned no players"
    for entry in players:
        for option in entry["options"]:
            assert "edge" in option and "mastery" in option


def test_state_payload_exposes_needs_you_flags_at_top_level(ctx):
    server_mod, gs = ctx
    out = server_mod.state()

    # computeNeedsYou in app.js reads these at the ROOT of /api/state; the
    # third #315 Codex round moved them there, so pin the location.
    for flag in (
        "promise_pending",
        "scrim_proposal_pending",
        "culture_violation_unack",
        "scout_shortlist_ready",
    ):
        assert flag in out, f"needs-you flag {flag} missing from /api/state root"
