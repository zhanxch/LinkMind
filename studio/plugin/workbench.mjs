import {createRSIViews} from './rsi-views.mjs?v=0.12.0';
import {studioStyles,studioFrame,createStudioChrome} from './studio-shell.mjs?v=0.12.0';
import {createStudioDock,terminalDockStyles} from './studio-dock.mjs?v=0.12.0';
import {overviewStyles,createOverview} from './studio-overview.mjs?v=0.8.0';
// Presentation-only extension for DSH 0.2.2-rc.2. Native conversations and dock tabs keep their owners.
export function installWorkbench(ctx, React, ui, api, createSnapshotStore) {
  const h=React.createElement, {Button,IconFolderCloseRegular,IconFolderOpenRegular}=ui;
  const current=ctx.uiSession.adapter.current;
  const readPreference=()=>{try{return JSON.parse(localStorage.getItem('linkmind.workbench')||'{}');}catch{return {};}};
  const saved=readPreference();
  const prefs=createSnapshotStore({stacked:saved.stacked!==false,split:Math.min(75,Math.max(25,Number(saved.split)||57)),explorer:Math.min(420,Math.max(210,Number(saved.explorer)||260))});
  const setPreference=patch=>{prefs.set({...prefs.getSnapshot(),...patch});try{localStorage.setItem('linkmind.workbench',JSON.stringify(prefs.getSnapshot()));}catch{/* Layout remains usable without browser storage. */}};
  const currentId=()=>current.getSnapshot().key;
  const dock=createStudioDock({sidebar:ctx.sidebarRight,current,sessions:ctx.sessions.list,createStore:createSnapshotStore});
  ctx.effect(()=>()=>dock.dispose(),'LinkMind lower panel');
  const openPage=kind=>kind==='terminal'&&ctx.sessions.list.getSnapshot().byId[currentId()]?.projectionValues?.agentPreset==='linkmind-embodied'?dock.openTerminal():ctx.sidebarRight.openTab(kind);
  const chatAddress=id=>'dsh-resource://linkmindchat/session/'+encodeURIComponent(id);
  const parseChat=address=>{try{const url=new URL(address);return url.hostname==='linkmindchat'&&url.pathname.startsWith('/session/')?decodeURIComponent(url.pathname.slice(9)):null;}catch{return null;}};
  const openChat=id=>ctx.sidebarRight.openResource(chatAddress(id));
  const requestExplorer=action=>window.dispatchEvent(new CustomEvent('linkmind:explorer',{detail:action}));
  const bindings=()=>({hooks:{current,prefs,dock:dock.store},openPage,setPreference,openSession:id=>ctx.uiWorkspace.openSession(id),toggleSidebar:()=>ctx.layout.toggleSidebar(),openSettings:()=>ctx.layout.selectPanel('plugins'),requestExplorer,showChat:dock.showChat,openTerminal:dock.openTerminal,closeTerminal:dock.closeTerminal});
  const StudioChrome=createStudioChrome(React,ui), Overview=createOverview(React,ui,api);
  const css=`
.lm-library{font-size:13px;min-width:0;padding:4px 8px 12px}.lm-tools{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin:8px 0}.lm-tools strong{font-weight:500;margin-right:auto}.lm-library input,.lm-library select{box-sizing:border-box;min-width:0;width:100%;font:inherit;color:inherit;background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l3);border-radius:6px;padding:6px 8px}.lm-tree{margin:8px 0}.lm-tree-row{display:flex;align-items:center;min-height:32px;gap:4px;border-radius:6px;min-width:0}.lm-tree-row:hover,.lm-tree-row[data-selected=true]{background:var(--dsw-alias-bg-hover)}.lm-tree-row[data-current=true]{box-shadow:inset 2px 0 var(--dsw-alias-brand-primary,#587bc1)}.lm-row-main{display:flex;align-items:center;gap:6px;min-width:0;flex:1;background:none;border:0;color:inherit;text-align:left;padding:6px 4px;cursor:pointer;font:inherit}.lm-row-main span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lm-tree-row svg{flex-shrink:0}.lm-row-action{opacity:0}.lm-tree-row:hover .lm-row-action,.lm-tree-row:focus-within .lm-row-action,.lm-tree-row[data-selected=true] .lm-row-action,.lm-row-actions{opacity:1}.lm-editor{display:flex;flex-direction:column;gap:8px;padding:10px 4px;border-top:1px solid var(--dsw-alias-border-l3)}.lm-explorer-heading{display:flex;align-items:center;gap:2px;padding:8px 0}.lm-explorer-heading strong{font-size:12px;flex:1;font-weight:500}.lm-row-actions{display:flex;gap:0;flex-shrink:0;opacity:0}.lm-tree-row:hover .lm-row-actions,.lm-tree-row:focus-within .lm-row-actions,.lm-tree-row[data-selected=true] .lm-row-actions{opacity:1}.lm-row-actions button,.lm-tree-chevron{padding:3px!important;min-width:22px!important}.lm-tree-row{border-radius:4px;gap:0}.lm-tree-group{position:relative}.lm-location{font-size:11px;color:var(--dsw-alias-label-secondary);display:flex;gap:4px;align-items:center;margin:8px 2px;overflow-wrap:anywhere}.lm-location button{border:0;background:none;color:inherit;margin-left:auto;cursor:pointer}.lm-inline-edit{display:flex;min-width:0;flex:1;gap:2px;align-items:center}.lm-inline-edit input{padding:4px!important}.lm-empty-create{border:0;background:none;color:var(--dsw-alias-label-secondary);font:inherit;font-size:11px;line-height:1.8;text-align:left;padding:6px;cursor:pointer}.lm-project-row{margin-top:8px;font-weight:500}.lm-root-chats{border-top:1px solid var(--dsw-alias-border-l3);margin-top:6px;padding-top:6px}.lm-running{color:var(--dsw-alias-brand-primary)}.lm-small{font-size:12px;line-height:1.6;color:var(--dsw-alias-label-secondary)}.lm-library p{margin:8px 4px}.lm-error{font-size:12px;overflow-wrap:anywhere}.lm-chat-view{height:100%;min-height:0;display:flex;flex-direction:column}.lm-chat-view>[data-slot]{min-height:0}.lm-chat-bar{display:flex;gap:8px;align-items:center;padding:6px 12px;border-bottom:1px solid var(--dsw-alias-border-l3);font-size:12px}.lm-chat-view [data-composer-seat]{display:none}.lm-embedded-body{flex:1;min-height:0;overflow:hidden}.lm-grip{display:none}.lm-view-home{padding:20px;display:flex;flex-direction:column;gap:14px;font-size:13px;min-width:0;overflow:auto;height:100%;box-sizing:border-box}.lm-view-home h2{font-size:18px;font-weight:500;margin:0}.lm-view-actions{display:flex;gap:8px;flex-wrap:wrap}.lm-view-home ul{padding-left:20px;line-height:1.8}.lm-process-grid{flex:1;min-height:180px;overflow:hidden;display:grid;grid-template-columns:minmax(220px,1.1fr) minmax(220px,1fr);gap:16px;align-items:stretch}.lm-process-events{display:flex;flex-direction:column;gap:10px;max-height:48vh;overflow:auto;overscroll-behavior:contain}.lm-process-event{border-left:2px solid var(--dsw-alias-border-l3);padding:4px 10px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65;font-size:12px}.lm-control{min-width:0;min-height:0;display:flex;flex-direction:column;gap:8px}.lm-control-heading{display:flex;align-items:center;gap:12px}.lm-run-extras{display:flex;gap:8px 20px;flex-wrap:wrap;font-size:12px}.lm-run-extras>details[open]{flex-basis:100%}.lm-control-feed{flex:1;min-height:80px;overflow:auto;overscroll-behavior:contain;display:flex;flex-direction:column;gap:18px;padding:10px 8px 14px 0}.lm-control-message{font-size:13px}.lm-control-message[data-role=user]{padding:8px;background:var(--dsw-alias-bg-hover);border-radius:8px}.lm-control-tool{font-size:12px;color:var(--dsw-alias-label-secondary);min-width:0}.lm-control-tool>summary{cursor:pointer;overflow-wrap:anywhere;line-height:1.6}.lm-tool-command{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:monospace}.lm-tool-body{padding:10px 12px;border-left:2px solid var(--dsw-alias-border-l3);margin-top:8px}.lm-tool-payload{font:12px/1.6 monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;color:var(--dsw-alias-label-primary);margin:6px 0 14px}.lm-run-panel{container-type:inline-size;box-sizing:border-box}.lm-run-panel>label,.lm-run-panel>div:not(.lm-process-grid),.lm-run-panel>details,.lm-run-panel>p{flex-shrink:0}.lm-process-grid>section[aria-label="摄像头"]{min-height:0;overflow:auto}.lm-process-grid figure{display:flex;flex-direction:column;height:100%;min-height:0}.lm-process-grid img{flex:1;min-height:0;height:100%;max-height:none!important;aspect-ratio:auto!important}.lm-process-grid figcaption{flex-shrink:0}@container (max-width:600px){.lm-process-grid{grid-template-columns:1fr;overflow:auto;flex:none}.lm-control-feed{max-height:220px;flex:none}.lm-process-events{max-height:240px}}
`;
  function Marker(props) {
    const {useCurrent,usePrefs,useSessions,useDock,setPreference}=props;
    const id=useCurrent(s=>s.key), p=usePrefs(s=>s), embodied=useSessions(s=>s.byId[id]?.projectionValues?.agentPreset==='linkmind-embodied'), dockState=useDock(s=>s);
    const marker=React.useRef(null),[rect,setRect]=React.useState(null);
    React.useLayoutEffect(()=>{
      const frame=marker.current?.closest('[data-slot="root"]')?.firstElementChild;
      const center=frame?.querySelector('[data-slot="main"]')?.parentElement?.parentElement;
      if(!frame||!center)return;
      const measure=()=>{const r=center.getBoundingClientRect();const next={left:r.left,top:r.top,width:r.width,height:r.height};setRect(old=>old&&Object.keys(next).every(k=>old[k]===next[k])?old:next);};
      const observer=new ResizeObserver(measure);observer.observe(frame);observer.observe(center);measure();
      window.addEventListener('resize',measure);return()=>{observer.disconnect();window.removeEventListener('resize',measure);};
    },[id,embodied,p.split,p.explorer]);
    React.useEffect(()=>{
      if(!embodied||!p.stacked)return;
      const shortcut=e=>{if(e.ctrlKey&&!e.metaKey&&!e.altKey&&!e.shiftKey&&e.code==='Backquote'&&!document.querySelector('[role="dialog"]')){e.preventDefault();e.stopImmediatePropagation();if(dock.store.getSnapshot().panel==='terminal')dock.showChat();else dock.openTerminal();}};
      window.addEventListener('keydown',shortcut,true);return()=>window.removeEventListener('keydown',shortcut,true);
    },[embodied,p.stacked]);
    return h(React.Fragment,null,h('span',{ref:marker,hidden:true,className:'lm-layout-marker','data-stacked':String(p.stacked&&embodied),'data-dock':dockState.sessionId===id?dockState.panel:'chat'}),h('style',null,css+studioStyles+overviewStyles+`[data-slot="root"]>div{--lm-upper:${p.split}%;--lm-explorer:${p.explorer}px}`+terminalDockStyles(studioFrame,dockState,rect)),h(Grip,{usePrefs,setPreference}),h(StudioChrome,{...props,dockRect:rect}));
  }
  function Grip({usePrefs,setPreference}) {
    const p=usePrefs(s=>s), dragging=React.useRef(false);
    const move=e=>{if(!dragging.current)return;const frame=e.currentTarget.closest('[data-slot="root"]')?.firstElementChild;if(!frame)return;const rect=frame.getBoundingClientRect();setPreference({split:Math.max(25,Math.min(75,100*(e.clientY-rect.top-44)/rect.height))});};
    return h('div',{className:'lm-grip',role:'separator',tabIndex:0,'aria-label':'调整查看区和对话区高度','aria-orientation':'horizontal','aria-valuenow':Math.round(p.split),'aria-valuemin':25,'aria-valuemax':75,
      onPointerDown:e=>{dragging.current=true;e.currentTarget.setPointerCapture(e.pointerId);},onPointerMove:move,onPointerUp:e=>{move(e);dragging.current=false;e.currentTarget.releasePointerCapture(e.pointerId);},onPointerCancel:()=>{dragging.current=false;},onLostPointerCapture:()=>{dragging.current=false;},onKeyDown:e=>{if(['ArrowUp','ArrowDown','Home'].includes(e.key)){e.preventDefault();setPreference({split:e.key==='Home'?57:Math.max(25,Math.min(75,p.split+(e.key==='ArrowUp'?-5:5)))});}}});
  }
  function Library({wide,useSessions,useWorkspaces,useCurrent,usePrefs,openSession,openChat,openPage,createSession,renameSession,archiveSession,restoreSession,createWorkspace,pickDirectory,setPreference}) {
    const list=useSessions(s=>s), workspaceState=useWorkspaces(s=>s), currentId=useCurrent(s=>s.key), pref=usePrefs(s=>s);
    const [doc,setDoc]=React.useState(null),[error,setError]=React.useState(''),[busy,setBusy]=React.useState(false),[selection,setSelection]=React.useState(null),[editing,setEditing]=React.useState(null),[value,setValue]=React.useState(''),[query,setQuery]=React.useState(''),[menu,setMenu]=React.useState(null),[picker,setPicker]=React.useState(false),[workspacePath,setWorkspacePath]=React.useState(''),[archived,setArchived]=React.useState(false),[explorerTab,setExplorerTab]=React.useState('workspace');
    const locked=React.useRef(false), migrated=React.useRef('');
    const [closed,setClosed]=React.useState(()=>{try{return new Set(JSON.parse(localStorage.getItem('linkmind.closed-folders')||'[]'));}catch{return new Set();}});
    const load=async(signal)=>{try{const next=await api('/library',undefined,signal);if(!signal?.aborted)setDoc(old=>!old||next.revision>=old.revision?next:old);}catch(e){if(!signal?.aborted)setError(e.message);}};
    React.useEffect(()=>{const controller=new AbortController();let timer;const poll=async()=>{await load(controller.signal);if(!controller.signal.aborted)timer=setTimeout(poll,4000);};poll();return()=>{controller.abort();clearTimeout(timer);};},[]);
    const change=async(operation,data)=>{const next=await api('/library',{revision:doc.revision,operation,data});setDoc(old=>!old||next.revision>=old.revision?next:old);return next;};
    const perform=async action=>{if(locked.current)return;locked.current=true;setBusy(true);setError('');try{await action();}catch(e){setError(e.message);await load();}finally{locked.current=false;setBusy(false);}};
    const workspaces=workspaceState.items, workspaceMap=new Map(workspaces.map(w=>[w.workspaceId,w])), archivedIds=new Set(workspaceState.archivedSessionIds);
    const folders=doc?.folders||[],members=doc?.members||{},folderMap=new Map(folders.map(f=>[f.id,f]));
    // Native ownership is authoritative. A folder never changes a Session's cwd.
    const workspaceOf=id=>workspaces.find(w=>w.sessionIds.includes(id))?.workspaceId||workspaces.find(w=>w.path===list.byId[id]?.cwd)?.workspaceId;
    React.useEffect(()=>{if(currentId)setSelection({type:'session',id:currentId,workspaceId:workspaceOf(currentId)});},[currentId]);
    const displayName=s=>s?.projectionValues?.title||(s?.blank?'新会话':s?.displayTitle)||'新会话';
    const workspaceName=id=>workspaceMap.get(id)?.title||workspaceMap.get(id)?.path.split('/').filter(Boolean).at(-1)||'工作区';
    const allSessions=list.ids.map(id=>list.byId[id]).filter(s=>s&&s.origin!=='subagent');
    const sessions=allSessions.filter(s=>archivedIds.has(s.id)===archived&&(!s.blank||s.id===currentId||Object.hasOwn(members,s.id)||archived));
    const actualFolder=(id,scope)=>folderMap.get(members[id])?.workspace_id===scope?members[id]:null;
    const folderPath=id=>{const result=[];for(let f=folderMap.get(id);f;f=folderMap.get(f.parent_id))result.unshift(f.name);return result.join(' / ');};
    const location=item=>{const workspaceId=item?.workspaceId||workspaceOf(currentId);return {workspaceId,folderId:item?.type==='folder'?item.id:item?.type==='workspace'?null:actualFolder(item?.id||currentId,workspaceId)};};
    const selected=location(selection), locationName=selected.workspaceId?[workspaceName(selected.workspaceId),folderPath(selected.folderId)].filter(Boolean).join(' / '):'请先打开工作区';
    const expand=(id,scope)=>setClosed(prev=>{const next=new Set(prev);next.delete('workspace:'+scope);for(let f=folderMap.get(id);f;f=folderMap.get(f.parent_id))next.delete(f.id);return next;});
    const toggle=id=>setClosed(prev=>{const next=new Set(prev);next.has(id)?next.delete(id):next.add(id);try{localStorage.setItem('linkmind.closed-folders',JSON.stringify([...next]));}catch{}return next;});
    // Upgrade pre-release folders using real workspace membership; never guess a cwd.
    React.useEffect(()=>{
      if(!doc||!folders.some(f=>!f.workspace_id)||workspaceState.phase!=='ready'||list.phase!=='ready'||locked.current)return;
      const session_workspaces=Object.fromEntries(allSessions.map(s=>[s.id,workspaceOf(s.id)]).filter(([,w])=>w));
      const key=JSON.stringify([doc.revision,session_workspaces]);if(migrated.current===key)return;migrated.current=key;
      perform(()=>change('migrate_workspaces',{session_workspaces,default_workspace_id:workspaceOf(currentId)||workspaces[0]?.workspaceId}));
    },[doc,workspaceState,list]);
    const adoptWorkspace=async path=>{const w=await createWorkspace(path);setPicker(false);setSelection({type:'workspace',id:w.workspaceId,workspaceId:w.workspaceId});expand(null,w.workspaceId);};
    const openPicker=()=>perform(async()=>{let path;try{path=await pickDirectory();}catch{setPicker(true);return;}if(path)await adoptWorkspace(path);});
    const edit=(type,id,workspaceId,name='')=>{if(busy)return;setQuery('');setMenu(null);setEditing({type,id,workspaceId});setValue(name);setError('');if(type==='create')expand(id,workspaceId);};
    const save=()=>perform(async()=>{
      if(!value.trim())throw new Error('请输入名称');
      if(editing.type==='rename_session')await renameSession(editing.id,value.trim());
      else {const next=await change(editing.type==='create'?'create_folder':'rename_folder',editing.type==='create'?{name:value,parent_id:editing.id,workspace_id:editing.workspaceId}:{id:editing.id,name:value});if(editing.type==='create'){const added=next.folders.find(f=>!folderMap.has(f.id));setSelection({type:'folder',id:added.id,workspaceId:editing.workspaceId});}}
      setEditing(null);
    });
    const newChat=(workspaceId,folderId=null)=>perform(async()=>{
      if(!workspaceMap.has(workspaceId))throw new Error('请先打开项目工作区');
      if(folderId&&folderMap.get(folderId)?.workspace_id!==workspaceId)throw new Error('目录不属于这个项目，请刷新');
      setQuery('');setMenu(null);setArchived(false);expand(folderId,workspaceId);
      const id=await createSession(workspaceId);
      try{await change('move_session',{session_id:id,folder_id:folderId,workspace_id:workspaceId});}
      catch(e){openSession(id);throw new Error('会话已在所选工作区创建，但归类未保存：'+e.message+'。可从项目根目录重新移动。');}
      setSelection({type:'session',id,workspaceId});openSession(id);
    });
    React.useEffect(()=>{const handle=e=>{setExplorerTab('workspace');if(e.detail==='project')openPicker();else if(e.detail==='chat')selected.workspaceId?newChat(selected.workspaceId,selected.folderId):openPicker();else if(e.detail==='folder'){if(selected.workspaceId)edit('create',selected.folderId,selected.workspaceId);else openPicker();}};window.addEventListener('linkmind:explorer',handle);return()=>window.removeEventListener('linkmind:explorer',handle);});
    const showMenu=(e,item)=>{e.preventDefault();e.stopPropagation();setSelection(item);const rect=e.currentTarget.getBoundingClientRect();setMenu({item,point:e.type==='keydown'?{x:rect.left+20,y:rect.bottom}:{x:e.clientX,y:e.clientY},returnTo:e.currentTarget});};
    const iconButton=(label,icon,action,extra={})=>h(Button,{size:'sm',variant:'ghost',title:label,'aria-label':label,onClick:e=>{e.stopPropagation();action(e);},disabled:busy||!doc,...extra},icon);
    const folderIcon=h(IconFolderCloseRegular,{size:15}),chatIcon=h(ui.IconNewChatOutlineRegular,{size:15});
    const editor=(depth,label)=>h('form',{className:'lm-inline-edit',style:{marginLeft:depth*14},onSubmit:e=>{e.preventDefault();if(!e.nativeEvent.isComposing)save();}},h('input',{'aria-label':label,autoFocus:true,value,onChange:e=>setValue(e.target.value),onKeyDown:e=>{if(e.key==='Escape')setEditing(null);if(e.nativeEvent.isComposing&&e.key==='Enter')e.preventDefault();},placeholder:'输入名称，Enter 保存',maxLength:editing.type==='rename_session'?200:80}),iconButton('保存名称','✓',save,{type:'button'}),iconButton('取消编辑','×',()=>setEditing(null),{type:'button'}));
    const dragStart=(e,item)=>{e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('application/x-linkmind-library',JSON.stringify(item));};
    const move=(item,folderId,workspaceId)=>perform(async()=>{
      const owner=item.type==='session'?workspaceOf(item.id):folderMap.get(item.id)?.workspace_id;
      if(!owner||owner!==workspaceId)throw new Error('只能在同一项目内整理。会话的工作区不会随拖动而改变。');
      await change(item.type==='folder'?'move_folder':'move_session',item.type==='folder'?{id:item.id,parent_id:folderId,workspace_id:owner}:{session_id:item.id,folder_id:folderId,workspace_id:owner});expand(folderId,owner);
    });
    const drop=(e,target,workspaceId)=>{e.preventDefault();e.stopPropagation();let item;try{item=JSON.parse(e.dataTransfer.getData('application/x-linkmind-library'));}catch{return;}if(['folder','session'].includes(item?.type))move(item,target,workspaceId);};
    const matches=s=>!query||`${displayName(s)} ${s.cwd||''}`.toLowerCase().includes(query.toLowerCase());
    const keyMenu=(e,item)=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))showMenu(e,item);};
    const sessionRow=(s,depth,workspaceId)=>{const item={type:'session',id:s.id,workspaceId};return h('div',{key:s.id,role:'treeitem','aria-level':depth+1,'aria-selected':selection?.id===s.id,className:'lm-tree-row','data-current':String(s.id===currentId),'data-selected':String(selection?.id===s.id),style:{paddingLeft:depth*14},draggable:!editing,onDragStart:e=>dragStart(e,item),onContextMenu:e=>showMenu(e,item)},editing?.type==='rename_session'&&editing.id===s.id?editor(0,'重命名会话'):h('button',{className:'lm-row-main',title:`${displayName(s)}\n${s.cwd||'未绑定工作区'}`,onClick:()=>{setSelection(item);openSession(s.id);},onKeyDown:e=>{if(e.key==='F2')edit('rename_session',s.id,workspaceId,displayName(s));keyMenu(e,item);}},chatIcon,h('span',null,displayName(s)),s.running&&h('span',{'aria-label':'正在运行',className:'lm-running'},'●')),h('span',{className:'lm-row-actions'},iconButton('上方查看 '+displayName(s),'↗',()=>openChat(s.id)),iconButton('会话操作 '+displayName(s),'⋯',e=>showMenu(e,item))));};
    const newFolderRow=(parent,depth,scope)=>editing?.type==='create'&&editing.id===parent&&editing.workspaceId===scope?editor(depth,'新文件夹名称'):null;
    const branch=(parent,depth,scope)=>folders.filter(f=>f.parent_id===parent&&f.workspace_id===scope).sort((a,b)=>a.name.localeCompare(b.name)).map(f=>{const item={type:'folder',id:f.id,workspaceId:scope},label=workspaceName(scope)+' / '+folderPath(f.id);return h('div',{key:f.id,role:'treeitem','aria-level':depth+1,'aria-expanded':!closed.has(f.id),'aria-selected':selection?.id===f.id},h('div',{className:'lm-tree-row','data-selected':String(selection?.id===f.id),style:{paddingLeft:depth*14},draggable:!editing,onDragStart:e=>dragStart(e,item),onDragOver:e=>e.preventDefault(),onDrop:e=>drop(e,f.id,scope),onContextMenu:e=>showMenu(e,item)},iconButton((closed.has(f.id)?'展开 ':'折叠 ')+f.name,closed.has(f.id)?'›':'⌄',()=>toggle(f.id),{className:'lm-tree-chevron'}),editing?.type==='rename'&&editing.id===f.id?editor(0,'重命名文件夹'):h('button',{className:'lm-row-main',title:label,onClick:()=>{setSelection(item);if(closed.has(f.id))expand(f.id,scope);},onDoubleClick:()=>toggle(f.id),onKeyDown:e=>{if(e.key==='F2')edit('rename',f.id,scope,f.name);if(e.key==='ArrowLeft'&&!closed.has(f.id))toggle(f.id);if(e.key==='ArrowRight'&&closed.has(f.id))toggle(f.id);keyMenu(e,item);}},h(closed.has(f.id)?IconFolderCloseRegular:IconFolderOpenRegular,{size:16}),h('span',null,f.name)),h('span',{className:'lm-row-actions'},iconButton('在 '+label+' 中新建会话',chatIcon,()=>newChat(scope,f.id)),iconButton('文件夹操作 '+label,'⋯',e=>showMenu(e,item)))),!closed.has(f.id)&&h('div',{role:'group',className:'lm-tree-group'},newFolderRow(f.id,depth+1,scope),...branch(f.id,depth+1,scope),...sessions.filter(s=>workspaceOf(s.id)===scope&&actualFolder(s.id,scope)===f.id&&matches(s)).map(s=>sessionRow(s,depth+1,scope)),!folders.some(c=>c.parent_id===f.id)&&!sessions.some(s=>workspaceOf(s.id)===scope&&actualFolder(s.id,scope)===f.id)&&editing?.id!==f.id&&h('button',{className:'lm-empty-create',style:{marginLeft:(depth+1)*14},disabled:busy,onClick:()=>newChat(scope,f.id)},'+ 在此新建会话')));});
    const project=w=>{const scope=w.workspaceId,key='workspace:'+scope,item={type:'workspace',id:scope,workspaceId:scope},own=sessions.filter(s=>workspaceOf(s.id)===scope&&matches(s));return h('div',{key:scope,role:'treeitem','aria-level':1,'aria-expanded':!closed.has(key),'aria-selected':selection?.id===scope},h('div',{className:'lm-tree-row lm-project-row','data-selected':String(selection?.id===scope),onContextMenu:e=>showMenu(e,item),onDragOver:e=>e.preventDefault(),onDrop:e=>drop(e,null,scope)},iconButton((closed.has(key)?'展开项目 ':'折叠项目 ')+workspaceName(scope),closed.has(key)?'›':'⌄',()=>toggle(key),{className:'lm-tree-chevron'}),h('button',{className:'lm-row-main',title:w.path,onClick:()=>{setSelection(item);if(closed.has(key))expand(null,scope);},onDoubleClick:()=>toggle(key),onKeyDown:e=>keyMenu(e,item)},h(IconFolderOpenRegular,{size:16}),h('span',null,workspaceName(scope))),h('span',{className:'lm-row-actions'},iconButton('在项目 '+workspaceName(scope)+' 中新建会话',chatIcon,()=>newChat(scope)),iconButton('项目操作 '+workspaceName(scope),'⋯',e=>showMenu(e,item)))),(!closed.has(key)||query)&&h('div',{role:'group'},query?own.map(s=>sessionRow(s,1,scope)):h(React.Fragment,null,newFolderRow(null,1,scope),...branch(null,1,scope),...own.filter(s=>!actualFolder(s.id,scope)).map(s=>sessionRow(s,1,scope)),!own.length&&!folders.some(f=>f.workspace_id===scope)&&h('button',{className:'lm-empty-create',style:{marginLeft:14},onClick:()=>newChat(scope),disabled:busy},'+ 新建会话'))));};
    const target=menu?.item, scope=target?.workspaceId;
    const isDescendant=id=>{for(let f=folderMap.get(id);f;f=folderMap.get(f.parent_id))if(f.id===target?.id)return true;return false;};
    const destinations=[{id:'move:',label:'项目根目录'},...folders.filter(f=>f.workspace_id===scope&&(target?.type!=='folder'||!isDescendant(f.id))).map(f=>({id:'move:'+f.id,label:folderPath(f.id)})).sort((a,b)=>a.label.localeCompare(b.label))];
    const newItems=[{id:'chat',label:'新建会话'},{id:'folder',label:target?.type==='folder'?'新建子文件夹':'新建文件夹'}];
    const menuItems=target?.type==='workspace'?[{type:'label',id:'path',text:workspaceMap.get(scope)?.path||''},...newItems,{type:'separator',id:'s'},{id:'files',label:'查看项目文件'}]:target?.type==='folder'?[{type:'label',id:'path',text:workspaceName(scope)+' / '+folderPath(target.id)},...newItems,{type:'separator',id:'s'},{id:'rename',label:'重命名'},{id:'move',label:'移动到',submenu:destinations},{id:'remove',label:'移除空文件夹',disabled:folders.some(f=>f.parent_id===target.id)||Object.values(members).includes(target.id)}]:target?.type==='session'?[{id:'open',label:'打开对话'},{id:'view',label:'在上方查看'},{type:'separator',id:'s'},{id:'chat',label:'在同一目录新建会话',disabled:!scope},{id:'rename',label:'重命名'},{id:'move',label:'移动到',submenu:destinations,disabled:!scope},{id:archived?'restore':'archive',label:archived?'取消归档':'归档会话',disabled:!!list.byId[target.id]?.running}]:[{id:'workspace',label:'打开项目文件夹…'},{id:'workspace-path',label:'输入工作区路径…'},{id:'archived',label:archived?'返回活跃会话':'查看归档会话'},{type:'separator',id:'s'},{id:'layout',label:pref.stacked?'切回左右布局':'切换上下布局'},{id:'home',label:'打开工作台'}];
    const choose=key=>{setMenu(null);if(key.startsWith('move:'))move(target,key.slice(5)||null,scope);else if(key==='chat'){const loc=location(target);newChat(loc.workspaceId,loc.folderId);}else if(key==='folder')edit('create',target?.type==='folder'?target.id:null,scope);else if(key==='rename')edit(target.type==='folder'?'rename':'rename_session',target.id,scope,target.type==='folder'?folderMap.get(target.id).name:displayName(list.byId[target.id]));else if(key==='remove')perform(()=>change('remove_folder',{id:target.id}));else if(key==='open')openSession(target.id);else if(key==='view')openChat(target.id);else if(key==='archive')perform(()=>archiveSession(target.id));else if(key==='restore')perform(()=>restoreSession(target.id));else if(key==='archived')setArchived(!archived);else if(key==='workspace')openPicker();else if(key==='workspace-path')setPicker(true);else if(key==='files')perform(async()=>{const id=workspaceMap.get(scope)?.sessionIds.find(id=>!archivedIds.has(id));if(id)openSession(id);else openSession(await createSession(scope));openPage('files');});else if(key==='layout')setPreference({stacked:!pref.stacked});else if(key==='home')openPage('linkmind-workbench');};
    if(wide===false)return h('div',{className:'lm-library'},iconButton('打开工作台','▤',()=>openPage('linkmind-workbench')));
    return h('div',{className:'lm-library',onContextMenu:e=>{if(e.target===e.currentTarget)showMenu(e,null);}},h('div',{className:'lm-explorer-heading'},h('strong',null,archived?'归档会话':'资源管理器'),iconButton('在 '+locationName+' 中新建会话',chatIcon,()=>selected.workspaceId?newChat(selected.workspaceId,selected.folderId):openPicker()),iconButton('打开项目文件夹',folderIcon,openPicker),iconButton('目录选项','⋯',e=>showMenu(e,null))),h('div',{className:'lm-explorer-tabs',role:'tablist','aria-label':'资源管理器分类'},...[["workspace","工作区"],["artifacts","成果"],["tools","工具"]].map(([key,label])=>h('button',{key,role:'tab','aria-selected':explorerTab===key,onClick:()=>setExplorerTab(key)},label))),explorerTab==='workspace'&&h('input',{'aria-label':'筛选会话',placeholder:'查找会话…',value:query,onChange:e=>setQuery(e.target.value)}),explorerTab==='workspace'&&h('div',{className:'lm-location',title:workspaceMap.get(selected.workspaceId)?.path||''},'新建于 · ',locationName),error&&h('p',{className:'lm-error',role:'alert'},error,iconButton('刷新目录','↻',()=>{setError('');load();})),!doc&&h('p',{role:'status'},'正在读取目录…'),doc&&explorerTab==='workspace'&&h('div',{role:'tree','aria-label':'项目会话目录',className:'lm-tree',onContextMenu:e=>{if(e.target===e.currentTarget)showMenu(e,null);}},...workspaces.filter(w=>!query||sessions.some(s=>workspaceOf(s.id)===w.workspaceId&&matches(s))).map(project),sessions.some(s=>!workspaceOf(s.id))&&h('div',{role:'group','aria-label':'未绑定工作区'},h('p',{className:'lm-small'},'未绑定工作区'),...sessions.filter(s=>!workspaceOf(s.id)&&matches(s)).map(s=>sessionRow(s,0,undefined))),!workspaces.length&&h('p',{className:'lm-small'},'打开项目文件夹后，右键项目新建会话。每个会话使用所属项目的工作区。')),
      explorerTab!=='workspace'&&h('div',{className:'lm-explorer-info'},...(explorerTab==='artifacts'?[['linkmind-workbench','运行结果与观察画面'],['files','项目文件与报告'],['linkmind-tasks','任务证据与记录']]:[['linkmind-project','运行配置'],['terminal','项目终端'],['linkmind-camera','控制会话与摄像头']]).map(([kind,label])=>h(Button,{key:kind,variant:'ghost',onClick:()=>openPage(kind)},label)),h('p',{className:'lm-small'},explorerTab==='artifacts'?'查看当前对话工作区的真实产物与记录。':'沿用当前对话的工作区和 DSH 工具。')),
      explorerTab==='workspace'&&h('div',{className:'lm-references'},h('h3',null,h(ui.IconLinkOutlineRegular,{size:14}),'同项目会话 · 可在上方参考'),...sessions.filter(s=>s.id!==currentId&&workspaceOf(s.id)===workspaceOf(currentId)).slice(0,3).map(s=>h(Button,{key:s.id,variant:'ghost',size:'sm',onClick:()=>openChat(s.id)},displayName(s))),!sessions.some(s=>s.id!==currentId&&workspaceOf(s.id)===workspaceOf(currentId))&&h('span',{className:'lm-small'},'右键会话 → 在上方查看')),
      h(ui.Modal,{open:picker,onClose:()=>setPicker(false),title:'打开项目工作区',closeLabel:'关闭',footer:h(Button,{variant:'primary',disabled:busy||!workspacePath.trim(),onClick:()=>perform(()=>adoptWorkspace(workspacePath.trim()))},'打开')},h('p',{className:'lm-small'},'选择本机项目文件夹。此项目下新建的会话都会绑定这个工作区。'),h('input',{'aria-label':'项目文件夹绝对路径',autoFocus:true,placeholder:'/home/user/projects/HexaShell',value:workspacePath,onChange:e=>setWorkspacePath(e.target.value),style:{width:'100%',padding:10,color:'inherit',background:'var(--dsw-alias-bg-base)',border:'1px solid var(--dsw-alias-border-l3)',borderRadius:6},onKeyDown:e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing&&workspacePath.trim())perform(()=>adoptWorkspace(workspacePath.trim()));}}),error&&h('p',{role:'alert'},error)),
      h(ui.Menu,{open:!!menu,anchor:null,portal:true,contextual:true,autoFocus:true,anchorPoint:menu?.point,returnFocus:()=>menu?.returnTo||null,items:menuItems,onSelect:choose,onClose:()=>setMenu(null)}));
  }
  function FixedView({renderSlot}) {return renderSlot('conversation.session',{view:'chat'});}
  function EmbeddedChat({useSession,useConversation,renderFactorySlot}) {
    const session=useSession(s=>s), conversation=useConversation(s=>s);
    const active=session.running||conversation.activeTargets.size>0||(!session.blank&&!session.awaitingFirstTurn);
    return h('div',{className:'lm-embedded-body'},renderFactorySlot('conversation.content',{variant:'embedded',phase:active?'active':session.openState==='loading'?'settling':'hero',hero:!active},{slots:{views:FixedView}}));
  }
  function ChatTab({useResource,useTabInfo,SessionProvider,renderSlot,openSession}) {
    const {tab}=useTabInfo(), resource=useResource(tab.contentId), id=parseChat(tab.contentId);
    return h('section',{className:'lm-chat-view'},h('div',{className:'lm-chat-bar'},h('span',null,'会话实时查看'),h(Button,{size:'sm',variant:'ghost',onClick:()=>openSession(id)},'切换到下方对话')),
      resource.value?h(SessionProvider,{session:resource.value.reference},renderSlot('linkmind.viewer.conversation',{})):h('p',{className:'lm-small'},resource.error?'会话暂时无法读取，请关闭页签后重试':'正在读取会话…'));
  }
  ctx.effect(()=>ctx.resources.register({protocol:'linkmindchat',async *open(address,{signal}) {
    const id=parseChat(address);if(!id)throw new Error('会话地址无效');
    const reference=ctx.sessions.retain(id,{source:'linkmindViewer',signal});
    try {yield {ok:true,value:{reference}};if(!signal.aborted)await new Promise(resolve=>signal.addEventListener('abort',resolve,{once:true}));}finally{reference.release();}
  }}),'LinkMind conversation resources');
  ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-chat',kind:'linkmind-chat',patterns:['dsh-resource://linkmindchat/session/**'],keepMounted:true,title:address=>ctx.sessions.list.getSnapshot().byId[parseChat(address)]?.displayTitle||'会话'}),'LinkMind conversation tabs');
  ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-chat',children:{'linkmind.viewer.conversation':{kind:'single',scope:'session'}},inject:()=>({openSession:id=>ctx.uiWorkspace.openSession(id)})},ChatTab));
  ctx.slots.inject('linkmind.viewer.conversation',()=>ctx.slots.register({name:'linkmind.viewer.conversation'},EmbeddedChat));
  ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-workbench',kind:'linkmind-workbench',title:()=> '项目概览',guide:[{id:'linkmind-workbench',order:-60,title:()=> '项目概览',description:()=> '文件、会话、执行过程和摄像头'}]}),'LinkMind workbench tab');
  ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-workbench',inject:()=>({openPage,openRun:id=>{window.dispatchEvent(new CustomEvent('linkmind:overview-run',{detail:{id,sessionId:currentId()}}));openPage('linkmind-camera');},openFile:path=>ctx.sidebarRight.openResource('dsh-resource://file/session/'+encodeURIComponent(currentId())+'/'+path.split('/').map(encodeURIComponent).join('/'))})},Overview));
  ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-graph',kind:'linkmind-graph',title:()=> '任务图'}),'LinkMind task graph');
  ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-graph',inject:()=>({openPage,graphOnly:true})},Overview));
  const {Board,Environments}=createRSIViews(React,ui,api);
  for(const [kind,title,Panel] of [['studio-rsi','Agent RSI Board',Board],['studio-environments','环境注册',Environments]]) {
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:kind,kind,title:()=>title}),title);
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({
      name:'sidebar.right.pane.tab',key:kind,inject:()=>({
        openFile:path=>ctx.sidebarRight.openResource('dsh-resource://file/session/'+encodeURIComponent(currentId())+'/'+path.split('/').map(encodeURIComponent).join('/')),openPage,pickDirectory:()=>globalThis.__DSH_DIRECTORY_PICKER__?.pick?.()??ctx.uiWorkspace.pickDirectory(),
        openRun:id=>{window.dispatchEvent(new CustomEvent('linkmind:overview-run',{detail:{id,sessionId:currentId()}}));openPage('linkmind-camera');}
      })},Panel));
  }
  for(const [key,title,icon] of [['linkmind-graph','任务图','IconBranchOutlineRegular'],['linkmind-workbench','项目概览','IconLayersOutlineRegular'],['linkmind-camera','控制会话与摄像头','IconEyeOutlineRegular'],['linkmind-tasks','任务','IconBranchOutlineRegular'],['linkmind-project','运行配置','IconPlayOutlineRegular']]) {
    ctx.slots.inject('sidebar.right.pane.tab.title',()=>ctx.slots.register({name:'sidebar.right.pane.tab.title',key},()=>h('span',{className:'lm-tab-label'},h(ui[icon],{size:15}),title)));
  }
  ctx.slots.inject('sidebar.workspaces',()=>ctx.slots.register({
    name:'sidebar.workspaces',priority:-50,
    inject:()=>({...bindings(),openSession:id=>ctx.uiWorkspace.openSession(id),openChat,
      createSession:async workspaceId=>{
        if(!ctx.workspaces.list.getSnapshot().items.some(w=>w.workspaceId===workspaceId))throw new Error('项目工作区已移除，请重新打开');
        return ctx.sessions.create({sessionId:'session-'+crypto.randomUUID(),workspaceId,agentPreset:'linkmind-embodied'});
      },
      createWorkspace:path=>ctx.workspaces.create({path}),
      pickDirectory:()=>globalThis.__DSH_DIRECTORY_PICKER__?.pick?.()??ctx.uiWorkspace.pickDirectory(),
      archiveSession:id=>ctx.uiWorkspace.archiveSession(id),restoreSession:id=>ctx.uiWorkspace.unarchiveSession(id),
      renameSession:async(id,title)=>{const r=await ctx.remote.session.rename({sessionId:id,title});if(!r.ok)throw new Error(r.error.message);}
    })},Library));
  ctx.slots.inject('shell.overlay',()=>ctx.slots.register({name:'shell.overlay',id:'linkmind-layout',inject:bindings},Marker));
  // Entering the Studio opens its existing dock once; ordinary DSH modes keep their layout.
  const visited=new Set();
  ctx.effect(()=>{let timer;const sync=()=>{const id=currentId();if(!id||visited.has(id)||ctx.sessions.list.getSnapshot().byId[id]?.projectionValues?.agentPreset!=='linkmind-embodied')return;visited.add(id);timer=setTimeout(()=>{if(currentId()===id&&!ctx.sidebarRight.isExpanded())openPage('linkmind-workbench');},200);};const a=current.subscribe(sync),b=ctx.sessions.list.subscribe(sync);sync();return()=>{clearTimeout(timer);a();b();};},'LinkMind workbench entry');
}

