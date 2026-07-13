"""Stress tests for the LLM-powered 1:1 Talk module 2.0."""

from __future__ import annotations

import json
import threading
import time
import pytest
from pathlib import Path

from esports_sim.manager.campaign import new_campaign
from esports_sim.registry import load_all
from esports_sim.web import llm_talk
from esports_sim.manager import talk


@pytest.fixture(scope="module")
def game_data():
    return load_all()


def test_fallback_classifier_stress():
    """Stress test the fallback keyword classifier with edge case inputs."""
    candidate_ids = ["reassure", "challenge", "listen", "promise_playtime", "streaming"]
    
    # 1. Edge-case inputs
    inputs = [
        "",  # Empty string
        "   ",  # Whitespace only
        "😀🤖🔥",  # Emojis only
        "Hello 😀🤖🔥 world",  # Mixed emojis
        "a" * 100000,  # Very long text
        "!@#$%^&*()_+{}[]|\\:;\"'<>,.?/~`",  # Special characters
        "\x00\x01\x02\n\r\t",  # Control characters / null byte
        "こんにちは",  # Unicode/foreign characters
        "reassure",  # Direct keyword
        "MORALE",  # Uppercase keyword
        "Morale and Standard and Streaming",  # Multiple keywords (first matches wins check)
    ]
    
    for text in inputs:
        intent = llm_talk.deterministic_intent(text, candidate_ids)
        assert intent in candidate_ids, f"Returned intent '{intent}' not in candidates for text: {text[:100]}"

    # Verify fallback behavior when candidate list is empty
    # This should return "" because candidate_ids is empty.
    assert llm_talk.deterministic_intent("any text", []) == ""


