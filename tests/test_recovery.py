"""Paid recovery, and the way out of the condition death-spiral.

Three synthetic players independently drove a five-man roster to condition
zero and reported it as a dead end. Rest already existed in `training.py`
(+18 condition for a team rest week or a per-player `dev_focus="rest"`), but
it lived on a different sub-tab from the screen showing the problem, and
nothing warned them. `manager/recovery.py` adds the other currency: spend
money instead of a week of development.

These tests pin both halves — that resting recovers, that buying recovers,
and that neither can be used to print condition for free.
"""

from __future__ import annotations

import pytest

from esports_sim.manager import advance_week, new_campaign, recovery, training
from esports_sim.registry import GameData

TEAM = "team_nexus"


def _wrecked(game_data: GameData, seed: int = 2026, condition: float = 8.0):
    """A campaign whose user squad is in the state the playtesters reached."""
    gs = new_campaign(game_data, seed=seed, user_team_id=TEAM)
    for player in gs.roster(TEAM):
        player.stamina = condition
    return gs


# ── the free way out: rest ──────────────────────────────────────────────


@pytest.mark.campaign
def test_a_team_rest_week_recovers_condition(game_data: GameData) -> None:
    gs = _wrecked(game_data)
    gs.training_focus[TEAM] = "rest"
    before = recovery.average_condition(gs, TEAM)
    advance_week(gs, game_data)
    assert recovery.average_condition(gs, TEAM) > before


@pytest.mark.campaign
def test_one_player_can_rest_while_the_squad_trains(game_data: GameData) -> None:
    """The per-player lever: nurse one starter without shelving practice."""
    gs = _wrecked(game_data, condition=20.0)
    gs.training_focus[TEAM] = "mechanical"
    roster = sorted(gs.roster(TEAM), key=lambda p: p.id)
    rester, worker = roster[0], roster[1]
    rester.dev_focus = "rest"
    worker.dev_focus = "auto"
    before_rester, before_worker = rester.stamina, worker.stamina

    advance_week(gs, game_data)

    assert rester.stamina > before_rester, "a resting player must recover"
    assert worker.stamina < before_worker, "a training player must still drain"


@pytest.mark.campaign
def test_rest_is_a_real_option_at_both_levels() -> None:
    """The UI offers what the campaign accepts — no dead dropdown entries."""
    assert "rest" in training.FOCUS_OPTIONS
    assert "rest" in training.DEV_FOCUS_OPTIONS


# ── the paid way out ────────────────────────────────────────────────────


@pytest.mark.campaign
def test_booking_recovery_restores_the_squad_and_charges_for_it(
    game_data: GameData,
) -> None:
    gs = _wrecked(game_data)
    balance = gs.teams[TEAM].balance
    cost = recovery.tier_cost(gs, TEAM, "retreat")
    before = recovery.average_condition(gs, TEAM)

    ok, message = recovery.book(gs, TEAM, "retreat")

    assert ok, message
    assert gs.teams[TEAM].balance == balance - cost
    assert recovery.average_condition(gs, TEAM) > before
    assert all(p.stamina <= 100.0 for p in gs.roster(TEAM))


@pytest.mark.campaign
def test_the_expensive_tier_recovers_more_than_the_cheap_one(
    game_data: GameData,
) -> None:
    """Otherwise the price is a lie and there is no decision to make."""
    gains = {}
    for tier in recovery.TIER_IDS:
        gs = _wrecked(game_data)
        before = recovery.average_condition(gs, TEAM)
        assert recovery.book(gs, TEAM, tier)[0]
        gains[tier] = recovery.average_condition(gs, TEAM) - before
    assert gains["retreat"] > gains["day"]
    gs = _wrecked(game_data)
    assert recovery.tier_cost(gs, TEAM, "retreat") > recovery.tier_cost(gs, TEAM, "day")


@pytest.mark.campaign
def test_cost_scales_with_squad_size(game_data: GameData) -> None:
    """A ten-man roster costs more to look after than a five-man one."""
    gs = _wrecked(game_data)
    five = recovery.tier_cost(gs, TEAM, "day")
    extra = next(
        pid for pid in gs.free_agent_ids if pid not in gs.teams[TEAM].player_ids
    )
    gs.teams[TEAM].player_ids.append(extra)
    assert recovery.tier_cost(gs, TEAM, "day") > five


