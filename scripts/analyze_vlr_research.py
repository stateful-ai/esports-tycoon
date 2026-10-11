"""Validate VLR CSVs, propose quality estimates, and fit experimental lineup WAR.

Only pre-match identities enter the outcome model: same-map box scores are
outcomes and must never be used to predict that map's winner. NumPy and PyYAML
are existing project dependencies. All output is research, never runtime data.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

from collect_vlr_research import ROOT, normalize, write_csv


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def num(row, field):
    return float(row[field]) if row.get(field) not in {"", None} else None


def agent_roles():
    raw = yaml.safe_load((ROOT / "data/agents.yaml").read_text())
    agents = raw.get("agents", raw) if isinstance(raw, dict) else raw
    return {a["id"]: a["role"] for a in agents}


def role_for(row, roles):
    return roles.get((row.get("agent") or row.get("agents") or "").split("|")[0], "unknown")


def validate(data):
    events = read_csv(data / "events.csv")
    stats = read_csv(data / "player_event_stats.csv")
    maps = read_csv(data / "map_outcomes.csv")
    players = read_csv(data / "player_map_stats.csv")
    errors, warnings = [], []
    provenance_checks = 0
    if (data / "sources.csv").exists():
        ledger = {r["source_url"]: r for r in read_csv(data / "sources.csv")}
        profiles = read_csv(data / "player_profiles.csv") if (data / "player_profiles.csv").exists() else []
        for r in stats + maps + players + profiles:
            source = ledger.get(r["source_url"], {})
            if r["source_sha256"] != source.get("sha256") or r["retrieved_at_utc"] != source.get("retrieved_at_utc"):
                errors.append(f"Source hash/timestamp does not reconcile: {r['source_url']}")
            provenance_checks += 1
    for label, rows, fields in [("events", events, ["event_id"]), ("event_stats", stats, ["event_id", "vlr_player_id"]),
                               ("maps", maps, ["match_id", "map_id"]), ("player_maps", players, ["match_id", "map_id", "vlr_player_id"])]:
        keys = [tuple(r[f] for f in fields) for r in rows]
        duplicate_count = len(keys) - len(set(keys))
        if duplicate_count:
            errors.append(f"{label}: {duplicate_count} duplicate keys")
    event_ids = {r["event_id"] for r in events}
    by_map = defaultdict(list)
    for row in players:
        by_map[(row["match_id"], row["map_id"])].append(row)
        for k in ["kills", "deaths", "assists", "first_kills", "first_deaths"]:
            v = num(row, k)
            if v is None:
                warnings.append(f"player map {row['map_id']}: missing {k}; preserved as blank")
            elif v < 0 or not v.is_integer():
                errors.append(f"player map {row['map_id']}: invalid {k}")
        for k in ["kast_pct", "hs_pct"]:
            v = num(row, k)
            if v is not None and not 0 <= v <= 100:
                errors.append(f"player map {row['map_id']}: invalid {k}")
    map_keys = {(r["match_id"], r["map_id"]) for r in maps}
    for key in by_map.keys() - map_keys:
        errors.append(f"orphan player map {key}")
    for m in maps:
        key = (m["match_id"], m["map_id"])
        rows = by_map[key]
        rounds = int(m["rounds"])
        scores = [int(m["team1_rounds"]), int(m["team2_rounds"])]
        if rounds != sum(scores) or max(scores) < 13 or abs(scores[0]-scores[1]) < 2 or not m["map_name"]:
            errors.append(f"map {key}: invalid outcome")
        if m["event_id"] not in event_ids:
            errors.append(f"map {key}: unknown event")
        expected_winner = m["team1_id"] if scores[0] > scores[1] else m["team2_id"]
        if m["winner_team_id"] != expected_winner or m["team1_id"] == m["team2_id"]:
            errors.append(f"map {key}: winner/team identity mismatch")
        for p in rows:
            if p["team_id"] not in {m["team1_id"], m["team2_id"]}:
                errors.append(f"map {key}: player has unknown team")
        for i in [1, 2]:
            team = m[f"team{i}_id"]
            lineup = [p for p in rows if p["team_id"] == team]
            if len(lineup) != 5 or len({p["vlr_player_id"] for p in lineup}) != 5:
                warnings.append(f"map {key} team {team}: source has {len(lineup)} player rows; excluded from lineup model")
            for p in lineup:
                if p["rounds"] != m["rounds"] or int(p["map_win"]) != int(team == m["winner_team_id"]):
                    errors.append(f"map {key}: player outcome mismatch")
        if len(rows) != 10:
            warnings.append(f"map {key}: {len(rows)} player rows; excluded from lineup model")
        # Sum FK and FD should match each other, but no-death objective rounds
        # mean neither must equal the number of rounds.
        fk = sum(num(p, "first_kills") or 0 for p in rows)
        fd = sum(num(p, "first_deaths") or 0 for p in rows)
        opening_complete = len(rows) == 10 and all(num(p, k) is not None for p in rows for k in ["first_kills", "first_deaths"])
        if opening_complete and fk != fd:
            warnings.append(f"map {key}: FK {fk} != FD {fd}; source inconsistency")
    for r in stats:
        if r["event_id"] not in event_ids or not r["vlr_player_id"]:
            errors.append("event observation has invalid identity or event")
        if not num(r, "rounds") or not num(r, "maps"):
            warnings.append(f"event {r['event_id']} player {r['vlr_player_id']}: missing sample size")
    # Reconcile fully collected event totals against per-map counts. A gap can
    # expose dropped series, side/aggregate double counting, or source drift.
    complete_events = {e["event_id"] for e in events if e["collect_maps"] == "True"
                       and e["matches_listed"] == e["matches_parsed"]}
    map_counts = defaultdict(Counter)
    missing_counts = set()
    for p in players:
        for k in ["kills", "deaths", "assists", "first_kills", "first_deaths", "rounds"]:
            v = num(p, k)
            if v is None:
                missing_counts.add((p["event_id"], p["vlr_player_id"], k))
            else:
                map_counts[(p["event_id"], p["vlr_player_id"])][k] += int(v)
        map_counts[(p["event_id"], p["vlr_player_id"])]["maps"] += 1
    for r in stats:
        if r["event_id"] not in complete_events:
            continue
        sums = map_counts[(r["event_id"], r["vlr_player_id"])]
        for k in ["kills", "deaths", "assists", "first_kills", "first_deaths", "rounds", "maps"]:
            v = num(r, k)
            if (r["event_id"], r["vlr_player_id"], k) in missing_counts:
                continue
            if v is not None and v != sums[k]:
                warnings.append(f"event {r['event_id']} player {r['vlr_player_id']} {k}: aggregate {v:g} vs maps {sums[k]}")
    receipt = {"schema_version": 1, "counts": {"events": len(events), "event_observations": len(stats),
               "unique_event_players": len({r['vlr_player_id'] for r in stats}), "maps": len(maps),
               "unique_map_players": len({r['vlr_player_id'] for r in players}),
               "unique_observed_players": len({r['vlr_player_id'] for r in stats + players}),
               "player_map_observations": len(players), "fully_reconciled_event_candidates": len(complete_events)},
               "player_map_missing_counts": {k: sum(num(r, k) is None for r in players)
                       for k in ["vlr_rating", "acs", "kills", "deaths", "assists", "kast_pct", "adr", "hs_pct", "first_kills", "first_deaths"]},
               "errors": sorted(set(errors)), "warnings": sorted(set(warnings)),
               "source_provenance_rows_checked": provenance_checks,
               "reconciliation_note": "Complete listed-and-parsed events only. Event pages can drift between retrievals; mismatches remain visible."}
    (data / "validation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if errors:
        raise ValueError(f"Dataset validation failed: {len(errors)} errors; see validation.json")
    return receipt


def lineup_eligible(m, observed):
    return len(observed) == 10 and all(
        len({r["vlr_player_id"] for r in observed
             if r["team_id"] == m[f"team{i}_id"] and r["vlr_player_id"]}) == 5
        for i in [1, 2])


def propose_quality(data):
    rows = read_csv(data / "player_event_stats.csv")
    crosswalk = read_csv(data / "roster_crosswalk.csv")
    roles = agent_roles()
    from esports_sim.registry.rosters import load_roster_pack
    from esports_sim.manager.development import overall
    pack = load_roster_pack("vct-2026", ROOT / "data")
    runtime = {}
    for team in pack.teams.values():
        for pid in team.player_ids:
            player = pack.players[pid]
            runtime[(team.name, normalize(player.handle))] = (pid, overall(player))
    for pid, player in pack.free_agents.items():
        runtime[("", normalize(player.handle))] = (pid, overall(player))
    groups = defaultdict(list)
    for r in rows:
        r["observed_role"] = role_for(r, roles)
        groups[(r["event_id"], r["observed_role"])].append(r)
    by_event = defaultdict(list)
    for r in rows:
        by_event[r["event_id"]].append(r)
    scored = []
    for r in rows:
        if not num(r, "rounds") or num(r, "vlr_rating") is None:
            continue
        peers = [p for p in groups[(r["event_id"], r["observed_role"])] if (num(p, "rounds") or 0) >= 100]
        role_control = len(peers) >= 5 and r["observed_role"] != "unknown"
        if not role_control:
            peers = [p for p in by_event[r["event_id"]] if (num(p, "rounds") or 0) >= 100] or by_event[r["event_id"]]
        z = 0.0
        for col, weight, floor in [("vlr_rating", .7, .08), ("adr", .15, 10.0), ("kast_pct", .15, 4.0)]:
            values = [num(p, col) for p in peers if num(p, col) is not None]
            if not values or num(r, col) is None:
                continue
            median = float(np.median(values))
            scale = max(floor, 1.4826 * float(np.median(np.abs(np.asarray(values) - median))))
            z += weight * float(np.clip((num(r, col) - median) / scale, -3, 3))
        n = num(r, "rounds")
        anchor = 74 if r["competition_tier"] == "1" else 64
        signal = float(np.clip(anchor + 9 * z * n / (n + 300), 45, 92))
        scored.append({"event_id": r["event_id"], "vlr_player_id": r["vlr_player_id"], "handle": r["handle"],
                       "competition_tier": r["competition_tier"], "observed_role": r["observed_role"],
                       "rounds": int(n), "role_control": role_control, "quality_signal": round(signal, 4),
                       "source_url": r["source_url"]})
    write_csv(data / "event_quality_signals.csv", scored)
    by_player = defaultdict(list)
    for r in scored:
        by_player[r["vlr_player_id"]].append(r)
    proposals = []
    for p in crosswalk:
        runtime_id, runtime_overall = runtime.get((p["pack_team"], normalize(p["handle"])), ("", None))
        observations = by_player.get(p["vlr_player_id"], []) if p["identity_status"] == "corroborated" else []
        n = sum(r["rounds"] for r in observations)
        signal = sum(r["quality_signal"] * r["rounds"] for r in observations) / n if n else None
        prior = float(p["pack_quality"])
        estimate = prior + (signal - prior) * n / (n + 600) if signal is not None else None
        proposals.append({**p, "runtime_player_id": runtime_id, "current_runtime_overall": round(runtime_overall, 2) if runtime_overall is not None else None,
                          "event_count": len(observations), "observed_rounds": n,
                          "box_score_quality_signal": round(signal, 2) if signal is not None else None,
                          "suggested_quality": round(estimate, 1) if estimate is not None else None,
                          "suggested_quality_delta": round(estimate - prior, 1) if estimate is not None else None,
                          "review_state": "heuristic_review_required" if n else "insufficient_identity_or_evidence",
                          "snapshot_warning": "Season-to-date evidence; may include matches after the July 9 pack snapshot"})
    write_csv(data / "quality_recommendations.csv", proposals)
    # Unmapped real competitors form a research shortlist, never asserted free agents.
    known = {r["vlr_player_id"] for r in crosswalk if r["identity_status"] == "corroborated"}
    prospects = []
    for pid, obs in sorted(by_player.items(), key=lambda x: int(x[0])):
        if pid in known:
            continue
        n = sum(r["rounds"] for r in obs)
        prospects.append({"vlr_player_id": pid, "handle": obs[-1]["handle"], "events": len(obs), "rounds": n,
                          "quality_signal": round(sum(r["quality_signal"] * r["rounds"] for r in obs) / n, 2),
                          "roster_status": "unverified", "review_state": "identity_and_contract_status_required"})
    write_csv(data / "unmapped_player_shortlist.csv", prospects)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(x, y, penalty=5.0):
    """Ridge logistic likelihood, no arbitrary home-side intercept."""
    coef = np.zeros(x.shape[1])
    eye = np.eye(x.shape[1])
    for _ in range(40):
        p = sigmoid(x @ coef)
        grad = x.T @ (p - y) + penalty * coef
        if float(np.max(np.abs(grad), initial=0)) < 1e-7:
            break
        hessian = x.T @ ((p * (1-p))[:, None] * x) + penalty * eye
        step = np.linalg.solve(hessian, grad)
        coef -= step
        if float(np.max(np.abs(step), initial=0)) < 1e-8:
            break
    return coef


def metrics(y, p):
    p = np.clip(p, 1e-8, 1-1e-8)
    return {"log_loss": round(float(-np.mean(y*np.log(p) + (1-y)*np.log(1-p))), 6),
            "brier_score": round(float(np.mean((p-y)**2)), 6),
            "accuracy": round(float(np.mean((p >= .5) == y)), 6)}


def outcome_model(data):
    all_maps = sorted(read_csv(data / "map_outcomes.csv"), key=lambda r: (r["played_at_utc"], int(r["match_id"]), int(r["map_id"])))
    rows = read_csv(data / "player_map_stats.csv")
    by_map = defaultdict(list)
    for r in rows:
        by_map[(r["match_id"], r["map_id"])].append(r)
    maps, eligibility = [], []
    for m in all_maps:
        observed = by_map[(m["match_id"], m["map_id"])]
        eligible = lineup_eligible(m, observed)
        eligibility.append({"match_id": m["match_id"], "map_id": m["map_id"], "event_id": m["event_id"],
                            "observed_player_rows": len(observed), "lineup_model_eligible": eligible,
                            "reason": "ten_identified_players" if eligible else "incomplete_source_lineup",
                            "source_url": m["source_url"]})
        if eligible:
            maps.append(m)
    write_csv(data / "map_model_eligibility.csv", eligibility)
    eligible_keys = {(m["match_id"], m["map_id"]) for m in maps}
    rows = [r for r in rows if (r["match_id"], r["map_id"]) in eligible_keys]
    ids = sorted({r["vlr_player_id"] for r in rows}, key=int)
    index = {pid: i for i, pid in enumerate(ids)}
    teams = sorted({r["team_id"] for r in rows}, key=int)
    ti = {t: i for i, t in enumerate(teams)}
    x, tx = np.zeros((len(maps), len(ids))), np.zeros((len(maps), len(teams)))
    y = np.array([int(m["winner_team_id"] == m["team1_id"]) for m in maps], dtype=float)
    for i, m in enumerate(maps):
        for r in by_map[(m["match_id"], m["map_id"])]:
            x[i, index[r["vlr_player_id"]]] = 1 if r["team_id"] == m["team1_id"] else -1
        tx[i, ti[m["team1_id"]]], tx[i, ti[m["team2_id"]]] = 1, -1
    # Split by date, keeping entire series and simultaneous calendar dates on
    # one side. Penalty selection uses an earlier split within training only.
    dates = sorted({m["played_at_utc"][:10] for m in maps})
    split_date = dates[min(len(dates)-1, int(len(dates)*.8))]
    train = np.array([m["played_at_utc"][:10] < split_date for m in maps])
    validation_date = dates[max(1, int(len(dates)*.6))]
    inner = np.array([m["played_at_utc"][:10] < validation_date for m in maps])
    inner_val = train & ~inner
    if not train.any() or train.all() or not inner_val.any():
        raise ValueError("Need multiple chronological train/validation/test dates")
    choices = []
    for lam in [1.0, 5.0, 20.0]:
        fitted = fit_logistic(x[inner], y[inner], lam)
        score = metrics(y[inner_val], sigmoid(x[inner_val] @ fitted))
        choices.append({"ridge_penalty": lam, **score})
    penalty = min(choices, key=lambda r: r["log_loss"])["ridge_penalty"]
    fit = fit_logistic(x[train], y[train], penalty)
    team_penalty = min([.2, 1.0, 4.0, 5.0, 20.0], key=lambda lam: metrics(y[inner_val], sigmoid(tx[inner_val] @ fit_logistic(tx[inner], y[inner], lam)))["log_loss"])
    team_fit = fit_logistic(tx[train], y[train], team_penalty)
    heldout = metrics(y[~train], sigmoid(x[~train] @ fit))
    baseline = metrics(y[~train], sigmoid(tx[~train] @ team_fit))
    # Refit on all observations only AFTER holding out and reporting performance.
    coef = fit_logistic(x, y, penalty)
    # Exact column equality identifies inseparable teammates. Ridge distributes
    # their shared evidence equally; it does not identify individual impact.
    signature = defaultdict(list)
    for j, pid in enumerate(ids):
        signature[x[:, j].tobytes()].append(pid)
    roles = agent_roles()
    observed = defaultdict(list)
    for r in rows:
        observed[r["vlr_player_id"]].append(r)
    player_roles = {p: Counter(role_for(r, roles) for r in observed[p]).most_common(1)[0][0] for p in ids}
    # Connected competition components prevent comparing coefficients between
    # circuits that have no shared match or player.
    parent = {p: p for p in ids}
    def root(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]; p = parent[p]
        return p
    for m in maps:
        ps = [r["vlr_player_id"] for r in by_map[(m["match_id"], m["map_id"])]]
        for p in ps[1:]:
            parent[root(p)] = root(ps[0])
    component = {p: root(p) for p in ids}
    replacement_pool = [p for p in ids if sum(r["competition_tier"] == "2" for r in observed[p]) >= 10]
    ranked = []
    for p in ids:
        j = index[p]; obs = observed[p]
        peers = [q for q in signature[x[:, j].tobytes()] if q != p]
        pool = [q for q in replacement_pool if component[q] == component[p] and player_roles[q] == player_roles[p] and q != p]
        fallback = False
        if len(pool) < 8:
            pool = [q for q in replacement_pool if component[q] == component[p] and q != p]
            fallback = True
        replacement = float(np.quantile([coef[index[q]] for q in pool], .25)) if len(pool) >= 8 else None
        ix = np.flatnonzero(x[:, j])
        sign = x[ix, j]
        own_logit = (x[ix] @ coef) * sign
        delta = coef[j] - replacement if replacement is not None else None
        wins = float(np.sum(sigmoid(own_logit) - sigmoid(own_logit-delta))) if delta is not None else None
        ranked.append({"vlr_player_id": p, "handle": obs[-1]["handle"], "observed_role": player_roles[p],
                       "maps": len(obs), "map_wins": sum(int(r["map_win"]) for r in obs),
                       "component_id": component[p], "lineup_logit_coefficient": round(float(coef[j]), 6),
                       "inseparable_teammates": "|".join(peers), "replacement_pool_players": len(pool),
                       "replacement_role_fallback": fallback,
                       "replacement_coefficient": round(replacement, 6) if replacement is not None else None,
                       "experimental_war_proxy": round(wins, 4) if wins is not None else None,
                       "experimental_war_per_100_maps": round(wins/len(obs)*100, 4) if wins is not None else None,
                       "review_state": "inseparable_lineup" if peers else "no_connected_replacement_pool" if replacement is None else "small_sample" if len(obs)<20 else "experimental_not_causal",
                       "use_for_game_overall": False})
    write_csv(data / "experimental_lineup_war.csv", ranked)
    locked = sum(bool(r["inseparable_teammates"]) for r in ranked)
    receipt = {"model_version": 1, "features": "Signed pre-match player identities (+1 team1, -1 team2); no same-map statistics",
               "source_maps": len(all_maps), "eligible_maps": len(maps), "excluded_incomplete_lineup_maps": len(all_maps)-len(maps),
               "target": "team1 map win", "ridge_penalty": penalty, "tuning": choices,
               "team_baseline_ridge_penalty": team_penalty,
               "split": {"validation_start_utc_date": validation_date, "test_start_utc_date": split_date,
                         "train_maps": int(train.sum()), "test_maps": int((~train).sum()), "unit": "UTC date, entire series stays together"},
               "test_lineup_model": heldout, "test_team_identity_baseline": baseline,
               "test_even_probability_baseline": metrics(y[~train], np.full((~train).sum(), .5)),
               "classification_tie_rule": "p=0.5 predicts team1. Even-probability accuracy is the team1 win frequency, not expected random coin-flip accuracy.",
               "beats_team_baseline_log_loss": heldout["log_loss"] < baseline["log_loss"],
               "exactly_inseparable_players": locked, "total_players": len(ids), "connected_components": len(set(component.values())),
               "replacement_definition": "25th percentile coefficient of same-component, same-dominant-role players with >=10 tier-2 maps; component-wide fallback if <8 peers; blank if still <8. Not the actual free-agent market.",
               "war_definition": "Sum over played maps of fitted P(win with player) minus fitted P(win replacing their coefficient with replacement); full-data refit after test evaluation.",
               "limits": ["Observational association, not causal WAR", "Teammate and opponent strengths enter through signed lineups but stable rosters cannot separate individual contributions",
                          "No economy, coaching, map/side preferences, patch, or schedule adjustments", "Regional disconnected coefficients are not comparable",
                          "No calibrated uncertainty intervals; map observations within a series are dependent", "No automatic use in roster ratings"]}
    (data / "model_evaluation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT / "data/research/vct-2026")
    p.add_argument("--validate-only", action="store_true")
    args = p.parse_args()
    receipt = validate(args.data)
    print(json.dumps(receipt["counts"], sort_keys=True))
    if not args.validate_only:
        propose_quality(args.data)
        model = outcome_model(args.data)
        summarize(args.data, receipt, model)
        print(json.dumps({"test_lineup": model["test_lineup_model"], "test_team": model["test_team_identity_baseline"], "inseparable": model["exactly_inseparable_players"]}, sort_keys=True))


def summarize(data, validation, model):
    manifest = json.loads((data / "event_manifest.json").read_text())
    crosswalk = read_csv(data / "roster_crosswalk.csv")
    free_agents = read_csv(data / "free_agent_review.csv")
    proposals = read_csv(data / "quality_recommendations.csv")
    manual_path = data / "manual_audit/result.json"
    manual = json.loads(manual_path.read_text()) if manual_path.exists() else None
    if manual:
        manual["matches_current_csv_hashes"] = all(
            hashlib.sha256((data / name).read_bytes()).hexdigest() == digest
            for name, digest in manual.get("checked_csv_sha256", {}).items()) and bool(manual.get("checked_csv_sha256"))
    receipt = {
        "schema_version": 1, "season": 2026,
        "pack_snapshot": manifest.get("pack_snapshot_date"), "research_snapshot": manifest.get("as_of_date"),
        "coverage": {"selected_events": len(manifest["events"]),
                     "full_map_events": sum(e["collect_maps"] for e in manifest["events"]),
                     "scope_note": manifest.get("scope_note", "Selected sample; not exhaustive worldwide coverage.")},
        "counts": {**validation["counts"], "source_pages": len(read_csv(data / "sources.csv")),
                   "pack_players": len(crosswalk), "pack_free_agents": len(free_agents),
                   "reviewable_quality_proposals": sum(bool(r["suggested_quality"]) for r in proposals)},
        "identity_status": dict(Counter(r["identity_status"] for r in crosswalk)),
        "free_agent_identity_status": dict(Counter(r["identity_status"] for r in free_agents)),
        "collection_issues": read_csv(data / "collection_issues.csv"),
        "validation_errors": len(validation["errors"]), "validation_warnings": len(validation["warnings"]),
        "source_provenance_rows_checked": validation["source_provenance_rows_checked"],
        "manual_browser_audit": manual,
        "model": {k: model[k] for k in ["eligible_maps", "excluded_incomplete_lineup_maps", "total_players",
                  "exactly_inseparable_players", "connected_components", "test_lineup_model", "test_team_identity_baseline"]},
        "rating_decision": "No automatic gameplay edits. Box-score quality proposals are authored heuristics; compare lineup and team baselines and inseparable player counts before interpreting WAR.",
        "free_agent_status": "Authored pack free agents reviewed; professional contract availability remains unverified. Historical retirement/bench and current team listings retained as evidence."
    }
    (data / "research_summary.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
