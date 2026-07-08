"""Narrative v0 — deterministic templated news from real match data.

Grounding rule (from docs/salvage): every fact in a rendered string comes
straight from GameState / MatchStats fields. Templates vary phrasing, never
facts. Variant choice is seeded from stable string parts (salvaged
templated-content pattern), so the same week renders the same copy.

Tone (docs/salvage/tone_and_cast_lock.md): dry, understated, no hype.
"""

from __future__ import annotations

import random

from esports_sim.manager.state import AwardRecord, GameState

_MIN_AWARD_MAPS = 6


def _rng(*parts) -> random.Random:
    return random.Random("|".join(str(p) for p in parts))


def _pick(rng: random.Random, variants: list[str], **facts) -> str:
    return rng.choice(variants).format(**facts)


# ---------------------------------------------------------------------------
# Weekly news


def weekly_news(gs: GameState, report, week_kills: dict[str, int]) -> None:
    """Called at the end of advance_week, before the week increments.
    `week_kills` is this week's per-player kill delta (for milestones)."""
    for f in report.fixtures:
        if not f.played or not f.results:
            continue
        is_user = gs.user_team_id in (f.team_a, f.team_b)
        stats_list = report.match_stats.get(f.id, [])
        if is_user:
            _user_recap(gs, f, stats_list)
        else:
            _league_line(gs, f, stats_list)
    _milestones(gs, week_kills)


def _series_score(f) -> str:
    if f.best_of > 1:
        a, b = f.map_score
        return f"{a}-{b}"
    r = f.results[0]
    return f"{r.score_a}-{r.score_b}"


def _star_line(stats_list) -> tuple[str, float, int] | None:
    """(player_id, best map rating, kills that map) for the series' top line."""
    best = None
    for stats in stats_list:
        for pid, line in stats.lines.items():
            if best is None or line.rating > best[1]:
                best = (pid, line.rating, line.kills)
    return best


# ---------------------------------------------------------------------------
# Head-to-head history (this season only — past seasons' fixtures are
# discarded at rollover, see campaign._run_offseason).


def _reigning_champion_id(gs: GameState) -> str | None:
    """The team_id of the most recently crowned champion, or None if no
    season has finished yet. `gs.champions` only ever records winners (never
    runners-up or past finals), so this is the one piece of cross-season
    history grounding can lean on."""
    return gs.champions[-1].team_id if gs.champions else None


def _ordinal(n: int) -> str:
    """Small-int ordinal words for streak callbacks ("third straight loss").
    Falls back to a numeric ordinal (11th, 23rd, ...) past the named range —
    real seasons rarely see a streak beyond a handful of meetings, but this
    keeps the function total instead of raising."""
    words = {
        1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
        6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    }
    if n in words:
        return words[n]
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def head_to_head(gs: GameState, team_a: str, team_b: str) -> dict:
    """Pure summary of every played meeting between `team_a` and `team_b`
    this season, plus the one cross-season fact grounding allows (the
    reigning champion's id). No RNG, no ordering dependency on which side of
    a Fixture each team landed on — meetings are found by set membership and
    sorted by week so the result is stable regardless of call order.

    Only `gs.fixtures` is consulted: past seasons' fixtures are replaced
    wholesale at rollover (`build_regular_season` overwrites the list), so
    every played fixture found here is from the current season by
    construction — there is nothing to invent and nothing older to filter
    out.

    Returns a dict with:
      meetings: number of played fixtures between the two teams so far.
      wins_a / wins_b: series wins for each side among those meetings.
      last_meeting_week / last_winner_id: the most recent meeting.
      streak_winner_id / streak_len: the team on a current unbroken run of
        wins against the other, and how long that run is (0 / None if the
        two haven't met, or if the last two meetings split).
      revenge / revenge_week: True + the earlier week if the most recent
        meeting's winner differs from the one before it — i.e. the last
        result flipped the previous one.
      reigning_champion_id: latest ChampionRecord.team_id, or None.
    """
    meetings = sorted(
        (
            f for f in gs.fixtures
            if f.played and f.winner_id is not None
            and {f.team_a, f.team_b} == {team_a, team_b}
        ),
        key=lambda f: (f.week, f.id),
    )

    wins_a = sum(1 for f in meetings if f.winner_id == team_a)
    wins_b = sum(1 for f in meetings if f.winner_id == team_b)

    last_meeting_week = meetings[-1].week if meetings else None
    last_winner_id = meetings[-1].winner_id if meetings else None

    streak_winner_id: str | None = None
    streak_len = 0
    for f in reversed(meetings):
        if streak_winner_id is None:
            streak_winner_id = f.winner_id
            streak_len = 1
        elif f.winner_id == streak_winner_id:
            streak_len += 1
        else:
            break

    revenge = False
    revenge_week: int | None = None
    if len(meetings) >= 2:
        prev = meetings[-2]
        if prev.winner_id != last_winner_id:
            revenge = True
            revenge_week = prev.week

    return {
        "meetings": len(meetings),
        "wins_a": wins_a,
        "wins_b": wins_b,
        "last_meeting_week": last_meeting_week,
        "last_winner_id": last_winner_id,
        "streak_winner_id": streak_winner_id,
        "streak_len": streak_len,
        "revenge": revenge,
        "revenge_week": revenge_week,
        "reigning_champion_id": _reigning_champion_id(gs),
    }


