const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const helpers = source.slice(source.indexOf('function developmentPlanFeedback('), source.indexOf('async function roster('));
async function scenario(action, failure) {
  const fields = {focus: 'dev_focus', language: 'learning_language', intensity: 'training_intensity'};
  const player = {id: 'p1', dev_focus: 'auto', learning_language: '', training_intensity: 'normal', not_developing: 'exhausted', development_plan: {skills: ['game_sense'], advice: 'Old'}};
  const controls = Object.fromEntries(Object.entries(fields).map(([key, field]) => [key, {value: player[field], disabled: key === 'language', focus() {document.activeElement = this;}}]));
  const feedback = {innerHTML: ''};
  const row = {isConnected: true, querySelector(selector) {return selector === '.dev-feedback' ? feedback : controls[selector.match(/"(\w+)"/)[1]];}};
  const document = {body: {}, activeElement: controls[action]};
  const requests = [], messages = [];
  const updated = {...player, [fields[action]]: 'accepted', not_developing: null, development_plan: {skills: [], advice: 'Server recovery <safe>'}};
  const context = {document, esc: text => text.replaceAll('<', '&lt;').replaceAll('>', '&gt;'), humanize: text => text, toast: message => messages.push(message), api: async (path, body) => {
    requests.push({path, body});
    if (body) {
      assert.ok(Object.values(controls).every(control => control.disabled));
      document.activeElement = document.body;
      if (failure === 'reject') throw new Error('rejected');
      if (failure === 'soft') return {ok: false, message: 'Rejected'};
      return {ok: true, message: 'Saved'};
    }
    if (failure === 'readback') throw new Error('offline');
    return {players: [updated]};
  }};
  vm.createContext(context);
  vm.runInContext(helpers, context);
  feedback.innerHTML = context.developmentPlanFeedback(player);
  context.bindDevelopmentPlanControls(row, player, 'team1');
  controls[action].value = 'requested';
  await controls[action].onchange();
  assert.equal(controls[action].disabled, action === 'language');
  assert.equal(controls.language.disabled, true);
  assert.equal(document.activeElement, controls[action]);
  if (failure === 'reject' || failure === 'soft') {
    assert.equal(requests.length, 1);
    assert.equal(controls[action].value, action === 'focus' ? 'auto' : action === 'language' ? '' : 'normal');
    assert.match(feedback.innerHTML, /too exhausted to train/);
  } else if (failure === 'readback') {
    assert.equal(controls[action].value, 'requested');
    assert.match(messages.at(-1), /feedback could not refresh/);
  } else {
    assert.equal(requests[1].path, '/api/roster/team1');
    assert.equal(controls[action].value, 'accepted');
    assert.match(feedback.innerHTML, /Recovery/);
    assert.match(feedback.innerHTML, /&lt;safe&gt;/);
    assert.doesNotMatch(feedback.innerHTML, /exhausted|game_sense/);
  }
}
(async () => {
  for (const action of ['focus', 'language', 'intensity']) await scenario(action);
  for (const failure of ['reject', 'soft', 'readback']) await scenario('focus', failure);
  console.log('Development feedback: three controls, server readback, rejection, refresh failure, focus preservation passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
