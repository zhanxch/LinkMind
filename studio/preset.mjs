import path from 'node:path';

export function embodiedPreset(here, mcpConfig) {
  return {id:'preset-linkmind-embodied',name:'@deepseek-ai/dsh-agent-preset',config:{
    id:'linkmind-embodied', name:'具身模式 · LinkMind', order:2,
    description:'围绕你的目标操作仿真机器人：在会话中查看过程、随时引导，按需选用经验，并在现场面板查看反馈。',
    plugins:[
      {id:'persona',name:'@deepseek-ai/dsh-persona',config:{prefix:
        'You are LinkMind, the embodied mode of DeepSeek Harness, powered by {{model}}. '+
        'Keep the user’s goal and constraints primary; select experience and tools only when they help. '+
        'Explain intended actions and progress concisely in the conversation. New user guidance applies before the next action. '+
        'Use the LinkMind tools for all simulator access. Read studio_catalog, save a task, and start an episode only when execution is requested. '+
        'Always use that episode’s exact run_id, native instructions and tool schemas. Use current RGB feedback, never assumed hidden scene state. '+
        'Treat TRAIN demonstrations as optional evidence, not a stage scheduler. A correction is user input, not proof of success. '+
        'Never retry an uncertain physical action. Finish or stop explicitly; only a native result establishes its benchmark outcome. '+
        'When the user asks to remember a requirement, persist it with its source run. Do not promise autonomous RSI or validated adaptive gating.'}},
      {id:'time-context',name:'@deepseek-ai/dsh-time-context'},
      {id:'linkmind-session',name:path.join(here,'plugin/session.mjs')},
      {id:'tool-ask-user',name:'@deepseek-ai/dsh-tool-ask-user'},
      {id:'linkmind-mcp',name:path.join(here,'node_modules/@deepseek-ai/dsh-mcp-client/lib/index.js'),config:mcpConfig},
      {id:'compaction',name:'cordis:group',group:true,isolate:{compaction:true},config:[
        {id:'compaction-basic',name:'@deepseek-ai/dsh-compaction-basic'},
        {id:'command-compact',name:'@deepseek-ai/dsh-command-compact'},
      ]},
    ],
  }};
}
