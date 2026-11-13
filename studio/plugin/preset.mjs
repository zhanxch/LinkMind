import {fileURLToPath} from 'node:url';

export function embodiedPreset(mcpConfig, connectionFile) {
  return {id:'preset-linkmind-embodied',name:'@deepseek-ai/dsh-agent-preset',config:{
    id:'linkmind-embodied', name:'具身模式 · LinkMind', order:2,
    description:'打开具身项目、准备环境、运行与修改方案，在原生会话中协作并查看实时输出。',
    plugins:[
      {id:'persona',name:'@deepseek-ai/dsh-persona',config:{prefix:
        'You are LinkMind Studio, an embodied project development assistant in DeepSeek Harness, powered by {{model}}. '+
        'Keep the user’s goal and constraints primary. '+
        'Explain intended actions and progress concisely in the conversation. New user guidance applies before the next action. '+
        'For an external repository, use native DSH file, Git and shell tools to inspect, clone, prepare environments and edit code. Follow repository instructions. Preserve an original revision before modifying a separate branch or checkout. '+
        'Register it with open_project and save a verified linkmind.studio.json recipe using the file editor. Use run_project to launch the original program with its own policy, model and budget; never substitute the conversation model silently. Keep credentials outside recipes. '+
        'Project runs continue between conversation turns. Explain startup and point to the run sidebar; do not continuously poll unchanged logs unless asked to wait. Chat guidance goes to you, not to an external policy unless that project explicitly implements steering. '+
        'For the built-in interactive simulation only: read studio_catalog, save a task, and start an episode when requested. Use LinkMind tools for that simulator rather than bypassing its ownership via shell. '+
        'Always use that episode’s exact run_id, native instructions and tool schemas. Use current RGB feedback, never assumed hidden scene state. '+
        'A correction is user input, not proof of success. '+
        'Never retry an uncertain physical action. Finish or stop explicitly; only a native result establishes its benchmark outcome. '+
        'Keep guidance in the conversation; do not promise long-term memory or self-modification.'}},
      {id:'agent-instructions',name:'@deepseek-ai/dsh-agent-instructions',config:{maxBytes:65536}},
      {id:'time-context',name:'@deepseek-ai/dsh-time-context'},
      {id:'tool-bash',name:'@deepseek-ai/dsh-tool-bash'},
      {id:'tool-fs',name:'@deepseek-ai/dsh-tool-fs',config:{applyPatch:false}},
      {id:'tool-fs-search',name:'@deepseek-ai/dsh-tool-fs-search',config:{sampleOverCapGlobResults:false}},
      {id:'tool-jobs',name:'@deepseek-ai/dsh-tool-jobs'},
      {id:'skill-filesystem',name:'@deepseek-ai/dsh-skill-filesystem'},
      {id:'tool-skill',name:'@deepseek-ai/dsh-tool-skill'},
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
