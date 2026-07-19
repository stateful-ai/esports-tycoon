"""Reproducible paired-seed analysis for causal match experiment datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from statsmodels.stats.proportion import proportion_confint


PAIR_KEYS = ["map_id", "identity_swap", "seed"]
OUTCOMES = ["weak_win", "weak_round_margin", "weak_score", "strong_score"]
PALETTE = {"blue": "#2563EB", "orange": "#EA580C", "gold": "#CA8A04", "slate": "#475569"}

# Neutral/current reference levels used for decision-facing treatment comparisons.
# Role comfort and IGL experience default to 100 in the normalized roster factory;
# lower values are therefore expressed as rounds lost versus that baseline.
BASELINE_LEVELS = {
    "weak_overall": "65",
    "agent_mastery": "75",
    "agent_selection": "auto",
    "chemistry_complex_system": "65",
    "chemistry_neutral": "65",
    "coach_quality": "50",
    "confidence": "50",
    "counter_edge": "0",
    "focus_target": "none",
    "form": "50",
    "halftime_talk": "none",
    "igl_experience": "100",
    "map_mastery": "75",
    "mental_bundle": "65",
    "micro_bundle": "65",
    "morale": "50",
    "prep_edge": "0",
    "role_assignment": "rotated",
    "role_comfort": "100",
    "roster_shape": "balanced",
    "shared_language": "50",
    "stamina": "100",
    "tactical_bundle": "65",
    "touchline_shout": "none",
    "tactic_aggression": "50",
    "tactic_eco_greed": "50",
    "tactic_map_control": "50",
    "tactic_pace": "50",
    "tactic_util_discipline": "50",
}
BASELINE_LEVELS.update({
    factor: "65"
    for factor in (
        "skill_aim_precision", "skill_aim_reactivity", "skill_clutch_factor",
        "skill_comms_quality", "skill_composure", "skill_game_sense",
        "skill_movement", "skill_positioning", "skill_tilt_resistance",
        "skill_utility_usage",
    )
})


def load_dataset(path: Path, source: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    frame["source"] = source
    frame["level"] = frame["level"].astype(str)
    return frame


def _cluster_ci(values: pd.Series) -> tuple[float, float, float, int]:
    values = values.dropna().astype(float)
    estimate = float(values.mean())
    if len(values) < 2 or float(values.std(ddof=1)) == 0:
        return estimate, estimate, estimate, len(values)
    sem = float(values.std(ddof=1) / np.sqrt(len(values)))
    critical = float(stats.t.ppf(0.975, len(values) - 1))
    return estimate, estimate - critical * sem, estimate + critical * sem, len(values)


def paired_comparison(
    frame: pd.DataFrame,
    context: str,
    factor: str,
    low_level: str,
    high_level: str,
) -> dict[str, Any]:
    subset = frame[(frame["context"] == context) & (frame["factor"] == factor)]
    analysis_columns = [*PAIR_KEYS, "seed_block", *OUTCOMES]
    low = subset[subset["level"] == str(low_level)][analysis_columns]
    high = subset[subset["level"] == str(high_level)][analysis_columns]
    merged = low.merge(high, on=PAIR_KEYS, suffixes=("_low", "_high"), validate="one_to_one")
    if merged.empty:
        raise ValueError(f"empty pair: {context}/{factor}/{low_level}->{high_level}")
    result: dict[str, Any] = {
        "context": context,
        "factor": factor,
        "low_level": str(low_level),
        "high_level": str(high_level),
        "matches_per_level": len(merged),
    }
    for outcome in OUTCOMES:
        merged[f"delta_{outcome}"] = merged[f"{outcome}_high"] - merged[f"{outcome}_low"]
        by_seed = merged.groupby("seed", observed=True)[f"delta_{outcome}"].mean()
        estimate, low_ci, high_ci, clusters = _cluster_ci(by_seed)
        result.update({
            f"{outcome}_effect": estimate,
            f"{outcome}_ci_low": low_ci,
            f"{outcome}_ci_high": high_ci,
            f"{outcome}_seed_clusters": clusters,
        })
    # Audience-facing estimand: how many additional rounds the treated team won.
    # The opponent component is signed positively when treatment denies rounds.
    result["rounds_won_added"] = result["weak_score_effect"]
    result["rounds_won_added_ci_low"] = result["weak_score_ci_low"]
    result["rounds_won_added_ci_high"] = result["weak_score_ci_high"]
    result["opponent_rounds_denied"] = -result["strong_score_effect"]
    result["opponent_rounds_denied_ci_low"] = -result["strong_score_ci_high"]
    result["opponent_rounds_denied_ci_high"] = -result["strong_score_ci_low"]
    result["margin_reconciliation_error"] = (
        result["weak_round_margin_effect"]
        - result["rounds_won_added"]
        - result["opponent_rounds_denied"]
    )
    block = merged.groupby("seed_block_low", observed=True)["delta_weak_round_margin"].mean()
    score_block = merged.groupby("seed_block_low", observed=True)["delta_weak_score"].mean()
    overall_sign = np.sign(result["weak_round_margin_effect"])
    result["seed_block_effects"] = {str(int(k)): float(v) for k, v in block.items()}
    result["seed_block_rounds_won_added"] = {str(int(k)): float(v) for k, v in score_block.items()}
    result["seed_block_sign_agreement"] = float((np.sign(block) == overall_sign).mean())
    return result


def baseline_effects(frame: pd.DataFrame) -> pd.DataFrame:
    """Compare every authored treatment level with its explicit neutral baseline."""
    rows: list[dict[str, Any]] = []
    for (context, factor), group in frame.groupby(["context", "factor"], observed=True):
        baseline = BASELINE_LEVELS.get(str(factor))
        levels = {str(level) for level in group["level"].unique()}
        if baseline is None or baseline not in levels:
            continue
        for treatment in sorted(levels - {baseline}):
            row = paired_comparison(frame, str(context), str(factor), baseline, treatment)
            row["baseline_level"] = baseline
            row["treatment_level"] = treatment
            rows.append(row)
    result = pd.DataFrame(rows)
    if not result.empty:
        result["weak_win_effect_pp"] = result["weak_win_effect"] * 100
    return result


def _level_pair(group: pd.DataFrame) -> tuple[str, str, str]:
    numeric = group[["level", "level_numeric"]].drop_duplicates().dropna(subset=["level_numeric"])
    if len(numeric) == group["level"].nunique():
        ordered = numeric.sort_values("level_numeric")
        return str(ordered.iloc[0]["level"]), str(ordered.iloc[-1]["level"]), "low-to-high"
    means = group.groupby("level", observed=True)["weak_round_margin"].mean().sort_values()
    return str(means.index[0]), str(means.index[-1]), "observed worst-to-best"


def all_factor_effects(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (context, factor), group in frame.groupby(["context", "factor"], observed=True):
        if group["level"].nunique() < 2:
            continue
        low_level, high_level, comparison = _level_pair(group)
        row = paired_comparison(frame, str(context), str(factor), low_level, high_level)
        row["comparison"] = comparison
        rows.append(row)
    result = pd.DataFrame(rows)
    result["weak_win_effect_pp"] = result["weak_win_effect"] * 100
    result["weak_win_ci_low_pp"] = result["weak_win_ci_low"] * 100
    result["weak_win_ci_high_pp"] = result["weak_win_ci_high"] * 100
    return result


def overall_curve(primary: pd.DataFrame) -> pd.DataFrame:
    data = primary[primary["factor"] == "weak_overall"].copy()
    rows = []
    for level, group in data.groupby("level_numeric", observed=True):
        wins = int(group["weak_win"].sum())
        n = len(group)
        ci_low, ci_high = proportion_confint(wins, n, alpha=0.05, method="wilson")
        rows.append({
            "weak_overall": float(level), "matches": n, "wins": wins,
            "win_rate": wins / n, "win_ci_low": ci_low, "win_ci_high": ci_high,
            "mean_round_margin": group["weak_round_margin"].mean(),
            "close_match_rate": group["close_match"].mean(),
        })
    return pd.DataFrame(rows).sort_values("weak_overall")


def requested_comparisons(combined: pd.DataFrame) -> pd.DataFrame:
    requests = [
        ("normalized_65v85", "skill_aim_precision", "65", "85", "Aim precision 65 to 85"),
        ("normalized_65v85", "skill_aim_reactivity", "65", "85", "Aim reactivity 65 to 85"),
        ("normalized_65v85", "skill_movement", "65", "85", "Movement 65 to 85"),
        ("normalized_65v85_supplement", "micro_bundle", "65", "85", "Micro bundle 65 to 85"),
        ("normalized_75v80_supplement", "micro_bundle", "65", "85", "Micro bundle 65 to 85"),
        ("normalized_65v85_supplement", "role_comfort", "40", "100", "Role comfort"),
        ("normalized_75v80_supplement", "role_comfort", "40", "100", "Role comfort"),
        ("normalized_65v85_supplement", "role_assignment", "rotated", "aligned", "Aligned roles vs rotated"),
        ("normalized_75v80_supplement", "role_assignment", "rotated", "aligned", "Aligned roles vs rotated"),
        ("normalized_65v85_supplement", "shared_language", "50", "100", "Language 50 to 100"),
        ("normalized_75v80_supplement", "shared_language", "50", "100", "Language 50 to 100"),
        ("normalized_65v85_supplement", "igl_experience", "40", "100", "IGL experience"),
        ("normalized_75v80_supplement", "igl_experience", "40", "100", "IGL experience"),
        ("normalized_75v80_supplement", "tactical_bundle", "65", "85", "Tactical bundle 65 to 85"),
        ("normalized_75v80_supplement", "mental_bundle", "65", "85", "Mental bundle 65 to 85"),
    ]
    rows = []
    available = set(zip(combined["context"], combined["factor"]))
    for context, factor, low, high, label in requests:
        if (context, factor) not in available:
            continue
        row = paired_comparison(combined, context, factor, low, high)
        row["lever"] = label
        rows.append(row)
    result = pd.DataFrame(rows)
    result["win_effect_pp"] = result["weak_win_effect"] * 100
    return result


def exact_language_check(supplement: pd.DataFrame) -> dict[str, Any]:
    checks = {}
    for context in sorted(supplement["context"].unique()):
        group = supplement[(supplement["context"] == context) & (supplement["factor"] == "shared_language")]
        none = group[group["level"] == "no_common"]
        fifty = group[group["level"] == "50"]
        merged = none.merge(fifty, on=PAIR_KEYS, suffixes=("_none", "_50"), validate="one_to_one")
        checks[context] = {
            "paired_matches": len(merged),
            "identical_winner_and_score": bool(
                (merged["weak_win_none"] == merged["weak_win_50"]).all()
                and (merged["weak_score_none"] == merged["weak_score_50"]).all()
                and (merged["strong_score_none"] == merged["strong_score_50"]).all()
            ),
            "all_tested_levels_identical": bool(
                group.groupby(PAIR_KEYS, observed=True)[["weak_win", "weak_score", "strong_score"]]
                .nunique()
                .le(1)
                .all()
                .all()
            ),
        }
    return checks


def _plot_overall(curve: pd.DataFrame, figures: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(curve["weak_overall"], curve["win_rate"] * 100, marker="o", color=PALETTE["blue"])
    axes[0].fill_between(curve["weak_overall"], curve["win_ci_low"] * 100, curve["win_ci_high"] * 100, color=PALETTE["blue"], alpha=.15)
    axes[0].set(title="Underdog win probability vs an 85 team", xlabel="Underdog overall", ylabel="Win rate (%)", ylim=(-2, 55))
    axes[1].plot(curve["weak_overall"], curve["mean_round_margin"], marker="o", color=PALETTE["orange"])
    axes[1].axhline(0, color=PALETTE["slate"], linewidth=1)
    axes[1].set(title="Talent gap shows up strongly in round margin", xlabel="Underdog overall", ylabel="Mean underdog round margin")
    fig.tight_layout()
    fig.savefig(figures / "overall_curve.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_requested(requested: pd.DataFrame, figures: Path) -> None:
    data = requested[requested["context"].str.contains("75v80")].sort_values("rounds_won_added")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    y = np.arange(len(data))
    ax.errorbar(
        data["rounds_won_added"], y,
        xerr=[data["rounds_won_added"] - data["rounds_won_added_ci_low"], data["rounds_won_added_ci_high"] - data["rounds_won_added"]],
        fmt="o", color=PALETTE["blue"], ecolor="#94A3B8", capsize=3,
    )
    ax.axvline(0, color=PALETTE["slate"], linewidth=1)
    ax.set(yticks=y, yticklabels=data["lever"], xlabel="Additional rounds won per match vs stated baseline", title="Requested levers in the close 75-vs-80 matchup")
    fig.tight_layout()
    fig.savefig(figures / "requested_levers_close_gap.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_equal_management(effects: pd.DataFrame, figures: Path) -> None:
    data = effects[effects["context"].str.startswith("equal_75v75")].copy()
    data = data.reindex(data["rounds_won_added"].abs().sort_values().index).tail(18)
    data["label"] = data["factor"].str.replace("_", " ") + ": " + data["treatment_level"].astype(str)
    fig, ax = plt.subplots(figsize=(10, 7))
    colors = [PALETTE["orange"] if value < 0 else PALETTE["blue"] for value in data["rounds_won_added"]]
    ax.barh(data["label"], data["rounds_won_added"], color=colors)
    ax.axvline(0, color=PALETTE["slate"], linewidth=1)
    ax.set(xlabel="Additional rounds won per match vs neutral baseline", title="Management treatments with identical 75-overall players")
    fig.tight_layout()
    fig.savefig(figures / "equal_talent_management.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_seed_robustness(effects: pd.DataFrame, figures: Path) -> pd.DataFrame:
    data = effects.copy()
    data["abs_effect"] = data["weak_round_margin_effect"].abs()
    top = data.sort_values("abs_effect", ascending=False).groupby("context", observed=True).head(8)
    rows = []
    for _, row in top.iterrows():
        for block, effect in row["seed_block_effects"].items():
            rows.append({"context": row["context"], "factor": row["factor"], "seed_block": block, "effect": effect})
    robust = pd.DataFrame(rows)
    if robust.empty:
        return robust
    close = robust[robust["context"].str.contains("75v80")]
    if close.empty:
        close = robust.head(24)
    pivot = close.pivot_table(index="factor", columns="seed_block", values="effect", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(8, max(4, .45 * len(pivot))))
    sns.heatmap(pivot, cmap="vlag", center=0, annot=True, fmt=".2f", ax=ax, cbar_kws={"label": "Round-margin effect"})
    ax.set(title="Top effects reproduce across held-out seed blocks", xlabel="Seed block", ylabel="Factor")
    fig.tight_layout()
    fig.savefig(figures / "seed_block_robustness.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return robust


def run_analysis(
    primary_path: Path,
    supplement_path: Path,
    equal_core_path: Path,
    equal_mechanisms_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = output_dir / "tables"
    figures = output_dir / "figures"
    tables.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    sources = {
        "primary": load_dataset(primary_path, "primary"),
        "supplement": load_dataset(supplement_path, "supplement"),
        "equal_core": load_dataset(equal_core_path, "equal_core"),
        "equal_mechanisms": load_dataset(equal_mechanisms_path, "equal_mechanisms"),
    }
    combined = pd.concat(sources.values(), ignore_index=True, sort=False)
    quality = pd.DataFrame([
        {
            "source": name, "rows": len(frame), "cells": frame["cell_id"].nunique(),
            "contexts": frame["context"].nunique(), "factors": frame["factor"].nunique(),
            "maps": frame["map_id"].nunique(), "seed_blocks": frame["seed_block"].nunique(),
            "duplicate_pairing_rows": int(frame.duplicated(["version_id", *PAIR_KEYS]).sum()),
        }
        for name, frame in sources.items()
    ])
    curve = overall_curve(sources["primary"])
    effects = all_factor_effects(combined)
    baselines = baseline_effects(combined)
    requested = requested_comparisons(combined)
    language = exact_language_check(sources["supplement"])
    mechanism_levels = (
        sources["supplement"]
        .groupby(["context", "factor", "level"], observed=True)
        .agg(
            matches=("weak_win", "size"),
            effective_weak_quality=("weak_quality", "mean"),
            weak_win_rate=("weak_win", "mean"),
            mean_weak_round_margin=("weak_round_margin", "mean"),
            assignment_comfort=("weak_assignment_comfort", "mean"),
            igl_experience=("weak_igl_experience", "mean"),
        )
        .reset_index()
    )
    robust = _plot_seed_robustness(effects, figures)

    curve.to_csv(tables / "overall_curve.csv", index=False)
    effects.drop(columns=["seed_block_effects", "seed_block_rounds_won_added"]).to_csv(tables / "factor_effects.csv", index=False)
    baselines.drop(columns=["seed_block_effects", "seed_block_rounds_won_added"]).to_csv(tables / "baseline_rounds_added.csv", index=False)
    requested.drop(columns=["seed_block_effects", "seed_block_rounds_won_added"]).to_csv(tables / "requested_levers.csv", index=False)
    mechanism_levels.to_csv(tables / "mechanism_levels.csv", index=False)
    quality.to_csv(tables / "data_quality.csv", index=False)
    robust.to_csv(tables / "seed_block_robustness.csv", index=False)
    _plot_overall(curve, figures)
    _plot_requested(requested, figures)
    _plot_equal_management(baselines, figures)

    win65 = curve.loc[curve["weak_overall"] == 65].iloc[0]
    win80 = curve.loc[curve["weak_overall"] == 80].iloc[0]
    margin75 = float(curve.loc[curve["weak_overall"] == 75, "mean_round_margin"].iloc[0])
    margin80 = float(curve.loc[curve["weak_overall"] == 80, "mean_round_margin"].iloc[0])
    local_slope = (margin80 - margin75) / 5
    requested["local_overall_equivalent_points"] = requested["weak_round_margin_effect"] / local_slope
    requested.to_csv(tables / "requested_levers_with_equivalents.csv", index=False)

    # Exact algebraic QA: score improvement + opponent score reduction = margin improvement.
    max_reconciliation_error = float(max(
        effects["margin_reconciliation_error"].abs().max(),
        baselines["margin_reconciliation_error"].abs().max(),
        requested["margin_reconciliation_error"].abs().max(),
    ))
    if max_reconciliation_error > 1e-12:
        raise AssertionError(f"round outcome reconciliation failed: {max_reconciliation_error}")

    equal = baselines[baselines["context"].str.startswith("equal_75v75")].copy()
    equal["absolute_rounds_added"] = equal["rounds_won_added"].abs()
    equal = equal.sort_values("absolute_rounds_added", ascending=False)
    summary = {
        "total_matches": int(len(combined)),
        "dataset_rows": {name: int(len(frame)) for name, frame in sources.items()},
        "overall_65_vs_85": {
            "wins": int(win65["wins"]), "matches": int(win65["matches"]),
            "win_rate": float(win65["win_rate"]), "mean_round_margin": float(win65["mean_round_margin"]),
        },
        "overall_80_vs_85": {
            "wins": int(win80["wins"]), "matches": int(win80["matches"]),
            "win_rate": float(win80["win_rate"]), "mean_round_margin": float(win80["mean_round_margin"]),
        },
        "round_margin_per_overall_point_75_to_80": local_slope,
        "rounds_added_definition": "mean paired treatment weak_score minus baseline weak_score",
        "opponent_rounds_denied_definition": "mean paired baseline strong_score minus treatment strong_score",
        "max_margin_reconciliation_error": max_reconciliation_error,
        "language_no_common_equals_shared_50": language,
        "top_equal_talent_management_factors": equal.head(12)[
            ["context", "factor", "baseline_level", "treatment_level", "rounds_won_added", "opponent_rounds_denied", "weak_round_margin_effect", "weak_win_effect_pp", "seed_block_sign_agreement"]
        ].to_dict(orient="records"),
        "requested_levers": requested[
            ["context", "lever", "low_level", "high_level", "rounds_won_added", "rounds_won_added_ci_low", "rounds_won_added_ci_high", "opponent_rounds_denied", "weak_round_margin_effect", "win_effect_pp", "local_overall_equivalent_points", "seed_block_sign_agreement"]
        ].to_dict(orient="records"),
    }
    (output_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--equal-core", type=Path, required=True)
    parser.add_argument("--equal-mechanisms", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run_analysis(args.primary, args.supplement, args.equal_core, args.equal_mechanisms, args.out)
    print(json.dumps(result, indent=2))
