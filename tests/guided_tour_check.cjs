const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map(), listeners = new Map(), saved = new Map(), timers = new Map();
let document, blocked = false, timerId = 0;
function element() {
  const classes = new Set();
  const node = {
    hidden: false, style: {}, isConnected: true, children: [], events: {}, attrs: {},
    classList: {add: x => classes.add(x), remove: x => classes.delete(x)},
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(k, fn) { this.events[k] = fn; },
    focus() { document.activeElement = this; },
    closest() { return this.hiddenParent || null; },
    querySelector(s) { return this.children.find(c => s.includes(`"${c.action}"`)) || null; },
    querySelectorAll() { return this.children; },
  };
  Object.defineProperty(node, 'innerHTML', {set(html) {
    this.children = [...html.matchAll(/data-tour="(\w+)"/g)].map(m => {
      const child = element(); child.action = m[1]; return child;
    });
  }});
  return node;
}
const opener = element(), handbook = element();
nodes.set('help-open', handbook);
document = {
  activeElement: opener,
  body: {append(...els) { els.forEach(e => nodes.set(e.id, e)); }},
  createElement: element,
  getElementById: id => nodes.get(id),
  querySelector: () => blocked ? element() : null,
  addEventListener: (k, fn) => listeners.set(k, fn),
  removeEventListener: k => listeners.delete(k),
};
const window = {addEventListener() {}, removeEventListener() {}};
const context = vm.createContext({
  window, document, innerWidth: 1024, innerHeight: 768,
  localStorage: {setItem: (k, v) => saved.set(k, v)},
  setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
  clearTimeout: id => timers.delete(id),
});
// Match production order: the classic tour script precedes app.js's module.
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/tour.js', 'utf8'), context);
window.startTour(); assert.equal(window._tour.active, false);
window.App = {mp: {code: 'WORLD_A'}};
window.esc = String;
window.dashGoTab = () => {};
window.closeHelp = () => {};
function key(k, shiftKey = false) {
  listeners.get('keydown')({key: k, shiftKey, preventDefault() {}, stopImmediatePropagation() {}});
}
function closed() {
  assert.equal(window._tour.active, false);
  for (const id of ['tour-backdrop', 'tour-spot', 'tour-card']) assert.equal(nodes.get(id).hidden, true);
  assert.equal(listeners.has('keydown'), false);
  assert.equal(timers.size, 0);
}
blocked = true; window.startTour(); assert.equal(window._tour.active, false); blocked = false;
window.startTour();
const card = nodes.get('tour-card');
assert.equal(document.activeElement.action, 'next');
key('Tab'); assert.equal(document.activeElement.action, 'skip');
key('Tab', true); assert.equal(document.activeElement.action, 'next');
// A browser click event must not be mistaken for successful completion.
card.querySelector('[data-tour="skip"]').onclick({type: 'click'});
closed(); assert.equal(saved.size, 0); assert.equal(document.activeElement, opener);
window.startTour(); nodes.get('tour-backdrop').events.click({type: 'click'});
closed(); assert.equal(saved.size, 0);
window.startTour(); const pending = [...timers.values()][0]; key('Escape'); pending();
closed(); assert.equal(saved.size, 0);
// Per-world persistence uses the current App, rather than a pre-module fallback.
window.App = {mp: {code: 'WORLD_B'}};
window.startTour();
for (let i = 0; i < window._tour.STEPS.length; i++) key('ArrowRight');
closed(); assert.equal(saved.get('esports-sim:guided-tour:WORLD_B'), '1');
assert.equal(saved.has('esports-sim:guided-tour:local'), false);
// A launch button in a handbook that closes falls back to a visible opener.
opener.hiddenParent = element(); document.activeElement = opener;
window.startTour(); window.endTour(false); closed();
assert.equal(document.activeElement, handbook);
