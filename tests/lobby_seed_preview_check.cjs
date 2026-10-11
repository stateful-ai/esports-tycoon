const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Node {
  constructor() {
    this.children = []; this.value = ''; this._html = '';
    const classes = new Set();
    this.classList = {
      add: x => classes.add(x), remove: x => classes.delete(x),
      contains: x => classes.has(x),
      toggle(x, on) { if (on) classes.add(x); else classes.delete(x); },
    };
  }
  set innerHTML(value) { this._html = value; this.children = []; }
  get innerHTML() { return this._html; }
  appendChild(node) { this.children.push(node); }
  append(...nodes) { this.children.push(...nodes); }
  querySelector(selector) { return (this.parts ||= {})[selector] ||= new Node(); }
}

const app = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const code = app.slice(app.indexOf('let lobbyGeneration ='), app.indexOf('async function joinGame('));
const tick = async () => { await Promise.resolve(); await Promise.resolve(); };
function harness() {
  const nodes = {}, pending = [], creations = [], interviews = [], interactions = [], timers = new Map();
  let timerId = 0;
  const $ = selector => nodes[selector] ||= new Node();
  const context = {
    $, window: {Usage: {view() {}, interaction: (...args) => interactions.push(args)}},
    App: {}, Math: {random: () => 6162 / 999999, floor: Math.floor},
    Number, clearTimeout: id => timers.delete(id),
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    el: () => new Node(), refresh: async () => {}, toast: () => {},
    renderTeamGrid(grid, teams, pick) { grid.innerHTML = ''; grid.teams = teams; grid.pick = pick; },
    renderOfferGrid(grid, offers, pick) { grid.innerHTML = ''; grid.offers = offers; grid.pick = pick; },
    runDraftInterview(grid, opts, accept) { interviews.push({grid, opts, accept}); },
    api(path, body) {
      if (path === '/api/new') {
        creations.push(body); return Promise.resolve({code: 'TEST', team_id: body.team_id});
      }
      return new Promise((resolve, reject) => pending.push({path, resolve, reject}));
    },
  };
  vm.createContext(context); vm.runInContext(code, context);
  const lob = {teams: [], scenarios: [{id: 'youth', name: 'Youth', blurb: 'Youth'}], packs: [
    {id: 'pack', name: 'Pack', regions: ['Pacific'], teams_per_region: 1, teams: [{id: 'pack-team'}]},
  ]};
  context.setupLobby(lob);
  return {context, $, pending, creations, interviews, interactions, timers, lob,
    input(value) { $('#ng-seed').value = value; $('#ng-seed').oninput(); },
    flush() { for (const [id, fn] of [...timers]) { timers.delete(id); fn(); } },
  };
}

