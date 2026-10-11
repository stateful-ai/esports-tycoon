const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const start = app.indexOf('  const tierSeg = el("div", "seg");', app.indexOf('async function stats(v)'));
const end = app.indexOf('  right.push(tierSeg);', start);
assert(start >= 0 && end > start);
const requests = [];
let renders = 0;
const context = {
  window: {addEventListener() {}}, document: {hidden: false, addEventListener() {}},
  crypto: require('node:crypto').webcrypto, performance: {now: () => 0},
  setInterval() {}, setTimeout, clearTimeout, AbortController,
  fetch: async (_, options) => { requests.push(...JSON.parse(options.body).events); return {ok: true}; },
  App: {statsTab: 'meta', statsSplit: {kind: 'map', key: 'PRIVATE_MAP'}},
  renderApp() { renders++; },
  el(tag, cls, label) { return {tag, cls, label, children: [], appendChild(b) {this.children.push(b);}}; },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/usage.js', 'utf8'), context);
function render() {
  return vm.runInContext(`(() => {const lgTier = App.statsTier ?? 1; ${app.slice(start, end)} return tierSeg.children;})()`, context);
}
async function take() {
  await context.window.Usage.boundary();
  return JSON.parse(JSON.stringify(requests.splice(0).filter(e => e.kind === 'interaction')));
}
(async () => {
  let buttons = render();
  assert.deepEqual(await take(), []); // Default and rendering do not imply selection.
  buttons[0].onclick();
  assert.equal(renders, 0);
  assert.deepEqual(await take(), []); // Undefined tier is already Top flight.
  buttons[1].onclick();
  buttons[1].onclick(); // Even before rerender, the current state prevents duplicates.
  assert.equal(context.App.statsTier, 2);
  assert.equal(renders, 1);
  assert.deepEqual(await take(), [{kind: 'interaction', target: 'stats/competition_challengers'}]);
  buttons = render(); buttons[1].onclick();
  assert.deepEqual(await take(), []);
  buttons[0].onclick();
  assert.equal(context.App.statsTier, 1);
  assert.equal(renders, 2);
  assert.deepEqual(await take(), [{kind: 'interaction', target: 'stats/competition_top_flight'}]);
  assert.equal(context.App.statsTab, 'meta');
  assert.equal(context.App.statsSplit.key, 'PRIVATE_MAP');
  render(); render(); assert.deepEqual(await take(), []);
  for (const target of ['stats/competition_3', 'stats/competition_challengers/PRIVATE_TEAM', 'stats/tier']) {
    context.window.Usage.interaction(target);
  }
  assert.deepEqual(await take(), []); // Client fixed vocabulary rejects dynamic/private targets.
  context.window.Usage = undefined;
  render()[1].onclick();
  assert.equal(context.App.statsTier, 2);
  assert.equal(renders, 3); // Optional telemetry cannot block selection.
  console.log('Stats competition callback and queue semantics passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
