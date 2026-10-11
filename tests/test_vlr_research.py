"""Research contracts: map grain, source identity, missingness, and leakage."""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

BeautifulSoup = pytest.importorskip("bs4").BeautifulSoup

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


collector = load_script("collect_vlr_research")
analysis = load_script("analyze_vlr_research")
EVENT = {"event_id": "10", "competition_tier": 1, "region": "americas"}
SOURCE = {"source_url": "https://www.vlr.gg/123/a-vs-b", "sha256": "a"*64, "retrieved_at_utc": "2026-10-06T00:00:00+00:00"}


def match_fixture():
    parts = ['<div class="match-header-date"><div data-utc-ts="2026-04-01 10:00:00"></div>Patch 12.03</div>',
             '<div class="match-header-vs"><a class="match-header-link" href="/team/1/a"><div class="wf-title-med">A</div></a>',
             '<a class="match-header-link" href="/team/2/b"><div class="wf-title-med">B</div></a></div>']
    for gid in ["all", "99"]:
        parts.append(f'<div class="vm-stats-game" data-game-id="{gid}"><div class="vm-stats-game-header"><div class="score">13</div><div class="score">8</div><div class="map"><div><span>Haven<span>PICK</span></span></div></div></div>')
        for team in range(2):
            parts.append('<div class="ovw-table"><div class="ovw-row mod-head"></div>')
            for player in range(5):
                pid = team*5 + player + 1
                parts.append(f'<div class="ovw-row"><a href="/player/{pid}/p{pid}"><div class="ovw-player-name">p{pid}</div></a><div class="ovw-agents"><img src="/img/vlr/game/agents/sova.png"></div>')
                for col in collector.MAP_COLS:
                    value = "0" if col in {"fb", "fd"} else "10"
                    parts.append(f'<div data-col="{col}"><span class="side mod-both">{value}</span><span class="side mod-t">999</span><span class="side mod-ct">888</span></div>')
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')
    return BeautifulSoup("".join(parts), "html.parser")


def test_map_grain_excludes_series_and_sides():
    maps, rows, status = collector.parse_match(match_fixture(), EVENT, SOURCE, "2026-10-06")
    assert status == "parsed"
    assert len(maps) == 1 and len(rows) == 10
    assert maps[0]["map_name"] == "Haven"
    assert maps[0]["rounds"] == 21
    assert {r["kills"] for r in rows} == {10}
    assert sum(r["map_win"] for r in rows) == 5
    assert {r["source_sha256"] for r in rows} == {SOURCE["sha256"]}


def test_match_date_cutoff_prevents_future_outcomes():
    assert collector.parse_match(match_fixture(), EVENT, SOURCE, "2026-03-31")[0] == []


def test_unnamed_team_is_reported_without_crashing():
    soup = match_fixture()
    del soup.select_one('a.match-header-link')["href"]
    assert collector.parse_match(soup, EVENT, SOURCE, "2026-10-06")[2] == "missing_teams"


@pytest.mark.parametrize("scores", [(12, 10), (13, 12)])
def test_live_regulation_or_overtime_lead_is_not_a_map_outcome(scores):
    soup = match_fixture()
    for cell, score in zip(soup.select('.vm-stats-game[data-game-id="99"] .score'), scores):
        cell.string = str(score)
    maps, players, status = collector.parse_match(soup, EVENT, SOURCE, "2026-10-06")
    assert maps == [] and players == [] and status == "no_played_maps"


def test_missing_values_remain_missing_and_fk_rates_use_counts():
    html = '''<table id="st-table"><tbody><tr><td><a href="/player/4/name"><div class="st-pl-name">Name</div></a></td>
    <td data-col="rnd">20</td><td data-col="maps">1</td><td data-col="rating2">-</td>
    <td data-col="fbpr">15%</td><td data-col="fk">3</td><td data-col="fd">0</td></tr></tbody></table>'''
    row = collector.parse_event_stats(BeautifulSoup(html, "html.parser"), EVENT, SOURCE)[0]
    assert row["vlr_rating"] is None and row["kills"] is None
    assert row["fkpr"] == .15 and row["fdpr"] == 0
    assert row["fk_rate_reported"] == 15  # original display stays separate


def test_profile_current_team_does_not_include_past_teams():
    html = '''<div class="player-header"><h1 class="wf-title">Name</h1><h2 class="player-real-name">Real Name</h2></div>
    <h2 class="wf-label">Current Teams</h2><div><a href="/team/1/a">A stand-in</a></div>
    <h2 class="wf-label">Past Teams</h2><div><a href="/team/2/b">B</a></div>'''
    row = collector.parse_profile(BeautifulSoup(html, "html.parser"), {**SOURCE, "source_url": "https://www.vlr.gg/player/4/name"})
    assert row["current_team_evidence"] == "A stand-in"
    assert row["team_listing_status"] == "current_team_listed"


