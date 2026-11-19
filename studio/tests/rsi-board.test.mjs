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

test('compare exact evaluation cases and retain missing scores and changed conditions', async () => {
  const {compareCases} = await import('../plugin/rsi-views.mjs');
  const caseOf=(id,outcome,setup='a',split='dev')=>({id,outcome,setup,split});
  const reference={episodes:[caseOf('fixed','failure'),caseOf('lost','success'),caseOf('held','success'),caseOf('new-seed','failure'),caseOf('unscored','interrupted'),caseOf('gone','success')]};
  const current={episodes:[caseOf('lost','failure'),caseOf('fixed','success'),caseOf('held','success','a','heldout'),caseOf('new-seed','success','b'),caseOf('unscored','success'),caseOf('extra','failure')]};
  assert.deepEqual(Object.fromEntries(compareCases(current,reference).map(p=>[p.id,p.kind])),{
    lost:'regression', fixed:'gain',held:'different','new-seed':'different',unscored:'restored',gone:'missing',extra:'added'
  });
  assert.ok(compareCases(current,null).every(p=>p.kind==='single'));
});
