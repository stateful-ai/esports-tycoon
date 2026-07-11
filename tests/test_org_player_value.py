"""Org-specific player valuation, behaviour and saved observability."""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import market, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.schemas.player import PlayerBadge


@pytest.fixture
def campaign(game_data):
    return new_campaign(game_data, seed=123)


def _rival(gs):
    return next(t for t in gs.teams.values() if t.id != gs.user_team_id and t.tier == 1)


def _make_icon(gs, tid: str, pid: str) -> None:
    p = gs.players[pid]
    p.personality_tags = list(set(p.personality_tags) | {"fan_favorite", "streamer", "star_player"})
    p.badges.append(PlayerBadge(id="superstar"))
    p.followers = 1_000_000
    p.stream_load = 70
    p.tenure_weeks = 180
    gs.teams[tid].captain_id = pid
    gs.teams[tid].balance = 0


def test_home_org_values_icon_above_portable_buyer_value(campaign) -> None:
    gs = campaign
    seller = _rival(gs)
    pid = max(seller.player_ids, key=lambda q: market.player_quality(gs.players[q]))
    _make_icon(gs, seller.id, pid)
    home = market.org_player_valuation(gs, seller.id, pid, "sell")
    buyer = market.org_player_valuation(gs, gs.user_team_id, pid, "buy")
    assert home["stance"] == "not for sale"
    assert home["value"] > buyer["value"]
    assert "club pillar" in home["components"]
    assert "supporter favorite" in home["components"]
    assert "audience revenue" in home["components"]


def test_ai_refuses_cash_for_not_for_sale_icon_and_records_why(campaign) -> None:
    gs = campaign
    seller = _rival(gs)
    pid = max(seller.player_ids, key=lambda q: market.player_quality(gs.players[q]))
    _make_icon(gs, seller.id, pid)
    gs.teams[gs.user_team_id].balance = 10_000_000
    ok, msg = market.user_bid(gs, pid)
    assert not ok and "pillar" in msg
    entry = gs.market_decisions[-1]
    assert entry.kind == "bid" and entry.outcome == "rejected"
    assert entry.stance == "not for sale"
    assert entry.components["supporter favorite"] > 0


def test_pillar_departure_has_supporter_cost_and_is_audited(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    pid = max(gs.teams[tid].player_ids, key=lambda q: market.player_quality(gs.players[q]))
    _make_icon(gs, tid, pid)
    before_fans = gs.teams[tid].fan_count
    before_sentiment = gs.sentiment(tid)
    ok, _ = market.release_player(gs, tid, pid)
    assert ok
    assert gs.teams[tid].fan_count < before_fans
    assert gs.sentiment(tid) < before_sentiment
    assert gs.market_decisions[-1].kind == "release"


def test_market_decisions_round_trip_and_v11_migrates(tmp_path, campaign) -> None:
    gs = campaign
    pid = gs.teams[gs.user_team_id].player_ids[0]
    market.renew_contract(gs, gs.user_team_id, pid)
    path = tmp_path / "career.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert loaded.market_decisions == gs.market_decisions

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("market_decisions")
    raw["schema_version"] = 11
    path.write_text(json.dumps(raw), encoding="utf-8")
    migrated = GameState.load(path)
    assert migrated.market_decisions == []
