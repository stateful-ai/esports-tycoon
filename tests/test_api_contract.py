from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

import esports_sim.web.server as server_mod
from esports_sim.manager import new_campaign, advance_week
from esports_sim.manager.state import SponsorDemand
from esports_sim.registry import GameData

@pytest.fixture(scope="module")
def test_env(game_data: GameData):
    # Create a real GameState and advance it to generate stats and relationships
    gs = new_campaign(game_data, seed=2026, user_team_id="team_nexus")
    advance_week(gs, game_data)
    
    # Create the _Game instance
    game = server_mod._Game(game_data, "TESTC", gs=gs)
    
    # Bind context
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))
    
    return gs

def test_roster_endpoint_contract(test_env) -> None:
    gs = test_env
    team_id = gs.user_team_id
    
    # Direct function call
    data = server_mod.roster(team_id)
    
    # Verify the new keys exist in the response
    assert "hierarchy" in data
    assert "relationships" in data
    assert "promises" in data
    
    # Verify hierarchy structure mapping pid -> role
    hierarchy = data["hierarchy"]
    assert isinstance(hierarchy, dict)
    for p in gs.roster(team_id):
        assert p.id in hierarchy
        
    # Verify relationships duos and feuds
    rels = data["relationships"]
    assert "duos" in rels
    assert "feuds" in rels
    assert isinstance(rels["duos"], list)
    assert isinstance(rels["feuds"], list)
    
    # Verify promises list
    assert isinstance(data["promises"], list)


def test_facilities_endpoint_contract(test_env) -> None:
    data = server_mod.facilities_view()

    assert set(data) == {
        "balance", "total_upkeep", "built_count", "total_levels", "facilities",
    }
    assert [facility["id"] for facility in data["facilities"]] == [
        "training_center",
        "analytics_suite",
        "marketing_office",
        "recovery_suite",
        "strategy_lab",
        "team_house",
    ]
    assert next(
        facility for facility in data["facilities"]
        if facility["id"] == "analytics_suite"
    )["label"] == "VOD Review Room"


def test_sponsor_demand_finances_and_action_contract(test_env) -> None:
    gs = test_env
    tid = gs.user_team_id
    fixture = next(
        f for f in sorted(gs.fixtures, key=lambda row: (row.week, row.id))
        if not f.played and f.week >= gs.week and tid in (f.team_a, f.team_b)
    )
    opponent = fixture.team_b if fixture.team_a == tid else fixture.team_a
    player_id = gs.teams[tid].player_ids[0]
    demand = SponsorDemand(
        id="api-demand", brand="Contract Corp", slot="jersey",
        kind="field_rookie", fixture_id=fixture.id, opponent_id=opponent,
        player_id=player_id, issued_season=gs.season, issued_week=gs.week,
        deadline_week=fixture.week, reward=30_000, penalty=15_000,
    )
    gs.sponsor_demands.append(demand)

    data = server_mod.finances()
    assert data["demands"][0]["id"] == demand.id
    assert data["demands"][0]["can_respond"] is True
    result = server_mod.sponsor_demand_action(
        server_mod.SponsorDemandBody(demand_id=demand.id, accept=True)
    )
    assert result["ok"] is True
    assert demand.status == "accepted"
    assert gs.action_log[-1].kind == "sponsor_demand_respond"


def test_player_profile_endpoint_contract(test_env) -> None:
    gs = test_env
    player_id = gs.teams[gs.user_team_id].player_ids[0]
    
    # Direct function call
    data = server_mod.player_profile(player_id)
    
    # Verify player block contains hierarchy_role and mentorship info
    player_block = data["player"]
    assert "hierarchy_role" in player_block
    assert "mentor_id" in player_block or "mentor_progress" in player_block
    
    # Verify promises block is present in player block
    assert "promises" in player_block
    
    # Verify xDuel and xDE data are present in the season block
    season_block = data["season"]
    assert "xduel_expected_wins" in season_block
    assert "xduel_actual_wins" in season_block
    assert "xde" in season_block

def test_post_actions_endpoints(test_env) -> None:
    gs = test_env
    # Find a valid unplayed fixture in the campaign
    valid_fx = next((f for f in gs.fixtures if not f.played), None)
    assert valid_fx is not None, "No active fixture found for test"
    fixture_id = valid_fx.id
    
    # 1. Halftime Pep Talk
    req = server_mod.PepTalkBody(
        fixture_id=fixture_id,
        talk_type="reassure",
        relative_score=-2
    )
    res_data = server_mod.pep_talk_action(req)
    assert res_data["ok"] is True
    assert "message" in res_data
    
    # 2. Touchline Shout
    player_id = gs.teams[gs.user_team_id].player_ids[0]
    req2 = server_mod.ShoutBody(
        fixture_id=fixture_id,
        shout_type="demand_focus",
        target_player_id=player_id,
        loss_streak=3
    )
    res_data = server_mod.shout_action(req2)
    assert res_data["ok"] is True
    assert "message" in res_data
    
    # 3. LLM Chat
    req3 = server_mod.LLMChatBody(
        player_id=player_id,
        text="Keep up the good work!"
    )
    res_data = server_mod.llm_chat(req3)
    assert res_data["ok"] is True
    assert "response" in res_data
    assert ("effects" in res_data or res_data.get("offline") is True)


