import {CodexSessions} from '../plugin/codex-session.mjs';
import {codexStream} from '../plugin/codex-rpc.mjs';
import {tmpdir} from 'node:os';
const results=[];
for(const variant of ['before','after']){
  const metrics=[],sessions=new CodexSessions({onMetric:m=>metrics.push(m)});
  const options={sessionId:'benchmark-'+variant,model:process.env.LINKMIND_BENCHMARK_MODEL||'gpt-6-astra',reasoningEffort:'xhigh',
    system:'You are running a bounded fixture test. Use read_fixture to follow the linked records until next is null. Do not guess records or use other tools. Return the four values in order. No extra planning is necessary.',
    messages:[{role:'user',content:'Read record a, follow next until the end, return the collected values.'}],
    tools:[{name:'read_fixture',description:'Read exactly one record in a linked list.',parameters:{type:'object',properties:{id:{type:'string'}},required:['id'],additionalProperties:false}}],
    signal:AbortSignal.timeout(240000)};
  const data={a:{value:17,next:'b'},b:{value:53,next:'c'},c:{value:29,next:'d'},d:{value:91,next:null}};
  const started=performance.now(), steps=[];
  try{
    for(let i=0;i<8;i++){
      const began=performance.now(),blocks=[];let first=null;
      for await(const chunk of variant==='before'?codexStream(options,null,{cwd:tmpdir()}):sessions.stream(options,tmpdir())){
        if(chunk.type.endsWith('-delta'))first??=performance.now()-began;
        if(chunk.type==='block-end')blocks.push(chunk.block);
      }
      steps.push({ms:performance.now()-began,firstDeltaMs:first});
      options.messages.push({role:'assistant',content:blocks});
      const calls=blocks.filter(b=>b.type==='tool-call');
      if(!calls.length)break;
      for(const call of calls){
        const {id}=JSON.parse(call.arguments);if(!data[id])throw Error('Unknown fixture');
        options.messages.push({role:'tool',source:{callId:call.id},content:[{type:'text',text:JSON.stringify(data[id])}]});
      }
    }
    const result={variant,ms:performance.now()-started,steps,metrics:metrics.map(({threadId,sessionId,...timing})=>timing),answer:options.messages.at(-1).content.filter(b=>b.type==='text').map(b=>b.text).join('\n')};
    results.push(result);console.log(JSON.stringify(result));
  }catch(error){results.push({variant,error:error.message});console.log(variant,error.message);}
  finally{sessions.close();}
}
if(results.some(r=>r.error))process.exitCode=1;
