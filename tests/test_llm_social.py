"""LLM social ghost-writer (web/llm_social.py): provider resolution,
prompt grounding, response parsing, cache overlay — all without a
network (the transport is faked)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.registry import load_all
from esports_sim.web import llm_social


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture(scope="module")
def played(game_data):
    gs = new_campaign(game_data, seed=207)
    for _ in range(2):
        advance_week(gs, game_data)
    return gs


def test_provider_resolution(monkeypatch):
    monkeypatch.setattr(llm_social, "_ENV_LOADED", True)  # skip .env file
    monkeypatch.setenv("SOCIAL_LLM", "off")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert llm_social.provider() is None
    monkeypatch.setenv("SOCIAL_LLM", "auto")
    cfg = llm_social.provider()
    assert cfg is not None and "openrouter.ai" in cfg["url"]
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert llm_social.provider() is None  # auto without key or base url
    monkeypatch.setenv("SOCIAL_LLM", "local")
    monkeypatch.setenv("SOCIAL_LLM_BASE_URL", "http://localhost:11434/v1")
    cfg = llm_social.provider()
    assert cfg is not None
    assert cfg["url"] == "http://localhost:11434/v1/chat/completions"
    assert cfg["key"] == ""


def test_payload_grounds_facts_and_personas(played):
    gs = played
    posts = [p.model_dump() for p in gs.social_feed[-6:]]
    assert posts, "two weeks produced no posts"
    payload = llm_social.build_payload(posts, gs, "test-model")
    user = payload["messages"][1]["content"]
    for p in posts:
        assert p["text"] in user  # every fact line rides along
        assert p["id"] in user
    sys_msg = payload["messages"][0]["content"]
    assert "never invent" in sys_msg
    player_posts = [p for p in posts if p["author_kind"] == "player"]
    if player_posts:
        assert gs.players[player_posts[0]["author_id"]].handle in user


def test_parse_response_strict_and_sloppy():
    good = json.dumps({"posts": [{"id": "a1", "text": "we move."}]})
    assert llm_social.parse_response(good) == {"a1": "we move."}
    sloppy = "Sure! Here you go:\n" + good + "\nHope that helps!"
    assert llm_social.parse_response(sloppy) == {"a1": "we move."}
    assert llm_social.parse_response("no json here") == {}
    assert llm_social.parse_response(json.dumps({"posts": [{"id": "x"}]})) == {}


def test_overlay_swaps_text_and_keeps_fact(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_social, "CACHE_DIR", tmp_path)
    feed = [
        {"id": "p1", "text": "TEMPLATE one", "kind": "hype"},
        {"id": "p2", "text": "TEMPLATE two", "kind": "result"},
    ]
    llm_social._save_cache("TESTW", {"p1": "ghost-written one"})
    out = llm_social.overlay("TESTW", feed)
    assert out[0]["text"] == "ghost-written one"
    assert out[0]["fact"] == "TEMPLATE one"
    assert out[0]["ai"] is True
    assert out[1]["text"] == "TEMPLATE two"
    assert out[1]["ai"] is False


def test_enqueue_writes_cache_via_fake_transport(
    tmp_path, monkeypatch, played, game_data
):
    import esports_sim.web.server as server_mod

    monkeypatch.setattr(llm_social, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm_social, "_ENV_LOADED", True)
    monkeypatch.setenv("SOCIAL_LLM", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    calls: list[dict] = []

    def fake_call(cfg, payload):
        calls.append(payload)
        items = json.loads(
            payload["messages"][1]["content"].split("posts:\n", 1)[-1]
        )
        return {
            it["id"]: f"[ai] {it['fact'][:40]}"
            for it in items["posts"]
        }

    monkeypatch.setattr(llm_social, "_call", fake_call)
    game = server_mod._Game(game_data, "TESTW2", gs=played)

    # Run synchronously for the test: patch Thread to run inline.
    class InlineThread:
        def __init__(self, target=None, **kw):
            self._t = target

        def start(self):
            self._t()

    monkeypatch.setattr(llm_social.threading, "Thread", InlineThread)
    llm_social._ATTEMPTED.pop("TESTW2", None)
    assert llm_social.enqueue(game) is True
    assert calls, "the fake transport was never hit"
    cache = llm_social.load_cache("TESTW2")
    assert cache and all(v.startswith("[ai]") for v in cache.values())
    # Catch-up passes drain the remaining recent posts batch by batch,
    # then the well runs dry.
    for _ in range(6):
        if not llm_social.enqueue(game):
            break
    assert llm_social.enqueue(game) is False
    assert len(llm_social.load_cache("TESTW2")) > len(cache) or len(
        calls
    ) == 1  # either more got written, or one batch covered everything
