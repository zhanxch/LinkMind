// Provider accounting is independent of DSH tool-step boundaries. Codex may
// report a tool-producing response only AFTER the host returns its result.
export function usageBuckets(value) {
  if (!value || !['inputTokens','outputTokens'].every(k=>Number.isSafeInteger(value[k])&&value[k]>=0)) return null;
  const input=value.inputTokens, read=value.cachedInputTokens??0, write=value.cacheWriteInputTokens??0;
  if (![read,write].every(n=>Number.isSafeInteger(n)&&n>=0)||read+write>input) return null;
  return {inputTokens:input-read-write,cacheReadTokens:read,cacheWriteTokens:write,outputTokens:value.outputTokens,
    ...(Number.isSafeInteger(value.reasoningOutputTokens)?{reasoningTokens:value.reasoningOutputTokens}:{}),
    ...(value.totalTokens===input+value.outputTokens?{totalTokens:value.totalTokens}:{})};
}
export function effectiveContext(model, override) {
  const size=override??model?.context_window, percent=model?.effective_context_window_percent;
  return Number.isSafeInteger(size)&&size>0&&Number.isFinite(percent)&&percent>0&&percent<=100
    ? Math.floor(size*percent/100):undefined;
}
const fields=['inputTokens','outputTokens','cachedInputTokens','cacheWriteInputTokens'];
export const emptyCodexStats=()=>({threads:{},inputTokens:0,outputTokens:0,cachedInputTokens:0,cacheWriteInputTokens:0,
  measuredOutputTokens:0,responseMs:0,ttftMs:0,ttftCount:0,responses:0,unmeasuredResponses:0});
export function foldCodexStats(state, sample) {
  if (!usageBuckets(sample.total)||!sample.threadId) return state;
  const previous=state.threads[sample.threadId]||sample.previousTotal;
  if(previous&&fields.every(k=>(previous[k]??0)===(sample.total[k]??0)))return state;
  // A new/rebased thread starts at zero. A resumed thread retains its counters.
  // Decreasing counters are not invented as negative billing; mark the gap.
  if(previous&&fields.some(k=>(sample.total[k]??0)<(previous[k]??0)))return state;
  const next={...state,threads:{...state.threads,[sample.threadId]:sample.total},responses:state.responses+1};
  for(const field of fields)next[field]+=(sample.total[field]??0)-(previous?.[field]??0);
  const output=(sample.total.outputTokens??0)-(previous?.outputTokens??0);
  if(sample.span?.wallMs>0){next.responseMs+=sample.span.wallMs;next.measuredOutputTokens+=output;
    if(sample.span.firstDeltaMs!==null&&sample.span.firstDeltaMs>=0){next.ttftMs+=sample.span.firstDeltaMs;next.ttftCount++;}
  }else next.unmeasuredResponses++;
  return next;
}
