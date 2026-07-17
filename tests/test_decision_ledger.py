"""Decision ledger: settlements are grounded, bounded, and deterministic.

The ledger is a pure derived reader (manager/decision_ledger.py): it grades
recent HUMAN decisions (telemetry.action_log) against data the save already
stores (dev/stat history, played fixture lines, season aggregates). These
tests drive a small headless campaign through real decisions and pin:

  (a) each covered decision kind produces one grounded settlement,
  (b) the weekly inbox digest carries the top settlements,
  (c) the whole thing is deterministic (same seed + same script -> same
      rows AND byte-identical GameState), and
  (d) a hands-off campaign (no recorded actions) settles nothing.
"""

from __future__ import annotations

import pytest

from esports_sim.manager import (
    advance_week,
    decision_ledger,
    market,
    new_campaign,
    telemetry,
)
from esports_sim.manager.state import GamePlan, GameState
from esports_sim.registry import GameData

VERDICTS = {
    decision_ledger.PAID_OFF,
    decision_ledger.NEUTRAL,
    decision_ledger.BACKFIRED,
}


def _next_fixture_week(gs: GameState, gd: GameData, uid: str, cap: int = 12):
    """Advance until the user has an unplayed fixture this week."""
    while gs.week < cap:
        fx = gs.team_fixture(uid)
        if fx is not None and not fx.played:
            return fx
        advance_week(gs, gd)
    return None


def _scripted_campaign(gd: GameData, seed: int) -> tuple[GameState, list[dict], list[dict]]:
    """One small campaign that makes (and records) a training call, a
    game-plan focus target, and a per-map lineup override, then settles
    them. Returns (gs, training_rows, matchweek_rows)."""
    gs = new_campaign(gd, seed=seed)
    uid = gs.user_team_id
    advance_week(gs, gd)
    advance_week(gs, gd)

    # Week 3: an explicit training call (week 3 has a full baseline pair).
    assert gs.week == 3
    gs.training_focus[uid] = "mechanical"
    telemetry.record_action(
        gs, "set_training", {"focus": "mechanical", "delegate_to_coach": False}
    )
    advance_week(gs, gd)
    training_rows = decision_ledger.settlements(gs, uid, 1, 3)

    # Next match week: a focus target + a one-map lineup override.
    fx = _next_fixture_week(gs, gd, uid)
    assert fx is not None, "no fixture found in the early regular season"
    opp = fx.team_b if fx.team_a == uid else fx.team_a
    target = sorted(gs.teams[opp].player_ids)[0]
    gs.game_plan = GamePlan(fixture_id=fx.id, focus_target=target)
    telemetry.record_action(
        gs, "set_game_plan",
        {
            "fixture_id": fx.id, "opponent": opp, "n_dials": 0,
            "site_focus": "", "focus_target": target, "one_match_lineup": False,
        },
    )
    five = sorted(gs.teams[uid].player_ids)[:5]
    assert fx.maps, "fixture has no planned maps"
    map_id = fx.maps[0]
    gs.map_lineups[f"{uid}|{fx.id}|{map_id}"] = five
    telemetry.record_action(
        gs, "set_lineup",
        {
            "agents": False, "default_five": False, "per_map": True,
            "fixture_id": fx.id, "map_id": map_id,
        },
    )
    match_week = gs.week
    advance_week(gs, gd)
    match_rows = decision_ledger.settlements(gs, uid, 1, match_week)
    return gs, training_rows, match_rows


@pytest.fixture(scope="module")
def scripted(game_data: GameData):
    return _scripted_campaign(game_data, seed=42)


# Co-locate the consumers of the module-scoped scripted campaign so
# `--dist loadgroup` builds it once instead of once per worker.
_SCRIPTED_GROUP = pytest.mark.xdist_group("decision_ledger_scripted")


@_SCRIPTED_GROUP
def test_training_settlement_is_grounded(scripted) -> None:
    _gs, training_rows, _match_rows = scripted
    rows = [r for r in training_rows if r["kind"] == "training"]
    assert len(rows) == 1
    r = rows[0]
    assert r["verdict"] in VERDICTS
    assert r["week"] == 3
    assert "mechanical" in r["text"]
    assert "typical week" in r["text"]
    assert r["text"].isascii()
    assert 0.0 <= r["signal"] <= 1.0


