"""Campaign-depth features: AI tactic adaptation, system-fit development,
narrative tactical identity, and the team-level award.

All of these live in the manager layer and never run inside the match
gates, so they can't touch the golden/balance stack — the guarantee here is
that they're wired, deterministic, and neutral-safe where they feed the sim
(system fit is exactly 1.0 at neutral tactics, like every other dial term).
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import advance_week, new_campaign, training
from esports_sim.manager.campaign import _adapt_ai_tactics
from esports_sim.manager.narrative import _tactic_flavor
from esports_sim.registry import load_all


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