@pytest.mark.campaign
def test_only_one_booking_per_week(game_data: GameData) -> None:
    gs = _wrecked(game_data)
    assert recovery.book(gs, TEAM, "day")[0]
    ok, message = recovery.book(gs, TEAM, "day")
    assert not ok
    assert "already booked" in message
    # ...and the week rolling over frees it again.
    gs.week += 1
    assert recovery.can_book(gs, TEAM, "day")[0]


@pytest.mark.campaign
def test_same_week_in_next_season_allows_recovery(game_data: GameData) -> None:
    gs = _wrecked(game_data)
    assert recovery.book(gs, TEAM, "day")[0]
    gs.season += 1
    assert recovery.can_book(gs, TEAM, "day")[0]
    assert recovery.book(gs, TEAM, "day")[0]
    assert not recovery.can_book(gs, TEAM, "retreat")[0]


@pytest.mark.campaign
def test_legacy_recovery_booking_preserves_current_season_lock(
    game_data: GameData, tmp_path,
) -> None:
    import json

    from esports_sim.manager.state import GameState, MediaDecision

    gs = _wrecked(game_data)
    assert recovery.book(gs, TEAM, "day")[0]
    gs.media_history_by[TEAM] = [MediaDecision(
        event_id="legacy-media", season=gs.season, week=gs.week,
        team_id=TEAM, type_id="sponsor_duty", choice_id="attend",
        summary="Legacy media choice", sentiment_delta=2.0,
    )]
    old = gs.model_dump(mode="json")
    old["schema_version"] = 36
    old.pop("recovery_booked_season_by")
    old.pop("map_meta_stats_by_tier")
    for decision in old["media_history_by"][TEAM]:
        for field in ("immediate_effects", "settlement_effects", "culture_trust_effects"):
            decision.pop(field)
    save = tmp_path / "legacy-recovery.json"
    save.write_text(json.dumps(old), encoding="utf-8")
    loaded = GameState.load(save)
    assert recovery.already_booked(loaded, TEAM)
    assert loaded.map_meta_stats_by_tier == {}
    decision = loaded.media_history_by[TEAM][0]
    assert decision.immediate_effects is None
    assert decision.settlement_effects is None
    assert decision.culture_trust_effects is None
    assert decision.sentiment_delta == 2.0
    loaded.season += 1
    assert not recovery.already_booked(loaded, TEAM)


def _load_legacy_recovery(gs, tmp_path):
    import json

    from esports_sim.manager.state import GameState

    old = gs.model_dump(mode="json")
    old["schema_version"] = 37
    old.pop("recovery_booked_season_by")
    save = tmp_path / "legacy-recovery.json"
    save.write_text(json.dumps(old), encoding="utf-8")
    return GameState.load(save)


@pytest.mark.campaign
@pytest.mark.parametrize("evidence", ["news", "recovery", "book_recovery"])
def test_later_season_legacy_current_booking_retains_lock(
    game_data: GameData, tmp_path, evidence: str,
) -> None:
    from esports_sim.manager import telemetry

    gs = _wrecked(game_data)
    gs.season, gs.week = 2, 3
    assert recovery.book(gs, TEAM, "day")[0]
    if evidence != "news":
        telemetry.record_action(gs, evidence, {"tier": "day"}, team_id=TEAM)
        gs.news.clear()
    loaded = _load_legacy_recovery(gs, tmp_path)
    assert loaded.recovery_booked_season_by[TEAM] == 2
    assert not recovery.can_book(loaded, TEAM, "retreat")[0]
    assert loaded.teams[TEAM].balance == gs.teams[TEAM].balance


@pytest.mark.campaign
@pytest.mark.parametrize("keep_evidence", [True, False])
def test_legacy_previous_season_same_week_does_not_block(
    game_data: GameData, tmp_path, keep_evidence: bool,
) -> None:
    from esports_sim.manager import telemetry
    from esports_sim.manager.state import GameState

    gs = _wrecked(game_data)
    gs.week = 3
    assert recovery.book(gs, TEAM, "day")[0]
    telemetry.record_action(gs, "recovery", {"tier": "day"}, team_id=TEAM)
    gs.season = 2
    if not keep_evidence:
        gs.action_log.clear()
        gs.news.clear()
    loaded = _load_legacy_recovery(gs, tmp_path)
    assert loaded.recovery_booked_by[TEAM] == 3
    assert TEAM not in loaded.recovery_booked_season_by
    assert recovery.can_book(loaded, TEAM, "day")[0]
    save = tmp_path / "roundtrip.json"
    loaded.save(save)
    reloaded = GameState.load(save)
    assert reloaded.model_dump_json() == loaded.model_dump_json()
    assert recovery.book(reloaded, TEAM, "day")[0]
    assert reloaded.recovery_booked_season_by[TEAM] == 2
    assert not recovery.can_book(reloaded, TEAM, "retreat")[0]
    reloaded.save(save)
    assert recovery.already_booked(GameState.load(save), TEAM)