def test_advance_response_carries_week_reveal(
    game_data: GameData, tmp_path, monkeypatch
) -> None:
    """POST /api/actions/advance returns a week_reveal block for the client's
    staged advance beat: the manager's own played fixture id plus prev/now
    league positions (prev captured pre-tick in session memory). On a season's
    FIRST played week prev is None — the pre-tick table is all 0-0, ordered by
    tiebreak/id noise, and staging a "drop" away from it would be fiction.
    /api/report serves the identical block for waiting shared-world
    managers."""
    from esports_sim.web import review_history

    gs = new_campaign(game_data, seed=99, user_team_id="team_nexus")
    gs.autosave_enabled = False  # keep the test off the real saves/ dir
    game = server_mod._Game(game_data, "REVEALT", gs=gs)
    token = server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(server_mod.llm_social, "enqueue", lambda *_a, **_k: None)
    try:
        res = server_mod.advance()
        assert res["advanced"] is True
        wr = res["week_reveal"]
        assert set(wr) == {"fixture_id", "standings"}

        mine = [
            f for f in res["fixtures"]
            if gs.user_team_id in (f["team_a"], f["team_b"]) and f["played"]
        ]
        assert wr["fixture_id"] == (mine[0]["id"] if mine else None)

        assert res["phase"] == "regular"
        st = wr["standings"]
        assert st is not None and set(st) == {"prev", "now", "of"}
        # Week 1: the pre-tick table had no played games, so there is no
        # meaningful "from" position — the client shows the plain position.
        assert st["prev"] is None
        assert 1 <= st["now"] <= st["of"]

        # Waiting managers fetch the same reveal from /api/report.
        rep2 = server_mod.last_week_report()["report"]
        assert rep2["week_reveal"] == wr

        # Week 2: last week's results are on the table, so the reveal now
        # carries a real pre-tick position to move from.
        res2 = server_mod.advance()
        st2 = res2["week_reveal"]["standings"]
        assert st2 is not None
        assert 1 <= st2["prev"] <= st2["of"]
        assert 1 <= st2["now"] <= st2["of"]
    finally:
        server_mod._ctx.reset(token)


def test_inbox_endpoint_serves_leverage_calls(test_env) -> None:
    """GET /api/inbox carries a "calls" marker list ({id, kind, leverage})
    for the digest's "This week's calls" header. Every call references an
    item already in the feed — the ranking is derived live, never stored
    (see inbox.top_calls / LEVERAGE)."""
    from esports_sim.manager import inbox as inbox_mod

    data = server_mod.inbox_view()
    assert "calls" in data
    assert isinstance(data["calls"], list)
    assert len(data["calls"]) <= inbox_mod.TOP_CALLS
    item_ids = {it["id"] for it in data["items"]}
    scores = [c["leverage"] for c in data["calls"]]
    assert scores == sorted(scores, reverse=True)
    for c in data["calls"]:
        assert set(c) == {"id", "kind", "leverage"}
        assert c["id"] in item_ids
        assert c["kind"] in inbox_mod.LEVERAGE


def test_matchday_endpoint_contract(test_env) -> None:
    """GET /api/matchday composes the pre-match buildup entirely from
    existing reads: the enriched next-fixture board (identical to
    /api/state's next_fixture, both come from _next_fixture_board), both
    sides' recent-form chips and season danger men, the opposing coach
    persona, and the scout-gated identity/tendencies."""
    gs = test_env

    data = server_mod.matchday()
    assert set(data) == {"fixture", "you", "them", "plan_set"}

    fx = data["fixture"]
    assert fx is not None  # week 2 of a regular season: a fixture exists
    # Thin composition: the same enriched board /api/state serves.
    assert {"preview", "map_pool", "rivalry"} <= set(fx)
    assert server_mod.state()["next_fixture"] == fx

    you, them = data["you"], data["them"]
    assert set(you) == {"id", "name", "form", "danger_men"}
    assert set(them) == {
        "id", "name", "form", "danger_men",
        "coach", "identity", "tendencies", "scouted",
    }
    assert you["id"] == gs.user_team_id
    assert them["id"] in (fx["team_a"], fx["team_b"])
    assert them["id"] != you["id"]

    for side in (you, them):
        for chip in side["form"]:
            assert set(chip) == {"result", "opponent", "score", "week"}
            assert chip["result"] in {"W", "L"}
        for dm in side["danger_men"]:
            assert set(dm) == {"player_id", "handle", "role", "rating", "maps"}
            assert dm["maps"] >= 3

    if them["coach"] is not None:
        assert set(them["coach"]) == {"name", "specialty", "style"}
    # Tactical reads stay hidden until the rival is scouted (>=0.5) — the
    # same gate the roster screen uses. The coach persona is public.
    if not them["scouted"]:
        assert them["identity"] is None
        assert them["tendencies"] == []

    assert isinstance(data["plan_set"], bool)
