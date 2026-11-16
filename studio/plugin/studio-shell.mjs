// The Studio owns its chrome; DSH continues to own panes, sessions and composers.
const frame='[data-slot="root"]>div:has(.lm-layout-marker[data-stacked=true]):not(:has([data-global-panel=true]))';
export const studioFrame=frame;
export const studioStyles = `
body[data-ds-dark-theme] ${frame}{--dsw-alias-bg-base:#151821;--dsw-alias-bg-hover:#252a37;--dsw-alias-border-l3:#343947;--dsw-alias-label-primary:#e7e9f2;--dsw-alias-label-secondary:#a9b0c2;--lm-accent:#a48cf2}
${frame} [data-slot="sidebar"]>div>div:has([data-slot="sidebar.brand.mark"]){display:none}
${frame} [data-slot="main.conversation"] [data-composer-seat] div:has(>[data-slot="conversation.composer.bar"]){width:100%;max-width:none;padding-bottom:4px}
${frame} [data-slot="main.conversation"] [data-slot="conversation.composer.bar"]>div{max-width:none;width:100%;padding:0}
${frame} [data-slot="main.conversation"] [data-phase=hero] div:has(>[data-slot="conversation.hero.workspace"]){font-size:12px}

.lm-studio-chrome{display:none}
${frame}:has(.lm-layout-marker[data-dock=terminal]) [data-slot="main"]{visibility:hidden;pointer-events:none}
.lm-chat-tabs [role=tablist]{display:flex;align-items:center;flex-shrink:0}
.lm-terminal-actions{display:flex;align-items:center;gap:4px;margin-left:auto;min-width:0}
.lm-terminal-actions button{padding-inline:8px!important}
.lm-terminal-picker{overflow:hidden;text-overflow:ellipsis;max-width:200px}
.lm-dock-error{position:absolute;left:calc(48px + var(--lm-explorer,260px));right:0;bottom:24px;z-index:18;padding:8px 12px;background:var(--dsw-alias-bg-base);pointer-events:auto;font-size:12px}
${frame} .lm-process-grid{gap:12px}
${frame} .lm-control{border:1px solid var(--dsw-alias-border-l3);border-radius:9px;padding:12px;background:color-mix(in srgb,var(--dsw-alias-bg-hover) 40%,var(--dsw-alias-bg-base))}
${frame} .lm-control strong{font-weight:500}

${frame} .lm-goal-hint{display:none}
.lm-tab-label{display:inline-flex;align-items:center;gap:7px;font-size:12px}.lm-tab-label svg{color:var(--lm-accent,#7c65d2)}
${frame}{--lm-accent:#7c65d2;--lm-line:var(--dsw-alias-border-l3);--lm-surface:var(--dsw-alias-bg-base);--lm-muted:var(--dsw-alias-label-secondary);grid-template-columns:48px var(--lm-explorer,260px) minmax(0,1fr)!important;grid-template-rows:44px minmax(200px,min(var(--lm-upper,57%),calc(100% - 310px))) minmax(240px,1fr) 24px!important;gap:0!important;background:var(--dsw-alias-bg-base)}
${frame}>div:has(>[data-slot="sidebar"]){grid-column:2!important;grid-row:2/4!important;width:100%!important;min-height:0;border-right:1px solid var(--lm-line)}
${frame} [data-slot="sidebar"]>div{background:var(--dsw-alias-bg-base)!important;width:100%!important;border-radius:0!important;padding:0!important}
${frame} [data-slot="sidebar"]>div>button,${frame} [data-sidebar-scrollport]>nav{display:none!important}
${frame} [data-sidebar-scrollport]{overflow:hidden!important;padding:0!important;mask:none!important}
${frame} [data-sidebar-scrollport]::before,${frame} [data-sidebar-scrollport]::after{display:none!important}
${frame} [data-sidebar-scrollport]>div{height:100%;min-height:0}
${frame} [data-slot="sidebar.workspaces"]>div{height:100%}
${frame} .lm-library{height:100%;padding:0 10px;display:flex;flex-direction:column;min-height:0;box-sizing:border-box}
${frame} .lm-tree{flex:1;overflow:auto;margin:0 -6px;padding:4px 4px 16px;min-height:0}
${frame} .lm-explorer-heading{height:42px;padding:0 2px;flex-shrink:0}
${frame} .lm-explorer-heading strong{font-size:13px}
${frame} .lm-location{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;margin:8px 0 4px;flex-shrink:0}
${frame} .lm-tree-row{min-height:29px}.lm-tree-group{border-left:1px solid color-mix(in srgb,currentColor 10%,transparent);margin-left:9px;padding-left:0}
${frame} .lm-tree-row[data-current=true]{background:color-mix(in srgb,var(--lm-accent) 15%,transparent);box-shadow:inset 2px 0 var(--lm-accent)}
${frame} .lm-project-row{margin:8px 0 3px}
${frame} .lm-project-row svg,${frame} .lm-tree-group>.lm-tree-row svg{color:var(--lm-accent)}
${frame} .lm-row-main{padding-top:4px;padding-bottom:4px}
${frame}>div:has(>[data-slot="sidebar"])~div:has([data-slot="main"]){grid-column:3!important;grid-row:3!important;position:relative;padding-top:35px;border-top:1px solid var(--lm-line);min-height:0;background:var(--dsw-alias-bg-base)}
${frame}>[data-rightbar-col]{grid-column:3!important;grid-row:2!important;position:relative;min-width:0;min-height:0;padding:0 6px 6px;background:var(--dsw-alias-bg-base)}
${frame} [data-sidebar-right-panel]{width:100%!important;max-width:100%!important;--dsh-sidebar-width:100%!important;border-radius:0!important;border:0!important}
${frame}>[data-shell-bottom]{grid-row:4!important;grid-column:1/4}
${frame}>[data-side]{display:none!important}
${frame} [data-slot="main.conversation"]>div{position:relative;min-height:0}
${frame} [data-slot="main.conversation"] [data-conversation-content]{--dsh-conversation-column-width:100%;--dsh-composer-card-max-width:100%!important;--dsh-composer-side-clearance:0px!important}
${frame} [data-slot="main.conversation"] [data-slot="conversation.header"],${frame} [data-slot="main.conversation"] [data-slot="conversation.hero.options"]{display:none}
${frame} [data-slot="main.conversation"] [data-phase=hero] [data-conversation-scroll]{justify-content:flex-end}
${frame} [data-slot="main.conversation"] [data-phase=hero] div:has(>span>[data-slot="conversation.hero.brand.mark"]){display:none}
${frame} [data-slot="main.conversation"] [data-composer-seat]{padding:8px 16px 10px!important}
${frame} .lm-studio-chrome{display:contents}
.lm-titlebar,.lm-activity,.lm-statusbar,.lm-chat-tabs{pointer-events:auto;position:absolute;display:flex;align-items:center;box-sizing:border-box;color:var(--dsw-alias-label-primary);font-size:12px;background:var(--dsw-alias-bg-base)}
.lm-titlebar{top:0;left:0;right:0;height:44px;border-bottom:1px solid var(--lm-line);gap:18px;padding:0 14px;z-index:15}
.lm-brand{display:flex;align-items:center;gap:9px;min-width:185px;font-size:14px;font-weight:500;letter-spacing:.15px}.lm-brand svg{color:var(--lm-accent)}
.lm-title-menu{display:flex;gap:4px}.lm-title-menu button{font-size:12px;padding:5px 8px;border:0;background:none;color:var(--lm-muted);cursor:pointer}
.lm-quick-search{display:flex;align-items:center;gap:8px;max-width:490px;min-width:160px;flex:1;margin:0 auto;padding:5px 12px;border:1px solid var(--lm-line);border-radius:6px;color:var(--lm-muted);background:var(--dsw-alias-bg-hover);font:inherit;text-align:left;cursor:pointer}.lm-quick-search span{flex:1}.lm-quick-search kbd{font:11px inherit}
.lm-agent-state{display:flex;align-items:center;gap:7px;white-space:nowrap;font-size:11px}.lm-status-dot{width:7px;height:7px;flex-shrink:0;border-radius:50%;background:#42a87a}.lm-agent-state[data-running=true] .lm-status-dot{background:var(--lm-accent)}
.lm-activity{left:0;top:44px;bottom:24px;width:48px;border-right:1px solid var(--lm-line);flex-direction:column;align-items:stretch;gap:7px;padding:9px 3px;z-index:15}.lm-activity button{height:39px!important;padding:9px!important;border-radius:6px!important;position:relative;color:var(--lm-muted)}.lm-activity button[aria-pressed=true]{color:var(--lm-accent);background:color-mix(in srgb,var(--lm-accent) 13%,transparent)}.lm-activity button[aria-pressed=true]::before{content:'';position:absolute;left:-3px;top:6px;bottom:6px;width:2px;background:var(--lm-accent)}.lm-activity-spacer{flex:1}
.lm-statusbar{bottom:0;left:0;right:0;height:24px;border-top:1px solid var(--lm-line);padding:0 12px;gap:14px;color:var(--lm-muted);font-size:11px;z-index:15}.lm-statusbar .lm-status-path{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lm-chat-tabs{left:calc(48px + var(--lm-explorer,260px));right:0;top:calc(44px + min(var(--lm-upper,57%),100% - 310px));height:35px;padding:0 10px;border-bottom:1px solid var(--lm-line);gap:4px;z-index:16}.lm-chat-tabs button{display:flex;gap:7px;align-items:center;border:0;background:none;color:var(--lm-muted);font:inherit;font-size:12px;padding:8px 12px;height:35px;cursor:pointer;white-space:nowrap}.lm-chat-tabs button[aria-selected=true]{color:var(--dsw-alias-label-primary);border-bottom:2px solid var(--lm-accent);background:var(--dsw-alias-bg-hover)}.lm-chat-title{margin-left:auto;font-size:11px;color:var(--lm-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:32%}
${frame} .lm-grip{display:block;position:absolute;top:calc(41px + min(var(--lm-upper,57%),100% - 310px));left:calc(48px + var(--lm-explorer,260px));right:0;height:6px;cursor:row-resize;z-index:30;pointer-events:auto;touch-action:none}.lm-grip:hover,.lm-grip:focus-visible{background:var(--lm-accent)}
.lm-side-grip{position:absolute;pointer-events:auto;top:44px;bottom:24px;left:calc(45px + var(--lm-explorer,260px));width:6px;cursor:col-resize;z-index:30;touch-action:none}.lm-side-grip:hover,.lm-side-grip:focus-visible{background:var(--lm-accent)}
.lm-explorer-tabs{display:flex;flex-shrink:0;margin:0 0 10px;gap:2px;padding:3px;border:1px solid var(--dsw-alias-border-l3);border-radius:7px}.lm-explorer-tabs button{flex:1;border:0;border-radius:4px;padding:5px 1px;cursor:pointer;background:none;color:var(--dsw-alias-label-secondary);font:inherit;font-size:12px}.lm-explorer-tabs button[aria-selected=true]{background:var(--dsw-alias-bg-hover);color:var(--dsw-alias-label-primary);box-shadow:0 1px 3px #0001}
.lm-explorer-info{overflow:auto;flex:1;display:flex;flex-direction:column;gap:10px;padding:8px 2px}.lm-explorer-info button{text-align:left;white-space:normal;justify-content:flex-start}.lm-explorer-info p{margin:0}.lm-references{flex-shrink:0;border-top:1px solid var(--dsw-alias-border-l3);padding:10px 0;display:flex;flex-direction:column;gap:4px}.lm-references h3{display:flex;gap:6px;align-items:center;font-size:11px;font-weight:500;color:var(--dsw-alias-label-secondary);margin:0 0 4px}.lm-references button{font-size:12px;justify-content:flex-start;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.lm-command-input{width:100%;padding:10px 12px;border:1px solid var(--dsw-alias-border-l3);border-radius:7px;background:var(--dsw-alias-bg-base);color:inherit;font:inherit;box-sizing:border-box}.lm-command-list{display:flex;flex-direction:column;gap:3px;max-height:48vh;overflow:auto;margin-top:12px}.lm-command-list button{justify-content:flex-start;text-align:left;min-height:36px}.lm-command-list small{margin-left:auto;color:var(--dsw-alias-label-secondary);overflow:hidden;max-width:45%;text-overflow:ellipsis;white-space:nowrap}
${frame}[data-sidebar-collapsed]{--lm-explorer:0px!important}
${frame}[data-sidebar-collapsed]>div:has(>[data-slot="sidebar"]){visibility:hidden}
@media(max-width:1000px){.lm-title-menu{display:none}.lm-brand{min-width:165px}.lm-chat-title{display:none}.lm-titlebar{gap:12px}}
@media(max-width:760px){${frame}{--lm-explorer:0px!important;grid-template-rows:44px minmax(200px,min(var(--lm-upper,50%),calc(100% - 310px))) minmax(240px,1fr) 24px!important}${frame}>div:has(>[data-slot="sidebar"]){display:none}${frame}:not([data-sidebar-collapsed])>div:has(>[data-slot="sidebar"]){display:block;position:absolute;grid-area:1 / 1 / -1 / -1!important;left:48px;top:44px;bottom:24px;width:min(300px,calc(100% - 48px))!important;z-index:80;background:var(--dsw-alias-bg-base)}.lm-side-grip{display:none}.lm-titlebar .lm-agent-state,.lm-titlebar kbd{display:none}.lm-brand{min-width:0;font-size:12px}.lm-titlebar{padding:0 8px;gap:8px}.lm-quick-search{min-width:80px}.lm-chat-tabs button{padding:8px}.lm-statusbar span:last-child{display:none}}
`;

