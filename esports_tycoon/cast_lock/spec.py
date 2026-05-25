"""Acceptance-bar validation for the Week-6-of-8 canned save.

The checks here are exactly the M0.0 ticket's acceptance criteria, expressed as
code so the canned save can't silently drift below the bar:

  * 5 named starters, one per role, each with a voice prompt;
  * every starter appears in at least one explicit clash pair;
  * 5–6 rival archetypes;
  * >= 30 precedent memory entries with stable, unique `mem:<player>:<event>` IDs
    whose owner segment is a real starter;
  * last week's scoreline and last week's Chirper feed present;
  * tone pinned to dry-mockumentary and Vector Strike (Valorant) flavor.

This is a structural gate, not the game's typed schema. It reads plain dicts so
it has zero coupling to the (later) pydantic models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Repository root is three parents up from this file:
# esports_tycoon/cast_lock/spec.py -> esports_tycoon -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAVE_PATH = _REPO_ROOT / "saves" / "week6.yaml"
DEFAULT_DOC_PATH = _REPO_ROOT / "docs" / "tone_and_cast_lock.md"

# Acceptance thresholds (from scope-m0.md and the M0.0 ticket).
REQUIRED_STARTERS = 5
MIN_RIVALS = 5
MAX_RIVALS = 6
MIN_MEMORIES = 30
VALID_ROLES = {"IGL", "DUELIST", "CONTROLLER", "SENTINEL", "INITIATOR"}
VALID_MEMORY_KINDS = {"match", "scrim", "social", "1on1", "press", "rumor"}

# `mem:<player_id>:<event_slug>` — lowercase ascii, dash-snake slug.
MEMORY_ID_RE = re.compile(r"^mem:([a-z0-9_]+):([a-z0-9]+(?:_[a-z0-9]+)*)$")


@dataclass(frozen=True)
class Check:
    """One acceptance-criterion result."""

    name: str
    passed: bool
    detail: str


@dataclass
class ValidationResult:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name=name, passed=passed, detail=detail))


def load_save(path: str | Path = DEFAULT_SAVE_PATH) -> dict[str, Any]:
    """Parse the canned save YAML into a plain dict."""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def _starters(save: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (save.get("players") or []) if isinstance(p, dict)]


def _all_memory_entries(save: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for player in _starters(save):
        for entry in player.get("memory_log") or []:
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def validate_save(save: dict[str, Any]) -> ValidationResult:
    """Validate a parsed canned save against the M0.0 acceptance bar."""
    result = ValidationResult()

    starters = _starters(save)
    starter_ids = {p.get("id") for p in starters if p.get("id")}

    # --- tone + flavor lock --------------------------------------------------
    meta = save.get("save") or {}
    tone = str(meta.get("tone", "")).lower()
    flavor = str(meta.get("flavor", "")).lower()
    game = str(meta.get("game", "")).lower()
    result.add(
        "tone_locked",
        tone == "dry-mockumentary",
        f"save.tone={meta.get('tone')!r} (want 'dry-mockumentary')",
    )
    result.add(
        "flavor_locked",
        "valorant" in flavor and "vector strike" in game,
        f"save.flavor={meta.get('flavor')!r}, save.game={meta.get('game')!r}",
    )

    # --- 5 named starters, one per role, each with a voice -------------------
    named = [
        p
        for p in starters
        if p.get("id") and str(p.get("name", "")).strip() and p.get("role") in VALID_ROLES
    ]
    result.add(
        "five_named_starters",
        len(named) == REQUIRED_STARTERS,
        f"{len(named)} named starters with a valid role (want {REQUIRED_STARTERS})",
    )
    roles = [p.get("role") for p in named]
    result.add(
        "one_per_role",
        sorted(roles) == sorted(VALID_ROLES),
        f"roles={sorted(r for r in roles if r)} (want one each of {sorted(VALID_ROLES)})",
    )
    missing_voice = [p.get("id") for p in starters if not str(p.get("persona_voice", "")).strip()]
    result.add(
        "starters_have_voice",
        not missing_voice,
        "all starters have persona_voice" if not missing_voice else f"missing voice: {missing_voice}",
    )

    # --- explicit clash pairs covering every starter ------------------------
    clash_pairs = [c for c in (save.get("clash_pairs") or []) if isinstance(c, dict)]
    clashed: set[str] = set()
    bad_pairs: list[str] = []
    for pair in clash_pairs:
        a, b = pair.get("a"), pair.get("b")
        if not a or not b:
            bad_pairs.append(repr(pair))
            continue
        if a in starter_ids:
            clashed.add(a)
        if b in starter_ids:
            clashed.add(b)
    uncovered = sorted(starter_ids - clashed)
    result.add(
        "clash_pairs_present",
        len(clash_pairs) >= 1 and not bad_pairs,
        f"{len(clash_pairs)} clash pairs"
        + (f"; malformed: {bad_pairs}" if bad_pairs else ""),
    )
    result.add(
        "every_starter_clashes",
        not uncovered,
        "every starter in >=1 clash pair" if not uncovered else f"no clash for: {uncovered}",
    )

    # --- 5-6 rival archetypes ------------------------------------------------
    rivals = [r for r in (save.get("rivals") or []) if isinstance(r, dict)]
    well_formed_rivals = [
        r for r in rivals if r.get("id") and str(r.get("name", "")).strip() and str(r.get("archetype", "")).strip()
    ]
    result.add(
        "rival_archetype_count",
        MIN_RIVALS <= len(well_formed_rivals) <= MAX_RIVALS,
        f"{len(well_formed_rivals)} well-formed rival archetypes (want {MIN_RIVALS}-{MAX_RIVALS})",
    )

    # --- >= 30 memory entries with stable, unique, owner-valid IDs ----------
    entries = _all_memory_entries(save)
    result.add(
        "memory_count",
        len(entries) >= MIN_MEMORIES,
        f"{len(entries)} memory entries (want >= {MIN_MEMORIES})",
    )

    seen: set[str] = set()
    malformed: list[str] = []
    duplicates: list[str] = []
    wrong_owner: list[str] = []
    bad_kind: list[str] = []
    for player in starters:
        owner = player.get("id")
        for entry in player.get("memory_log") or []:
            if not isinstance(entry, dict):
                continue
            mem_id = entry.get("id", "")
            m = MEMORY_ID_RE.match(str(mem_id))
            if not m:
                malformed.append(str(mem_id))
                continue
            if mem_id in seen:
                duplicates.append(mem_id)
            seen.add(mem_id)
            if m.group(1) != owner:
                wrong_owner.append(f"{mem_id} in {owner}'s log")
            if entry.get("kind") not in VALID_MEMORY_KINDS:
                bad_kind.append(f"{mem_id} kind={entry.get('kind')!r}")

    result.add(
        "memory_ids_well_formed",
        not malformed,
        "all memory IDs match mem:<player>:<event>" if not malformed else f"malformed: {malformed}",
    )
    result.add(
        "memory_ids_unique",
        not duplicates,
        "all memory IDs unique" if not duplicates else f"duplicates: {duplicates}",
    )
    result.add(
        "memory_owner_matches_log",
        not wrong_owner,
        "every memory ID owner matches its log" if not wrong_owner else f"mismatches: {wrong_owner}",
    )
    result.add(
        "memory_kinds_valid",
        not bad_kind,
        "all memory kinds valid" if not bad_kind else f"bad kinds: {bad_kind}",
    )

    # --- last week: scoreline + Chirper feed --------------------------------
    last_week = save.get("last_week") or {}
    scoreline = last_week.get("scoreline") or {}
    maps = scoreline.get("maps") if isinstance(scoreline, dict) else None
    has_scoreline = (
        isinstance(scoreline, dict)
        and "overcast" in scoreline
        and "opponent" in scoreline
        and isinstance(maps, list)
        and len(maps) >= 1
    )
    result.add(
        "last_week_scoreline",
        has_scoreline,
        "last_week.scoreline present with map breakdown" if has_scoreline else f"scoreline={scoreline!r}",
    )

    feed = last_week.get("chirper_feed")
    has_feed = isinstance(feed, list) and len([p for p in feed if isinstance(p, dict) and p.get("text")]) >= 1
    result.add(
        "last_week_feed",
        bool(has_feed),
        f"last_week.chirper_feed has {len(feed) if isinstance(feed, list) else 0} posts",
    )

    # --- feed/clash cites resolve to real memory IDs (no dangling history) ---
    dangling: list[str] = []
    for pair in clash_pairs:
        for cite in pair.get("seeded_by") or []:
            if cite not in seen:
                dangling.append(f"clash {pair.get('a')}/{pair.get('b')} -> {cite}")
    if isinstance(feed, list):
        for post in feed:
            if not isinstance(post, dict):
                continue
            for cite in post.get("cites") or []:
                if cite not in seen:
                    dangling.append(f"chirp {post.get('id')} -> {cite}")
    result.add(
        "cites_resolve",
        not dangling,
        "all clash/feed cites resolve to a memory ID" if not dangling else f"dangling cites: {dangling}",
    )

    return result


def validate_path(path: str | Path = DEFAULT_SAVE_PATH) -> ValidationResult:
    """Convenience: load and validate a save file in one call."""
    return validate_save(load_save(path))