(async () => {
  // Input-driven preview refresh must carry coarse usage without waiting for change.
  // Burst edits collapse at the existing preview debounce; no raw value is emitted.
  const usage = harness();
  assert.equal(usage.interactions.length, 0);
  usage.$('#ng-modes').children[1].onclick();
  usage.$('#ng-worlds').children[1].onclick();
  assert.equal(usage.interactions.length, 0);
  usage.input('2'); usage.input('20'); usage.input('2040');
  assert.equal(usage.interactions.length, 0);
  usage.flush();
  assert.deepEqual(usage.interactions, [['lobby/seed_change']]);
  usage.$('#ng-seed').onchange(); usage.$('#ng-seed').onblur(); usage.flush();
  assert.equal(usage.interactions.length, 1);
  usage.input('2040'); usage.flush();
  assert.equal(usage.interactions.length, 1);
  usage.input('temporary'); usage.input('2040'); usage.flush();
  assert.equal(usage.interactions.length, 1);
  for (const value of ['0', '', '2040']) {
    usage.input(value); usage.flush();
  }
  assert.deepEqual(usage.interactions, Array.from({length: 4}, () => ['lobby/seed_change']));

  const blur = harness(); blur.input('2040'); blur.$('#ng-seed').onblur();
  assert.deepEqual(blur.interactions, [['lobby/seed_change']]);
  blur.$('#ng-seed').onchange(); blur.flush();
  assert.equal(blur.interactions.length, 1);
  const changeUsage = harness(); changeUsage.$('#ng-seed').value = '2040';
  changeUsage.$('#ng-seed').onchange(); changeUsage.$('#ng-seed').onblur();
  assert.deepEqual(changeUsage.interactions, [['lobby/seed_change']]);

  // Mode switches settle pending input once; switching modes alone is not an edit.
  const interrupted = harness(); interrupted.input('2040');
  interrupted.$('#mode-join').onclick(); interrupted.flush();
  assert.deepEqual(interrupted.interactions, [['lobby/seed_change']]);
  interrupted.$('#mode-solo').onclick();
  assert.equal(interrupted.interactions.length, 1);

  // A late callback from a previous lobby visit must neither render nor emit.
  const staleUsage = harness(); staleUsage.input('2040');
  const staleTimer = [...staleUsage.timers.values()][0];
  const staleBlur = staleUsage.$('#ng-seed').onblur;
  staleUsage.context.setupLobby(staleUsage.lob);
  const pendingAfterRevisit = staleUsage.pending.length;
  staleTimer(); staleBlur();
  assert.equal(staleUsage.pending.length, pendingAfterRevisit);
  assert.equal(staleUsage.interactions.length, 0);
  staleUsage.input('0'); staleUsage.flush();
  staleUsage.$('#ng-seed').onchange(); staleUsage.$('#ng-seed').onblur();
  assert.deepEqual(staleUsage.interactions, [['lobby/seed_change']]);

  const h = harness();
  assert.match(h.pending[0].path, /seed=6163$/);
  h.pending[0].resolve({teams: [{id: 'old', balance: 227100}]}); await tick();
  const stalePick = h.$('#ng-teams').pick;
  h.input('2040');
  assert.match(h.$('#ng-teams').innerHTML, /Updating/);
  stalePick({id: 'old'}); assert.equal(h.creations.length, 0);
  h.flush();
  assert.match(h.pending[1].path, /seed=2040$/);
  h.input('2041'); h.flush();
  h.pending[2].resolve({teams: [{id: 'latest', balance: 246900}]}); await tick();
  h.pending[1].resolve({teams: [{id: 'late'}]}); await tick();
  assert.equal(h.$('#ng-teams').teams[0].id, 'latest');
  await h.$('#ng-teams').pick({id: 'latest'});
  assert.equal(h.creations[0].seed, 2041);

  const change = harness(); change.$('#ng-seed').value = '2040';
  change.$('#ng-seed').onchange();
  assert.match(change.pending[1].path, /seed=2040$/);

  for (const value of ['', '1.5', '9007199254740992']) {
    const x = harness(); x.input(value); x.flush();
    assert.equal(x.pending.length, 1);
    assert.match(x.$('#ng-teams').innerHTML, /whole-number/);
    x.pending[0].resolve({teams: [{id: 'old'}]}); await tick();
    assert.match(x.$('#ng-teams').innerHTML, /whole-number/);
  }
  for (const value of ['0', '-7']) {
    const x = harness(); x.input(value); x.flush();
    assert.match(x.pending[1].path, new RegExp(`seed=${value}$`));
    x.pending[1].resolve({teams: [{id: 't'}]}); await tick();
    await x.$('#ng-teams').pick({id: 't'});
    assert.equal(x.creations[0].seed, Number(value));
  }
  const failure = harness(); failure.input('2040'); failure.flush();
  failure.pending[0].reject(new Error('old error')); await tick();
  assert.match(failure.$('#ng-teams').innerHTML, /Preparing/);
  failure.pending[1].reject(new Error('offline')); await tick();
  assert.match(failure.$('#ng-teams').innerHTML, /Could not load teams/);

  const pack = harness(); pack.$('#ng-worlds').children[1].onclick();
  pack.pending[0].resolve({teams: [{id: 'late-fiction'}]}); await tick();
  assert.equal(pack.$('#ng-teams').teams[0].id, 'pack-team');
  pack.$('#ng-scenarios').children[1].onclick();
  await pack.$('#ng-teams').pick({id: 'pack-team'});
  assert.equal(pack.creations[0].pack, 'pack');
  assert.equal(pack.creations[0].scenario, 'youth');

  const legacy = harness(); legacy.$('#ng-modes').children[1].onclick();
  legacy.input('2040'); legacy.flush();
  legacy.pending[2].resolve({offers: [{team_id: 'career'}]}); await tick();
  legacy.pending[1].resolve({offers: [{team_id: 'stale-career'}]}); await tick();
  legacy.pending[0].resolve({teams: [{id: 'stale-team'}]}); await tick();
  assert.equal(legacy.$('#ng-teams').offers[0].team_id, 'career');
  await legacy.$('#ng-teams').pick({team_id: 'career'});
  assert.equal(legacy.creations[0].game_mode, 'legacy');
  assert.equal(legacy.creations[0].seed, 2040);

  const shared = harness(); shared.$('#mode-shared').onclick();
  shared.pending[1].resolve({teams: [{id: 'shared'}]}); await tick();
  await shared.$('#ng-teams').pick({id: 'shared'});
  assert.equal(shared.creations[0].shared, true);

  const draft = harness(); draft.$('#ng-draft').children[1].onclick();
  const before = draft.interviews[0];
  draft.input('2040'); draft.flush();
  assert.equal(before.opts.isCurrent(), false);
  before.accept({team_id: 'stale'}, {}); assert.equal(draft.creations.length, 0);
  const current = draft.interviews[1];
  assert.equal(current.opts.getSeed(), 2040);
  await current.accept({team_id: 'draft'}, {style: 'fast'});
  assert.equal(draft.creations[0].fantasy_draft, true);
  assert.equal(draft.creations[0].seed, 2040);
  assert.equal(draft.creations[0].scenario, null);

  const join = harness(); join.$('#mode-join').onclick();
  join.pending[0].resolve({teams: [{id: 'old'}]}); await tick();
  assert.match(join.$('#ng-teams').innerHTML, /Preparing/);
  const revisit = harness(); revisit.context.setupLobby(revisit.lob);
  revisit.pending[1].resolve({teams: [{id: 'new-visit'}]}); await tick();
  revisit.pending[0].resolve({teams: [{id: 'old-visit'}]}); await tick();
  assert.equal(revisit.$('#ng-teams').teams[0].id, 'new-visit');

  // Exercise the actual interview's guards across both awaited endpoints.
  const draftSource = fs.readFileSync('src/esports_sim/web/static/draft.js', 'utf8');
  const draftCode = draftSource.slice(draftSource.indexOf('async function runDraftInterview('), draftSource.indexOf('window.runDraftInterview'));
  for (const staleAt of ['questions', 'offers']) {
    const requests = []; let current = true;
    const container = new Node();
    const context = {el: () => new Node(), esc: x => x, money: x => x,
      api: () => new Promise(resolve => requests.push(resolve))};
    vm.createContext(context); vm.runInContext(draftCode, context);
    const work = context.runDraftInterview(container, {getSeed: () => 2040, isCurrent: () => current}, () => {});
    if (staleAt === 'questions') {
      current = false; container.innerHTML = 'new preview';
      requests[0]({questions: []}); await work;
    } else {
      requests[0]({questions: []}); await tick();
      current = false; container.innerHTML = 'new preview';
      requests[1]({offers: []}); await work; await tick();
    }
    assert.equal(container.innerHTML, 'new preview');
  }
  const joinBodies = [];
  const joinContext = {el: () => new Node(), esc: x => x, money: x => x,
    api: async (path, body) => {
      if (body) { joinBodies.push(body); return {offers: []}; }
      return {questions: []};
    }};
  vm.createContext(joinContext); vm.runInContext(draftCode, joinContext);
  const joinContainer = new Node();
  await joinContext.runDraftInterview(joinContainer, {code: 'TEST'}, () => {});
  await tick();
  assert.equal(joinBodies[0].code, 'TEST');
  assert.equal(Object.hasOwn(joinBodies[0], 'seed'), false);
  assert.equal(joinContainer.children.length, 2);
})().catch(error => { console.error(error); process.exitCode = 1; });
