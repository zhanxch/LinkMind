import test from 'node:test';
import assert from 'node:assert/strict';
import {taskContext} from '../plugin/task-context.mjs';
test('task memory keeps constraints intact while historical logs become a bounded, explicit index',()=>{
 const task={id:'t',original_request:'request'.repeat(1000),constraints:'constraint'.repeat(1000),criteria:[{text:'never change the protocol'}]};
 const value={registration_id:'p',project:{revision:4,work:Array.from({length:50},(_,i)=>({id:'w'+i,objective_id:'t',state:i===49?'active':'done',description:'x'.repeat(8000)})),records:Array.from({length:30},(_,i)=>({id:'r'+i,objective_id:'t',kind:'evidence',text:'x'.repeat(8000),reference:'result.json'}))},runs:[{id:'run',project_context:{objective_id:'t'},status:'completed',recipe:{secret:'must not be duplicated'}}]};
 const view=taskContext(value,task);
 assert.deepEqual(view.task,task);assert.equal(view.work[0].id,'w49');assert.equal(view.work.length,20);
 assert.equal(view.records.length,6);assert.equal(view.records[0].id,'r24');assert.equal(view.records[0].text.length,1200);assert.equal(view.records[0].excerpt,true);
 assert.deepEqual(view.runs,[{id:'run',status:'completed'}]);assert.equal(view.available.records,30);assert.equal(value.project.records[0].text.length,8000);
});
