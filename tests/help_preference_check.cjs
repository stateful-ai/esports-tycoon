const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const storage = new Map();
function node() {
  const classes = new Set(['hidden']);
  return {dataset: {}, checked: false, events: {},
    classList: {contains: x => classes.has(x), add: x => classes.add(x), remove: x => classes.delete(x), toggle() {}},
    setAttribute() {}, querySelector() { return null; },
    addEventListener(k, fn) { this.events[k] = fn; }};
}
const help = node(), skip = node(), wrap = node(), body = node();
const nodes = {'help': help, 'help-body': body, 'help-skip': skip, 'help-skip-wrap': wrap};
const context = vm.createContext({
  App: {tab: 'dashboard', mp: {code: 'WORLD_A'}}, window: {},
  document: {getElementById: id => nodes[id], addEventListener() {}, querySelectorAll: () => []},
  localStorage: {getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k)},
  helpFirstWeekMarkup: () => '', helpScreensMarkup: () => '', helpGlossaryMarkup: () => '',
});
const app = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
vm.runInContext(app.slice(app.indexOf('function helpSeenKey()'), app.indexOf('function helpFirstWeekMarkup()')), context);
vm.runInContext(app.slice(app.indexOf('let helpUsageSection = null;'), app.indexOf('window.openHelp')), context);
context.initHelpSystem();
const key = world => `esports-sim:first-week-guide:${world}`;
// Declining the preference must allow auto-open again after a fresh load.
context.openHelp('first-week', 'dashboard', true);
assert.equal(skip.checked, false); context.closeHelp();
assert.equal(storage.has(key('WORLD_A')), false);
context.App.onboardingShown = false;
context.maybeShowFirstWeekHelp({season: 1, week: 1});
assert.equal(help.classList.contains('hidden'), false);
// Check, then uncheck, then dismiss: closing must not overwrite that choice.
skip.checked = true; skip.events.change({target: skip});
assert.equal(storage.get(key('WORLD_A')), '1');
skip.checked = false; skip.events.change({target: skip}); context.closeHelp();
assert.equal(storage.has(key('WORLD_A')), false);
// Checking survives closing and suppresses the next automatic opening.
context.openHelp('first-week', 'dashboard', true);
skip.checked = true; skip.events.change({target: skip}); context.closeHelp();
context.App.onboardingShown = false;
context.maybeShowFirstWeekHelp({season: 1, week: 1});
assert.equal(help.classList.contains('hidden'), true);
// Reusing the same checkbox in a different world reads that world's key.
context.App.mp.code = 'WORLD_B'; context.openHelp('first-week', 'dashboard', true);
assert.equal(skip.checked, false); context.closeHelp();
assert.equal(storage.get(key('WORLD_A')), '1');
assert.equal(storage.has(key('WORLD_B')), false);
context.App.mp.code = 'WORLD_A'; context.openHelp('first-week', 'dashboard');
assert.equal(skip.checked, true); assert.equal(wrap.hidden, true);
context.closeHelp(); assert.equal(storage.get(key('WORLD_A')), '1');
