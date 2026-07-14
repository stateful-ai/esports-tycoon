"""Durable match-review corpus — the growing on-disk record of every review.

GameState keeps only the LATEST review per team (the dashboard card reads it).
This module appends EVERY review to an append-only JSONL sidecar
(`saves/match_review_<code>.jsonl`), never pruned, so the full history of what
good vs bad outcomes look like accumulates for offline analysis
(`scripts/match_review_report.py` mines it).

It is a serving-layer side effect — called from the web advance path, off the
deterministic tick — so campaign determinism (same seed -> byte-identical
GameState) is untouched, exactly like `web/llm_social.py`'s sidecar cache.
`saves/` is git-ignored, so the corpus never enters version control.

Each record is a superset of the (already tier-agnostic) `MatchReview` plus
analysis context — the analyst tier, coach quality/specialty, and team/opp
strength at match time — so records can be sliced and normalized later.
"""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from esports_sim.manager import development
from esports_sim.manager.staff import analytics_tier
from esports_sim.manager.state import GameState, MatchReview

CORPUS_DIR = Path("saves")
_LOCK = threading.Lock()


class ReviewRecord(BaseModel):
    """One line of the corpus: a review plus its analysis context."""

    model_config = ConfigDict(extra="forbid")

    world_code: str
    review: MatchReview
    analyst_tier: int = 0
    coach_quality: float = 0.0
    coach_specialty: str = ""
    team_ca: float = 0.0
    opp_ca: float = 0.0


def _path(code: str) -> Path:
    return CORPUS_DIR / f"match_review_{code}.jsonl"


def _team_ca(gs: GameState, tid: str) -> float:
    """Mean current ability of a team's roster (strength context)."""
    ids = gs.teams[tid].player_ids if tid in gs.teams else []
    vals = [development.overall(gs.players[pid]) for pid in ids if pid in gs.players]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def append_reviews(gs: GameState, code: str, seen: set[tuple[str, str]]) -> None:
    from esports_sim.manager import staff_effects

    """Append reviews from `gs.last_review_by` not yet in `seen` to the corpus.
    Context (analyst tier, coach, strength) is resolved per team — the acting
    pointer is switched per team and restored, so this is safe to call whatever
    the caller's acting manager is."""
    prev = gs._acting_team_id
    records: list[ReviewRecord] = []
    try:
        for tid in sorted(gs.last_review_by):
            rv: MatchReview = gs.last_review_by[tid]
            key = (tid, rv.fixture_id)
            if key in seen:
                continue
            seen.add(key)
            gs.set_acting(tid)
            coach = gs.staff.get("coach")
            records.append(
                ReviewRecord(
                    world_code=code,
                    review=rv,
                    analyst_tier=analytics_tier(gs),
                    coach_quality=staff_effects.overall(coach) if coach else 0.0,
                    coach_specialty=coach.specialty if coach else "",
                    team_ca=_team_ca(gs, tid),
                    opp_ca=_team_ca(gs, rv.opp_id),
                )
            )
    finally:
        gs.set_acting(prev)
    if not records:
        return
    with _LOCK:
        p = _path(code)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(rec.model_dump_json() + "\n")


def load_records(code: str) -> list[ReviewRecord]:
    """Read the corpus back, deduped by (season, week, team, fixture) and
    ordered. A malformed line is skipped, never fatal."""
    try:
        text = _path(code).read_text(encoding="utf-8")
    except OSError:
        return []
    out: dict[tuple, ReviewRecord] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = ReviewRecord.model_validate_json(line)
        except Exception:
            continue
        rv = rec.review
        out[(rv.season, rv.week, rv.team_id, rv.fixture_id)] = rec
    return [out[k] for k in sorted(out)]
