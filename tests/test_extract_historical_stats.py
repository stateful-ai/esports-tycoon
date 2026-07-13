from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SPEC = spec_from_file_location(
    "extract_historical_stats",
    Path(__file__).resolve().parents[1] / "scripts" / "extract_historical_stats.py",
)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_extract_preserves_event_provenance_and_deduplicates_snapshots(tmp_path):
    html = """<title>VALORANT Champions 2021: Statistics</title>
    <script>RLCONF={\"wgPageName\":\"VALORANT_Champions_2021/Statistics\",\"wgCurRevisionId\":42};</script>
    <table class=\"table2__table\"><tr><th>#</th><th>Player</th><th>Team</th><th>Agents</th><th>Maps</th><th>ACS</th><th>K</th><th>D</th><th>A</th><th>KD</th><th>KDA</th><th>K/Map</th><th>D/Map</th><th>A/Map</th></tr>
    <tr><td>1</td><td><a href=\"/valorant/Derke\">Derke</a></td><td><a href=\"/valorant/Fnatic\" title=\"Fnatic\">FNATIC</a></td><td><img title=\"Raze\"><img title=\"Jett\"></td><td>9</td><td>278</td><td>200</td><td>146</td><td>34</td><td>1.37</td><td>1.60</td><td>22.2</td><td>16.2</td><td>3.8</td></tr></table>"""
    (tmp_path / "VALORANT Champions 2021_ Statistics.htm").write_text(html, encoding="utf-8")
    (tmp_path / "duplicate.htm").write_text(html, encoding="utf-8")

    result = MODULE.extract(tmp_path)

    assert len(result["events"]) == 1
    assert len(result["observations"]) == 1
    row = result["observations"][0]
    assert row["source_player_key"] == "Derke"
    assert row["team"] == "Fnatic"
    assert row["agents"] == ["Raze", "Jett"]
    assert row["acs"] == 278
    assert row["source_event_key"] == "liquipedia:VALORANT_Champions_2021/Statistics"
    assert len(result["warnings"]) == 1
    assert result["warnings"][0].endswith(": duplicate source content skipped")
