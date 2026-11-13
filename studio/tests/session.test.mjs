import {test} from 'node:test';
import assert from 'node:assert/strict';
import {apply,taskFromResult} from '../plugin/session.mjs';

test('native MCP result identity preserves errors and accepts text or structured task results',()=>{
  assert.equal(taskFromResult({isError:true}),null);
  assert.equal(taskFromResult({isError:false,value:{structuredContent:{id:'task1'}}}).id,'task1');
  assert.equal(taskFromResult({isError:false,value:{content:[{type:'text',text:'{"id":"task2"}'}]}}).id,'task2');
  assert.throws(()=>taskFromResult({isError:false,value:{content:[]}}),/could not be linked/);
});

test('dispatch checks host conversation identity before allowing execution',async()=>{
  const original={url:process.env.LINKMIND_STUDIO_URL,token:process.env.LINKMIND_STUDIO_TOKEN,fetch:globalThis.fetch};
  process.env.LINKMIND_STUDIO_URL='http://127.0.0.1:9999';
  process.env.LINKMIND_STUDIO_TOKEN='test';
  let handler;const calls=[];
  globalThis.fetch=async(url,options)=>{
    calls.push({path:url.pathname,...JSON.parse(options.body)});
    return {ok:false,json:async()=>({error:'This conversation does not own that task'})};
  };
  try{
    await apply({on:(event,fn)=>{assert.equal(event,'tools/execute');handler=fn;}});
    let dispatched=false;
    await assert.rejects(handler({name:'mcp__linkmind__start_episode',agent:{id:'chat-b'},arguments:{task_id:'task1',session_id:'chat-a'}},async()=>{dispatched=true;}),/does not own/);
    assert.equal(dispatched,false);
    assert.equal(calls[0].session_id,'chat-b');
    assert.equal(calls[0].task_id,'task1');
    calls.length=0;
    globalThis.fetch=async(url,options)=>{calls.push({path:url.pathname,...JSON.parse(options.body)});return{ok:true,json:async()=>({})};};
    const result={isError:false,value:{structuredContent:{id:'task2'}}};
    assert.equal(await handler({name:'mcp__linkmind__create_task',agent:{id:'chat-b'},arguments:{}},async()=>result),result);
    assert.deepEqual(calls,[{path:'/api/tasks/task2/bind-session',session_id:'chat-b'}]);
  }finally{
    globalThis.fetch=original.fetch;
    for(const [key,value]of [['LINKMIND_STUDIO_URL',original.url],['LINKMIND_STUDIO_TOKEN',original.token]]){
      if(value===undefined)delete process.env[key];else process.env[key]=value;
    }
  }
});

test('project dispatch binds registration and checks both comparison runs against the native conversation',async()=>{
  const original=globalThis.fetch;
  const calls=[];let handler;
  globalThis.fetch=async(url,options)=>{
    const body=JSON.parse(options.body);calls.push({path:url.pathname,...body});
    return {ok:body.run_id!=='other-chat',json:async()=>({error:'This conversation does not own that project'})};
  };
  try{
    await apply({get:()=>({url:'http://127.0.0.1:9999',token:'test'}),on:(_,fn)=>handler=fn});
    await handler({name:'mcp__linkmind__open_project',agent:{id:'native-chat'},arguments:{}},async()=>({value:{structuredContent:{id:'project1'}}}));
    assert.deepEqual(calls.pop(),{path:'/api/projects/project1/bind-session',session_id:'native-chat'});
    let dispatched=false;
    await assert.rejects(handler({name:'mcp__linkmind__compare_project_runs',agent:{id:'native-chat'},arguments:{left_run_id:'mine',right_run_id:'other-chat',session_id:'forged'}},async()=>{dispatched=true;}),/does not own/);
    assert.equal(dispatched,false);
    assert.deepEqual(calls.map(x=>[x.session_id,x.run_id]),[['native-chat','mine'],['native-chat','other-chat']]);
  }finally{globalThis.fetch=original;}
});
