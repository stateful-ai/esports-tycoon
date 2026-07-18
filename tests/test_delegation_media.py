"""Staff-policy delegation and durable, contextual media decisions."""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import (
    delegation,
    flavor_events,
    market,
    media_events,
    new_campaign,
    rivalries,
)
from esports_sim.manager.campaign import WeekReport
from esports_sim.manager.decision_env import HeadlessManagerEnv, InvalidManagerAction
from esports_sim.manager.state import GameState, SCHEMA_VERSION, SponsorDeal
from esports_sim.rng.tree import RngTree
import esports_sim.web.server as server_mod


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=7331)


def _policy(**overrides) -> dict:
    values = {
        "auto_training": False,
        "auto_renew_core": True,
        "renewal_salary_min": 800,
        "renewal_salary_max": 20_000,
        "renewal_trigger_weeks": 8,
        "auto_scout": True,
        "scout_region": "pacific",
        "scout_roles": ["initiator"],
        "scout_max_age": 21,
        "alert_level": "tier1_ready",
    }
    values.update(overrides)
    return values


def test_delegated_training_uses_roster_aware_coach_and_manual_is_noop(
    campaign: GameState, monkeypatch,
) -> None:
    tid = campaign.user_team_id
    roster = campaign.roster(tid)
    campaign.training_focus[tid] = "mental"

    def should_not_run(*_args):
        raise AssertionError("manual training must not draw from the coach picker")

    monkeypatch.setattr(delegation.training, "ai_pick_focus", should_not_run)
    assert delegation.pick_training_focus(campaign, tid, roster, object()) == "mental"

    delegation.configure(campaign, tid, _policy(auto_training=True))
    monkeypatch.setattr(
        delegation.training, "ai_pick_focus", lambda players, rng, team: "rest"
    )
    assert delegation.pick_training_focus(campaign, tid, roster, object()) == "rest"
    assert campaign.training_focus[tid] == "rest"


def test_delegated_renewal_uses_real_salary_path_and_preserves_terms(
    campaign: GameState,
) -> None:
    tid = campaign.user_team_id
    pid = sorted(campaign.teams[tid].player_ids)[0]
    for other_id in campaign.teams[tid].player_ids:
        campaign.players[other_id].contract_weeks_left = 40
    player = campaign.players[pid]
    player.contract_weeks_left = 7
    player.no_transfer_clause = True
    player.release_fee = 77_000
    player.roster_role = "starter"
    delegation.configure(campaign, tid, _policy(auto_scout=False))

    delegation.begin_week(campaign)

    assert player.contract_weeks_left == 48
    assert player.no_transfer_clause is True
    assert player.release_fee == 77_000
    report = campaign.delegation_reports_by[tid][-1]
    assert report.renewed_player_ids == [pid]


def test_delegation_reports_out_of_band_contract_instead_of_overriding_it(
    campaign: GameState,
) -> None:
    tid = campaign.user_team_id
    pid = sorted(campaign.teams[tid].player_ids)[0]
    player = campaign.players[pid]
    player.contract_weeks_left = 5
    player.roster_role = "starter"
    delegation.configure(
        campaign, tid, _policy(auto_scout=False, renewal_salary_max=800)
    )

    delegation.begin_week(campaign)

    assert player.contract_weeks_left == 5
    report = campaign.delegation_reports_by[tid][-1]
    assert report.renewed_player_ids == []
    assert report.exceptions and "outside" in report.exceptions[0]


