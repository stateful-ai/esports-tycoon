const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const receipts = [], posts = [];
let response;
const context = {
  window: {addEventListener() {}}, document: {hidden: false, addEventListener() {}},
  crypto: require('node:crypto').webcrypto, performance: {now: () => 12},
  setInterval() {}, setTimeout, clearTimeout, AbortController,
  toast() { throw new Error('silent reads must not toast'); },
  fetch: async (path, options) => {
    if (path === '/api/usage/events') {
      receipts.push(...JSON.parse(options.body).events);
      return {ok: true};
    }
    assert.equal(path, '/api/inbox/read');
    posts.push(JSON.parse(options.body));
    if (response instanceof Error) throw response;
    return response;
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/usage.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/inbox.js', 'utf8'), context);
async function read(body, reply, outcome, status, expected) {
  response = reply;
  const value = await context.inboxPost(body);
  assert.equal(JSON.stringify(value), JSON.stringify(expected));
  await context.window.Usage.boundary();
  const events = receipts.splice(0).filter(e => ['attempt', 'result'].includes(e.kind));
  assert.equal(events.length, 2);
  assert.equal(events[0].kind, 'attempt');
  assert.equal(events[1].kind, 'result');
  assert.equal(events[0].request_id, events[1].request_id);
  assert(events.every(e => e.target === '/api/inbox/read'));
  assert.equal(events[1].outcome, outcome);
  assert.equal(events[1].status, status);
  assert(events.every(e => Object.keys(e).every(k =>
    ['kind', 'target', 'request_id', 'outcome', 'status', 'duration_ms'].includes(k))));
  assert(!JSON.stringify(events).includes('PRIVATE'));
}
(async () => {
  const data = {unread: 1, actionable_unread: 1};
  await read({id: 'PRIVATE_ITEM'}, {ok: true, status: 200, json: async () => data}, 'success', 200, data);
  await read({all: true}, {ok: true, status: 200, json: async () => ({unread: 0})}, 'success', 200, {unread: 0});
  await read({id: 'PRIVATE_ITEM'}, {ok: false, status: 409, json: () => {throw Error('must not parse');}}, 'http_error', 409, null);
  await read({id: 'PRIVATE_ITEM'}, new Error('PRIVATE_NETWORK_DETAIL'), 'transport_error', undefined, null);
  await read({id: 'PRIVATE_ITEM'}, {ok: true, status: 200, json: async () => {throw Error('PRIVATE_JSON');}}, 'transport_error', 200, null);
  await read({id: 'PRIVATE_ITEM'}, {ok: true, status: 200, json: async () => ({ok: false})}, 'rejected', 200, {ok: false});
  assert.deepEqual(posts[0], {id: 'PRIVATE_ITEM'});
  assert.deepEqual(posts[1], {all: true});
  const token = context.window.Usage.request('/api/inbox/read?secret=PRIVATE', true);
  context.window.Usage.result(token, 'success', 200);
  const dynamic = context.window.Usage.request('/api/inbox/PRIVATE_ITEM', true);
  context.window.Usage.result(dynamic, 'success', 200);
  await context.window.Usage.boundary();
  assert.equal(token.target, '/api/inbox/read');
  assert.equal(dynamic.target, '/api/inbox');
  assert(!JSON.stringify(receipts).includes('PRIVATE'));
  response = {ok: true, status: 200, json: async () => data};
  delete context.window.Usage;
  assert.equal(JSON.stringify(await context.inboxPost({id: 'PRIVATE_ITEM'})), JSON.stringify(data));
  context.window.Usage = {request() {throw Error('hook');}, result() {throw Error('hook');}};
  assert.equal(JSON.stringify(await context.inboxPost({all: true})), JSON.stringify(data));
})().catch(error => { console.error(error); process.exitCode = 1; });
