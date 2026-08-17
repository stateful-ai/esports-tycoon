"""The /api/agent/* surface: header identity, lobby flow, act/vote/tick, and
the human+agent shared week barrier. Direct route-function calls with the
request context bound — the house pattern for web endpoint tests."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import HTTPException

import esports_sim.web.server as server

SID_A = "a" * 32
SID_B = "b" * 32


@pytest.fixture
def lobby(tmp_path, monkeypatch, game_data):
    # The lobby persists sessions + saves under a RELATIVE saves/ dir; run in
    # a tmp cwd. Reuse the session-scoped registries instead of re-parsing
    # YAML, and point the module singleton (the endpoints read it) here.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "load_all", lambda: game_data)
    lob = server.Lobby()
    monkeypatch.setattr(server, "_LOBBY", lob)
    return lob


def _as(lobby: "server.Lobby", sid: str) -> None:
    """Bind the request context the way SessionMiddleware would."""
    game, team = lobby.game_for(sid)
    server._ctx.set(server._ReqCtx(game, team))
    server._sid_ctx.set(sid)


def test_scope_sid_prefers_valid_header_over_cookie():
    header_scope = {"headers": [(b"x-esports-sid", SID_A.encode())]}
    assert server._scope_sid(header_scope) == SID_A
    # An ill-formed header is ignored, not trusted; the cookie still counts.
    mixed = {
        "headers": [
            (b"x-esports-sid", b"not-a-sid"),
            (b"cookie", f"esports_sid={SID_B}".encode()),
        ]
    }
    assert server._scope_sid(mixed) == SID_B
    assert server._scope_sid({"headers": []}) is None


def test_agent_help_is_readable_before_joining(lobby):
    _as(lobby, SID_A)
    card = server.agent_help()
    assert card["agent_play_version"] == 1
    assert "advance" in card["actions"]
    assert "set_tactics" in card["actions"]
    assert card["docs"] == "docs/agent-play.md"


def test_agent_state_requires_a_world(lobby):
    _as(lobby, SID_A)
    with pytest.raises(HTTPException) as err:
        server.agent_state()
    assert err.value.status_code == 409


def test_join_guards_taken_seats_and_draft_worlds(lobby):
    _as(lobby, SID_A)
    created = server.agent_create(
        server.AgentCreateBody(team_id="team_nexus", seed=914)
    )
    code = created["code"]

    _as(lobby, SID_B)
    with pytest.raises(HTTPException) as err:
        server.agent_join(server.AgentJoinBody(code=code, team_id="team_nexus"))
    assert "another manager" in err.value.detail

    with pytest.raises(HTTPException) as err:
        server.agent_join(server.AgentJoinBody(code="ZZZZZ", team_id="team_nexus"))
    assert "no game" in err.value.detail

    # A world with an unfinished fantasy draft cannot take agent seats: the
    # decision contract has no draft_pick action, so the seat would wedge.
    draft = lobby.create_game(
        "c" * 32, "team_nexus", 915, shared=True, fantasy_draft=True
    )
    with pytest.raises(HTTPException) as err:
        server.agent_join(
            server.AgentJoinBody(code=draft.code, team_id="team_vanguard")
        )
    assert "fantasy draft" in err.value.detail


def test_create_act_vote_and_mixed_human_agent_barrier(lobby, game_data):
    # Agent A founds the world through the agent surface.
    _as(lobby, SID_A)
    created = server.agent_create(
        server.AgentCreateBody(team_id="team_nexus", seed=916)
    )
    code = created["code"]
    assert created["sid"] == SID_A and created["mode"] == "shared"
    game = lobby.games[code]
    free = sorted(
        t for t in game.gs.teams
        if game.gs.teams[t].tier == 1 and t != "team_nexus"
    )[0]

    # Agent B joins by code, like a LAN friend.
    _as(lobby, SID_B)
    joined = server.agent_join(server.AgentJoinBody(code=code, team_id=free))
    assert joined["team_id"] == free
    assert sorted(game.gs.human_team_ids) == sorted(["team_nexus", free])

    # B's observation is bound to B's seat and carries the agent blocks.
    _as(lobby, SID_B)
    state = server.agent_state()
    assert state["team_id"] == free
    assert {"legal_actions", "sync", "objective", "world"} <= set(state)
    assert state["world"]["code"] == code
    assert state["sync"]["waiting_on"] == sorted(["team_nexus", free])

    # Actions resolve through the decision contract; illegal ones 422 with
    # the reason in the detail.
    acted = server.agent_act(
        server.AgentActBody(kind="set_training", params={"focus": "team"})
    )
    assert acted["ok"] and acted["message"] == "training focus set to team"
    with pytest.raises(HTTPException) as err:
        server.agent_act(
            server.AgentActBody(kind="sign", params={"player_id": "ghost"})
        )
    assert err.value.status_code == 422
    assert "free agent" in err.value.detail

    # B votes; the world waits on the human seat (ids, not display names).
    vote = server.agent_act(server.AgentActBody(kind="advance"))
    assert vote["advanced"] is False
    assert vote["waiting_on"] == ["team_nexus"]
    sync = server.agent_sync()
    assert sync["you_ready"] is True and sync["waiting_on"] == ["team_nexus"]

    # The HUMAN advance endpoint completes the same barrier — browser
    # managers and agents share one world and one week.
    _as(lobby, SID_A)
    report = server.advance()
    assert report["advanced"] is True

    # Both seats now see the resolved week's digest.
    for sid, tid in ((SID_A, "team_nexus"), (SID_B, free)):
        _as(lobby, sid)
        sync = server.agent_sync()
        assert sync["tick_seq"] == 1
        assert sync["last_tick"] is not None
        assert sync["last_tick"]["week"] == 1
        assert sync["last_tick"]["now_week"] == 2
        assert sync["you_ready"] is False

    _as(lobby, SID_B)
    league = server.agent_league()
    assert [s["team_id"] for s in league["seats"]] == sorted(
        ["team_nexus", free]
    )
    objective = server.agent_objective()
    assert objective["team_id"] == free
    assert objective["titles"]["total"] == 0
    assert [r["team_id"] for r in objective["rival_seats"]] == ["team_nexus"]
