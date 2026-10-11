const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/esports_sim/web/static/app.js', 'utf8');
const statement = source.split('\n').find(line => line.includes('Current squad condition:'));
assert.ok(statement, 'Preparation condition row must exist');
const participants = [
  {handle: 'Hollowlock', condition: 55.900000000000006},
  {handle: 'Integer', condition: 56},
  {handle: '<zero>', condition: 0},
  {handle: 'Full', condition: 100},
  {handle: 'Round', condition: 55.96},
];
const before = JSON.stringify(participants);
let rendered;
vm.runInNewContext(statement, {
  pr: {participants}, pc: {appendChild(node) {rendered = node;}},
  el: (tag, cls, content) => ({tag, cls, content}),
  esc: value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
});
assert.equal(rendered.tag, 'p');
assert.equal(rendered.cls, 'muted');
assert.equal(rendered.content, 'Current squad condition: Hollowlock 55.9 · Integer 56.0 · &lt;zero&gt; 0.0 · Full 100.0 · Round 56.0.');
assert.equal(JSON.stringify(participants), before, 'Formatting must preserve source values');
console.log('Preparation condition: float noise, integers, bounds, rounding, escaped names, source preservation passed');
