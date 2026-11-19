import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyCodexStats,foldCodexStats,usageBuckets,effectiveContext} from '../plugin/codex-telemetry.mjs';
const total=(input,cached,output)=>({inputTokens:input,cachedInputTokens:cached,outputTokens:output});
test('uncached input excludes both cache buckets and never double-counts reasoning',()=>{
 assert.deepEqual(usageBuckets({...total(100,60,20),cacheWriteInputTokens:10,reasoningOutputTokens:12,totalTokens:120}),{inputTokens:30,cacheReadTokens:60,cacheWriteTokens:10,outputTokens:20,reasoningTokens:12,totalTokens:120});
 assert.equal(usageBuckets(total(10,11,2)),null);
 assert.equal(usageBuckets(undefined),null);
 assert.equal(usageBuckets({...total(10,1,2),totalTokens:25}).totalTokens,undefined);
});
test('context capacity follows CLI metadata and overrides; unknown capacity stays unknown',()=>{
 assert.equal(effectiveContext({context_window:272000,effective_context_window_percent:95}),258400);
 assert.equal(effectiveContext({context_window:272000,effective_context_window_percent:95},120000),114000);
 assert.equal(effectiveContext({}),undefined);assert.equal(effectiveContext({context_window:0,effective_context_window_percent:95}),undefined);
});
test('late tool usage, replay, resume and rebase retain exact cumulative accounting',()=>{
 let s=emptyCodexStats();
 const first={threadId:'a',total:total(100,20,30),span:{wallMs:1000,firstDeltaMs:300}};
 s=foldCodexStats(s,first);assert.equal(foldCodexStats(s,first),s);
 s=foldCodexStats(s,{threadId:'a',total:total(220,45,35),span:{wallMs:500,firstDeltaMs:200}});
 assert.equal(s.inputTokens,220);assert.equal(s.outputTokens,35);assert.equal(s.responseMs,1500);
 s=foldCodexStats(JSON.parse(JSON.stringify(s)),{threadId:'a',total:total(350,100,40)});
 s=foldCodexStats(s,{threadId:'b',total:total(80,0,10),span:{wallMs:500,firstDeltaMs:100}});
 assert.equal(s.inputTokens,430);assert.equal(s.outputTokens,50);assert.equal(s.measuredOutputTokens,45);
 assert.equal(s.ttftCount,3);assert.equal(s.responses,4);assert.equal(s.unmeasuredResponses,1);
 assert.equal(foldCodexStats(s,{threadId:'a',total:total(100,0,5)}),s);
});

test('upgrading a previously used thread does not bill its old totals against a new timer',()=>{
 const s=foldCodexStats(emptyCodexStats(),{threadId:'old',previousTotal:total(50000,20000,5000),total:total(51000,20500,5100),span:{wallMs:1000,firstDeltaMs:200}});
 assert.equal(s.inputTokens,1000);assert.equal(s.outputTokens,100);assert.equal(s.measuredOutputTokens,100);
});

test('disk statistics survive restart, avoid duplicate billing, and isolate sessions',async()=>{
 const {mkdtemp,rm,stat}=await import('node:fs/promises');const {tmpdir}=await import('node:os');
 const {CodexStatsStore,readCodexStats,statsPath}=await import('../plugin/codex-stats.mjs');
 const dir=await mkdtemp(tmpdir()+'/codex-stats-');
 const sample={sessionId:'chat-a',threadId:'a',total:total(100,50,20),span:{wallMs:1000,firstDeltaMs:100}};
 try{
  const store=new CodexStatsStore(dir);await store.record(sample);
  await new CodexStatsStore(dir).record(sample);
  const saved=await readCodexStats(dir,'chat-a');assert.equal(saved.inputTokens,100);assert.equal(saved.responses,1);assert.equal(saved.threads,undefined);
  assert.equal(await readCodexStats(dir,'chat-b'),null);
  assert.equal((await stat(statsPath(dir,'chat-a'))).mode&0o777,0o600);
 }finally{await rm(dir,{recursive:true,force:true});}
});