def test_scout_policy_rotates_existing_desk_and_only_alerts_at_threshold(
    campaign: GameState,
) -> None:
    tid = campaign.user_team_id
    delegation.configure(campaign, tid, _policy(auto_renew_core=False))

    delegation.begin_week(campaign)
    # The department's recruit deep-dive now rides the standing AMATEUR lane
    # (scout_lanes_by) instead of clobbering the single scout_targets slot the
    # RL/decision-env path still owns.
    assigned = campaign.scout_lanes_by[tid]["amateur"]
    assert assigned.startswith("player:")
    candidate = campaign.players[assigned.removeprefix("player:")]
    assert candidate.age <= 21
    assert str(candidate.role) == "initiator"
    assert delegation._player_region(campaign, candidate.id) == "pacific"
    for attr in candidate.attributes:
        candidate.attributes[attr] = 90.0
    campaign.scout_progress_by.setdefault(tid, {})[f"player:{candidate.id}"] = 0.50
    delegation.finalize_week(campaign)

    report = campaign.delegation_reports_by[tid][-1]
    assert len(report.alerts) == 1
    assert "tier1 ready" in report.alerts[0]
    delegation.finalize_week(campaign)
    assert len(report.alerts) == 1


def _only_struggling_player(campaign: GameState) -> str:
    tid = campaign.user_team_id
    roster = [campaign.players[pid] for pid in campaign.teams[tid].player_ids]
    for player in roster:
        player.age = 24
        player.form = player.confidence = player.morale = 70.0
    roster[0].form = 30.0
    return roster[0].id


def test_media_defence_changes_trust_sentiment_sponsor_and_history(
    campaign: GameState,
) -> None:
    tid = campaign.user_team_id
    pid = _only_struggling_player(campaign)
    campaign.sponsor_slots_by.setdefault(tid, {})["jersey"] = SponsorDeal(
        name="Signal", kind="steady", weekly=4_000, weeks_left=20
    )
    campaign.sponsor_relations_by.setdefault(tid, {})["Signal"] = 50.0
    event = media_events._build_event(
        campaign, tid, RngTree(campaign.seed).derive("test", "media")
    )
    assert event is not None and event.type_id == "defend_player"
    campaign.media_events_by[tid] = event
    salary_before = market.renewal_salary(campaign, tid, pid)

    ok, _message, effects = media_events.resolve(
        campaign, tid, "defend_publicly"
    )

    assert ok
    assert effects == {"sentiment": 3, "sponsor_relation": -2, "trust": 8}
    assert media_events.trust(campaign, tid, pid) == 58.0
    assert campaign.sentiment(tid) == 53.0
    assert campaign.sponsor_relations_by[tid]["Signal"] == 48.0
    assert market.renewal_salary(campaign, tid, pid) <= salary_before
    assert campaign.media_history_by[tid][-1].choice_id == "defend_publicly"
    assert any(e.kind == "media" and e.player_id == pid for e in campaign.chronicle)


def test_derby_expectation_settles_from_result_not_a_random_outcome(
    campaign: GameState,
) -> None:
    tid = campaign.user_team_id
    for pid in campaign.teams[tid].player_ids:
        p = campaign.players[pid]
        p.age = 24
        p.form = p.confidence = p.morale = 70.0
    fixture = campaign.team_fixture(tid)
    assert fixture is not None
    opponent = fixture.team_b if fixture.team_a == tid else fixture.team_a
    campaign.rivalries[rivalries.key(tid, opponent)] = 30.0
    event = media_events._build_event(
        campaign, tid, RngTree(campaign.seed).derive("test", "derby")
    )
    assert event is not None and event.type_id == "derby_expectations"
    campaign.media_events_by[tid] = event
    ok, _, _ = media_events.resolve(campaign, tid, "set_high_bar")
    assert ok and tid in campaign.media_commitments_by
    before = campaign.sentiment(tid)
    fixture.played = True
    fixture.winner_id = tid

    media_events.settle_commitments(
        campaign,
        WeekReport(
            season=campaign.season,
            week=campaign.week,
            phase=campaign.phase,
            fixtures=[fixture],
        ),
    )

    assert tid not in campaign.media_commitments_by
    assert campaign.sentiment(tid) == before + 5.0
    assert "won" in campaign.media_history_by[tid][-1].settlement


