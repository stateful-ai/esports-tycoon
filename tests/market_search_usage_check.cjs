const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const start = source.indexOf('const PlayerSearch =');
const end = source.indexOf('  const handleBuyout', start);
const callbacks = source.slice(start, end) + 'return {handleInput, handleKeyDown}; };';
let slots = [], index = 0, effect, cleanup, pending, queries = [], receipts = [];
const context = {
  useState(initial) { const i = index++; slots[i] ??= initial; return [slots[i], v => { slots[i] = v; }]; },
  useRef(initial) { const i = index++; slots[i] ??= {current: initial}; return slots[i]; },
  useEffect(fn) { effect = fn; },
  setTimeout(fn, ms) { assert.equal(ms, 250); pending = fn; return 1; },
  clearTimeout() { pending = null; },
  api: async url => { queries.push(url); return {results: []}; },
  window: {Usage: {interaction: target => receipts.push(target)}}, console,
};
vm.createContext(context);
vm.runInContext(callbacks + '\nglobalThis.component = PlayerSearch;', context);
function render() { index = 0; const handlers = context.component({}); slots[5].current = {isConnected: true}; cleanup?.(); cleanup = effect(); return handlers; }
async function fire() { const fn = pending; pending = null; fn?.(); await Promise.resolve(); }
(async () => {
  let handlers = render(); await fire(); // Initial render.
  assert.equal(receipts.length, 0); assert.equal(queries.length, 0);
  handlers.handleInput({target: {value: 'S'}}); handlers = render(); await fire();
  assert.equal(receipts.length, 0);
  handlers.handleInput({target: {value: 'Sly'}}); handlers = render();
  handlers.handleInput({target: {value: 'Slyblade'}}); handlers = render(); await fire();
  assert.equal(receipts.length, 1); assert.equal(queries.length, 1);
  assert(queries[0].endsWith('Slyblade'));
  handlers.handleInput({target: {value: 'cancelled'}}); handlers = render();
  handlers.handleInput({target: {value: '  '}}); handlers = render(); await fire();
  assert.equal(receipts.length, 1);
  handlers.handleInput({target: {value: 'secret'}}); handlers = render(); slots[5].current.isConnected = false; await fire();
  assert.equal(receipts.length, 1); // Navigation unmount cancels pending work.
  handlers.handleInput({target: {value: 'Enter query'}}); handlers = render();
  handlers.handleKeyDown({key: 'Enter'}); await fire();
  assert.equal(receipts.length, 2); assert.equal(queries.length, 2);
  handlers.handleKeyDown({key: 'Enter'}); await fire();
  assert.equal(receipts.length, 3); // Explicit repeat submission counts again.
  slots[0] = 'programmatic'; handlers = render(); await fire();
  assert.equal(receipts.length, 3); // Programmatic update is not control use.
  context.window.Usage = undefined;
  handlers.handleKeyDown({key: 'Enter'}); await fire(); // Optional sidecar never blocks search.
  assert.equal(queries.length, 5);
  assert.deepEqual(receipts, Array(3).fill('market/player_search'));
  console.log('Market search callback semantics passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