// The controlling agent's structured stream. Runner stdout stays in Diagnostics.
export function createControlConversation(React, ui, api) {
  const h=React.createElement, {Button}=ui;
  const printable=value=>typeof value==='string'?value:value==null?'':JSON.stringify(value,null,2);
  function Payload({value}) {
    const [full,setFull]=React.useState(false), text=printable(value);
    if(!text)return null;
    return h(React.Fragment,null,h('pre',{className:'lm-tool-payload'},full?text:text.slice(0,16000)),text.length>16000&&h(Button,{size:'sm',variant:'ghost',onClick:()=>setFull(v=>!v)},full?'收起长结果':'展开完整结果'));
  }
  function Card({item}) {
    if(item.kind==='tool')return h('details',{className:'lm-control-tool'},h('summary',null,
      h('span',{'aria-hidden':true},item.status==='in_progress'?'◌':'⌘'), ' ',item.status==='in_progress'?'正在调用 ':'已调用 ',item.name,
      h('span',{className:'lm-tool-command'},typeof item.arguments==='string'?item.arguments:'')),
      h('div',{className:'lm-tool-body'},h('span',{className:'lm-small'},'调用参数'),h(Payload,{value:item.arguments}),
        h('span',{className:'lm-small'},'返回结果'),h(Payload,{value:item.output}),
        item.status==='in_progress'&&h('p',{className:'lm-small'},'等待工具返回…'),
        h('span',{className:'lm-small'},[item.status, item.exit_code!=null?'退出码 '+item.exit_code:''].filter(Boolean).join(' · '))));
    if(item.kind==='error')return h('details',{className:'lm-control-tool'},h('summary',null,'运行提示'),h(Payload,{value:item.text}));
    return h('article',{className:'lm-control-message','data-role':item.role||'system'},
      h('div',{className:'lm-small'},item.summary?'模型提供的思考摘要':item.role==='assistant'?'操控 Agent':item.role==='user'?'用户':'运行状态'),
      h('div',{style:{whiteSpace:'pre-wrap',overflowWrap:'anywhere',lineHeight:1.75}},printable(item.text)));
  }
  return function ControlConversation({run}) {
    const [state,setState]=React.useState({items:[],available:null}),[error,setError]=React.useState(''),[retry,setRetry]=React.useState(0),[following,setFollowing]=React.useState(true);
    const viewport=React.useRef(null), auto=React.useRef(true);
    React.useEffect(()=>{
      const controller=new AbortController();let timer,offset=0,source=null,items=new Map(),thread='',phase='',usage=null,warningSet=new Set();
      setState({items:[],available:null});setError('');auto.current=true;setFollowing(true);
      const update=async()=>{
        try{
          const reply=await api(`/project-runs/${run.id}/conversation`,{offset,source},controller.signal);
          if(controller.signal.aborted)return;
          if(reply.reset){items=new Map();thread='';phase='';usage=null;warningSet=new Set();}
          offset=reply.next_offset;source=reply.source;
          for(const event of reply.events){
            if(event.type==='session')thread=event.thread_id;
            else if(event.type==='item')items.set(event.item.id,{...items.get(event.item.id),...event.item});
            else if(event.type==='lifecycle'){phase=event.event;if(event.usage)usage=event.usage;if(event.detail)warningSet.add(printable(event.detail));}
            else if(event.type==='unsupported')warningSet.add('未渲染的原始事件：'+event.event);
          }
          for(const warning of reply.warnings||[])warningSet.add(warning);
          // Bound a retained viewer, not the underlying file. Explain any omitted history.
          while(items.size>1500){items.delete(items.keys().next().value);warningSet.add('当前显示最近 1500 项，较早内容请查看源文件。');}
          setState({items:[...items.values()],thread,phase,usage,available:reply.available,path:reply.path,format:reply.format,warnings:[...warningSet]});setError('');
          timer=setTimeout(update,reply.more?30:800);
        }catch(e){if(controller.signal.aborted)return;setError('控制会话连接中断：'+e.message);timer=setTimeout(update,2000);}
      };
      update();return()=>{controller.abort();clearTimeout(timer);};
    },[run.id,retry]);
    React.useLayoutEffect(()=>{if(auto.current&&viewport.current)viewport.current.scrollTop=viewport.current.scrollHeight;},[state]);
    return h('section',{className:'lm-control','aria-label':'真实控制会话'},
      h('div',{className:'lm-control-heading'},h('strong',null,'控制会话'),h('span',{className:'lm-small'},['starting','running','stopping'].includes(run.status)?'实时更新':'历史会话')),
      state.path&&h('details',{className:'lm-small'},h('summary',{title:state.thread},'会话与事件来源 · '+state.format),state.thread&&h('div',null,'会话 '+state.thread),h('code',null,state.path),h('div',null,'直接显示模型消息、工具调用与返回结果；按来源提供的粒度更新。'),state.usage&&h(Payload,{value:state.usage})),
      error&&h('p',{role:'alert',className:'lm-small'},error,h(Button,{size:'sm',variant:'ghost',onClick:()=>setRetry(v=>v+1)},'重连')),
      h('div',{className:'lm-control-feed',ref:viewport,onScroll:e=>{const el=e.currentTarget;auto.current=el.scrollHeight-el.scrollTop-el.clientHeight<60;setFollowing(auto.current);}},
        state.available===null&&h('p',{className:'lm-small'},'正在连接控制会话…'),
        state.available===false&&h('p',{className:'lm-small'},'尚未发现控制会话事件。等待 Agent 写入 agent-events.jsonl；API 方案可在运行配置中声明 conversation 事件源。普通程序输出可在诊断日志中查看。'),
        state.available&&state.items.length===0&&h('p',{className:'lm-small'},'已连接，等待 Agent 消息或工具调用…'),
        ...state.items.map(item=>h(Card,{key:item.id,item}))),
      !following&&h(Button,{size:'sm',variant:'outline',onClick:()=>{auto.current=true;setFollowing(true);viewport.current.scrollTop=viewport.current.scrollHeight;}},'回到最新'),
      state.phase==='turn.completed'&&h('span',{className:'lm-small'},'本轮控制会话已结束'),
      state.phase==='turn.failed'&&h('span',{className:'lm-small',role:'status'},'本轮控制会话失败'),
      state.warnings?.length>0&&h('details',{className:'lm-small'},h('summary',null,'事件提示'),...state.warnings.map((x,i)=>h('p',{key:i},x))));
  };
}