@pytest.mark.campaign
def test_legacy_evidence_is_club_specific_for_multiple_humans_and_ai(
    game_data: GameData, tmp_path,
) -> None:
    from esports_sim.manager import telemetry

    gs = _wrecked(game_data)
    other, ai = [tid for tid in sorted(gs.teams) if tid != TEAM][:2]
    gs.human_team_ids = [TEAM, other]
    gs.season, gs.week = 2, 3
    for tid in (TEAM, other, ai):
        assert recovery.book(gs, tid, "day")[0]
    # Only the first human has accepted current-season action evidence.
    telemetry.record_action(gs, "recovery", {"tier": "day"}, team_id=TEAM)
    # AI is not in the human log, but its deterministic news proves booking.
    gs.news = [line for line in gs.news if gs.teams[ai].name in line]
    loaded = _load_legacy_recovery(gs, tmp_path)
    assert recovery.already_booked(loaded, TEAM)
    assert recovery.already_booked(loaded, ai)
    assert not recovery.already_booked(loaded, other)


@pytest.mark.campaign
def test_legacy_first_season_lock_needs_no_retained_evidence(
    game_data: GameData, tmp_path,
) -> None:
    gs = _wrecked(game_data)
    assert recovery.book(gs, TEAM, "day")[0]
    gs.news.clear()
    loaded = _load_legacy_recovery(gs, tmp_path)
    assert recovery.already_booked(loaded, TEAM)


@pytest.mark.campaign
def test_legacy_news_requires_unique_club_name_and_exact_booking_sentence(
    game_data: GameData, tmp_path,
) -> None:
    gs = _wrecked(game_data)
    gs.season, gs.week = 2, 3
    assert recovery.book(gs, TEAM, "day")[0]
    other = next(tid for tid in sorted(gs.teams) if tid != TEAM)
    gs.teams[other].name = gs.teams[TEAM].name
    assert not recovery.already_booked(_load_legacy_recovery(gs, tmp_path), TEAM)
    gs.teams[other].name = "Distinct club"
    gs.news = [f"[S2 W3] {gs.teams[TEAM].name} consider a recovery day."]
    assert not recovery.already_booked(_load_legacy_recovery(gs, tmp_path), TEAM)


@pytest.mark.campaign
@pytest.mark.parametrize("kind,week", [("recovery", 2), ("advance", 3)])
def test_legacy_unrelated_action_does_not_qualify_booking(
    game_data: GameData, tmp_path, kind: str, week: int,
) -> None:
    from esports_sim.manager import telemetry

    gs = _wrecked(game_data)
    gs.season, gs.week = 2, week
    telemetry.record_action(gs, kind, team_id=TEAM)
    gs.week = 3
    gs.recovery_booked_by[TEAM] = 3
    gs.news.clear()
    assert not recovery.already_booked(_load_legacy_recovery(gs, tmp_path), TEAM)


@pytest.mark.campaign
def test_explicit_booking_season_survives_migration(game_data: GameData) -> None:
    from esports_sim.manager.state import _migrate_v37_to_v38

    gs = _wrecked(game_data)
    gs.season, gs.week = 2, 3
    assert recovery.book(gs, TEAM, "day")[0]
    data = gs.model_dump(mode="json")
    data["recovery_booked_season_by"][TEAM] = 1
    migrated = _migrate_v37_to_v38(data)
    assert migrated["recovery_booked_season_by"][TEAM] == 1


@pytest.mark.campaign
def test_a_club_that_cannot_pay_is_refused_with_the_shortfall(
    game_data: GameData,
) -> None:
    gs = _wrecked(game_data)
    gs.teams[TEAM].balance = 10
    ok, message = recovery.book(gs, TEAM, "retreat")
    assert not ok
    assert "short" in message
    assert recovery.average_condition(gs, TEAM) == 8.0, "a refusal must not heal"


@pytest.mark.campaign
def test_an_unknown_tier_is_refused(game_data: GameData) -> None:
    gs = _wrecked(game_data)
    ok, _ = recovery.book(gs, TEAM, "spa-weekend-in-ibiza")
    assert not ok


