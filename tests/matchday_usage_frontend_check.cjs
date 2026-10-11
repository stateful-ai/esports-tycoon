const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const requests = [];
function el(tag, classes = '', html = '') {
  const tokens = new Set(classes.split(' '));
  const children = [];
  return {tag, children, html, onclick: null,
    classList: {contains: x => tokens.has(x), add: x => tokens.add(x), remove: x => tokens.delete(x)},
    set innerHTML(value) { children.length = 0; this.html = value; },
    appendChild(child) { children.push(child); return child; },
    append(...items) { children.push(...items); },
    get childElementCount() { return children.length; }};
}
let overlay = el('div', 'hidden');
const fixture = {fixture: {stage: 'regular', week: 3, best_of: 3,
  map_pool: {team_name: 'Private You', maps: [], fixture: {
    opponent: 'PRIVATE_THEM', veto_locked: true, veto: ['PRIVATE_VETO'],
    maps: [{map: 'PRIVATE_MAP', ours: {played: 2, wins: 1, win_rate: 50},
      theirs: {played: 0, wins: 0, win_rate: null}}]}}},
  you: {id: 'PRIVATE_YOU', name: 'Private You'}, them: {id: 'PRIVATE_THEM', name: 'Private Them'}};
const context = {window: {addEventListener() {}}, document: {hidden: false, addEventListener() {}},
  crypto: require('node:crypto').webcrypto, performance: {now: () => 0},
  setInterval() {}, setTimeout, clearTimeout, AbortController,
  fetch: async (_, options) => {requests.push(...JSON.parse(options.body).events); return {ok: true};},
  $: () => overlay, el, api: async () => fixture, App: {state: {season: 1}},
  esc: x => x, stageLabel: x => x, humanize: x => x, formSquare: () => el('span'),
  tlink: (id, name) => name, plink: (id, name) => name, dashGoTab: name => {context.destination = name;}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/usage.js', 'utf8'), context);
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
// Load the production shared renderer too: openMatchday calls it even when
// there is no map pool. A stub would conceal missing fixture-map rendering.
const fixtureMapStart = source.indexOf('function fixtureMapRead(board, mp) {');
const fixtureMapEnd = source.indexOf('\nfunction toast(', fixtureMapStart);
assert(fixtureMapStart >= 0 && fixtureMapEnd > fixtureMapStart);
vm.runInContext(source.slice(fixtureMapStart, fixtureMapEnd), context);
vm.runInContext(source.slice(source.indexOf('let matchdayUsageOpen = false;'),
  source.indexOf('// Legacy career: the job-market takeover panel')), context);
async function take() {
  await context.window.Usage.boundary();
  const events = requests.splice(0).filter(e => e.kind === 'interaction');
  assert(events.every(e => Object.keys(e).sort().join(',') === 'kind,target'));
  assert(!JSON.stringify(events).includes('PRIVATE'));
  return events.map(e => e.target);
}
function button(text) {
  const find = node => node.tag === 'button' && node.html.startsWith(text) ? node : node.children.map(find).find(Boolean);
  return find(overlay);
}
function renderedText(node = overlay) {
  return [node.html, ...node.children.map(renderedText)].join('\n');
}
(async () => {
  context.closeMatchday(); assert.deepEqual(await take(), []);
  await context.openMatchday();
  assert.equal(overlay.classList.contains('hidden'), false);
  assert(renderedText().includes('Series maps — veto locked'));
  assert(renderedText().includes('PRIVATE_VETO'));
  assert(renderedText().includes('PRIVATE_MAP — you 50% (1/2) · PRIVATE_THEM no season maps played'));
  assert.deepEqual(await take(), ['matchday/briefing_open']);
  await context.openMatchday(); assert.deepEqual(await take(), []); // visible refresh
  overlay.onclick({target: {}}); assert.deepEqual(await take(), []); // content click
  button('Continue').onclick(); context.closeMatchday();
  assert.deepEqual(await take(), ['matchday/briefing_close']);
  assert.equal(overlay.classList.contains('hidden'), true);
  assert.equal(overlay.childElementCount, 0);
  await context.openMatchday(); overlay.onclick({target: overlay});
  assert.deepEqual(await take(), ['matchday/briefing_open', 'matchday/briefing_close']);
  await context.openMatchday(); button('Set game plan').onclick();
  assert.equal(context.App.tacticsTab, 'gameplan');
  assert.equal(context.destination, 'tactics');
  assert.deepEqual(await take(), ['matchday/briefing_open', 'matchday/briefing_close']);
  context.api = async () => ({...fixture, plan_set: true});
  await context.openMatchday(); button('Review game plan').onclick();
  assert.deepEqual(await take(), ['matchday/briefing_open', 'matchday/briefing_close']);
  context.api = async () => ({...fixture, fixture: {...fixture.fixture,
    map_pool: {maps: [], fixture: {opponent: 'PRIVATE_THEM', veto_locked: false, veto: [], maps: []}}}});
  await context.openMatchday();
  assert(renderedText().includes('Scheduled maps'));
  button('Continue').onclick();
  assert.deepEqual(await take(), ['matchday/briefing_open', 'matchday/briefing_close']);
  context.api = async () => ({...fixture, fixture: {...fixture.fixture, map_pool: null}});
  await context.openMatchday();
  assert(renderedText().includes('No map record yet this season.'));
  button('Continue').onclick();
  assert.deepEqual(await take(), ['matchday/briefing_open', 'matchday/briefing_close']);
  context.api = async () => ({fixture: null});
  await context.openMatchday(); button('Close').onclick();
  assert.deepEqual(await take(), ['matchday/briefing_open', 'matchday/briefing_close']);
  context.api = async () => {throw Error('PRIVATE_FAILURE');};
  await context.openMatchday(); context.closeMatchday(); assert.deepEqual(await take(), []);
  overlay = null; context.api = async () => fixture;
  await context.openMatchday(); context.closeMatchday(); assert.deepEqual(await take(), []);
  overlay = el('div', 'hidden');
  context.api = async () => ({fixture: fixture.fixture}); // render failure is not an inspection
  await assert.rejects(context.openMatchday()); context.closeMatchday();
  assert.deepEqual(await take(), []);
  context.window.Usage.interaction('matchday/briefing_open/PRIVATE');
  context.window.Usage.interaction('matchday/unknown'); assert.deepEqual(await take(), []);
  // Instrumentation stays optional when usage.js is absent.
  delete context.window.Usage; context.api = async () => fixture;
  await context.openMatchday(); button('Continue').onclick();
  assert.equal(overlay.classList.contains('hidden'), true);
})().catch(error => {console.error(error); process.exitCode = 1;});
