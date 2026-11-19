import test from 'node:test';
import assert from 'node:assert/strict';
import {codexStream, projectMessages, wireToolName} from '../plugin/codex-rpc.mjs';

const options = {model:'test',messages:[{role:'user',content:'Inspect the scene'}],tools:[
  {name:'mcp__linkmind__robot_call',description:'Robot bridge',parameters:{type:'object'}}]};
function fakeFactory(events, calls) {
  return ({onEvent}) => ({
    async initialize() {calls.push('initialized');},
    async request(method, params) {
      calls.push({method,params});
      if(method==='thread/start') return {thread:{id:'t'}};
      if(method==='turn/start') queueMicrotask(()=>events.forEach(onEvent));
      return {};
    },
    send(message) {calls.push({send:message});},
    close() {calls.push('closed');},
  });
}
const collect = async stream => {const out=[];for await(const item of stream) out.push(item);return out;};

test('Codex calls become native dsh calls without executing or acknowledging them', async () => {
  const calls=[];
  const chunks=await collect(codexStream(options,null,{rpcFactory:fakeFactory([
    {id:9,method:'item/tool/call',params:{threadId:'t',callId:'call-1',tool:wireToolName(options.tools[0].name),arguments:{tool:'observe'}}},
  ],calls)}));
  assert.equal(chunks.find(c=>c.type==='block-end').block.name,'mcp__linkmind__robot_call');
  assert.deepEqual(chunks.at(-1),{type:'finish',reason:{kind:'tool-calls'}});
  assert.ok(calls.includes('closed'));
  assert.equal(calls.some(c=>c?.send?.id===9),false);
  const declaration=calls.find(c=>c.method==='thread/start').params;
  assert.deepEqual(declaration.environments,[]);
  assert.ok(!declaration.dynamicTools[0].name.startsWith('mcp__'));
});

test('Replay preserves tool correlation, roles and image bytes', async () => {
  const tool={type:'tool-call',id:'original',name:'mcp__linkmind__robot_call',arguments:'{}'};
  const messages=[{role:'user',content:'look'}, {role:'assistant',content:[tool]},
    {role:'tool',source:{callId:'original'},content:[{type:'text',text:'observation'},{type:'image',attachment:{attachmentId:'image1'}}]}];
  const items=await projectMessages(messages,{readImage:async()=>({ref:{mediaType:'image/png'},data:Buffer.from('bytes')})});
  assert.equal(items[0].role,'user');assert.equal(items[1].name,wireToolName(tool.name));
  assert.equal(items[2].call_id,'original');assert.equal(items[2].output[1].image_url,'data:image/png;base64,Ynl0ZXM=');
});

test('Unknown tools fail closed and cancellation closes the provider', async () => {
  const calls=[];
  await assert.rejects(collect(codexStream(options,null,{rpcFactory:fakeFactory([
    {id:9,method:'item/tool/call',params:{threadId:'t',callId:'c',tool:'other',arguments:{}}},
  ],calls)})),/Undeclared/);
  const abort=new AbortController();abort.abort();
  await assert.rejects(collect(codexStream({...options,signal:abort.signal},null,{rpcFactory:fakeFactory([],calls)})),/abort/i);
  assert.ok(calls.includes('closed'));
});

test('Streamed progress and summaries end as native conversation blocks', async () => {
  const chunks=await collect(codexStream(options,null,{rpcFactory:fakeFactory([
    {method:'item/reasoning/summaryTextDelta',params:{threadId:'t',itemId:'r',delta:'Checking the scene'}},
    {method:'item/agentMessage/delta',params:{threadId:'t',itemId:'a',delta:'Observed.'}},
    {method:'turn/completed',params:{threadId:'t',turn:{status:'completed'}}},
  ],[])}));
  assert.equal(chunks.filter(c=>c.type==='block-end').length,2);
  assert.equal(chunks.at(-1).reason.kind,'stop');
});
