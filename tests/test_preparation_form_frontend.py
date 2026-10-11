"""Exercise booking retention and fixture/option boundaries in the real helper."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.web


def test_preparation_form_retains_only_valid_current_fixture_booking():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for frontend verification")
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    helper = re.search(r"function hydratePreparationForm\(pr, controls\) \{.*?\n\}", source, re.S).group()
    script = helper + """
const choices = {partner_id: ['first', 'chosen'], map_id: ['bind', 'haven'],
  objective: ['anti_exec', 'mental_reset'], intensity: ['normal', 'intense']};
const plan = {fixture_id: 'current', partner_id: 'chosen', map_id: 'haven',
  objective: 'mental_reset', intensity: 'intense'};
function render(current, fixture = {id: 'current'}) {
  const controls = Object.fromEntries(Object.entries(choices).map(([key, values]) =>
    [key, {value: values[0], options: values.map(value => ({value}))}]));
  hydratePreparationForm({current, fixture}, controls);
  return Object.fromEntries(Object.entries(controls).map(([key, control]) => [key, control.value]));
}
console.log(JSON.stringify([render(plan), render(plan), render(null),
  render({...plan, fixture_id: 'old'}), render({...plan, partner_id: 'removed'}),
  render({...plan, map_id: 'removed'}), render({...plan, objective: 'removed'}),
  render({...plan, intensity: 'removed'}), render(plan, null)]));
"""
    actual = json.loads(subprocess.check_output([node, "-e", script], text=True))
    booked = dict(partner_id="chosen", map_id="haven", objective="mental_reset", intensity="intense")
    defaults = dict(partner_id="first", map_id="bind", objective="anti_exec", intensity="normal")
    assert actual[:2] == [booked, booked]
    assert actual[2:] == [defaults] * 7
    assert "hydratePreparationForm(pr, { partner_id: partner, map_id: map, objective: obj, intensity });" in source
