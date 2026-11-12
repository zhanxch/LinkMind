// Bind native dsh conversations to tasks through tool dispatch, not model-supplied IDs.
export const inject = ['tools'];

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

export function apply(ctx) {
  const backend = new URL(process.env.LINKMIND_STUDIO_URL);
  const headers = {Authorization:`Bearer ${process.env.LINKMIND_STUDIO_TOKEN}`, 'Content-Type':'application/json'};
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
    const result = await next();
    if (operation === 'create_task') {
      const task = taskFromResult(result);
      if (task) await post(`/api/tasks/${encodeURIComponent(task.id)}/bind-session`, {session_id:sessionId});
    }
    return result;
  });
}