# ── the warning that was missing ────────────────────────────────────────


@pytest.mark.campaign
def test_a_tired_squad_is_flagged(game_data: GameData) -> None:
    gs = _wrecked(game_data)
    assert recovery.squad_needs_a_break(gs, TEAM)


@pytest.mark.campaign
def test_a_fresh_squad_is_not_flagged(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
    for player in gs.roster(TEAM):
        player.stamina = 95.0
    assert not recovery.squad_needs_a_break(gs, TEAM)


@pytest.mark.campaign
def test_two_wrecked_starters_flag_even_when_the_average_looks_fine(
    game_data: GameData,
) -> None:
    """The exact shape a playtester hit: 14 / 0 / 14 / 0 / 13 on five players.

    An average-only check can sit above the threshold while two starters are
    unusable, which is why `squad_needs_a_break` also looks at the worst case.
    """
    gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
    roster = sorted(gs.roster(TEAM), key=lambda p: p.id)
    for player in roster:
        player.stamina = 100.0
    roster[0].stamina = 0.0
    roster[1].stamina = 0.0
    assert recovery.average_condition(gs, TEAM) > recovery.TIRED_THRESHOLD
    assert recovery.squad_needs_a_break(gs, TEAM), (
        "two starters at zero must raise the flag even on a healthy average"
    )


# ── invariants ──────────────────────────────────────────────────────────


@pytest.mark.campaign
def test_ai_clubs_use_the_lever_too(game_data: GameData) -> None:
    """An unanswered player-only lever is a difficulty leak."""
    gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
    for _ in range(6):
        advance_week(gs, game_data)
    ai_bookings = [tid for tid in gs.recovery_booked_by if not gs.is_human(tid)]
    assert ai_bookings, "no AI club ever booked recovery over six weeks"


@pytest.mark.campaign
def test_ai_never_books_the_expensive_tier(game_data: GameData) -> None:
    """Documented restraint: the retreat is a human judgement call.

    An AI spending five times as much every time it dipped would quietly drain
    the league's transfer money.
    """
    gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
    tid = next(t for t in sorted(gs.teams) if not gs.is_human(t))
    for player in gs.roster(tid):
        player.stamina = 5.0
    gs.teams[tid].balance = 10_000_000
    before = gs.teams[tid].balance
    recovery.ai_weekly_booking(gs)
    spent = before - gs.teams[tid].balance
    assert spent == recovery.tier_cost(gs, tid, "day"), (
        f"AI spent {spent}, expected the cheap tier only"
    )


@pytest.mark.campaign
@pytest.mark.slow
def test_recovery_keeps_the_campaign_deterministic(game_data: GameData) -> None:
    """Same seed, byte-identical GameState — invariant 1, with a new tick phase."""
    def run() -> str:
        gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
        for _ in range(6):
            advance_week(gs, game_data)
        return gs.model_dump_json()

    assert run() == run()


@pytest.mark.campaign
def test_booking_never_pushes_a_player_over_full_condition(
    game_data: GameData,
) -> None:
    gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
    for player in gs.roster(TEAM):
        player.stamina = 99.0
    assert recovery.book(gs, TEAM, "retreat")[0]
    assert all(p.stamina == 100.0 for p in gs.roster(TEAM))
    assert all(p.morale <= 100.0 for p in gs.roster(TEAM))

@pytest.mark.campaign
def test_the_exhaustion_threshold_matches_the_training_systems(
    game_data: GameData,
) -> None:
    """One threshold, not two.

    A playtester found the dashboard reporting zero exhausted players while a
    player carried the training system's TOO EXHAUSTED TO TRAIN badge: this
    module hardcoded 25 while training flagged at 35. A player between the two
    was exhausted by one system and invisible to the other.
    """
    assert recovery.EXHAUSTED_STAMINA == training.EXHAUSTED_STAMINA


@pytest.mark.campaign
def test_a_player_too_exhausted_to_train_raises_the_break_flag(
    game_data: GameData,
) -> None:
    """The gap case: one player below the training threshold, squad fine."""
    gs = new_campaign(game_data, seed=2026, user_team_id=TEAM)
    for player in gs.roster(TEAM):
        player.stamina = 100.0
    # Squarely between the old hardcoded 25 and the real 35.
    sorted(gs.roster(TEAM), key=lambda p: p.id)[0].stamina = 30.0
    assert recovery.squad_needs_a_break(gs, TEAM), (
        "a player the training system calls too exhausted to train must count"
    )