@_SCRIPTED_GROUP
def test_focus_target_and_lineup_settle_on_match_week(scripted) -> None:
    gs, _training_rows, match_rows = scripted
    kinds = {r["kind"] for r in match_rows}
    assert "focus_target" in kinds
    assert "lineup" in kinds
    for r in match_rows:
        assert r["verdict"] in VERDICTS
        assert r["text"].isascii()
    # Highest-signal first, deterministic ordering.
    signals = [r["signal"] for r in match_rows]
    assert signals == sorted(signals, reverse=True)
    # The dashboard read agrees with the tick-time read (pure derived data).
    assert decision_ledger.latest_settlements(gs, gs.user_team_id) == match_rows


@_SCRIPTED_GROUP
def test_inbox_digest_carries_top_settlements(scripted) -> None:
    gs, _training_rows, match_rows = scripted
    items = [
        it for it in gs.inboxes.get(gs.user_team_id, [])
        if it.title.startswith("Decisions settled")
    ]
    assert items, "settled decisions should produce an inbox digest"
    latest = items[-1]
    assert latest.category == "analytics"
    body_lines = latest.body.splitlines()
    assert 1 <= len(body_lines) <= decision_ledger.MAX_DIGEST
    for line in body_lines:
        assert line.startswith("- [")
        assert line.isascii()
    # The digest's first line is the highest-signal settlement.
    assert match_rows[0]["text"] in body_lines[0]


def test_signing_settles_after_fixed_delay(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=7)
    uid = gs.user_team_id
    fa = sorted(gs.free_agent_ids)[0]
    ok, msg = market.sign_player(gs, uid, fa)
    assert ok, msg
    telemetry.record_action(gs, "sign", {"player_id": fa})
    # Force the signing into the dressed five so they actually play.
    gs.teams[uid].lineup_ids = [fa] + sorted(
        pid for pid in gs.teams[uid].player_ids if pid != fa
    )[:4]
    sign_week = gs.week
    settle_week = sign_week + decision_ledger.SIGNING_SETTLE_WEEKS
    for _ in range(decision_ledger.SIGNING_SETTLE_WEEKS):
        advance_week(gs, game_data)
    rows = [
        r
        for r in decision_ledger.settlements(gs, uid, 1, settle_week)
        if r["kind"] == "signing"
    ]
    assert len(rows) == 1
    r = rows[0]
    assert r["verdict"] in VERDICTS
    assert gs.players[fa].handle in r["text"]
    assert "map(s) in their first weeks" in r["text"]
    # One-shot: the same signing does not settle again a week later.
    advance_week(gs, game_data)
    later = decision_ledger.settlements(gs, uid, 1, settle_week + 1)
    assert not [r for r in later if r["kind"] == "signing"]


@_SCRIPTED_GROUP
def test_state_endpoint_serializes_ledger(scripted, game_data: GameData) -> None:
    """The dashboard payload carries the settled rows verbatim -- the web
    layer is a thin passthrough over decision_ledger (no logic in JS)."""
    pytest.importorskip("fastapi")
    import esports_sim.web.server as server_mod

    gs, _training_rows, match_rows = scripted
    game = server_mod._Game(game_data, "TESTL", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))
    data = server_mod.state()
    assert data["decision_ledger"] == match_rows


def test_settlements_are_deterministic(game_data: GameData) -> None:
    gs_a, train_a, match_a = _scripted_campaign(game_data, seed=99)
    gs_b, train_b, match_b = _scripted_campaign(game_data, seed=99)
    assert train_a == train_b
    assert match_a == match_b
    assert gs_a.model_dump_json() == gs_b.model_dump_json()


def test_hands_off_campaign_settles_nothing(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=5)
    uid = gs.user_team_id
    for _ in range(4):
        advance_week(gs, game_data)
    assert decision_ledger.latest_settlements(gs, uid) == []
    assert not [
        it for it in gs.inboxes.get(uid, [])
        if it.title.startswith("Decisions settled")
    ]
