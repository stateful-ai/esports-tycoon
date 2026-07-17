"""Sim ahead (manager/sim_ahead.py): trigger detection, the batched
advance-until-interrupt loop, its action-log parity with manual advances,
campaign determinism, and the web endpoint."""

from __future__ import annotations

import numpy as np
import pytest

from esports_sim.manager import flavor_events, new_campaign, sim_ahead
from esports_sim.manager.campaign import default_five
from esports_sim.manager.economy import INSOLVENCY_FLOOR
from esports_sim.manager.state import ManagerContract, TransferOffer
from esports_sim.registry import GameData

UID = "team_nexus"


def _only(slug: str) -> tuple[sim_ahead.Trigger, ...]:
    return tuple(t for t in sim_ahead.TRIGGERS if t.slug == slug)


# -- trigger detection ---------------------------------------------------------


def test_triggers_fire_one_by_one(game_data: GameData) -> None:
    """Each data-driven trigger fires on the state it watches. An opening
    world can legitimately start a starter on a short deal (that's exactly
    why contract_expiry is advisory, not hard), so the baseline pushes the
    starting five's contracts out of the horizon first."""
    gs = new_campaign(game_data, seed=5, user_team_id=UID)
    for pid in default_five(gs, UID):
        p = gs.players[pid]
        p.contract_weeks_left = max(p.contract_weeks_left, 40)
    assert sim_ahead.stop_reason(gs, UID) is None

    # Own fixture this week is a playoff-stage match.
    f = gs.team_fixture(UID)
    assert f is not None
    f.stage = "semi"
    assert sim_ahead.stop_reason(gs, UID) == "big_match"
    f.stage = "regular"

    # A starter's contract inside the horizon.
    starter = gs.players[default_five(gs, UID)[0]]
    kept = starter.contract_weeks_left
    starter.contract_weeks_left = sim_ahead.CONTRACT_HORIZON_WEEKS - 1
    assert sim_ahead.stop_reason(gs, UID) == "contract_expiry"
    starter.contract_weeks_left = kept

    # An incoming bid for a starter (a bid for a benchwarmer wouldn't stop).
    rival = sorted(t for t in gs.teams if t != UID)[0]
    gs.transfer_offers.append(
        TransferOffer(
            player_id=starter.id, from_team=UID, to_team=rival,
            fee=120_000, expires_week=gs.week + 2,
        )
    )
    assert sim_ahead.stop_reason(gs, UID) == "transfer_offer"
    gs.transfer_offers.pop()

    # Board patience wearing thin (legacy-style seat contract).
    seat = gs.seat_for_session(UID)
    assert seat is not None and seat.contract is None  # sandbox baseline
    seat.contract = ManagerContract(
        start_season=gs.season, seasons=2, goal="top_half",
        patience=sim_ahead.BOARD_PATIENCE_BAR - 5,
    )
    assert sim_ahead.stop_reason(gs, UID) == "board_warning"
    seat.contract = None

    # Balance at the insolvency floor.
    bal = gs.teams[UID].balance
    gs.teams[UID].balance = INSOLVENCY_FLOOR - 1
    assert sim_ahead.stop_reason(gs, UID) == "insolvency_risk"
    gs.teams[UID].balance = bal

    # A pending flavor decision (would 409 a manual advance too).
    ev = flavor_events._build_event(gs, UID, np.random.default_rng(0))
    gs.flavor_events_by[UID] = ev
    assert sim_ahead.stop_reason(gs, UID) == "decision_pending"
    del gs.flavor_events_by[UID]

    # Season rollover: the next tick would run the whole offseason.
    gs.phase = "offseason"
    assert sim_ahead.stop_reason(gs, UID) == "season_rollover"
    gs.phase = "regular"

    assert sim_ahead.stop_reason(gs, UID) is None  # everything restored


def test_trigger_order_first_match_wins(game_data: GameData) -> None:
    """TRIGGERS is ordered — when several fire, the earlier one names the
    stop (the hard blockers outrank the advisories)."""
    gs = new_campaign(game_data, seed=5, user_team_id=UID)
    f = gs.team_fixture(UID)
    f.stage = "final"
    gs.players[default_five(gs, UID)[0]].contract_weeks_left = 3
    assert sim_ahead.stop_reason(gs, UID) == "big_match"  # precedes contracts
    gs.phase = "offseason"
    assert sim_ahead.stop_reason(gs, UID) == "season_rollover"


def test_every_trigger_has_a_toast_label() -> None:
    for t in sim_ahead.TRIGGERS:
        assert sim_ahead.label_for(t.slug) == t.label
        assert t.label.isascii() and t.label
    assert sim_ahead.label_for("roster_short")
    assert sim_ahead.label_for(None) is None


def test_hard_and_advisory_split() -> None:
    """The hard gates are the things a manual advance would refuse or the
    manager must never be simmed past; everything else is advisory."""
    hard = {t.slug for t in sim_ahead.TRIGGERS if t.hard}
    assert hard == {"decision_pending", "job_market", "season_rollover", "big_match"}


def test_advisory_trigger_stops_but_never_pins_at_zero(
    game_data: GameData,
) -> None:
    """A standing advisory condition (a starter's deal inside the horizon)
    stops the batch after ONE week instead of blocking it entirely — the
    press still makes progress, the toast says why it halted."""
    gs = new_campaign(game_data, seed=11, user_team_id=UID)
    starter = gs.players[default_five(gs, UID)[0]]
    starter.contract_weeks_left = sim_ahead.CONTRACT_HORIZON_WEEKS
    start = gs.week
    weeks, reason = sim_ahead.advance_until(
        gs, game_data, team_id=UID, max_weeks=4,
        triggers=_only("contract_expiry"),
    )
    assert (weeks, reason) == (1, "contract_expiry")
    assert gs.week == start + 1


