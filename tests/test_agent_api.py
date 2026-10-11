"""The /api/agent/* surface: header identity, lobby flow, act/vote/tick, and
the human+agent shared week barrier. Direct route-function calls with the
request context bound — the house pattern for web endpoint tests."""

from __future__ import annotations

import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
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


def test_http_league_includes_joined_challengers_and_tier2_only_regions(lobby):
    from fastapi.testclient import TestClient
    from esports_sim.manager.agent_play import league_view

    client = TestClient(server.app)
    created = client.post("/api/agent/create", headers={"X-Esports-Sid": SID_A},
                          json={"team_id": "team_nexus", "seed": 941})
    assert created.status_code == 200
    code = created.json()["code"]
    game = lobby.games[code]
    gs = game.gs
    # Leave two tiers in Americas, but remove tier one from EMEA.
    for team in gs.teams.values():
        if team.tier == 1 and str(team.region) == "emea":
            team.region = gs.teams["team_nexus"].region
    tid = next(t for t in sorted(gs.teams)
               if gs.teams[t].tier == 2 and str(gs.teams[t].region) == "americas")
    joined = client.post("/api/agent/join", headers={"X-Esports-Sid": SID_B},
                         json={"code": code, "team_id": tid})
    assert joined.status_code == 200
    before = gs.model_dump_json()
    expected = league_view(gs)
    for sid in (SID_A, SID_B, SID_B):
        response = client.get("/api/agent/league", headers={"X-Esports-Sid": sid})
        assert response.status_code == 200
        view = response.json()
        assert view == expected
        assert "emea" not in view["regions"]
        assert {(t["tier"], t["region"]) for t in view["tables"]} >= {
            (1, "americas"), (2, "americas"), (2, "emea"),
        }
        own = next(t for t in view["tables"] if t["tier"] == 2 and t["region"] == "americas")
        assert [r["team_id"] for r in own["rows"]] == gs.standings_order("americas", tier=2)
        assert any(r["team_id"] == tid and r["human"] for r in own["rows"])
        assert any(not r["human"] for r in own["rows"])
        assert gs.model_dump_json() == before


@pytest.mark.parametrize("cached_tick", [True, False])
def test_accept_job_keeps_last_tick_available_at_new_club(lobby, cached_tick):
    from esports_sim.manager import career

    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=916))
    game = lobby.games[created["code"]]
    old = "team_nexus"
    other = next(t for t in sorted(game.gs.teams) if t != old and game.gs.teams[t].tier == 1)
    _as(lobby, SID_B)
    server.agent_join(server.AgentJoinBody(code=game.code, team_id=other))
    game.gs.game_mode = "legacy"
    seat = game.gs.manager_for(old)
    career.apply_dismissals(game.gs, [seat.id])
    target = game.gs.career_offers_by[seat.id][0].team_id
    chronicle_before = deepcopy(game.gs.chronicle)

    # Represent the dismissal week's cached digest without simulating a week.
    # Historical club references must survive the cache-key move verbatim.
    digest = {
        "season": 1, "week": 10, "now_season": 2, "now_week": 1,
        "done": True, "reward": -1.0,
        "results": [{"fixture_id": "s1_test", "opponent_id": other, "score": [1, 2]}],
        "season_champion": {"team_id": old, "team_name": game.gs.teams[old].name, "yours": True},
    }
    digest_before = deepcopy(digest)
    other_digest = {"season": 1, "week": 10, "done": False}
    game.agent_last_tick = {other: other_digest}
    if cached_tick:
        game.agent_last_tick[old] = digest
    game.tick_seq = 3
    game.ready.update((old, other))

    _as(lobby, SID_A)
    moved = server.agent_act(server.AgentActBody(kind="accept_job", params={"team_id": target}))
    assert moved["ok"] and moved["team_id"] == target
    assert lobby.membership(SID_A) == (game.code, target)
    assert game.gs.managers[seat.id].team_id == target
    assert game.ready == {other}
    assert old not in game.agent_last_tick
    assert game.agent_last_tick[other] is other_digest
    assert game.gs.chronicle[:len(chronicle_before)] == chronicle_before
    assert game.gs.chronicle[-1].kind == "appointment"
    assert game.gs.chronicle[-1].team_id == target
    assert game.gs.chronicle[-1].manager_id == seat.id

    # A fresh request resolves the new lobby binding before reading either API.
    _as(lobby, SID_A)
    state = server.agent_state()
    sync = server.agent_sync()
    assert state["team_id"] == target
    assert sync["tick_seq"] == state["sync"]["tick_seq"] == 3
    expected = digest_before if cached_tick else None
    assert sync["last_tick"] == state["sync"]["last_tick"] == expected
    if cached_tick:
        assert game.agent_last_tick[target] is digest
        assert digest == digest_before
    else:
        assert target not in game.agent_last_tick
    _as(lobby, SID_B)
    assert server.agent_sync()["last_tick"] == other_digest


def test_rejected_job_does_not_rebind_last_tick(lobby):
    from esports_sim.manager import career

    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=916))
    game = lobby.games[created["code"]]
    old = "team_nexus"
    game.gs.game_mode = "legacy"
    seat = game.gs.manager_for(old)
    career.apply_dismissals(game.gs, [seat.id])
    digest = {"season": 1, "week": 10, "done": True}
    game.agent_last_tick[old] = digest
    game.ready.add(old)
    before = game.gs.model_dump_json()

    _as(lobby, SID_A)
    with pytest.raises(HTTPException) as err:
        server.agent_act(server.AgentActBody(kind="accept_job", params={"team_id": "unknown-club"}))
    assert err.value.status_code == 422
    assert game.gs.model_dump_json() == before
    assert lobby.membership(SID_A) == (game.code, old)
    assert game.ready == {old}
    assert game.agent_last_tick == {old: digest}
    assert game.agent_last_tick[old] is digest
    assert server.agent_state()["sync"]["last_tick"] == digest
    assert server.agent_sync()["last_tick"] == digest


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
    advances = [a for a in game.gs.action_log if a.kind == "advance"]
    assert {a.team_id: a.source for a in advances} == {
        "team_nexus": "web", free: "agent",
    }

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


