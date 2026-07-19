"""Build the portable roster-fit experiment report artifact."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def _source(source_id: str, label: str, path: Path, description: str) -> dict:
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    return {
        "id": source_id,
        "label": label,
        "path": relative,
        "query": {
            "language": "sql",
            "engine": "duckdb",
            "description": description,
            "sql": f"SELECT * FROM read_csv_auto('{relative}')",
            "tables_used": [relative],
            "filters": ["Complete validated paired rows only"],
            "metric_definitions": [
                "Series win lift is paired treatment win minus neutral-control win.",
                "Rounds won added is treatment score minus control score on the same maps.",
                "Fit interaction is aligned-roster lift minus mismatched-roster lift.",
            ],
        },
    }


def build(run_dir: Path, output_dir: Path) -> dict:
    effects = pd.read_csv(output_dir / "tables" / "roster_fit_effects.csv")
    interactions = pd.read_csv(output_dir / "tables" / "roster_fit_interactions.csv")
    analysis = json.loads((output_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    bo3 = effects[effects["best_of"] == 3].copy()
    dial_short = {
        "aggression": "Agg",
        "pace": "Pace",
        "util_discipline": "Util",
        "map_control": "Control",
    }
    profile_short = {
        "fraggers": "Frag",
        "balanced": "Bal",
        "mixed": "Mixed",
        "tacticians": "Tac",
    }
    bo3["comparison"] = (
        bo3["dial"].map(dial_short)
        + " "
        + bo3["treatment_value"].map(lambda value: f"{value:g}")
        + " | "
        + bo3["roster_profile"].map(profile_short)
    )
    bo3_interactions = interactions[interactions["best_of"] == 3].copy()
    bo3_interactions["comparison"] = (
        bo3_interactions["dial"].map(dial_short)
        + " "
        + bo3_interactions["treatment_value"].map(lambda value: f"{value:g}")
    )
    significant = bo3_interactions[
        (bo3_interactions["fit_interaction_win_ci_low"] > 0)
        | (bo3_interactions["fit_interaction_win_ci_high"] < 0)
    ]
    strongest = bo3_interactions.loc[
        bo3_interactions["fit_interaction_win_pp"].abs().idxmax()
    ]
    mean_abs_interaction = float(bo3_interactions["fit_interaction_win_pp"].abs().mean())
    correlation = float(analysis["fit_round_margin_within_treatment_correlation"])
    global_share = 100.0 * float(analysis["bo3_round_global_dial_pole_share"])
    roster_share = 100.0 * float(analysis["bo3_round_roster_specific_share"])
    global_effects = (
        bo3.groupby(["dial", "treatment_value"], as_index=False)
        .agg(
            mean_win_lift_pp=("series_win_lift_pp", "mean"),
            mean_round_margin_added=("round_margin_added_per_map", "mean"),
        )
    )
    global_lookup = global_effects.set_index(["dial", "treatment_value"])[
        "mean_win_lift_pp"
    ]
    aggression_high = float(global_lookup[("aggression", 100.0)])
    aggression_low = float(global_lookup[("aggression", 0.0)])
    pace_high = float(global_lookup[("pace", 100.0)])
    utility_high = float(global_lookup[("util_discipline", 100.0)])
    decomposition = pd.read_csv(
        output_dir / "tables" / "global_vs_roster_decomposition.csv"
    )
    decomposition["comparison"] = decomposition.apply(
        lambda row: f"BO{int(row.best_of)} "
        + ("win lift" if row.outcome == "series_win_lift_pp" else "round margin"),
        axis=1,
    )
    answer = (
        "Partly: roster fit changes outcomes, but global dial direction still dominates."
    )

    series_source = _source(
        "series",
        "Paired roster-fit series outcomes",
        run_dir / "series.csv",
        "Read one neutral-control versus one-dial-treatment result per seed and format.",
    )
    maps_source = _source(
        "maps",
        "Paired roster-fit map outcomes",
        run_dir / "series_maps.csv",
        "Audit control and treatment map scores under identical map ids and seeds.",
    )
    generated = datetime.now(UTC).isoformat()
    report_manifest = {
        "version": 1,
        "title": "Does the Game Plan Fit the Roster?",
        "surface": "report",
        "description": (
            f"Paired roster-plan interaction analysis across "
            f"{manifest['simulated_maps']:,} deterministic map simulations."
        ),
        "generatedAt": generated,
        "sources": [series_source, maps_source],
        "charts": [
            {
                "id": "decomposition-chart",
                "title": "Global setting versus roster-specific variation",
                "dataset": "decomposition",
                "type": "bar",
                "encodings": {
                    "x": {"field": "comparison_component", "title": "Outcome and component"},
                    "y": {"field": "share_pct", "title": "Variation share (%)"},
                },
                "source": series_source,
            },
            {
                "id": "interaction-chart",
                "title": "Aligned versus mismatched BO3 treatment lift",
                "dataset": "bo3_interactions",
                "type": "bar",
                "encodings": {
                    "x": {"field": "comparison", "title": "One-dial treatment"},
                    "y": {
                        "field": "fit_interaction_win_pp",
                        "title": "Aligned minus mismatched win lift (pp)",
                    },
                },
                "source": series_source,
            },
            {
                "id": "effect-chart",
                "title": "BO3 win lift by roster and one-dial treatment",
                "dataset": "bo3_effects_primary",
                "type": "bar",
                "encodings": {
                    "x": {"field": "comparison", "title": "Treatment and roster"},
                    "y": {"field": "series_win_lift_pp", "title": "Win-rate lift (pp)"},
                },
                "source": series_source,
            },
            {
                "id": "fit-response-chart",
                "title": "Declared roster fit and rounds added",
                "dataset": "fit_response",
                "type": "scatter",
                "encodings": {
                    "x": {"field": "expected_fit_edge", "title": "Roster-fit edge"},
                    "y": {
                        "field": "round_margin_added_per_map",
                        "title": "Round-margin lift per map",
                    },
                },
                "source": maps_source,
            },
        ],
        "tables": [
            {
                "id": "effects-table",
                "title": "BO3 control and treatment outcomes",
                "dataset": "bo3_effects",
                "columns": [
                    {"field": "dial_label", "label": "Dial"},
                    {"field": "roster_label", "label": "Roster"},
                    {"field": "treatment_value", "label": "Treatment", "format": "number"},
                    {
                        "field": "series_win_lift_pp",
                        "label": "Win lift (pp)",
                        "format": "number",
                        "movement": True,
                    },
                    {
                        "field": "rounds_won_added_per_map",
                        "label": "Rounds added/map",
                        "format": "number",
                        "movement": True,
                    },
                ],
                "source": series_source,
            },
            {
                "id": "interactions-table",
                "title": "Roster-fit interactions by format",
                "dataset": "interactions",
                "columns": [
                    {"field": "dial_label", "label": "Dial"},
                    {"field": "treatment_value", "label": "Treatment", "format": "number"},
                    {"field": "format", "label": "Format"},
                    {"field": "aligned_label", "label": "Aligned roster"},
                    {
                        "field": "fit_interaction_win_pp",
                        "label": "Fit interaction (pp)",
                        "format": "number",
                        "movement": True,
                    },
                    {
                        "field": "fit_interaction_rounds_per_map",
                        "label": "Fit rounds/map",
                        "format": "number",
                        "movement": True,
                    },
                ],
                "source": series_source,
            },
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Does the Game Plan Fit the Roster?"},
            {
                "id": "executive-summary",
                "type": "markdown",
                "sourceId": "series",
                "body": (
                    "## Executive Summary\n"
                    f"- **{answer}** Global dial and pole choice explains "
                    f"{global_share:.1f}% of BO3 round-margin variation across treatment "
                    f"cells, versus {roster_share:.1f}% for roster-specific differences.\n"
                    f"- **Fit is nevertheless a real within-treatment signal.** After "
                    f"controlling for dial, pole, and format, the declared roster-fit edge "
                    f"correlates {correlation:.2f} with residual round-margin lift. The "
                    f"average absolute BO3 win interaction is {mean_abs_interaction:.1f} "
                    f"percentage points, but only {len(significant)} of "
                    f"{len(bo3_interactions)} cells excludes zero at the 95% interval.\n"
                    f"- **The strongest observed fit contrast is "
                    f"{strongest['dial'].replace('_', ' ')} at {strongest['treatment_value']:g}.** "
                    f"Its aligned roster gains {strongest['fit_interaction_win_pp']:+.1f} "
                    "percentage points more BO3 win lift than the mismatched roster.\n"
                    "- **Interpret the interaction, not the raw winning pole.** A setting "
                    "that wins for both rosters may still reward fit if the aligned roster "
                    "benefits materially more; a setting that helps every roster equally is "
                    "a global dial effect, not roster adaptation."
                ),
            },
            {
                "id": "global-dominance-finding",
                "type": "markdown",
                "sourceId": "series",
                "body": (
                    "## The Engine Still Has Generally Good and Bad Dial Directions\n"
                    f"Across roster profiles, global dial and pole choice explains "
                    f"{global_share:.1f}% of BO3 round-margin differences between "
                    f"treatment cells. Roster-specific residual variation explains "
                    f"{roster_share:.1f}%. This means composition modifies the result, "
                    "but managers can currently gain more by learning broadly strong "
                    "directions than by deeply tailoring the system to their players. "
                    f"For example, aggression 100 averages {aggression_high:+.1f} BO3 "
                    f"win points across profiles while aggression 0 averages "
                    f"{aggression_low:+.1f}; pace 100 averages {pace_high:+.1f} and "
                    f"utility discipline 100 averages {utility_high:+.1f}."
                ),
            },
            {"id": "decomposition-chart-block", "type": "chart", "chartId": "decomposition-chart"},
            {
                "id": "fit-finding",
                "type": "markdown",
                "sourceId": "series",
                "body": (
                    "## The Same Plan Is Worth Different Amounts to Different Rosters\n"
                    "The fit interaction compares two fully paired causal effects: the "
                    "one-dial treatment lift for the aligned roster minus the same lift "
                    "for the mismatched roster on identical series seeds. Positive values "
                    "mean that adapting the plan to player strengths produces more wins "
                    "than merely moving the dial."
                ),
            },
            {"id": "interaction-chart-block", "type": "chart", "chartId": "interaction-chart"},
            {"id": "interaction-table-block", "type": "table", "tableId": "interactions-table"},
            {
                "id": "raw-effect-finding",
                "type": "markdown",
                "sourceId": "series",
                "body": (
                    "## Raw Treatment Effects Still Matter, but They Are Not the Question\n"
                    "Each row below changes exactly one dial from the neutral control. "
                    "Both teams otherwise use the same mechanically mirrored roster at "
                    "75 overall. Comparing frag-heavy, tactical, balanced, and mixed "
                    "columns shows whether a treatment is broadly strong or specifically "
                    "amplified by roster fit."
                ),
            },
            {"id": "effect-chart-block", "type": "chart", "chartId": "effect-chart"},
            {"id": "effects-table-block", "type": "table", "tableId": "effects-table"},
            {
                "id": "round-finding",
                "type": "markdown",
                "sourceId": "maps",
                "body": (
                    "## Fit Appears in Round Control Before It Appears in Every Series Result\n"
                    "Rounds are the more sensitive outcome because a series win is binary. "
                    "The paired round-margin measure uses the same scheduled BO3 or BO5 maps "
                    "for control and treatment, so it can detect direction even when a plan "
                    "does not flip the final series winner."
                ),
            },
            {"id": "fit-response-chart-block", "type": "chart", "chartId": "fit-response-chart"},
            {
                "id": "recommendations",
                "type": "markdown",
                "body": (
                    "## Recommended Next Steps\n"
                    "1. Use aligned-minus-mismatched series lift as the balance KPI for "
                    "roster-fit mechanics; do not optimize the largest raw dial effect.\n"
                    "2. Repeat the strongest and weakest interactions with less polarized, "
                    "authored-style rosters to find the practical live-game magnitude.\n"
                    "3. Add opponent identities next: the same roster-plan pair should face "
                    "aggressive, disciplined, and balanced opponents so fit is not confused "
                    "with a universal counter.\n"
                    "4. Keep BO3 as the primary decision format and BO5 as the determinism "
                    "stress test."
                ),
            },
            {
                "id": "further-questions",
                "type": "markdown",
                "body": (
                    "## Further Questions\n"
                    "- Do moderate 60-to-80 player profiles preserve the same interaction ranking?\n"
                    "- Does agent selection strengthen or weaken the roster-plan interaction?\n"
                    "- Does explicit opponent counter-stratting create a three-way roster x plan x opponent effect?\n"
                    "- How much of the interaction survives between-map adaptation and veto decisions?"
                ),
            },
            {
                "id": "caveats",
                "type": "markdown",
                "body": (
                    "## Caveats and Assumptions\n"
                    "These are synthetic, deliberately polarized 75-overall rosters. "
                    "The experiment establishes engine causality, not the frequency or "
                    "magnitude of these roster shapes in authored packs. BO3 and BO5 use "
                    "the same fixed five-map schedule and do not model vetoes, substitutions, "
                    "fatigue, or between-map adaptation. Confidence intervals use paired "
                    "seed-level differences and do not adjust for selecting the strongest "
                    "cell for descriptive emphasis."
                ),
            },
        ],
    }

    primary_profiles = {"fraggers", "tacticians"}
    fit_response = effects[
        effects["roster_profile"].isin(primary_profiles)
    ].copy()
    snapshot = {
        "version": 1,
        "status": "ready",
        "generatedAt": generated,
        "datasets": {
            "decomposition": [
                {
                    "comparison_component": f"{row.comparison.replace('round margin', 'margin').replace('win lift', 'wins')} global",
                    "comparison": row.comparison,
                    "component": "Global dial/pole",
                    "share_pct": 100.0 * row.global_dial_pole_share,
                }
                for row in decomposition.itertuples(index=False)
            ]
            + [
                {
                    "comparison_component": f"{row.comparison.replace('round margin', 'margin').replace('win lift', 'wins')} roster",
                    "comparison": row.comparison,
                    "component": "Roster-specific",
                    "share_pct": 100.0 * row.roster_specific_share,
                }
                for row in decomposition.itertuples(index=False)
            ],
            "bo3_interactions": bo3_interactions[
                [
                    "comparison",
                    "dial",
                    "treatment_value",
                    "fit_interaction_win_pp",
                    "fit_interaction_win_ci_low",
                    "fit_interaction_win_ci_high",
                ]
            ].to_dict(orient="records"),
            "bo3_effects_primary": bo3[
                bo3["roster_profile"].isin(primary_profiles)
            ][
                [
                    "comparison",
                    "dial",
                    "roster_profile",
                    "treatment_value",
                    "series_win_lift_pp",
                ]
            ].to_dict(orient="records"),
            "fit_response": fit_response[
                [
                    "dial",
                    "roster_profile",
                    "treatment_value",
                    "best_of",
                    "expected_fit_edge",
                    "round_margin_added_per_map",
                ]
            ].to_dict(orient="records"),
            "bo3_effects": [
                {
                    **row._asdict(),
                    "dial_label": row.dial.replace("_", " ").title(),
                    "roster_label": row.roster_profile.replace("_", " ").title(),
                    "control_win_pct": 100.0 * row.control_win_rate,
                    "treatment_win_pct": 100.0 * row.treatment_win_rate,
                }
                for row in bo3.itertuples(index=False)
            ],
            "interactions": [
                {
                    **row._asdict(),
                    "dial_label": row.dial.replace("_", " ").title(),
                    "format": f"BO{row.best_of}",
                    "aligned_label": row.aligned_profile.title(),
                    "mismatched_label": row.mismatched_profile.title(),
                }
                for row in interactions.itertuples(index=False)
            ],
        },
    }
    return {
        "surface": "report",
        "manifest": report_manifest,
        "snapshot": snapshot,
        "sources": report_manifest["sources"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/roster_fit/output"))
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("analysis/roster_fit/artifact.json"),
    )
    args = parser.parse_args()
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(
        json.dumps(build(args.run_dir, args.output_dir), indent=2),
        encoding="utf-8",
    )
    print(args.target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
