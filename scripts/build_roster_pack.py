"""Expand a compact roster spec into a full roster pack.

Reads  data/rosters/<pack>/src/*.yaml   (hand-editable research sheets)
Writes data/rosters/<pack>/teams/*.yaml (full Team + Player bundles)
   and data/rosters/<pack>/pack.yaml    (meta + world shape)

Deterministic: every derived number (attribute jitter, masteries, tags,
contract lengths) comes from a blake2b hash of pack id + player id, so
rebuilding the pack from the same specs is byte-identical. Real players
therefore have the SAME sheet in every campaign, at any seed.

Spec shape per src file:

    region: americas
    teams:
      - name: Sentinels
        tag: SEN
        tier: 1
        prestige: 92
        partial: false        # optional; tier-2 sheets may be incomplete
        players:
          - handle: zekken
            real_name: Zachary Patrone
            age: 21
            role: duelist
            playstyle: entry
            igl: false
            quality: 82       # overall 50-88; becomes the attribute base
            agents: [jett, raze]

Usage: python scripts/build_roster_pack.py vct-2026
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from esports_sim.manager import development  # noqa: E402
from esports_sim.manager.gen import _ARCHETYPES, _clamp  # noqa: E402
from esports_sim.registry.loader import load_all  # noqa: E402
from esports_sim.schemas.common import Playstyle, Region, Role  # noqa: E402

_ATTR_IDS = [
    "aim_precision", "aim_reactivity", "movement", "game_sense",
    "utility_usage", "positioning", "clutch_factor", "tilt_resistance",
    "composure", "comms_quality",
]
_TAG_POOL = [
    "grinder", "streamer", "quiet", "hot_head", "veteran", "rookie",
    "team_player", "perfectionist", "independent", "analytical", "flashy",
    "clutch_gene", "slow_starter", "fan_favorite",
]
# Fill playstyles for topping up partial tier-2 sheets to a full five.
_FILL_SLOTS = [
    (Playstyle.IGL, Role.CONTROLLER),
    (Playstyle.ENTRY, Role.DUELIST),
    (Playstyle.SUPPORT, Role.INITIATOR),
    (Playstyle.ANCHOR, Role.SENTINEL),
    (Playstyle.AWPER, Role.DUELIST),
]


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return re.sub(r"_+", "_", s)


def _rng_for(pack_id: str, label: str) -> np.random.Generator:
    h = hashlib.blake2b(f"{pack_id}:{label}".encode("ascii"), digest_size=8)
    return np.random.default_rng(int.from_bytes(h.digest(), "big"))


def _require_ascii(s: str, where: str) -> str:
    try:
        s.encode("ascii")
    except UnicodeEncodeError as e:
        raise SystemExit(f"non-ASCII text in {where}: {s!r}") from e
    return s


def _expand_player(
    pack_id: str,
    pid: str,
    spec: dict,
    region: str,
    gd,
    team_slug: str,
) -> dict:
    rng = _rng_for(pack_id, pid)
    handle = _require_ascii(str(spec["handle"]), pid)
    quality = float(spec["quality"])
    age = int(spec.get("age", 22))
    role = Role(spec["role"])
    playstyle = Playstyle(spec["playstyle"])

    shape = _ARCHETYPES[playstyle]
    attributes = {}
    for attr_id in _ATTR_IDS:
        # Tighter jitter than world-gen (3.5 vs 5): these are known
        # quantities, the archetype does the differentiating.
        base = quality + shape.get(attr_id, 0.0) + rng.normal(0, 3.5)
        attributes[attr_id] = round(_clamp(base), 1)

    # Agent pool: the spec's signature agents, topped up from same-role
    # agents (or any agent for flex players) to at least two picks.
    picks = [str(a) for a in spec.get("agents", [])][:3]
    for a in picks:
        if a not in gd.agents:
            raise SystemExit(f"{pid}: unknown agent id {a!r}")
    if len(picks) < 2:
        same_role = sorted(
            a.id for a in gd.agents.values()
            if a.role == role and a.id not in picks
        ) or sorted(a.id for a in gd.agents.values() if a.id not in picks)
        while len(picks) < 2 and same_role:
            picks.append(same_role.pop(0))
    agent_pool = [
        {
            "agent_id": a,
            # First-listed agent is the main: masteries step down the list.
            "mastery": round(
                _clamp(quality + 14 - 5 * i + rng.normal(0, 4), 30, 99), 1
            ),
        }
        for i, a in enumerate(picks)
    ]
    # Baseline the rest of the cast (mirrors gen.py): same-role agents are
    # at least okay, off-role playable-but-weak, with a rare off-role gap.
    same_role = sorted(
        a.id for a in gd.agents.values() if a.role == role and a.id not in picks
    )
    off_role = sorted(
        a.id for a in gd.agents.values() if a.role != role and a.id not in picks
    )
    for aid in same_role:
        agent_pool.append({
            "agent_id": aid,
            "mastery": round(_clamp(quality - 8 + rng.normal(0, 4), 35, 80), 1),
        })
    for aid in off_role:
        if rng.random() < 0.06:  # never touched the agent — the rare gap
            agent_pool.append({
                "agent_id": aid,
                "mastery": round(float(rng.uniform(0, 8)), 1),
            })
        else:
            agent_pool.append({
                "agent_id": aid,
                "mastery": round(_clamp(quality - 20 + rng.normal(0, 5), 12, 60), 1),
            })
    map_pool = [
        {
            "map_id": mid,
            "mastery": round(_clamp(quality + rng.normal(8, 6), 30, 99), 1),
        }
        for mid in sorted(gd.maps)
    ]

    tags = {str(t) for t in rng.choice(_TAG_POOL, size=2, replace=False)}
    tags.discard("veteran")
    tags.discard("rookie")
    if age >= 28:
        tags.add("veteran")
    if age <= 18:
        tags.add("rookie")

    salary = max(int(np.round((quality ** 1.6) * 6 / 100) * 100), 1200)
    # Optional authored identity: `country: BR` and
    # `languages: [{lang: pt, level: 95}, {lang: en, level: 60}]` on the
    # src sheet. Absent -> left empty here; the campaign's identity heal
    # derives a region-plausible one deterministically at load.
    languages = [
        {"lang": str(l["lang"]), "level": float(l.get("level", 80))}
        for l in spec.get("languages", [])
    ][:3]
    player = {
        "id": pid,
        "handle": handle,
        "real_name": _require_ascii(str(spec.get("real_name", "")), pid),
        "region": region,
        "country": _require_ascii(str(spec.get("country", "")), pid),
        "languages": languages,
        "age": age,
        "role": str(role),
        "playstyle": str(playstyle),
        "attributes": attributes,
        "agent_pool": agent_pool,
        "map_pool": map_pool,
        "salary": salary,
        "contract_weeks_left": int(rng.integers(30, 80)),
        "morale": round(float(rng.uniform(60, 85)), 1),
        "stamina": round(float(rng.uniform(80, 100)), 1),
        "form": round(float(rng.uniform(45, 60)), 1),
        "personality_tags": sorted(tags),
    }
    # Hidden ceiling via the same curve world-gen uses (age-aware).
    from esports_sim.schemas import Player

    p = Player(**player)
    development.assign_potential(p, rng)
    player["potential"] = p.potential
    return player


def _fill_player_spec(rng: np.random.Generator, i: int, team_q: float) -> dict:
    """Synthetic academy player to top up a partial tier-2 sheet."""
    style, role = _FILL_SLOTS[i % len(_FILL_SLOTS)]
    return {
        "handle": f"prospect{i + 1}",
        "real_name": "",
        "age": int(rng.integers(17, 21)),
        "role": str(role),
        "playstyle": str(style),
        "igl": style is Playstyle.IGL,
        "quality": int(np.clip(team_q + rng.normal(-3, 3), 45, 70)),
        "agents": [],
    }


def build(pack_id: str) -> None:
    pack_dir = REPO / "data" / "rosters" / pack_id
    src_dir = pack_dir / "src"
    out_dir = pack_dir / "teams"
    # free_agents.yaml is the FA spec, not a region sheet — handled below.
    specs = sorted(
        f for f in src_dir.glob("*.yaml") if f.name != "free_agents.yaml"
    )
    if not specs:
        raise SystemExit(f"no spec files under {src_dir}")

    gd = load_all()
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.yaml"):
        old.unlink()

    regions: list[str] = []
    tier1_counts: dict[str, int] = {}
    tier2_counts: dict[str, int] = {}
    n_players = 0
    used_slugs: set[str] = set()

    for spec_file in specs:
        raw = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        region = str(Region(raw["region"]))
        regions.append(region)
        for tspec in raw["teams"]:
            name = _require_ascii(str(tspec["name"]), spec_file.name)
            tier = int(tspec.get("tier", 1))
            slug = "team_" + _slug(name)
            if slug in used_slugs:
                raise SystemExit(f"duplicate team slug {slug!r}")
            used_slugs.add(slug)

            pspecs = list(tspec.get("players", []))
            igls = [p for p in pspecs if p.get("igl")]
            if tier == 1 and len(pspecs) != 5:
                raise SystemExit(f"{name}: tier-1 team needs exactly 5 players")
            if tier == 1 and len(igls) != 1:
                raise SystemExit(f"{name}: tier-1 team needs exactly one IGL")
            if len(pspecs) > 5:
                raise SystemExit(f"{name}: more than 5 players")
            # Top up partial (tier-2) sheets to a playable five.
            fill_rng = _rng_for(pack_id, f"{slug}:fill")
            team_q = float(
                np.mean([p["quality"] for p in pspecs]) if pspecs else 55.0
            )
            i = 0
            while len(pspecs) < 5:
                fp = _fill_player_spec(fill_rng, i, team_q)
                if igls:  # never a second IGL
                    fp["igl"] = False
                    if fp["playstyle"] == str(Playstyle.IGL):
                        fp["playstyle"] = str(Playstyle.SUPPORT)
                elif fp["igl"]:
                    igls.append(fp)
                pspecs.append(fp)
                i += 1

            players = []
            captain_id = None
            for p in pspecs:
                pid = f"{slug}_{_slug(str(p['handle']))}"
                players.append(
                    _expand_player(pack_id, pid, p, region, gd, slug)
                )
                if p.get("igl"):
                    captain_id = pid
            if captain_id is None:
                # Partial sheet with no confirmed IGL: best game-sense calls.
                captain_id = max(
                    players, key=lambda pl: pl["attributes"]["game_sense"]
                )["id"]

            prestige = float(tspec.get("prestige", 50))
            balance = (
                int(300_000 + prestige * 6_000)
                if tier == 1
                else int(60_000 + prestige * 3_000)
            )
            fans = int(prestige**2 * (90 if tier == 1 else 15))
            chem_rng = _rng_for(pack_id, f"{slug}:chem")
            team = {
                "id": slug,
                "name": name,
                "tag": _require_ascii(str(tspec["tag"]), name).upper(),
                "region": region,
                "tier": tier,
                "captain_id": captain_id,
                "balance": balance,
                "reputation": round(_clamp(prestige, 20, 95), 1),
                "fan_count": fans,
                "chemistry": round(float(chem_rng.uniform(58, 82)), 1),
                "players": players,
            }
            (out_dir / f"{slug}.yaml").write_text(
                yaml.safe_dump(team, sort_keys=False, width=88),
                encoding="ascii",
            )
            counts = tier1_counts if tier == 1 else tier2_counts
            counts[region] = counts.get(region, 0) + 1
            n_players += len(players)

    # Optional real free agents: src/free_agents.yaml carries unrostered
    # players (each entry is the same compact spec plus a `region:`), which
    # expand exactly like rostered players and seed the campaign FA pool.
    fa_src = src_dir / "free_agents.yaml"
    n_fas = 0
    if fa_src.is_file():
        raw_fas = yaml.safe_load(fa_src.read_text(encoding="utf-8")) or {}
        out_fas = []
        seen_fa: set[str] = set()
        for spec in raw_fas.get("free_agents", []):
            region = str(Region(spec["region"]))
            pid = "fa_" + _slug(str(spec["handle"]))
            if pid in seen_fa:
                raise SystemExit(f"duplicate free-agent handle {spec['handle']!r}")
            seen_fa.add(pid)
            player = _expand_player(pack_id, pid, spec, region, gd, "fa")
            player["contract_weeks_left"] = 0  # signable from day one
            out_fas.append(player)
            n_fas += 1
        (pack_dir / "free_agents.yaml").write_text(
            yaml.safe_dump({"free_agents": out_fas}, sort_keys=False, width=88),
            encoding="ascii",
        )

    # Floor 4: the regional playoff bracket needs four qualifiers.
    teams_per_region = max(4, max(tier1_counts.values()))
    if len(set(tier1_counts.values())) > 1:
        print(f"WARN: uneven tier-1 regions {tier1_counts} — "
              f"shorter regions get generated fill at new-game.")
    meta = {
        "id": pack_id,
        "name": raw_meta_name(pack_id),
        "description": (
            "Imported real-world rosters. Attributes are estimates expanded "
            "deterministically from the src/ sheets by "
            "scripts/build_roster_pack.py."
        ),
        "world": {
            "league_regions": regions,
            "teams_per_region": teams_per_region,
            "tier2_per_region": 6,
        },
    }
    (pack_dir / "pack.yaml").write_text(
        yaml.safe_dump(meta, sort_keys=False), encoding="ascii"
    )
    print(
        f"pack {pack_id}: {sum(tier1_counts.values())} tier-1 + "
        f"{sum(tier2_counts.values())} tier-2 teams, {n_players} players, "
        f"{n_fas} free agents, regions {regions}, "
        f"teams_per_region {teams_per_region}"
    )


def raw_meta_name(pack_id: str) -> str:
    return pack_id.replace("-", " ").upper()


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "vct-2026")
