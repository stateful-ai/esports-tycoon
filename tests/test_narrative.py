"""Tests for `head_to_head` and the history callbacks it feeds into weekly
recaps (esports_sim.manager.narrative).

GameState is built by hand — no registry data, no sim engine — since
`head_to_head` and the recap wiring only ever read Fixture / Team /
ChampionRecord fields already sitting on GameState. Fixtures stand in for
`report` objects too (weekly_news only needs `.fixtures` and `.match_stats`),
so nothing from campaign.py or the engine is imported here.
"""

from __future__ import annotations

import types

from esports_sim.manager.narrative import head_to_head, weekly_news
from esports_sim.manager.state import ChampionRecord, Fixture, GameState, MapResult
from esports_sim.schemas import Team


def _team(team_id: str, name: str, world_rank: int | None = None) -> Team:
    return Team(id=team_id, name=name, tag=team_id.upper()[:3], world_rank=world_rank)


def _played_fixture(
    fid: str,
    week: int,
    team_a: str,
    team_b: str,
    winner_id: str,
    stage: str = "regular",
) -> Fixture:
    """A finished BO1 fixture. The score is just flavor — winner_id is the
    only fact head_to_head / _series_score actually read."""
    score_a, score_b = (13, 7) if winner_id == team_a else (7, 13)
    return Fixture(
        id=fid,
        week=week,
        stage=stage,
        best_of=1,
        team_a=team_a,
        team_b=team_b,
        maps=["ascent"],
        played=True,
        winner_id=winner_id,
        results=[
            MapResult(
                map_id="ascent", seed=0, score_a=score_a, score_b=score_b,
                winner_id=winner_id,
            )
        ],
    )


def _gs(fixtures, champions=None, week: int = 1) -> GameState:
    teams = {
        "nxs": _team("nxs", "Nexus"),
        "vgd": _team("vgd", "Vanguard"),
        "obs": _team("obs", "Obsidian"),
    }
    return GameState(
        seed=1234,
        season=2,
        week=week,
        user_team_id="nxs",
        teams=teams,
        fixtures=list(fixtures),
        champions=list(champions or []),
    )


def _report(fixtures):
    """Minimal stand-in for campaign.WeekReport: weekly_news only reads
    `.fixtures` and `.match_stats.get(fixture_id, [])`."""
    return types.SimpleNamespace(fixtures=list(fixtures), match_stats={})


# ---------------------------------------------------------------------------
# head_to_head: pure computation


def test_no_prior_meetings_is_empty_and_grounded():
    gs = _gs(fixtures=[])
    h2h = head_to_head(gs, "nxs", "vgd")
    assert h2h["meetings"] == 0
    assert h2h["wins_a"] == 0
    assert h2h["wins_b"] == 0
    assert h2h["last_meeting_week"] is None
    assert h2h["last_winner_id"] is None
    assert h2h["streak_winner_id"] is None
    assert h2h["streak_len"] == 0
    assert h2h["revenge"] is False
    assert h2h["revenge_week"] is None


def test_ignores_unplayed_and_unrelated_fixtures():
    fixtures = [
        _played_fixture("s2w1m0", 1, "nxs", "obs", winner_id="nxs"),  # different pair
        Fixture(id="s2w2m0", week=2, team_a="nxs", team_b="vgd"),  # not played
        _played_fixture("s2w3m0", 3, "nxs", "vgd", winner_id="vgd"),
    ]
    gs = _gs(fixtures)
    h2h = head_to_head(gs, "nxs", "vgd")
    assert h2h["meetings"] == 1
    assert h2h["last_meeting_week"] == 3
    assert h2h["last_winner_id"] == "vgd"


def test_streak_detection():
    fixtures = [
        _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd"),
        _played_fixture("s2w2m0", 2, "vgd", "nxs", winner_id="vgd"),
        _played_fixture("s2w3m0", 3, "nxs", "vgd", winner_id="vgd"),
    ]
    gs = _gs(fixtures)
    h2h = head_to_head(gs, "nxs", "vgd")
    assert h2h["meetings"] == 3
    assert h2h["wins_a"] == 0  # team_a arg was "nxs"
    assert h2h["wins_b"] == 3
    assert h2h["streak_winner_id"] == "vgd"
    assert h2h["streak_len"] == 3
    assert h2h["revenge"] is False  # last two meetings share a winner


def test_streak_breaks_on_split_result():
    fixtures = [
        _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd"),
        _played_fixture("s2w2m0", 2, "vgd", "nxs", winner_id="nxs"),
    ]
    gs = _gs(fixtures)
    h2h = head_to_head(gs, "nxs", "vgd")
    assert h2h["streak_winner_id"] == "nxs"
    assert h2h["streak_len"] == 1


def test_revenge_detection():
    fixtures = [
        _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd"),
        _played_fixture("s2w4m0", 4, "vgd", "nxs", winner_id="nxs"),
    ]
    gs = _gs(fixtures)
    h2h = head_to_head(gs, "nxs", "vgd")
    assert h2h["revenge"] is True
    assert h2h["revenge_week"] == 1
    assert h2h["last_winner_id"] == "nxs"


