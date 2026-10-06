"""Counterfactual careers: decisions and match evidence must change outcomes."""

from __future__ import annotations

import json

import numpy as np
import pytest

from esports_sim.manager import development, development_path as path, training
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState, SCHEMA_VERSION
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import Player, Team
from esports_sim.schemas.player import DevelopmentCurveModel
from esports_sim.sim.stats import PlayerLine

ATTRS = sorted({a for group in training._CATEGORY_ATTRS.values() for a in group})


def player(pid="prospect", ca=55, pa=88):
    return Player(
        id=pid, handle=pid, age=19, role="duelist", playstyle="entry",
        attributes={a: float(ca) for a in ATTRS}, potential=pa,
        career_volatility=0,
        development_curve=DevelopmentCurveModel(
            archetype="steady", growth_peak_age=21, growth_width=4,
            peak_years=5, decline_age=30, realization=1, volatility=1,
        ),
    )


def state(p):
    return GameState(seed=3, season=1, week=1, user_team_id="t",
                     teams={"t": Team(id="t", name="Team", tag="T", player_ids=[p.id])},
                     players={p.id: p})


def good_line(p):
    return PlayerLine(player_id=p.id, kills=24, deaths=10, assists=7,
                      first_kills=5, trade_kills=4, headshots=12,
                      survived=12, clutch_1v2=1)


def bad_line(p):
    return PlayerLine(player_id=p.id, kills=4, deaths=22, assists=1,
                      survived=1, first_deaths=12)


def play_week(gs, line, focus="mechanical", seed=10):
    p = next(iter(gs.players.values()))
    path.begin_week(gs)
    training.apply_match_experience(p, line, 24, support_bonus=0, opponent_quality=60)
    path.update_trends(gs)
    training.apply_training(gs.teams["t"], [p], focus, RngTree(seed).derive(gs.week))
    gs.week += 1


def test_performances_change_subsequent_practice_not_just_match_xp():
    strong, poor = state(player()), state(player())
    for _ in range(6):
        play_week(strong, good_line(strong.players["prospect"]))
        play_week(poor, bad_line(poor.players["prospect"]))
    # Normalize current skills/condition so only the earned trend differs.
    for gs in (strong, poor):
        gs.players["prospect"].attributes = {a: 55.0 for a in ATTRS}
        gs.players["prospect"].stamina = 90
        path.begin_week(gs)
        training.apply_training(gs.teams["t"], list(gs.players.values()), "mechanical",
                                RngTree(1).derive("same-practice"))
    good_gain = sum(strong.players["prospect"].development_progress.latest.practice_gains.values())
    bad_gain = sum(poor.players["prospect"].development_progress.latest.practice_gains.values())
    assert good_gain > bad_gain * 1.4 > 0


def test_focus_reinforces_match_skills_and_changes_which_attributes_grow():
    gs = state(player())
    play_week(gs, good_line(gs.players["prospect"]))
    report = path.report_view(gs.players["prospect"])
    practice = report["sources"]["practice_gains"]["skills"]
    assert set(practice) == set(training._CATEGORY_ATTRS["mechanical"])
    assert any("reinforces" in text for text in report["factors"])
    assert report["sources"]["match_gains"]["overall_gain"] > 0
    # Compare the same drill with/without relevant in-match experience.
    matched, unrelated = player(), player()
    ga, gb = state(matched), state(unrelated)
    path.begin_week(ga)
    path.begin_week(gb)
    matched.development_progress.latest.match_gains = {"aim_precision": 0.1}
    unrelated.development_progress.latest.match_gains = {"utility_usage": 0.1}
    for game in (ga, gb):
        training.apply_training(game.teams["t"], list(game.players.values()), "mechanical",
                                RngTree(11).derive("same"))
    assert sum(matched.attributes.values()) > sum(unrelated.attributes.values())


