import {CodexRpc, codexStream} from './codex-rpc.mjs';
import {LlmAdapter} from '@deepseek-ai/dsh-llm';

export class CodexAdapter extends LlmAdapter {
  constructor(attachments, cwd) { super(); this.attachments = attachments; this.cwd = cwd; }
  providerInfo(provider) { return {id: provider, name: 'Codex · 本机登录'}; }
  async catalog() {
    if (!this.models) this.models = (async () => {
      const rpc = new CodexRpc({cwd: this.cwd});
      try {
        await rpc.initialize();
        const account = await rpc.request('account/read', {refreshToken: false});
        if (!account.account) throw new Error('Run codex login in a terminal before selecting this provider.');
        const response = await rpc.request('model/list', {});
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
      reasoning: {defaultEffort:m.defaultReasoningEffort,
        efforts:m.supportedReasoningEfforts.map(e => ({id:e.reasoningEffort, name:e.reasoningEffort, description:e.description}))}};
  }
  async *stream(options) {
    const model = await this.model(options.model);
    yield* codexStream({...options, model:model.model}, this.attachments, {cwd:this.cwd});
  }
}
