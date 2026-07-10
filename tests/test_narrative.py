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

from esports_sim.manager import chronicle
from esports_sim.manager.narrative import (
    head_to_head,
    season_awards,
    season_in_review,
    weekly_news,
)
from esports_sim.manager.state import (
    AwardRecord,
    ChampionRecord,
    Fixture,
    GameState,
    MapResult,
    PlayerSeasonStats,
)
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role


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


# ---------------------------------------------------------------------------
# Season awards: Clutch Merchant + Most Improved (grounded in the aggregates)


def _award_player(pid: str, ca: float, age: int = 24) -> Player:
    return Player(
        id=pid, handle=pid.title(), age=age, role=Role.DUELIST,
        playstyle=Playstyle.ENTRY,
        attributes={a: ca for a in ("aim_precision", "aim_reactivity", "movement")},
    )


def _award_gs(players, stats, season_start_ca=None) -> GameState:
    team = Team(
        id="nxs", name="Nexus", tag="NXS", tier=1,
        player_ids=[p.id for p in players],
    )
    return GameState(
        seed=1, season=3, week=1, user_team_id="nxs",
        teams={"nxs": team},
        players={p.id: p for p in players},
        player_stats=dict(stats),
        season_start_ca=dict(season_start_ca or {}),
    )


def test_clutch_merchant_goes_to_the_top_clutcher():
    a, b = _award_player("aria", 75), _award_player("brax", 70)
    stats = {
        # b is the better fragger (higher rating/kills) but a is the clutch god.
        "aria": PlayerSeasonStats(maps=10, rating_sum=10.0, kills=150,
                                  first_kills=20, clutches=6, clutch_1v3=2),
        "brax": PlayerSeasonStats(maps=10, rating_sum=12.0, kills=180,
                                  first_kills=25, clutches=1),
    }
    awards = season_awards(_award_gs([a, b], stats))
    by_name = {r.award: r for r in awards}
    assert "Clutch Merchant" in by_name
    assert by_name["Clutch Merchant"].player_id == "aria"
    assert "1v3" in by_name["Clutch Merchant"].value  # cites the 1v3+ heroics
    # sanity: the fragging honours still went to brax
    assert by_name["Season MVP"].player_id == "brax"


def test_clutch_merchant_silent_below_the_bar():
    a = _award_player("aria", 75)
    stats = {"aria": PlayerSeasonStats(maps=10, rating_sum=10.0, kills=150,
                                       first_kills=20, clutches=2)}
    awards = season_awards(_award_gs([a], stats))
    assert not any(r.award == "Clutch Merchant" for r in awards)


def test_most_improved_reads_the_season_start_baseline():
    a, b = _award_player("aria", 78), _award_player("brax", 70)
    stats = {
        "aria": PlayerSeasonStats(maps=10, rating_sum=11.0, kills=150, first_kills=20),
        "brax": PlayerSeasonStats(maps=10, rating_sum=10.0, kills=140, first_kills=18),
    }
    gs = _award_gs([a, b], stats, season_start_ca={"aria": 70.0, "brax": 69.0})
    mip = next((r for r in season_awards(gs) if r.award == "Most Improved"), None)
    assert mip is not None and mip.player_id == "aria"  # +8 CA vs brax's +1
    assert "+8" in mip.value


def test_most_improved_silent_without_a_baseline():
    """Season 1 / an old save has no snapshot -> no manufactured winner."""
    a = _award_player("aria", 78)
    stats = {"aria": PlayerSeasonStats(maps=10, rating_sum=11.0, kills=150, first_kills=20)}
    awards = season_awards(_award_gs([a], stats, season_start_ca={}))
    assert not any(r.award == "Most Improved" for r in awards)


def test_most_improved_silent_when_nobody_really_rose():
    a = _award_player("aria", 71)
    stats = {"aria": PlayerSeasonStats(maps=10, rating_sum=11.0, kills=150, first_kills=20)}
    gs = _award_gs([a], stats, season_start_ca={"aria": 70.0})  # only +1 CA
    assert not any(r.award == "Most Improved" for r in season_awards(gs))


# ---------------------------------------------------------------------------
# Season-in-review: one grounded paragraph over the season's records


def test_season_in_review_composes_grounded_clauses():
    gs = _gs(
        fixtures=[],
        champions=[ChampionRecord(season=2, team_id="vgd", team_name="Vanguard")],
        week=1,
    )  # _gs pins season=2
    gs.awards = [
        AwardRecord(season=2, award="Season MVP", player_id="a", handle="Aria",
                    team_name="Nexus", value="1.30 rating"),
        AwardRecord(season=2, award="Most Improved", player_id="b", handle="Brax",
                    team_name="Nexus", value="+8 CA"),
    ]
    chronicle.record(
        gs, "retirement",
        "Legend retires at 40 (Nexus) - 6 pro seasons, 2 individual honours (2x MVP).",
        player_id="c", importance=70.0,
    )
    chronicle.record(gs, "meta_shift", "Season 2 closes as an aggro-heavy era.")

    review = season_in_review(gs)
    assert review is not None and review.startswith("S2 in review:")
    assert "Vanguard were crowned world champions" in review
    assert "Aria claimed MVP" in review
    assert "Brax made the biggest leap" in review
    assert "Legend" in review and "storied career" in review
    assert "an aggro-heavy era" in review
    assert review.isascii()  # surfaced in ASCII CLI news too


def test_season_in_review_none_when_nothing_notable():
    gs = _gs(fixtures=[], champions=[], week=1)  # season 2, no awards/chronicle
    assert season_in_review(gs) is None


def test_season_in_review_drops_a_quiet_retirement():
    """A run-of-the-mill retirement (importance at the floor) doesn't earn a
    line — only a genuinely notable career does."""
    gs = _gs(
        fixtures=[],
        champions=[ChampionRecord(season=2, team_id="vgd", team_name="Vanguard")],
        week=1,
    )
    chronicle.record(gs, "retirement", "Journeyman retires at 33.",
                     player_id="j", importance=40.0)
    review = season_in_review(gs)
    assert review is not None  # champion clause still fires
    assert "storied career" not in review
