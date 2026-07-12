"""Regression: starting a NEW solo game in the default fictional (non-pack)
world must succeed.

The lobby's fictional team ids are GENERATED from the seed (e.g.
``team_adriatic_sirens``) and are NOT in the static registry -- ``gd.teams``
holds only the two YAML starters. ``Lobby.create_game`` therefore has to
validate a pick against a same-seed campaign preview, not against
``gd.teams`` (which used to 422 every fictional pick from the lobby).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from esports_sim.manager import new_campaign
from esports_sim.web import server


def _fresh_lobby(tmp_path, monkeypatch) -> server.Lobby:
    # Lobby persists its session map + world saves under a RELATIVE "saves/"
    # dir; run in a tmp cwd so the test never reads or writes the real one.
    monkeypatch.chdir(tmp_path)
    return server.Lobby()


def test_new_solo_game_fictional_world_succeeds(tmp_path, monkeypatch) -> None:
    lobby = _fresh_lobby(tmp_path, monkeypatch)
    seed = 2026
    # A GENERATED team -- exactly the kind the lobby offers, and the kind that
    # used to be rejected because its id isn't in the static registry.
    preview = new_campaign(lobby.gd, seed=seed)
    generated = sorted(set(preview.teams) - set(lobby.gd.teams))
    assert generated, "fictional world should generate teams beyond the starters"
    team_id = generated[0]

    game = lobby.create_game("sid-solo", team_id, seed=seed, shared=False)

    assert game.gs is not None
    assert team_id in game.gs.teams
    assert game.gs.user_team_id == team_id


def test_new_game_still_rejects_unknown_team(tmp_path, monkeypatch) -> None:
    # Widening the accepted set to the generated league must NOT let a
    # genuinely nonexistent id through.
    lobby = _fresh_lobby(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        lobby.create_game("sid-bad", "team_not_a_real_id", seed=2026, shared=False)
    assert exc.value.status_code == 422


def test_delete_saved_world_removes_files_and_history(tmp_path, monkeypatch) -> None:
    lobby = _fresh_lobby(tmp_path, monkeypatch)
    game = lobby.create_game("sid-owner", "team_nexus", seed=2026, shared=False)
    code = game.code
    lobby.leave("sid-owner")

    assert server._save_path_for(code).exists()
    assert lobby.delete_world("sid-owner", code) is None
    assert not server._save_path_for(code).exists()
    assert not server._meta_path_for(code).exists()
    assert lobby.worlds_for("sid-owner") == []


def test_delete_saved_shared_world_requires_everyone_to_leave(tmp_path, monkeypatch) -> None:
    lobby = _fresh_lobby(tmp_path, monkeypatch)
    game = lobby.create_game("sid-owner", "team_nexus", seed=2026, shared=True)
    code = game.code
    other_team = next(tid for tid in game.gs.teams if tid != "team_nexus")
    joined, err = lobby.join_game("sid-guest", code, other_team)
    assert joined is game
    assert err is None
    lobby.leave("sid-owner")

    assert "cannot be deleted" in (lobby.delete_world("sid-owner", code) or "")
    assert server._save_path_for(code).exists()
