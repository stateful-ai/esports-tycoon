"""Social media layer: follower counts and a weekly feed.

Players (and orgs, via fan_count) carry an audience. Followers move on
real outcomes — results, big stat lines, viral moments from the dev-event
system — and the feed renders those same facts as posts. Grounded like
the narrative layer: every post resolves to something that actually
happened this week; likes are flavor, follower counts are state.

Effects flow back into the game two ways: milestone crossings nudge
confidence (a player watching their number go up believes it), and the
roster's combined reach feeds sponsor marketability (see sponsors.py).

Determinism: seeded baselines come from blake2 of stable ids; the weekly
tick draws from a dedicated campaign rng stream (label "social"), so this
system can be extended without shifting any other subsystem's draws.
"""

from __future__ import annotations

import hashlib

from esports_sim.manager import development

FEED_CAP = 120
MILESTONES = [
    10_000, 25_000, 50_000, 100_000, 250_000,
    500_000, 1_000_000, 2_000_000, 5_000_000,
]

_FLAVOR_POSTS = [
    "Lock in.",
    "New week. Back to work.",
    "Trust the process.",
    "Scrims felt different today.",
    "Sleep, grind, repeat.",
    "We're not done yet.",
]


def _h(*parts) -> str:
    b = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8)
    return b.hexdigest()


def _hint(*parts) -> int:
    b = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8)
    return int.from_bytes(b.digest(), "big")


def _baseline(seed: int, p) -> int:
    """Stable starting audience: exponential in ability (stars are famous,
    journeymen aren't), jittered per player, discounted for teenagers
    nobody has heard of yet."""
    ca = development.overall(p)
    base = 400.0 * (1.09 ** ca)
    jitter = 0.6 + (_hint(seed, p.id, "fseed") % 1000) / 1000.0  # 0.6..1.6
    if p.age <= 19:
        base *= 0.5
    return max(500, int(base * jitter))


def seed_followers(gs) -> None:
    """Give every unseeded player (followers == 0) a stable baseline.
    Called at campaign start and each week (rookies/generated players
    arrive mid-season); already-seeded players are never touched."""
    for pid in sorted(gs.players):
        p = gs.players[pid]
        if p.followers <= 0:
            p.followers = _baseline(gs.seed, p)


def roster_reach(gs, team_id: str) -> int:
    return sum(p.followers for p in gs.roster(team_id))


def _post(
    gs, season: int, week: int, kind: str, author_kind: str,
    author_id: str, author: str, text: str, likes: int, salt: str = "",
) -> None:
    from esports_sim.manager.state import SocialPost

    gs.social_feed.append(
        SocialPost(
            id=_h(season, week, kind, author_id or author, salt),
            season=season,
            week=week,
            author_kind=author_kind,
            author_id=author_id,
            author=author,
            text=text,
            likes=likes,
            kind=kind,
        )
    )


def _likes(rng, followers: int) -> int:
    return max(3, int(followers * float(rng.uniform(0.02, 0.08))))


def _grow(p, pct: float) -> None:
    p.followers = max(500, int(p.followers * (1.0 + pct / 100.0)))


