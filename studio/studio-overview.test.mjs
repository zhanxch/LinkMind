import assert from 'node:assert/strict';
import test from 'node:test';
import {resultMetrics,graphPositions} from './plugin/studio-overview.mjs';
test('process completion does not invent a score or a success rate',()=>{
 assert.deepEqual(resultMetrics({status:'completed',elapsed_seconds:12},{success:true}),{score:null,seconds:12});
 assert.deepEqual(resultMetrics({}, {native:{score:0},wall_seconds:0}),{score:0,seconds:0});
 assert.deepEqual(resultMetrics({elapsed_seconds:Infinity},{native:{score:'100'}}),{score:null,seconds:null});
});
test('task graph preserves independent work and recorded dependency levels',()=>{
 const work=[{id:'a',depends_on:[]},{id:'b',depends_on:[]},{id:'c',depends_on:['a','b']},{id:'d',depends_on:['c']}];
 const [a,b,c,d]=graphPositions(work);
 assert.equal(a.x,b.x);assert.notEqual(a.y,b.y);assert.ok(c.x>a.x);assert.ok(d.x>c.x);
 assert.deepEqual(work[2].depends_on,['a','b']);
});
test('unknown or malformed historical dependency edges do not loop',()=>{
 const nodes=graphPositions([{id:'a',depends_on:['b']},{id:'b',depends_on:['a','missing']}]);
 assert.equal(nodes.length,2);assert.ok(nodes.every(n=>Number.isFinite(n.x)));
});
