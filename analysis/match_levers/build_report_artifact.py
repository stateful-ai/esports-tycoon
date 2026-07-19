"""Build the canonical portable report around rounds won above baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "analysis" / "match_levers" / "output"


def source(source_id: str, label: str, path: str, sql: str, description: str) -> dict:
    return {
        "id": source_id,
        "label": label,
        "path": path,
        "query": {
            "language": "sql",
            "engine": "duckdb",
            "description": description,
            "sql": sql,
            "tables_used": [path],
            "filters": ["Validated complete paired cells only"],
            "metric_definitions": [
                "Effects pair the same map, identity swap, and seed.",
                "Rounds won above baseline equals treatment weak_score minus baseline weak_score.",
                "Opponent rounds denied equals baseline strong_score minus treatment strong_score.",
                "95% intervals cluster paired differences by seed.",
            ],
        },
    }


def build() -> dict:
    curve = pd.read_csv(OUTPUT / "tables" / "overall_curve.csv")
    requested = pd.read_csv(OUTPUT / "tables" / "requested_levers_with_equivalents.csv")
    requested = requested[requested["context"] == "normalized_75v80_supplement"]
    effects = pd.read_csv(OUTPUT / "tables" / "baseline_rounds_added.csv")
    equal = effects[effects["context"].str.startswith("equal_75v75")].copy()
    equal["absolute_effect"] = equal["rounds_won_added"].abs()
    equal = equal.sort_values("absolute_effect", ascending=False).head(12)
    variance = pd.read_csv(OUTPUT / "tables" / "variance_decomposition.csv")
    families = pd.read_csv(OUTPUT / "tables" / "treatment_family_decomposition.csv")
    series = pd.read_csv(OUTPUT / "tables" / "series_format_win_rates.csv")
    series_favorites = series[series["team_role"] == "favorite"].copy()
    series_favorites["comparison"] = (
        series_favorites["matchup"] + " " + series_favorites["format"]
    )
    series_favorites["favorite_win_pct"] = 100.0 * series_favorites["win_rate"]
    series_favorites["underdog_win_pct"] = 100.0 * series_favorites["underdog_win_rate"]
    primary_families = families[
        families["dataset"] == "Broad 65-vs-85 lever sweep"
    ].sort_values("share_of_direct_treatment_pct", ascending=False)

    primary_source = source(
        "primary",
        "Broad causal match sweep",
        "runs/causal-match-20260718-main-e1d9db2/matches.csv",
        "SELECT level_numeric AS weak_overall, AVG(weak_win) AS win_rate, "
        "AVG(weak_round_margin) AS mean_round_margin, COUNT(*) AS matches, "
        "SUM(weak_win) AS wins FROM read_csv_auto('runs/causal-match-20260718-main-e1d9db2/matches.csv') "
        "WHERE factor = 'weak_overall' GROUP BY level_numeric ORDER BY level_numeric",
        "Aggregate normalized overall treatments.",
    )
    analysis_source = source(
        "analysis",
        "Paired causal analysis notebook",
        "analysis/match_levers/output/tables/baseline_rounds_added.csv",
        "SELECT context, factor, baseline_level, treatment_level, rounds_won_added, "
        "opponent_rounds_denied, weak_round_margin_effect, weak_win_effect_pp FROM "
        "read_csv_auto('analysis/match_levers/output/tables/baseline_rounds_added.csv') "
        "ORDER BY ABS(rounds_won_added) DESC",
        "Read paired, seed-clustered causal effects produced by the notebook.",
    )
    variance_source = source(
        "variance",
        "Balanced match variance decomposition",
        "analysis/match_levers/output/tables/variance_decomposition.csv",
        "SELECT dataset, component_label, fair_share_pct, direct_main_pct, "
        "total_effect_pct FROM read_csv_auto("
        "'analysis/match_levers/output/tables/variance_decomposition.csv')",
        "Read functional-ANOVA variance shares with interactions allocated equally.",
    )
    series_source = {
        "id": "series",
        "label": "Best-of-one, best-of-three, and best-of-five outcomes",
        "path": "analysis/match_levers/output/tables/series_format_win_rates.csv",
        "query": {
            "language": "sql",
            "engine": "duckdb",
            "description": "Read paired series outcomes by normalized overall matchup and format.",
            "sql": "SELECT matchup, format, win_rate, ci_low, ci_high, underdog_win_rate, "
            "series_rows, seed_clusters FROM read_csv_auto("
            "'analysis/match_levers/output/tables/series_format_win_rates.csv') "
            "WHERE team_role = 'favorite' ORDER BY matchup, format",
            "tables_used": ["analysis/match_levers/output/tables/series_format_win_rates.csv"],
            "filters": ["Favorite rows for normalized unequal-team matchups"],
            "metric_definitions": [
                "BO1 is the map-level favorite win rate.",
                "BO3 is the favorite winning at least two of the first three maps in deterministic map order.",
                "BO5 is the favorite winning at least three of five maps.",
                "Intervals cluster the two identity orientations by seed.",
            ],
        },
    }

    manifest = {
        "version": 1,
        "title": "What Drives Match Outcomes?",
        "surface": "report",
        "description": "Causal lever, variance, and series-format analysis across 191,745 deterministic map simulations.",
        "generatedAt": "2026-07-19T05:00:00Z",
        "sources": [primary_source, analysis_source, variance_source, series_source],
        "charts": [
            {
                "id": "overall-chart",
                "title": "Underdog win rate against an 85-overall team",
                "dataset": "overall_curve",
                "type": "line",
                "encodings": {
                    "x": {"field": "weak_overall", "title": "Underdog overall"},
                    "y": {"field": "win_rate", "title": "Win rate", "format": "percent"},
                },
                "source": primary_source,
            },
            {
                "id": "levers-chart",
                "title": "Additional rounds won in a close 75-vs-80 matchup",
                "dataset": "requested_levers",
                "type": "bar",
                "encodings": {
                    "x": {"field": "lever", "title": "Lever"},
                    "y": {"field": "rounds_won_added", "title": "Rounds won above baseline"},
                },
                "source": analysis_source,
            },
            {
                "id": "variance-chart",
                "title": "Fair-share attribution of round-margin variance",
                "dataset": "variance_components",
                "type": "bar",
                "encodings": {
                    "x": {"field": "comparison_label", "title": "Experiment and component"},
                    "y": {"field": "fair_share_pct", "title": "Variance share (%)"},
                },
                "source": variance_source,
            },
            {
                "id": "series-chart",
                "title": "Longer series increasingly protect the favorite",
                "dataset": "series_favorite_rates",
                "type": "bar",
                "encodings": {
                    "x": {"field": "comparison", "title": "Matchup and format"},
                    "y": {"field": "win_rate", "title": "Favorite win rate", "format": "percent"},
                },
                "source": series_source,
            },
        ],
        "tables": [
            {
                "id": "management-table",
                "title": "Largest equal-player baseline-relative effects",
                "dataset": "equal_management",
                "columns": [
                    {"field": "factor", "label": "Factor"},
                    {"field": "comparison", "label": "Baseline to treatment"},
                    {"field": "rounds_won_added", "label": "Rounds added", "format": "number", "movement": True},
                    {"field": "opponent_rounds_denied", "label": "Opponent rounds denied", "format": "number", "movement": True},
                ],
                "defaultSort": {"field": "rounds_won_added", "direction": "desc"},
                "source": analysis_source,
            },
            {
                "id": "treatment-family-table",
                "title": "Direct treatment signal in the broad lever sweep",
                "dataset": "treatment_families",
                "columns": [
                    {"field": "family", "label": "Lever family"},
                    {"field": "versions", "label": "Authored versions", "format": "number"},
                    {"field": "share_of_direct_treatment_pct", "label": "Share of treatment signal (%)", "format": "number"},
                ],
                "defaultSort": {"field": "share_of_direct_treatment_pct", "direction": "desc"},
                "source": variance_source,
            },
            {
                "id": "series-table",
                "title": "Favorite and upset rates by series format",
                "dataset": "series_favorite_rates",
                "columns": [
                    {"field": "matchup", "label": "Overall matchup"},
                    {"field": "format", "label": "Format"},
                    {"field": "favorite_win_pct", "label": "Favorite win (%)", "format": "number"},
                    {"field": "underdog_win_pct", "label": "Upset rate (%)", "format": "number"},
                    {"field": "seed_clusters", "label": "Seed clusters", "format": "number"},
                ],
                "source": series_source,
            },
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# What Drives Match Outcomes?"},
            {"id": "executive-summary", "type": "markdown", "body": "## Executive Summary\n- **Longer series filter upsets without creating an equal-team bias.** Identical 75 teams finished at 49.3% in BO3 and 49.0% in BO5. For an 80-vs-85 matchup, favorite win probability rose from 72.1% in BO1 to 78.9% in BO3 and 85.6% in BO5.\n- **Seed randomness is meaningful, but contextual.** It receives 62.2% of variance in the exact identical-team baseline and about one-third in both larger sweeps. Most of that influence appears through interactions with map and identity rather than universally favorable seed numbers.\n- **Talent dominates the controllable signal.** Treatment configuration receives 24.2% of fair-share variance in the broad sweep, and overall talent accounts for 81.5% of the direct treatment-configuration signal.\n- **Management matters, but single matches are noisy.** With identical players, management treatment receives 10.8% of fair-share variance, compared with 33.3% seed, 25.6% map, and 30.2% identity/orientation. Paired multi-seed experiments are therefore essential for balancing decisions.\n- **The favorite does not need a blanket buff.** A normalized 65 team still beat an 85 team only 7 times in 900 maps (0.78%) and won every reconstructed BO3 and BO5."},
            {"id": "variance-section", "type": "markdown", "body": "## Randomness Is Large, but It Is Not a Universal Seed Bonus\nThe identical 75-vs-75 baseline is the cleanest measure of inherent match volatility: seed receives 62.2% of the fair-share round-margin variance and map receives 37.8%. In the broad 65-vs-85 lever sweep, the split is seed 31.8%, map 24.4%, treatment configuration 24.2%, and stable identity/orientation 19.7%. The large seed share means an individual match can be decided by its stochastic trajectory. It does not mean certain numerical seeds are always strong: 72.0% of baseline variance is specifically map-by-seed interaction."},
            {"id": "variance-chart-block", "type": "chart", "chartId": "variance-chart"},
            {"id": "series-section", "type": "markdown", "body": "## Series Length Converts Map Skill Into Match Certainty\nThe format effect is material even for close teams. An 85 favorite against an 80 team rises from 72.1% in BO1 to 78.9% in BO3 and 85.6% in BO5. An 80 favorite against a 75 team rises from 73.2% to 83.3% to 88.9%. A ten-point 85-vs-75 advantage is already 89.8% on one map, then 98.3% in BO3 and 99.4% in BO5. Identical teams remain statistically centered at 50% in both formats, although the BO3 and BO5 winner differs on 19.0% of paired series seeds because BO5 exposes the teams to additional maps. BO3 therefore filters a meaningful portion of single-map volatility while retaining more upset potential than BO5."},
            {"id": "series-chart-block", "type": "chart", "chartId": "series-chart"},
            {"id": "series-table-block", "type": "table", "tableId": "series-table"},
            {"id": "treatment-family-section", "type": "markdown", "body": "## Overall Talent Dominates the Controllable Signal\nWithin the direct treatment-configuration component of the broad sweep, the authored overall curve contributes 81.5%; individual player mechanics and role treatments contribute 9.1%; strategy and management contribute 6.9%; and readiness or mastery contributes 2.5%. These shares describe the ranges and weighting in this experiment catalog, not the frequency of situations in a live campaign. The practical implication is that player quality should remain the strongest long-run edge, while strategy is most visible in close matchups and over repeated maps."},
            {"id": "treatment-family-table-block", "type": "table", "tableId": "treatment-family-table"},
            {"id": "overall-section", "type": "markdown", "body": "## Overall Talent\nThe controlled 65-vs-85 upset rate is already below 1%, so the evidence does not support a blanket buff to favorites. The response is nonlinear: probability opens quickly between 75 and 85. For interventions, rounds won above baseline remains readable even when win rate is near zero."},
            {"id": "overall-chart-block", "type": "chart", "chartId": "overall-chart"},
            {"id": "player-section", "type": "markdown", "body": "## Player-Level Levers\nIn the broad 65-vs-85 sweep, raising aim precision from 65 to 85 won 2.47 extra rounds per match (95% CI 2.27 to 2.66); aim reactivity added 2.07, while movement added 0.46. In the close 75-vs-80 matchup, the 65-to-85 micro bundle added 5.73 rounds won and denied the opponent 3.19 more, for an 8.92-round margin improvement. Restoring role comfort from 40 to 100 added 1.40 rounds. Aligning roles instead of the neutral rotated assignment added 2.83 rounds and denied 3.16, for a 6.00-round margin improvement."},
            {"id": "levers-chart-block", "type": "chart", "chartId": "levers-chart"},
            {"id": "management-section", "type": "markdown", "body": "## Management With Identical Players\nThe equal-75-vs-75 design isolates choices around the roster using predeclared neutral baselines. Aggression 100 versus 50 won 1.52 extra rounds and denied 1.94; reassure versus no halftime talk added 0.84 and denied 1.13. Counter edge +3 versus 0 added 0.80 rounds, complex-system chemistry 100 versus 65 added 0.84, and maximum prep versus zero added 0.16. These are direct treatment effects, not sample-selected best-to-worst spans."},
            {"id": "management-table-block", "type": "table", "tableId": "management-table"},
            {"id": "recommendations", "type": "markdown", "body": "## Recommended Next Steps\n1. Use BO3 as the primary balance target for standard competitive play. It dampens single-map variance while preserving materially more upset potential than BO5.\n2. Set an explicit target for five-point-gap series. The current 79% to 83% BO3 favorite range may be appropriate; the 86% to 89% BO5 range is considerably more deterministic.\n3. Preserve the current equal-team randomness unless playtesting says individual maps feel illegible. It remains fair over repeated trials and series length already performs useful filtering.\n4. Investigate the stable identity/orientation component before tuning randomness. Its 19.7% broad-sweep and 30.2% equal-player shares may contain starting-side, team-id tie-break, or identity-specific interactions.\n5. Continue using paired seeds for every lever decision; unpaired single-match comparisons are too noisy to isolate management effects.\n6. Do not globally increase favorite strength yet; compare normalized results with authored-roster and production-save telemetry."},
            {"id": "further-questions", "type": "markdown", "body": "## Further Questions\n- Does stable identity/orientation remain large when actual side assignment and team ids are crossed independently?\n- Do between-map adaptation, fatigue, substitutions, and map vetoes materially alter the reconstructed series curves?\n- Does the same decomposition hold for authored roster packs rather than normalized teams?\n- Which stochastic engine mechanisms - day form, duel resolution, tactical calls, or economy sequencing - contribute most to the seed component?"},
            {"id": "caveats", "type": "markdown", "body": "## Metric Definition and Caveats\nThe decomposition uses balanced functional ANOVA on round margin. Interaction variance is split equally among participating factors, producing fair-share attributions that sum to 100%. Total-effect percentages are also saved for sensitivity analysis but overlap and should not be added together. Stable identity/orientation includes team-id, treatment orientation, starting-side, and their interactions; it is not evidence that authored players differ in the symmetry baseline. Unequal-team BO3 and BO5 results reconstruct series from five map outcomes using a deterministic map order; they do not model between-map fatigue, adaptation, substitutions, or veto decisions. The fresh identical-team series use actual early stopping but likewise reset match state between maps. Treatment-family shares depend on the levels and number of versions authored in these experiments and are not forecasts of live campaign frequencies. Rounds-added estimates remain paired on map, identity, and seed."},
        ],
    }

    snapshot = {
        "version": 1,
        "status": "ready",
        "generatedAt": "2026-07-19T05:00:00Z",
        "datasets": {
            "overall_curve": curve[["weak_overall", "win_rate", "mean_round_margin", "matches", "wins"]].to_dict(orient="records"),
            "requested_levers": [
                {
                    "lever": {
                        "Micro bundle 65 to 85": "Micro 65 to 85",
                        "Aligned roles vs rotated": "Aligned roles",
                        "Tactical bundle 65 to 85": "Tactical 65 to 85",
                        "Role comfort": "Comfort 40 to 100",
                        "Mental bundle 65 to 85": "Mental 65 to 85",
                        "IGL experience": "IGL 40 to 100",
                        "Language 50 to 100": "Language 50 to 100",
                    }.get(row.lever, row.lever),
                    "rounds_won_added": row.rounds_won_added,
                    "opponent_rounds_denied": row.opponent_rounds_denied,
                    "round_margin_effect": row.weak_round_margin_effect,
                    "win_effect_pp": row.win_effect_pp,
                    "context": "75 vs 80",
                    "ci_low": row.rounds_won_added_ci_low,
                    "ci_high": row.rounds_won_added_ci_high,
                }
                for row in requested.itertuples()
            ],
            "equal_management": [
                {
                    "factor": row.factor.replace("_", " ").title(),
                    "comparison": f"{row.baseline_level} to {row.treatment_level}",
                    "rounds_won_added": row.rounds_won_added,
                    "opponent_rounds_denied": row.opponent_rounds_denied,
                    "round_margin_effect": row.weak_round_margin_effect,
                    "win_effect_pp": row.weak_win_effect_pp,
                    "seed_sign_agreement": row.seed_block_sign_agreement,
                }
                for row in equal.itertuples()
            ],
            "variance_components": [
                {
                    "dataset_short": {
                        "Broad 65-vs-85 lever sweep": "Broad lever sweep",
                        "Equal-player management sweep": "Equal-player management",
                        "Identical 75-vs-75 baseline": "Identical baseline",
                    }[row.dataset],
                    "comparison_label": (
                        {
                            "Broad 65-vs-85 lever sweep": "Broad",
                            "Equal-player management sweep": "Equal",
                            "Identical 75-vs-75 baseline": "Baseline",
                        }[row.dataset]
                        + ": "
                        + row.component_label
                    ),
                    "component_label": row.component_label,
                    "fair_share_pct": row.fair_share_pct,
                    "direct_main_pct": row.direct_main_pct,
                    "total_effect_pct": row.total_effect_pct,
                }
                for row in variance.itertuples()
            ],
            "treatment_families": primary_families[
                ["family", "versions", "share_of_direct_treatment_pct", "share_of_total_variance_pct"]
            ].to_dict(orient="records"),
            "series_favorite_rates": series_favorites[
                [
                    "matchup",
                    "format",
                    "comparison",
                    "win_rate",
                    "favorite_win_pct",
                    "underdog_win_pct",
                    "ci_low",
                    "ci_high",
                    "series_rows",
                    "seed_clusters",
                ]
            ].to_dict(orient="records"),
        },
    }
    return {"surface": "report", "manifest": manifest, "snapshot": snapshot, "sources": manifest["sources"]}


if __name__ == "__main__":
    target = ROOT / "analysis" / "match_levers" / "artifact.json"
    target.write_text(json.dumps(build(), indent=2), encoding="utf-8")
    print(target)
