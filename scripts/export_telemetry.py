"""Export RL/analysis datasets from campaign saves.

Reads one save file (or every ``*.json`` campaign save in a directory)
and writes JSONL datasets next to the output stem:

- ``<stem>.episodes.jsonl`` — one line per (seat, week) transition:
  the post-tick state feature vector, the actions that seat took during
  the week, the next week's features, and per-component + scalar reward
  (manager/telemetry.py owns feature extraction and reward shaping —
  this script never re-derives either). Episodes are cut per season
  (standings reset at rollover, so cross-season deltas would be noise)
  and follow the SEAT, not the org, across a legacy dismissal.

- ``<stem>.actions.jsonl`` — the raw action log, one decision per line
  (feature-ideation fodder; scripts/telemetry_report.py aggregates it).

- ``<stem>.chronicle.jsonl`` — the career chronicle, one event per line
  (long-horizon context for world-model work).

Usage:
    python scripts/export_telemetry.py <save.json | saves-dir> [out-stem]

Deterministic: output ordering is (seat, season, week); no wall-clock,
no rng. ASCII-only output (cp1252 consoles).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from esports_sim.manager import telemetry
from esports_sim.manager.state import GameState


def _episode_rows(gs: GameState, save_name: str) -> list[dict]:
    rows: list[dict] = []
    dismissal_weeks: dict[str, set[tuple[int, int]]] = {}
    for e in gs.chronicle:
        if e.kind == "dismissal":
            dismissal_weeks.setdefault(e.manager_id, set()).add(
                (e.season, e.week)
            )

    actions_by: dict[tuple[str, int, int], list[dict]] = {}
    for a in gs.action_log:
        key = (a.manager_id, a.season, a.week)
        actions_by.setdefault(key, []).append(
            {"kind": a.kind, "params": a.params, "source": a.source}
        )

    for mid in sorted(gs.telemetry_snaps):
        snaps = gs.telemetry_snaps[mid]
        for prev, now in zip(snaps, snaps[1:]):
            if now.season != prev.season:
                continue  # season rollover: episode boundary, no reward
            if not prev.features or not now.features:
                continue  # a between-jobs gap
            dismissed = (now.season, now.week) in dismissal_weeks.get(mid, set())
            comps = telemetry.reward_components(
                prev.features, now.features, dismissed=dismissed
            )
            rows.append(
                {
                    "save": save_name,
                    "seat": mid,
                    "season": prev.season,
                    "week": prev.week,
                    "team_id": prev.team_id,
                    "state": prev.features,
                    "actions": actions_by.get((mid, prev.season, prev.week), []),
                    "next_state": now.features,
                    "reward": comps.pop("reward"),
                    "reward_components": comps,
                    "done": dismissed,
                }
            )
    return rows


def export_save(path: Path, stem: Path) -> tuple[int, int, int]:
    gs = GameState.load(path)
    name = path.stem

    episodes = _episode_rows(gs, name)
    actions = [
        {"save": name, **a.model_dump()} for a in gs.action_log
    ]
    chronicle = [
        {"save": name, **e.model_dump()} for e in gs.chronicle
    ]

    stem.parent.mkdir(parents=True, exist_ok=True)
    for suffix, rows in (
        (".episodes.jsonl", episodes),
        (".actions.jsonl", actions),
        (".chronicle.jsonl", chronicle),
    ):
        out = stem.with_name(stem.name + suffix)
        with out.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    return len(episodes), len(actions), len(chronicle)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = Path(sys.argv[1])
    stem = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("telemetry/export")

    if target.is_dir():
        saves = sorted(
            p
            for p in target.glob("*.json")
            if not p.name.startswith("social_llm_")  # LLM sidecars, not saves
        )
    else:
        saves = [target]
    if not saves:
        print(f"no saves found under {target}")
        return 1

    # Fresh export: truncate any prior files at this stem.
    for suffix in (".episodes.jsonl", ".actions.jsonl", ".chronicle.jsonl"):
        out = stem.with_name(stem.name + suffix)
        if out.exists():
            out.unlink()

    total = [0, 0, 0]
    for p in saves:
        try:
            n = export_save(p, stem)
        except Exception as exc:  # a non-campaign json in the folder
            print(f"  skip {p.name}: {str(exc).splitlines()[0]}")
            continue
        total = [a + b for a, b in zip(total, n)]
        print(
            f"  {p.name}: {n[0]} transitions, {n[1]} actions, "
            f"{n[2]} chronicle events"
        )
    print(
        f"exported {total[0]} transitions, {total[1]} actions, "
        f"{total[2]} chronicle events -> {stem}.*.jsonl"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
