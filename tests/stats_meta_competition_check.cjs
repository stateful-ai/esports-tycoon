// Authored, UNRUN. Exercise the actual Stats function, selection handlers and renderer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
function section(start, end) {
  const a = source.indexOf(start), b = source.indexOf(end, a);
  assert(a >= 0 && b > a);
  return source.slice(a, b);
}
class Element {
  constructor(tag, cls = '', text = '') { this.tag = tag; this.cls = cls; this.text = text; this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
}
const requests = [], heads = [], dispatch = [];
const context = {
  App: {statsTab: 'meta', state: {season: 1}}, STATS_TABS: [],
  el: (...args) => new Element(...args),
  screenHead: (name, opts) => { heads.push(opts); return new Element('head'); },
  renderApp() {},
  api: async url => {
    requests.push(url);
    if (url.startsWith('/api/stats')) return {analytics: {tier: 2}, league_tier: Number(new URL(url, 'http://local').searchParams.get('league_tier')), teams: []};
    return {tier_list: [], map_trends: [], sample: {completed_team_maps: 0, recorded_team_maps: 0, legacy_team_maps: 0}};
  },
  statsMeta: (...args) => dispatch.push(args), statsLeaders() {}, statsRaces() {}, statsHistory() {},
};
vm.createContext(context);
vm.runInContext(section('async function stats(v)', '/* Stats · Leaders:'), context);
const view = () => new Element('view');
(async () => {
  await context.stats(view());
  assert.deepEqual(requests, ['/api/stats?league_tier=1', '/api/meta?league_tier=1']);
  const challenger = heads.at(-1).right[0].children.find(b => b.text === 'Challengers');
  challenger.onclick();
  assert.equal(context.App.statsTier, 2);
  assert.equal(context.App.statsTab, 'meta');
  requests.length = 0;
  await context.stats(view());
  assert.deepEqual(requests, ['/api/stats?league_tier=2', '/api/meta?league_tier=2']);
  heads.at(-1).right[0].children.find(b => b.text === 'Top flight').onclick();
  context.App.statsSplit = {kind: 'map', key: 'map space/&'};
  requests.length = 0;
  await context.stats(view());
  assert.deepEqual(requests, ['/api/stats?league_tier=1&split=map&key=map%20space%2F%26', '/api/meta?league_tier=1']);
  assert.equal(context.App.statsTab, 'meta');
  assert.equal(context.App.statsSplit.key, 'map space/&');
  context.App.statsTab = 'leaders';
  requests.length = 0;
  await context.stats(view());
  assert(!requests.some(url => url.startsWith('/api/meta')));

  // Render real Meta UI with public server values. No tactics formula in JS.
  Object.assign(context, {esc: String, humanize: String, mapThumb: () => '', tlink: (_, name) => name});
  vm.runInContext(section('function statsMeta(ws, data, metaResp, tier)', '/* Stats · History:'), context);
  const root = view();
  context.statsMeta(root, {league_tier: 2, teams: [], patches: []}, {
    latest_patch: {version: '1.03', season: 1, week: 3, lines: ['patch applies globally']},
    tier_list: [], sample: {completed_team_maps: 4, recorded_team_maps: 2, legacy_team_maps: 2},
    map_trends: [{map_id: 'lotus', team_maps: 4, recorded_team_maps: 2, agents: [], tactics: [{key: 'aggression', average: 75}], site_focus: null}],
  }, 2);
  const flatten = node => [node.text || '', node.innerHTML || '', ...node.children.flatMap(flatten)];
  const text = flatten(root).join(' ');
  assert(text.includes('Agent meta — Challengers'));
  assert(text.includes('Map trends — Challengers'));
  assert(text.includes('Team tendencies — Challengers'));
  assert(text.includes('Global patch 1.03'));
  assert(text.includes('4 completed team maps'));
  assert(text.includes('2 older team maps'));
  assert(text.includes('Recorded sample: 2 team maps'));
  assert(text.includes('75'));
  assert(!text.includes('Most focused site: null'));
})().catch(error => { console.error(error); process.exitCode = 1; });
