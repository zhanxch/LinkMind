import {CodexStatsStore} from './codex-stats.mjs';
import {CodexAdapter} from './codex-provider.mjs';
import z from '@deepseek-ai/schemastery';
import {appendFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
export const inject = ['llm', 'attachments', 'agents', 'workingDirectory'];
export const Config = z.object({stateDir:z.string().required()});
export async function apply(ctx, config) {
  const stats=new CodexStatsStore(config.stateDir);
  let metrics=Promise.resolve();
  const adapter=new CodexAdapter(ctx.attachments,process.cwd(),{stateDir:config.stateDir,
    onUsage:sample=>stats.record(sample).catch(error=>ctx.logger.warn('Codex usage record: %s',error.message)),
    resolveCwd:async id=>{const agent=ctx.agents.get(id);if(!agent)throw new Error('Codex conversation has no live DSH workspace');return ctx.workingDirectory.ensure(agent);},
    onMetric:value=>{metrics=metrics.then(async()=>{await mkdir(config.stateDir,{recursive:true,mode:0o700});await appendFile(path.join(config.stateDir,'timings.jsonl'),JSON.stringify({...value,at:new Date().toISOString()})+'\n',{mode:0o600});}).catch(error=>ctx.logger.warn('Codex timing record: %s',error.message));},
  });
  ctx.effect(()=>{const unregister=ctx.llm.registerAdapter(['linkmind-codex'],adapter);return()=>{adapter.close();unregister();};},'LinkMind persistent Codex conversations');
  ctx.on('agent/disposed',({agent})=>adapter.close(agent.id));
  ctx.on('agent/status',({agent,status})=>{if(status==='idle'){const s=adapter.conversations.sessions.get(agent.id);if(s?.state==='tool')adapter.close(agent.id);}});
}
