import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {createHash} from 'node:crypto';

// Codex reserves its own MCP/builtin names. Keep the dsh name in durable
// history and translate it consistently on both declarations and replay.
export function wireToolName(name) {
  return `dsh_${createHash('sha256').update(name).digest('hex').slice(0,12)}_${name.replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,44)}`;
}

// Native CLI owns authentication. This transport never reads or copies credentials.
export class CodexRpc {
  constructor({command = 'codex', cwd, onEvent = () => {}} = {}) {
    this.nextId = 1;
    this.pending = new Map();
    this.onEvent = onEvent;
    this.child = spawn(command, ['app-server', '--stdio', '-c', 'mcp_servers={}', '-c', 'features.plugins=false'],
      {cwd, stdio: ['pipe', 'pipe', 'pipe']});
    this.child.stderr.on('data', () => {}); // CLI diagnostics can contain local configuration paths.
    this.lines = createInterface({input: this.child.stdout});
    this.lines.on('line', line => {
      let event;
      try { event = JSON.parse(line); } catch { return; }
      if (event.id !== undefined && !event.method) {
        const pending = this.pending.get(event.id);
        if (!pending) return;
        this.pending.delete(event.id);
        clearTimeout(pending.timer);
        event.error ? pending.reject(new Error(event.error.message)) : pending.resolve(event.result);
      } else this.onEvent(event);
    });
    this.child.on('error', error => this.fail(error));
    this.child.on('exit', code => this.fail(new Error(`Codex app-server exited (${code})`)));
  }
  fail(error) {
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(error); }
    this.pending.clear();
    this.onEvent({method: 'transport/error', error});
  }
  send(message) { if (this.child.stdin.writable) this.child.stdin.write(JSON.stringify(message) + '\n'); }
  request(method, params, timeout = 45000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`Codex ${method} timed out`)); }, timeout);
      this.pending.set(id, {resolve, reject, timer});
      this.send({id, method, params});
    });
  }
  async initialize() {
    await this.request('initialize', {clientInfo: {name: 'linkmind_dsh', title: 'LinkMind', version: '0.1.0'},
      capabilities: {experimentalApi: true}});
    this.send({method: 'initialized', params: {}});
  }
  close() { this.child.kill('SIGTERM'); this.lines.close(); }
}

export const threadConfig = {
  'web_search': 'disabled', 'features.shell_tool': false, 'features.unified_exec': false,
  'features.plugins': false, 'features.multi_agent': false, 'features.skill_search': false,
  'features.skip_host_skill_discovery': true,
};

// Native dsh logs remain the source of history. Each provider call reconstructs
// that history in an ephemeral Codex thread; Codex never executes dsh's tools.
export async function projectMessages(messages, attachments, signal) {
  const items = [];
  for (const message of messages) {
    const blocks = typeof message.content === 'string' ? [{type: 'text', text: message.content}] : message.content;
    const content = [];
    for (const block of blocks || []) {
      if (block.type === 'text') content.push({type: message.role === 'assistant' ? 'output_text' : 'input_text', text: block.text});
      else if (block.type === 'image') {
        if (block.offloaded) content.push({type: 'input_text', text: '[Earlier image offloaded by dsh]'});
        else {
          const image = await attachments.readImage(block.attachment, signal);
          content.push({type: 'input_image', image_url: `data:${image.ref.mediaType};base64,${Buffer.from(image.data).toString('base64')}`});
        }
      } else if (block.type === 'tool-call') {
        if (content.length) items.push({type: 'message', role: message.role, content: content.splice(0)});
        items.push({type: 'function_call', call_id: block.id, name: wireToolName(block.name), arguments: block.arguments});
      } else if (block.type !== 'reasoning') {
        throw new Error(`Codex adapter cannot project content block ${block.type}`);
      }
    }
    if (message.role === 'tool') items.push({type: 'function_call_output', call_id: message.source.callId, output: content});
    else if (content.length) items.push({type: 'message', role: message.role, content});
  }
  return items;
}

