const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const requests = [];
function el(hidden = true) {
  const classes = new Set(hidden ? ['hidden'] : []);
  return {dataset: {}, innerHTML: '', scrollTop: 0,
    classList: {contains: x => classes.has(x), add: x => classes.add(x), remove: x => classes.delete(x),
      toggle: (x, yes) => yes ? classes.add(x) : classes.delete(x)},
    addEventListener() {}, setAttribute() {}, focus() {}, querySelector: () => el()};
}
const help = el(), helpBody = el(), body = el(), back = el(), close = el();
const overlay = el(); overlay.querySelector = selector => selector === '#profile-body' ? body : selector === '.pf-back' ? back : close;
const nodes = {'help': help, 'help-body': helpBody};
const document = {hidden: false, addEventListener() {}, body: {appendChild() {}},
  createElement: () => overlay, getElementById: id => nodes[id], querySelectorAll: () => []};
const context = {document, window: {addEventListener() {}}, crypto: require('node:crypto').webcrypto,
  performance: {now: () => 0}, setInterval() {}, setTimeout, clearTimeout, AbortController,
  fetch: async (_, options) => {requests.push(...JSON.parse(options.body).events); return {ok: true};},
  render() {}, html: () => ({}), ProfileLoading: {}, PlayerProfile: {}, TeamProfile: {}, StaffProfile: {},
  ManagerProfile: {}, Unavailable: {}, App: {tab: 'club'}, localStorage: {setItem() {}},
  helpScreensMarkup: () => 'screens', helpGlossaryMarkup: () => 'terms', helpFirstWeekMarkup: () => 'first',
  helpSeenKey: () => 'seen', profileFetch: async () => ({})};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/esports_sim/web/static/usage.js','utf8'), context);
const profile = fs.readFileSync('src/esports_sim/web/static/profile.js','utf8');
vm.runInContext(profile.slice(profile.indexOf('let pfOverlayEl = null;'), profile.indexOf('/* -- one delegated listener')), context);
const app = fs.readFileSync('src/esports_sim/web/static/app.js','utf8');
vm.runInContext(app.slice(app.indexOf('let helpUsageSection = null;'), app.indexOf('function maybeShowFirstWeekHelp')), context);
async function take() {
  await context.window.Usage.boundary();
  const events = requests.splice(0).filter(e => e.kind === 'interaction');
  assert(events.every(e => Object.keys(e).sort().join(',') === 'kind,target'));
  return events.map(e => e.target);
}
(async () => {
  await context.openPlayerProfile('SECRET');
  assert.deepEqual(await take(), ['profile/player_open']);
  await context.openPlayerProfile('SECRET', {replace:true});
  assert.deepEqual(await take(), []); // refresh does not create a second inspection
  await context.openTeamProfile('SECRET_TEAM');
  assert.deepEqual(await take(), ['profile/player_close','profile/team_open']);
  context.pfGoBack(); await new Promise(setImmediate);
  assert.deepEqual(await take(), ['profile/team_close','profile/player_open']);
  context.closeProfile(); context.closeProfile();
  assert.deepEqual(await take(), ['profile/player_close']);
  context.profileFetch = async () => null;
  await context.openPlayerProfile('FAILED_SECRET'); context.closeProfile();
  assert.deepEqual(await take(), []);
  let resolve;
  context.profileFetch = () => new Promise(done => {resolve=done;});
  const loading = context.openPlayerProfile('STALE_SECRET'); context.closeProfile(); resolve({}); await loading;
  assert.deepEqual(await take(), []);
  context.profileFetch = async () => ({});
  await context.openStaffProfile('STAFF_SECRET'); context.closeProfile();
  context.window.openManagerProfile({id:'MANAGER_SECRET'}); context.closeProfile();
  assert.deepEqual(await take(), ['profile/staff_open','profile/staff_close','profile/manager_open','profile/manager_close']);
  // Only the latest request may become visible when fetches resolve out of order.
  const waiting = {};
  context.profileFetch = url => new Promise(done => {waiting[url] = done;});
  const old = context.openPlayerProfile('OLD_SECRET');
  const latest = context.openTeamProfile('NEW_SECRET');
  waiting['/api/teams/NEW_SECRET/profile']({}); await latest;
  waiting['/api/players/OLD_SECRET/profile']({}); await old;
  assert.deepEqual(await take(), ['profile/team_open']);
  context.profileFetch = async () => null;
  await context.openPlayerProfile('FAILED_SECRET'); context.closeProfile();
  assert.deepEqual(await take(), ['profile/team_close']);
  context.profileFetch = async () => ({});
  context.openHelp(); context.openHelp(); context.renderHelp('first-week');
  context.renderHelp('screens'); context.renderHelp('screens'); context.renderHelp('glossary');
  context.closeHelp(); context.closeHelp();
  assert.deepEqual(await take(), ['handbook/open','handbook/section_first_week','handbook/section_screens','handbook/section_glossary','handbook/close']);
  context.renderHelp('screens'); assert.deepEqual(await take(), []); // hidden rendering is not inspection
  context.openHelp('screens', 'club', true); context.closeHelp();
  assert.deepEqual(await take(), ['handbook/open','handbook/section_screens','handbook/close']);
  delete nodes.help; context.openHelp(); assert.deepEqual(await take(), []);
  context.window.Usage.interaction('profile/player_open/SECRET');
  context.window.Usage.interaction('handbook/section_PRIVATE'); assert.deepEqual(await take(), []);
  const allowed = ['lobby/seed_change','week/full_report_open', ...['player','team','staff','manager'].flatMap(k => ['open','close'].map(a => `profile/${k}_${a}`)),
    'handbook/open','handbook/close','handbook/section_first_week','handbook/section_screens','handbook/section_glossary'];
  for (const target of allowed) context.window.Usage.interaction(target);
  console.log(JSON.stringify(await take()));
})().catch(e => {console.error(e);process.exitCode=1;});
