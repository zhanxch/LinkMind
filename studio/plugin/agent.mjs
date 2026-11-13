import {CodexAdapter} from './codex-provider.mjs';
export const inject = ['llm', 'attachments'];
export function apply(ctx) {
  ctx.effect(() => ctx.llm.registerAdapter(['linkmind-codex'], new CodexAdapter(ctx.attachments, process.cwd())), 'LinkMind native Codex model');
}
