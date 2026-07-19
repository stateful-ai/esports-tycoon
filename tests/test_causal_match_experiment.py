from __future__ import annotations

from scripts.causal_match_experiment import (
    Cell,
    Variant,
    _build_cell_inputs,
    experiment_variants,
    run_cell,
)


def _cell(factor: str, level: str, value: float | None = None) -> Cell:
    return Cell(
        variant=Variant(0, factor, level, value),
        map_id="haven",
        identity_swap=0,
        seed_block=1234,
        seeds_per_cell=1,
    )


def test_design_version_ids_are_unique_and_seed_block_is_explicit() -> None:
    versions = experiment_variants()
    assert len(versions) >= 100
    assert len({variant.version_id for variant in versions}) == len(versions)
    assert _cell("prep_edge", "0", 0.0).cell_id.endswith("__seed1234")


def test_normalized_inputs_change_only_the_declared_skill() -> None:
    cell = _cell("skill_aim_precision", "85", 85.0)
    gd, plans, inputs = _build_cell_inputs(cell)
    assert plans == {}
    assert inputs["weak_quality"] == 67.0
    assert inputs["strong_quality"] == 85.0
    for pid in gd.teams[cell.weak_team_id].player_ids:
        player = gd.players[pid]
        assert player.attributes["aim_precision"] == 85.0
        assert player.attributes["game_sense"] == 65.0


def test_symmetry_baseline_mirrors_every_player_mechanic() -> None:
    cell = Cell(
        variant=Variant(
            0,
            "symmetry_baseline",
            "identical",
            context="equal_75v75_symmetry",
            weak_quality=75.0,
            strong_quality=75.0,
        ),
        map_id="haven",
        identity_swap=0,
        seed_block=1234,
        seeds_per_cell=1,
    )
    gd, plans, inputs = _build_cell_inputs(cell)
    assert plans == {}
    assert inputs["weak_quality"] == inputs["strong_quality"] == 75.0
    team_a = gd.teams["team_nexus"]
    team_b = gd.teams["team_vanguard"]
    assert team_a.chemistry == team_b.chemistry
    assert team_a.tactics == team_b.tactics
    for source_id, target_id in zip(team_a.player_ids, team_b.player_ids):
        source = gd.players[source_id].model_dump(
            exclude={"id", "handle", "real_name"}
        )
        target = gd.players[target_id].model_dump(
            exclude={"id", "handle", "real_name"}
        )
        assert source == target


def test_one_match_cell_is_deterministic_and_analysis_ready() -> None:
    cell = _cell("prep_edge", "0", 0.0)
    first = run_cell(cell)
    second = run_cell(cell)
    assert first == second
    assert len(first) == 1
    assert first[0]["seed"] == 1234
    assert first[0]["weak_quality"] == 65.0
    assert first[0]["strong_quality"] == 85.0
    assert first[0]["weak_win"] in (0, 1)


def test_symmetry_identity_orientations_use_disjoint_seeds() -> None:
    variant = Variant(
        0,
        "symmetry_baseline",
        "identical",
        context="equal_75v75_symmetry",
        weak_quality=75.0,
        strong_quality=75.0,
    )
    first = run_cell(Cell(variant, "haven", 0, 70000, 2))
    second = run_cell(Cell(variant, "haven", 1, 70000, 2))
    assert [row["seed"] for row in first] == [70000, 70001]
    assert [row["seed"] for row in second] == [70002, 70003]
