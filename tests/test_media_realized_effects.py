"""MEDIA feedback measures only the mutations it describes, including caps."""
import json

import pytest

from esports_sim.manager import media_events, new_campaign
from esports_sim.manager.campaign import WeekReport
from esports_sim.manager.state import GameState, MediaChoice, MediaEvent, SponsorDeal, SCHEMA_VERSION
import esports_sim.web.server as server_mod


@pytest.fixture
def campaign(game_data):
    return new_campaign(game_data, seed=2038)


def queue(gs, kind="derby_expectations", choice="respect_rival", player=""):
    tid = gs.user_team_id
    fixture = gs.team_fixture(tid)
    gs.media_events_by[tid] = MediaEvent(
        id="measured-media", season=gs.season, week=gs.week, team_id=tid,
        type_id=kind, title="Press", prompt="Choose", player_id=player,
        fixture_id=fixture.id if kind == "derby_expectations" else "",
        choices=[MediaChoice(id=choice, label=choice, impact="")],
    )
    return tid, fixture


def settle(gs, fixture, won=False):
    fixture.played = True
    fixture.winner_id = gs.user_team_id if won else fixture.team_b if fixture.team_a == gs.user_team_id else fixture.team_a
    media_events.settle_commitments(gs, WeekReport(
        season=gs.season, week=gs.week, phase=gs.phase, fixtures=[fixture]))


def test_immediate_clamps_and_deduplicates_sponsor_targets(campaign):
    tid = campaign.user_team_id
    pid = sorted(campaign.teams[tid].player_ids)[0]
    queue(campaign, "defend_player", "defend_publicly", pid)
    campaign.team_sentiment[tid] = 99.5
    campaign.manager_player_trust_by[tid] = {pid: 98.0}
    deal = SponsorDeal(name="Signal", kind="steady", weekly=4000, weeks_left=20)
    campaign.sponsor_slots_by[tid] = {"jersey": deal, "stream": deal}
    campaign.sponsor_by[tid] = deal
    campaign.sponsor_relations_by[tid] = {"Signal": 0.5}
    ok, message, _ = media_events.resolve(campaign, tid, "defend_publicly")
    assert ok
    effect = campaign.media_history_by[tid][-1].immediate_effects
    assert (effect.sentiment.before, effect.sentiment.after, effect.sentiment.delta) == (99.5, 100, 0.5)
    assert [(p.id, p.before, p.after, p.delta) for p in effect.player_trust] == [(pid, 98, 100, 2)]
    assert [(b.id, b.before, b.after, b.delta) for b in effect.sponsor_relations] == [("Signal", 0.5, 0, -0.5)]
    assert "Community sentiment +0.5 (99.5 -> 100)" in message
    assert "Signal -0.5 (0.5 -> 0)" in message


@pytest.mark.parametrize("won,sentiment,trust", [(False, -1, 1), (True, 2, 2)])
def test_derby_separates_phases_and_cumulative_attribution(campaign, won, sentiment, trust):
    tid, fixture = queue(campaign)
    media_events.resolve(campaign, tid, "respect_rival")
    row = campaign.media_history_by[tid][-1]
    original_ids = [p.id for p in row.immediate_effects.player_trust]
    # Other weekly systems may move sentiment between choice and settlement.
    campaign.team_sentiment[tid] = 40
    removed = original_ids[0]
    campaign.teams[tid].player_ids.remove(removed)
    settle(campaign, fixture, won)
    assert row.immediate_effects.sentiment.delta == 1
    assert row.settlement_effects.sentiment.before == 40
    assert row.settlement_effects.sentiment.delta == sentiment
    assert [p.id for p in row.settlement_effects.player_trust] == original_ids[1:]
    assert all(p.delta == trust for p in row.settlement_effects.player_trust)
    assert not row.immediate_effects.sponsor_relations
    text = " ".join(media_events.decision_feedback(row))
    assert f"Community sentiment {1 + sentiment:+g};" in text
    assert f"{campaign.players[removed].handle} +3" in text
    assert "no active sponsor affected" in text
    assert "Includes only this choice and its result settlement" in text
    before = campaign.model_dump_json()
    settle(campaign, fixture, won)
    assert campaign.model_dump_json() == before  # consumed once


