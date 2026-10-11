const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/inbox.js', 'utf8');
const receipts = [], reads = [], clicks = [], rowCtl = new Map(), buttons = new Map();
function el(tag, classes = '', text = '') {
  const names = new Set(classes.split(' ').filter(Boolean));
  return {tag, textContent: text, children: [],
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); },
    setAttribute() {},
    classList: {toggle(name, on) { on ? names.add(name) : names.delete(name); },
      contains(name) { return names.has(name); }, remove(name) { names.delete(name); }},
  };
}
const context = {el, rowCtl, App: {}, INBOX_CAT_LABEL: {talk: 'Talk'}, inboxLabel: x => x,
  window: {Usage: {interaction: target => receipts.push(target)}},
  document: {querySelector: selector => buttons.get(selector)},
  markItemRead: async it => { if (it.unread) { reads.push(it.id); it.unread = false; } },
  inboxActionRow: () => el('div'),
};
vm.createContext(context);
const routeStart = source.indexOf('const INBOX_TAB_ALIAS =');
const routeEnd = source.indexOf('// Quietly re-pull', routeStart);
const rowStart = source.indexOf('  function inboxRow(it) {');
const rowEnd = source.indexOf('  /* -- rail:', rowStart);
vm.runInContext(source.slice(routeStart, routeEnd) + source.slice(rowStart, rowEnd), context);
for (const tab of ['club', 'tactics', 'season', 'company']) {
  buttons.set(`#tabs [data-tab="${tab}"]`, {click() { clicks.push([tab, {...context.App}]); }});
}
(async () => {
  const item = {id: 'PRIVATE_ID', title: 'PRIVATE_TITLE', body: 'PRIVATE_BODY',
    category: 'talk', week: 2, unread: true, tab: 'roster'};
  const row = context.inboxRow(item), header = row.children[0], body = row.children[1];
  assert.deepEqual(receipts, []); // Initial collapsed rendering emits nothing.
  await header.onclick();
  await rowCtl.get(item.id).openRow();
  await rowCtl.get(item.id).openRow(); // Digest expansion of an open row is a no-op.
  assert.deepEqual(receipts, ['inbox/item_open']);
  assert.deepEqual(reads, ['PRIVATE_ID']);
  assert(!body.classList.contains('collapsed'));
  await header.onclick(); await header.onclick();
  assert.deepEqual(receipts, ['inbox/item_open', 'inbox/item_close', 'inbox/item_open']);
  assert.deepEqual(reads, ['PRIVATE_ID']); // Reopening still preserves idempotent read behavior.
  let stopped = false;
  body.children[1].onclick({stopPropagation() { stopped = true; }});
  assert(stopped);
  assert.equal(context.App.clubTab, 'squad');
  assert.equal(receipts.at(-1), 'inbox/shortcut_club');
  context.inboxGoTab('match'); context.inboxGoTab('schedule'); context.inboxGoTab('social');
  assert.equal(context.App.tacticsTab, 'strategy');
  assert.equal(context.App.seasonTab, 'fixtures');
  assert.equal(context.App.companyTab, 'brand');
  assert.deepEqual(receipts.slice(-3), ['inbox/shortcut_tactics', 'inbox/shortcut_season', 'inbox/shortcut_company']);
  const before = receipts.length;
  context.inboxGoTab('PRIVATE_UNKNOWN'); context.inboxGoTab('market');
  buttons.get('#tabs [data-tab="club"]').disabled = true;
  context.inboxGoTab('roster');
  assert.equal(receipts.length, before); // Missing and disabled destinations do not count.
  assert.equal(clicks.length, 4);
  assert(!JSON.stringify(receipts).includes('PRIVATE'));
  context.window.Usage = undefined;
  await header.onclick();
  context.inboxGoTab('match'); // An absent sidecar does not block interaction.
  assert(body.classList.contains('collapsed'));
  assert.equal(clicks.length, 5);
  console.log('Inbox usage callback semantics passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