def test_teamwork_in_matches_reinforces_communication_training():
    gs = state(player())
    play_week(gs, good_line(gs.players["prospect"]), focus="team")
    report = path.report_view(gs.players["prospect"])
    assert report["sources"]["match_gains"]["skills"]["comms_quality"] > 0
    assert any("reinforces" in text for text in report["factors"])


def test_support_performance_and_opponent_strength_are_credited():
    p = player()
    support = PlayerLine(player_id=p.id, kills=8, deaths=12, assists=15,
                         plants=5, defuses=2, trade_kills=3, survived=12)
    assert path.performance_score(p, support, 24, 60) > 0.2
    assert path.performance_score(p, support, 24, 80) > path.performance_score(p, support, 24, 40)
    # Doubling every counter and the round count leaves performance unchanged.
    twice = PlayerLine(player_id=p.id, **{
        key: getattr(support, key) * 2
        for key in ("kills", "deaths", "assists", "plants", "defuses", "trade_kills", "survived")
    })
    assert path.performance_score(p, twice, 48, 60) == pytest.approx(path.performance_score(p, support, 24, 60))


def test_feeding_first_deaths_is_not_a_development_strategy():
    p = player()
    before = dict(p.attributes)
    line = PlayerLine(player_id=p.id, deaths=24, first_deaths=24)
    training.apply_match_experience(p, line, 24)
    assert p.attr("positioning") == before["positioning"]
    assert path.performance_score(p, line, 24, 60) < -0.9


def test_bye_week_decays_trend_without_inventing_evidence():
    gs = state(player())
    p = gs.players["prospect"]
    p.development_progress.momentum = 0.5
    path.begin_week(gs)
    path.update_trends(gs)
    assert p.development_progress.momentum == 0.45
    assert p.development_progress.performance_weeks == 0
    assert not path.career_turning_points(gs, RngTree(1))
    assert path.report_view(p)["maps"] == 0


def test_fatigue_makes_intense_training_a_contextual_choice():
    fresh, tired = player(), player()
    fresh.stamina, tired.stamina = 95, 30
    fresh.training_intensity = "normal"
    tired.training_intensity = "intense"
    for p in (fresh, tired):
        gs = state(p)
        path.begin_week(gs)
        training.apply_training(gs.teams["t"], [p], "mechanical", np.random.default_rng(2))
    assert sum(fresh.attributes.values()) > sum(tired.attributes.values())
    assert any("Tired" in text for text in path.report_view(tired)["factors"])


def test_rest_retains_match_learning_and_reports_zero_practice():
    gs = state(player())
    play_week(gs, good_line(gs.players["prospect"]), focus="rest")
    report = path.report_view(gs.players["prospect"])
    assert report["focus"] == "rest"
    assert report["sources"]["practice_gains"]["overall_gain"] == 0
    assert report["sources"]["match_gains"]["overall_gain"] > 0


def test_population_contains_real_busts_with_identical_opening_skills_and_forecasts():
    cohort = [player(f"cohort_{i}") for i in range(200)]
    for p in cohort:
        p.career_volatility = None
    busts = [p for p in cohort if development.career_response(p) < 0.5]
    outliers = [p for p in cohort if development.career_response(p) > 1.0]
    assert 4 <= len(busts) <= 30 and 4 <= len(outliers) <= 30
    ordinary = next(p for p in cohort if development.career_response(p) == 1.0)
    bust = busts[0]
    assert development.natural_potential(bust) < development.natural_potential(ordinary) - 15
    assert dict(bust.attributes) == ordinary.attributes
    for p in (bust, ordinary):
        for week in range(20):
            p.stamina = 90
            training.apply_training(state(p).teams["t"], [p], "mechanical",
                                    RngTree(7).derive(week))
    assert development.overall(ordinary) - 55 > (development.overall(bust) - 55) * 3


