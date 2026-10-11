"""Exercise the real Dashboard card renderer with server-authored rows (UNRUN locally)."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("tier", [1, 2])
@pytest.mark.parametrize("availability", ["present", "empty", "absent"])
def test_card_keeps_own_fifth_place_and_server_label(tier, availability):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the Dashboard renderer regression")
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    block = source[source.index("  // 5c. League snapshot:"):source.index("  // 5d. News + on this day.")]
    rows = [{"id": f"peer{i}", "name": f"Peer {i}", "wins": 4-i, "losses": i, "diff": 4-i}
            for i in range(4)]
    rows += [{"id": "you", "name": "Azure Vanta", "wins": 0, "losses": 2, "diff": -17},
             {"id": "sixth", "name": "Patagonia Sur", "wins": 0, "losses": 2, "diff": -20}]
    label = f"EMEA {'Challengers' if tier == 2 else 'league'} (Tier {tier})"
    script = """
const input = INPUT;
const main = {children: [], appendChild(n) { this.children.push(n); }};
function el(tag, cls='', html='') {
  return {tag, cls, innerHTML: html, dataset: {}, children: [],
          appendChild(n) {this.children.push(n); return n;}};
}
const myId = 'you', me = {}, competition = input.available ? input.competition : null;
// Distracting T1 data must never replace the manager's server snapshot.
const table = {regions: [{is_user:true, rows:[{id:'unrelated',name:'Nova Rift'}]}]};
const s = {standings_top:[{team_id:'unrelated',name:'Nova Rift'}]};
const playedFor = () => [];
const tlink = (id, name) => `${id}:${name}`;
let destination = null;
const dashGoTab = tab => {destination = tab;};
BLOCK
function flatten(n) {return [n.innerHTML, ...n.children.flatMap(flatten)];}
const card = main.children[0];
card.children.find(n => n.tag === 'button').onclick();
process.stdout.write(JSON.stringify({html:flatten(card).join(' '), destination}));
""".replace("INPUT", json.dumps({"available": availability != "absent", "competition": {
        "label": label, "rows": rows if availability == "present" else [],
    }})).replace("BLOCK", block)
    actual = json.loads(subprocess.check_output([node, "-e", script], text=True, encoding="utf-8"))
    assert actual["destination"] == "standings"
    assert "Nova Rift" not in actual["html"]
    if availability == "present":
        assert label in actual["html"]
        assert "<td>5</td><td>you:Azure Vanta</td>" in actual["html"]
        assert '<td class="num">-17</td>' in actual["html"]
    else:
        assert (label if availability == "empty" else "Competition standings") in actual["html"]
        assert "No standings available for your competition yet." in actual["html"]
