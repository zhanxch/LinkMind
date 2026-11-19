import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile, rename} from 'node:fs/promises';
import path from 'node:path';
import {CodexRpc, projectMessages, threadConfig, wireToolName} from './codex-rpc.mjs';

import {usageBuckets} from './codex-telemetry.mjs';

const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
// Reasoning stays in Codex. DSH summaries are display data, not a replacement for it.
const key = message => hash({role:message.role, content:typeof message.content==='string'?message.content:
  message.content.filter(b=>b.type!=='reasoning'), callId:message.source?.callId});
const hostInstructions = 'DSH executes the declared tools under its own workspace and approval policy. Use these tools for actions; do not bypass denied operations. The Codex transport sandbox is read-only, but host tools have their own permissions. Continue in this same conversation after tool results. Explain progress concisely. Prefer independent reads together when a tool supports batching.';

/** Convert actual host results, preserving images, failure status and call correlation. */
export async function toolResponse(message, attachments, signal) {
  const [output] = await projectMessages([message], attachments, signal);
  return {success:!message.isError, contentItems:output.output.map(c=>c.type==='input_image'
    ? {type:'inputImage',imageUrl:c.image_url}: {type:'inputText',text:c.text})};
}

/** One owner per native DSH conversation; auxiliary calls never borrow its thread. */
export class CodexSessions {
  constructor({attachments, stateDir, rpcFactory=config=>new CodexRpc(config), onMetric=()=>{}, onUsage=()=>{}, idleTimeoutMs=60000}={}) {
    this.attachments=attachments; this.stateDir=stateDir; this.rpcFactory=rpcFactory;
    this.onMetric=onMetric;this.onUsage=onUsage; this.sessions=new Map();this.idleTimeoutMs=idleTimeoutMs;
  }
  async *stream(options, cwd) {
    if(!options.sessionId || options.purpose) throw new Error('Persistent Codex requires an ordinary conversation identity');
    let session=this.sessions.get(options.sessionId);
    if(!session){session=new Conversation(this,options.sessionId,cwd);this.sessions.set(options.sessionId,session);}
    yield* session.stream(options,cwd);
  }
  close(sessionId) {
    if(sessionId){this.sessions.get(sessionId)?.close();this.sessions.delete(sessionId);}
    else {for(const session of this.sessions.values())session.close();this.sessions.clear();}
  }
}

