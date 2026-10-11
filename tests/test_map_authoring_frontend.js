const test=require('node:test');
const assert=require('node:assert/strict');
const {floorOutline}=require('../src/esports_sim/web/static/map-authoring.js');

test('floor union outline removes internal tile seams and preserves a hole',()=> {
  const surface={polygon:[[0,0],[4,0],[4,2],[0,2]],floor_extensions:[
    {x:0,y:2,w:1,h:2},{x:3,y:2,w:1,h:2},{x:0,y:4,w:4,h:1},
    {x:0,y:0,w:4,h:2}, // overlap does not duplicate the core boundary
  ]};
  const edges=floorOutline(surface);
  const length=edges.reduce((sum,[a,b])=>sum+Math.hypot(b[0]-a[0],b[1]-a[1]),0);
  assert.equal(length,26); // 4x5 outer perimeter plus 2x2 hole
  assert.ok(edges.some(([a,b])=>a[0]===1 && b[0]===3 && a[1]===2 && b[1]===2));
  assert.ok(!edges.some(([a,b])=>a[1]===4 && b[1]===4 && a[0]===0 && b[0]===4));
});
