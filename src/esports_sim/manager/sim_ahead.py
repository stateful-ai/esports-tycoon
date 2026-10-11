"""Sim ahead: batch the weekly advance until something needs the manager.

`advance_until` repeatedly runs the NORMAL weekly tick (`campaign.advance_week`,
under whatever delegation policies are already set) and stops the moment one of
the data-driven TRIGGERS fires — a playoff-stage fixture up this week, a
starter's contract running down, an incoming bid for a starter, board patience
wearing thin, finances heading for the insolvency floor, a pending flavor/media
decision, or the season reaching the offseason. Triggers are evaluated BEFORE
each advance, so the loop never sims past a decision point.

Triggers come in two strengths. HARD triggers gate every tick including the
first — things the manager must not be simmed past (a playoff-stage fixture
this week, a pending decision, the offseason): if one fires immediately the
batch returns (0, reason) without ticking at all. ADVISORY triggers describe
standing situations the manager may deliberately be riding out (an expiring
starter deal, an open bid, thin patience, red books — an opening-world roster
can legitimately START with a short contract): they stop the batch but are
skipped before the first tick, so a press always makes at least one week of
progress rather than being pinned at zero for weeks on end.

Determinism: this is pure orchestration — no new rng streams, no new persisted
state. A batch of N weeks is byte-identical to N manual advances plus the same
action_log records the web layer would have written (one "sim_ahead" record for
the button press itself, then one "advance" per ticked week — it is a
human-initiated batch, so it IS logged, unlike AI moves). Two same-seed runs of
the same call produce byte-identical GameState.

The optional `before_week`/`after_week` callbacks exist for the serving layer's
side effects (pre-tick standings capture, review-corpus appends, autosave) and
must never mutate GameState. Hands-off sims (--auto, the gates) never call this
module, so it is an exact no-op for them.
"""

from __future__ import annotations

from esports_sim.labels import humanize_identifier

from typing import TYPE_CHECKING, Callable, NamedTuple, Sequence

from esports_sim.manager import (
    campaign,
    career,
    economy,
    flavor_events,
    market,
    media_events,
    staff,
    telemetry,
)

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState
    from esports_sim.registry import GameData

# Endpoint default and hard clamp for one button press.
DEFAULT_MAX_WEEKS = 4
MAX_WEEKS_CAP = 12

# A starter's deal inside this window is a renewal decision, not background
# noise (market.tick_contracts starts agitating at CONTRACT_PRESSURE_WEEKS=8;
# we stop a little later so short sims aren't permanently blocked).
CONTRACT_HORIZON_WEEKS = 6
# Legacy-mode board patience at/below this is a warning worth stopping for
# (career.MIDSEASON_FLOOR = 5 is the sack itself — far too late to interrupt).
BOARD_PATIENCE_BAR = 35.0
# Projected weeks until the balance crosses economy.INSOLVENCY_FLOOR at the
# current run rate; at/below this the books need a manager, not autopilot.
INSOLVENCY_RUNWAY_WEEKS = 4


class Trigger(NamedTuple):
    """One reason to hand the wheel back. `check(gs, team_id) -> bool` is a
    pure read (acting is bound to team_id before evaluation); `label` is the
    ASCII, toast-ready phrasing the web layer serves alongside the slug.
    `hard` triggers gate every tick including the first; advisory ones are
    skipped until at least one week has advanced (see module docstring)."""

    slug: str
    label: str
    check: Callable[["GameState", str], bool]
    hard: bool = False


def _decision_pending(gs: "GameState", tid: str) -> bool:
    # These two block a manual advance with a 409, so the batch must stop too.
    return (
        flavor_events.pending_for(gs, tid) is not None
        or media_events.pending_for(gs, tid) is not None
    )


def _job_market(gs: "GameState", tid: str) -> bool:
    # Legacy mode: a dismissed seat must accept a post before the world moves.
    return bool(career.blocked_seats(gs))


def _season_rollover(gs: "GameState", tid: str) -> bool:
    # The next tick would run the whole offseason — that's the manager's.
    return gs.phase == "offseason"


def _big_match(gs: "GameState", tid: str) -> bool:
    f = gs.team_fixture(tid)
    return (
        f is not None and not f.played and f.tier == 1 and f.stage != "regular"
    )


def _starter_contract(gs: "GameState", tid: str) -> bool:
    for pid in campaign.default_five(gs, tid):
        p = gs.players.get(pid)
        if p is not None and 0 < p.contract_weeks_left <= CONTRACT_HORIZON_WEEKS:
            return True
    return False


def _starter_bid(gs: "GameState", tid: str) -> bool:
    starters = set(campaign.default_five(gs, tid))
    return any(
        o.from_team == tid
        and o.player_id in starters
        and o.expires_week >= gs.week
        for o in gs.transfer_offers
    )


def _board_warning(gs: "GameState", tid: str) -> bool:
    seat = next(
        (gs.managers[m] for m in sorted(gs.managers) if gs.managers[m].team_id == tid),
        None,
    )
    return (
        seat is not None
        and seat.contract is not None
        and seat.contract.patience <= BOARD_PATIENCE_BAR
    )