def test_name_only_candidate_never_links_to_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "roster_rows", lambda: [{"handle": "Name", "real_name": "Different Person", "country": "US", "pack_team_tag": "A", "pack_status": "free_agent"}])
    class OfflineProfile:
        sources = {}
        def get(self, url):
            return BeautifulSoup('<div class="player-header"><h1 class="wf-title">Name</h1><h2 class="player-real-name">Other Person</h2></div>', 'html.parser'), {**SOURCE, "source_url": url}
    collector.collect_profiles(OfflineProfile(), [{"handle": "Name", "vlr_player_id": "4", "country": "CA", "team_tag_at_event": "B", "player_url": "https://www.vlr.gg/player/4/name"}], [], tmp_path, tmp_path / "missing.json")
    with (tmp_path / "roster_crosswalk.csv").open() as f:
        row = next(csv.DictReader(f))
    assert row["identity_status"] == "candidate_needs_review"
    assert row["vlr_player_id"] == ""


def test_validation_rejects_duplicate_maps(tmp_path):
    maps, rows, _ = collector.parse_match(match_fixture(), EVENT, SOURCE, "2026-10-06")
    collector.write_csv(tmp_path / "events.csv", [{"event_id": "10", "collect_maps": "False"}])
    collector.write_csv(tmp_path / "player_event_stats.csv", [], ["event_id", "vlr_player_id"])
    collector.write_csv(tmp_path / "player_map_stats.csv", rows)
    collector.write_csv(tmp_path / "map_outcomes.csv", maps)
    assert analysis.validate(tmp_path)["errors"] == []
    collector.write_csv(tmp_path / "map_outcomes.csv", maps + maps)
    with pytest.raises(ValueError, match="validation failed"):
        analysis.validate(tmp_path)


def test_source_missing_opening_stats_do_not_become_zero(tmp_path):
    maps, rows, _ = collector.parse_match(match_fixture(), EVENT, SOURCE, "2026-10-06")
    rows[0]["first_kills"] = None
    collector.write_csv(tmp_path / "events.csv", [{"event_id": "10", "collect_maps": "False"}])
    collector.write_csv(tmp_path / "player_event_stats.csv", [], ["event_id", "vlr_player_id"])
    collector.write_csv(tmp_path / "player_map_stats.csv", rows)
    collector.write_csv(tmp_path / "map_outcomes.csv", maps)
    receipt = analysis.validate(tmp_path)
    assert receipt["errors"] == []
    assert receipt["player_map_missing_counts"]["first_kills"] == 1


def test_logistic_orientation_and_inseparable_teammates():
    x = np.array([[1, 1, -1], [1, 1, -1], [-1, -1, 1], [1, 1, -1]], dtype=float)
    y = np.array([1, 1, 0, 0], dtype=float)
    coef = analysis.fit_logistic(x, y)
    assert coef[0] == pytest.approx(coef[1])
    reversed_coef = analysis.fit_logistic(-x, 1-y)
    assert reversed_coef == pytest.approx(coef)
    assert analysis.sigmoid(x @ coef) == pytest.approx(1-analysis.sigmoid(-x @ coef))


def test_incomplete_source_lineup_preserves_outcome_but_is_not_model_eligible(tmp_path):
    soup = match_fixture()
    for row in soup.select('.vm-stats-game[data-game-id="99"] .ovw-table')[0].select('.ovw-row:not(.mod-head)'):
        row.decompose()
    maps, players, status = collector.parse_match(soup, EVENT, SOURCE, "2026-10-06")
    assert status == "parsed" and maps[0]["rounds"] == 21 and len(players) == 5
    assert not analysis.lineup_eligible(maps[0], players)
    collector.write_csv(tmp_path / "events.csv", [{"event_id": "10", "collect_maps": "False"}])
    collector.write_csv(tmp_path / "player_event_stats.csv", [], ["event_id", "vlr_player_id"])
    collector.write_csv(tmp_path / "player_map_stats.csv", players)
    collector.write_csv(tmp_path / "map_outcomes.csv", maps)
    receipt = analysis.validate(tmp_path)
    assert receipt["errors"] == []
    assert any("excluded from lineup model" in w for w in receipt["warnings"])


def test_map_evidence_does_not_erase_country_corroboration(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "roster_rows", lambda: [{"handle": "Name", "real_name": "Unknown", "country": "CA", "pack_team_tag": "B", "pack_status": "free_agent"}])
    class OfflineProfile:
        sources = {}
        def get(self, url):
            return BeautifulSoup('<div class="player-header"><h1 class="wf-title">Name</h1></div>', 'html.parser'), {**SOURCE, "source_url": url}
    evidence = {"handle": "Name", "vlr_player_id": "4", "country": "CA", "team_tag_at_event": "B", "player_url": "https://www.vlr.gg/player/4/name"}
    collector.write_csv(tmp_path / "player_map_stats.csv", [{**evidence, "team_tag_at_match": "B"}])
    collector.collect_profiles(OfflineProfile(), [evidence], [], tmp_path, tmp_path / "missing.json")
    with (tmp_path / "roster_crosswalk.csv").open() as f:
        row = next(csv.DictReader(f))
    assert row["identity_status"] == "corroborated"
    assert row["identity_evidence"] == "handle+event_team_tag+country"
