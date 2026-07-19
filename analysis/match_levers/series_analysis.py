"""Measure how BO3 and BO5 formats amplify team-strength advantages."""

from __future__ import annotations

import argparse
from hashlib import blake2b
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.proportion import proportion_confint


MAPS = ("ascent", "bind", "haven", "lotus", "split")
FORMAT_ORDER = ("BO1", "BO3", "BO5")


def _map_order(seed: int, identity_swap: int) -> list[str]:
    return sorted(
        MAPS,
        key=lambda map_id: blake2b(
            f"series-reconstruct:{seed}:{identity_swap}:{map_id}".encode("utf-8"),
            digest_size=8,
        ).digest(),
    )


def _reconstruct(frame: pd.DataFrame, matchup: str) -> pd.DataFrame:
    rows = []
    for (seed, identity_swap), group in frame.groupby(["seed", "identity_swap"], observed=True):
        outcomes = {row.map_id: int(row.weak_win) for row in group.itertuples()}
        if set(outcomes) != set(MAPS):
            raise ValueError(f"{matchup} seed {seed}/swap {identity_swap} lacks all maps")
        order = _map_order(int(seed), int(identity_swap))
        rows.append({
            "matchup": matchup,
            "seed": int(seed),
            "identity_swap": int(identity_swap),
            "BO1": sum(outcomes.values()) / len(MAPS),
            "BO3": int(sum(outcomes[map_id] for map_id in order[:3]) >= 2),
            "BO5": int(sum(outcomes.values()) >= 3),
        })
    return pd.DataFrame(rows)


def _cluster_ci(frame: pd.DataFrame, column: str) -> tuple[float, float, float]:
    estimate = float(frame[column].mean())
    clusters = frame.groupby("seed", observed=True)[column].mean()
    if len(clusters) < 2 or float(clusters.std(ddof=1)) == 0:
        return estimate, estimate, estimate
    sem = float(clusters.std(ddof=1) / np.sqrt(len(clusters)))
    critical = float(stats.t.ppf(0.975, len(clusters) - 1))
    return estimate, max(0.0, estimate - critical * sem), min(1.0, estimate + critical * sem)


def _plot_favorites(summary: pd.DataFrame, target: Path) -> None:
    data = summary[summary["team_role"] == "favorite"].copy()
    colors = {
        "65 vs 85": "#475569",
        "75 vs 85": "#EA580C",
        "75 vs 80": "#CA8A04",
        "80 vs 85": "#2563EB",
    }
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = np.arange(len(FORMAT_ORDER))
    for matchup, group in data.groupby("matchup", sort=False):
        ordered = group.set_index("format").reindex(FORMAT_ORDER)
        ax.plot(
            x,
            ordered["win_rate"] * 100,
            marker="o",
            linewidth=2.2,
            label=matchup,
            color=colors[matchup],
        )
    ax.set(
        xticks=x,
        xticklabels=FORMAT_ORDER,
        ylim=(65, 103),
        xlabel="Series format",
        ylabel="Favorite series win rate (%)",
    )
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8)
    ax.legend(title="Normalized matchup", frameon=False, ncol=2, loc="lower right")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)


def run_series_analysis(
    primary_path: Path,
    supplement_path: Path,
    identical_series_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = output_dir / "tables"
    figures = output_dir / "figures"
    tables.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    primary = pd.read_csv(primary_path, low_memory=False)
    supplement = pd.read_csv(supplement_path, low_memory=False)
    reconstructed = []
    for level in (65, 75, 80):
        selected = primary[
            (primary["factor"] == "weak_overall")
            & (primary["level_numeric"] == level)
        ]
        reconstructed.append(_reconstruct(selected, f"{level} vs 85"))
    selected = supplement[
        (supplement["context"] == "normalized_75v80_supplement")
        & (supplement["factor"] == "shared_language")
        & (supplement["level"].astype(str) == "50")
    ]
    reconstructed.append(_reconstruct(selected, "75 vs 80"))
    historical = pd.concat(reconstructed, ignore_index=True)

    summary_rows = []
    for matchup, group in historical.groupby("matchup", sort=False):
        for format_id in FORMAT_ORDER:
            underdog, low, high = _cluster_ci(group, format_id)
            summary_rows.append({
                "matchup": matchup,
                "format": format_id,
                "team_role": "favorite",
                "win_rate": 1 - underdog,
                "ci_low": 1 - high,
                "ci_high": 1 - low,
                "underdog_win_rate": underdog,
                "series_rows": len(group) if format_id != "BO1" else len(group) * len(MAPS),
                "seed_clusters": int(group["seed"].nunique()),
            })

    identical = pd.read_csv(identical_series_path)
    identical_details = []
    for best_of, group in identical.groupby("best_of", observed=True):
        wins = int(group["designated_series_win"].sum())
        low, high = proportion_confint(wins, len(group), alpha=0.05, method="wilson")
        summary_rows.append({
            "matchup": "75 vs 75 identical",
            "format": f"BO{int(best_of)}",
            "team_role": "designated equal team",
            "win_rate": wins / len(group),
            "ci_low": float(low),
            "ci_high": float(high),
            "underdog_win_rate": float("nan"),
            "series_rows": len(group),
            "seed_clusters": int(group["series_seed"].nunique()),
        })
        identical_details.append({
            "format": f"BO{int(best_of)}",
            "series": len(group),
            "wins": wins,
            "win_rate": wins / len(group),
            "average_maps_played": float(group["maps_played"].mean()),
            "decider_rate": float((group["maps_played"] == best_of).mean()),
        })
    paired = identical.pivot(
        index="series_seed", columns="best_of", values="designated_series_win"
    )
    winner_flip_rate = float((paired[3] != paired[5]).mean())

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(tables / "series_format_win_rates.csv", index=False)
    _plot_favorites(summary, figures / "series_format_favorite_win_rates.png")
    result = {
        "method": (
            "BO3 and BO5 use the same series seed, deterministic map order, and per-map "
            "outcomes; historical matchup intervals cluster identity orientations by seed"
        ),
        "favorite_win_rates": summary[summary["team_role"] == "favorite"].to_dict(orient="records"),
        "identical_team_series": identical_details,
        "identical_bo3_bo5_winner_flip_rate": winner_flip_rate,
    }
    (output_dir / "series_format_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--identical-series", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(run_series_analysis(
        args.primary, args.supplement, args.identical_series, args.out
    ), indent=2))