def test_pending_media_blocks_headless_advance_and_resolves(campaign, game_data) -> None:
    tid = campaign.user_team_id
    _only_struggling_player(campaign)
    event = media_events._build_event(
        campaign, tid, RngTree(campaign.seed).derive("test", "headless")
    )
    assert event is not None
    campaign.media_events_by[tid] = event
    campaign.flavor_events_by.pop(tid, None)
    env = HeadlessManagerEnv(campaign, game_data)
    legal = env.observe()["legal_actions"]
    assert legal["advance"]["enabled"] is False
    assert legal["resolve_media"]["enabled"] is True
    with pytest.raises(InvalidManagerAction, match="media"):
        env.step({"kind": "advance", "params": {}})
    result = env.step({
        "kind": "resolve_media",
        "params": {"event_id": event.id, "choice_id": event.choices[0].id},
    })
    assert not result.advanced
    assert tid not in campaign.media_events_by


def test_media_queue_never_stacks_and_respects_six_week_cooldown(
    campaign: GameState, monkeypatch
) -> None:
    tid = campaign.user_team_id
    _only_struggling_player(campaign)
    campaign.flavor_events_by[tid] = flavor_events._build_event(
        campaign, tid, RngTree(campaign.seed).derive("test", "flavor-block")
    )
    monkeypatch.setattr(media_events, "WEEKLY_CHANCE", 1.0)
    media_events.queue_weekly_events(campaign)
    assert tid not in campaign.media_events_by

    campaign.flavor_events_by.pop(tid)
    media_events.queue_weekly_events(campaign)
    assert tid in campaign.media_events_by
    first_stamp = campaign.media_last_week_by[tid]
    campaign.media_events_by.pop(tid)
    campaign.week += media_events.COOLDOWN_WEEKS - 1
    media_events.queue_weekly_events(campaign)
    assert tid not in campaign.media_events_by
    assert campaign.media_last_week_by[tid] == first_stamp


def test_v22_migration_and_round_trip(campaign: GameState, tmp_path) -> None:
    delegation.configure(campaign, campaign.user_team_id, _policy())
    path = tmp_path / "current.json"
    campaign.save(path)
    loaded = GameState.load(path)
    assert loaded.delegation_policies_by == campaign.delegation_policies_by

    old = json.loads(campaign.model_dump_json())
    old["schema_version"] = 22
    for field in (
        "delegation_policies_by",
        "delegation_reports_by",
        "delegation_alerted_players_by",
        "media_events_by",
        "media_commitments_by",
        "media_history_by",
        "media_last_week_by",
        "manager_player_trust_by",
    ):
        old.pop(field)
    old_path = tmp_path / "v22.json"
    old_path.write_text(json.dumps(old), encoding="utf-8")
    migrated = GameState.load(old_path)
    assert migrated.schema_version == SCHEMA_VERSION
    assert migrated.delegation_policies_by == {}
    assert migrated.media_history_by == {}


def test_web_contract_exposes_policy_and_resolves_media(campaign, game_data) -> None:
    tid = campaign.user_team_id
    game = server_mod._Game(game_data, "DELEGATEMEDIA", gs=campaign)
    server_mod._ctx.set(server_mod._ReqCtx(game, tid))
    configured = server_mod.delegation_policy_action(
        server_mod.DelegationPolicyBody(**_policy())
    )
    assert configured["ok"] is True
    club = server_mod.club_view()
    assert club["delegation"]["policy"]["alert_level"] == "tier1_ready"
    assert "player_trust" in club["media"]
    training_result = server_mod.set_training(
        server_mod.TrainingBody(delegate_to_coach=True)
    )
    assert training_result["delegate_to_coach"] is True
    assert server_mod.state()["training_delegated"] is True

    _only_struggling_player(campaign)
    event = media_events._build_event(
        campaign, tid, RngTree(campaign.seed).derive("test", "web-media")
    )
    assert event is not None
    campaign.flavor_events_by.pop(tid, None)
    campaign.media_events_by[tid] = event
    wire = server_mod.state()["media_event"]
    assert wire["id"] == event.id
    assert all("impact" in choice for choice in wire["choices"])
    result = server_mod.resolve_media_event(server_mod.MediaEventChoiceBody(
        event_id=event.id, choice_id=event.choices[0].id,
    ))
    assert result["ok"] is True
    assert server_mod.state()["media_event"] is None
