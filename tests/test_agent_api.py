"""The /api/agent/* surface: header identity, lobby flow, act/vote/tick, and
the human+agent shared week barrier. Direct route-function calls with the
request context bound — the house pattern for web endpoint tests."""

from __future__ import annotations

import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

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


@pytest.mark.parametrize("pace", ["fast", None, [], {}])
def test_malformed_nested_parameters_are_recoverable(lobby, pace):
    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=918))
    _as(lobby, SID_A)
    game = lobby.games[created["code"]]
    before = game.gs.model_dump_json()
    with pytest.raises(HTTPException) as err:
        server.agent_act(server.AgentActBody(kind="set_tactics", params={"pace": pace}))
    assert err.value.status_code == 422
    assert err.value.detail
    assert game.gs.model_dump_json() == before


@pytest.mark.parametrize("accept", ["false", "true", 0, 1, None, [], {}])
def test_http_transfer_requires_boolean_before_mutation(lobby, accept):
    from esports_sim.manager.state import TransferOffer

    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=922))
    _as(lobby, SID_A)
    game = lobby.games[created["code"]]
    seller = "team_nexus"
    buyer = next(t for t in sorted(game.gs.teams) if t != seller)
    pid = game.gs.teams[seller].player_ids[0]
    game.gs.transfer_offers.append(TransferOffer(
        player_id=pid, from_team=seller, to_team=buyer,
        fee=10_000, expires_week=game.gs.week + 2,
    ))
    before = game.gs.model_dump_json()
    with pytest.raises(HTTPException) as err:
        server.agent_act(server.AgentActBody(kind="transfer_offer", params={
            "player_id": pid, "to_team": buyer, "accept": accept,
        }))
    assert err.value.status_code == 422
    assert "JSON boolean" in err.value.detail
    assert game.gs.model_dump_json() == before


@pytest.mark.parametrize("kind", ["sponsor_respond", "sponsor_demand_respond"])
@pytest.mark.parametrize("accept", ["false", "true", 0, 1, None, [], {}])
def test_http_sponsor_decisions_reject_nonboolean_without_mutation(lobby, monkeypatch, kind, accept):
    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=925))
    _as(lobby, SID_A)
    game = lobby.games[created["code"]]
    called = []
    def domain_action(*args):
        called.append(args)
        game.gs.teams["team_nexus"].balance += 1
        return True, "resolved"
    monkeypatch.setattr(server.sponsors, "sign_market_offer", domain_action)
    monkeypatch.setattr(server.sponsors, "decline_market_offer", domain_action)
    monkeypatch.setattr(server.sponsors, "respond_demand", domain_action)
    before = game.gs.model_dump_json()
    with pytest.raises(HTTPException) as err:
        server.agent_act(server.AgentActBody(kind=kind, params={"accept": accept}))
    assert err.value.status_code == 422
    assert "JSON boolean" in err.value.detail
    assert not called
    assert game.gs.model_dump_json() == before


@pytest.mark.parametrize("first_advances", [False, True])
def test_agent_advance_response_is_captured_before_concurrent_votes(lobby, monkeypatch, first_advances):
    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=923))
    game = lobby.games[created["code"]]
    a = "team_nexus"
    b = next(t for t in sorted(game.gs.teams) if t != a and game.gs.teams[t].tier == 1)
    _as(lobby, SID_B)
    server.agent_join(server.AgentJoinBody(code=game.code, team_id=b))
    if first_advances:
        game.ready.add(b)

    # Resolve only the coordinator boundary, so the concurrency regression
    # controls the interleaving without a match simulation or background work.
    def tick(gs, gd, ready, **kwargs):
        week = gs.week
        gs.week += 1
        return SimpleNamespace(
            report=SimpleNamespace(season=gs.season, week=week),
            summaries={t: {"week": week} for t in gs.human_team_ids},
        )
    monkeypatch.setattr(server.agent_play, "tick_shared_week", tick)
    monkeypatch.setattr(server, "_weekly_development_report", lambda *args: {})
    monkeypatch.setattr(server, "_report_view", lambda *args: {"advanced": True})
    monkeypatch.setattr(server.review_history, "append_reviews", lambda *args: None)
    monkeypatch.setattr(server.llm_social, "enqueue", lambda *args: None)
    monkeypatch.setattr(game, "autosave_tick", lambda: None)
    released = threading.Event()
    competitor_done = threading.Event()
    underlying = threading.Lock()
    original_thread = []

    class InterleavingLock:
        triggered = False

        def __enter__(self):
            underlying.acquire()

        def __exit__(self, *args):
            underlying.release()
            if threading.get_ident() == original_thread[0] and not self.triggered:
                self.triggered = True
                released.set()
                assert competitor_done.wait(10)

    monkeypatch.setattr(game, "lock", InterleavingLock())

    def original():
        original_thread.append(threading.get_ident())
        _as(lobby, SID_A)
        return server.agent_act(server.AgentActBody(kind="advance"))

    def competitor():
        assert released.wait(10)
        try:
            _as(lobby, SID_B)
            server.agent_act(server.AgentActBody(kind="advance"))
            if first_advances:
                _as(lobby, SID_A)
                server.agent_act(server.AgentActBody(kind="advance"))
        finally:
            competitor_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = pool.submit(competitor)
        response = pool.submit(original).result(timeout=20)
        concurrent.result(timeout=20)
    if first_advances:
        assert response["advanced"]
        assert response["tick"]["week"] == 1
        assert game.agent_last_tick[a]["week"] == 2
    else:
        assert not response["advanced"]
        assert response["waiting_on"] == [b]
        assert response["ready"] == [a]
        assert not game.ready


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
