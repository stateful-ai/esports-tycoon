"""Decision ledger: recent human decisions settled against what happened.

"Decisions settle visibly": every graded line here is DERIVED from data the
save already stores -- telemetry.action_log (the decision itself),
gs.dev_history / gs.stat_history (the weekly snapshots), gs.fixtures (played
results with per-map box-score lines) and gs.player_stats (season
aggregates). Nothing new is persisted and no RNG is drawn: this module is a
pure, deterministic reader, so hands-off sims (which record no human
actions) see an empty ledger and stay byte-identical.

Covered decision kinds:

- set_training  -> did the focused skill block move faster than a typical
                   week? (settles the same tick its training week resolves)
- set_game_plan -> did the hunted focus target underperform their season
                   form in that fixture? (settles when the fixture plays)
- sign          -> a new signing's first-weeks rating (settles a fixed
                   SIGNING_SETTLE_WEEKS after the ink dried, one-shot)
- set_lineup    -> a per-map lineup override: map W/L plus the dressed
                   five's mean rating (settles when the fixture plays)

Each settlement is one grounded ASCII sentence plus a verdict tag
(paid_off / neutral / backfired) computed from the stored numbers via the
thresholds below -- never invented. When the data is silent (no maps
played yet, the target never dressed, no baseline week to compare against)
the decision simply does not settle: silence beats invented drama.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import ActionRecord, Fixture, GameState

# How far back (in weeks) a decision may still settle, and how many rows the
# weekly inbox digest shows.
LOOKBACK_WEEKS = 3
MAX_DIGEST = 3
# A signing settles exactly this many weeks after the action -- late enough
# for a real sample, early enough to still feel like feedback. One fixed
# offset keeps the settlement one-shot and re-derivable at any later time.
SIGNING_SETTLE_WEEKS = 2

PAID_OFF = "paid_off"
NEUTRAL = "neutral"
BACKFIRED = "backfired"

# Verdict thresholds. Ratings sit on the HLTV-flavoured ~1.0-average scale
# (sim/stats.py); attributes are 0-100 with weekly training moves of a few
# tenths of a point.
_TRAIN_EDGE = 0.05  # focused-attr weekly delta vs the roster's typical week
_TARGET_EDGE = 0.08  # focus target's fixture rating vs their season form
_SIGN_GOOD = 1.05  # first-weeks rating at/above this: the signing paid off
_SIGN_BAD = 0.92  # below this: it backfired
_LINEUP_SAVE = 1.02  # a losing five that still averaged this rates neutral


def _row(
    kind: str, verdict: str, text: str, signal: float,
    season: int, week: int, subject: str,
) -> dict:
    return {
        "kind": kind,
        "verdict": verdict,
        "text": text,
        "signal": round(signal, 3),
        "season": season,
        "week": week,
        "subject": subject,
    }


def _recent_actions(
    gs: "GameState", team_id: str, season: int, week: int,
) -> list["ActionRecord"]:
    """This team's actions inside the settle window, oldest-first. The log
    is append-only chronological, so a reversed scan with an early break
    stays cheap on old saves."""
    lo = week - LOOKBACK_WEEKS
    out: list["ActionRecord"] = []
    for rec in reversed(gs.action_log):
        if rec.season < season or (rec.season == season and rec.week < lo):
            break
        if rec.season != season or rec.week > week:
            continue
        if rec.team_id != team_id:
            continue
        out.append(rec)
    out.reverse()
    return out


# ---------------------------------------------------------------------------
# Per-kind settlers


def _settle_training(
    gs: "GameState", team_id: str, season: int, week: int,
    actions: list["ActionRecord"],
) -> list[dict]:
    """Grade this week's explicit training call: mean delta of the focused
    attributes across the roster this week vs the roster's typical week
    (all prior consecutive dev-snapshot pairs)."""
    from esports_sim.manager import training

    picks = [r for r in actions if r.kind == "set_training" and r.week == week]
    if not picks:
        return []
    rec = picks[-1]  # the last call set this week is the one that applied
    if rec.params.get("delegate_to_coach") == "True":
        return []  # the coach picked the focus, not the manager
    focus = rec.params.get("focus", "")
    attrs = training._CATEGORY_ATTRS.get(focus)
    if not attrs:
        return []  # a rest week has no skill block to measure
    team = gs.teams.get(team_id)
    if team is None:
        return []

    def pair_delta(a, b) -> float | None:
        vals = [
            b.attributes[x] - a.attributes[x]
            for x in attrs
            if x in a.attributes and x in b.attributes
        ]
        return sum(vals) / len(vals) if vals else None

    this_deltas: list[float] = []
    typical_deltas: list[float] = []
    for pid in sorted(team.player_ids):
        dh = gs.dev_history.get(pid, [])
        idx = None
        for i in range(len(dh) - 1, -1, -1):
            if dh[i].season == season and dh[i].week == week:
                idx = i
                break
            if (dh[i].season, dh[i].week) < (season, week):
                break
        if idx is None or idx == 0:
            continue  # joined this week / no snapshot pair yet
        d = pair_delta(dh[idx - 1], dh[idx])
        if d is None:
            continue
        this_deltas.append(d)
        prior = [pair_delta(dh[i - 1], dh[i]) for i in range(1, idx)]
        prior = [p for p in prior if p is not None]
        if prior:
            typical_deltas.append(sum(prior) / len(prior))
    if not this_deltas or not typical_deltas:
        return []  # first measured week -- no honest baseline yet
    this_wk = sum(this_deltas) / len(this_deltas)
    typical = sum(typical_deltas) / len(typical_deltas)
    diff = this_wk - typical
    if diff >= _TRAIN_EDGE:
        verdict = PAID_OFF
    elif diff <= -_TRAIN_EDGE:
        verdict = BACKFIRED
    else:
        verdict = NEUTRAL
    text = (
        f"Training call ({focus}): focused skills moved {this_wk:+.2f} avg "
        f"this week vs {typical:+.2f} in a typical week."
    )
    return [_row(
        "training", verdict, text, min(1.0, abs(diff) / 0.15),
        season, rec.week, f"training|{focus}|{rec.week}",
    )]


def _plans_by_fixture(
    actions: list["ActionRecord"], fixtures_by_id: dict[str, "Fixture"],
) -> dict[str, "ActionRecord"]:
    """Latest surviving set_game_plan per fixture. A later clear_game_plan
    voids any pending plan (one per manager) whose fixture hadn't played
    when the clear landed -- the plan never reached the engine."""
    plans: dict[str, "ActionRecord"] = {}
    for r in actions:
        if r.kind == "set_game_plan":
            fid = r.params.get("fixture_id", "")
            if fid:
                plans[fid] = r  # a re-edit overwrites: last write wins
        elif r.kind == "clear_game_plan":
            for fid in list(plans):
                fx = fixtures_by_id.get(fid)
                if fx is None or fx.week >= r.week:
                    del plans[fid]
    return plans


def _settle_focus_targets(
    gs: "GameState", team_id: str, season: int, week: int,
    actions: list["ActionRecord"], fixtures_by_id: dict[str, "Fixture"],
) -> list[dict]:
    """Grade a game plan's focus target: their rating in that fixture vs
    their season form. Settles only the tick the fixture resolved."""
    out: list[dict] = []
    plans = _plans_by_fixture(actions, fixtures_by_id)
    for fid in sorted(plans):
        rec = plans[fid]
        pid = rec.params.get("focus_target", "")
        if not pid:
            continue
        fx = fixtures_by_id.get(fid)
        if fx is None or not fx.played or fx.week != week:
            continue
        p = gs.players.get(pid)
        if p is None:
            continue
        ratings = [
            ln.rating
            for res in fx.results
            for ln in res.lines
            if ln.player_id == pid
        ]
        if not ratings:
            continue  # the target never dressed -- nothing honest to grade
        st = gs.player_stats.get(pid)
        if st is None or st.maps < 3:
            continue  # too few season maps for an honest form line
        fixture_rating = sum(ratings) / len(ratings)
        season_form = st.rating
        diff = fixture_rating - season_form
        if diff <= -_TARGET_EDGE:
            verdict = PAID_OFF  # the hunt suppressed them below their form
        elif diff >= _TARGET_EDGE:
            verdict = BACKFIRED
        else:
            verdict = NEUTRAL
        text = (
            f"Game plan hunted {p.handle}: {fixture_rating:.2f} rating in "
            f"the series vs {season_form:.2f} season form."
        )
        out.append(_row(
            "focus_target", verdict, text, min(1.0, abs(diff) / 0.3),
            season, rec.week, f"focus|{fid}|{pid}",
        ))
    return out


def _settle_signings(
    gs: "GameState", team_id: str, season: int, week: int,
    actions: list["ActionRecord"],
) -> list[dict]:
    """Grade a signing's first weeks: map-weighted mean rating from their
    weekly stat snapshots since the signing week (inclusive -- a player
    signed before the fixture can dress the same week)."""
    out: list[dict] = []
    seen: set[str] = set()
    for rec in actions:
        if rec.kind != "sign" or rec.week != week - SIGNING_SETTLE_WEEKS:
            continue
        pid = rec.params.get("player_id", "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        p = gs.players.get(pid)
        if p is None:
            continue
        snaps = [
            s for s in gs.stat_history.get(pid, [])
            if s.season == season and rec.week <= s.week <= week
        ]
        maps = sum(s.maps for s in snaps)
        if maps == 0:
            continue  # yet to play a map -- nothing honest to grade
        mean_rating = sum(s.rating * s.maps for s in snaps) / maps
        if mean_rating >= _SIGN_GOOD:
            verdict = PAID_OFF
        elif mean_rating < _SIGN_BAD:
            verdict = BACKFIRED
        else:
            verdict = NEUTRAL
        text = (
            f"New signing {p.handle}: {mean_rating:.2f} rating across "
            f"{maps} map(s) in their first weeks."
        )
        out.append(_row(
            "signing", verdict, text, min(1.0, abs(mean_rating - 1.0) / 0.25),
            season, rec.week, f"sign|{pid}",
        ))
    return out


def _settle_lineups(
    gs: "GameState", team_id: str, season: int, week: int,
    actions: list["ActionRecord"], fixtures_by_id: dict[str, "Fixture"],
) -> list[dict]:
    """Grade a per-map lineup override: did the handpicked five win the
    map, and how did they rate? Settles only the tick the fixture
    resolved, so team membership still matches the dressed five."""
    picks: dict[tuple[str, str], "ActionRecord"] = {}
    for r in actions:
        if r.kind != "set_lineup" or r.params.get("per_map") != "True":
            continue
        fid, mid = r.params.get("fixture_id", ""), r.params.get("map_id", "")
        if fid and mid:
            picks[(fid, mid)] = r  # a re-pick overwrites: last write wins
    team = gs.teams.get(team_id)
    if team is None:
        return []
    roster_ids = set(team.player_ids)
    out: list[dict] = []
    for fid, mid in sorted(picks):
        rec = picks[(fid, mid)]
        fx = fixtures_by_id.get(fid)
        if fx is None or not fx.played or fx.week != week:
            continue
        res = next((r for r in fx.results if r.map_id == mid), None)
        if res is None:
            continue  # series ended before this map was played
        ours = [ln for ln in res.lines if ln.player_id in roster_ids]
        if not ours:
            continue
        mean_rating = sum(ln.rating for ln in ours) / len(ours)
        won = res.winner_id == team_id
        us, them = (
            (res.score_a, res.score_b)
            if fx.team_a == team_id
            else (res.score_b, res.score_a)
        )
        if won:
            verdict = PAID_OFF
        elif mean_rating >= _LINEUP_SAVE:
            verdict = NEUTRAL  # lost the map, but the five showed up
        else:
            verdict = BACKFIRED
        text = (
            f"One-map lineup call on {mid}: {'won' if won else 'lost'} "
            f"{us}-{them}, the five averaged {mean_rating:.2f}."
        )
        out.append(_row(
            "lineup", verdict, text,
            min(1.0, 0.5 + abs(mean_rating - 1.0)),
            season, rec.week, f"lineup|{fid}|{mid}",
        ))
    return out


# ---------------------------------------------------------------------------
# Entry points


def settlements(
    gs: "GameState", team_id: str, season: int, week: int,
) -> list[dict]:
    """Every settlement that lands at the end of tick (season, week) for
    this team's recent decisions, highest-signal first. Pure derived read:
    calling it twice (or on a reloaded save) returns the same rows."""
    if team_id not in gs.teams:
        return []
    actions = _recent_actions(gs, team_id, season, week)
    if not actions:
        return []
    rows = _settle_training(gs, team_id, season, week, actions)
    rows += _settle_signings(gs, team_id, season, week, actions)
    if any(r.kind in ("set_game_plan", "clear_game_plan", "set_lineup")
           for r in actions):
        fixtures_by_id = {f.id: f for f in gs.fixtures}
        rows += _settle_focus_targets(
            gs, team_id, season, week, actions, fixtures_by_id
        )
        rows += _settle_lineups(
            gs, team_id, season, week, actions, fixtures_by_id
        )
    rows.sort(key=lambda r: (-r["signal"], r["kind"], r["subject"]))
    return rows


def latest_settlements(gs: "GameState", team_id: str) -> list[dict]:
    """The most recently resolved week's settlements, for the dashboard
    card. advance_week rolls the counter after settling, so the settled
    week is week-1; week 1 (or a fresh season) has nothing to grade yet."""
    if gs.week < 2:
        return []
    return settlements(gs, team_id, gs.season, gs.week - 1)
