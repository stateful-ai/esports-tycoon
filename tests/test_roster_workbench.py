"""Portable roster documents, atomic compilation, and Roster Studio API."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from esports_sim.manager.campaign import new_campaign
from esports_sim.registry.loader import load_all
from esports_sim.registry.roster_workbench import (
    dump_document,
    example_document,
    install_document,
    library_revision,
    load_document,
    parse_document,
    validate_document,
)
from esports_sim.registry.rosters import load_roster_pack


def test_example_document_is_valid_and_yaml_round_trips():
    raw = example_document()
    result = validate_document(raw)
    assert result["valid"] is True
    assert result["summary"] == {
        "id": "my-roster-pack",
        "regions": ["americas", "emea", "pacific"],
        "teams": 1,
        "tier1_teams": 1,
        "tier2_teams": 0,
        "players": 5,
        "free_agents": 0,
    }
    assert parse_document(dump_document(raw))["teams"][0]["tag"] == "MFT"


def test_validation_reports_structural_and_game_catalog_errors():
    wrong_shape = example_document()
    wrong_shape["teams"][0]["players"].pop()
    result = validate_document(wrong_shape)
    assert result["valid"] is False
    assert any("exactly 5" in error["message"] for error in result["errors"])

    bad_agent = example_document()
    bad_agent["teams"][0]["players"][0]["agents"] = ["not_an_agent"]
    result = validate_document(bad_agent)
    assert result["valid"] is False
    assert result["errors"] == [{
        "path": "teams.0.players.0.agents.0",
        "message": "unknown agent id 'not_an_agent'",
    }]


def test_install_compiles_partial_world_and_preserves_authored_meta(tmp_path: Path):
    before_revision = library_revision(tmp_path)
    raw = example_document()
    raw["name"] = "Agents United"
    raw["description"] = "A portable custom pack."
    raw["world"]["league_regions"] = ["pacific", "americas", "emea"]
    raw["teams"][0]["region"] = "pacific"
    result = install_document(raw, tmp_path)
    assert library_revision(tmp_path) != before_revision

    assert result["compiled"]["teams"] == 1
    assert result["compiled"]["players"] == 5
    pack = load_roster_pack("my-roster-pack", tmp_path)
    assert pack.meta.name == "Agents United"
    assert pack.meta.description == "A portable custom pack."
    assert pack.meta.world.teams_per_region == 8
    assert [str(region) for region in pack.meta.world.league_regions] == [
        "pacific", "americas", "emea",
    ]

    portable = load_document("my-roster-pack", tmp_path)
    assert portable.model_dump(mode="json") == raw
    assert (tmp_path / "rosters" / "my-roster-pack" / "src" / "pack.yaml").is_file()

    # The installed artifact is not merely schema-valid: it seeds a playable,
    # deterministic world through the normal new-game path.
    gd = load_all()
    gs1 = new_campaign(
        gd, seed=77, user_team_id="team_my_favorite_team", pack=pack
    )
    gs2 = new_campaign(
        gd, seed=77, user_team_id="team_my_favorite_team", pack=pack
    )
    assert gs1.model_dump_json() == gs2.model_dump_json()
    assert gs1.roster_pack == "my-roster-pack"


def test_player_tags_are_open_vocabulary_and_round_trip(tmp_path: Path):
    """Src sheets may tag players ("rookie", or invented ones like
    "pure_aimer" in vct-2021) — the builder has always consumed them, and
    personality.py no-ops unknown tags, so the editable schema must
    accept any well-formed slug and preserve it through install."""
    raw = example_document()
    raw["teams"][0]["players"][0]["tags"] = ["veteran", "pure_aimer"]
    result = validate_document(raw)
    assert result["valid"] is True, result["errors"]

    install_document(raw, tmp_path)
    portable = load_document(raw["id"], tmp_path)
    assert portable.teams[0].players[0].tags == ["veteran", "pure_aimer"]
    # The compiled bundle carries them as runtime personality_tags.
    pack = load_roster_pack(raw["id"], tmp_path)
    caller = next(
        p for p in pack.players.values() if p.handle == "caller"
    )
    assert {"veteran", "pure_aimer"} <= set(caller.personality_tags)

    # Malformed tags are still rejected: not a slug / duplicates.
    bad = example_document()
    bad["teams"][0]["players"][0]["tags"] = ["Not A Slug"]
    assert validate_document(bad)["valid"] is False
    dup = example_document()
    dup["teams"][0]["players"][0]["tags"] = ["rookie", "rookie"]
    assert validate_document(dup)["valid"] is False


def test_failed_install_does_not_touch_an_existing_pack(tmp_path: Path):
    raw = example_document()
    install_document(raw, tmp_path)
    pack_file = tmp_path / "rosters" / raw["id"] / "pack.yaml"
    before = pack_file.read_bytes()

    raw["teams"][0]["players"][0]["agents"] = ["not_an_agent"]
    with pytest.raises(ValueError, match="unknown agent"):
        install_document(raw, tmp_path)
    assert pack_file.read_bytes() == before


def test_source_metadata_is_not_mistaken_for_a_region_sheet(tmp_path: Path):
    raw = example_document()
    install_document(raw, tmp_path)
    source_meta = yaml.safe_load(
        (tmp_path / "rosters" / raw["id"] / "src" / "pack.yaml").read_text()
    )
    assert source_meta["schema_version"] == 2
    assert source_meta["world"]["tier2_per_region"] == 4


def test_roster_studio_schema_and_draft_validation_api():
    pytest.importorskip("fastapi")
    from esports_sim.web import server

    # Call the thin route functions directly. The web extra intentionally does
    # not depend on httpx/TestClient; these functions are the exact route
    # handlers FastAPI registers.
    schema = server.roster_studio_schema()
    assert schema["schema"]["title"] == "RosterPackDocument"
    assert "jett" in {agent["id"] for agent in schema["catalog"]["agents"]}

    valid = server.roster_studio_validate(example_document())
    assert valid["valid"] is True

    incomplete = server.roster_studio_validate({"id": "draft"})
    assert incomplete["valid"] is False
    assert incomplete["errors"]

    parsed = server.roster_studio_parse({
        "text": dump_document(example_document())
    })
    assert parsed["document"]["id"] == "my-roster-pack"


def test_roster_pack_admin_routes_are_loopback_only():
    pytest.importorskip("fastapi")
    from fastapi import HTTPException
    from esports_sim.web import server

    for host in ("127.0.0.1", "::1"):
        token = server._client_host_ctx.set(host)
        try:
            server._require_local_admin()
        finally:
            server._client_host_ctx.reset(token)

    for host in ("192.168.1.44", "10.0.0.8", ""):
        token = server._client_host_ctx.set(host)
        try:
            with pytest.raises(HTTPException) as exc:
                server._require_local_admin()
            assert exc.value.status_code == 403
        finally:
            server._client_host_ctx.reset(token)
