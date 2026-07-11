"""How are people actually playing? Aggregate the action logs across
saves into a feature-usage report for ideation.

Reads every campaign save under a directory (default ``saves/``) and
prints, ASCII-only:

- action mix (what players do, per action kind, with per-week rates)
- feature adoption (which systems get touched at all, per save)
- never-touched features (the ideation signal: unused = invisible,
  confusing, or genuinely unwanted)
- tactics identity distribution (how far from neutral players push
  each dial when they commit a book)
- talk / game-plan / market appetites
- weekly action intensity (actions per advanced week, by phase)

Usage: python scripts/telemetry_report.py [saves-dir]
Read-only; never mutates a save. Exit 0 always (report, not a gate).
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

from esports_sim.manager import telemetry
from esports_sim.manager.state import GameState


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("saves")
    saves = sorted(
        p
        for p in root.glob("*.json")
        if not p.name.startswith("social_llm_")
    )
    if not saves:
        print(f"no saves under {root}")
        return 0

    kind_counts: Counter[str] = Counter()
    kinds_per_save: dict[str, set[str]] = {}
    weeks_advanced = 0
    weeks_by_phase: Counter[str] = Counter()
    actions_by_phase: Counter[str] = Counter()
    dial_pushes: dict[str, list[float]] = defaultdict(list)
    talk_options: Counter[str] = Counter()
    plan_dials: Counter[int] = Counter()
    sources: Counter[str] = Counter()
    n_loaded = 0

    for p in saves:
        try:
            gs = GameState.load(p)
        except Exception as exc:
            print(f"  skip {p.name}: {str(exc).splitlines()[0]}")
            continue
        n_loaded += 1
        seen: set[str] = set()
        for a in gs.action_log:
            kind_counts[a.kind] += 1
            actions_by_phase[a.phase] += 1
            sources[a.source] += 1
            seen.add(a.kind)
            if a.kind == "advance":
                weeks_advanced += 1
                weeks_by_phase[a.phase] += 1
            elif a.kind == "set_tactics":
                for dial in (
                    "aggression", "pace", "util_discipline",
                    "eco_greed", "map_control",
                ):
                    v = a.params.get(dial)
                    if v is not None:
                        dial_pushes[dial].append(abs(float(v) - 50.0))
            elif a.kind == "talk":
                talk_options[a.params.get("option_id", "?")] += 1
            elif a.kind == "set_game_plan":
                plan_dials[int(a.params.get("n_dials", "0"))] += 1
        kinds_per_save[p.stem] = seen

    total = sum(kind_counts.values())
    print(f"telemetry report: {n_loaded} saves, {total} recorded actions")
    print()

    print("action mix (count, per advanced week):")
    per_week = max(weeks_advanced, 1)
    for kind, n in kind_counts.most_common():
        print(f"  {kind:<18} {n:>6}   {n / per_week:>6.2f}/wk")
    print()

    untouched = sorted(telemetry.ACTION_KINDS - set(kind_counts))
    if untouched:
        print("never used anywhere (ideation signal):")
        for kind in untouched:
            print(f"  {kind}")
        print()

    if kinds_per_save:
        print("feature adoption (saves that used it / saves):")
        for kind in sorted(telemetry.ACTION_KINDS):
            n = sum(1 for s in kinds_per_save.values() if kind in s)
            if n:
                print(f"  {kind:<18} {n}/{len(kinds_per_save)}")
        print()

    if dial_pushes:
        print("tactics: mean |dial - 50| when a book is committed:")
        for dial in sorted(dial_pushes):
            vals = dial_pushes[dial]
            print(
                f"  {dial:<16} {sum(vals) / len(vals):>5.1f} "
                f"(n={len(vals)}, max {max(vals):.0f})"
            )
        print()

    if plan_dials:
        n_plans = sum(plan_dials.values())
        heavy = sum(n for k, n in plan_dials.items() if k > 0)
        print(
            f"game plans: {n_plans} set; {heavy} carried dial overrides "
            f"({100 * heavy // max(n_plans, 1)}%)"
        )
    if talk_options:
        top = ", ".join(f"{k} x{n}" for k, n in talk_options.most_common(5))
        print(f"talk approaches: {top}")
    if weeks_by_phase:
        line = ", ".join(
            f"{ph}: {actions_by_phase[ph] / max(weeks_by_phase[ph], 1):.1f}"
            for ph in sorted(weeks_by_phase)
        )
        print(f"actions per week by phase: {line}")
    if sources:
        print(
            "sources: "
            + ", ".join(f"{k} {n}" for k, n in sources.most_common())
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