export function createStudioChrome(React,ui) {
 const h=React.createElement;
 const icon=(name,size=18)=>h(ui[name],{size});
 return function StudioChrome({useCurrent,useSessions,useWorkspaces,usePrefs,useDock,setPreference,openPage,openSession,toggleSidebar,openSettings,requestExplorer,showChat,openTerminal,closeTerminal,dockRect}) {
  const id=useCurrent(s=>s.key), list=useSessions(s=>s), spaces=useWorkspaces(s=>s), p=usePrefs(s=>s), session=list.byId[id];
  const [search,setSearch]=React.useState(false),[query,setQuery]=React.useState(''),[menu,setMenu]=React.useState(null);
  const dock=useDock(s=>s),[terminalMenu,setTerminalMenu]=React.useState(null);
  const panel=dock.sessionId===id?dock.panel:'chat';
  const selectedTerminal=dock.terminals.find(tab=>tab.id===dock.selected);
  const lowerTabs=React.useRef(null);
  const focusPanel=kind=>requestAnimationFrame(()=>{const root=lowerTabs.current?.closest('[data-slot="root"]');const target=kind==='chat'?root?.querySelector('[data-slot="main.conversation"] [contenteditable="true"]'):root?.querySelector(`[data-dockkit-content="${CSS.escape(dock.selected)}"] textarea`);target?.focus({preventScroll:true});});
  const selectPanel=(kind,focus=false)=>{if(kind==='chat')showChat();else openTerminal();if(focus)focusPanel(kind);};
  const drag=React.useRef(false);
  const workspace=spaces.items.find(w=>w.sessionIds.includes(id));
  const title=session?.projectionValues?.title||(session?.blank?'新会话':session?.displayTitle)||'Agent 对话';
  const actions=[['项目概览','linkmind-workbench'],['文件','files'],['控制会话与摄像头','linkmind-camera'],['任务图','linkmind-graph'],['运行配置','linkmind-project'],['终端','terminal']];
  const results=list.ids.map(key=>list.byId[key]).filter(s=>s&&s.origin!=='subagent'&&!spaces.archivedSessionIds.includes(s.id)&&(s.displayTitle||'').toLowerCase().includes(query.toLowerCase()));
  const actionButton=(label,name,action,pressed)=>h(ui.Tooltip,{label,portal:true},h(ui.Button,{size:'sm',variant:'ghost','aria-label':label,'aria-pressed':pressed,onClick:action},icon(name,20)));
  const select=value=>{setMenu(null);if(value==='project')requestExplorer('project');else if(value==='chat')requestExplorer('chat');else if(value==='folder')requestExplorer('folder');else if(value==='settings')openSettings();else openPage(value);};
  return h('div',{className:'lm-studio-chrome'},
   h('header',{className:'lm-titlebar'},h('div',{className:'lm-brand'},icon('IconAgentPresetOutlineRegular',23),'LinkMind Studio'),
    h('nav',{className:'lm-title-menu','aria-label':'工作台菜单'},...['文件','视图'].map(label=>h('button',{key:label,onClick:e=>setMenu({label,anchor:e.currentTarget})},label))),
    h('button',{className:'lm-quick-search',onClick:()=>setSearch(true),'aria-label':'搜索会话和视图'},icon('IconSearchOutlineRegular',15),h('span',null,'搜索会话、视图…'),h('kbd',null,'搜索')),
    h('div',{className:'lm-agent-state','data-running':!!session?.running},h('i',{className:'lm-status-dot'}),session?.running?'Agent 正在运行':'Agent 就绪'),actionButton('插件与设置','IconSettingsOutlineRegular',openSettings)),
   h('nav',{className:'lm-activity','aria-label':'工作台活动栏'},actionButton('项目会话目录','IconFolderOpenOutlineRegular',toggleSidebar),actionButton('搜索会话','IconSearchOutlineRegular',()=>setSearch(true)),actionButton('项目概览','IconLayersOutlineRegular',()=>openPage('linkmind-workbench')),actionButton('控制会话与摄像头','IconEyeOutlineRegular',()=>openPage('linkmind-camera')),actionButton('任务图','IconBranchOutlineRegular',()=>openPage('linkmind-graph')),actionButton('项目文件','IconCodeOutlineRegular',()=>openPage('files')),h('div',{className:'lm-activity-spacer'}),actionButton('运行配置','IconPlayOutlineRegular',()=>openPage('linkmind-project'))),
   h('div',{className:'lm-chat-tabs',ref:lowerTabs,style:dockRect?{top:dockRect.top,left:dockRect.left,right:'auto',width:dockRect.width}:undefined},
    h('div',{role:'tablist','aria-label':'下方工作面板',onKeyDown:e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'chat':e.key==='End'?'terminal':panel==='chat'?'terminal':'chat';selectPanel(next);e.currentTarget.querySelector(`[data-panel="${next}"]`)?.focus();}}},
     ...[['chat','Agent 对话','IconNewChatOutlineRegular'],['terminal','终端','IconCodeOutlineRegular']].map(([kind,label,name])=>h('button',{key:kind,role:'tab','data-panel':kind,'aria-selected':panel===kind,tabIndex:panel===kind?0:-1,onClick:()=>selectPanel(kind,true)},icon(name,16),label,kind==='terminal'&&dock.terminals.length>0?` (${dock.terminals.length})`:null))),
    panel==='terminal'?h('div',{className:'lm-terminal-actions'},h('button',{className:'lm-terminal-picker','aria-label':'选择终端','aria-haspopup':'menu','aria-expanded':!!terminalMenu,onClick:e=>setTerminalMenu(e.currentTarget)},selectedTerminal?.title||'终端',' ▾'),h('button',{'aria-label':'新建终端',onClick:()=>openTerminal({create:true})},icon('IconPlusOutlineRegular',16)),h('button',{'aria-label':'关闭当前终端',title:'关闭终端并结束其中的进程',onClick:closeTerminal},icon('IconCloseOutlineRegular',16))):h('span',{className:'lm-chat-title',title},title)),
   dock.error&&h('div',{className:'lm-dock-error',role:'alert'},dock.error,h(ui.Button,{size:'sm',variant:'ghost',onClick:()=>openTerminal()},'重试')),
   h(ui.Menu,{open:!!terminalMenu,anchor:null,anchorRef:{current:terminalMenu},returnFocus:()=>terminalMenu,portal:true,autoFocus:true,onClose:()=>setTerminalMenu(null),onSelect:tabId=>{setTerminalMenu(null);openTerminal({tabId});},items:dock.terminals.map((tab,index)=>({id:tab.id,label:`${index+1}. ${tab.title||'终端'}`}))}),
   h('footer',{className:'lm-statusbar'},h('span',null,'具身模式'),h('span',{className:'lm-status-path',title:workspace?.path||session?.cwd},workspace?.path||session?.cwd||'未选择工作区'),h('span',null,'DSH · 原生会话')),
   h('div',{className:'lm-side-grip',role:'separator',tabIndex:0,'aria-label':'调整项目目录宽度','aria-orientation':'vertical','aria-valuenow':p.explorer||260,'aria-valuemin':210,'aria-valuemax':420,onPointerDown:e=>{drag.current=true;e.currentTarget.setPointerCapture(e.pointerId);},onPointerMove:e=>{if(drag.current)setPreference({explorer:Math.min(420,Math.max(210,e.clientX-48))});},onPointerUp:e=>{drag.current=false;e.currentTarget.releasePointerCapture(e.pointerId);},onPointerCancel:()=>{drag.current=false;},onKeyDown:e=>{if(['ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();setPreference({explorer:e.key==='Home'?260:Math.max(210,Math.min(420,(p.explorer||260)+(e.key==='ArrowLeft'?-10:10)))});}}}),
   h(ui.Menu,{open:!!menu,anchor:null,anchorRef:{current:menu?.anchor||null},returnFocus:()=>menu?.anchor||null,portal:true,autoFocus:true,onClose:()=>setMenu(null),onSelect:select,items:menu?.label==='文件'?[{id:'project',label:'打开项目文件夹…'},{id:'chat',label:'在所选位置新建会话'},{id:'folder',label:'在所选位置新建文件夹'},{id:'files',label:'查看项目文件'}]:[...actions.map(([label,id])=>({id,label})),{id:'settings',label:'插件与设置'}]}),
   h(ui.Modal,{open:search,onClose:()=>setSearch(false),title:'搜索与快速打开',closeLabel:'关闭'},h('input',{className:'lm-command-input',autoFocus:true,'aria-label':'搜索会话和视图名称',value:query,onChange:e=>setQuery(e.target.value),placeholder:'输入会话名称，或打开一个视图…'}),h('div',{className:'lm-command-list'},...actions.filter(([label])=>label.includes(query)).map(([label,kind])=>h(ui.Button,{key:kind,variant:'ghost',onClick:()=>{setSearch(false);openPage(kind);}},label,h('small',null,'视图'))),...results.slice(0,30).map(s=>h(ui.Button,{key:s.id,variant:'ghost',onClick:()=>{setSearch(false);openSession(s.id);}},s.projectionValues?.title||s.displayTitle,h('small',null,spaces.items.find(w=>w.sessionIds.includes(s.id))?.title||s.cwd?.split('/').at(-1)))))));
 };
}