def test_zero_missing_target_and_negative_cap(campaign):
    tid, _ = queue(campaign, "roster_rumor", "acknowledge_market", "departed-player")
    campaign.team_sentiment[tid] = 0
    media_events.resolve(campaign, tid, "acknowledge_market")
    effect = campaign.media_history_by[tid][-1].immediate_effects
    assert effect.sentiment.delta == 0
    assert effect.player_trust == []
    assert effect.sponsor_relations == []
    tid, _ = queue(campaign, "roster_rumor", "no_comment", sorted(campaign.teams[tid].player_ids)[0])
    media_events.resolve(campaign, tid, "no_comment")
    assert campaign.media_history_by[tid][-1].immediate_effects.sentiment.delta == 0


@pytest.mark.parametrize("announce", [False, True])
def test_measured_feedback_is_private_to_the_resolving_club(campaign, announce):
    tid, fixture = queue(campaign)
    rival = next(team_id for team_id in campaign.teams if team_id != tid)
    # The active context can belong to another manager during weekly settlement.
    campaign.set_acting(rival)
    public_before = list(campaign.news)
    rival_before = list(campaign.private_news_by.get(rival, []))
    ok, message, _ = media_events.resolve(campaign, tid, "respect_rival", announce=announce)
    assert ok and "Immediate MEDIA effect" in message
    if announce:
        assert "Immediate MEDIA effect" in campaign.private_news_by[tid][-1]
        assert len(campaign.news) == len(public_before) + 1
    else:
        assert campaign.news == public_before
        assert not campaign.private_news_by.get(tid)
    settle(campaign, fixture)
    assert "Result settlement MEDIA effect" in campaign.private_news_by[tid][-1]
    assert all("MEDIA effect" not in line and "Player trust:" not in line
               and "Sponsor relations:" not in line for line in campaign.news)
    assert campaign.private_news_by.get(rival, []) == rival_before
    assert media_events.view(campaign, tid)["history"][-1]["effect_feedback"]
    assert not media_events.view(campaign, rival)["history"]


@pytest.mark.parametrize("base,delta,after,actual", [(99, 3, 100, 1), (1, -3, 0, -1), (50, 0, 50, 0)])
def test_each_target_measures_caps_and_noop(campaign, base, delta, after, actual):
    tid = campaign.user_team_id
    pid = sorted(campaign.teams[tid].player_ids)[0]
    campaign.team_sentiment[tid] = base
    campaign.manager_player_trust_by[tid] = {pid: base}
    campaign.sponsor_slots_by[tid] = {"jersey": SponsorDeal(
        name="Signal", kind="steady", weekly=4000, weeks_left=20)}
    campaign.sponsor_relations_by[tid] = {"Signal": base}
    effects = media_events._apply(campaign, tid, pid, delta, delta, delta)
    for change in [effects.sentiment, *effects.player_trust, *effects.sponsor_relations]:
        assert (change.before, change.after, change.delta) == (base, after, actual)


def test_full_state_is_deterministic_for_both_phases(campaign):
    tid, fixture = queue(campaign)
    twin = campaign.model_copy(deep=True)
    for gs in (campaign, twin):
        media_events.resolve(gs, tid, "respect_rival")
        settle(gs, next(f for f in gs.fixtures if f.id == fixture.id))
    assert campaign.model_dump_json() == twin.model_dump_json()


