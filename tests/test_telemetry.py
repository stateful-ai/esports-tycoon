"""Analytics pass: the action log, weekly state snapshots, reward
shaping, the RL episode exporter, and the match token corpus."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from esports_sim.manager import telemetry
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=321)


# ---------------------------------------------------------------------------
# Action log


def test_record_action_attributes_the_seat(campaign):
    gs = campaign
    telemetry.record_action(gs, "set_training", {"focus": "mental"})
    a = gs.action_log[-1]
    assert a.kind == "set_training"
    assert a.team_id == gs.user_team_id
    assert a.manager_id == f"mgr_{gs.user_team_id}"
    assert a.params == {"focus": "mental"}
    assert (a.season, a.week, a.phase) == (gs.season, gs.week, gs.phase)


def test_record_action_rejects_unknown_kind(campaign):
    with pytest.raises(ValueError):
        telemetry.record_action(campaign, "definitely_not_a_kind")


def test_params_are_stringified_and_sorted(campaign):
    gs = campaign
    telemetry.record_action(
        gs, "set_tactics", {"pace": 62.0, "aggression": 40, "flag": True}
    )
    p = gs.action_log[-1].params
    assert p == {"aggression": "40", "flag": "True", "pace": "62.0"}
    assert list(p) == sorted(p)


# ---------------------------------------------------------------------------
# Weekly snapshots


def test_snapshots_append_per_seat_per_week(campaign, game_data):
    gs = campaign
    for _ in range(2):
        advance_week(gs, game_data)
    seat = f"mgr_{gs.user_team_id}"
    snaps = gs.telemetry_snaps[seat]
    assert [s.week for s in snaps] == [1, 2]
    assert all(s.team_id == gs.user_team_id for s in snaps)
    f = snaps[-1].features
    # The vector is stable-keyed, floats only, and manager-visible.
    assert list(f) == sorted(f)
    assert all(isinstance(v, float) for v in f.values())
    for key in ("balance", "roster_ca", "league_position", "board_patience"):
        assert key in f
    assert f["board_patience"] == -1.0  # sandbox: no board


def test_snapshots_are_deterministic(game_data):
    a = new_campaign(game_data, seed=99)
    b = new_campaign(game_data, seed=99)
    for _ in range(2):
        advance_week(a, game_data)
        advance_week(b, game_data)
    assert {k: [s.model_dump() for s in v] for k, v in a.telemetry_snaps.items()} == {
        k: [s.model_dump() for s in v] for k, v in b.telemetry_snaps.items()
    }


def test_save_roundtrip_and_v5_load(tmp_path, campaign, game_data):
    gs = campaign
    telemetry.record_action(gs, "advance")
    advance_week(gs, game_data)
    path = tmp_path / "save.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert [a.model_dump() for a in loaded.action_log] == [
        a.model_dump() for a in gs.action_log
    ]
    assert loaded.telemetry_snaps == gs.telemetry_snaps

    # A v5 save (no telemetry fields) loads with empty defaults.
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("action_log")
    data.pop("telemetry_snaps")
    data["schema_version"] = 5
    v5 = tmp_path / "v5.json"
    v5.write_text(json.dumps(data), encoding="utf-8")
    migrated = GameState.load(v5)
    assert migrated.action_log == []
    assert migrated.telemetry_snaps == {}


# ---------------------------------------------------------------------------
# Reward shaping


def test_reward_components_and_scalar():
    prev = {"wins": 3.0, "round_diff": 10.0, "balance": 500_000.0,
            "reputation": 50.0, "sentiment": 50.0, "board_patience": 70.0}
    now = {"wins": 4.0, "round_diff": 16.0, "balance": 450_000.0,
           "reputation": 51.0, "sentiment": 54.0, "board_patience": 72.0}
    comps = telemetry.reward_components(prev, now)
    assert comps["wins_delta"] == 1.0
    assert comps["round_diff_delta"] == 6.0
    assert comps["balance_delta_100k"] == -0.5
    assert comps["patience_delta"] == 2.0
    assert comps["insolvent"] == 0.0
    expected = sum(
        telemetry.REWARD_WEIGHTS[k] * v
        for k, v in comps.items()
        if k in telemetry.REWARD_WEIGHTS
    )
    assert comps["reward"] == pytest.approx(expected, abs=1e-4)


def test_reward_sandbox_has_no_patience_term():
    prev = {"board_patience": -1.0}
    now = {"board_patience": -1.0}
    assert telemetry.reward_components(prev, now)["patience_delta"] == 0.0


def test_reward_dismissal_penalty():
    comps = telemetry.reward_components({}, {}, dismissed=True)
    assert comps["dismissed"] == 1.0
    assert comps["reward"] <= telemetry.REWARD_WEIGHTS["dismissed"]


# ---------------------------------------------------------------------------
# Exporter + tokenizer (script smoke tests, run in-process via runpy-style
# subprocess so the CLI contract is what's exercised)


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_export_telemetry_script(tmp_path, campaign, game_data):
    gs = campaign
    telemetry.record_action(gs, "set_training", {"focus": "team"})
    for _ in range(2):
        telemetry.record_action(gs, "advance")
        advance_week(gs, game_data)
    save = tmp_path / "probe.json"
    gs.save(save)
    stem = tmp_path / "out"
    r = _run("export_telemetry.py", str(save), str(stem))
    assert r.returncode == 0, r.stderr
    episodes = [
        json.loads(ln)
        for ln in (tmp_path / "out.episodes.jsonl").read_text().splitlines()
    ]
    assert len(episodes) == 1  # 2 snaps -> 1 transition
    ep = episodes[0]
    assert ep["seat"] == f"mgr_{gs.user_team_id}"
    assert set(ep["actions"][0]) == {"kind", "params", "source"}
    assert "reward" in ep and "wins_delta" in ep["reward_components"]
    assert ep["state"]["week"] == 1.0 and ep["next_state"]["week"] == 2.0
    actions = (tmp_path / "out.actions.jsonl").read_text().splitlines()
    assert len(actions) == 3
    assert (tmp_path / "out.chronicle.jsonl").exists()


def test_token_dump_deterministic_and_in_vocab(tmp_path):
    r1 = _run("dump_season_tokens.py", "4", "7", str(tmp_path / "a"))
    assert r1.returncode == 0, r1.stderr
    r2 = _run("dump_season_tokens.py", "4", "7", str(tmp_path / "b"))
    assert r2.returncode == 0, r2.stderr
    assert (tmp_path / "a.tokens.jsonl").read_bytes() == (
        tmp_path / "b.tokens.jsonl"
    ).read_bytes()
    vocab = json.loads((tmp_path / "a.vocab.json").read_text())
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "a.tokens.jsonl").read_text().splitlines()
    ]
    assert len(lines) == 4
    for ln in lines:
        assert all(0 <= t < len(vocab["tokens"]) for t in ln["tokens"])
        text = [vocab["tokens"][t] for t in ln["tokens"]]
        assert text[0] == "MATCH_START" and text[-1] == "MATCH_END"
        # A match is first-to-13: at least 13 round ends.
        assert sum(1 for t in text if t.startswith("ROUND_END_")) >= 13


def test_vocab_is_pinned():
    """The token vocabulary is a data contract for trained models —
    changing it must be a deliberate VOCAB_VERSION bump, not drift."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dump_season_tokens", SCRIPTS / "dump_season_tokens.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    vocab = mod.build_vocab()
    assert mod.VOCAB_VERSION == 1
    assert len(vocab) == 75
    assert vocab == sorted(vocab)
    import hashlib

    digest = hashlib.blake2b(
        "|".join(vocab).encode("ascii"), digest_size=8
    ).hexdigest()
    assert digest == "d8ba33faa4aadf06", (
        "vocab drifted - if intentional, bump VOCAB_VERSION and re-bless"
    )