def _h2h_callback(
    rng: random.Random, h2h: dict, user_team_id: str, opp_id: str, opp: str, won: bool
) -> str:
    """One optional trailing sentence grounded in `h2h`, chosen by priority:
    a live streak (>= 2) beats revenge beats a reigning-champions upset.
    Returns "" when nothing is notable — silence beats filler."""
    if h2h["streak_len"] >= 2 and h2h["streak_winner_id"] == opp_id:
        return " " + _pick(
            rng,
            [
                "That's the {n} straight loss to {opp} this season.",
                "{opp} have {n} straight over them now.",
            ],
            n=_ordinal(h2h["streak_len"]), opp=opp,
        )
    if h2h["streak_len"] >= 2 and h2h["streak_winner_id"] == user_team_id:
        return " " + _pick(
            rng,
            [
                "That's the {n} straight win over {opp} this season.",
                "{n} straight over {opp} now.",
            ],
            n=_ordinal(h2h["streak_len"]), opp=opp,
        )
    if h2h["revenge"]:
        return " " + _pick(
            rng,
            [
                "Flips the result from week {w}.",
                "That reverses the week {w} meeting.",
            ],
            w=h2h["revenge_week"],
        )
    if won and h2h["reigning_champion_id"] == opp_id:
        return " " + _pick(
            rng,
            [
                "And it came against the reigning champions.",
                "That's a scalp against the reigning champions, too.",
            ],
        )
    return ""


def _user_recap(gs: GameState, f, stats_list) -> None:
    won = f.winner_id == gs.user_team_id
    opp_id = f.team_b if f.team_a == gs.user_team_id else f.team_a
    opp = gs.teams[opp_id].name
    score = _series_score(f)
    rng = _rng(gs.seed, gs.season, gs.week, f.id, "recap")

    star = _star_line(stats_list)
    star_txt = ""
    if star is not None:
        pid, rating, kills = star
        p = gs.players.get(pid)
        if p is not None:
            star_txt = _pick(
                rng,
                [
                    " {h} finished at {r:.2f}.",
                    " {h} put up {k} kills ({r:.2f}).",
                    " Top rating: {h}, {r:.2f}.",
                ],
                h=p.handle, r=rating, k=kills,
            )

    maps_txt = ", ".join(r.map_id for r in f.results)
    if won:
        msg = _pick(
            rng,
            [
                "{score} over {opp} on {maps}.{star}",
                "Business as usual: {opp} dealt with, {score}.{star}",
                "A win against {opp} ({score}).{star}",
            ],
            score=score, opp=opp, maps=maps_txt, star=star_txt,
        )
    else:
        msg = _pick(
            rng,
            [
                "{score} loss to {opp} on {maps}.{star}",
                "{opp} had answers. {score}.{star}",
                "Dropped the series to {opp}, {score}.{star}",
            ],
            score=score, opp=opp, maps=maps_txt, star=star_txt,
        )
    h2h = head_to_head(gs, gs.user_team_id, opp_id)
    msg += _h2h_callback(rng, h2h, gs.user_team_id, opp_id, opp, won)
    if f.stage != "regular":
        msg = f"[{f.stage.upper()}] " + msg
    gs.push_news(msg)


