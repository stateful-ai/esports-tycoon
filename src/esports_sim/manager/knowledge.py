"""Organizational knowledge — what an org KNOWS, not just who it employs.

Three kinds of institutional knowledge accrue per org (0-100 each):
- "playbook:<map_id>"  — executes and setups for one map (playing it)
- "antistrat:<tid>"    — a book on one specific opponent (meeting them)
- "methodology"        — practice/prep culture (having a good coach)

Knowledge is created by playing, decays when the world moves (offseason
roster churn guts anti-strats; balance patches date playbooks; culture
mostly keeps), and LEAKS: staff hired away carry part of their old org's
book with them (staff.hire calls `on_staff_move`).

Effect: knowledge amplifies PREPARATION — it feeds the prep edge inside
the existing game-plan seam (campaign._fixture_plans), which the engine
already clamps (PREP_EDGE_CAP) and which the match gates never construct.
No plan, no payoff: knowledge without prep is a library nobody reads.
Accrual itself is rng-free and runs for every org (AI parity in the
STOCK of knowledge; only humans spend it, same documented parity choice
as game plans).

This is the GDD's designed dynasty engine — scripts/dynasty_report.py
watches title concentration so it stays an edge, not a ratchet.
"""

from __future__ import annotations

from esports_sim.manager.state import GameState

CAP = 100.0
PLAYBOOK_PER_MAP_PLAYED = 1.5
ANTISTRAT_PER_MEETING = 3.0
METHODOLOGY_PER_WEEK_COACHED = 0.4  # scaled by coach quality/100

# Offseason survival rates.
KEEP_PLAYBOOK = 0.65  # the meta moves
KEEP_ANTISTRAT = 0.40  # their roster changed too
KEEP_METHODOLOGY = 0.90  # culture compounds
PATCH_PLAYBOOK_KEEP = 0.85  # a balance patch dates the setups

# Staff-move leak: what a hired-away coach/analyst carries out the door.
LEAK_ANTISTRAT = 12.0
LEAK_METHODOLOGY = 6.0

# Prep-edge conversion (the engine clamps the total edge; these keep the
# knowledge share small next to scouting).
EDGE_PER_PLAYBOOK = 0.003  # 100 playbook -> +0.3
EDGE_PER_ANTISTRAT = 0.004  # 100 antistrat -> +0.4


def _org(gs: GameState, tid: str) -> dict[str, float]:
    return gs.org_knowledge.setdefault(tid, {})


def get(gs: GameState, tid: str, key: str) -> float:
    return gs.org_knowledge.get(tid, {}).get(key, 0.0)


def _bump(gs: GameState, tid: str, key: str, amount: float) -> None:
    book = _org(gs, tid)
    book[key] = round(min(CAP, book.get(key, 0.0) + amount), 2)


def on_week(gs: GameState, report) -> None:
    """Accrue from this week's play (rng-free, every org)."""
    from esports_sim.manager import staff_effects

    for f in sorted(report.fixtures, key=lambda x: x.id):
        if not f.played:
            continue
        for tid, opp in ((f.team_a, f.team_b), (f.team_b, f.team_a)):
            if tid not in gs.teams:
                continue
            for r in f.results:
                _bump(gs, tid, f"playbook:{r.map_id}", PLAYBOOK_PER_MAP_PLAYED)
            _bump(gs, tid, f"antistrat:{opp}", ANTISTRAT_PER_MEETING)
    # Methodology compounds under the concrete coach employed by each club.
    for tid in sorted(gs.teams):
        coach = gs.staff_by.get(tid, {}).get("coach")
        q = staff_effects.overall(coach) if coach is not None else 0.0
        if q > 0:
            _bump(gs, tid, "methodology", METHODOLOGY_PER_WEEK_COACHED * q / 100.0)


def offseason_decay(gs: GameState) -> None:
    for tid in sorted(gs.org_knowledge):
        book = gs.org_knowledge[tid]
        for key in sorted(book):
            if key.startswith("playbook:"):
                keep = KEEP_PLAYBOOK
            elif key.startswith("antistrat:"):
                keep = KEEP_ANTISTRAT
            else:
                keep = KEEP_METHODOLOGY
            book[key] = round(book[key] * keep, 2)
        gs.org_knowledge[tid] = {
            k: v for k, v in book.items() if v >= 1.0
        }


def on_patch(gs: GameState) -> None:
    """A balance patch dates every org's map setups a little."""
    for tid in sorted(gs.org_knowledge):
        book = gs.org_knowledge[tid]
        for key in sorted(book):
            if key.startswith("playbook:"):
                book[key] = round(book[key] * PATCH_PLAYBOOK_KEEP, 2)


def on_staff_move(gs: GameState, from_tid: str | None, to_tid: str) -> None:
    """A coach/analyst changing orgs carries part of the old book: the
    hiring org gains a chunk of anti-strat on their old employer and some
    methodology. Called by staff.hire when the candidate's last org is
    known. One direction only — knowledge copies, it doesn't leave."""
    if not from_tid or from_tid == to_tid or from_tid not in gs.teams:
        return
    _bump(gs, to_tid, f"antistrat:{from_tid}", LEAK_ANTISTRAT)
    src_method = get(gs, from_tid, "methodology")
    if src_method > 0:
        _bump(gs, to_tid, "methodology", min(LEAK_METHODOLOGY, src_method * 0.2))


def prep_bonus(gs: GameState, tid: str, opp: str, map_ids: list[str]) -> float:
    """The knowledge share of a game plan's prep edge: the org's book on
    the maps being played plus its book on this exact opponent. Small by
    construction; the engine's PREP_EDGE_CAP clamps the total."""
    playbook = 0.0
    if map_ids:
        playbook = sum(
            get(gs, tid, f"playbook:{m}") for m in map_ids
        ) / len(map_ids)
    anti = get(gs, tid, f"antistrat:{opp}")
    return playbook * EDGE_PER_PLAYBOOK + anti * EDGE_PER_ANTISTRAT


def org_summary(gs: GameState, tid: str) -> dict:
    """A serializer-friendly view: methodology, best playbooks, best books."""
    book = gs.org_knowledge.get(tid, {})
    plays = sorted(
        (
            (k.split(":", 1)[1], v)
            for k, v in book.items()
            if k.startswith("playbook:")
        ),
        key=lambda x: (-x[1], x[0]),
    )
    antis = sorted(
        (
            (k.split(":", 1)[1], v)
            for k, v in book.items()
            if k.startswith("antistrat:")
        ),
        key=lambda x: (-x[1], x[0]),
    )
    return {
        "methodology": round(book.get("methodology", 0.0), 1),
        "playbooks": [
            {"map": m, "depth": round(v, 1)} for m, v in plays[:5]
        ],
        "antistrats": [
            {
                "team_id": t,
                "name": gs.teams[t].name if t in gs.teams else t,
                "depth": round(v, 1),
            }
            for t, v in antis[:5]
        ],
    }
