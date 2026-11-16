import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {CodexSessions, toolResponse} from '../plugin/codex-session.mjs';
import {wireToolName} from '../plugin/codex-rpc.mjs';

const tool={name:'read_fixture',description:'Read one fixture',parameters:{type:'object'}};
const opts=()=>({sessionId:'chat-a',model:'test',tools:[tool],messages:[{role:'user',content:'Read the chain'}]});
const collect=async stream=>{const out=[];for await(const c of stream)out.push(c);return out;};
const record=(options,chunks)=>options.messages.push({role:'assistant',content:chunks.filter(c=>c.type==='block-end').map(c=>c.block)});
function fixture() {
  const calls=[],connections=[];
  const rpcFactory=({onEvent})=>{
    let threadId;
    const emit=(method,params,id)=>onEvent({method,params:{threadId,...params},...(id===undefined?{}:{id})});
    const connection={emit,closed:false};connections.push(connection);
    return {
      async initialize(){calls.push({method:'initialize'});},
      async request(method,params){
        calls.push({method,params});
        if(method==='thread/start'){threadId='thread-'+connections.length;return {thread:{id:threadId}};}
        if(method==='thread/resume'){threadId=params.threadId;return {};}
        if(method==='turn/start'){
          queueMicrotask(()=>emit('item/tool/call',{callId:'call-1',tool:wireToolName(tool.name),arguments:{file:'a'}},71));
          return {turn:{id:'turn-1'}};
        }
        return {};
      },
      send(value){calls.push({method:'response',value});queueMicrotask(()=>{
        emit('item/agentMessage/delta',{itemId:'answer',delta:'Read the result.'});
        emit('thread/tokenUsage/updated',{tokenUsage:{total:{inputTokens:100,cachedInputTokens:20,outputTokens:30,totalTokens:130}}});
        emit('thread/tokenUsage/updated',{tokenUsage:{total:{inputTokens:120,cachedInputTokens:25,outputTokens:35,totalTokens:155}}});
        emit('turn/completed',{turn:{status:'completed'}});
      });},
      close(){connection.closed=true;},
    };
  };
  return {calls,connections,rpcFactory};
}

test('DSH tool boundary keeps the original turn, consumes result once and injects guidance first',async()=>{
  const f=fixture(), metrics=[],sessions=new CodexSessions({...f,onMetric:m=>metrics.push(m)}),o=opts();
  try {
    const first=await collect(sessions.stream(o,'/tmp'));
    record(o,first);
    assert.equal(f.connections[0].closed,false);
    o.messages.push({role:'tool',source:{callId:'call-1'},content:[{type:'text',text:'A'}]}, {role:'user',content:'Explain briefly'});
    const second=await collect(sessions.stream(o,'/tmp'));record(o,second);
    assert.equal(second.at(-1).reason.kind,'stop');
    assert.equal(f.calls.filter(x=>x.method==='initialize').length,1);
    assert.equal(f.calls.filter(x=>x.method==='thread/start').length,1);
    assert.equal(f.calls.filter(x=>x.method==='turn/start').length,1);
    const response=f.calls.findIndex(x=>x.method==='response');
    assert.equal(f.calls[response-1].method,'thread/inject_items');
    assert.equal(f.calls[response].value.id,71);
    assert.deepEqual(f.calls[response].value.result,{success:true,contentItems:[{type:'inputText',text:'A'}]});
    assert.equal(second.find(x=>x.type==='usage').usage.inputTokens,80);
    assert.equal(second.filter(x=>x.type==='usage').at(-1).usage.inputTokens,95);
    assert.equal(second.filter(x=>x.type==='usage').at(-1).usage.outputTokens,35);
    assert.deepEqual(metrics.map(m=>m.mode),['start','continue']);
    o.messages.push({role:'user',content:'Again'});
    await collect(sessions.stream(o,'/tmp'));
    assert.equal(f.calls.filter(x=>x.method==='turn/start').length,2);
    assert.equal(f.connections.length,1);
  }finally{sessions.close();}
});

test('missing tool result fails without acknowledging or re-executing the action',async()=>{
  const f=fixture(),sessions=new CodexSessions(f),o=opts();
  record(o,await collect(sessions.stream(o,'/tmp')));
  await assert.rejects(collect(sessions.stream(o,'/tmp')),/Missing recorded/);
  assert.equal(f.calls.filter(x=>x.method==='turn/start').length,1);
  assert.equal(f.calls.some(x=>x.method==='response'),false);
  assert.equal(f.connections[0].closed,true);
});

test('settled conversations resume after restart; other chats and changed workspaces do not share them',async()=>{
  const dir=await mkdtemp(path.join(tmpdir(),'codex-continuity-')),f=fixture(),o=opts();
  let sessions=new CodexSessions({...f,stateDir:dir});
  try {
    record(o,await collect(sessions.stream(o,'/tmp')));
    o.messages.push({role:'tool',source:{callId:'call-1'},content:'A'});
    record(o,await collect(sessions.stream(o,'/tmp')));sessions.close();
    sessions=new CodexSessions({...f,stateDir:dir});o.messages.push({role:'user',content:'Next'});
    await collect(sessions.stream(o,'/tmp'));
    assert.equal(f.calls.filter(x=>x.method==='thread/resume').length,1);
    await collect(sessions.stream({...opts(),sessionId:'chat-b'},'/tmp'));
    await collect(sessions.stream({...opts(),sessionId:'chat-a'},'/var/tmp'));
    assert.equal(f.calls.filter(x=>x.method==='thread/start').length,3);
    assert.notEqual(sessions.sessions.get('chat-a').threadId,sessions.sessions.get('chat-b').threadId);
  }finally{sessions.close();await rm(dir,{recursive:true,force:true});}
});

test('tool failures and images keep their actual content and cancellation releases the connection',async()=>{
  assert.deepEqual(await toolResponse({role:'tool',source:{callId:'c'},isError:true,content:[{type:'text',text:'Denied'},{type:'image',attachment:{attachmentId:'x'}}]},
    {readImage:async()=>({ref:{mediaType:'image/png'},data:Buffer.from('x')})}),
    {success:false,contentItems:[{type:'inputText',text:'Denied'},{type:'inputImage',imageUrl:'data:image/png;base64,eA=='}]});
  const f=fixture(),sessions=new CodexSessions(f),signal=new AbortController();
  signal.abort();await assert.rejects(collect(sessions.stream({...opts(),signal:signal.signal},'/tmp')),/abort/i);
  assert.equal(f.connections.length,0);
});

test('changing prompt context does not discard a waiting tool or create another thread',async()=>{
  const f=fixture(),sessions=new CodexSessions(f),o=opts();
  try {
    record(o,await collect(sessions.stream(o,'/tmp')));
    o.messages.push({role:'tool',source:{callId:'call-1'},content:'A'});o.system='Project revision 2; task id task-1';
    await collect(sessions.stream(o,'/tmp'));
    assert.equal(f.calls.filter(x=>x.method==='thread/start').length,1);
    assert.ok(f.calls.some(x=>x.method==='thread/inject_items'&&x.params.items.some(i=>i.role==='developer')));
  }finally{sessions.close();}
});