def weekly_tick(
    gs, report, dev_events: list[dict], rng,
    match_team_of: dict[str, str] | None = None,
    mental_events: list[dict] | None = None,
) -> None:
    """One week of the social layer: seed newcomers, move follower counts
    on the week's real outcomes, write the feed — then fold the week into
    community sentiment and let it feed back (see _sentiment_tick). New
    draws only ever land at the END of the stream (repo convention: the
    'social' rng label is append-only, so existing draws never shift).

    `match_team_of` (player -> the team they DRESSED for this week) pins
    result bumps to the match-time side: contracts expire and transfers
    resolve before this runs, so recomputing membership from the live
    rosters would credit a same-tick mover with the wrong team's result."""
    seed_followers(gs)
    mental_events = mental_events or []
    season, week = report.season, report.week
    before = {pid: gs.players[pid].followers for pid in sorted(gs.players)}

    # -- weekly performance digest (from the transient match stats) --------
    perf: dict[str, dict] = {}  # pid -> {maps, rating_sum, aces, clutches}
    for fid in sorted(report.match_stats):
        for stats in report.match_stats[fid]:
            n_rounds = max(len(stats.rounds), 1)
            for pid, line in sorted(stats.lines.items()):
                if pid not in gs.players:
                    continue
                d = perf.setdefault(
                    pid, {"maps": 0, "rating_sum": 0.0, "aces": 0, "clutches": 0}
                )
                d["maps"] += 1
                d["rating_sum"] += line.rating
                d["aces"] += line.aces
                d["clutches"] += line.clutches

    won_series: dict[str, bool] = {}
    for f in report.fixtures:
        if f.played and f.winner_id is not None:
            won_series[f.winner_id] = True
            won_series[f.team_b if f.winner_id == f.team_a else f.team_a] = False

    # -- follower movement --------------------------------------------------
    for pid in sorted(gs.players):
        p = gs.players[pid]
        _grow(p, 0.15)  # ambient drift: the scene slowly grows
        d = perf.get(pid)
        if d is None:
            continue
        tid = (match_team_of or {}).get(pid) or next(
            (t.id for t in gs.teams.values() if pid in t.player_ids), None
        )
        if tid is not None and tid in won_series:
            _grow(p, 1.0 if won_series[tid] else 0.3)
        rating = d["rating_sum"] / max(d["maps"], 1)
        if rating >= 1.2:
            _grow(p, 1.5)
        if d["aces"]:
            _grow(p, 2.0 * min(d["aces"], 2))
        if d["clutches"]:
            _grow(p, 1.0 * min(d["clutches"], 2))

    # Dev-event amplifiers: the clip that went viral, the spat with fans.
    for ev in dev_events:
        p = gs.players.get(ev["player_id"])
        if p is None:
            continue
        if ev["kind"] == "viral_clip":
            _grow(p, 10.0 + float(rng.uniform(0.0, 15.0)))
            _post(
                gs, season, week, "viral", "media", p.id, "ClipHub",
                f"That {p.handle} clip is everywhere.",
                _likes(rng, p.followers * 3), salt=p.id,
            )
        elif ev["kind"] == "drama":
            _grow(p, 4.0)  # drama sells
            _post(
                gs, season, week, "drama", "player", p.id, p.handle,
                "I said what I said.", _likes(rng, p.followers * 2), salt=p.id,
            )

    # -- posts ----------------------------------------------------------------
    # Player of the week (min 1 map; deterministic tiebreak by pid).
    if perf:
        best = max(
            sorted(perf),
            key=lambda pid: (perf[pid]["rating_sum"] / max(perf[pid]["maps"], 1), pid),
        )
        bp = gs.players[best]
        b_rating = perf[best]["rating_sum"] / max(perf[best]["maps"], 1)
        _post(
            gs, season, week, "hype", "media", bp.id, "VCT Wire",
            f"Player of the Week: {bp.handle} — {b_rating:.2f} rating "
            f"across {perf[best]['maps']} map"
            f"{'s' if perf[best]['maps'] != 1 else ''}.",
            _likes(rng, bp.followers * 2),
        )

    # Human orgs post their result (dry, team-account voice).
    for tid in sorted(gs.human_team_ids):
        f = next((x for x in report.fixtures if tid in (x.team_a, x.team_b)), None)
        if f is None or not f.played:
            continue
        opp = f.team_b if f.team_a == tid else f.team_a
        a, b = f.map_score
        us, them = (a, b) if f.team_a == tid else (b, a)
        team = gs.teams[tid]
        text = (
            f"GGs @{gs.teams[opp].tag} — {us}-{them}."
            if f.winner_id == tid
            else f"Not our week. {us}-{them} vs {gs.teams[opp].tag}. Back to the lab."
        )
        _post(
            gs, season, week, "result", "team", tid, team.tag, text,
            _likes(rng, max(team.fan_count, 1_000)), salt=tid,
        )

    # Milestones: crossing a landmark is worth a post and a little belief.
    for pid in sorted(gs.players):
        p = gs.players[pid]
        prev = before.get(pid, p.followers)
        crossed = [m for m in MILESTONES if prev < m <= p.followers]
        if crossed:
            m = crossed[-1]
            label = f"{m // 1_000_000}M" if m >= 1_000_000 else f"{m // 1_000}K"
            p.confidence = round(min(95.0, p.confidence + 2.0), 1)
            _post(
                gs, season, week, "milestone", "player", p.id, p.handle,
                f"{label}. Thank you all, honestly.", _likes(rng, p.followers),
                salt=str(m),
            )

    # One flavor post from a big account keeps the feed alive in quiet weeks.
    big = sorted(gs.players, key=lambda pid: (-gs.players[pid].followers, pid))[:12]
    if big:
        poster = gs.players[big[int(rng.integers(0, len(big)))]]
        _post(
            gs, season, week, "hype", "player", poster.id, poster.handle,
            _FLAVOR_POSTS[int(rng.integers(0, len(_FLAVOR_POSTS)))],
            _likes(rng, poster.followers),
        )

    # -- appended feed beats (new draws stay at the END of the stream) -----
    # Mental-momentum texture: heaters get hyped, spirals get picked at.
    for ev in mental_events:
        p = gs.players.get(ev["player_id"])
        if p is None:
            continue
        if ev["kind"] == "heater":
            _grow(p, 2.0)
            _post(
                gs, season, week, "hype", "media", p.id, "VCT Wire",
                f"{p.handle} cannot miss right now.",
                _likes(rng, p.followers * 2), salt=p.id,
            )
        elif ev["kind"] == "tilt_spiral":
            _post(
                gs, season, week, "drama", "media", p.id, "VCT Wire",
                f"What has happened to {p.handle}?",
                _likes(rng, p.followers), salt=p.id,
            )

    # A shipped balance patch is the week's other story.
    if gs.patch_history:
        note = gs.patch_history[-1]
        if note.season == season and note.week == week and note.lines:
            _post(
                gs, season, week, "hype", "media", "", "PatchWatch",
                f"Patch {note.version} is live: {note.lines[0]}.",
                _likes(rng, 400_000), salt=note.version,
            )

    # -- community sentiment ------------------------------------------------
    _sentiment_tick(gs, report, dev_events, mental_events, rng)

    del gs.social_feed[:-FEED_CAP]


