"""Season-level campaign token corpus for world-model work (Track C).

The match-level corpus (``dump_season_tokens.py``) captures match GRAMMAR;
this captures season GRAMMAR: one token stream per (tier-1 team, season)
over a headless multi-season campaign. Team and player ids are erased from
the tokens — a stream reads as an anonymous org's season arc: weekly
results, chronicle beats (titles, signings, rivalries, dismissals...),
phase transitions, and a season-end strength bucket derived from the
stream's own win rate.

Outputs:
- ``<stem>.tokens.jsonl`` — one line per (team, season): metadata + token ids
- ``<stem>.vocab.json``  — {version, tokens: [str, ...]} (id = index)

Usage:
    python scripts/dump_campaign_tokens.py [n_seasons] [world_seed] [out-stem]

Deterministic: same args -> byte-identical corpus. ASCII-only output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.chronicle import KIND_IMPORTANCE
from esports_sim.registry import load_all

VOCAB_VERSION = 1

# Season-end strength buckets from the stream's own win rate (title beats
# override) — no standings API dependency, so the tokenizer can never drift
# from a resolver it does not read.
_TITLE_KINDS = ("champions_title", "masters_title", "regional_title")


def build_vocab() -> list[str]:
    """The full closed vocabulary, sorted. Order defines token ids."""
    toks = {
        "SEASON_START", "SEASON_END", "WEEK",
        "PHASE_PLAYOFFS", "PHASE_OFFSEASON",
        "RESULT_WIN", "RESULT_LOSS",
        "PLACE_TITLE", "PLACE_STRONG", "PLACE_MID", "PLACE_WEAK",
    }
    for kind in KIND_IMPORTANCE:
        toks.add(f"CHRON_{kind.upper()}")
    # chronicle.record() accepts ANY kind string (default importance), so the
    # closed vocab needs a catch-all for kinds outside the canonical table
    # (e.g. "culture", "leadership" from culture sessions).
    toks.add("CHRON_OTHER")
    return sorted(toks)


def _place_token(wins: int, losses: int, titled: bool) -> str:
    if titled:
        return "PLACE_TITLE"
    total = wins + losses
    rate = wins / total if total else 0.5
    if rate >= 0.6:
        return "PLACE_STRONG"
    if rate >= 0.4:
        return "PLACE_MID"
    return "PLACE_WEAK"


def dump_campaign(n_seasons: int, world_seed: int, stem: Path) -> dict[str, int]:
    gd = load_all()
    gs = new_campaign(gd, seed=world_seed)
    tier1 = sorted(t for t in gs.teams if gs.teams[t].tier == 1)

    vocab = build_vocab()
    tok_id = {t: i for i, t in enumerate(vocab)}

    stem.parent.mkdir(parents=True, exist_ok=True)
    vocab_path = stem.with_name(stem.name + ".vocab.json")
    vocab_path.write_text(
        json.dumps({"version": VOCAB_VERSION, "tokens": vocab}, indent=2),
        encoding="utf-8",
    )

    # Live accumulators for the season in progress.
    streams: dict[str, list[str]] = {tid: ["SEASON_START"] for tid in tier1}
    record: dict[str, list[int]] = {tid: [0, 0] for tid in tier1}  # [wins, losses]
    titled: dict[str, bool] = {tid: False for tid in tier1}
    lines: list[dict] = []
    season = gs.season
    prev_phase = gs.phase
    chron_mark = len(gs.chronicle)

    def _close_season(closing: int) -> None:
        for tid in tier1:
            wins, losses = record[tid]
            streams[tid].append(_place_token(wins, losses, titled[tid]))
            streams[tid].append("SEASON_END")
            lines.append({
                "season": closing,
                "team": tid,
                "wins": wins,
                "losses": losses,
                "n_tokens": len(streams[tid]),
                "tokens": [tok_id[t] for t in streams[tid]],
            })
            streams[tid] = ["SEASON_START"]
            record[tid] = [0, 0]
            titled[tid] = False

    max_weeks = n_seasons * 120  # hard stop well past any real season length
    weeks = 0
    while len(lines) < n_seasons * len(tier1):
        weeks += 1
        if weeks > max_weeks:
            raise SystemExit(
                f"campaign never produced {n_seasons} rollovers in {max_weeks} weeks"
            )
        report = advance_week(gs, gd)

        for tid in tier1:
            streams[tid].append("WEEK")
        if gs.phase != prev_phase and gs.phase in ("playoffs", "offseason"):
            for tid in tier1:
                streams[tid].append(f"PHASE_{gs.phase.upper()}")
        prev_phase = gs.phase

        for fx in report.fixtures:
            if not fx.played or fx.tier != 1 or fx.winner_id is None:
                continue
            for tid in (fx.team_a, fx.team_b):
                if tid not in streams:
                    continue
                won = fx.winner_id == tid
                streams[tid].append("RESULT_WIN" if won else "RESULT_LOSS")
                record[tid][0 if won else 1] += 1

        # Chronicle beats added this tick, attributed to their org. Entries
        # are appended in deterministic campaign order; keep that order.
        for entry in gs.chronicle[chron_mark:]:
            tid = entry.team_id
            if tid in streams:
                tok = f"CHRON_{entry.kind.upper()}"
                streams[tid].append(tok if tok in tok_id else "CHRON_OTHER")
                if entry.kind in _TITLE_KINDS:
                    titled[tid] = True
        chron_mark = len(gs.chronicle)

        if gs.season != season:
            _close_season(season)
            season = gs.season
            chron_mark = len(gs.chronicle)

    out_path = stem.with_name(stem.name + ".tokens.jsonl")
    n_tokens = 0
    with out_path.open("w", encoding="utf-8") as f:
        for line in lines:
            n_tokens += line["n_tokens"]
            f.write(json.dumps(line, sort_keys=True) + "\n")
    return {"streams": len(lines), "tokens": n_tokens, "vocab": len(vocab)}


def main() -> int:
    n_seasons = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    world_seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    stem = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("telemetry/campaign_tokens")
    stats = dump_campaign(n_seasons, world_seed, stem)
    print(
        f"dumped {stats['streams']} team-season streams, {stats['tokens']} tokens "
        f"(vocab {stats['vocab']}, v{VOCAB_VERSION}) -> "
        f"{stem.with_name(stem.name + '.tokens.jsonl')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
