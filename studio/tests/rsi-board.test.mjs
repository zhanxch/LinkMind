import test from 'node:test';
import assert from 'node:assert/strict';
import {roundLineage} from '../plugin/rsi-views.mjs';

test('branches keep their true generation even if the parent arrives last', () => {
  const records = [['v2','v1'],['alternative','v0'],['v1','v0'],['v0','']];
  const levels = roundLineage(records.map(([id,parent])=>({id,parent})));
  assert.deepEqual(levels.map(row=>[row.id,row.depth]), [['v0',0],['alternative',1],['v1',1],['v2',2]]);
});

test('missing, cyclic and ambiguous ancestors stay visible without a comparison', () => {
  const records = [['x','y'],['y','x'],['z',''],['z',''],['child','z'],['orphan','absent']];
  assert.deepEqual(roundLineage(records.map(([id,parent])=>({id,parent}))).map(row=>row.depth), records.map(()=>null));
});
