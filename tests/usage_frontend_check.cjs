const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let now = 0, world = null, failing = false;
const requests = [], listeners = {}, windowListeners = {};
const document = {hidden: false, addEventListener: (name, fn) => { listeners[name] = fn; }};
const context = {crypto: require('node:crypto').webcrypto, performance: {now: () => now}, document,
  window: {addEventListener: (name, fn) => { windowListeners[name] = fn; }},
  setInterval: () => {}, setTimeout, clearTimeout, AbortController,
  fetch: async (path, options) => {
    assert.equal(path, '/api/usage/events');
    if (failing) throw new Error('offline');
    requests.push({world, ...JSON.parse(options.body)});
    return {ok: true};
  }};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/usage.js', 'utf8'), context);
(async () => {
  const usage = context.window.Usage;
  now = 1000; usage.view('club/squad');
  now = 2000; document.hidden = true; listeners.visibilitychange();
  await usage.flush();
  now = 100000; document.hidden = false; listeners.visibilitychange();
  now = 101000; usage.view('club/development');
  const token = usage.request('/api/join?code=SECRET', true);
  await usage.boundary();
  world = 'NEW';
  usage.result(token, 'success', 200);
  await usage.flush();
  const before = requests.filter(r => r.world === null).flatMap(r => r.events);
  assert.equal(before.filter(e => e.kind === 'visible_time').reduce((n,e) => n+e.duration_ms, 0), 3000);
  assert(before.some(e => e.kind === 'attempt' && e.target === '/api/join'));
  assert(requests.filter(r => r.world === 'NEW').flatMap(r => r.events).some(e => e.kind === 'result' && e.request_id === token.id));
  assert(!JSON.stringify(requests).includes('SECRET'));
  const a = usage.request('/api/actions/train', true), b = usage.request('/api/actions/train', true);
  usage.result(b, 'http_error', 409); usage.result(a, 'transport_error');
  await usage.flush();
  assert.notEqual(a.id, b.id);
  failing = true;
  usage.replay('play'); await usage.flush();
  usage.view('season/league'); await usage.boundary();
  console.log('frontend usage contract passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