@pytest.mark.parametrize("agent_first", [False, True])
def test_mixed_votes_keep_first_source_through_repeat_and_reset(lobby, agent_first):
    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=916))
    game = lobby.games[created["code"]]
    a = "team_nexus"
    b = next(t for t in sorted(game.gs.teams) if t != a and game.gs.teams[t].tier == 1)
    _as(lobby, SID_B)
    server.agent_join(server.AgentJoinBody(code=game.code, team_id=b))

    def vote(sid, agent):
        _as(lobby, sid)
        return (server.agent_act(server.AgentActBody(kind="advance"))
                if agent else server.advance())

    before_log = list(game.gs.action_log)
    season, week, phase = game.gs.season, game.gs.week, game.gs.phase
    first_source = "agent" if agent_first else "web"
    assert not vote(SID_A, agent_first)["advanced"]
    assert game.ready_sources == {a: first_source}
    assert game.gs.action_log == before_log  # a pending vote is not a tick decision
    assert not vote(SID_A, not agent_first)["advanced"]
    assert game.ready_sources == {a: first_source}
    assert game.gs.action_log == before_log
    assert vote(SID_B, not agent_first)["advanced"]
    advances = [row for row in game.gs.action_log if row.kind == "advance"]
    assert [row.team_id for row in advances] == sorted([a, b])
    assert {row.team_id: row.source for row in advances} == {
        a: first_source, b: "web" if agent_first else "agent",
    }
    assert all((row.season, row.week, row.phase) == (season, week, phase)
               and row.params == {} and row.manager_id for row in advances)
    assert not game.ready and not game.ready_sources

    # A fresh vote board may use different surfaces; previous-week provenance
    # cannot follow a seat into its next accepted advance.
    for tid in (a, b):
        pending = server.flavor_events.pending_for(game.gs, tid)
        if pending is not None:
            server.flavor_events.resolve(game.gs, tid, pending.choices[0].id)
        pending = server.media_events.pending_for(game.gs, tid)
        if pending is not None:
            server.media_events.resolve(game.gs, tid, pending.choices[0].id)
    assert not vote(SID_A, not agent_first)["advanced"]
    assert vote(SID_B, agent_first)["advanced"]
    advances = [row for row in game.gs.action_log if row.kind == "advance"]
    assert {row.team_id: row.source for row in advances[-2:]} == {
        a: "web" if agent_first else "agent", b: first_source,
    }
    assert not game.ready and not game.ready_sources


def test_rejected_short_roster_revokes_source_and_reready_uses_new_surface(lobby):
    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=916))
    game = lobby.games[created["code"]]
    a = "team_nexus"
    b = next(t for t in sorted(game.gs.teams) if t != a and game.gs.teams[t].tier == 1)
    _as(lobby, SID_B)
    server.agent_join(server.AgentJoinBody(code=game.code, team_id=b))
    _as(lobby, SID_A)
    assert not server.agent_act(server.AgentActBody(kind="advance"))["advanced"]
    original_roster = list(game.gs.teams[a].player_ids)
    game.gs.teams[a].player_ids = original_roster[:server.market.ROSTER_MIN - 1]
    before = game.gs.model_dump_json()
    with pytest.raises(HTTPException):
        server.advance()  # rejected before voting: keep the pending vote intact
    assert game.gs.model_dump_json() == before
    assert game.ready_sources == {a: "agent"}
    _as(lobby, SID_B)
    with pytest.raises(HTTPException):
        server.advance()  # tick-time revalidation revokes A's old vote and source
    assert game.ready == {b} and game.ready_sources == {b: "web"}
    assert not [row for row in game.gs.action_log if row.kind == "advance"]
    game.gs.teams[a].player_ids = original_roster
    _as(lobby, SID_A)
    assert server.advance()["advanced"]
    assert {row.team_id: row.source for row in game.gs.action_log if row.kind == "advance"} == {
        a: "web", b: "web",
    }
    assert not game.ready and not game.ready_sources


def test_vote_source_follows_session_vote_lifetime_on_leave_resume_and_reload(lobby):
    _as(lobby, SID_A)
    created = server.agent_create(server.AgentCreateBody(team_id="team_nexus", seed=916))
    game = lobby.games[created["code"]]
    b = next(t for t in sorted(game.gs.teams) if t != "team_nexus" and game.gs.teams[t].tier == 1)
    _as(lobby, SID_B)
    server.agent_join(server.AgentJoinBody(code=game.code, team_id=b))
    _as(lobby, SID_A)
    server.agent_act(server.AgentActBody(kind="advance"))
    server.leave_game()
    assert game.ready == {"team_nexus"}
    assert game.ready_sources == {"team_nexus": "agent"}
    server.resume_game(server.ResumeBody(code=game.code))
    _as(lobby, SID_A)
    assert not server.advance()["advanced"]
    assert game.ready_sources == {"team_nexus": "agent"}
    reloaded = server._Game(game.gd, game.code)
    assert not reloaded.ready and not reloaded.ready_sources
    assert not [row for row in reloaded.gs.action_log if row.kind == "advance"]
