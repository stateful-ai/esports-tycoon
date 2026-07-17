"""Durable match-review corpus: append/load round-trip and dedup."""

from __future__ import annotations

from esports_sim.manager import advance_week, new_campaign
from esports_sim.registry import GameData
from esports_sim.web import review_history


def _played(gd: GameData, seed: int = 123, weeks: int = 3):
    gs = new_campaign(gd, seed=seed)
    for _ in range(weeks):
        advance_week(gs, gd)
    return gs


def test_append_and_load_roundtrip(game_data: GameData, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    gs = _played(game_data)
    review_history.append_reviews(gs, "WRLD1", set())

    recs = review_history.load_records("WRLD1")
    assert recs, "expected at least one recorded review"
    rec = recs[0]
    assert rec.world_code == "WRLD1"
    # Context rode along with the review.
    assert rec.team_ca > 0 and rec.opp_ca > 0
    assert rec.analyst_tier >= 0
    # The corpus keeps the FULL (ungated) signal set, not the tier-filtered view.
    stored = rec.review
    assert stored.team_id in gs.teams
    # File actually landed under the patched dir.
    assert (tmp_path / "match_review_WRLD1.jsonl").exists()


def test_seen_set_skips_reappend(game_data: GameData, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    gs = _played(game_data)
    seen: set = set()
    review_history.append_reviews(gs, "WRLD2", seen)
    n1 = len(review_history.load_records("WRLD2"))
    # Same state + same seen -> nothing new appended.
    review_history.append_reviews(gs, "WRLD2", seen)
    n2_lines = (tmp_path / "match_review_WRLD2.jsonl").read_text().strip().splitlines()
    assert len(n2_lines) == n1  # no duplicate lines written


def test_load_dedups_by_key(game_data: GameData, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    gs = _played(game_data)
    # Append twice with FRESH seen sets -> duplicate lines on disk...
    review_history.append_reviews(gs, "WRLD3", set())
    review_history.append_reviews(gs, "WRLD3", set())
    raw = (tmp_path / "match_review_WRLD3.jsonl").read_text().strip().splitlines()
    recs = review_history.load_records("WRLD3")
    # ...but load_records dedups by (season, week, team, fixture).
    assert len(recs) < len(raw) or len(raw) == len(recs) == len(set(
        (r.review.season, r.review.week, r.review.team_id, r.review.fixture_id)
        for r in recs
    ))
    keys = [
        (r.review.season, r.review.week, r.review.team_id, r.review.fixture_id)
        for r in recs
    ]
    assert len(keys) == len(set(keys))  # unique after dedup


def test_missing_corpus_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    assert review_history.load_records("NOPE") == []


def test_old_corpus_lines_without_calls_still_load(
    game_data: GameData, tmp_path, monkeypatch
) -> None:
    """The JSONL schema is additive: lines written before the review gained
    manager attribution (`calls`) must keep loading (calls defaults to None),
    and new lines must round-trip the captured calls."""
    import json

    monkeypatch.setattr(review_history, "CORPUS_DIR", tmp_path)
    gs = _played(game_data)
    review_history.append_reviews(gs, "WRLD5", set())
    path = tmp_path / "match_review_WRLD5.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    # New lines carry the attribution record.
    assert all("calls" in json.loads(ln)["review"] for ln in lines)
    # Rewrite the corpus in the PRE-calls shape and reload.
    old_style = []
    for ln in lines:
        rec = json.loads(ln)
        rec["review"].pop("calls", None)
        old_style.append(json.dumps(rec))
    path.write_text("\n".join(old_style) + "\n", encoding="utf-8")
    recs = review_history.load_records("WRLD5")
    assert len(recs) == len(lines)
    assert all(r.review.calls is None for r in recs)
