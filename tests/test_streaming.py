"""Streaming: org revenue, the practice tradeoff, and the trade-value premium.

Three impacts, one system: a player's follower-driven streaming load
(social.py) pays the org a cut of stream revenue (economy.py), slows their
current-ability growth (training.py), and makes them cost more to prise away —
the more so for a cash-strapped org (market.py). A manager reins a player in
via the weekly 1:1 (talk.py), trading revenue + morale for development.
"""

from __future__ import annotations

import json

import numpy as np

from esports_sim.manager import economy, market, social, talk, training
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import SCHEMA_VERSION, GameState
from esports_sim.registry import GameData
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role


def _player(pid: str, ca: float, *, followers: int = 0, load: float = 0.0,
            age: int = 20, potential: float = 0.0) -> Player:
    return Player(
        id=pid, handle=pid, age=age, role=Role.DUELIST, playstyle=Playstyle.ENTRY,
        attributes={a: ca for a in ("aim_precision", "aim_reactivity", "movement")},
        followers=followers, stream_load=load, potential=potential,
    )


def _team() -> Team:
    return Team(id="t", name="T", tag="T")


# ---------------------------------------------------------------------------
# Impact 1: revenue


def test_player_stream_income_scales_with_followers_and_load() -> None:
    star = _player("s", 80, followers=1_000_000, load=100.0)
    gross = economy.player_stream_gross(star)
    assert gross == int(1_000_000 * economy.STREAM_RATE_PER_FOLLOWER)
    # The org keeps exactly its cut; the player keeps the rest.
    assert economy.player_stream_income(star) == int(gross * economy.STREAM_ORG_CUT)
    # No audience or not streaming -> no money.
    assert economy.player_stream_gross(_player("a", 80, followers=0, load=100.0)) == 0
    assert economy.player_stream_income(_player("b", 80, followers=1_000_000, load=0.0)) == 0
    # More load -> more money.
    half = _player("h", 80, followers=1_000_000, load=50.0)
    assert economy.player_stream_income(half) < economy.player_stream_income(star)


def test_apply_weekly_finance_counts_streaming(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=11)
    tid = gs.user_team_id
    team = gs.teams[tid]
    roster = gs.roster(tid)
    # Force a big streaming roster and confirm the income line reflects it.
    for p in roster:
        p.followers, p.stream_load = 800_000, 90.0
    expected_stream = economy.roster_stream_income(roster)
    assert expected_stream > 0
    base_income, _ = economy.apply_weekly_finance(team, roster)
    # Zeroing streaming drops income by exactly the streaming line.
    for p in roster:
        p.stream_load = 0.0
    no_stream_income, _ = economy.apply_weekly_finance(team, roster)
    assert base_income - no_stream_income == expected_stream


# ---------------------------------------------------------------------------
# Impact 2: the practice tradeoff


def test_stream_practice_mult_endpoints() -> None:
    assert training.stream_practice_mult(_player("z", 50, load=0.0)) == 1.0
    assert training.stream_practice_mult(_player("f", 50, load=100.0)) == (
        1.0 - training.STREAM_GROWTH_PENALTY_SPAN
    )
    assert training.stream_practice_mult(_player("h", 50, load=50.0)) == (
        1.0 - training.STREAM_GROWTH_PENALTY_SPAN / 2.0
    )


def test_heavy_streamer_develops_slower_but_still_grows() -> None:
    grinder = _player("grind", 50.0, load=0.0, age=18, potential=90.0)
    streamer = _player("stream", 50.0, load=90.0, age=18, potential=90.0)
    team = _team()
    # Identical draw streams so the ONLY difference is the streaming penalty.
    rg, rs = np.random.default_rng(3), np.random.default_rng(3)
    for _ in range(25):
        training.apply_training(team, [grinder], "mechanical", rg)
        training.apply_training(team, [streamer], "mechanical", rs)
    grind_gain = development_gain(grinder)
    stream_gain = development_gain(streamer)
    assert stream_gain > 0, "a streamer still develops, just slower"
    assert grind_gain > stream_gain * 1.1, "practice clearly out-develops streaming"


def development_gain(p: Player) -> float:
    return sum(p.attributes.values()) - 50.0 * len(p.attributes)


# ---------------------------------------------------------------------------
# Streaming load state (social): baseline, seed, heal


def test_stream_baseline_saturating_and_monotonic() -> None:
    assert social.stream_baseline(0) == 0.0
    assert social.stream_baseline(social.STREAM_LOAD_HALF) == 50.0
    lo, mid, hi = (
        social.stream_baseline(50_000),
        social.stream_baseline(500_000),
        social.stream_baseline(5_000_000),
    )
    assert lo < mid < hi <= 100.0


def test_campaign_seeds_stream_load(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=7)
    # Every player with an audience has a seeded load; a big account streams
    # more than a small one.
    loads = {p.id: p.stream_load for p in gs.players.values()}
    assert any(v > 0 for v in loads.values())
    a = max(gs.players.values(), key=lambda p: p.followers)
    b = min(gs.players.values(), key=lambda p: p.followers)
    assert a.stream_load >= b.stream_load


def test_reined_load_drifts_back_toward_baseline(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=7)
    pid = max(gs.players, key=lambda q: gs.players[q].followers)
    p = gs.players[pid]
    baseline = social.stream_baseline(p.followers)
    p.stream_load = social.STREAM_LOAD_MIN  # as if just reined all the way in
    social.stream_load_tick(gs)
    assert social.STREAM_LOAD_MIN < p.stream_load <= baseline, "it heals back up"


