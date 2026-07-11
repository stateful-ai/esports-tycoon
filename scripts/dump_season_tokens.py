"""Match token corpus for world-model / match-RL work (Track C).

Simulates a deterministic corpus of matches over a generated campaign
world and writes each map's event log as a compact token sequence:
round flow, side-attributed kills (weapon class / headshot / trade),
buy tiers, utility, spike actions, gimmicks. Player ids and team ids
are deliberately erased — sides are ATK/DEF — so a model trains on
match GRAMMAR, not roster trivia. Movement/comms/whiff texture is out
of scope for v1 (the vocab is versioned; extending it bumps
VOCAB_VERSION and re-blesses the pinned-vocab test).

Outputs:
- ``<stem>.tokens.jsonl`` — one line per match: metadata + token ids
- ``<stem>.vocab.json``  — {version, tokens: [str, ...]} (id = index)

Usage:
    python scripts/dump_season_tokens.py [n_matches] [world_seed] [out-stem]

Deterministic: same args -> byte-identical corpus. ASCII-only output.
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

from esports_sim.manager.campaign import _dressed_gamedata, default_five, new_campaign
from esports_sim.registry import load_all
from esports_sim.sim import simulate_match

VOCAB_VERSION = 1

_SIDES = ("ATK", "DEF")
_WCLASSES = ("lmg", "pistol", "rifle", "shotgun", "smg", "sniper")
_BUY_TIERS = ("eco", "force", "half", "full")
_END_REASONS = ("elim", "spike_defused", "spike_detonation", "time")

# Per-player average spend -> buy tier. Coarse on purpose; the exact
# engine economy stays the source of truth, these just bucket it.
_BUY_BOUNDS = ((900, "eco"), (2000, "force"), (3200, "half"))


def build_vocab() -> list[str]:
    """The full closed vocabulary, sorted. Order defines token ids."""
    toks = {"MATCH_START", "MATCH_END", "ROUND_START", "PLANT", "DEFUSE"}
    for side in _SIDES:
        toks.add(f"GIMMICK_{side}")
        for tier in _BUY_TIERS:
            toks.add(f"BUY_{side}_{tier}")
        for flag in ("", "_FAIL"):
            toks.add(f"UTIL_{side}{flag}")
        for reason in _END_REASONS:
            toks.add(f"ROUND_END_{side}_{reason.upper()}")
        for wc in _WCLASSES:
            for hs in ("", "_HS"):
                for tr in ("", "_TRADE"):
                    toks.add(f"KILL_{side}_{wc.upper()}{hs}{tr}")
    return sorted(toks)


def _buy_tier(total_spent: int, n_players: int) -> str:
    avg = total_spent / max(n_players, 1)
    for bound, tier in _BUY_BOUNDS:
        if avg < bound:
            return tier
    return "full"


def tokenize(events, team_of: dict[str, str]) -> list[str]:
    """One match event list -> token sequence. `team_of` maps every
    dressed player to their team id; sides re-derive per round from the
    RoundStartEvent."""
    out: list[str] = ["MATCH_START"]
    atk_team = ""

    def side_of(pid: str) -> str:
        return "ATK" if team_of.get(pid, "") == atk_team else "DEF"

    # Buys are emitted between round.start and the first live event;
    # buffer them per round and flush as two per-side tier tokens.
    buys: dict[str, list[int]] = {"ATK": [], "DEF": []}

    def flush_buys() -> None:
        for side in _SIDES:
            if buys[side]:
                out.append(
                    f"BUY_{side}_{_buy_tier(sum(buys[side]), len(buys[side]))}"
                )
            buys[side] = []

    for e in events:
        t = e.type
        if t == "round.start":
            flush_buys()
            atk_team = e.attacking_team_id
            out.append("ROUND_START")
        elif t == "round.buy":
            buys[side_of(e.player_id)].append(e.spent)
        elif t == "round.kill":
            flush_buys()
            wc = _weapon_class(e.weapon_id)
            tok = f"KILL_{side_of(e.killer_id)}_{wc.upper()}"
            if e.headshot:
                tok += "_HS"
            if e.is_trade:
                tok += "_TRADE"
            out.append(tok)
        elif t == "round.utility_used":
            flush_buys()
            tok = f"UTIL_{side_of(e.player_id)}"
            if e.failed:
                tok += "_FAIL"
            out.append(tok)
        elif t == "round.spike_plant":
            flush_buys()
            out.append("PLANT")
        elif t == "round.spike_defuse":
            flush_buys()
            out.append("DEFUSE")
        elif t == "round.gimmick":
            flush_buys()
            out.append(f"GIMMICK_{side_of(e.player_id)}")
        elif t == "round.end":
            flush_buys()
            winner_side = "ATK" if e.winner_id == atk_team else "DEF"
            out.append(f"ROUND_END_{winner_side}_{e.reason.upper()}")
        elif t == "match.end":
            out.append("MATCH_END")
    return out


_WCLASS_BY_ID: dict[str, str] = {}


def _weapon_class(weapon_id: str) -> str:
    return _WCLASS_BY_ID.get(weapon_id, "rifle")


def main() -> int:
    n_matches = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    world_seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    stem = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("telemetry/tokens")

    gd = load_all()
    _WCLASS_BY_ID.update(
        {wid: str(w.weapon_class) for wid, w in gd.weapons.items()}
    )
    gs = new_campaign(gd, seed=world_seed)
    tier1 = sorted(t for t in gs.teams if gs.teams[t].tier == 1)
    pairs = list(combinations(tier1, 2))
    maps = sorted(gd.maps)
    vocab = build_vocab()
    tok_id = {t: i for i, t in enumerate(vocab)}

    stem.parent.mkdir(parents=True, exist_ok=True)
    vocab_path = stem.with_name(stem.name + ".vocab.json")
    vocab_path.write_text(
        json.dumps({"version": VOCAB_VERSION, "tokens": vocab}, indent=2),
        encoding="utf-8",
    )

    out_path = stem.with_name(stem.name + ".tokens.jsonl")
    n_tokens = 0
    with out_path.open("w", encoding="utf-8") as f:
        for i in range(n_matches):
            a, b = pairs[i % len(pairs)]
            map_id = maps[i % len(maps)]
            five = {tid: default_five(gs, tid) for tid in (a, b)}
            team_of = {pid: tid for tid in five for pid in five[tid]}
            rt_gd = _dressed_gamedata(gs, gd, five)
            events = simulate_match(rt_gd, a, b, map_id, seed=world_seed * 10_000 + i)
            toks = tokenize(events, team_of)
            unknown = [t for t in toks if t not in tok_id]
            if unknown:
                raise SystemExit(f"token outside vocab: {unknown[:3]}")
            n_tokens += len(toks)
            f.write(
                json.dumps(
                    {
                        "match": i,
                        "team_a": a,
                        "team_b": b,
                        "map": map_id,
                        "seed": world_seed * 10_000 + i,
                        "n_tokens": len(toks),
                        "tokens": [tok_id[t] for t in toks],
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    print(
        f"dumped {n_matches} matches, {n_tokens} tokens "
        f"(vocab {len(vocab)}, v{VOCAB_VERSION}) -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
