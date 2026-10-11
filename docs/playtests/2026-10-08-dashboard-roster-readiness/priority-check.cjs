const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync('src/esports_sim/web/static/app.js','utf8');
const block = source.slice(source.indexOf('    const lineupIns ='),source.indexOf('    prepCard("Head coach"',source.indexOf('    const lineupIns =')));
function briefing(ready, changed, burnout) {
  const App={}; let card; let destination;
  const run = new Function('s','sug','burnoutWatch','rosterShort','esc','plink','prepCard','App','dashGoTab',block);
  run({roster_readiness:{ready,count:ready?5:4,minimum:5,shortfall:ready?0:1}}, {changed,players:[{id:'replacement',handle:'Replacement',dressed:false}]}, burnout?[{id:'tired',handle:'Tired'}]:[], !ready, x=>x, (id,h)=>h, (...a)=>{card=a},App,t=>{destination=t});
  card[6](); return {title:card[1],copy:card[2],status:card[3],tone:card[4],action:card[5],destination,App};
}
for(const changed of [false,true]) for(const burnout of [false,true]) {
  const b=briefing(false,changed,burnout); assert.equal(b.status,'Blocked'); assert.equal(b.title,'Complete the match squad'); assert.equal(b.action,'Find players'); assert.equal(b.destination,'market'); assert.equal(b.App.marketTab,'players'); assert.match(b.copy,/Sign 1 more/);
}
assert.equal(briefing(true,false,false).status,'Stable');
assert.equal(briefing(true,false,true).title,"Protect Tired's legs");
assert.equal(briefing(true,true,true).title,'Review the suggested five');
assert.equal(briefing(true,true,false).destination,'club');
console.log('8 roster/lineup/fatigue priority counterexamples passed');
