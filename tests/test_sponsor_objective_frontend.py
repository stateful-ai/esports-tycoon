"""Sponsor goals retain separate contracts and escape their display identity."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.web


def test_needs_you_sponsor_identity_escaping_and_legacy_fallback():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for frontend verification")
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    helpers = source[source.index("const DISPLAY_TOKENS"):source.index("const tooltipMarkup")]
    slots = re.search(r"const SLOT_LABELS = \{.*?\n\};", source, re.S).group()
    needs = re.search(r"function computeNeedsYou\(data\) \{.*?\n\}", source, re.S).group()
    script = helpers + slots + needs + """
const goal = {kind:'sponsor', label:'make the regional playoffs', state:'at_risk', detail:'currently 6th of 8'};
const input = {objectives_hub: [
  {...goal, sponsor_name:'Hypercarry Energy', sponsor_slot:'jersey'},
  {...goal, sponsor_name:'GlitchTV', sponsor_slot:'stream'},
  {...goal, sponsor_name:'Hypercarry Energy', sponsor_slot:'stream'},
  {...goal, sponsor_name:'<img src=x onerror="bad"> & Brand', sponsor_slot:'<script>', label:'<goal>', detail:'<detail>'},
  goal,
  {...goal, sponsor_name:'Done', sponsor_slot:'title', state:'achieved'}
]};
const before = JSON.stringify(input);
const rows = computeNeedsYou(input);
console.log(JSON.stringify({rows, pure:JSON.stringify(input) === before}));
"""
    actual = json.loads(subprocess.check_output([node, "-e", script], text=True, encoding="utf-8"))
    rows = actual["rows"]
    assert actual["pure"]
    assert len(rows) == 5
    assert [r["label"] for r in rows[:3]] == [
        "Hypercarry Energy — make the regional playoffs",
        "GlitchTV — make the regional playoffs",
        "Hypercarry Energy — make the regional playoffs",
    ]
    assert rows[0]["detail"] == "Sponsor · Jersey · At Risk · currently 6th of 8"
    assert rows[1]["detail"] == rows[2]["detail"] == "Sponsor · Stream · At Risk · currently 6th of 8"
    assert rows[3]["label"] == '&lt;img src=x onerror=&quot;bad&quot;&gt; &amp; Brand — &lt;goal&gt;'
    assert rows[3]["detail"] == "Sponsor · &lt;script&gt; · At Risk · &lt;detail&gt;"
    assert rows[4]["label"] == "make the regional playoffs"
    assert rows[4]["detail"] == "Sponsor · At Risk · currently 6th of 8"
    assert all(r["needs_action"] is False for r in rows)
