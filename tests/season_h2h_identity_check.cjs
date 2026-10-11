const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const matrix = source.slice(source.indexOf('  // Head-to-head matrix:'), source.indexOf('  // Results archive:'));
const esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
function render(data, teams) {
  const rail = {children: [], appendChild(child) {this.children.push(child);}};
  const el = (tag, cls = '', html = '') => ({tag, cls, innerHTML: html, children: [],
    appendChild(child) {this.children.push(child);}});
  const league = {h2h_matrix: {teams, rows: teams.map((tm, i) => ({team_id: tm.team_id,
    cells: teams.map((_, j) => i === j ? null : i === 0
      ? {played: true, w: 2, l: 1} : {played: false, w: 0, l: 0})}))}};
  vm.runInNewContext(matrix, {data, league, rail, el, esc});
  const table = rail.children[0].children[1].children[0].children[0];
  return {head: table.innerHTML, rows: table.children[0].children.map(row => row.innerHTML)};
}
const teams = [{team_id: 'nexus', name: 'Team Nexus'}, {team_id: 'vanguard', name: 'Team Vanguard'}];
// Standings may be in a different order and include either tier.
const data = {regions: [{rows: [{id: 'vanguard', tag: 'VGD'}], tier2_rows: [{id: 'nexus', tag: 'NXS'}]}]};
const actual = render(data, teams);
assert.match(actual.head, /aria-label="Team Nexus">NXS<\/th>.*aria-label="Team Vanguard">VGD<\/th>/);
assert.match(actual.head, /scope="col" title="Team Nexus"/);
assert.match(actual.rows[0], /scope="row" title="Team Nexus" aria-label="Team Nexus"/);
assert.match(actual.rows[0], /class="tlink" data-tid="nexus" title="Team Nexus" aria-label="Team Nexus">NXS<\/span>/);
assert.match(actual.rows[1], /data-tid="vanguard" title="Team Vanguard" aria-label="Team Vanguard">VGD<\/span>/);
assert.match(actual.rows[0], /<td class="es-h2hm-self">—<\/td><td class="good">2-1<\/td>$/);
assert.match(actual.rows[1], /<td class="muted">·<\/td><td class="es-h2hm-self">—<\/td>$/);
const legacy = render(null, teams);
assert.match(legacy.head, />Team Nexus<\/th>.*>Team Vanguard<\/th>/);
assert.match(legacy.rows[0], />Team Nexus<\/span>/);
const quoted = render({regions: [{rows: [{id: 'a"&', tag: '<A&>'}]}]}, [
  {team_id: 'a"&', name: 'A "&<club>'}, {team_id: 'b', name: 'B', tag: 'PUBLIC'},
]);
assert.match(quoted.head, /title="A &quot;&amp;&lt;club&gt;" aria-label="A &quot;&amp;&lt;club&gt;">&lt;A&amp;&gt;<\/th>/);
assert.match(quoted.rows[0], /data-tid="a&quot;&amp;"/);
assert.match(quoted.head, />PUBLIC<\/th>/);
assert.doesNotMatch(actual.head + actual.rows.join(''), />TEA</);