# ---------------------------------------------------------------------------
# Community sentiment: the crowd's mood about each org, fed by the same
# real outcomes as the feed, and fed BACK into the game — players read
# their mentions (confidence/morale), and brands read the room (sponsor
# marketability + relations, see sponsors.py). Stored on GameState so the
# one-week lag to the sponsor tick is deterministic.

SENT_PULL = 0.30  # how fast sentiment chases the week's target
SENT_DEADZONE = 8.0  # |sentiment-50| below this doesn't move players
SENT_CONF_SPAN = 1.5  # confidence points/week at sentiment 0/100
SENT_MORALE_SPAN = 1.2


def _clamp_conf(v: float) -> float:
    return round(min(95.0, max(5.0, v)), 1)


def _sentiment_tick(
    gs, report, dev_events: list[dict], mental_events: list[dict], rng
) -> None:
    """Move each org's sentiment toward this week's target (rng-free), let
    extremes touch the roster's heads, and post when a fanbase flips. The
    target construction is bounded, so sentiment can't run away — a team
    that wins every week converges near 60, not 100."""
    won_series: dict[str, bool] = {}
    stakes: dict[str, float] = {}
    for f in report.fixtures:
        if f.played and f.winner_id is not None:
            loser = f.team_b if f.winner_id == f.team_a else f.team_a
            won_series[f.winner_id] = True
            won_series[loser] = False
            big = 1.5 if f.stage != "regular" else 1.0
            stakes[f.winner_id] = big
            stakes[loser] = big

    drama_by: dict[str, float] = {}
    for ev in dev_events:
        tid = ev["team_id"]
        if ev["kind"] == "drama":
            drama_by[tid] = drama_by.get(tid, 0.0) - 6.0
        elif ev["kind"] == "viral_clip":
            drama_by[tid] = drama_by.get(tid, 0.0) + 4.0
    for ev in mental_events:
        tid = ev["team_id"]
        if ev["kind"] == "heater":
            drama_by[tid] = drama_by.get(tid, 0.0) + 2.0
        elif ev["kind"] == "tilt_spiral":
            drama_by[tid] = drama_by.get(tid, 0.0) - 3.0

    before: dict[str, float] = {}
    for tid in sorted(gs.teams):
        drivers = 0.0
        if tid in won_series:
            drivers += (9.0 if won_series[tid] else -8.0) * stakes.get(tid, 1.0)
        drivers += drama_by.get(tid, 0.0)
        target = 50.0 + max(-30.0, min(30.0, drivers))
        cur = gs.team_sentiment.get(tid, 50.0)
        before[tid] = cur
        gs.team_sentiment[tid] = round(
            min(100.0, max(0.0, cur + (target - cur) * SENT_PULL)), 1
        )

    # Feedback: players read their mentions. Small and dead-zoned — the
    # weekly confidence regression (training.py) is the counterweight that
    # keeps this from snowballing (verified by the snowball gate).
    for tid in sorted(gs.teams):
        scale = (gs.team_sentiment[tid] - 50.0) / 50.0
        if abs(scale) * 50.0 < SENT_DEADZONE:
            continue
        for p in gs.roster(tid):
            p.confidence = _clamp_conf(p.confidence + SENT_CONF_SPAN * scale)
            p.morale = round(
                min(100.0, max(0.0, p.morale + SENT_MORALE_SPAN * scale)), 1
            )

    # A fanbase flipping to euphoric/toxic is a story (crossing posts only,
    # like follower milestones — the feed never repeats a standing mood).
    for tid in sorted(gs.teams):
        cur, prev = gs.team_sentiment[tid], before[tid]
        team = gs.teams[tid]
        if prev < 70.0 <= cur:
            _post(
                gs, report.season, report.week, "hype", "media", tid, "VCT Wire",
                f"{team.name} fans are ALL-IN right now.",
                _likes(rng, max(team.fan_count, 2_000)), salt=tid,
            )
        elif prev > 30.0 >= cur:
            _post(
                gs, report.season, report.week, "drama", "media", tid, "VCT Wire",
                f"The replies under every {team.name} post are getting ugly.",
                _likes(rng, max(team.fan_count, 2_000)), salt=tid,
            )
