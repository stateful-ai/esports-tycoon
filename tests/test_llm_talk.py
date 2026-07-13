"""Tests for the LLM-powered 1:1 Talk module 2.0 (llm_talk.py) and server endpoints."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from fastapi import HTTPException

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import new_campaign, advance_week
from esports_sim.registry import load_all
from esports_sim.web import server, llm_talk
from esports_sim.manager import talk


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture
def gs(game_data):
    # Fresh campaign for testing
    return new_campaign(game_data, seed=208)


def test_deterministic_intent():
    # Test keyword matching with correct mapping
    candidate_ids = ["reassure", "challenge", "listen", "promise_playtime"]
    
    # Matches "reassure" keywords (e.g., "morale", "slump", "public", "support", "worry", "ok", "fine")
    assert llm_talk.deterministic_intent("I want to reassure the team", candidate_ids) == "reassure"
    assert llm_talk.deterministic_intent("Don't worry about the slump", candidate_ids) == "reassure"
    
    # Matches "challenge" keywords (e.g., "blunt", "improve", "better", "standard", "step it up")
    assert llm_talk.deterministic_intent("We need to improve standards", candidate_ids) == "challenge"
    
    # Case insensitivity
    assert llm_talk.deterministic_intent("LISTEN to me", candidate_ids) == "listen"
    
    # No matches fallback to first candidate
    assert llm_talk.deterministic_intent("some random message", candidate_ids) == "reassure"
    
    # Test different candidates order fallback
    assert llm_talk.deterministic_intent("some random message", ["challenge", "listen"]) == "challenge"


def test_provider_resolution(monkeypatch):
    monkeypatch.setattr(llm_talk, "_ENV_LOADED", True)  # Skip reading actual .env
    
    # Off mode
    monkeypatch.setenv("SOCIAL_LLM", "off")
    assert llm_talk.provider() is None
    
    # OpenRouter mode with key
    monkeypatch.setenv("SOCIAL_LLM", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
    cfg = llm_talk.provider()
    assert cfg is not None
    assert cfg["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert cfg["key"] == "sk-test-key"
    assert cfg["model"] == "google/gemini-2.5-flash"
    
    # OpenRouter custom model
    monkeypatch.setenv("SOCIAL_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")
    cfg = llm_talk.provider()
    assert cfg["model"] == "meta-llama/llama-3.3-70b-instruct"
    
    # Auto mode with key
    monkeypatch.setenv("SOCIAL_LLM", "auto")
    cfg = llm_talk.provider()
    assert cfg is not None
    assert cfg["key"] == "sk-test-key"
    
    # Auto mode without key or base URL
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert llm_talk.provider() is None
    
    # Local mode
    monkeypatch.setenv("SOCIAL_LLM", "local")
    monkeypatch.setenv("SOCIAL_LLM_BASE_URL", "http://localhost:11434/v1")
    cfg = llm_talk.provider()
    assert cfg is not None
    assert cfg["url"] == "http://localhost:11434/v1/chat/completions"
    assert cfg["key"] == ""
    assert cfg["model"] == "llama3.2"
    
    # Local custom model
    monkeypatch.setenv("SOCIAL_LLM_LOCAL_MODEL", "my-local-llama")
    cfg = llm_talk.provider()
    assert cfg["model"] == "my-local-llama"


def test_process_chat_fallback(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(llm_talk, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm_talk, "provider", lambda: None)
    
    player_id = gs.teams[gs.acting_team_id].player_ids[0]
    p = gs.players[player_id]
    p.morale = 80.0
    p.contract_weeks_left = 24
    p.stamina = 100.0
    p.form = 90.0
    
    # First verify we can talk
    ok, why = talk.can_talk(gs, player_id)
    assert ok, f"Should be able to talk, but: {why}"
    
    # Trigger check_in conversation using "banter" keyword
    text = "Let's joke and have some fun"
    save_code = "TEST_FALLBACK"
    
    res = llm_talk.process_chat(gs, player_id, text, save_code)
    
    # Validate result
    assert res["ok"] is True
    assert res["ai"] is False
    assert res["intent"] == "banter"
    assert "message" in res
    assert "effects" in res
    
    # Verify GameState side-effects
    assert gs.talked_week == talk.week_key(gs)
    
    # Verify sidecar caching
    cache_data = llm_talk.load_talk_cache(save_code)
    cache_key = f"{gs.season}_{gs.week}_{gs.acting_team_id}_{player_id}"
    assert cache_key in cache_data
    history = cache_data[cache_key]
    assert history["intent"] == "banter"
    assert history["ai"] is False
    assert history["message"] == res["message"]
    assert history["effects"] == res["effects"]
    
    # Talking again in the same week should raise ValueError
    with pytest.raises(ValueError) as exc:
        llm_talk.process_chat(gs, player_id, "Banter again", save_code)
    assert "already held this week's 1:1" in str(exc.value)


def test_process_chat_llm_mock(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(llm_talk, "CACHE_DIR", tmp_path)
    
    # Enable provider
    monkeypatch.setattr(llm_talk, "provider", lambda: {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": "sk-mock-key",
        "model": "google/gemini-2.5-flash"
    })
    
    player_id = gs.teams[gs.acting_team_id].player_ids[0]
    p = gs.players[player_id]
    p.morale = 80.0
    p.contract_weeks_left = 24
    p.stamina = 100.0
    p.form = 90.0
    
    # Mock LLM response for praise (positive outcome)
    mock_resp = {
        "intent": "praise",
        "reply_positive": "Wow, thank you! I'll keep it up.",
        "reply_negative": "I don't care about praise."
    }
    calls = []
    
    def mock_call(cfg, payload):
        calls.append(payload)
        return mock_resp
        
    monkeypatch.setattr(llm_talk, "_call", mock_call)
    
    save_code = "TEST_LLM"
    res = llm_talk.process_chat(gs, player_id, "You did an excellent job", save_code)
    
    assert len(calls) == 1
    assert res["ok"] is True
    assert res["ai"] is True
    assert res["intent"] == "praise"
    assert res["message"] == "Wow, thank you! I'll keep it up."
    
    # Now verify negative/bristle response routing
    # We'll reset talked_week and mock talk.resolve to return negative effects
    gs.talked_week = None
    
    def mock_bristle_resolve(gs, pid, option_id):
        return True, "Player bristles. That landed badly.", {"morale": -5.0, "form": 0.0, "chemistry": -1.0}
        
    monkeypatch.setattr(talk, "resolve", mock_bristle_resolve)
    
    mock_resp_neg = {
        "intent": "praise",
        "reply_positive": "Sure, I'll step it up.",
        "reply_negative": "Don't talk to me like that. I am doing my best."
    }
    monkeypatch.setattr(llm_talk, "_call", lambda cfg, payload: mock_resp_neg)
    
    res_neg = llm_talk.process_chat(gs, player_id, "Step it up", save_code)
    
    assert res_neg["ok"] is True
    assert res_neg["ai"] is True
    assert res_neg["intent"] == "praise"
    assert res_neg["message"] == "Don't talk to me like that. I am doing my best."


def test_server_endpoints(game_data, tmp_path, monkeypatch):
    monkeypatch.setattr(llm_talk, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm_talk, "provider", lambda: None)  # Fallback mode
    
    # Initialize game & register with server GameProxy context
    gs = new_campaign(game_data, seed=209)
    game = server._Game(game_data, "TEST_SERVER_CODE", gs=gs)
    
    player_id = gs.teams[gs.acting_team_id].player_ids[0]
    p = gs.players[player_id]
    p.morale = 80.0
    p.contract_weeks_left = 24
    p.stamina = 100.0
    p.form = 90.0
    
    # Bind request context var so S.gs / S.code work
    token = server._ctx.set(server._ReqCtx(game, gs.acting_team_id))
    try:
        # 1. GET /api/talk/{player_id} when available
        res_get = server.talk_topic(player_id)
        assert res_get["available"] is True
        assert "topic" in res_get
        assert "options" in res_get
        # Test intermediate choice generation
        gen_body = server.GenerateChoicesBody(player_id=player_id, history=[])
        res_gen = server.talk_generate_choices(gen_body)
        assert res_gen["ok"] is True
        assert "player_response" in res_gen
        assert len(res_gen["choices"]) == 3
        
        # 2. POST /api/talk/chat normal execution
        body = server.TalkChatBody(player_id=player_id, text="Let's banter")
        res_post = server.talk_chat(body)
        
        assert res_post["ok"] is True
        assert res_post["ai"] is False
        assert res_post["intent"] == "banter"
        
        # Verify telemetry record
        assert len(gs.action_log) > 0
        last_action = gs.action_log[-1]
        assert last_action.kind == "talk_chat"
        assert last_action.params["player_id"] == player_id
        assert last_action.params["intent"] == "banter"
        assert last_action.params["ai"] == "False"
        
        # 3. GET /api/talk/{player_id} after talking (should return history)
        res_get_after = server.talk_topic(player_id)
        assert res_get_after["available"] is False
        assert res_get_after["reason"] == "you already held this week's 1:1"
        assert "history" in res_get_after
        assert res_get_after["history"]["intent"] == "banter"
        assert res_get_after["history"]["ai"] is False
        
        # 4. POST /api/talk/chat when already talked -> raises 409
        with pytest.raises(HTTPException) as exc:
            server.talk_chat(body)
        assert exc.value.status_code == 409
        
    finally:
        server._ctx.reset(token)