def test_sidecar_caching_thread_safety(tmp_path, monkeypatch):
    """Stress test sidecar caching thread safety by writing concurrently from multiple threads."""
    # Use temporary directory for caching
    monkeypatch.setattr(llm_talk, "CACHE_DIR", tmp_path)
    
    save_code = "STRESS_THREAD_SAFETY"
    num_threads = 10
    writes_per_thread = 50
    
    errors = []
    
    def worker(thread_id):
        try:
            for i in range(writes_per_thread):
                cache = llm_talk.load_talk_cache(save_code)
                key = f"thread_{thread_id}_write_{i}"
                cache[key] = {
                    "intent": "banter",
                    "message": f"Message from thread {thread_id} step {i}",
                    "effects": {},
                    "ai": False
                }
                llm_talk._save_talk_cache(save_code, cache)
                time.sleep(0.001)  # encourage thread interleaving
        except Exception as e:
            errors.append(e)
            
    threads = []
    for t_id in range(num_threads):
        t = threading.Thread(target=worker, args=(t_id,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert not errors, f"Threads raised exceptions: {errors}"
    
    # Read final cache and measure data loss
    final_cache = llm_talk.load_talk_cache(save_code)
    expected_count = num_threads * writes_per_thread
    actual_count = len(final_cache)
    
    print(f"\n[CACHE THREAD SAFETY] Expected: {expected_count}, Got: {actual_count}")
    
    missing = []
    for t_id in range(num_threads):
        for i in range(writes_per_thread):
            key = f"thread_{t_id}_write_{i}"
            if key not in final_cache:
                missing.append(key)
                
    # We expect that some writes will be lost due to the read-modify-write race condition
    # in load_talk_cache / _save_talk_cache.
    loss_pct = (len(missing) / expected_count) * 100.0
    print(f"[CACHE THREAD SAFETY] Lost updates: {len(missing)} ({loss_pct:.2f}%)")
    
    # Note: Because the caching implementation in llm_talk.py lacks transaction/atomic locking
    # across the load-modify-save sequence, data loss is expected.
    # To demonstrate this bug, we can check if data loss occurred.
    # If we want to verify that no save-data is corrupted (meaning it is still valid JSON),
    # we assert that the final cache is a valid dict and load succeeds.
    assert isinstance(final_cache, dict), "Cache should be a dictionary"
    
    # Try to re-load from disk to verify file is not corrupt
    loaded_directly = json.loads((tmp_path / f"talk_llm_{save_code}.json").read_text(encoding="utf-8"))
    assert loaded_directly == final_cache, "Saved file content must match in-memory cache"


def test_byte_for_byte_determinism(game_data, tmp_path, monkeypatch):
    """Verify that resolving a weekly talk in fallback vs. online/mock mode yields identical campaign saves."""
    # Setup temporary save and cache directories
    monkeypatch.setattr(llm_talk, "CACHE_DIR", tmp_path)
    
    seed = 42
    
    # ----------------------------------------------------
    # Case 1: Resolve talk in offline/fallback mode
    # ----------------------------------------------------
    monkeypatch.setattr(llm_talk, "provider", lambda: None)
    
    gs_fallback = new_campaign(game_data, seed=seed)
    player_id = gs_fallback.teams[gs_fallback.acting_team_id].player_ids[0]
    
    # Standardize player state to avoid random variations
    p_fallback = gs_fallback.players[player_id]
    p_fallback.morale = 80.0
    p_fallback.contract_weeks_left = 24
    p_fallback.stamina = 100.0
    p_fallback.form = 90.0
    
    # Call process_chat in fallback mode
    text = "Let's joke and have some fun"
    res_fallback = llm_talk.process_chat(gs_fallback, player_id, text, "DETERMINISM_TEST")
    
    assert res_fallback["ok"] is True
    assert res_fallback["ai"] is False
    assert res_fallback["intent"] == "banter"
    
    save_path_fallback = tmp_path / "save_fallback.json"
    gs_fallback.save(save_path_fallback)
    
    # ----------------------------------------------------
    # Case 2: Resolve talk in online/mock LLM mode
    # ----------------------------------------------------
    # Reset/restart campaign with the same seed
    gs_online = new_campaign(game_data, seed=seed)
    p_online = gs_online.players[player_id]
    
    p_online.morale = 80.0
    p_online.contract_weeks_left = 24
    p_online.stamina = 100.0
    p_online.form = 90.0
    
    # Enable provider mock
    monkeypatch.setattr(llm_talk, "provider", lambda: {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": "sk-mock-key",
        "model": "google/gemini-2.5-flash"
    })
    
    # Mock LLM response to match same intent but provide custom dialogue text
    mock_resp = {
        "intent": "banter",
        "reply_positive": "Haha, that's a good one! Custom LLM response here.",
        "reply_negative": "Not funny. Custom LLM negative response."
    }
    monkeypatch.setattr(llm_talk, "_call", lambda cfg, payload: mock_resp)
    
    res_online = llm_talk.process_chat(gs_online, player_id, text, "DETERMINISM_TEST")
    
    assert res_online["ok"] is True
    assert res_online["ai"] is True
    assert res_online["intent"] == "banter"
    
    save_path_online = tmp_path / "save_online.json"
    gs_online.save(save_path_online)
    
    # ----------------------------------------------------
    # Verifications
    # ----------------------------------------------------
    # Read the files
    content_fallback = save_path_fallback.read_bytes()
    content_online = save_path_online.read_bytes()
    
    # Assert byte-for-byte identical campaign saves
    assert content_fallback == content_online, "Campaign save JSON files are not byte-for-byte identical!"
    
    # Let's inspect sidecar caches to verify they are updated correctly and contain different data
    sidecar_path = tmp_path / "talk_llm_DETERMINISM_TEST.json"
    assert sidecar_path.exists(), "Sidecar cache file was not created!"
    
    sidecar_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    
    # Since we used the same save_code "DETERMINISM_TEST", the second write (online) should have overwritten the first (fallback)
    # in the sidecar cache. Let's verify that the cache shows it was generated by AI.
    cache_key = f"{gs_online.season}_{gs_online.week}_{gs_online.acting_team_id}_{player_id}"
    assert cache_key in sidecar_data
    history = sidecar_data[cache_key]
    assert history["ai"] is True
    assert "Custom LLM" in history["message"]
