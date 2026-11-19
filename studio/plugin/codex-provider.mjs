import {CodexRpc, codexStream} from './codex-rpc.mjs';
import {CodexSessions} from './codex-session.mjs';
import {readFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import path from 'node:path';
import {effectiveContext} from './codex-telemetry.mjs';
import {LlmAdapter} from '@deepseek-ai/dsh-llm';

export class CodexAdapter extends LlmAdapter {
  constructor(attachments, cwd, {stateDir, resolveCwd=async()=>cwd, onMetric, onUsage}={}) {
    super(); this.attachments=attachments;this.cwd=cwd;this.resolveCwd=resolveCwd;
    this.contextWindows=new Map();
    const report=sample=>{if(Number.isSafeInteger(sample.contextWindow)&&sample.contextWindow>0)this.contextWindows.set(sample.model,sample.contextWindow);return onUsage?.(sample);};
    this.conversations=new CodexSessions({attachments,stateDir,onMetric,onUsage:report});
  }
  close(sessionId) {this.conversations.close(sessionId);}
  providerInfo(provider) { return {id: provider, name: 'Codex · 本机登录'}; }
  async catalog() {
    if (!this.models) this.models = (async () => {
      const rpc = new CodexRpc({cwd: this.cwd});
      try {
        await rpc.initialize();
        const account = await rpc.request('account/read', {refreshToken: false});
        if (!account.account) throw new Error('Run codex login in a terminal before selecting this provider.');
        const response = await rpc.request('model/list', {});
        // model/list does not expose capacity. Read only the CLI's model metadata
        // cache and explicit capacity override; never authentication files.
        const {config}=await rpc.request('config/read',{includeLayers:false});
        try {
          const cache=JSON.parse(await readFile(path.join(process.env.CODEX_HOME||path.join(homedir(),'.codex'),'models_cache.json'),'utf8'));
          for(const model of cache.models||[]){const size=effectiveContext(model,config.model_context_window);if(size)this.contextWindows.set(model.slug,size);}
        }catch(error){if(!['ENOENT','EACCES'].includes(error.code)&&!(error instanceof SyntaxError))throw error;}

        return response.data.filter(m => !m.hidden);
      } finally { rpc.close(); }
    })().catch(error => { this.models = null; throw error; });
    return this.models;
  }
  async model(id) {
    const models = await this.catalog();
    const model = id === 'codex-default' ? models.find(m => m.isDefault) || models[0] : models.find(m => m.model === id);
    if (!model) throw new Error(`Model not available in the native Codex catalog: ${id}`);
    return model;
  }
  async listModels(provider) {
    return [{provider, id:'codex-default', name:'Codex · 默认模型', inputModalities:['text','image']},
      ...(await this.catalog()).map(m => ({provider, id:m.model, name:m.displayName, description:m.description, inputModalities:m.inputModalities}))];
  }
  async resolveModel(provider, id) {
    const m = await this.model(id);
    return {provider, id, name:m.displayName, inputModalities:m.inputModalities,
      ...(this.contextWindows.has(m.model)?{context:{contextWindow:this.contextWindows.get(m.model)}}:{}),
      reasoning: {defaultEffort:m.defaultReasoningEffort,
        efforts:m.supportedReasoningEfforts.map(e => ({id:e.reasoningEffort, name:e.reasoningEffort, description:e.description}))}};
  }
  async *stream(options) {
    const model = await this.model(options.model);
    const resolved={...options,model:model.model};
    if(options.sessionId&&!options.purpose)yield* this.conversations.stream(resolved,await this.resolveCwd(options.sessionId));
    else yield* codexStream(resolved,this.attachments,{cwd:this.cwd});
  }
}
