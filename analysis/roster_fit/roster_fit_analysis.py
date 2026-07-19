"""Analyze paired roster-composition by one-dial series experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PROFILE_ORDER = ["fraggers", "balanced", "mixed", "tacticians"]
DIAL_ORDER = ["aggression", "pace", "util_discipline", "map_control"]
DIAL_LABELS = {
    "aggression": "Aggression",
    "pace": "Pace",
    "util_discipline": "Utility discipline",
    "map_control": "Map control",
}
PROFILE_LABELS = {
    "fraggers": "Frag-heavy",
    "balanced": "Balanced",
    "mixed": "Mixed 2/3",
    "tacticians": "Tactical",
}


def _plot_bo3_heatmaps(effects: pd.DataFrame, path: Path) -> None:
    selected = effects[effects["best_of"] == 3]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8), sharey=True)
    values = selected["series_win_lift_pp"].abs()
    bound = max(5.0, float(values.max()))
    image = None
    for axis, pole in zip(axes, (0.0, 100.0)):
        matrix = (
            selected[selected["treatment_value"] == pole]
            .pivot(index="dial", columns="roster_profile", values="series_win_lift_pp")
            .reindex(index=DIAL_ORDER, columns=PROFILE_ORDER)
        )
        image = axis.imshow(
            matrix.to_numpy(),
            cmap="RdBu",
            vmin=-bound,
            vmax=bound,
            aspect="auto",
        )
        axis.set_title(f"Dial moved to {pole:g}")
        axis.set_xticks(range(len(PROFILE_ORDER)), [PROFILE_LABELS[p] for p in PROFILE_ORDER])
        axis.tick_params(axis="x", rotation=25)
        axis.set_yticks(range(len(DIAL_ORDER)), [DIAL_LABELS[d] for d in DIAL_ORDER])
        for row in range(len(DIAL_ORDER)):
            for column in range(len(PROFILE_ORDER)):
                value = matrix.iloc[row, column]
                axis.text(
                    column,
                    row,
                    f"{value:+.1f}",
                    ha="center",
                    va="center",
                    color="white" if abs(value) > bound * 0.55 else "#172033",
                    fontsize=10,
                    fontweight="bold",
                )
    color_axis = fig.add_axes([0.91, 0.18, 0.018, 0.62])
    fig.colorbar(
        image,
        cax=color_axis,
        label="BO3 win-rate lift vs neutral (percentage points)",
    )
    fig.suptitle("The same plan change produces different outcomes by roster shape", fontweight="bold")
    fig.subplots_adjust(left=0.12, right=0.88, bottom=0.19, top=0.84, wspace=0.10)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_fit_interactions(interactions: pd.DataFrame, path: Path) -> None:
    selected = interactions[interactions["best_of"] == 3].copy()
    x = np.arange(len(DIAL_ORDER))
    width = 0.34
    fig, axis = plt.subplots(figsize=(11, 5.8))
    for offset, pole, color in ((-width / 2, 0.0, "#6d5dfc"), (width / 2, 100.0, "#e7632f")):
        frame = selected[selected["treatment_value"] == pole].set_index("dial").reindex(DIAL_ORDER)
        values = frame["fit_interaction_win_pp"].to_numpy()
        low = values - frame["fit_interaction_win_ci_low"].to_numpy()
        high = frame["fit_interaction_win_ci_high"].to_numpy() - values
        axis.bar(
            x + offset,
            values,
            width,
            label=f"Dial {pole:g}",
            color=color,
            yerr=np.vstack([low, high]),
            capsize=4,
        )
    axis.axhline(0, color="#5e6879", linewidth=1)
    axis.set_xticks(x, [DIAL_LABELS[d] for d in DIAL_ORDER])
    axis.set_ylabel("Aligned minus mismatched BO3 win lift (pp)")
    axis.set_title("Roster fit changes the value of the same game-plan treatment", fontweight="bold")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_fit_response(effects: pd.DataFrame, path: Path) -> None:
    selected = effects[(effects["best_of"] == 3) & effects["roster_profile"].isin(["fraggers", "tacticians"])]
    fig, axis = plt.subplots(figsize=(9.5, 6))
    colors = {0.0: "#6d5dfc", 100.0: "#e7632f"}
    for pole, frame in selected.groupby("treatment_value"):
        axis.scatter(
            frame["expected_fit_edge"],
            frame["round_margin_added_per_map"],
            s=72,
            alpha=0.85,
            color=colors[float(pole)],
            label=f"Dial {pole:g}",
        )
    if len(selected) >= 2:
        coefficients = np.polyfit(
            selected["expected_fit_edge"],
            selected["round_margin_added_per_map"],
            1,
        )
        x = np.linspace(selected["expected_fit_edge"].min(), selected["expected_fit_edge"].max(), 100)
        axis.plot(x, coefficients[0] * x + coefficients[1], color="#27364f", linewidth=2)
    axis.axhline(0, color="#5e6879", linewidth=1)
    axis.axvline(0, color="#5e6879", linewidth=1, linestyle="--")
    axis.set_xlabel("Engine roster-fit edge at the treatment pole")
    axis.set_ylabel("Round-margin improvement per map")
    axis.set_title("Execution fit predicts whether a plan gains or loses rounds", fontweight="bold")
    axis.legend(frameon=False)
    axis.grid(alpha=0.22)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _global_vs_roster_decomposition(effects: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for best_of, frame in effects.groupby("best_of"):
        for outcome in ("series_win_lift_pp", "round_margin_added_per_map"):
            values = frame[outcome]
            grand_mean = values.mean()
            group_means = frame.groupby(["dial", "treatment_value"])[outcome].transform("mean")
            total_ss = float(((values - grand_mean) ** 2).sum())
            global_ss = float(((group_means - grand_mean) ** 2).sum())
            roster_ss = float(((values - group_means) ** 2).sum())
            rows.append({
                "best_of": int(best_of),
                "outcome": outcome,
                "global_dial_pole_share": global_ss / total_ss if total_ss else 0.0,
                "roster_specific_share": roster_ss / total_ss if total_ss else 0.0,
                "total_ss": total_ss,
            })
    return pd.DataFrame(rows)


def _plot_global_vs_roster(decomposition: pd.DataFrame, path: Path) -> None:
    frame = decomposition.copy()
    frame["label"] = frame.apply(
        lambda row: f"BO{int(row.best_of)} "
        + ("win lift" if row.outcome == "series_win_lift_pp" else "round margin"),
        axis=1,
    )
    x = np.arange(len(frame))
    global_values = 100 * frame["global_dial_pole_share"].to_numpy()
    roster_values = 100 * frame["roster_specific_share"].to_numpy()
    fig, axis = plt.subplots(figsize=(9.5, 5.8))
    axis.bar(x, global_values, color="#59677f", label="Global dial + pole")
    axis.bar(
        x,
        roster_values,
        bottom=global_values,
        color="#5e72e4",
        label="Roster-specific residual",
    )
    for index, (global_value, roster_value) in enumerate(zip(global_values, roster_values)):
        axis.text(index, global_value / 2, f"{global_value:.0f}%", ha="center", va="center", color="white", fontweight="bold")
        axis.text(index, global_value + roster_value / 2, f"{roster_value:.0f}%", ha="center", va="center", color="white", fontweight="bold")
    axis.set_xticks(x, frame["label"])
    axis.set_ylim(0, 100)
    axis.set_ylabel("Share of treatment-cell variation (%)")
    axis.set_title("Global dial direction dominates roster-specific variation", fontweight="bold")
    axis.legend(
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
    )
    fig.subplots_adjust(bottom=0.22, top=0.88)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def analyze(run_dir: Path, output_dir: Path) -> dict:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    effects = pd.DataFrame(summary["effects"])
    interactions = pd.DataFrame(summary["fit_interactions"])
    series = pd.read_csv(run_dir / "series.csv")
    tables = output_dir / "tables"
    figures = output_dir / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    effects.to_csv(tables / "roster_fit_effects.csv", index=False)
    interactions.to_csv(tables / "roster_fit_interactions.csv", index=False)
    decomposition = _global_vs_roster_decomposition(effects)
    decomposition.to_csv(tables / "global_vs_roster_decomposition.csv", index=False)

    profile_attributes = pd.DataFrame([
        {
            "roster_profile": profile,
            "player_slot": slot + 1,
            **attributes,
            "arithmetic_overall": sum(attributes.values()) / len(attributes),
        }
        for profile in ("balanced", "fraggers", "tacticians", "mixed")
        for slot, attributes in enumerate(
            __import__(
                "scripts.roster_fit_series_experiment",
                fromlist=["_profile_players"],
            )._profile_players(profile, 75.0)
        )
    ])
    profile_attributes.to_csv(tables / "roster_profile_attributes.csv", index=False)

    _plot_bo3_heatmaps(effects, figures / "bo3_roster_plan_heatmap.png")
    _plot_fit_interactions(interactions, figures / "bo3_fit_interactions.png")
    _plot_fit_response(effects, figures / "fit_response_round_margin.png")
    _plot_global_vs_roster(
        decomposition,
        figures / "global_vs_roster_decomposition.png",
    )

    control = (
        series.groupby(["roster_profile", "best_of"], as_index=False)
        .agg(
            control_win_rate=("control_series_win", "mean"),
            series_rows=("control_series_win", "size"),
        )
    )
    control.to_csv(tables / "control_symmetry.csv", index=False)
    raw_correlation = float(
        effects["expected_fit_edge"].corr(effects["round_margin_added_per_map"])
    )
    effects["treatment_cell"] = (
        effects["dial"]
        + ":"
        + effects["treatment_value"].astype(str)
        + ":"
        + effects["best_of"].astype(str)
    )
    effects["fit_demeaned"] = effects["expected_fit_edge"] - effects.groupby(
        "treatment_cell"
    )["expected_fit_edge"].transform("mean")
    effects["margin_demeaned"] = effects["round_margin_added_per_map"] - effects.groupby(
        "treatment_cell"
    )["round_margin_added_per_map"].transform("mean")
    within_fit_correlation = float(
        effects["fit_demeaned"].corr(effects["margin_demeaned"])
    )
    within_fit_slope = float(
        (effects["fit_demeaned"] * effects["margin_demeaned"]).sum()
        / (effects["fit_demeaned"] ** 2).sum()
    )
    bo3_round_decomp = decomposition[
        (decomposition["best_of"] == 3)
        & (decomposition["outcome"] == "round_margin_added_per_map")
    ].iloc[0]
    bo3_interactions = interactions[interactions["best_of"] == 3]
    result = {
        "run_dir": str(run_dir.resolve()),
        "effects_rows": len(effects),
        "interaction_rows": len(interactions),
        "series_rows": len(series),
        "fit_round_margin_raw_correlation": raw_correlation,
        "fit_round_margin_within_treatment_correlation": within_fit_correlation,
        "fit_round_margin_within_treatment_slope": within_fit_slope,
        "bo3_round_global_dial_pole_share": float(bo3_round_decomp["global_dial_pole_share"]),
        "bo3_round_roster_specific_share": float(bo3_round_decomp["roster_specific_share"]),
        "bo3_interaction_min_pp": float(bo3_interactions["fit_interaction_win_pp"].min()),
        "bo3_interaction_max_pp": float(bo3_interactions["fit_interaction_win_pp"].max()),
        "control_win_rate_min": float(control["control_win_rate"].min()),
        "control_win_rate_max": float(control["control_win_rate"].max()),
        "tables": {
            "effects": str((tables / "roster_fit_effects.csv").resolve()),
            "interactions": str((tables / "roster_fit_interactions.csv").resolve()),
            "profiles": str((tables / "roster_profile_attributes.csv").resolve()),
            "control": str((tables / "control_symmetry.csv").resolve()),
            "decomposition": str((tables / "global_vs_roster_decomposition.csv").resolve()),
        },
        "figures": {
            "heatmap": str((figures / "bo3_roster_plan_heatmap.png").resolve()),
            "interactions": str((figures / "bo3_fit_interactions.png").resolve()),
            "fit_response": str((figures / "fit_response_round_margin.png").resolve()),
            "decomposition": str((figures / "global_vs_roster_decomposition.png").resolve()),
        },
    }
    (output_dir / "analysis_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("analysis/roster_fit/output"),
    )
    args = parser.parse_args()
    print(json.dumps(analyze(args.run_dir, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
