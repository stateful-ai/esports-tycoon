"""Integration regressions authored during PR339 source review; no browser needed."""

from types import SimpleNamespace
import json

import numpy as np
import pytest

from esports_sim.manager.learned_manager_policy import (
    ACTION_VOCAB, LearnedManagerModel, LearnedManagerPolicy,
)
from esports_sim.playtest.session import PlaytestSession


@pytest.mark.campaign
def test_learned_recovery_uses_the_engine_legal_tier():
    policy = object.__new__(LearnedManagerPolicy)
    observation = {"legal_actions": {"book_recovery": {
        "enabled": True, "options": [{"tier": "retreat", "cost": 27000}],
    }}}
    assert policy._build_action(observation, "book_recovery", np.zeros(1)) == {
        "kind": "book_recovery", "params": {"tier": "retreat"},
    }


@pytest.mark.campaign
@pytest.mark.parametrize("legal", [
    {"enabled": False, "options": [{"tier": "day"}]},
    {"enabled": True, "options": []},
    {"enabled": True, "options": [{}]},
    {"enabled": True, "options": [{"tier": "unknown"}]},
])
def test_learned_recovery_refuses_unusable_masks(legal):
    policy = object.__new__(LearnedManagerPolicy)
    with pytest.raises(ValueError):
        policy._build_action({"legal_actions": {"book_recovery": legal}},
                             "book_recovery", np.zeros(1))


@pytest.mark.campaign
def test_pre_recovery_checkpoint_is_rejected_without_modification(tmp_path):
    path = tmp_path / "incumbent.json"
    model = LearnedManagerModel(action_weights=np.zeros((len(ACTION_VOCAB), 1)))
    model.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["action_vocab"].remove("book_recovery")
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="action vocabulary"):
        LearnedManagerModel.load(path)
    assert path.read_bytes() == before


@pytest.mark.web
def test_observation_retains_action_errors_exactly_once(tmp_path, monkeypatch):
    session = PlaytestSession(run_dir=tmp_path, base_url="http://127.0.0.1:1")
    monkeypatch.setattr(session, "_settle", lambda: None)
    monkeypatch.setattr(session, "snapshot", lambda: {})
    monkeypatch.setattr(session, "_shoot", lambda _: "screen.png")
    session._note("pageerror", "failure during click before observation")
    first = session.observe("click")
    assert [error["text"] for error in first.errors] == [
        "failure during click before observation",
    ]
    assert not session.observe("look").errors
    session.drain_errors()
    session._note("http", "409 expected refusal")
    assert session.observe("refusal").errors[0]["kind"] == "http"


@pytest.mark.web
@pytest.mark.parametrize("before,after", [("", "S1 W2"), ("S1 W1", ""),
                                          ("S1 W1", "S1 W1")])
def test_advance_requires_visible_before_and_after(tmp_path, monkeypatch, before, after):
    session = PlaytestSession(run_dir=tmp_path, base_url="http://127.0.0.1:1")
    contexts = iter((before, after))
    monkeypatch.setattr(session, "_context", lambda: next(contexts))
    values = iter(([], False))
    session._page = SimpleNamespace(evaluate=lambda _: next(values), click=lambda *a, **k: None)
    monkeypatch.setattr(session, "observe", lambda _, **kw: kw)
    assert session.advance_week()["ok"] is False
