"""Build and execute the review notebook from validated experiment artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def build_notebook(
    repo_root: Path,
    primary: Path,
    supplement: Path,
    equal_core: Path,
    equal_mechanisms: Path,
    symmetry_baseline: Path,
    identical_series: Path,
    analysis_dir: Path,
    notebook_path: Path,
) -> None:
    summary = json.loads((analysis_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    overall65 = summary["overall_65_vs_85"]
    overall80 = summary["overall_80_vs_85"]
    top_equal = summary["top_equal_talent_management_factors"][:3]
    top_text = ", ".join(item["factor"].replace("_", " ") for item in top_equal)
    close = {
        item["lever"]: item
        for item in summary["requested_levers"]
        if item["context"] == "normalized_75v80_supplement"
    }
    variance_summary = json.loads(
        (analysis_dir / "variance_decomposition.json").read_text(encoding="utf-8")
    )
    component_lookup = {
        (item["dataset"], item["component"]): item["fair_share_pct"]
        for item in variance_summary["components"]
    }
    series_summary = json.loads(
        (analysis_dir / "series_format_summary.json").read_text(encoding="utf-8")
    )
    series_lookup = {
        (item["matchup"], item["format"]): item["win_rate"]
        for item in series_summary["favorite_win_rates"]
    }

    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3", "language": "python", "name": "python3"
    }
    nb["metadata"]["language_info"] = {"name": "python", "version": "3.13"}
    nb["cells"] = [
        nbf.v4.new_markdown_cell(
            "# How many rounds does each lever add?\n\n"
            "A paired-seed causal analysis of talent, role fit, language, micro, "
            "and the management layer in the deterministic match engine."
        ),
        nbf.v4.new_markdown_cell(
            "## tl;dr\n\n"
            f"- A normalized 65 team beat an 85 team **{overall65['wins']} times in "
            f"{overall65['matches']} matches ({overall65['win_rate']:.1%})**; a normalized "
            f"80 team won **{overall80['win_rate']:.1%}**. The observed concern is real in "
            "principle, but not frequent in this controlled engine slice.\n"
            "- Overall talent is the dominant lever. Micro is the strongest player-skill "
            "subsystem: raising the 65 micro bundle to 85 won "
            f"**{close['Micro bundle 65 to 85']['rounds_won_added']:.2f} extra rounds per match** "
            "in the 75-vs-80 matchup.\n"
            "- Aligning roles instead of rotating them won "
            f"**{close['Aligned roles vs rotated']['rounds_won_added']:.2f} extra rounds**; "
            f"restoring role comfort from 40 to 100 won **{close['Role comfort']['rounds_won_added']:.2f}**. "
            "Language was **outcome-inert** "
            "in every tested one-match treatment, and no common language defaults to 50.\n"
            f"- With identical 75-overall players, the largest observed management "
            f"sensitivities included **{top_text}**.\n"
            "- In the fully identical baseline, seed randomness receives "
            f"**{component_lookup[('Identical 75-vs-75 baseline', 'seed')]:.1f}%** of "
            "round-margin variance under fair-share interaction attribution; map receives "
            f"**{component_lookup[('Identical 75-vs-75 baseline', 'map_id')]:.1f}%**."
            "\n- Longer series compound real strength gaps: the 80-vs-85 favorite rises "
            f"from **{series_lookup[('80 vs 85', 'BO1')]:.1%} BO1** to "
            f"**{series_lookup[('80 vs 85', 'BO3')]:.1%} BO3** and "
            f"**{series_lookup[('80 vs 85', 'BO5')]:.1%} BO5**."
        ),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "Each treatment reuses the same map, team-identity swap, and match seed as its "
            "comparison level. Effects are therefore within-seed differences, not raw "
            "correlations. Confidence intervals cluster the paired differences by seed; "
            "three disjoint seed blocks test sign reproducibility. The primary estimand is "
            "**rounds won above baseline = treated-team score minus baseline-team score**. "
            "We also report **opponent rounds denied = baseline opponent score minus treated "
            "opponent score**. Their sum exactly equals the older round-margin improvement. "
            "Every comparison names its baseline and treatment explicitly.\n\n"
            "Four experiment layers are combined: a broad 65-vs-85 matrix, targeted "
            "65-vs-85 and 75-vs-80 mechanism sweeps, and equal-player 75-vs-75 core and "
            "mechanism sweeps. Identity swaps protect against team-id and starting-side "
            "artifacts."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import json\n"
            "import pandas as pd\n"
            "from IPython.display import Image, display\n"
            "from analysis.match_levers.run_analysis import run_analysis\n\n"
            "REPO_ROOT = Path.cwd()\n"
            f"PRIMARY = REPO_ROOT / {repr(_rel(primary, repo_root))}\n"
            f"SUPPLEMENT = REPO_ROOT / {repr(_rel(supplement, repo_root))}\n"
            f"EQUAL_CORE = REPO_ROOT / {repr(_rel(equal_core, repo_root))}\n"
            f"EQUAL_MECHANISMS = REPO_ROOT / {repr(_rel(equal_mechanisms, repo_root))}\n"
            f"SYMMETRY_BASELINE = REPO_ROOT / {repr(_rel(symmetry_baseline, repo_root))}\n"
            f"IDENTICAL_SERIES = REPO_ROOT / {repr(_rel(identical_series, repo_root))}\n"
            f"OUTPUT = REPO_ROOT / {repr(_rel(analysis_dir, repo_root))}\n\n"
            "from analysis.match_levers.variance_decomposition import run_decomposition\n"
            "from analysis.match_levers.series_analysis import run_series_analysis\n"
            "summary = run_analysis(PRIMARY, SUPPLEMENT, EQUAL_CORE, EQUAL_MECHANISMS, OUTPUT)\n"
            "variance_summary = run_decomposition(PRIMARY, EQUAL_CORE, SYMMETRY_BASELINE, OUTPUT)\n"
            "series_summary = run_series_analysis(PRIMARY, SUPPLEMENT, IDENTICAL_SERIES, OUTPUT)\n"
            "print(f\"Analyzed {summary['total_matches']:,} deterministic matches.\")"
        ),
        nbf.v4.new_markdown_cell("## Data"),
        nbf.v4.new_code_cell(
            "quality = pd.read_csv(OUTPUT / 'tables/data_quality.csv')\n"
            "assert (quality['duplicate_pairing_rows'] == 0).all()\n"
            "display(quality)"
        ),
        nbf.v4.new_markdown_cell(
            "All datasets must have complete causal keys before interpretation. The two "
            "main sweeps use 90 unique seeds per treatment level; equal-player supplements "
            "use 45, each repeated over five maps and both identity swaps. The symmetry "
            "baseline adds 300 unique map-seed matches across 60 seeds."
        ),
        nbf.v4.new_markdown_cell("## Results"),
        nbf.v4.new_markdown_cell("### 1. Overall talent is the dominant match lever"),
        nbf.v4.new_code_cell(
            "curve = pd.read_csv(OUTPUT / 'tables/overall_curve.csv')\n"
            "curve_view = curve.copy()\n"
            "for col in ['win_rate','win_ci_low','win_ci_high','close_match_rate']: "
            "curve_view[col] = (curve_view[col] * 100).round(2)\n"
            "display(curve_view.round(3))\n"
            "display(Image(filename=str(OUTPUT / 'figures/overall_curve.png')))"
        ),
        nbf.v4.new_markdown_cell(
            "Win probability is intentionally nonlinear: the 65-vs-85 matchup is almost "
            "closed, while moving from 75 to 80 buys much more probability. The treatment "
            "team's rounds won remains interpretable even when win rate is floored near zero."
        ),
        nbf.v4.new_markdown_cell("### 2. Micro, role fit, language, and IGL experience"),
        nbf.v4.new_code_cell(
            "requested = pd.read_csv(OUTPUT / 'tables/requested_levers_with_equivalents.csv')\n"
            "cols = ['context','lever','low_level','high_level','rounds_won_added',"
            "'rounds_won_added_ci_low','rounds_won_added_ci_high','opponent_rounds_denied',"
            "'weak_round_margin_effect','win_effect_pp','seed_block_sign_agreement']\n"
            "requested_view = requested[cols].copy()\n"
            "requested_view['seed_block_sign_agreement'] *= 100\n"
            "display(requested_view.round(3))\n"
            "display(Image(filename=str(OUTPUT / 'figures/requested_levers_close_gap.png')))"
        ),
        nbf.v4.new_code_cell(
            "mechanisms = pd.read_csv(OUTPUT / 'tables/mechanism_levels.csv')\n"
            "role_detail = mechanisms[mechanisms['factor'].isin(['role_comfort','role_assignment'])]\n"
            "role_view = role_detail[['context','factor','level','effective_weak_quality','weak_win_rate',"
            "'mean_weak_round_margin']].copy()\n"
            "role_view['weak_win_rate'] *= 100\n"
            "display(role_view.round(3))"
        ),
        nbf.v4.new_markdown_cell(
            "Read each row as: changing the stated baseline level to the treatment level "
            "wins `rounds_won_added` more rounds per match on average. `opponent_rounds_denied` "
            "is separate; adding the two reproduces `weak_round_margin_effect`. Role assignment "
            "combines weighted skill-role fit and effective-ability consequences; role comfort "
            "isolates the campaign unfamiliarity penalty."
        ),
        nbf.v4.new_code_cell(
            "language_check = summary['language_no_common_equals_shared_50']\n"
            "display(pd.DataFrame(language_check).T)"
        ),
        nbf.v4.new_markdown_cell(
            "The exact equality above is only part of the finding: all tested fluency levels "
            "from 20 through 100 also produced byte-identical scores and winners. The comms "
            "model calculates language-adjusted recall, but these treatments never crossed "
            "a decision threshold under the current policy. When teammates have no common "
            "tongue, `_language_overlap` additionally defaults to 50. Longer-term language "
            "effects through relationships and chemistry are outside this direct estimate."
        ),
        nbf.v4.new_markdown_cell("### 3. Management leverage with identical players"),
        nbf.v4.new_code_cell(
            "effects = pd.read_csv(OUTPUT / 'tables/baseline_rounds_added.csv')\n"
            "equal = effects[effects['context'].str.startswith('equal_75v75')].copy()\n"
            "equal['absolute_effect'] = equal['rounds_won_added'].abs()\n"
            "equal_view = equal.sort_values('absolute_effect', ascending=False).head(20)["
            "['context','factor','baseline_level','treatment_level','rounds_won_added',"
            "'rounds_won_added_ci_low','rounds_won_added_ci_high','opponent_rounds_denied',"
            "'weak_round_margin_effect','weak_win_effect_pp',"
            "'seed_block_sign_agreement']].copy()\n"
            "equal_view['seed_block_sign_agreement'] *= 100\n"
            "display(equal_view.round(3))\n"
            "display(Image(filename=str(OUTPUT / 'figures/equal_talent_management.png')))"
        ),
        nbf.v4.new_markdown_cell(
            "Every row now compares with a predeclared neutral baseline: tactics use 50, "
            "counter-strat uses 0, prep uses 0, halftime/touchline choices use none, and role "
            "assignment uses rotated. Tactics remain directional identities, not universal "
            "quality sliders; a positive treatment effect in this matchup is not proof that "
            "the same endpoint is globally optimal."
        ),
        nbf.v4.new_markdown_cell("### 4. Reproducibility across seed blocks"),
        nbf.v4.new_code_cell(
            "display(Image(filename=str(OUTPUT / 'figures/seed_block_robustness.png')))\n"
            "robust = pd.read_csv(OUTPUT / 'tables/seed_block_robustness.csv')\n"
            "display(robust.head(24))"
        ),
        nbf.v4.new_markdown_cell("### 5. What actually drives match-to-match variance"),
        nbf.v4.new_code_cell(
            "variance = pd.read_csv(OUTPUT / 'tables/variance_decomposition.csv')\n"
            "display(variance.round(3))\n"
            "display(Image(filename=str(OUTPUT / 'figures/variance_decomposition.png')))\n"
            "families = pd.read_csv(OUTPUT / 'tables/treatment_family_decomposition.csv')\n"
            "display(families.round(3))\n"
            "display(Image(filename=str(OUTPUT / 'figures/treatment_family_decomposition.png')))"
        ),
        nbf.v4.new_markdown_cell(
            "The fair-share numbers use a balanced functional ANOVA. Every interaction is "
            "split equally among the factors participating in it, so the displayed shares "
            "sum to 100%. In the exact symmetry baseline, seed receives 62.2% and map 37.8%. "
            "In the broad lever sweep, seed remains the largest component at 31.8%, while "
            "treatment configuration receives 24.2%. This does **not** mean some seed numbers "
            "are universally good: 72.0% of baseline variance is a map-by-seed interaction."
        ),
        nbf.v4.new_markdown_cell("### 6. Longer series filter upsets, not fairness"),
        nbf.v4.new_code_cell(
            "series_rates = pd.read_csv(OUTPUT / 'tables/series_format_win_rates.csv')\n"
            "display(series_rates.round(4))\n"
            "display(Image(filename=str(OUTPUT / 'figures/series_format_favorite_win_rates.png')))"
        ),
        nbf.v4.new_markdown_cell(
            "Identical teams stayed fair: the designated team won 49.3% of 300 BO3s and "
            "49.0% of 300 BO5s. Longer formats instead amplify real strength differences. "
            "An 80-vs-85 favorite increased from 72.1% in BO1 to 78.9% in BO3 and 85.6% "
            "in BO5; a 75-vs-80 favorite increased from 73.2% to 83.3% to 88.9%. "
            "The BO3 and BO5 winner differed on 19.0% of identical-team paired seeds, so "
            "additional maps do not remove randomness—they average more of it."
        ),
        nbf.v4.new_markdown_cell("## Takeaways"),
        nbf.v4.new_markdown_cell(
            "1. **Do not globally increase favorite strength yet.** The controlled 65-vs-85 "
            "upset rate is below 1%; use production-save telemetry to see whether authored "
            "rosters, form, or management bonuses are creating a different distribution.\n"
            "2. **Treat micro as the main player-level tuning surface.** Aim precision and "
            "reactivity explain much more than comms/composure in the direct match layer.\n"
            "3. **Calibrate assignment-weighted role fit.** Specialized aligned attributes "
            "currently gain a large effective-rating premium; comfort penalties are already "
            "bounded and behave more predictably.\n"
            "4. **Make language behavior observable.** Review both the neutral no-common "
            "fallback and the downstream recall thresholds; the current one-match result is "
            "identical from 20 to 100 fluency.\n"
            "5. **Use the equal-player suite for strategy tuning.** It identifies prep, "
            "counter-strat, tactics, chemistry, coaching, agent/map mastery, language, IGL, "
            "and assignments without player talent drowning out the signal.\n"
            "6. **Keep meaningful randomness, but measure it as an interaction.** Seeds "
            "contribute strongly to single-match outcomes, primarily by changing what happens "
            "on a particular map and identity orientation rather than providing a universal bias.\n"
            "7. **Balance around series format.** BO3 already protects moderate favorites; "
            "BO5 makes a five-point talent edge win roughly 86-89% of normalized series.\n\n"
            "Further work: repeat the top categorical configurations on held-out seeds, add "
            "campaign-generated scouting accuracy as an explicit treatment, and compare "
            "these normalized teams with authored roster distributions."
        ),
    ]
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, notebook_path)
    client = NotebookClient(nb, timeout=600, kernel_name="python3", allow_errors=False)
    client.execute(cwd=str(repo_root))
    nbf.write(nb, notebook_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--equal-core", type=Path, required=True)
    parser.add_argument("--equal-mechanisms", type=Path, required=True)
    parser.add_argument("--symmetry-baseline", type=Path, required=True)
    parser.add_argument("--identical-series", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--notebook", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_notebook(
        args.repo_root, args.primary, args.supplement, args.equal_core,
        args.equal_mechanisms, args.symmetry_baseline, args.identical_series,
        args.analysis_dir, args.notebook,
    )
