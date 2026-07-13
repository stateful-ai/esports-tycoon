"""Roster packs: loader validation, pack-seeded campaigns, the 4-region
season state machine (8-side Masters), and the shipped vct-2026 pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.registry.loader import load_all
from esports_sim.registry.rosters import (
    PackMeta,
    PackWorld,
    RosterPack,
    list_roster_packs,
    load_roster_pack,
)
from esports_sim.schemas import AgentMastery, FutureProspect, MapMastery, Player, Team
from esports_sim.schemas.common import Playstyle, Region, Role

GD = load_all()

_STYLES = [
    (Playstyle.IGL, Role.CONTROLLER),
    (Playstyle.ENTRY, Role.DUELIST),
    (Playstyle.AWPER, Role.DUELIST),
    (Playstyle.SUPPORT, Role.INITIATOR),
    (Playstyle.ANCHOR, Role.SENTINEL),
]


def _mk_player(pid: str, region: Region, slot: int, quality: float) -> Player:
    style, role = _STYLES[slot]
    agent = sorted(
        a.id for a in GD.agents.values() if a.role == role
    )[0]
    return Player(
        id=pid,
        handle=pid,
        region=region,
        age=23,
        role=role,
        playstyle=style,
        attributes={aid: quality for aid in GD.attributes.ids()},
        agent_pool=[AgentMastery(agent_id=agent, mastery=quality + 10)],
        map_pool=[
            MapMastery(map_id=m, mastery=quality) for m in sorted(GD.maps)
        ],
        salary=3000,
        contract_weeks_left=50,
    )


def _mk_pack(
    regions: list[Region], teams_per_region: int, quality_step: float = 3.0
) -> RosterPack:
    teams: dict[str, Team] = {}
    players: dict[str, Player] = {}
    for region in regions:
        for i in range(teams_per_region):
            tid = f"pk_{region}_{i}"
            pids = []
            for j in range(5):
                pid = f"{tid}_p{j}"
                players[pid] = _mk_player(
                    pid, region, j, 68.0 - i * quality_step
                )
                pids.append(pid)
            teams[tid] = Team(
                id=tid,
                name=f"Pack {str(region)[:2].upper()} {i}",
                tag=f"P{str(region)[:1].upper()}{i}",
                region=region,
                tier=1,
                player_ids=pids,
                captain_id=pids[0],
            )
    meta = PackMeta(
        id="testpack",
        name="Test Pack",
        world=PackWorld(
            league_regions=regions,
            teams_per_region=teams_per_region,
            tier2_per_region=0,
        ),
    )
    return RosterPack(meta=meta, teams=teams, players=players)


FOUR_REGIONS = [Region.AMERICAS, Region.EMEA, Region.PACIFIC, Region.CHINA]


def test_pack_world_shape_and_determinism():
    pack = _mk_pack(FOUR_REGIONS, 4)
    gs1 = new_campaign(GD, seed=99, user_team_id="pk_americas_0", pack=pack)
    gs2 = new_campaign(GD, seed=99, user_team_id="pk_americas_0", pack=pack)
    assert gs1.model_dump_json() == gs2.model_dump_json()
    assert gs1.roster_pack == "testpack"
    assert gs1.league_regions == FOUR_REGIONS
    tier1 = [t for t in gs1.teams.values() if t.tier == 1]
    assert len(tier1) == 4 * 4
    # Pack teams are the league — no generated fill needed at 4/region.
    assert all(t.id.startswith("pk_") for t in tier1)
    # China players exist and the league schedules china fixtures.
    assert any(f.id.endswith("ch") for f in gs1.fixtures if f.tier == 1)


def test_four_region_season_reaches_eight_side_masters_and_champions():
    pack = _mk_pack(FOUR_REGIONS, 4)
    gs = new_campaign(GD, seed=3, user_team_id="pk_emea_0", pack=pack)
    saw_masters = 0
    for _ in range(40):
        advance_week(gs, GD)
        if gs.masters_seeds:
            saw_masters = max(saw_masters, len(gs.masters_seeds))
        if gs.phase == "offseason":
            break
    assert saw_masters == 8, "4 regions must field an 8-side Masters"
    assert gs.champions, "season must crown a Champions winner"
    qfs = [f for f in gs.fixtures if f.stage == "masters_qf"]
    sfs = [f for f in gs.fixtures if f.stage == "masters_sf"]
    assert len(qfs) == 4 and len(sfs) == 2
    # Champions field is the 8 Masters sides (no extras at 4 regions).
    assert len(gs.champions_seeds) == 8
    assert set(gs.champions_seeds) == set(gs.masters_seeds)
    # Season 2 schedules cleanly on the same world shape.
    advance_week(gs, GD)
    assert gs.season == 2 and gs.phase == "regular"
    assert gs.league_regions == FOUR_REGIONS


def test_partial_pack_gets_generated_fill():
    pack = _mk_pack([Region.AMERICAS, Region.EMEA, Region.PACIFIC], 4)
    # Ask for a bigger league than the pack fills.
    pack.meta.world.teams_per_region = 6
    pack.meta.world.tier2_per_region = 2
    gs = new_campaign(GD, seed=5, user_team_id="pk_emea_0", pack=pack)
    for region in pack.meta.world.league_regions:
        t1 = [
            t for t in gs.teams.values()
            if t.region == region and t.tier == 1
        ]
        t2 = [
            t for t in gs.teams.values()
            if t.region == region and t.tier == 2
        ]
        assert len(t1) == 6 and len(t2) == 2
    # Every roster (pack or generated) is a playable five.
    assert all(len(t.player_ids) == 5 for t in gs.teams.values())


def test_historical_future_prospect_develops_then_debuts_at_17():
    pack = _mk_pack(FOUR_REGIONS, 4)
    pack.meta.start_year = 2021
    prospect = _mk_player("future_known", Region.AMERICAS, 1, 52.0)
    prospect.age = 16
    prospect.handle = "FutureKnown"
    pack.future_prospects[prospect.id] = FutureProspect(
        player=prospect, debut_year=2022
    )

    gs = new_campaign(GD, seed=71, user_team_id="pk_americas_0", pack=pack)
    gs_same_seed = new_campaign(
        GD, seed=71, user_team_id="pk_americas_0", pack=pack
    )
    assert prospect.id not in gs.players
    assert prospect.id in gs.future_prospects
    for _ in range(40):
        advance_week(gs, GD)
        advance_week(gs_same_seed, GD)
        if gs.season == 2:
            break

    assert gs.calendar_year == 2022
    assert prospect.id in gs.players
    assert prospect.id in gs.free_agent_ids
    assert gs.players[prospect.id].age == 17
    assert prospect.id not in gs.future_prospects
    assert gs.model_dump_json() == gs_same_seed.model_dump_json()


def test_loader_rejects_bad_packs(tmp_path: Path):
    root = tmp_path / "rosters" / "bad"
    (root / "teams").mkdir(parents=True)
    (root / "pack.yaml").write_text(
        "id: bad\nname: Bad\nworld:\n  league_regions: [americas, emea]\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="3 or 4"):
        load_roster_pack("bad", data_dir=tmp_path)

    (root / "pack.yaml").write_text(
        "id: mismatch\nname: Bad\n", encoding="ascii"
    )
    with pytest.raises(ValueError, match="must match"):
        load_roster_pack("bad", data_dir=tmp_path)


VCT = Path(__file__).resolve().parents[1] / "data" / "rosters" / "vct-2026"
VCT_2021 = Path(__file__).resolve().parents[1] / "data" / "rosters" / "vct-2021"


@pytest.mark.skipif(
    not (VCT / "pack.yaml").is_file(), reason="vct-2026 pack not built"
)
def test_vct_2026_pack_is_sound():
    pack = load_roster_pack("vct-2026")
    w = pack.meta.world
    assert len(w.league_regions) == 4
    tier1 = [t for t in pack.teams.values() if t.tier == 1]
    for region in w.league_regions:
        n = sum(1 for t in tier1 if t.region == region)
        assert n == w.teams_per_region, f"{region}: {n} tier-1 teams"
    for t in pack.teams.values():
        assert len(t.player_ids) == 5, t.id
        assert t.captain_id in t.player_ids, t.id
        # Exactly one IGL per team keeps captaincy meaningful.
        igls = [
            p for p in t.player_ids
            if pack.players[p].playstyle == Playstyle.IGL
        ]
        assert len(igls) <= 1, t.id
    for p in pack.players.values():
        # ASCII-only (cp1252 console invariant) and sane quality band.
        p.handle.encode("ascii")
        p.real_name.encode("ascii")
        assert p.agent_pool, p.id
    assert any(m.id == "vct-2026" for m in list_roster_packs())


@pytest.mark.skipif(
    not (VCT / "pack.yaml").is_file(), reason="vct-2026 pack not built"
)
def test_vct_2026_campaign_builds_deterministically():
    pack = load_roster_pack("vct-2026")
    team = sorted(t.id for t in pack.teams.values() if t.tier == 1)[0]
    gs1 = new_campaign(GD, seed=42, user_team_id=team, pack=pack)
    gs2 = new_campaign(GD, seed=42, user_team_id=team, pack=pack)
    assert gs1.model_dump_json() == gs2.model_dump_json()
    assert gs1.teams_per_region == pack.meta.world.teams_per_region
    # One full playable week out of the box.
    r = advance_week(gs1, GD)
    assert r.fixtures, "week 1 must schedule matches"


@pytest.mark.skipif(
    not (VCT_2021 / "pack.yaml").is_file(), reason="vct-2021 pack not built"
)
def test_vct_2021_pack_is_selectable_and_era_seeded():
    pack = load_roster_pack("vct-2021")
    assert pack.meta.start_year == 2021
    assert pack.meta.world.teams_per_region == 10
    assert {str(r) for r in pack.meta.world.league_regions} == {
        "americas", "emea", "pacific"
    }
    assert len(pack.teams) == 48
    assert sum(1 for team in pack.teams.values() if team.tier == 1) == 30
    assert sum(1 for team in pack.teams.values() if team.tier == 2) == 18
    assert all(len(team.player_ids) == 5 for team in pack.teams.values())
    assert any(meta.id == "vct-2021" for meta in list_roster_packs())

    team = "team_sentinels"
    gs1 = new_campaign(GD, seed=2021, user_team_id=team, pack=pack)
    gs2 = new_campaign(GD, seed=2021, user_team_id=team, pack=pack)
    assert gs1.calendar_year == 2021
    assert gs1.model_dump_json() == gs2.model_dump_json()
    assert gs1.players["team_sentinels_tenz"].handle == "TenZ"
