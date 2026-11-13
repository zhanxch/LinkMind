// Bind native dsh conversations to tasks through tool dispatch, not model-supplied IDs.
import {readFile} from 'node:fs/promises';
import z from '@deepseek-ai/schemastery';
export const inject = ['tools'];
export const Config = z.object({connectionFile:z.string().default('')});

export function taskFromResult(result) {
  if (result.isError) return null;
  const value = result.value;
  if (value?.structuredContent?.id) return value.structuredContent;
  for (const block of value?.content || []) {
    if (block.type !== 'text') continue;
    try { const task = JSON.parse(block.text); if (task?.id) return task; } catch {}
  }
  throw new Error('Task was saved but its identity could not be linked to this conversation. Do not start it.');
}

export async function apply(ctx, config = {}) {
  const connection = config.connectionFile ? JSON.parse(await readFile(config.connectionFile,'utf8')) :
    ctx.get?.('linkmindStudio') || {url:process.env.LINKMIND_STUDIO_URL,token:process.env.LINKMIND_STUDIO_TOKEN};
  const backend = new URL(connection.url);
  const headers = {Authorization:`Bearer ${connection.token}`, 'Content-Type':'application/json'};
  const post = async (path, data) => {
    const response = await fetch(new URL(path,backend), {method:'POST',headers,body:JSON.stringify(data),signal:AbortSignal.timeout(10000)});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || 'Conversation assignment failed');
    return value;
  };
  ctx.on('tools/execute', async (exec, next) => {
    if (!exec.name.startsWith('mcp__linkmind__')) return next();
    const sessionId = exec.agent?.id;
    if (!sessionId) throw new Error('LinkMind requires a native dsh conversation');
    const operation = exec.name.slice('mcp__linkmind__'.length);
    const args = exec.arguments || {};
    if (['start_episode','remember_requirement','robot_call','finish_episode','stop_episode'].includes(operation)) {
      await post('/api/session/check', {session_id:sessionId, task_id:args.task_id, run_id:args.run_id});
    }
    if (['inspect_project','run_project','follow_project_run','stop_project_run'].includes(operation)) {
      await post('/api/projects/check', {session_id:sessionId, project_id:args.project_id, run_id:args.run_id});
    }
    if (operation === 'compare_project_runs') {
      for (const run_id of [args.left_run_id,args.right_run_id]) await post('/api/projects/check', {session_id:sessionId,run_id});
    }
    const result = await next();
    if (operation === 'create_task') {
      const task = taskFromResult(result);
      if (task) await post(`/api/tasks/${encodeURIComponent(task.id)}/bind-session`, {session_id:sessionId});
    }
    if (operation === 'open_project') {
      const project = taskFromResult(result);
      if (project) await post(`/api/projects/${encodeURIComponent(project.id)}/bind-session`, {session_id:sessionId});
    }
    return result;
  });
}
