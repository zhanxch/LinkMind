// Keep terminal ownership in DSH; only its placement and lower-panel selection belong to Studio.
export function createStudioDock({sidebar, current, sessions, createStore, schedule = queueMicrotask}) {
  const store = createStore({sessionId: '', panel: 'chat', selected: '', terminals: [], error: ''});
  const choices = new Map();
  let queued = false, disposed = false;
  const publish = next => {
    const old = store.getSnapshot();
    if (old.sessionId === next.sessionId && old.panel === next.panel && old.selected === next.selected && old.error === next.error
      && old.terminals.length === next.terminals.length && old.terminals.every((tab, i) => tab.id === next.terminals[i].id && tab.title === next.terminals[i].title)) return;
    store.set(next);
  };
  const eligible = id => !!id && sessions.getSnapshot().byId[id]?.projectionValues?.agentPreset === 'linkmind-embodied';
  const choice = id => choices.get(id) || {panel: 'chat', selected: ''};
  function sync() {
    queued = false;
    if (disposed) return;
    const id = current.getSnapshot().key;
    if (!eligible(id) || sidebar.mounted.getSnapshot() !== id) {
      publish({sessionId: id || '', panel: 'chat', selected: '', terminals: [], error: ''});
      return;
    }
    const terminals = sidebar.tabsIn(id).filter(tab => tab.kind === 'terminal');
    const next = {...choice(id)};
    if (!terminals.some(tab => tab.id === next.selected)) next.selected = terminals.at(-1)?.id || '';
    if (!next.selected) next.panel = 'chat';
    let error = '';
    try {
      // Native floating occurrences retain the same terminal model and Host process.
      // Studio anchors these occurrences in the lower region without mounting a second renderer.
      for (const tab of terminals) sidebar.float(tab.id);
    } catch (cause) { error = '终端面板暂时不可用：' + cause.message; }
    choices.set(id, next);
    publish({sessionId: id, ...next, terminals, error});
  }
  const refresh = () => { if (!queued && !disposed) { queued = true; schedule(sync); } };
  function openTerminal({create = false, tabId} = {}) {
    const id = current.getSnapshot().key;
    if (!eligible(id) || sidebar.mounted.getSnapshot() !== id) return false;
    try {
      const before = sidebar.tabsIn(id).filter(tab => tab.kind === 'terminal');
      let selected = before.find(tab => tab.id === (tabId || choice(id).selected)) || before.at(-1);
      if (create || !selected) {
        sidebar.openTab('terminal');
        selected = sidebar.tabsIn(id).find(tab => tab.kind === 'terminal' && !before.some(old => old.id === tab.id));
      }
      if (!selected) throw new Error('无法创建终端，请重试');
      sidebar.float(selected.id);
      choices.set(id, {panel: 'terminal', selected: selected.id});
      sidebar.focus(selected.id);
      sync();
      return true;
    } catch (cause) {
      store.set({...store.getSnapshot(), error: '无法打开终端：' + cause.message});
      return false;
    }
  }
  function showChat() {
    const id = current.getSnapshot().key;
    choices.set(id, {...choice(id), panel: 'chat'});
    sync();
  }
  function closeTerminal() {
    const state = store.getSnapshot();
    if (state.sessionId !== current.getSnapshot().key || !state.selected) return;
    try { sidebar.close(state.selected); sync(); }
    catch (cause) { store.set({...state, error: '无法关闭终端：' + cause.message}); }
  }
  const releases = [current.subscribe(refresh), sessions.subscribe(refresh), sidebar.mounted.subscribe(refresh), sidebar.openTabs.subscribe(refresh)];
  refresh();
  return {store, openTerminal, showChat, closeTerminal, dispose() { disposed = true; for (const release of releases) release(); }};
}

// Only target current-session native terminal occurrences. Other floating viewers keep DSH placement.
export function terminalDockStyles(frame, state, rect) {
  if (!rect || !state.terminals.length) return '';
  const escape = value => String(value).replace(/[^a-zA-Z0-9_-]/g, char => '\\' + char.codePointAt(0).toString(16) + ' ');
  return state.terminals.map(tab => {
    const selector = `${frame} [data-dockkit-float][data-dockkit-content="${escape(tab.id)}"]`;
    const shown = state.panel === 'terminal' && state.selected === tab.id;
    return `${selector}{display:${shown ? 'flex' : 'none'}!important;position:fixed!important;left:${rect.left}px!important;top:${rect.top + 35}px!important;width:${rect.width}px!important;height:${Math.max(0, rect.height - 35)}px!important;transform:none!important;border-radius:0!important;box-shadow:none!important;background:var(--dsw-alias-bg-base)}
${selector}>div:first-child,${selector}>[data-dockkit-float-resize]{display:none!important}
${frame} [data-dockkit-host="float"]:has(>[data-dockkit-content="${escape(tab.id)}"]){z-index:17!important}`;
  }).join('\n');
}
