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

    eligible = {
        pid: st
        for pid, st in gs.player_stats.items()
        if st.maps >= _MIN_AWARD_MAPS and pid in gs.players
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

    gs.awards.extend(out)
    del gs.awards[:-24]
    return out
