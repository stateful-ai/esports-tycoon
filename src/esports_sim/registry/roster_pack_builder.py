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
            attr_overrides:   # optional: pin specific attributes past the
              aim_precision: 92   # archetype shape, for deliberately lopsided
              game_sense: 34      # players (elite aim / weak IQ, and so on)

``src/future_prospects.yaml`` is optional. Entries use the same player fields
plus ``birth_year`` and ``region``; their age and debut year are derived from
the pack's ``src/pack.yaml:start_year``. They remain off-screen until age 17.

CLI usage: python scripts/build_roster_pack.py vct-2026

This module is also imported by `esports_sim.registry.roster_admin` so the
web admin-edit toggle can correct a single player/team's sheet and rebuild
the derived pack without shelling out to the script. `build()` is atomic —
every team is expanded and validated in memory before anything on disk is
touched, so a bad edit raises without leaving `teams/` half-rewritten.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import yaml

from esports_sim.manager import development
from esports_sim.manager.gen import _ARCHETYPES, _clamp
from esports_sim.registry.loader import DEFAULT_DATA_DIR, load_all
from esports_sim.schemas.common import Playstyle, Region, Role

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
_CAREER_PROFILE_FIELDS = {
    "potential", "career_volatility", "development_archetype",
    "development_peak_age", "development_peak_years", "development_decline_age",
    "development_realization",
}
# Fill playstyles for topping up partial tier-2 sheets to a full five.
_FILL_SLOTS = [
    (Playstyle.IGL, Role.CONTROLLER),
    (Playstyle.ENTRY, Role.DUELIST),
    (Playstyle.SUPPORT, Role.INITIATOR),
    (Playstyle.ANCHOR, Role.SENTINEL),
    (Playstyle.AWPER, Role.DUELIST),
]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return re.sub(r"_+", "_", s)