def test_stream_load_tick_is_deterministic_and_rng_free(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=7)
    b = GameState.model_validate_json(a.model_dump_json())
    social.stream_load_tick(a)  # takes only gs — no rng argument to drift
    social.stream_load_tick(b)
    assert a.model_dump_json() == b.model_dump_json()


# ---------------------------------------------------------------------------
# Impact 3: trade value relative to org income, amplified for the strapped


def _best_owned(gs: GameState) -> tuple[str, str]:
    tid = next(t for t in sorted(gs.teams) if gs.teams[t].player_ids)
    pid = max(gs.teams[tid].player_ids, key=lambda q: market.player_quality(gs.players[q]))
    return tid, pid


def test_transfer_ask_carries_a_streaming_premium(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=21)
    tid, pid = _best_owned(gs)
    p = gs.players[pid]
    p.followers, p.stream_load = 2_000_000, 0.0
    plain = market.transfer_ask(gs, pid)
    p.stream_load = 100.0  # now a genuine revenue engine
    streamed = market.transfer_ask(gs, pid)
    assert streamed > plain


def test_cash_strapped_owner_asks_more_for_the_same_revenue(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=21)
    tid, pid = _best_owned(gs)
    p = gs.players[pid]
    p.followers, p.stream_load = 500_000, 60.0  # a moderate share (below the cap)
    gs.teams[tid].balance = market.STREAM_STRAPPED_CASH  # comfortable
    rich = market.transfer_ask(gs, pid)
    gs.teams[tid].balance = 0  # broke: leans on the revenue
    broke = market.transfer_ask(gs, pid)
    assert broke > rich


def test_rich_buyer_values_streaming_less_than_a_poor_one(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=21)
    teams = sorted(gs.teams)
    owner = next(t for t in teams if gs.teams[t].player_ids)
    others = [t for t in teams if t != owner]
    rich, poor = others[0], others[1]
    gs.teams[rich].reputation, gs.teams[rich].fan_count = 99.0, 3_000_000
    gs.teams[poor].reputation, gs.teams[poor].fan_count = 1.0, 0
    pid = gs.teams[owner].player_ids[0]
    p = gs.players[pid]

    def premium_for(viewer: str) -> int:
        p.stream_load = 0.0
        base = market.perceived_value(gs, viewer, p)
        p.stream_load = 80.0
        return market.perceived_value(gs, viewer, p) - base

    p.followers = 1_000_000
    # Same audience is a bigger slice of the poor club's books, so it pays up.
    assert premium_for(poor) > premium_for(rich) > 0


# ---------------------------------------------------------------------------
# The manager lever: the "rein it in" 1:1


def test_rein_in_streaming_trades_morale_and_revenue_for_practice(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=33)
    tid = gs.user_team_id
    pid = max(gs.teams[tid].player_ids, key=lambda q: gs.players[q].followers)
    p = gs.players[pid]
    p.stream_load, p.morale = 80.0, 70.0
    load_before, morale_before = p.stream_load, p.morale
    inc_before = economy.player_stream_income(p)

    ok, _, effects = talk.rein_in_streaming(gs, pid)
    assert ok
    assert p.stream_load < load_before          # more practice
    assert p.morale < morale_before             # they resent it
    assert economy.player_stream_income(p) < inc_before  # less revenue
    assert effects["morale"] < 0
    # It spent the week's 1:1 — no second conversation this week.
    ok2, _, _ = talk.rein_in_streaming(gs, pid)
    assert not ok2
    assert not talk.can_talk(gs, pid)[0]


def test_cannot_rein_a_player_who_barely_streams(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=33)
    pid = gs.teams[gs.user_team_id].player_ids[0]
    gs.players[pid].stream_load = social.STREAM_LOAD_MIN
    ok, why = talk.can_rein_streaming(gs, pid)
    assert not ok and "barely" in why


def test_rein_in_streaming_is_deterministic(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=33)
    b = GameState.model_validate_json(a.model_dump_json())
    pid = a.teams[a.user_team_id].player_ids[0]
    a.players[pid].stream_load = b.players[pid].stream_load = 75.0
    talk.rein_in_streaming(a, pid)
    talk.rein_in_streaming(b, pid)
    assert a.players[pid].stream_load == b.players[pid].stream_load
    assert a.players[pid].morale == b.players[pid].morale


# ---------------------------------------------------------------------------
# Determinism + save compatibility


def test_streaming_campaign_stays_deterministic(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=44)
    b = new_campaign(game_data, seed=44)
    for _ in range(5):
        advance_week(a, game_data)
        advance_week(b, game_data)
    assert a.model_dump_json() == b.model_dump_json()
    # And the feature is actually live: someone is streaming after 5 weeks.
    assert any(p.stream_load > 0 for p in a.players.values())


def test_old_save_without_stream_load_loads(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=5)
    raw = gs.model_dump(mode="json")
    for p in raw["players"].values():
        p.pop("stream_load", None)
    reloaded = GameState.model_validate(raw)
    assert all(p.stream_load == 0.0 for p in reloaded.players.values())


def test_v10_save_migrates_to_current(game_data: GameData, tmp_path) -> None:
    gs = new_campaign(game_data, seed=5)
    raw = gs.model_dump(mode="json")
    raw["schema_version"] = 10
    for p in raw["players"].values():
        p.pop("stream_load", None)
    path = tmp_path / "v10.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == SCHEMA_VERSION
    assert all(p.stream_load == 0.0 for p in loaded.players.values())