def test_rare_career_shifts_require_history_are_bounded_and_appear_in_owned_news():
    results = set()
    for seed in range(150):
        for momentum in (0.8, -0.8):
            p = player()
            gs = state(p)
            path.begin_week(gs)
            progress = p.development_progress
            progress.momentum, progress.performance_weeks = momentum, 8
            progress.latest.maps = 2
            progress.latest.focus = "mechanical"
            progress.latest.practice_gains = {"aim_precision": 0.3}
            progress.latest.practice_skills = ["aim_precision"]
            before = dict(p.attributes)
            events = path.career_turning_points(gs, RngTree(seed))
            if events:
                results.add(events[0]["kind"])
                assert -6 <= progress.ceiling_shift <= 6
                assert progress.event_cooldown == path.EVENT_COOLDOWN
                assert all(p.attr(a) >= before[a] for a in ATTRS)
                assert not path.career_turning_points(gs, RngTree(seed))
                assert progress.latest.career_event
                assert gs.private_news_by["t"]
    assert results == {"career_breakthrough", "career_stall"}
    p = player()
    gs = state(p)
    path.begin_week(gs)
    p.development_progress.momentum = 0.8
    p.development_progress.latest.maps = 1
    p.development_progress.latest.practice_gains = {"aim_precision": 0.3}
    p.development_progress.latest.practice_skills = ["aim_precision"]
    assert not path.career_turning_points(gs, RngTree(0))


def test_path_survives_save_load_and_old_save_starts_without_fabricated_history(tmp_path):
    gs = state(player())
    play_week(gs, good_line(gs.players["prospect"]))
    save = tmp_path / "career.json"
    gs.save(save)
    loaded = GameState.load(save)
    assert loaded.model_dump_json() == gs.model_dump_json()
    data = json.loads(save.read_text())
    data["schema_version"] = 35
    del data["players"]["prospect"]["development_progress"]
    save.write_text(json.dumps(data))
    old = GameState.load(save)
    assert old.schema_version == SCHEMA_VERSION
    assert old.players["prospect"].development_progress.latest is None
    assert old.players["prospect"].development_progress.momentum == 0


def test_player_at_forecast_can_earn_new_headroom_and_exceed_expectations():
    for seed in range(150):
        p = player(ca=70, pa=70)
        p.skill_potential = {a: 70.0 for a in ATTRS}
        gs = state(p)
        path.begin_week(gs)
        progress = p.development_progress
        progress.momentum, progress.performance_weeks = 0.8, 8
        progress.latest.maps = 2
        training.apply_training(gs.teams["t"], [p], "mechanical", RngTree(9).derive("t"))
        assert progress.latest.practice_gains == {}
        events = path.career_turning_points(gs, RngTree(seed))
        if events:
            assert progress.ceiling_shift > 0
            assert development.overall(p) > p.potential
            assert progress.latest.event_gains
            view = path.report_view(p)
            assert "ceiling_shift" not in view and "career_response" not in view
            break
    else:
        pytest.fail("the fixed seed cohort should contain a rare breakthrough")


def test_team_recovery_week_cannot_trigger_intense_practice_burnout():
    class BurnoutRoll:
        def random(self):
            return 0.1

        def uniform(self, low, high):
            return low

    p = player()
    p.training_intensity = "intense"
    gs = state(p)
    path.begin_week(gs)
    training.apply_training(gs.teams["t"], [p], "rest", RngTree(3).derive("t"))
    condition_after_rest = p.stamina
    kind, _ = development._fire_event(gs, "t", p, BurnoutRoll())
    assert kind != "burnout"
    assert p.stamina == condition_after_rest


def test_campaign_wires_evidence_and_replays_byte_identically(game_data):
    gs = new_campaign(game_data, seed=73)
    twin = GameState.model_validate_json(gs.model_dump_json())
    advance_week(gs, game_data)
    advance_week(twin, game_data)
    assert gs.model_dump_json() == twin.model_dump_json()
    assert any(p.development_progress.latest.maps > 0 for p in gs.players.values())
    for tid in gs.teams:
        assert all(p.development_progress.latest is not None for p in gs.roster(tid))
