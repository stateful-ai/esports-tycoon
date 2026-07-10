"""The Hall of Fame — the save's long-term memory of greatness.

Induction happens at retirement (the only moment a career is complete),
scored purely from the chronicle + the player's final state: individual
awards dominate, peak ability and career length shade it. The bar is one
constant; a long save should induct a trickle, not a class per season.

The Hall itself is a stored list (`gs.hall_of_fame`) because the players
it describes are deleted at retirement — this is the one legacy view that
can't re-derive from live state. Each induction is also chronicled, so
manager reputations and narrative can cite it.
"""

from __future__ import annotations

from esports_sim.manager import chronicle
from esports_sim.manager.state import GameState, HofRecord
from esports_sim.schemas import Player

HOF_BAR = 60.0
AWARD_POINTS = 26.0
MVP_BONUS = 12.0
CA_SCALE = 1.6  # per point of peak CA above 55
SEASON_POINTS = 2.5  # per season pro (debut -> retirement)


def score_career(gs: GameState, p: Player, ca: float) -> tuple[float, list[str]]:
    """A finished career's Hall score + the lines that justify it."""
    mine = [e for e in gs.chronicle if e.player_id == p.id]
    awards = [e for e in mine if e.kind == "award"]
    mvps = [e for e in awards if "MVP" in e.data.get("award", "")]
    debut_season = min(
        (e.season for e in mine if e.kind == "debut"),
        default=None,
    )
    seasons_pro = (
        gs.season - debut_season + 1 if debut_season is not None else 0
    )
    score = (
        AWARD_POINTS * len(awards)
        + MVP_BONUS * len(mvps)
        + max(0.0, ca - 55.0) * CA_SCALE
        + SEASON_POINTS * seasons_pro
    )
    lines: list[str] = []
    if awards:
        lines.append(f"{len(awards)} individual honours")
    if seasons_pro >= 6:
        lines.append(f"a {seasons_pro}-season career")
    if ca >= 70:
        lines.append(f"peaked at {ca:.0f} CA")
    return round(score, 1), lines


def consider_at_retirement(
    gs: GameState, p: Player, ca: float, team_name: str
) -> bool:
    """Run for every retiree; inducts and chronicles when the career
    clears the bar. Returns True on induction."""
    score, lines = score_career(gs, p, ca)
    if score < HOF_BAR:
        return False
    blurb = "; ".join(lines) if lines else "a career the era remembers"
    gs.hall_of_fame.append(
        HofRecord(
            season=gs.season,
            player_id=p.id,
            handle=p.handle,
            real_name=p.real_name,
            team_name=team_name,
            score=score,
            blurb=blurb,
        )
    )
    gs.push_news(f"{p.handle} enters the Hall of Fame - {blurb}.")
    chronicle.record(
        gs, "hall_of_fame",
        f"{p.handle} is inducted into the Hall of Fame.",
        player_id=p.id,
        data={"score": f"{score:.0f}"},
    )
    return True