class Conversation {
  constructor(owner,id,cwd) {
    this.owner=owner;this.id=id;this.cwd=cwd;this.events=[];this.cursor=[];this.state='new';
    this.busy=false;this.generation=0;this.rpc=null;this.pending=null;this.expected=null;this.usage=null;
    this.file=owner.stateDir?path.join(owner.stateDir,hash(id)+'.json'):null;
  }
  close() {clearTimeout(this.idleTimer);this.generation++;this.rpc?.close();this.rpc=null;this.state='closed';this.wake?.();}
  async save() {
    if(!this.file)return;
    await mkdir(path.dirname(this.file),{recursive:true,mode:0o700});
    const temp=this.file+'.tmp';
    await writeFile(temp,JSON.stringify({version:1,threadId:this.threadId,cwd:this.cwd,signature:this.signature,
      cursor:this.cursor,expected:this.expected,state:this.state,systemHash:this.systemHash,usage:this.usage}),{mode:0o600});
    await rename(temp,this.file);
  }
  async connect() {
    this.events=[];
    const generation=++this.generation;
    this.rpc=this.owner.rpcFactory({cwd:this.cwd,onEvent:event=>{if(generation!==this.generation)return;this.events.push(event);this.wake?.();}});
    await this.rpc.initialize();
  }
  async next(signal) {
    while(!this.events.length){signal?.throwIfAborted();if(!this.rpc)throw new Error('Codex conversation was closed');await new Promise(resolve=>{this.wake=resolve;});this.wake=null;}
    return this.events.shift();
  }
  suffix(messages) {
    if(this.cursor.length>messages.length || this.cursor.some((k,i)=>key(messages[i])!==k))return null;
    const tail=messages.slice(this.cursor.length);
    if(this.expected){
      if(!tail.length || key(tail[0])!==this.expected)return null;
      tail.shift();
    }
    return tail;
  }
  async start(options,system,signature,history) {
    this.close();this.state='new';this.cwd=options.cwd;await this.connect();
    const {thread}=await this.rpc.request('thread/start',{
      model:options.model,ephemeral:false,cwd:this.cwd,environments:[],approvalPolicy:'never',sandbox:'read-only',
      baseInstructions:system||'Follow the user and use the host tools.',developerInstructions:hostInstructions,config:threadConfig,
      dynamicTools:(options.tools||[]).map(t=>({type:'function',name:wireToolName(t.name),description:t.description,inputSchema:t.parameters})),
    });
    this.threadId=thread.id;this.signature=signature;this.systemHash=hash(system);this.cursor=[];this.expected=null;this.pending=null;this.usage=null;this.pendingSpan=null;
    await this.inject(history,options.signal);this.state='idle';
  }
  async inject(messages,signal) {
    if(!messages.length)return;
    const items=await projectMessages(messages,this.owner.attachments,signal);
    if(items.length)await this.rpc.request('thread/inject_items',{threadId:this.threadId,items});
  }
  async *stream(options,cwd) {
    if(this.busy)throw new Error('Concurrent inference on the same Codex conversation is not allowed');
    clearTimeout(this.idleTimer);
    this.busy=true;const began=performance.now();let handedOff=false,finished=false,mode='continue',firstDelta=null,hasCurrentUsage=false;
    const abort=()=>{this.close();};
    options.signal?.addEventListener('abort',abort,{once:true});
    let blocks=new Map(),index=0;
    try {
      options.signal?.throwIfAborted();
      const history=options.messages.filter(m=>m.role!=='system');
      const system=[options.system,...options.messages.filter(m=>m.role==='system').map(m=>typeof m.content==='string'?m.content:m.content.filter(b=>b.type==='text').map(b=>b.text).join('\n'))].filter(Boolean).join('\n\n');
      const signature=hash({cwd,model:options.model,effort:options.reasoningEffort,tools:options.tools});
      // Only a settled thread can be resumed after host restart. An interrupted tool
      // handshake is recovered from DSH's recorded results, never by re-executing it.
      if(this.state==='new'&&this.file){
        let saved;try{saved=JSON.parse(await readFile(this.file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
        if(saved?.version===1&&saved.state==='idle'&&saved.signature===signature&&saved.cwd===cwd){
          Object.assign(this,{cursor:saved.cursor,expected:saved.expected,threadId:saved.threadId,signature,systemHash:saved.systemHash,usage:saved.usage});
          if(this.suffix(history)!==null){
            this.cwd=cwd;await this.connect();
            await this.rpc.request('thread/resume',{threadId:saved.threadId,excludeTurns:true,cwd,model:options.model,approvalPolicy:'never',sandbox:'read-only',config:threadConfig});
            this.state='idle';mode='resume';
          }
        }
      }
      let tail=this.suffix(history);
      if(!this.rpc||signature!==this.signature||tail===null){
        mode=this.threadId?'rebase':'start';
        await this.start({...options,cwd},system,signature,history);tail=[];
      }
      if(this.systemHash!==hash(system)){
        await this.inject([{role:'developer',content:'Updated DSH host instructions (superseding prior host instructions):\n'+system}],options.signal);
        this.systemHash=hash(system);
      }
      // Keep late tool-response accounting separate from the current request.
      if(this.pending){
        const result=tail.find(m=>m.role==='tool'&&m.source?.callId===this.pending.callId);
        if(!result)throw new Error('Missing recorded DSH tool result; refusing to retry the action');
        const extras=tail.filter(m=>m!==result);
        if(extras.some(m=>m.role==='assistant'||m.role==='tool'))throw new Error('Unexpected tool history while resuming Codex');
        // Guidance enters the history before releasing the blocked tool call.
        await this.inject(extras,options.signal);
        const response=await toolResponse(result,this.owner.attachments,options.signal);
        this.rpc.send({id:this.pending.id,result:response});this.pending=null;this.state='running';
      }else{
        await this.inject(tail,options.signal);
        const response=await this.rpc.request('turn/start',{threadId:this.threadId,input:[],effort:options.reasoningEffort,summary:'auto'});
        this.turnId=response.turn?.id;this.state='running';
      }
      this.cursor=history.map(key);this.expected=null;
      await this.save();
      while(true){
        const event=await this.next(options.signal),p=event.params||{};
        if(event.method==='transport/error')throw event.error;
        if(p.threadId&&p.threadId!==this.threadId)continue;
        if(event.method==='turn/started')this.turnId=p.turn.id;
        if(event.method==='thread/tokenUsage/updated'){
          const usage=p.tokenUsage, total=usage.total;
          if(JSON.stringify(total)!==JSON.stringify(this.usage)) {
            const delayed=!!this.pendingSpan;
            await this.owner.onUsage({sessionId:this.id,threadId:this.threadId,model:options.model,total,previousTotal:this.usage,
              contextWindow:usage.modelContextWindow,
              span:this.pendingSpan||{wallMs:performance.now()-began,firstDeltaMs:firstDelta}});
            this.pendingSpan=null;
            // DSH's meter expects ONE current prompt, not cumulative billing.
            // Late preceding-tool usage is retained in the durable Codex stats.
            if(!delayed){const current=usageBuckets(usage.last);if(current){yield {type:'usage',usage:current};hasCurrentUsage=true;}}
          }
          this.usage=total;
        }else if(event.method==='item/agentMessage/delta'||event.method==='item/reasoning/summaryTextDelta'){
          firstDelta??=performance.now()-began;
          const type=event.method==='item/agentMessage/delta'?'text':'reasoning', k=p.itemId+':'+type;
          if(!blocks.has(k)){blocks.set(k,{index:index++,type,text:''});yield {type:'block-start',index:blocks.get(k).index,blockType:type};}
          const b=blocks.get(k);b.text+=p.delta;yield {type:type+'-delta',index:b.index,text:p.delta};
        }else if(event.method==='item/tool/call'&&event.id!==undefined){
          firstDelta??=performance.now()-began;
          const declared=(options.tools||[]).find(t=>wireToolName(t.name)===p.tool);
          if(!declared)throw new Error('Undeclared Codex tool: '+p.tool);
          const content=[];
          for(const b of blocks.values()){const block={type:b.type,text:b.text};content.push(block);yield {type:'block-end',index:b.index,block};}
          const block={type:'tool-call',id:p.callId,name:declared.name,arguments:JSON.stringify(p.arguments)};content.push(block);
          yield {type:'block-start',index,blockType:'tool-call'};
          yield {type:'tool-call-delta',index,id:p.callId,name:declared.name,argumentsDelta:block.arguments};
          yield {type:'block-end',index,block};
          this.expected=key({role:'assistant',content});this.pending={id:event.id,callId:p.callId};this.state='tool';
          if(!hasCurrentUsage)this.pendingSpan??={wallMs:performance.now()-began,firstDeltaMs:firstDelta};
          await this.save();handedOff=true;
          yield {type:'finish',reason:{kind:'tool-calls'}};return;
        }else if(event.id!==undefined&&event.method){
          this.rpc.send({id:event.id,error:{code:-32601,message:'This action is not exposed by the DSH host'}});
        }else if(event.method==='error'&&!p.willRetry){throw new Error(p.error?.message||'Codex inference failed');
        }else if(event.method==='turn/completed'){
          if(p.turn.status!=='completed')throw new Error(p.turn.error?.message||'Codex turn '+p.turn.status);
          const content=[];for(const b of blocks.values()){const block={type:b.type,text:b.text};content.push(block);yield {type:'block-end',index:b.index,block};}
          this.expected=key({role:'assistant',content});this.state='idle';await this.save();finished=true;
          yield {type:'finish',reason:{kind:'stop'}};return;
        }
      }
    }finally{
      options.signal?.removeEventListener('abort',abort);this.busy=false;
      if(!handedOff&&!finished)this.close();
      if(finished&&this.owner.idleTimeoutMs>0){
        this.idleTimer=setTimeout(()=>this.owner.close(this.id),this.owner.idleTimeoutMs);this.idleTimer.unref?.();
      }
      this.owner.onMetric({sessionId:this.id,threadId:this.threadId,mode,state:this.state,firstDeltaMs:firstDelta,wallMs:performance.now()-began});
    }
  }
}
