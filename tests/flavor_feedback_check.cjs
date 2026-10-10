const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const start = source.indexOf('    const eventBlock = (ev, kicker, endpoint, fallbackDone) => {');
const end = source.indexOf('    if (media) {', start);
assert.ok(start > 0 && end > start);
const actualHandler = source.slice(start, end);
class Element {
  constructor(tag) { this.tag = tag; this.children = []; }
  appendChild(child) { this.children.push(child); }
  querySelectorAll(tag) { return this.children.flatMap(child => [...(child.tag === tag ? [child] : []), ...child.querySelectorAll(tag)]); }
}
async function scenario(switchWorld, switchTeam, reject) {
  let finish;
  const pending = new Promise((resolve, rejectPromise) => { finish = reject ? rejectPromise : resolve; });
  const context = {App: {mp: {code: 'OLD'}, state: {user_team: {id: 'team_nexus'}}},
    s: {user_team: {id: 'team_nexus'}}, card: new Element('card'), el: tag => new Element(tag),
    api: (endpoint, body) => { assert.equal(endpoint, '/api/actions/flavor_event'); assert.equal(body.choice_id, 'small_group'); return pending; },
    messages: [], refreshes: 0, toast: message => context.messages.push(message), refresh: () => context.refreshes++};
  vm.createContext(context);
  vm.runInContext(actualHandler + '\neventBlock({id:"clinic", choices:[{id:"small_group",label:"Send a small group"}]}, "Team moment", "/api/actions/flavor_event", "Done");', context);
  const button = context.card.querySelectorAll('button')[0];
  const request = button.onclick();
  assert.equal(button.disabled, true);
  if (switchWorld) context.App.mp = {code: 'NEW'}; // Same team, distinct career.
  if (switchTeam) context.App.state = {user_team: {id: 'team_other'}};
  finish(reject ? new Error('rejected') : {ok: true, message: 'Settled', realized_effects: []});
  await request;
  if (switchWorld || switchTeam || reject) {
    assert.equal(context.App.flavorSettlement, undefined);
    assert.equal(context.messages.length, 0);
    assert.equal(context.refreshes, 0);
    if (reject) assert.equal(button.disabled, false);
  } else {
    assert.equal(context.App.flavorSettlement.message, 'Settled');
    assert.equal(context.App.flavorSettlementWorld, 'OLD');
    assert.equal(context.App.flavorSettlementTeam, 'team_nexus');
    assert.equal(context.messages.length, 1);
    assert.equal(context.refreshes, 1);
  }
}
(async () => {
  await scenario(false, false, false);
  await scenario(true, false, false);
  await scenario(false, true, false);
  await scenario(false, false, true);
  console.log('Actual flavor handler: same-world receipt, in-flight world/team switches, rejected request passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