@pytest.mark.parametrize("initial_trust", [0.0, 50.0])
def test_choice_triggered_culture_trust_is_measured_separately(campaign, initial_trust):
    tid = campaign.user_team_id
    pid = sorted(campaign.teams[tid].player_ids)[0]
    queue(campaign, "roster_rumor", "acknowledge_market", pid)
    campaign.culture_principles[tid] = "player_led"
    campaign.culture_committed_since_by[tid] = 0
    campaign.manager_player_trust_by[tid] = dict.fromkeys(campaign.teams[tid].player_ids, initial_trust)
    twin = campaign.model_copy(deep=True)
    ok, message, _ = media_events.resolve(campaign, tid, "acknowledge_market")
    media_events.resolve(twin, tid, "acknowledge_market")
    assert ok and campaign.model_dump_json() == twin.model_dump_json()
    decision = campaign.media_history_by[tid][-1]
    media_after = {p.id: p.after for p in decision.immediate_effects.player_trust}
    adjustments = {p.id: p for p in decision.culture_trust_effects}
    for player_id in campaign.teams[tid].player_ids:
        before_culture = media_after.get(player_id, initial_trust)
        final = media_events.trust(campaign, tid, player_id)
        if final != before_culture:
            change = adjustments[player_id]
            assert (change.before, change.after, change.delta) == (before_culture, final, round(final-before_culture, 1))
            assert f"{change.before:g} -> {change.after:g}" in message
        else:
            assert player_id not in adjustments
    assert bool(adjustments) == bool(initial_trust)
    assert "Separate culture trust adjustment" in message
    assert all("culture trust adjustment" not in line for line in campaign.news)
    assert any("Separate culture trust adjustment" in line for line in media_events.decision_feedback(decision))
    assert GameState.model_validate_json(campaign.model_dump_json()).media_history_by == campaign.media_history_by
    legacy = decision.model_dump()
    legacy.pop("culture_trust_effects")
    old = type(decision).model_validate(legacy)
    assert "older record" in media_events.culture_trust_feedback(old)


def test_old_record_unknown_immediate_new_settlement_and_roundtrip(campaign, tmp_path):
    tid, fixture = queue(campaign)
    media_events.resolve(campaign, tid, "respect_rival")
    raw = json.loads(campaign.model_dump_json())
    raw["schema_version"] = 36
    raw["media_history_by"][tid][0].pop("immediate_effects")
    raw["media_history_by"][tid][0].pop("settlement_effects")
    path = tmp_path / "old.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = GameState.load(path)
    assert loaded.schema_version == SCHEMA_VERSION
    row = loaded.media_history_by[tid][0]
    assert row.immediate_effects is None
    fixture = next(f for f in loaded.fixtures if f.id == fixture.id)
    settle(loaded, fixture)
    feedback = " ".join(media_events.decision_feedback(row))
    assert "older record" in feedback and "Cumulative MEDIA contribution unavailable" in feedback
    assert row.settlement_effects.sentiment.delta == -1
    loaded.save(path)
    assert GameState.load(path).model_dump_json() == loaded.model_dump_json()
    row.settlement_effects = None
    assert "Result settlement MEDIA effect: measured changes unavailable" in " ".join(media_events.decision_feedback(row))


def test_web_measured_feedback_and_pure_deterministic_view(campaign, game_data):
    tid, fixture = queue(campaign)
    twin = campaign.model_copy(deep=True)
    game = server_mod._Game(game_data, "MEASUREDMEDIA", gs=campaign)
    token = server_mod._ctx.set(server_mod._ReqCtx(game, tid))
    try:
        result = server_mod.resolve_media_event(server_mod.MediaEventChoiceBody(
            event_id="measured-media", choice_id="respect_rival"))
        assert result["realized_effects"]["sentiment"]["delta"] == 1
        assert "Immediate MEDIA effect" in result["message"]
        assert "effect_feedback" in server_mod.club_view()["media"]["history"][-1]
    finally:
        server_mod._ctx.reset(token)
    media_events.resolve(twin, tid, "respect_rival")
    assert campaign.media_history_by == twin.media_history_by
    settle(campaign, fixture)
    settle(twin, next(f for f in twin.fixtures if f.id == fixture.id))
    assert campaign.media_history_by == twin.media_history_by
    before = campaign.model_dump_json()
    assert media_events.view(campaign, tid) == media_events.view(campaign, tid)
    assert campaign.model_dump_json() == before