# -- the loop ------------------------------------------------------------------


def test_advance_until_stops_before_the_trigger_week(game_data: GameData) -> None:
    """A playoff-stage fixture two weeks out stops the batch after exactly
    two ticks — the loop never sims past a decision point — and the action
    log carries the button press plus one advance per ticked week."""
    gs = new_campaign(game_data, seed=11, user_team_id=UID)
    start_week = gs.week
    f2 = gs.team_fixture(UID, start_week + 2)
    assert f2 is not None
    f2.stage = "semi"

    weeks, reason = sim_ahead.advance_until(
        gs, game_data, team_id=UID, max_weeks=4, triggers=_only("big_match")
    )
    assert (weeks, reason) == (2, "big_match")
    assert gs.week == start_week + 2
    kinds = [a.kind for a in gs.action_log]
    assert kinds == ["sim_ahead", "advance", "advance"]
    assert gs.action_log[0].params == {"max_weeks": "4"}
    assert all(a.team_id == UID for a in gs.action_log)


def test_advance_until_zero_weeks_when_already_at_a_trigger(
    game_data: GameData,
) -> None:
    """A trigger firing before the first tick means nothing sims — the
    manager falls back to the ordinary Advance button."""
    gs = new_campaign(game_data, seed=11, user_team_id=UID)
    gs.team_fixture(UID).stage = "semi"
    week = gs.week
    weeks, reason = sim_ahead.advance_until(
        gs, game_data, team_id=UID, max_weeks=4, triggers=_only("big_match")
    )
    assert (weeks, reason) == (0, "big_match")
    assert gs.week == week
    assert [a.kind for a in gs.action_log] == ["sim_ahead"]


def test_advance_until_respects_roster_guard(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=11, user_team_id=UID)
    team = gs.teams[UID]
    team.player_ids = team.player_ids[:4]
    weeks, reason = sim_ahead.advance_until(
        gs, game_data, team_id=UID, max_weeks=2, triggers=()
    )
    assert (weeks, reason) == (0, "roster_short")


def test_advance_until_runs_to_cap_without_triggers(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=11, user_team_id=UID)
    start = gs.week
    weeks, _reason = sim_ahead.advance_until(
        gs, game_data, team_id=UID, max_weeks=2, triggers=()
    )
    assert weeks == 2
    assert gs.week == start + 2


def test_advance_until_is_deterministic(game_data: GameData) -> None:
    """Two same-seed runs of the same batch produce byte-identical
    GameState (including the action log the batch itself writes)."""
    runs = []
    for _ in range(2):
        gs = new_campaign(game_data, seed=77, user_team_id=UID)
        weeks, reason = sim_ahead.advance_until(
            gs, game_data, team_id=UID, max_weeks=2
        )
        runs.append((weeks, reason, gs.model_dump_json()))
    assert runs[0][:2] == runs[1][:2]
    assert runs[0][2] == runs[1][2]


# -- the endpoint ----------------------------------------------------------------


def test_sim_ahead_endpoint(game_data: GameData, tmp_path, monkeypatch) -> None:
    fastapi = pytest.importorskip("fastapi")
    import esports_sim.web.server as server_mod
    from esports_sim.web import review_history

    gs = new_campaign(game_data, seed=101, user_team_id=UID)
    start_week = gs.week
    gs.autosave_enabled = False  # keep the test off the real saves/ dir
    game = server_mod._Game(game_data, "SIMAH", gs=gs)
    token = server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(server_mod.llm_social, "enqueue", lambda *_a, **_k: None)
    try:
        res = server_mod.sim_ahead_action(server_mod.SimAheadBody(max_weeks=2))
        assert set(res) == {
            "advanced", "weeks", "stop_reason", "stop_label", "report",
        }
        # A fresh week-1 campaign has nothing pending, so at least one week
        # ticks; a trigger may legitimately stop the second.
        assert 1 <= res["weeks"] <= 2
        assert res["advanced"] is True
        assert res["report"] is not None
        assert "week_reveal" in res["report"]  # feeds the staged reveal
        # The response report is the LAST advanced week's.
        assert res["report"]["week"] == start_week + res["weeks"] - 1
        if res["stop_reason"] is None:
            assert res["stop_label"] is None
        else:
            assert res["stop_label"] == sim_ahead.label_for(res["stop_reason"])

        kinds = [a.kind for a in gs.action_log]
        assert kinds[0] == "sim_ahead"
        assert kinds.count("advance") == res["weeks"]

        # Shared worlds advance by ready-up: the endpoint refuses outright.
        rival = sorted(t for t in gs.teams if t != UID)[0]
        gs.human_team_ids = [UID, rival]
        with pytest.raises(fastapi.HTTPException) as exc:
            server_mod.sim_ahead_action(server_mod.SimAheadBody(max_weeks=2))
        assert exc.value.status_code == 409
        gs.human_team_ids = [UID]

        # The manual advance's roster-size guard is preserved per press.
        team = gs.teams[UID]
        kept = list(team.player_ids)
        team.player_ids = kept[:4]
        with pytest.raises(fastapi.HTTPException) as exc:
            server_mod.sim_ahead_action(server_mod.SimAheadBody(max_weeks=2))
        assert exc.value.status_code == 409
        team.player_ids = kept
    finally:
        server_mod._ctx.reset(token)