export async function* codexStream(options, attachments, {cwd, rpcFactory = config => new CodexRpc(config)} = {}) {
  const events = [];
  let wake, stopped = false;
  const rpc = rpcFactory({cwd, onEvent: event => { events.push(event); wake?.(); }});
  const abort = () => { stopped = true; rpc.close(); wake?.(); };
  options.signal?.addEventListener('abort', abort, {once: true});
  let index = 0;
  const blocks = new Map();
  try {
    options.signal?.throwIfAborted();
    await rpc.initialize();
    const projected = await projectMessages(options.messages, attachments, options.signal);
    const system = [options.system, ...projected.filter(x => x.type === 'message' && x.role === 'system').map(x => x.content.map(c => c.text).join('\n'))].filter(Boolean).join('\n\n');
    const {thread} = await rpc.request('thread/start', {
      model: options.model, ephemeral: true, cwd, environments: [], approvalPolicy: 'never', sandbox: 'read-only',
      baseInstructions: system || 'Follow the conversation and use only the tools declared by the host.',
      developerInstructions: 'The host owns execution. Use the provided dynamic tools for every action. Explain progress concisely. Do not use undeclared tools.',
      config: threadConfig,
      dynamicTools: (options.tools || []).map(t => ({type: 'function', name: wireToolName(t.name), description: t.description, inputSchema: t.parameters})),
    });
    const history = projected.filter(x => !(x.type === 'message' && x.role === 'system'));
    // Use native role/tool/image items, never flatten history into user prose.
    await rpc.request('thread/inject_items', {threadId: thread.id, items: history});
    await rpc.request('turn/start', {threadId: thread.id, input: [], effort: options.reasoningEffort, summary: 'auto'});
    while (!stopped) {
      if (!events.length) await new Promise(resolve => { wake = resolve; });
      wake = null;
      while (events.length) {
        const event = events.shift(), p = event.params || {};
        if (event.method === 'transport/error') throw event.error;
        if (p.threadId && p.threadId !== thread.id) continue;
        if (event.method === 'item/agentMessage/delta' || event.method === 'item/reasoning/summaryTextDelta') {
          const type = event.method === 'item/agentMessage/delta' ? 'text' : 'reasoning';
          const key = `${p.itemId}:${type}`;
          if (!blocks.has(key)) {
            blocks.set(key, {index: index++, type, text: ''});
            yield {type: 'block-start', index: blocks.get(key).index, blockType: type};
          }
          const b = blocks.get(key); b.text += p.delta;
          yield {type: `${type}-delta`, index: b.index, text: p.delta};
        } else if (event.method === 'item/tool/call' && event.id !== undefined) {
          const declared = (options.tools || []).find(t => wireToolName(t.name) === p.tool);
          if (!declared) throw new Error(`Undeclared Codex tool: ${p.tool}`);
          for (const b of blocks.values()) yield {type: 'block-end', index: b.index, block: {type: b.type, text: b.text}};
          const block = {type: 'tool-call', id: p.callId, name: declared.name, arguments: JSON.stringify(p.arguments)};
          yield {type: 'block-start', index, blockType: 'tool-call'};
          yield {type: 'tool-call-delta', index, id: p.callId, name: declared.name, argumentsDelta: block.arguments};
          yield {type: 'block-end', index, block};
          // The outstanding RPC is intentionally not answered: dsh executes
          // the recorded call once, after this provider process has stopped.
          rpc.close();
          yield {type: 'finish', reason: {kind: 'tool-calls'}};
          return;
        } else if (event.id !== undefined && event.method) {
          rpc.send({id: event.id, error: {code: -32601, message: 'This action is not exposed by the dsh host'}});
        } else if (event.method === 'error' && !p.willRetry) {
          throw new Error(p.error?.message || 'Codex inference failed');
        } else if (event.method === 'turn/completed') {
          if (p.turn.status !== 'completed') throw new Error(p.turn.error?.message || `Codex turn ${p.turn.status}`);
          for (const b of blocks.values()) yield {type: 'block-end', index: b.index, block: {type: b.type, text: b.text}};
          yield {type: 'finish', reason: {kind: 'stop'}};
          return;
        }
      }
    }
    options.signal?.throwIfAborted();
  } finally { options.signal?.removeEventListener('abort', abort); rpc.close(); }
}