def test_reigning_champion_flag_uses_latest_record():
    gs = _gs(
        fixtures=[],
        champions=[
            ChampionRecord(season=1, team_id="obs", team_name="Obsidian"),
            ChampionRecord(season=2, team_id="vgd", team_name="Vanguard"),
        ],
    )
    h2h = head_to_head(gs, "nxs", "vgd")
    assert h2h["reigning_champion_id"] == "vgd"


def test_no_champion_crowned_yet_is_none():
    gs = _gs(fixtures=[], champions=[])
    assert head_to_head(gs, "nxs", "vgd")["reigning_champion_id"] is None


def test_head_to_head_is_deterministic_and_order_independent():
    fixtures = [
        _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd"),
        _played_fixture("s2w2m0", 2, "vgd", "nxs", winner_id="vgd"),
    ]
    gs = _gs(fixtures)
    first = head_to_head(gs, "nxs", "vgd")
    second = head_to_head(gs, "nxs", "vgd")
    assert first == second  # pure function: identical inputs, identical output

    swapped = head_to_head(gs, "vgd", "nxs")
    assert swapped["meetings"] == first["meetings"]
    assert swapped["wins_a"] == first["wins_b"]
    assert swapped["wins_b"] == first["wins_a"]
    assert swapped["streak_winner_id"] == first["streak_winner_id"]
    assert swapped["last_winner_id"] == first["last_winner_id"]


def test_never_claims_a_meeting_outside_the_fixture_list():
    """Every counted meeting must correspond to an actual played fixture
    between exactly these two teams — the grounding rule in prose form."""
    fixtures = [
        _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd"),
        _played_fixture("s2w2m0", 2, "nxs", "obs", winner_id="nxs"),
        _played_fixture("s2w3m0", 3, "obs", "vgd", winner_id="obs"),
    ]
    gs = _gs(fixtures)
    h2h = head_to_head(gs, "nxs", "vgd")
    actual = [
        f for f in fixtures
        if f.played and {f.team_a, f.team_b} == {"nxs", "vgd"}
    ]
    assert h2h["meetings"] == len(actual)
    assert h2h["wins_a"] + h2h["wins_b"] == len(actual)


# ---------------------------------------------------------------------------
# Wiring: the callback sentence in _user_recap / _league_line


def test_user_recap_mentions_losing_streak():
    prior = [
        _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd"),
        _played_fixture("s2w2m0", 2, "vgd", "nxs", winner_id="vgd"),
    ]
    current = _played_fixture("s2w3m0", 3, "nxs", "vgd", winner_id="vgd")
    gs = _gs(fixtures=prior + [current], week=3)
    weekly_news(gs, _report([current]), week_kills={})
    assert gs.news, "expected a recap line to be pushed"
    line = gs.news[-1]
    # Both seeded phrasings say "third straight" and name the opponent.
    assert "third straight" in line
    assert "Vanguard" in line


def test_user_recap_mentions_revenge():
    prior = [_played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="vgd")]
    current = _played_fixture("s2w2m0", 2, "vgd", "nxs", winner_id="nxs")
    gs = _gs(fixtures=prior + [current], week=2)
    weekly_news(gs, _report([current]), week_kills={})
    assert "week 1" in gs.news[-1]


def test_user_recap_mentions_reigning_champions_upset():
    current = _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="nxs")
    gs = _gs(
        fixtures=[current],
        champions=[ChampionRecord(season=1, team_id="vgd", team_name="Vanguard")],
        week=1,
    )
    weekly_news(gs, _report([current]), week_kills={})
    assert "reigning champions" in gs.news[-1]


def test_user_recap_silent_when_nothing_notable():
    """A single unremarkable win — no streak, no revenge, opponent isn't
    the reigning champion — gets no callback sentence. Silence beats
    filler."""
    current = _played_fixture("s2w1m0", 1, "nxs", "vgd", winner_id="nxs")
    gs = _gs(fixtures=[current], champions=[], week=1)
    weekly_news(gs, _report([current]), week_kills={})
    line = gs.news[-1]
    for phrase in ("straight", "Flips the result", "reverses the week", "reigning champions"):
        assert phrase not in line


def test_league_line_mentions_reigning_champions_upset():
    # obs (world #10) upsets vgd (world #1), the reigning champion.
    fixtures = [_played_fixture("s2w1m0", 1, "obs", "vgd", winner_id="obs")]
    gs = _gs(
        fixtures=fixtures,
        champions=[ChampionRecord(season=1, team_id="vgd", team_name="Vanguard")],
        week=1,
    )
    gs.teams["obs"].world_rank = 10
    gs.teams["vgd"].world_rank = 1
    weekly_news(gs, _report(fixtures), week_kills={})
    assert any("reigning champions" in line for line in gs.news)


def test_league_line_no_champion_mention_when_loser_isnt_champion():
    fixtures = [_played_fixture("s2w1m0", 1, "obs", "vgd", winner_id="obs")]
    gs = _gs(fixtures=fixtures, champions=[], week=1)
    gs.teams["obs"].world_rank = 10
    gs.teams["vgd"].world_rank = 1
    weekly_news(gs, _report(fixtures), week_kills={})
    assert gs.news
    assert not any("reigning champions" in line for line in gs.news)
