"""Integration regressions authored during PR339 source review; no browser needed."""

from types import SimpleNamespace
import json

import numpy as np
import pytest

from esports_sim.manager.learned_manager_policy import (
    ACTION_VOCAB, LearnedManagerModel, LearnedManagerPolicy,
    conditioned_features,
)
from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.decision_env import (
    HeadlessManagerEnv, InvalidManagerAction, validate_manager_action,
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
@pytest.mark.parametrize("tier", [None, "", "unknown", [], {}, False])
def test_malformed_recovery_is_refused_before_observation(tier, monkeypatch):
    env = object.__new__(HeadlessManagerEnv)

    def unexpected_observation():
        raise AssertionError("malformed recovery must fail before observing")

    monkeypatch.setattr(env, "observe", unexpected_observation)
    with pytest.raises(InvalidManagerAction, match="recovery tier"):
        env.step({"kind": "book_recovery", "params": {"tier": tier}})


@pytest.mark.campaign
@pytest.mark.parametrize("tier", ["day", "retreat"])
def test_shared_preflight_retains_valid_recovery_parameters(tier):
    action = {"kind": "book_recovery", "params": {"tier": tier}}
    assert validate_manager_action(action) == ("book_recovery", {"tier": tier})


@pytest.mark.campaign
def test_pre_recovery_checkpoint_loads_and_retains_its_indexed_vocabulary(tmp_path):
    path = tmp_path / "incumbent.json"
    vocab = tuple(reversed([kind for kind in ACTION_VOCAB if kind != "book_recovery"]))
    width = conditioned_features({"features": {}}).size
    weights = np.zeros((len(vocab), width))
    weights[vocab.index("advance"), 0] = 7.0
    model = LearnedManagerModel(action_weights=weights, action_vocab=vocab)
    model.save(path)
    before = path.read_bytes()
    loaded = LearnedManagerModel.load(path)
    assert path.read_bytes() == before
    assert loaded.action_vocab == vocab
    assert np.array_equal(loaded.action_weights, weights)
    policy = loaded.make_policy(generate_profile(1339, "legacy-recovery-subset"))
    observation = {"features": {}, "season": 1, "week": 1, "legal_actions": {
        "advance": {"enabled": True},
        "book_recovery": {"enabled": True, "options": [{"tier": "day"}]},
    }}
    assert "book_recovery" not in policy.action_probabilities(observation)
    assert policy.choose_action(observation)["kind"] == "advance"
    re_saved = tmp_path / "resaved.json"
    loaded.save(re_saved)
    assert json.loads(re_saved.read_text(encoding="utf-8"))["action_vocab"] == list(vocab)
    reloaded = LearnedManagerModel.load(re_saved)
    assert reloaded.action_vocab == vocab
    assert np.array_equal(reloaded.action_weights, weights)


@pytest.mark.campaign
@pytest.mark.parametrize("vocab", [[], ["advance", "advance"],
                                   ["advance", "unknown"], ["book_recovery"],
                                   "advance", ["advance", None]])
def test_malformed_pre_recovery_checkpoint_is_rejected_without_modification(tmp_path, vocab):
    path = tmp_path / "malformed.json"
    width = conditioned_features({"features": {}}).size
    model = LearnedManagerModel(action_weights=np.zeros((len(ACTION_VOCAB), width)))
    model.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["action_vocab"] = vocab
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
