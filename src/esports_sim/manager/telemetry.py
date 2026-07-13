"""Decision telemetry: what the humans actually did, and what the world
looked like when they did it.

Two artifacts, both on GameState so they save/load and stay
campaign-deterministic:

- `action_log` (ActionRecord): every HUMAN-seat action, recorded by the
  web/CLI/agent layer the moment it is applied. Autonomous rule-AI decisions
  are deliberately excluded — they re-derive from the seed, so logging them
  would only bloat the save with redundancy. seed + action_log fully determines a
  career, which makes any finished save a replayable input trace for
  RL/imitation work, and an honest record of which features real
  players touch (feature ideation reads it via
  scripts/telemetry_report.py).

- `telemetry_snaps` (TelemetrySnap): one post-tick org feature vector
  per human SEAT per week, appended by advance_week. This is the state
  half of (state, action, reward) episodes; the reward half is derived
  from consecutive snapshots by scripts/export_telemetry.py. Keyed by
  seat id so an episode follows the manager across a legacy dismissal.

`state_features` is the single source of truth for the feature vector —
the exporter and any future RL env wrapper must read it from here, never
re-derive their own (the tactics_fit lesson: one module, shared)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState

# The closed action vocabulary. Endpoints pass one of these; the guard
# below fails loudly on a typo so the log never silently fragments.
ACTION_KINDS = frozenset(
    {
        "advance",
        "set_training",
        "set_dev_plan",
        "sign",
        "release",
        "renew",
        "swap",
        "bid",
        "respond_offer",
        "propose_package",
        "set_scout",
        "mentor",
        "buyout",
        "negotiate_open",
        "negotiate_offer",
        "negotiate_cancel",
        "save_settings",
        "sponsor_respond",
        "facility_upgrade",
        "hire_staff",
        "release_staff",
        "set_tactics",
        "set_lineup",
        "set_game_plan",
        "clear_game_plan",
        "talk",
        "flavor_choice",
        "resolve_flavor",
        "rein_streaming",
        "accept_job",
        "academy_move",
        "academy_upgrade",
        "set_preparation",
        "tournament_registration",
        "series_directive",
        "set_leadership",
        "culture_session",
        "set_delegation",
        "media_choice",
        "resolve_media",
        "talk_chat",
    }
)


def record_action(
    gs: "GameState",
    kind: str,
    params: dict[str, object] | None = None,
    *,
    team_id: str | None = None,
    source: str = "web",
) -> None:
    """Append one human decision. Call from the web/CLI layer only —
    right after the action succeeded, for the acting manager (or an
    explicit `team_id`). Values are stringified so the record stays a
    flat, schema-stable dict."""
    from esports_sim.manager.state import ActionRecord

    if kind not in ACTION_KINDS:
        raise ValueError(f"unknown action kind '{kind}'")
    tid = team_id if team_id is not None else gs.acting_team_id
    seat = gs.seat_for_session(tid) if tid else None
    gs.action_log.append(
        ActionRecord(
            season=gs.season,
            week=gs.week,
            phase=gs.phase,
            manager_id=seat.id if seat is not None else "",
            team_id=tid or "",
            kind=kind,
            params={k: str(v) for k, v in sorted((params or {}).items())},
            source=source,
        )
    )


# -- the weekly state vector ---------------------------------------------------


def state_features(gs: "GameState", team_id: str) -> dict[str, float]:
    """The org-level feature vector for one team, as floats with stable
    sorted keys. Everything here is information the MANAGER can see
    (their own roster is unfogged; no rival hidden attributes leak into
    the episode), so a policy trained on it is playing the same game a
    human does."""
    from esports_sim.manager import development, staff

    team = gs.teams.get(team_id)
    if team is None:
        return {}
    roster = gs.roster(team_id)
    n = max(len(roster), 1)

    def mean(vals) -> float:
        vals = list(vals)
        return round(sum(vals) / max(len(vals), 1), 3)

    rec = gs.standings.get(team_id)
    order = gs.standings_order(str(team.region), tier=team.tier)
    position = float(order.index(team_id) + 1) if team_id in order else 0.0

    previous = gs.acting_team_id
    gs.set_acting(team_id)
    try:
        staff_q = {
            role: float(m.quality) for role, m in sorted(gs.staff.items())
        }
        facilities = dict(gs.facilities)
        payroll = sum(p.salary for p in roster) + staff.weekly_cost(gs)
        scout_mean = mean(gs.scout_progress.values()) if gs.scout_progress else 0.0
        n_sponsor_deals = float(len(gs.sponsor_slots))
    finally:
        gs.set_acting(previous)

    seat = gs.manager_for(team_id)
    patience = (
        float(seat.contract.patience)
        if seat is not None and seat.contract is not None
        else -1.0
    )

    feats: dict[str, float] = {
        "season": float(gs.season),
        "week": float(gs.week),
        "phase": {"regular": 0.0, "playoffs": 1.0, "offseason": 2.0}.get(
            gs.phase, 0.0
        ),
        "wins": float(rec.wins) if rec else 0.0,
        "losses": float(rec.losses) if rec else 0.0,
        "round_diff": float(rec.diff) if rec else 0.0,
        "league_position": position,
        "balance": float(team.balance),
        "weekly_payroll": float(payroll),
        "reputation": float(team.reputation),
        "fan_count": float(team.fan_count),
        "chemistry": float(team.chemistry),
        "sentiment": float(gs.sentiment(team_id)),
        "world_rank": float(team.world_rank or 0),
        "roster_size": float(len(roster)),
        "roster_ca": mean(development.overall(p) for p in roster),
        "roster_age": mean(p.age for p in roster),
        "roster_morale": mean(p.morale for p in roster),
        "roster_stamina": mean(p.stamina for p in roster),
        "roster_form": mean(p.form for p in roster),
        "roster_confidence": mean(p.confidence for p in roster),
        "contract_weeks_min": float(
            min((p.contract_weeks_left for p in roster), default=0)
        ),
        "scout_progress": scout_mean,
        "sponsor_deals": n_sponsor_deals,
        "board_patience": patience,  # -1 = sandbox (no board)
        "n": float(n),
    }
    for role in staff.ROLES:
        feats[f"staff_{role}"] = staff_q.get(role, 0.0)
    for fac in ("training_center", "analytics_suite", "marketing_office"):
        feats[f"facility_{fac}"] = float(facilities.get(fac, 0))
    return dict(sorted(feats.items()))


def weekly_snapshots(gs: "GameState") -> None:
    """Append this week's post-tick feature snapshot for every human
    seat. Runs at the END of advance_week (results, finances, sentiment
    all settled), before the week counter rolls — so snap N pairs with
    the actions taken during week N and the reward is the delta to snap
    N+1. A seat between jobs snapshots empty features (the episode gap
    is itself signal)."""
    from esports_sim.manager.state import TelemetrySnap

    for mid in sorted(gs.managers):
        seat = gs.managers[mid]
        gs.telemetry_snaps.setdefault(mid, []).append(
            TelemetrySnap(
                season=gs.season,
                week=gs.week,
                phase=gs.phase,
                team_id=seat.team_id,
                features=(
                    state_features(gs, seat.team_id) if seat.team_id else {}
                ),
            )
        )


# -- reward shaping --------------------------------------------------------------

# Default component weights for a scalar reward. Exported datasets keep
# the raw components too, so a training run can re-weight without
# re-exporting.
REWARD_WEIGHTS: dict[str, float] = {
    "wins_delta": 1.0,
    "round_diff_delta": 0.02,
    "balance_delta_100k": 0.3,
    "reputation_delta": 0.2,
    "sentiment_delta": 0.05,
    "patience_delta": 0.1,
    "insolvent": -2.0,
    "dismissed": -8.0,
}


def reward_components(
    prev: dict[str, float], now: dict[str, float], *, dismissed: bool = False
) -> dict[str, float]:
    """Per-week reward components between two consecutive snapshots of
    the SAME seat. Season rollovers reset standings, so wins/round-diff
    deltas only count within a season (the exporter passes snapshots
    from one season at a time)."""

    def d(key: str) -> float:
        return round(now.get(key, 0.0) - prev.get(key, 0.0), 3)

    comps = {
        "wins_delta": d("wins"),
        "round_diff_delta": d("round_diff"),
        "balance_delta_100k": round(d("balance") / 100_000.0, 4),
        "reputation_delta": d("reputation"),
        "sentiment_delta": d("sentiment"),
        "patience_delta": (
            d("board_patience")
            if prev.get("board_patience", -1.0) >= 0
            and now.get("board_patience", -1.0) >= 0
            else 0.0
        ),
        "insolvent": 1.0 if now.get("balance", 0.0) < 0 else 0.0,
        "dismissed": 1.0 if dismissed else 0.0,
    }
    comps["reward"] = round(
        sum(REWARD_WEIGHTS[k] * v for k, v in comps.items() if k in REWARD_WEIGHTS),
        4,
    )
    return comps
