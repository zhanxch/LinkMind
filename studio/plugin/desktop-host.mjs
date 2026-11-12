import z from '@deepseek-ai/schemastery';
import {apply as proxy} from './index.mjs';
import {startStudio} from './runtime.mjs';
import {embodiedPreset} from './preset.mjs';

export const inject = ['webServer', 'connection', 'agentPresets'];
export const Config = z.object({
  root: z.string().default('').description('LinkMind 项目目录，包含任务资源和仿真配置'),
  python: z.string().default('').description('留空使用项目配置的 Python'),
  state: z.string().default('').description('留空将执行记录保存到 DSH 数据目录'),
  codex: z.boolean().default(false).description('添加本机 Codex 模型，保留当前默认模型'),
});

export async function apply(ctx, config) {
  if (!config.root) {
    ctx.logger.info('LinkMind：请在插件设置中指定项目目录，重新加载后即可选择具身模式。');
    return;
  }
  let backend;
  await ctx.effect(async () => {
    backend = await startStudio(config);
    return () => backend.close();
  }, 'LinkMind service lifetime');
  ctx.provide('linkmindStudio', backend);
  proxy(ctx, backend);
  const mcp = {serverName: 'linkmind', transport: 'stdio', command: backend.python,
    args: ['-m', 'roborag.studio.mcp', '--basic', '--connection', backend.connectionFile], cwd: backend.root,
    env: {PYTHONPATH: backend.pythonPath}, toolCallTimeoutMs: 600000, failOnStartupError: true};
  const preset = embodiedPreset(mcp, backend.connectionFile);
  await ctx.effect(() => ctx.agentPresets.register(preset.config), 'LinkMind embodied mode');
  if (config.codex) {
    const agent = await import('./agent.mjs');
    // A Cordis plugin fiber is not an effect disposer; returning it unloads
    // the nested adapter after registration. Its parent already owns it.
    ctx.inject(['llm', 'attachments'], child => { child.plugin(agent); });
  }
}
