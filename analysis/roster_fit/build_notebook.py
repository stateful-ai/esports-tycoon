"""Build and execute the roster-fit series analysis notebook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def build_notebook(run_dir: Path, output_dir: Path, target: Path) -> None:
    summary = json.loads((output_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    effects_path = output_dir / "tables" / "roster_fit_effects.csv"
    interactions_path = output_dir / "tables" / "roster_fit_interactions.csv"
    control_path = output_dir / "tables" / "control_symmetry.csv"
    heatmap_path = output_dir / "figures" / "bo3_roster_plan_heatmap.png"
    interaction_figure = output_dir / "figures" / "bo3_fit_interactions.png"
    response_figure = output_dir / "figures" / "fit_response_round_margin.png"
    decomposition_figure = output_dir / "figures" / "global_vs_roster_decomposition.png"

    notebook = nbformat.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook["metadata"]["language_info"] = {"name": "python", "version": "3"}
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "## tl;dr\n"
            "This notebook answers whether changing one game-plan dial matters "
            "because it fits the roster, rather than because that dial has one "
            "globally optimal setting. Every comparison holds the players, "
            "opponent, identity orientation, map order, and seeds fixed."
        ),
        nbformat.v4.new_markdown_cell(
            "## Context & Methods\n"
            "Both teams use mechanically mirrored 75-overall rosters. The neutral "
            "control leaves every tactics dial at 50; the treatment moves exactly "
            "one designated-team dial to 0 or 100. The four roster shapes are "
            "balanced, frag-heavy, tactical, and a two-fragger/three-tactician mix. "
            "BO3 and BO5 are reconstructed from the same five deterministic maps.\n\n"
            "### Key Assumptions\n"
            "- Each roster profile is synthetic and deliberately polarized.\n"
            "- Series do not model between-map fatigue, substitutions, adaptation, or vetoes.\n"
            "- Percentage-point lift is paired treatment minus neutral-control series wins."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\n"
            "import pandas as pd\n"
            "from IPython.display import Image, display\n\n"
            f"RUN_DIR = Path({str(run_dir.resolve())!r})\n"
            f"EFFECTS_PATH = Path({str(effects_path.resolve())!r})\n"
            f"INTERACTIONS_PATH = Path({str(interactions_path.resolve())!r})\n"
            f"CONTROL_PATH = Path({str(control_path.resolve())!r})\n"
            f"HEATMAP_PATH = Path({str(heatmap_path.resolve())!r})\n"
            f"INTERACTION_FIGURE = Path({str(interaction_figure.resolve())!r})\n"
            f"RESPONSE_FIGURE = Path({str(response_figure.resolve())!r})\n"
            f"DECOMPOSITION_FIGURE = Path({str(decomposition_figure.resolve())!r})\n"
        ),
        nbformat.v4.new_markdown_cell("## Data\n### 1. Load paired outcomes and summaries"),
        nbformat.v4.new_code_cell(
            "series = pd.read_csv(RUN_DIR / 'series.csv')\n"
            "maps = pd.read_csv(RUN_DIR / 'series_maps.csv')\n"
            "effects = pd.read_csv(EFFECTS_PATH)\n"
            "interactions = pd.read_csv(INTERACTIONS_PATH)\n"
            "control = pd.read_csv(CONTROL_PATH)\n"
            "{'series_rows': len(series), 'map_rows': len(maps), "
            "'effect_cells': len(effects), 'interaction_cells': len(interactions)}"
        ),
        nbformat.v4.new_markdown_cell("### 2. Validate the experiment grain"),
        nbformat.v4.new_code_cell(
            "assert len(series) == 6_400\n"
            "assert len(maps) == 32_000\n"
            "assert not series.duplicated(['dial','roster_profile','treatment_value','best_of','series_index']).any()\n"
            "assert not maps.duplicated(['comparison_id','map_index','arm']).any()\n"
            "paired = maps.pivot(index=['comparison_id','map_index'], columns='arm', values=['map_id','match_seed'])\n"
            "assert (paired[('map_id','control')] == paired[('map_id','treatment')]).all()\n"
            "assert (paired[('match_seed','control')] == paired[('match_seed','treatment')]).all()\n"
            "control.sort_values(['best_of','roster_profile']).reset_index(drop=True)"
        ),
        nbformat.v4.new_markdown_cell(
            "## Results\n### 3. One plan treatment has different effects across roster shapes"
        ),
        nbformat.v4.new_code_cell(
            "display(Image(filename=str(HEATMAP_PATH)))\n"
            "bo3 = effects[effects.best_of.eq(3)].copy()\n"
            "bo3.pivot_table(index=['dial','treatment_value'], columns='roster_profile', "
            "values='series_win_lift_pp').round(1)"
        ),
        nbformat.v4.new_markdown_cell(
            "### 4. Estimate the causal fit interaction\n"
            "For aggression and pace, frag-heavy is the aligned roster and tactical "
            "is mismatched. For utility discipline and map control, that assignment "
            "is reversed. The interaction is the aligned treatment lift minus the "
            "mismatched treatment lift on the same seeds."
        ),
        nbformat.v4.new_code_cell(
            "display(Image(filename=str(INTERACTION_FIGURE)))\n"
            "interactions.sort_values(['best_of','dial','treatment_value']).round(2)"
        ),
        nbformat.v4.new_markdown_cell(
            "### 5. Separate global dial direction from roster-specific fit"
        ),
        nbformat.v4.new_code_cell(
            "display(Image(filename=str(DECOMPOSITION_FIGURE)))\n"
            "pd.read_csv(EFFECTS_PATH.parent / 'global_vs_roster_decomposition.csv')"
        ),
        nbformat.v4.new_markdown_cell(
            "### 6. Check whether the engine's declared fit edge predicts rounds"
        ),
        nbformat.v4.new_code_cell(
            "display(Image(filename=str(RESPONSE_FIGURE)))\n"
            "effects.groupby(['roster_profile','best_of'], as_index=False).agg(\n"
            "    mean_win_lift_pp=('series_win_lift_pp','mean'),\n"
            "    mean_round_margin_added=('round_margin_added_per_map','mean'),\n"
            ").round(2)"
        ),
        nbformat.v4.new_markdown_cell(
            "## Takeaways\n"
            f"- The experiment contains {summary['series_rows']:,} paired series rows.\n"
            f"- After controlling for dial, pole, and format, declared fit and "
            f"round-margin lift correlate "
            f"{summary['fit_round_margin_within_treatment_correlation']:.2f}.\n"
            f"- Global dial and pole choice explains "
            f"{100 * summary['bo3_round_global_dial_pole_share']:.1f}% of BO3 "
            f"round-margin variation across treatment cells; roster-specific "
            f"variation accounts for "
            f"{100 * summary['bo3_round_roster_specific_share']:.1f}%.\n"
            f"- The observed BO3 aligned-minus-mismatched interactions range from "
            f"{summary['bo3_interaction_min_pp']:+.1f} to "
            f"{summary['bo3_interaction_max_pp']:+.1f} percentage points.\n"
            "- Use the interaction estimates, not the largest raw dial effect, to "
            "judge whether the game rewards adapting a plan to the roster."
        ),
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(Path.cwd())}},
    ).execute()
    nbformat.write(notebook, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/roster_fit/output"))
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("analysis/roster_fit/roster_fit_series_analysis.ipynb"),
    )
    args = parser.parse_args()
    build_notebook(args.run_dir, args.output_dir, args.target)
    print(args.target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
