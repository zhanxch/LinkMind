import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startStudio} from '../plugin/runtime.mjs';
import {apply} from '../plugin/goal.mjs';

test('native Goal, restored Goal and slash creation bind exactly one shared task each',async()=>{
  const state=await mkdtemp(path.join(tmpdir(),'linkmind-goal-controller-'));
  const backend=await startStudio({root:fileURLToPath(new URL('../../',import.meta.url)),state,workspace:state});
  const handlers=new Map(),agent={id:'controller-test',status:'idle'},goals=new Map();let command,seq=0;
  const emit=()=>{const goal=goals.get(agent.id);for(const cb of handlers.get('goal/changed')||[])cb({agent,change:{ref:{id:goal.id,revision:goal.revision},goal:{...goal}}});};
  const ctx={logger:{warn:(...args)=>assert.fail(args.join(' '))},
    on(name,callback){handlers.set(name,[...(handlers.get(name)||[]),callback]);},
    agents:{get:()=>agent},workingDirectory:{ensure:async()=>state},commands:{register:d=>{command=d;}},
    goals:{get:()=>goals.get(agent.id),
      create(_agent,{objective}){const g={id:'native-'+(++seq),revision:1,objective,phase:'active',activation:'armed'};goals.set(agent.id,g);emit();return g;},
      pause(){const g=goals.get(agent.id);goals.set(agent.id,{...g,revision:g.revision+1,phase:'paused',activation:'disarmed'});emit();},
      resume(){const g=goals.get(agent.id);goals.set(agent.id,{...g,revision:g.revision+1,phase:'active',activation:'armed'});emit();}},
  };
  async function assembled(){const assembly={contexts:[]};for(const fn of handlers.get('system-prompt/assemble')||[])await fn(assembly,{agent},()=>{});return assembly;}
  async function api(route,data){const response=await fetch(backend.url+'/api'+route,{method:data?'POST':'GET',headers:{Authorization:'Bearer '+backend.token,'Content-Type':'application/json'},...(data?{body:JSON.stringify(data)}:{})});assert.ok(response.ok);return response.json();}
  try{
    await apply(ctx,{connectionFile:backend.connectionFile});
    ctx.goals.create(agent,{objective:'复现 fixture'});
    let prompt=await assembled();assert.match(prompt.contexts[0].text,/not the native goal id/);
    const registration=await api('/workspace/open',{path:state,session_id:agent.id});
    let value=await api('/projects/'+registration.id+'/context');
    assert.equal(value.project.objectives.length,1);assert.equal(value.project.objectives[0].native_goal_id,'native-1');
    goals.get(agent.id).phase='complete';
    const result=await command.handler({agent,attachments:[],rawInput:'优化 fixture'});
    assert.equal(result.kind,'success',result.text);
    await assembled();value=await api('/projects/'+registration.id+'/context');
    assert.equal(value.project.objectives.length,2);assert.equal(value.project.objectives[1].native_goal_id,'native-2');
    goals.set(agent.id,{id:'native-restored',revision:1,objective:'开发 fixture',phase:'active',activation:'disarmed'});
    await assembled();await assembled();value=await api('/projects/'+registration.id+'/context');
    assert.equal(value.project.objectives.length,3);assert.equal(value.project.objectives[2].native_goal_id,'native-restored');
  }finally{await backend.close();await rm(state,{recursive:true,force:true});}
});