def identity_key(name: str) -> str:
    """Canonical human identity used to keep historical imports deduplicated."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _load_career_profiles(src_dir: Path) -> tuple[dict, dict[str, dict]]:
    """Load optional pack-wide defaults and named career-profile overrides."""
    path = src_dir / "career_profiles.yaml"
    if not path.is_file():
        return {}, {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = dict(raw.get("defaults", {}))
    unknown_defaults = sorted(set(defaults) - _CAREER_PROFILE_FIELDS)
    if unknown_defaults:
        raise SystemExit(f"career profile defaults: unknown fields {unknown_defaults}")
    profiles: dict[str, dict] = {}
    for cohort_name, cohort in (raw.get("cohorts", {}) or {}).items():
        cohort = dict(cohort or {})
        handles = cohort.pop("players", [])
        unknown = sorted(set(cohort) - _CAREER_PROFILE_FIELDS)
        if unknown:
            raise SystemExit(f"career profile cohort {cohort_name!r}: unknown fields {unknown}")
        for handle in handles:
            key = identity_key(str(handle))
            if key in profiles:
                raise SystemExit(f"career profile duplicates player {handle!r}")
            profiles[key] = dict(cohort)
    for handle, override in (raw.get("overrides", {}) or {}).items():
        key = identity_key(str(handle))
        override = dict(override or {})
        unknown = sorted(set(override) - _CAREER_PROFILE_FIELDS)
        if unknown:
            raise SystemExit(f"career profile override {handle!r}: unknown fields {unknown}")
        profiles[key] = {**profiles.get(key, {}), **override}
    return defaults, profiles


def _apply_career_profile(spec: dict, defaults: dict, profiles: dict[str, dict], used_profiles: set[str]) -> dict:
    key = identity_key(str(spec["handle"]))
    if key in profiles:
        used_profiles.add(key)
    return {**defaults, **profiles.get(key, {}), **spec}


def _rng_for(pack_id: str, label: str) -> np.random.Generator:
    h = hashlib.blake2b(f"{pack_id}:{label}".encode("ascii"), digest_size=8)
    return np.random.default_rng(int.from_bytes(h.digest(), "big"))


def _require_ascii(s: str, where: str) -> str:
    try:
        s.encode("ascii")
    except UnicodeEncodeError as e:
        raise SystemExit(f"non-ASCII text in {where}: {s!r}") from e
    return s


def expand_player(
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
    # Optional authored overrides for deliberately lopsided profiles (elite
    # aim / poor game sense, brilliant IGL / mediocre mechanics, etc.) —
    # pins specific attributes past what quality+archetype+jitter would
    # produce. Unlisted attributes are untouched.
    for attr_id, value in spec.get("attr_overrides", {}).items():
        if attr_id not in _ATTR_IDS:
            raise SystemExit(f"{pid}: unknown attr_overrides key {attr_id!r}")
        attributes[attr_id] = round(_clamp(float(value)), 1)

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

    if "personality_tags" in spec or "tags" in spec:
        spec_tags = spec.get("personality_tags") or spec.get("tags") or []
        tags = {str(t) for t in spec_tags}
    else:
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
    for field in sorted(_CAREER_PROFILE_FIELDS - {"potential"}):
        if field in spec and spec[field] is not None:
            player[field] = spec[field]
    if "potential" in spec:
        player["potential"] = float(spec["potential"])
    # Hidden ceiling via the same curve world-gen uses (age-aware).
    from esports_sim.schemas import Player
    p = Player(**player)
    if spec.get("potential") is not None:
        p.potential = round(max(development.overall(p), float(spec["potential"])), 1)
    else:
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


def build(pack_id: str, data_dir: Path | None = None) -> str:
    """Rebuild a pack's `teams/*.yaml`, `free_agents.yaml` and `pack.yaml`
    from its `src/*.yaml` sheets. Atomic: every team is expanded (and every
    validation run) in memory first, and disk is only touched once the
    whole pack expands cleanly — a bad sheet edit raises without leaving
    `teams/` half-deleted. Returns a one-line summary."""
    pack_dir = (data_dir or DEFAULT_DATA_DIR) / "rosters" / pack_id
    src_dir = pack_dir / "src"
    out_dir = pack_dir / "teams"
    career_defaults, career_profiles = _load_career_profiles(src_dir)
    used_career_profiles: set[str] = set()
    # Market/prospect intake sheets are not region sheets — handled below.
    specs = sorted(
        f for f in src_dir.glob("*.yaml")
        if f.name not in {
            "free_agents.yaml", "future_prospects.yaml",
            "future_archive_free_agents.yaml", "future_archive_prospects.yaml",
            "future_2026_backfill_free_agents.yaml",
            "future_2026_backfill_prospects.yaml",
            "career_profiles.yaml",
            "pack.yaml",
        }
    )
    if not specs:
        raise SystemExit(f"no spec files under {src_dir}")

    gd = load_all()

    regions: list[str] = []
    tier1_counts: dict[str, int] = {}
    tier2_counts: dict[str, int] = {}
    n_players = 0
    used_slugs: set[str] = set()
    active_identities: set[str] = set()
    team_yaml: dict[str, str] = {}  # slug -> rendered yaml text

    for spec_file in specs:
        raw = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        region = str(Region(raw["region"]))
        regions.append(region)
        for tspec in raw["teams"]:
            name = _require_ascii(str(tspec["name"]), spec_file.name)
            tier = int(tspec.get("tier", 1))
            slug = "team_" + slugify(name)
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
                p = _apply_career_profile(p, career_defaults, career_profiles, used_career_profiles)
                identity = identity_key(str(p["handle"]))
                if identity in active_identities:
                    raise SystemExit(
                        f"duplicate active-player handle {p['handle']!r}"
                    )
                active_identities.add(identity)
                pid = f"{slug}_{slugify(str(p['handle']))}"
                players.append(
                    expand_player(pack_id, pid, p, region, gd, slug)
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
            team_yaml[slug] = yaml.safe_dump(team, sort_keys=False, width=88)
            counts = tier1_counts if tier == 1 else tier2_counts
            counts[region] = counts.get(region, 0) + 1
            n_players += len(players)

    # Optional real free agents: src/free_agents.yaml carries unrostered
    # players (each entry is the same compact spec plus a `region:`), which
    # expand exactly like rostered players and seed the campaign FA pool.
    fa_sources = [
        src_dir / "free_agents.yaml",
        src_dir / "future_archive_free_agents.yaml",
        src_dir / "future_2026_backfill_free_agents.yaml",
    ]
    n_fas = 0
    fa_yaml: str | None = None
    if any(source.is_file() for source in fa_sources):
        out_fas = []
        seen_fa: set[str] = set()
        seen_fa_identities: set[str] = set()
        specs_fa = []
        for source in fa_sources:
            if source.is_file():
                raw_fas = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
                specs_fa.extend(raw_fas.get("free_agents", []))
        for spec in specs_fa:
            spec = _apply_career_profile(spec, career_defaults, career_profiles, used_career_profiles)
            region = str(Region(spec["region"]))
            pid = "fa_" + slugify(str(spec["handle"]))
            if pid in seen_fa:
                raise SystemExit(f"duplicate free-agent handle {spec['handle']!r}")
            identity = identity_key(str(spec["handle"]))
            if identity in active_identities or identity in seen_fa_identities:
                raise SystemExit(
                    f"free-agent handle duplicates active/imported player {spec['handle']!r}"
                )
            seen_fa.add(pid)
            seen_fa_identities.add(identity)
            player = expand_player(pack_id, pid, spec, region, gd, "fa")
            player["contract_weeks_left"] = 0  # signable from day one
            out_fas.append(player)
            n_fas += 1
        fa_yaml = yaml.safe_dump(
            {"free_agents": out_fas}, sort_keys=False, width=88
        )

    # Optional source metadata lets a partial/custom pack keep its friendly
    # name and request generated fill beyond the authored clubs. Older packs
    # without src/pack.yaml retain the original derived defaults.
    author_meta_file = src_dir / "pack.yaml"
    author_meta = (
        yaml.safe_load(author_meta_file.read_text(encoding="utf-8")) or {}
        if author_meta_file.is_file()
        else {}
    )
    start_year = author_meta.get("start_year")
    if start_year is not None:
        start_year = int(start_year)
    author_world = author_meta.get("world", {})
    declared_id = author_meta.get("id")
    if declared_id is not None and str(declared_id) != pack_id:
        raise SystemExit(
            f"src/pack.yaml id {declared_id!r} does not match {pack_id!r}"
        )
    declared_regions = author_world.get("league_regions")
    if declared_regions is not None:
        authored_regions = [str(Region(region)) for region in declared_regions]
        if (
            set(authored_regions) != set(regions)
            or len(authored_regions) != len(regions)
        ):
            raise SystemExit(
                "src/pack.yaml league_regions must match the region sheets"
            )
        regions = authored_regions

    # Floor 4: the regional playoff bracket needs four qualifiers. Empty
    # authored regions are legal in a partial pack; new_campaign fills them.
    authored_t1_max = max(tier1_counts.values(), default=0)
    requested_t1 = int(author_world.get("teams_per_region", authored_t1_max))
    teams_per_region = max(4, requested_t1, authored_t1_max)
    if teams_per_region > 16:
        raise SystemExit("teams_per_region must be between 4 and 16")
    tier2_per_region = int(author_world.get("tier2_per_region", 6))
    if not 0 <= tier2_per_region <= 16:
        raise SystemExit("tier2_per_region must be between 0 and 16")
    if len(set(tier1_counts.values())) > 1:
        print(f"WARN: uneven tier-1 regions {tier1_counts} — "
              f"shorter regions get generated fill at new-game.")
    meta = {
        "id": pack_id,
        "name": _require_ascii(
            str(author_meta.get("name", raw_meta_name(pack_id))), "pack name"
        ),
        "description": _require_ascii(
            str(author_meta.get(
                "description",
                "Imported real-world rosters. Attributes are estimates "
                "expanded deterministically from the src/ sheets by "
                "scripts/build_roster_pack.py.",
            )),
            "pack description",
        ),
        "start_year": start_year,
        "world": {
            "league_regions": regions,
            "teams_per_region": teams_per_region,
            "tier2_per_region": tier2_per_region,
        },
    }
    pack_yaml = yaml.safe_dump(meta, sort_keys=False)

    # Future real players stay outside the active market until they turn 17.
    # Their source sheet supplies a birth year; the starting age and debut year
    # are derived from pack start_year so a copied prospect cannot drift.
    future_yaml: str | None = None
    future_sources = [
        src_dir / "future_prospects.yaml",
        src_dir / "future_archive_prospects.yaml",
        src_dir / "future_2026_backfill_prospects.yaml",
    ]
    if any(source.is_file() for source in future_sources):
        if start_year is None:
            raise SystemExit("future_prospects.yaml requires src/pack.yaml start_year")
        future_out = []
        seen_future: set[str] = set()
        specs_future = []
        for source in future_sources:
            if source.is_file():
                raw_future = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
                specs_future.extend(raw_future.get("future_prospects", []))
        for spec in specs_future:
            spec = _apply_career_profile(spec, career_defaults, career_profiles, used_career_profiles)
            birth_year = int(spec["birth_year"])
            age = start_year - birth_year
            if not 0 <= age < 17:
                raise SystemExit(
                    f"future prospect {spec.get('handle', '?')!r}: age {age} is not under 17 at {start_year}"
                )
            pid = "future_" + slugify(str(spec["handle"]))
            if pid in seen_future or pid in used_slugs:
                raise SystemExit(f"duplicate future prospect id {pid!r}")
            seen_future.add(pid)
            prospect_spec = {k: v for k, v in spec.items() if k != "birth_year"}
            prospect_spec["age"] = age
            player = expand_player(pack_id, pid, prospect_spec, str(Region(spec["region"])), gd, "future")
            future_out.append({"player": player, "debut_year": birth_year + 17})
        future_yaml = yaml.safe_dump(
            {"future_prospects": future_out}, sort_keys=False, width=88
        )

    unused_profiles = sorted(set(career_profiles) - used_career_profiles)
    if unused_profiles:
        raise SystemExit("career profiles reference unknown players: " + ", ".join(unused_profiles))

    # Every team expanded and validated cleanly -> commit to disk now.
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.yaml"):
        old.unlink()
    for slug, text in team_yaml.items():
        (out_dir / f"{slug}.yaml").write_text(text, encoding="ascii")
    if fa_yaml is not None:
        (pack_dir / "free_agents.yaml").write_text(fa_yaml, encoding="ascii")
    future_out_file = pack_dir / "future_prospects.yaml"
    if future_yaml is not None:
        future_out_file.write_text(future_yaml, encoding="ascii")
    elif future_out_file.exists():
        future_out_file.unlink()
    (pack_dir / "pack.yaml").write_text(pack_yaml, encoding="ascii")

    summary = (
        f"pack {pack_id}: {sum(tier1_counts.values())} tier-1 + "
        f"{sum(tier2_counts.values())} tier-2 teams, {n_players} players, "
        f"{n_fas} free agents, regions {regions}, "
        f"teams_per_region {teams_per_region}"
    )
    print(summary)
    return summary


def raw_meta_name(pack_id: str) -> str:
    return pack_id.replace("-", " ").upper()
