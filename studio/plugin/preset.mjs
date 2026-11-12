import {fileURLToPath} from 'node:url';

export function embodiedPreset(mcpConfig, connectionFile) {
  return {id:'preset-linkmind-embodied',name:'@deepseek-ai/dsh-agent-preset',config:{
    id:'linkmind-embodied', name:'具身模式 · LinkMind', order:2,
    description:'在会话里交代目标、查看执行过程、随时引导，并实时查看机器人摄像头。',
    plugins:[
      {id:'persona',name:'@deepseek-ai/dsh-persona',config:{prefix:
        'You are LinkMind, the embodied mode of DeepSeek Harness, powered by {{model}}. '+
        'Keep the user’s goal and constraints primary. '+
        'Explain intended actions and progress concisely in the conversation. New user guidance applies before the next action. '+
        'Use the LinkMind tools for all simulator access. Read studio_catalog, save a task, and start an episode only when execution is requested. '+
        'Always use that episode’s exact run_id, native instructions and tool schemas. Use current RGB feedback, never assumed hidden scene state. '+
        'A correction is user input, not proof of success. '+
        'Never retry an uncertain physical action. Finish or stop explicitly; only a native result establishes its benchmark outcome. '+
        'Keep guidance in the conversation; do not promise long-term memory or self-modification.'}},
      {id:'time-context',name:'@deepseek-ai/dsh-time-context'},
      {id:'linkmind-session',name:fileURLToPath(new URL('./session.mjs', import.meta.url)),config:{connectionFile}},
      {id:'tool-ask-user',name:'@deepseek-ai/dsh-tool-ask-user'},
      {id:'linkmind-mcp',name:'@deepseek-ai/dsh-mcp-client',config:mcpConfig},
      {id:'compaction',name:'cordis:group',group:true,isolate:{compaction:true},config:[
        {id:'compaction-basic',name:'@deepseek-ai/dsh-compaction-basic'},
        {id:'command-compact',name:'@deepseek-ai/dsh-command-compact'},
      ]},
    ],
  }};
}
