from __future__ import annotations

from scripts.causal_match_experiment import Cell, Variant
from scripts.causal_match_supplement import (
    build_supplement_inputs,
    run_supplement_cell,
    supplement_variants,
)


def _cell(factor: str, level: str, value: float | None = None) -> Cell:
    return Cell(
        Variant(0, factor, level, value, "normalized_65v85_supplement", 65.0, 85.0),
        "haven",
        0,
        30000,
        1,
    )


def test_supplement_design_covers_both_talent_contexts() -> None:
    variants = supplement_variants()
    assert {variant.context for variant in variants} == {
        "normalized_65v85_supplement",
        "normalized_75v80_supplement",
    }
    assert {variant.factor for variant in variants} >= {
        "shared_language", "role_comfort", "role_assignment", "micro_bundle"
    }


def test_role_comfort_applies_campaign_match_view() -> None:
    low, _ = build_supplement_inputs(_cell("role_comfort", "40", 40.0))
    high, _ = build_supplement_inputs(_cell("role_comfort", "100", 100.0))
    weak_id = "team_nexus"
    assert sum(low.players[pid].attributes["aim_precision"] for pid in low.teams[weak_id].player_ids) < sum(
        high.players[pid].attributes["aim_precision"] for pid in high.teams[weak_id].player_ids
    )


def test_language_cell_is_deterministic_and_records_mode() -> None:
    cell = _cell("shared_language", "100", 100.0)
    first = run_supplement_cell(cell)
    second = run_supplement_cell(cell)
    assert first == second
    assert first[0]["weak_language_mode"] == "100"