def _league_line(gs: GameState, f, stats_list) -> None:
    """One line for a notable non-user result: upsets and playoff results."""
    assert f.winner_id is not None
    loser_id = f.team_b if f.winner_id == f.team_a else f.team_a
    w, l = gs.teams[f.winner_id], gs.teams[loser_id]
    upset = (
        w.world_rank is not None
        and l.world_rank is not None
        and w.world_rank - l.world_rank >= 3
    )
    if not (upset or f.stage != "regular"):
        return
    rng = _rng(gs.seed, gs.season, gs.week, f.id, "league")
    score = _series_score(f)
    if upset:
        msg = _pick(
            rng,
            [
                "Upset: #{wr} {w} take down #{lr} {l}, {score}.",
                "#{lr} {l} stumble against #{wr} {w} ({score}).",
            ],
            w=w.name, l=l.name, wr=w.world_rank, lr=l.world_rank, score=score,
        )
        if _reigning_champion_id(gs) == l.id:
            msg += " " + _pick(
                rng,
                [
                    "Beat the reigning champions, too.",
                    "The reigning champions, no less.",
                ],
            )
    else:
        msg = f"[{f.stage.upper()}] {w.name} beat {l.name}, {score}."
    gs.push_news(msg)


def _milestones(gs: GameState, week_kills: dict[str, int]) -> None:
    for pid in sorted(week_kills):
        st = gs.player_stats.get(pid)
        p = gs.players.get(pid)
        if st is None or p is None:
            continue
        for bar in (100, 200, 300):
            # Aggregation already ran, so st.kills includes this week.
            if st.kills >= bar and st.kills - week_kills[pid] < bar:
                team = next(
                    (t.name for t in gs.teams.values() if pid in t.player_ids),
                    "free agency",
                )
                gs.push_news(f"{p.handle} ({team}) passes {bar} kills this season.")


# ---------------------------------------------------------------------------
# Season awards


def season_awards(gs: GameState) -> list[AwardRecord]:
    """Computed at season end from season aggregates. Grounded by
    construction — every value comes from the stat line it cites."""

    def team_of(pid: str) -> str:
        return next(
            (t.name for t in gs.teams.values() if pid in t.player_ids), "—"
        )

    def tier_of(pid: str) -> int:
        return next(
            (t.tier for t in gs.teams.values() if pid in t.player_ids), 1
        )

    # Main awards are tier-1 only — Challengers numbers come against
    # Challengers competition and get their own award below.
    eligible = {
        pid: st
        for pid, st in gs.player_stats.items()
        if st.maps >= _MIN_AWARD_MAPS and pid in gs.players and tier_of(pid) == 1
    }
    out: list[AwardRecord] = []

    def add(award: str, pid: str, value: str) -> None:
        p = gs.players[pid]
        rec = AwardRecord(
            season=gs.season, award=award, player_id=pid,
            handle=p.handle, team_name=team_of(pid), value=value,
        )
        out.append(rec)
        gs.push_news(f"{award}: {p.handle} ({rec.team_name}) — {value}.")

    if eligible:
        mvp = max(eligible, key=lambda pid: (eligible[pid].rating, pid))
        add("Season MVP", mvp,
            f"{eligible[mvp].rating:.2f} rating over {eligible[mvp].maps} maps")

        frag = max(eligible, key=lambda pid: (eligible[pid].kills, pid))
        add("Top Fragger", frag, f"{eligible[frag].kills} kills")

        opener = max(eligible, key=lambda pid: (eligible[pid].first_kills, pid))
        add("Opening King", opener, f"{eligible[opener].first_kills} opening kills")

        rookies = {pid: st for pid, st in eligible.items() if gs.players[pid].age <= 19}
        if rookies:
            rook = max(rookies, key=lambda pid: (rookies[pid].rating, pid))
            add("Rookie of the Season", rook,
                f"{rookies[rook].rating:.2f} rating at age {gs.players[rook].age}")

    # Challengers MVP: the tier-2 name every tier-1 scout now knows.
    t2_eligible = {
        pid: st
        for pid, st in gs.player_stats.items()
        if st.maps >= _MIN_AWARD_MAPS and pid in gs.players and tier_of(pid) == 2
    }
    if t2_eligible:
        t2mvp = max(t2_eligible, key=lambda pid: (t2_eligible[pid].rating, pid))
        add(
            "Challengers MVP", t2mvp,
            f"{t2_eligible[t2mvp].rating:.2f} rating, age {gs.players[t2mvp].age}",
        )

    gs.awards.extend(out)
    del gs.awards[:-24]
    return out
