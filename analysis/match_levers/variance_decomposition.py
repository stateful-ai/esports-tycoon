"""Functional-ANOVA decomposition of deterministic match outcome variance."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


FACTORS = ("version_id", "map_id", "identity_swap", "seed")
DISPLAY = {
    "version_id": "Treatment configuration",
    "map_id": "Map",
    "identity_swap": "Stable identity / orientation",
    "seed": "Seed randomness",
}
COLORS = {
    "version_id": "#2563EB",
    "map_id": "#CA8A04",
    "identity_swap": "#EA580C",
    "seed": "#475569",
}


def _functional_anova(
    frame: pd.DataFrame,
    outcome: str,
    factors: tuple[str, ...],
) -> dict[str, Any]:
    grand = float(frame[outcome].mean())
    total_ss = float(((frame[outcome] - grand) ** 2).sum())
    pure: dict[tuple[str, ...], float] = {}
    for size in range(1, len(factors) + 1):
        for subset in itertools.combinations(factors, size):
            grouped = frame.groupby(list(subset), observed=True)[outcome].agg(["mean", "size"])
            marginal_ss = float((grouped["size"] * (grouped["mean"] - grand) ** 2).sum())
            lower_ss = sum(value for key, value in pure.items() if set(key) < set(subset))
            pure[subset] = marginal_ss - lower_ss
    if min(pure.values(), default=0.0) < -1e-7:
        raise AssertionError("functional ANOVA produced a negative component")
    shapley = {factor: 0.0 for factor in factors}
    total_effect = {factor: 0.0 for factor in factors}
    for subset, component_ss in pure.items():
        for factor in subset:
            shapley[factor] += component_ss / len(subset)
            total_effect[factor] += component_ss
    return {
        "grand_mean": grand,
        "total_variance": float(frame[outcome].var(ddof=0)),
        "total_ss": total_ss,
        "pure": pure,
        "shapley": shapley,
        "total_effect": total_effect,
    }


def _family(factor: str) -> str:
    if factor == "weak_overall":
        return "Overall talent"
    if factor.startswith("skill_") or factor in {
        "roster_shape", "micro_bundle", "tactical_bundle", "mental_bundle",
        "role_assignment", "role_comfort",
    }:
        return "Player mechanics / role"
    if factor in {
        "form", "morale", "stamina", "confidence", "agent_mastery",
        "map_mastery", "igl_experience", "shared_language",
    }:
        return "Readiness / mastery"
    return "Strategy / management"


def _dataset_decomposition(
    frame: pd.DataFrame,
    label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    result = _functional_anova(frame, "weak_round_margin", FACTORS)
    rows = []
    for factor in FACTORS:
        rows.append({
            "dataset": label,
            "component": factor,
            "component_label": DISPLAY[factor],
            "fair_share_pct": 100 * result["shapley"][factor] / result["total_ss"],
            "direct_main_pct": 100 * result["pure"][(factor,)] / result["total_ss"],
            "total_effect_pct": 100 * result["total_effect"][factor] / result["total_ss"],
        })

    version_means = (
        frame.groupby(["version_id", "factor"], observed=True)["weak_round_margin"]
        .mean()
        .reset_index()
    )
    observations_per_version = len(frame) / len(version_means)
    version_means["family"] = version_means["factor"].map(_family)
    version_means["effect"] = version_means["weak_round_margin"] - result["grand_mean"]
    direct_treatment_ss = result["pure"][("version_id",)]
    families = []
    for family, group in version_means.groupby("family", observed=True):
        family_ss = observations_per_version * float((group["effect"] ** 2).sum())
        families.append({
            "dataset": label,
            "family": family,
            "versions": len(group),
            "share_of_direct_treatment_pct": 100 * family_ss / direct_treatment_ss,
            "share_of_total_variance_pct": 100 * family_ss / result["total_ss"],
        })
    metadata = {
        "rows": len(frame),
        "versions": int(frame["version_id"].nunique()),
        "maps": int(frame["map_id"].nunique()),
        "seeds": int(frame["seed"].nunique()),
        "grand_mean_round_margin": result["grand_mean"],
        "round_margin_variance": result["total_variance"],
    }
    return rows, families, metadata


def _baseline_decomposition(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = frame.copy()
    data["team_a_round_margin"] = data["weak_round_margin"].where(
        data["weak_team_id"] == "team_nexus",
        -data["weak_round_margin"],
    )
    result = _functional_anova(data, "team_a_round_margin", ("map_id", "seed"))
    rows = []
    for factor in ("map_id", "seed"):
        rows.append({
            "dataset": "Identical 75-vs-75 baseline",
            "component": factor,
            "component_label": DISPLAY[factor],
            "fair_share_pct": 100 * result["shapley"][factor] / result["total_ss"],
            "direct_main_pct": 100 * result["pure"][(factor,)] / result["total_ss"],
            "total_effect_pct": 100 * result["total_effect"][factor] / result["total_ss"],
        })
    metadata = {
        "rows": len(data),
        "unique_map_seed_pairs": int(data[["map_id", "seed"]].drop_duplicates().shape[0]),
        "maps": int(data["map_id"].nunique()),
        "seeds": int(data["seed"].nunique()),
        "team_a_mean_round_margin": result["grand_mean"],
        "round_margin_variance": result["total_variance"],
        "map_seed_interaction_pct": (
            100 * result["pure"][("map_id", "seed")] / result["total_ss"]
        ),
    }
    return rows, metadata


def _plot_components(components: pd.DataFrame, target: Path) -> None:
    order = [
        "Broad 65-vs-85 lever sweep",
        "Equal-player management sweep",
        "Identical 75-vs-75 baseline",
    ]
    pivot = (
        components.pivot(index="dataset", columns="component", values="fair_share_pct")
        .reindex(order)
        .fillna(0.0)
    )
    fig, ax = plt.subplots(figsize=(11, 4.8))
    left = pd.Series(0.0, index=pivot.index)
    for component in FACTORS:
        if component not in pivot:
            continue
        values = pivot[component]
        ax.barh(
            pivot.index,
            values,
            left=left,
            label=DISPLAY[component],
            color=COLORS[component],
            edgecolor="#FFFFFF",
            linewidth=0.8,
        )
        for index, value in enumerate(values):
            if value >= 7:
                ax.text(left.iloc[index] + value / 2, index, f"{value:.1f}%", ha="center", va="center", color="white", fontsize=9)
        left += values
    ax.set(xlim=(0, 100), xlabel="Fair-share attribution of round-margin variance (%)", ylabel="")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.15), frameon=False)
    ax.grid(axis="x", color="#E2E8F0", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_families(families: pd.DataFrame, target: Path) -> None:
    data = families[families["dataset"] == "Broad 65-vs-85 lever sweep"].copy()
    data = data.sort_values("share_of_direct_treatment_pct")
    colors = {
        "Overall talent": "#2563EB",
        "Player mechanics / role": "#EA580C",
        "Readiness / mastery": "#CA8A04",
        "Strategy / management": "#475569",
    }
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.barh(data["family"], data["share_of_direct_treatment_pct"], color=[colors[value] for value in data["family"]])
    for index, value in enumerate(data["share_of_direct_treatment_pct"]):
        ax.text(value + 1, index, f"{value:.1f}%", va="center", fontsize=10)
    ax.set(xlim=(0, 100), xlabel="Share of direct treatment-configuration variance (%)", ylabel="")
    ax.grid(axis="x", color="#E2E8F0", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)


def run_decomposition(
    primary_path: Path,
    equal_core_path: Path,
    baseline_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = output_dir / "tables"
    figures = output_dir / "figures"
    tables.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    primary = pd.read_csv(primary_path, low_memory=False)
    equal = pd.read_csv(equal_core_path, low_memory=False)
    baseline = pd.read_csv(baseline_path, low_memory=False)
    component_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    for frame, label, key in (
        (primary, "Broad 65-vs-85 lever sweep", "primary"),
        (equal, "Equal-player management sweep", "equal_core"),
    ):
        components, families, details = _dataset_decomposition(frame, label)
        component_rows.extend(components)
        family_rows.extend(families)
        metadata[key] = details
    baseline_components, baseline_details = _baseline_decomposition(baseline)
    component_rows.extend(baseline_components)
    metadata["symmetry_baseline"] = baseline_details

    components = pd.DataFrame(component_rows)
    families = pd.DataFrame(family_rows)
    components.to_csv(tables / "variance_decomposition.csv", index=False)
    families.to_csv(tables / "treatment_family_decomposition.csv", index=False)
    _plot_components(components, figures / "variance_decomposition.png")
    _plot_families(families, figures / "treatment_family_decomposition.png")

    summary = {
        "method": (
            "balanced functional ANOVA with interaction sums of squares split equally "
            "among participating factors (Shapley fair-share attribution)"
        ),
        "metadata": metadata,
        "components": component_rows,
        "treatment_families": family_rows,
    }
    (output_dir / "variance_decomposition.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--equal-core", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(run_decomposition(args.primary, args.equal_core, args.baseline, args.out), indent=2))