def _insolvency_risk(gs: "GameState", tid: str) -> bool:
    if gs.teams[tid].balance <= economy.INSOLVENCY_FLOOR:
        return True
    # weekly_breakdown/weeks_until_insolvent read the acting org (bound by
    # stop_reason before any check runs).
    runway = economy.weeks_until_insolvent(gs, staff.weekly_cost(gs))
    return runway is not None and runway <= INSOLVENCY_RUNWAY_WEEKS


# Ordered: the first trigger that fires names the stop, so the hard blockers
# (things a manual advance would refuse or the manager must not sim past)
# outrank the advisories.
TRIGGERS: tuple[Trigger, ...] = (
    Trigger("decision_pending", "a decision is waiting in Needs You on the Dashboard", _decision_pending, hard=True),
    Trigger("job_market", "a manager must accept a job offer first", _job_market, hard=True),
    Trigger("season_rollover", "the season has reached the offseason", _season_rollover, hard=True),
    Trigger("big_match", "a playoff-stage match is up this week", _big_match, hard=True),
    Trigger("transfer_offer", "a club is bidding for one of your starters", _starter_bid),
    Trigger(
        "contract_expiry",
        f"a starter's contract runs out inside {CONTRACT_HORIZON_WEEKS} weeks",
        _starter_contract,
    ),
    Trigger("board_warning", "the board's patience is wearing thin", _board_warning),
    Trigger("insolvency_risk", "finances are heading for the insolvency floor", _insolvency_risk),
)

_LABELS: dict[str, str] = {t.slug: t.label for t in TRIGGERS}
# Not a Trigger (it's the per-week advance guard), but it needs a toast too.
_LABELS["roster_short"] = "the roster is under five players"


def label_for(slug: str | None) -> str | None:
    """Toast-ready ASCII text for a stop-reason slug (None passes through)."""
    return None if slug is None else _LABELS.get(slug, humanize_identifier(slug))


def stop_reason(
    gs: "GameState",
    team_id: str,
    triggers: Sequence[Trigger] | None = None,
    *,
    include_soft: bool = True,
) -> str | None:
    """First firing trigger's slug for this team, or None. Binds the acting
    manager to `team_id` (checks like the insolvency runway read the acting
    org); a pure read otherwise. `include_soft=False` restricts the sweep to
    the hard triggers (the loop's before-first-tick gate)."""
    gs.set_acting(team_id)
    for t in TRIGGERS if triggers is None else triggers:
        if not include_soft and not t.hard:
            continue
        if t.check(gs, team_id):
            return t.slug
    return None


def advance_until(
    gs: "GameState",
    gd: "GameData",
    *,
    team_id: str | None = None,
    max_weeks: int = DEFAULT_MAX_WEEKS,
    triggers: Sequence[Trigger] | None = None,
    source: str = "web",
    events_out: dict[str, list[list]] | None = None,
    before_week: Callable[["GameState"], None] | None = None,
    after_week: Callable[..., None] | None = None,
) -> tuple[int, str | None]:
    """Advance up to `max_weeks` normal weekly ticks for the human on
    `team_id` (default: the acting manager), stopping BEFORE any week whose
    pre-state fires a trigger (hard triggers gate every tick, advisory ones
    only after the first) or fails the roster-size guard. Returns
    (weeks_advanced, stop_reason) — stop_reason is None only when the cap
    was the stopper and nothing needs attention afterwards either.

    Records the button press itself ("sim_ahead") plus the same one
    "advance" record per ticked week that a manual advance writes, so
    seed + action_log still fully determines the career. `events_out` is
    cleared before every tick — like the web layer's replay buffer it only
    ever holds the LAST advanced week's match logs."""
    tid = team_id or gs.acting_team_id
    max_weeks = max(1, min(int(max_weeks), MAX_WEEKS_CAP))
    telemetry.record_action(
        gs, "sim_ahead", {"max_weeks": max_weeks}, team_id=tid, source=source
    )
    weeks = 0
    for _ in range(max_weeks):
        # Advisory triggers only bite once the batch has made progress —
        # before the first tick only the hard gates can stop it (see the
        # module docstring for why).
        reason = stop_reason(gs, tid, triggers, include_soft=weeks > 0)
        if reason is not None:
            return weeks, reason
        if not market.roster_ready(gs, tid)[0]:
            return weeks, "roster_short"
        if before_week is not None:
            before_week(gs)
        telemetry.record_action(gs, "advance", team_id=tid, source=source)
        if events_out is not None:
            events_out.clear()
        report = campaign.advance_week(gs, gd, events_out=events_out)
        weeks += 1
        if after_week is not None:
            after_week(report)
    # Cap reached: report what (if anything) is waiting now, so the toast can
    # say "simmed 4 weeks - and X needs you" instead of leaving it to be found.
    return weeks, stop_reason(gs, tid, triggers)
