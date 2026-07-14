"""Campaign-depth features: AI tactic adaptation, system-fit development,
narrative tactical identity, and the team-level award.

All of these live in the manager layer and never run inside the match
gates, so they can't touch the golden/balance stack — the guarantee here is
that they're wired, deterministic, and neutral-safe where they feed the sim
(system fit is exactly 1.0 at neutral tactics, like every other dial term).
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import (
    advance_week,
    chronicle,
    development,
    new_campaign,
    training,
    transfer_requests,
)
from esports_sim.manager.campaign import _adapt_ai_tactics, _process_retirements
from esports_sim.manager.narrative import _tactic_flavor
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role


def _campaign(seed: int = 7):
    gd = load_all()
    return gd, new_campaign(gd, seed=seed)


def test_system_fit_is_neutral_at_default_tactics() -> None:
    """A default (neutral) coach gives every player exactly a 1.0 dev
    multiplier — so default teams and the development tests are unchanged.
    An extreme system rewards the fitting playstyle and taxes the rest."""
    gd, gs = _campaign()
    team = gd.teams["team_nexus"]
    for p in gs.roster("team_nexus"):
        assert training._system_fit_mult(team, p) == 1.0

    team.tactics.aggression = 100.0
    team.tactics.pace = 100.0
    entries = [p for p in gs.roster("team_nexus") if str(p.playstyle) in ("entry", "awper")]
    others = [p for p in gs.roster("team_nexus") if str(p.playstyle) in ("igl", "support", "anchor")]
    if entries:
        assert training._system_fit_mult(team, entries[0]) > 1.0
    if others:
        assert training._system_fit_mult(team, others[0]) == 1.0  # not their dials


def test_ai_tactics_adapt_and_stay_deterministic() -> None:
    """AI dials drift week to week (they used to be frozen for the season),
    and the whole campaign stays byte-identical across identical seeds."""
    gd, gs = _campaign()
    ai = [t for t in gs.teams if t != gs.user_team_id]
    before = {t: gs.teams[t].tactics.aggression for t in ai}
    for _ in range(6):
        advance_week(gs, gd)
    drifted = sum(1 for t in ai if gs.teams[t].tactics.aggression != before[t])
    assert drifted >= len(ai) // 2, "AI tactics barely moved — adaptation not wired"

    def run():
        _, g = _campaign(11)
        for _ in range(8):
            advance_week(g, gd)
        return g.model_dump_json()

    assert run() == run()


def test_adapt_respects_min_maps_and_user_team() -> None:
    """No adaptation before enough maps, and the user's dials are never
    touched by the AI adaptation pass."""
    gd, gs = _campaign()
    user_before = gs.teams[gs.user_team_id].tactics.model_dump()
    # Fresh season: no team has played _ADAPT_MIN_MAPS yet -> no-op.
    snap = {t: gs.teams[t].tactics.model_dump() for t in gs.teams}
    _adapt_ai_tactics(gs, np.random.default_rng(0))
    assert all(gs.teams[t].tactics.model_dump() == snap[t] for t in gs.teams)
    # After real weeks, the user team is still exactly as the user left it.
    for _ in range(5):
        advance_week(gs, gd)
    assert gs.teams[gs.user_team_id].tactics.model_dump() == user_before


def test_tactic_flavor_only_fires_on_extremes() -> None:
    """The narrative clause names the most off-neutral dial, and stays
    silent for a balanced identity."""
    gd, _ = _campaign()
    neutral = gd.teams["team_nexus"].tactics
    assert _tactic_flavor(neutral) == ""
    neutral.aggression = 90.0
    assert "aggression" in _tactic_flavor(neutral).lower()


def test_tactic_flavor_credits_the_winner_not_the_loser() -> None:
    """The recap clause names the WINNER's identity: a user win credits the
    user's system; a user loss must NOT stamp the user's own flavor onto a
    defeat (the bug was appending it on the loss branch)."""
    from esports_sim.manager.narrative import _user_recap
    from esports_sim.manager.state import Fixture, MapResult

    _, gs = _campaign()
    user, opp = gs.user_team_id, "team_vanguard"
    gs.teams[user].tactics.aggression = 90.0  # extreme, quotable identity
    gs.teams[opp].tactics.aggression = 50.0  # neutral, no clause

    def recap(winner: str) -> str:
        f = Fixture(
            id="t", week=1, best_of=1, team_a=user, team_b=opp, played=True,
            winner_id=winner,
            results=[MapResult(
                map_id="haven", seed=1,
                score_a=13 if winner == user else 7,
                score_b=7 if winner == user else 13,
                winner_id=winner,
            )],
        )
        _user_recap(gs, f, [])
        return gs.news[-1].lower()

    assert "aggression" in recap(user)  # user won -> user's clause
    assert "aggression" not in recap(opp)  # user lost -> no user clause


def test_best_defensive_team_award_is_granted() -> None:
    """A full season produces the team-level award, anchored to a real
    player on the winning team."""
    gd, gs = _campaign(seed=3)
    for _ in range(60):
        advance_week(gs, gd)
        if gs.season >= 2 and gs.phase == "regular":
            break
    team_awards = [a for a in gs.awards if a.award == "Best Defensive Team"]
    assert team_awards, "no Best Defensive Team award was granted"
    a = team_awards[-1]
    assert a.player_id in gs.players
    assert "%" in a.value
    # CLI news is ASCII-only (cp1252 consoles) — the award line must comply.
    def_news = [n for n in gs.news if "Best Defensive Team" in n]
    assert def_news and all(n.isascii() for n in def_news)


def _decorated_veteran() -> GameState:
    """A 40-year-old two-time MVP on a tier-1 side, with a debut and two
    award entries already on the chronicle — the raw material for a
    retirement sendoff."""
    star = Player(
        id="star", handle="Legend", age=40, role=Role.DUELIST,
        playstyle=Playstyle.ENTRY,
        attributes={a: 82.0 for a in ("aim_precision", "aim_reactivity", "movement")},
    )
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["star"])
    gs = GameState(
        seed=1, season=6, week=1, user_team_id="nxs",
        teams={"nxs": team}, players={"star": star},
    )
    gs.season = 1
    chronicle.record(gs, "debut", "Legend debuts.", team_id="nxs", player_id="star")
    for yr, rat in ((3, "1.30"), (5, "1.25")):
        gs.season = yr
        chronicle.record(
            gs, "award", f"Legend wins Season MVP ({rat}).",
            team_id="nxs", player_id="star",
            data={"award": "Season MVP", "value": f"{rat} rating"},
        )
    gs.season = 6
    return gs


class _AlwaysRetireRng:
    """rng.random() == 0.0 < any positive retirement prob, so an
    already-past-decline veteran is guaranteed to hang it up."""

    def random(self) -> float:
        return 0.0


def test_retirement_tribute_for_a_decorated_career() -> None:
    gs = _decorated_veteran()
    team = gs.teams["nxs"]
    team.lineup_ids = ["star"]
    team.lineup.starters = ["star"]
    team.lineup.agents = {"star": "jett"}
    gs.academy_player_rights["star"] = "nxs"
    gs.leadership_groups["nxs"] = ["star"]
    transfer_requests.issue(gs, "star", "wants a final move")
    n = _process_retirements(gs, _AlwaysRetireRng())
    assert n == 1
    # A decorated retiree earns their own sendoff line...
    sendoffs = [ln for ln in gs.news if "End of an era" in ln and "Legend" in ln]
    assert sendoffs, "a two-time MVP retired without a tribute"
    assert all(ln.isascii() for ln in sendoffs)  # CLI news is ASCII-only
    # ...and the retirement chronicle entry carries the career resume,
    # lifted above the plain-retirement importance floor for callbacks.
    ret = [e for e in gs.chronicle if e.kind == "retirement" and e.player_id == "star"]
    assert ret and "pro seasons" in ret[0].text and "MVP" in ret[0].text
    assert ret[0].importance > 40.0
    assert team.lineup_ids == []
    assert team.lineup.starters == []
    assert team.lineup.agents == {}
    assert "star" not in gs.academy_player_rights
    assert "star" not in gs.leadership_groups["nxs"]
    assert "star" not in gs.transfer_requests_by


def test_undecorated_retiree_gets_no_tribute() -> None:
    """A journeyman with no honours retires quietly — no sendoff spam."""
    p = Player(
        id="jrn", handle="Journeyman", age=40, role=Role.SENTINEL,
        playstyle=Playstyle.ANCHOR,
        attributes={a: 55.0 for a in ("aim_precision", "aim_reactivity", "movement")},
    )
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["jrn"])
    gs = GameState(
        seed=1, season=4, week=1, user_team_id="nxs",
        teams={"nxs": team}, players={"jrn": p},
    )
    _process_retirements(gs, _AlwaysRetireRng())
    assert not any("End of an era" in ln for ln in gs.news)


def test_career_stats_accumulate_and_kill_milestone():
    from esports_sim.manager.campaign import _accumulate_career_stats
    from esports_sim.manager.state import CareerStats, PlayerSeasonStats

    p = Player(id="ace", handle="Ace", age=24, role=Role.DUELIST,
               playstyle=Playstyle.ENTRY, attributes={"aim_precision": 80})
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["ace"])
    gs = GameState(seed=1, season=2, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players={"ace": p})
    gs.career_stats["ace"] = CareerStats(maps=40, kills=480, deaths=400, seasons=3)
    gs.player_stats["ace"] = PlayerSeasonStats(
        maps=14, kills=60, deaths=50, rounds=300, first_kills=10, clutches=5)
    _accumulate_career_stats(gs)
    cs = gs.career_stats["ace"]
    assert cs.kills == 540 and cs.maps == 54 and cs.seasons == 4
    assert cs.first_kills == 10 and cs.clutches == 5
    # crossed 500 career kills this season -> chronicled milestone + news
    assert any(e.kind == "milestone" and "500 career kills" in e.text
               for e in gs.chronicle)
    assert any("500 career kills" in n for n in gs.news)


def test_career_stats_no_milestone_without_a_crossing():
    from esports_sim.manager.campaign import _accumulate_career_stats
    from esports_sim.manager.state import PlayerSeasonStats

    p = Player(id="rk", handle="Rook", age=19, role=Role.DUELIST,
               playstyle=Playstyle.ENTRY, attributes={"aim_precision": 70})
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["rk"])
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players={"rk": p})
    gs.player_stats["rk"] = PlayerSeasonStats(maps=8, kills=120, deaths=100)
    _accumulate_career_stats(gs)
    assert gs.career_stats["rk"].kills == 120  # first season, no prior total
    assert not any(e.kind == "milestone" for e in gs.chronicle)  # 120 < 500 bar


def _mp(pid, age, ca, role=Role.DUELIST, potential=0.0):
    return Player(id=pid, handle=pid.upper(), age=age, role=role,
                  playstyle=Playstyle.ENTRY, potential=potential,
                  attributes={a: ca for a in ("aim_precision", "aim_reactivity", "movement")})


def test_mentorship_valid_requires_older_and_better_teammate():
    from esports_sim.manager.campaign import mentorship_valid
    young = _mp("y", 19, 60.0)
    vet = _mp("v", 27, 85.0, role=Role.CONTROLLER)
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["y", "v"])
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players={"y": young, "v": vet})
    assert mentorship_valid(gs, "y", "v") is True
    assert mentorship_valid(gs, "v", "y") is False   # mentor must be older + better
    assert mentorship_valid(gs, "y", "y") is False   # not oneself


def test_mentor_mults_is_none_without_a_set_mentorship():
    from esports_sim.manager.campaign import _mentor_mults
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["y"])
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players={"y": _mp("y", 19, 60.0)})
    assert _mentor_mults(gs, "nxs") is None  # hands-off -> byte-identical training


def test_mentorship_boosts_protege_growth_same_seed():
    import numpy as np
    from esports_sim.manager import training

    proto = _mp("y", 18, 55.0, potential=92.0)  # big headroom -> real growth
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["y"])
    base = proto.model_copy(deep=True)
    boosted = proto.model_copy(deep=True)

    def ca(p):
        return sum(p.attributes.values()) / len(p.attributes)

    training.apply_training(team, [base], "mechanical", np.random.default_rng(0))
    training.apply_training(team, [boosted], "mechanical", np.random.default_rng(0),
                            mentor_mults={"y": training.MENTOR_GROWTH_MULT})
    assert ca(boosted) > ca(base)  # identical rng, only the mentor mult differs


def test_duo_mentor_and_morale_create_support_headroom():
    from esports_sim.manager import relationships
    from esports_sim.manager.campaign import _development_support_bonuses

    young = _mp("young", 19, 69.0, potential=70.0)
    young.morale, young.confidence, young.form = 96.0, 88.0, 75.0
    veteran = _mp("vet", 30, 82.0, role=Role.CONTROLLER)
    veteran.personality_tags = ["veteran", "leader"]
    team = Team(
        id="nxs", name="Nexus", tag="NXS", tier=1,
        player_ids=[young.id, veteran.id], chemistry=92.0,
    )
    gs = GameState(
        seed=1, season=1, week=1, user_team_id="nxs",
        teams={"nxs": team}, players={young.id: young, veteran.id: veteran},
        mentorships={young.id: veteran.id},
    )
    relationships.nudge(gs, young.id, veteran.id, 46.0)  # 50 -> 96: named duo
    bonuses = _development_support_bonuses(gs, "nxs")
    assert bonuses and bonuses[young.id] >= 7.0
    assert development.development_ceiling(
        young, "aim_precision", bonuses[young.id]
    ) > young.potential


def test_team_talk_nudges_dressed_confidence_and_is_bounded():
    from esports_sim.manager.campaign import _apply_team_talk
    lo = _mp("lo", 24, 70.0)
    lo.confidence = 90.0   # near the ceiling: a fire_up can't push past 95
    mid = _mp("mid", 24, 70.0)
    mid.confidence = 50.0
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["lo", "mid"])
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players={"lo": lo, "mid": mid})
    _apply_team_talk(gs, "fire_up", ["lo", "mid"])
    assert gs.players["mid"].confidence > 50.0      # a lift
    assert gs.players["lo"].confidence <= 95.0       # clamped to the ceiling


def test_team_talk_focus_settles_toward_the_middle():
    from esports_sim.manager.campaign import _apply_team_talk
    tilted = _mp("t", 24, 70.0)
    tilted.confidence = 20.0
    hubris = _mp("h", 24, 70.0)
    hubris.confidence = 90.0
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1, player_ids=["t", "h"])
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players={"t": tilted, "h": hubris})
    _apply_team_talk(gs, "focus", ["t", "h"])
    assert gs.players["t"].confidence > 20.0    # pulled up toward 55
    assert gs.players["h"].confidence < 90.0    # pulled down toward 55


def test_team_talk_recipients_follow_a_per_map_override():
    # Codex review: the talk must land on the players who ACTUALLY dress. With
    # a per-map lineup override, dressed_for (and so the recipient set) rotates
    # the bench player in — the talk must follow, not stick to default_five.
    from esports_sim.manager.campaign import _talk_recipients
    from esports_sim.manager.state import Fixture

    ids = ["a", "b", "c", "d", "e", "f"]
    ps = {pid: _mp(pid, 24, 70.0) for pid in ids}
    team = Team(id="nxs", name="Nexus", tag="NXS", tier=1,
                player_ids=ids, lineup_ids=["a", "b", "c", "d", "e"])
    gs = GameState(seed=1, season=1, week=1, user_team_id="nxs",
                   teams={"nxs": team}, players=ps)
    fx = Fixture(id="s1w1m0", week=1, team_a="nxs", team_b="opp", maps=["ascent"])
    # Default: recipients are the default five (bench player 'f' excluded).
    assert _talk_recipients(gs, "nxs", fx) == ["a", "b", "c", "d", "e"]
    # Override rotates 'f' in for 'e' -> the recipients follow.
    gs.map_lineups["nxs|s1w1m0|ascent"] = ["a", "b", "c", "d", "f"]
    assert _talk_recipients(gs, "nxs", fx) == ["a", "b", "c", "d", "f"]


def test_ai_fixture_plan_uses_shared_resolver_and_rotates_a_rested_bench():
    """AI plans are stored GamePlans, not an invisible match-only modifier."""
    from esports_sim.manager.campaign import (
        _apply_bench_week,
        _book_ai_fixture_plans,
        _fixture_plans,
        default_five,
    )

    _gd, gs = _campaign(88)
    fixture = next(
        f for f in gs.fixtures
        if f.team_a != gs.user_team_id and f.team_b != gs.user_team_id
    )
    ai, opponent = fixture.team_a, fixture.team_b
    bench_id = max(gs.free_agent_ids, key=lambda pid: (sum(gs.players[pid].attributes.values()), pid))
    gs.free_agent_ids.remove(bench_id)
    gs.teams[ai].player_ids.append(bench_id)
    for attr in gs.players[bench_id].attributes:
        gs.players[bench_id].attributes[attr] = 99.0
    gs.players[bench_id].stamina = 100.0
    old_five = default_five(gs, ai)
    for pid in old_five:
        gs.players[pid].stamina = 30.0
    gs.teams[ai].tactics.pace = 85.0
    gs.teams[opponent].tactics.aggression = 85.0

    _book_ai_fixture_plans(gs, [fixture])

    plan = gs.game_plans_by[ai]
    plans, lineups = _fixture_plans(gs, fixture)
    assert {fixture.team_a, fixture.team_b} <= set(gs.game_plans_by)
    assert plan.fixture_id == fixture.id
    assert plan.aggression == 40.0
    assert bench_id in lineups[ai]
    assert plans[ai].counter_edge > 0.0
    assert any("counter-plan" in note and gs.teams[ai].tag in note for note in fixture.series_notes)

    sat_out = next(pid for pid in old_five if pid not in lineups[ai])
    before = gs.players[sat_out].stamina
    _apply_bench_week(gs, {ai: set(lineups[ai])})
    assert gs.players[sat_out].stamina == before + 6.0


def test_ai_rotation_and_fixture_plan_respect_tournament_registration():
    """A playoff plan cannot claim an unregistered sixth player starts."""
    from esports_sim.manager.campaign import _ai_match_lineup, _fixture_plans, default_five
    from esports_sim.manager.state import GamePlan

    _gd, gs = _campaign(89)
    fixture = next(f for f in gs.fixtures if f.team_a != gs.user_team_id)
    ai = fixture.team_a
    bench_id = max(gs.free_agent_ids, key=lambda pid: (sum(gs.players[pid].attributes.values()), pid))
    gs.free_agent_ids.remove(bench_id)
    gs.teams[ai].player_ids.append(bench_id)
    old_five = default_five(gs, ai)
    fixture.best_of = 3
    fixture.maps = ["ascent", "bind", "haven"]
    gs.tournament_rosters[ai] = list(old_five)

    assert _ai_match_lineup(gs, ai, fixture) == []
    gs.game_plans_by[ai] = GamePlan(fixture_id=fixture.id, starter_ids=[*old_five[:4], bench_id])
    _plans, lineups = _fixture_plans(gs, fixture)
    assert ai not in lineups
