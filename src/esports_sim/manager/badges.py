"""Player badges: rolled, decaying honours (and stigmas) that MOVE a player.

Layered on the monumental-moment hooks (development.moment_potential_bump gives
the small universal nudge; a BADGE is the rare, named, rolled reward on top). A
career moment does not GRANT a badge --- it ROLLS for one on a dedicated
``"badges"`` RngTree stream, so match and every other draw are untouched.
Winning Clutch King only gives you a *chance* at Clutch Master.

Effects (schemas/badges.py): a REVERSIBLE current-ability edge (stored per
badge, subtracted back if it decays) plus a PERMANENT ceiling revision (kept ---
you proved the potential). Negative badges carry a reversible CA drag only.

Applied to EVERY org (AI parity, like dev events); the news line goes only to
the owning human. Decay is rng-free (an offseason re-check). gs.mentorships-
style no-op safety does NOT apply here --- badges fire for AI too, so the
snowball/dynasty gates must be re-run after any change.
"""

from __future__ import annotations

from esports_sim.manager import chronicle, development
from esports_sim.schemas.badges import BADGES

# Roll probabilities per source. A moment is a CHANCE, not a coronation.
P_AWARD = 0.35        # winning the linked league award
P_TITLE = 0.22        # per player on a title-winning roster (age-scaled below)
P_MATCH_FEAT = 0.30   # a monster single-map fragging game
P_CLUTCH_FEAT = 0.28  # a 1v3+ clutch in a map
P_NEG_EVENT = 0.10    # per qualifying negative dev event (injury / slump)
P_CHOKE = 0.30        # a bad personal game in a playoff/final loss

FEAT_KILLS = 28       # single-map kills that flag a fragging feat
CHOKE_RATING = 0.75   # personal rating floor for a choke in a big game

_PLAYOFF_STAGES = frozenset({
    "semi", "final", "masters_qf", "masters_sf", "masters_final",
    "champ_qf", "champ_sf", "champ_final",
})

# Award-name substring -> badge id.
_AWARD_BADGES = {
    "MVP": "superstar",
    "Top Fragger": "aim_demon",
    "Clutch Merchant": "clutch_master",
    "Rookie of the Season": "phenom",
    "Most Improved": "ascending",
}


def _team_of(gs, pid: str) -> str:
    return next((t for t in sorted(gs.teams) if pid in gs.teams[t].player_ids), "")


def _clamp(v: float) -> float:
    return round(min(99.0, max(1.0, v)), 2)


def held_ids(p) -> set[str]:
    return {b.id for b in p.badges}


def _eligible(p, bid: str) -> bool:
    return all(p.attr(a) >= mn for a, mn in BADGES[bid].get("eligible", {}).items())


def _earn(gs, tid: str, p, bid: str) -> bool:
    """Apply a badge's effect and record it. The CA deltas are stored (post-
    clamp) for exact reversion on decay; the PA revision is permanent."""
    from esports_sim.schemas.player import PlayerBadge

    b = BADGES[bid]
    applied: dict[str, float] = {}
    for attr, d in sorted(b.get("ca", {}).items()):
        cur = p.attr(attr)
        new = _clamp(cur + d)
        applied[attr] = round(new - cur, 2)
        p.attributes[attr] = new
    pa_applied = 0.0
    if b.get("pa", 0.0) or b.get("pa_skills"):
        pa_applied = development.adjust_potential(
            p, b.get("pa", 0.0), attrs=b.get("pa_skills") or None
        )
    p.badges.append(
        PlayerBadge(
            id=bid, season=gs.season, week=gs.week,
            applied=applied, pa_applied=pa_applied, last_qualified=gs.season,
        )
    )
    p.badges.sort(key=lambda x: x.id)
    verb = "earns" if b["polarity"] > 0 else "is saddled with"
    chronicle.record(
        gs, "badge", f"{p.handle} {verb} the {b['name']} badge.",
        team_id=tid, player_id=p.id,
        importance=55.0 if b["polarity"] > 0 else 45.0,
        data={"badge": bid},
    )
    if gs.is_human(tid):
        gs.push_private_news(f"{p.handle} {verb} the {b['name']} badge.", owner=tid)
    return True


def roll(gs, rng, tid: str, p, bid: str, prob: float) -> bool:
    """Roll for a badge. If already held, refresh its decay clock (re-qualified)
    and return False. Otherwise, if eligible and the roll hits, earn it. Draws
    from rng ONLY when a fresh, eligible badge is actually in play (deterministic
    given sorted iteration), so the dedicated badge stream stays stable."""
    for existing in p.badges:
        if existing.id == bid:
            existing.last_qualified = gs.season
            return False
    if not _eligible(p, bid):
        return False
    if rng.random() < prob:
        return _earn(gs, tid, p, bid)
    return False


