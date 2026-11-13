import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import * as desktop from '../plugin/desktop-host.mjs';

test('optional model adapter survives Cordis setup and is released with the desktop plugin',async()=>{
  const root=fileURLToPath(new URL('../../',import.meta.url));
  const state=await mkdtemp(path.join(tmpdir(),'linkmind-desktop-host-'));
  const ctx=new Context(), adapters=new Map();
  let registrations=0;
  ctx.provide('webServer',{host:'127.0.0.1',getOrigin:()=> 'http://127.0.0.1:3082',register:()=>()=>{}});
  ctx.provide('connection',{});
  ctx.provide('agentPresets',{register:async()=>()=>{}});
  ctx.provide('attachments',{});
  ctx.provide('llm',{registerAdapter(providers,adapter){
    registrations++;
    for(const provider of providers)adapters.set(provider,adapter);
    return ()=>{for(const provider of providers)adapters.delete(provider);};
  }});
  try {
    await ctx.plugin(desktop,{root,state,codex:true});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(registrations,1);
    assert.equal(adapters.get('linkmind-codex')?.providerInfo('linkmind-codex').id,'linkmind-codex');
    await ctx.fiber.dispose();
    assert.equal(adapters.size,0);
  } finally {await ctx.fiber.dispose();await rm(state,{recursive:true,force:true});}
});