def award_feats(gs, rng, awards) -> None:
    """Roll award-linked badges at the offseason (awards = AwardRecords)."""
    for a in awards:
        p = gs.players.get(a.player_id)
        if p is None:
            continue
        tid = _team_of(gs, a.player_id)
        for key, bid in _AWARD_BADGES.items():
            if key in a.award:
                roll(gs, rng, tid, p, bid, P_AWARD)
                break


def title_feats(gs, rng, tid: str) -> None:
    """Roll the Big-Game Player badge across a title-winning roster (the young,
    with room, more likely -- reuses the moment age scale)."""
    team = gs.teams.get(tid)
    if team is None:
        return
    for pid in sorted(team.player_ids):
        p = gs.players.get(pid)
        if p is None:
            continue
        prob = P_TITLE * (0.4 + 0.6 * development._moment_scale(p))
        roll(gs, rng, tid, p, "big_game_player", prob)


def weekly_feats(gs, rng, report, dev_events) -> None:
    """Roll match-performance badges from the week's box scores plus negative
    badges from injury/slump dev events. `rng` is the dedicated weekly badge
    stream. Every org (AI parity); news only to the owning human."""
    for fid in sorted(report.match_stats):
        fx = next((f for f in report.fixtures if f.id == fid), None)
        big_game = fx is not None and fx.stage in _PLAYOFF_STAGES
        loser = ""
        if fx is not None and fx.winner_id:
            loser = fx.team_b if fx.winner_id == fx.team_a else fx.team_a
        for stats in report.match_stats[fid]:
            for pid in sorted(stats.lines):
                p = gs.players.get(pid)
                if p is None:
                    continue
                tid = _team_of(gs, pid)
                line = stats.lines[pid]
                if line.kills >= FEAT_KILLS:
                    roll(gs, rng, tid, p, "aim_demon", P_MATCH_FEAT)
                if line.clutch_1v3 >= 1:
                    roll(gs, rng, tid, p, "clutch_master", P_CLUTCH_FEAT)
                choked = (
                    big_game
                    and loser in gs.teams
                    and pid in gs.teams[loser].player_ids
                    and line.rating <= CHOKE_RATING
                )
                if choked:
                    roll(gs, rng, tid, p, "choker", P_CHOKE)
    for ev in dev_events:
        p = gs.players.get(ev.get("player_id"))
        if p is None:
            continue
        tid = ev.get("team_id") or _team_of(gs, ev.get("player_id"))
        kind = ev.get("kind")
        if kind in ("minor_injury", "burnout"):
            roll(gs, rng, tid, p, "injury_prone", P_NEG_EVENT)
        elif kind in ("slump", "tilt_spiral"):
            roll(gs, rng, tid, p, "inconsistent", P_NEG_EVENT)


def _revert(p, pb) -> None:
    """Undo a decayed badge's REVERSIBLE current-ability edge. The permanent
    ceiling revision (pa_applied) is deliberately kept."""
    for attr, d in pb.applied.items():
        p.attributes[attr] = _clamp(p.attr(attr) - d)


def decay(gs) -> list[dict]:
    """Offseason: decay badges whose criterion is met (a celebrated skill fell
    below its floor, or the badge went stale without re-qualifying). Reverts the
    CA edge, keeps the permanent ceiling, removes the badge; chronicles + news.
    rng-free; every org."""
    out: list[dict] = []
    for tid in sorted(gs.teams):
        for p in sorted(gs.roster(tid), key=lambda q: q.id):
            keep = []
            for pb in p.badges:
                b = BADGES.get(pb.id)
                if b is None:
                    keep.append(pb)
                    continue
                da = b.get("decay_attr")
                floored = da is not None and p.attr(da) < b.get("decay_floor", 0.0)
                stale = gs.season - pb.last_qualified >= b.get("decay_seasons", 99)
                if not (floored or stale):
                    keep.append(pb)
                    continue
                _revert(p, pb)
                out.append({"team_id": tid, "player_id": p.id, "badge": pb.id})
                verb = "loses" if b["polarity"] > 0 else "sheds"
                chronicle.record(
                    gs, "badge_lost", f"{p.handle} {verb} the {b['name']} badge.",
                    team_id=tid, player_id=p.id, importance=30.0,
                    data={"badge": pb.id},
                )
                if gs.is_human(tid):
                    gs.push_private_news(
                        f"{p.handle} {verb} the {b['name']} badge.", owner=tid
                    )
            p.badges = keep
    return out
