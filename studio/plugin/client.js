// DSH owns the conversation, streaming and steering. This is its native side pane.
window.__ModuleLoader__.load({id:'@linkmind/dsh-studio', factory:require => {
  const React=require('react'), h=React.createElement;
  const {Button,writeClipboard}=require('@deepseek-ai/dsh-client-ui-primitives');
  const active=run=>['starting','ready','running','finishing','stopping'].includes(run?.status);
  const statusText={starting:'正在准备',ready:'仿真运行中',running:'程序运行中',finishing:'正在结束',completed:'执行已结束',stopping:'正在停止',stopped:'已停止',failed:'运行失败',interrupted:'已中断',timed_out:'已超时',cleanup_failed:'子进程未能完全停止'};
  const cameraNames={head:'主摄像头',wrist_l:'左腕摄像头',wrist_r:'右腕摄像头'};
  const muted={fontSize:12,color:'var(--dsw-alias-label-secondary, currentColor)',lineHeight:1.6};
  const selectStyle={font:'inherit',color:'inherit',background:'var(--dsw-alias-background-primary, transparent)',padding:6,borderRadius:6,border:'1px solid color-mix(in srgb, currentColor 18%, transparent)',minWidth:0,maxWidth:'100%'};
  const preStyle={fontSize:12,lineHeight:1.6,whiteSpace:'pre-wrap',overflowWrap:'anywhere',overflowY:'auto',maxHeight:240,margin:'8px 0 0'};
  async function api(path,data,signal) {
    const response=await fetch('/linkmind/api'+path,data===undefined?{cache:'no-store',signal}:
      {method:'POST',headers:{'Content-Type':'application/json','X-LinkMind-Request':'1'},body:JSON.stringify(data),signal});
    const value=await response.json();
    if(!response.ok)throw new Error(value.error||'请求失败');
    return value;
  }
  async function follow(runId,signal,onValue) {
    const response=await fetch(`/linkmind/api/runs/${encodeURIComponent(runId)}/stream`,{signal,cache:'no-store'});
    if(!response.ok)throw new Error('暂时无法连接运行服务');
    const reader=response.body.getReader(), decoder=new TextDecoder();
    let pending='';
    try {
      while(true) {
        const {value,done}=await reader.read();if(done)return false;
        pending+=decoder.decode(value,{stream:true});
        let end;
        while((end=pending.indexOf('\n\n'))>=0) {
          const event=pending.slice(0,end);pending=pending.slice(end+2);
          const line=event.split('\n').find(line=>line.startsWith('data: '));
          if(line) {const run=JSON.parse(line.slice(6));onValue(run);if(!active(run))return true;}
        }
      }
    } finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
  }
  const projectCopy={
    zh:{title:'项目与配置',description:'浏览工作区文件，编辑和运行项目配置',files:'浏览文件',refresh:'刷新',defaultWorkspace:'默认 Studio 工作区',directory:'项目目录',browse:'浏览目录',openWorkspace:'作为工作区打开',workspaceHint:'选择本地仓库目录，例如 HexaShell。文件、配置与代码保留在原目录。',configurations:'运行配置',empty:'这个工作区还没有运行配置',emptyHint:'新建配置并填写项目的启动命令，或让会话助手根据 README 准备配置。',loading:'正在读取项目…',new:'新建配置',duplicate:'复制所选配置',edit:'编辑配置文件',save:'保存配置',cancel:'放弃草稿并刷新',editorHint:'编辑当前项目的 linkmind.studio.json。argv 是程序与参数数组；{project} 是项目目录，{output} 是本次输出目录。保存后才可运行。',draft:'未保存草稿',run:'运行所选配置',starting:'正在启动…',selected:'所选配置',command:'启动命令',metadata:'模型与任务说明',checks:'环境检查',ready:'路径检查通过',missing:'缺少所需文件或程序',unchecked:'未声明环境检查',active:'项目正在运行，请结束运行后再编辑配置',noSelection:'请先选择一个配置',copy:'复制会话指令',copied:'启动指令已复制，可粘贴到会话中发送',copyFailed:'复制失败，请在会话中说明要运行的配置名',saved:'配置已保存',readError:'无法读取项目',invalid:'配置有误，修正并保存后才能运行',current:'当前工作区',hint:'会话助手与此面板使用同一份配置。配置中的模型和命令决定实际运行方案。',prompt:'打开项目 {path}，使用已有的 {name} 配置实际启动一次。保持配置中的模型、场景和预算，不重新搭建方案。启动后告诉我运行状态。',template:'新配置',missingScript:'请替换为项目实际的入口文件',newHint:'默认工作区用于整理自己的项目；已有代码库可以直接作为工作区打开。'},
    en:{title:'Project & configurations',description:'Browse workspace files, edit and run project configurations',files:'Browse files',refresh:'Refresh',defaultWorkspace:'Default Studio workspace',directory:'Project directory',browse:'Browse directory',openWorkspace:'Open as workspace',workspaceHint:'Choose a local repository, such as HexaShell. Files, configurations and code stay in its directory.',configurations:'Run configurations',empty:'This workspace has no run configurations',emptyHint:'Create one with the original launch command, or ask the conversation assistant to prepare it from the README.',loading:'Reading project…',new:'New configuration',duplicate:'Duplicate selected',edit:'Edit configuration file',save:'Save configurations',cancel:'Discard draft and reload',editorHint:'Edit linkmind.studio.json in this project. argv is a program and argument array; {project} is the project directory and {output} is the new run output. Save before running.',draft:'Unsaved draft',run:'Run selected configuration',starting:'Starting…',selected:'Selected configuration',command:'Launch command',metadata:'Model and task notes',checks:'Environment checks',ready:'Path checks passed',missing:'Required files or executables are missing',unchecked:'No environment checks declared',active:'This project is running. End the run before editing its configurations.',noSelection:'Select a configuration first',copy:'Copy conversation instruction',copied:'Instruction copied; paste it into the conversation to send',copyFailed:'Copy failed; name the configuration in the conversation',saved:'Configuration saved',readError:'Unable to read project',invalid:'Fix and save the configuration before running',current:'Current workspace',hint:'The conversation assistant and this panel share the same file. Its model settings and command define the actual run.',prompt:'Open project {path} and start its existing {name} configuration. Keep its model, scenario and budget unchanged. Report the run status.',template:'New configuration',missingScript:'Replace with the project’s real entry point',newHint:'Use the default workspace for your own projects, or open an existing repository directly.'}
  };
  // Preserve unsaved edits and uncertain start receipts across pane/session switches.
  const projectDrafts=new Map(), projectSelections=new Map(), startRequests=new Map(), goalDrafts=new Map(), cameraSelections=new Map();
  const bookNames={reproduce:'复现',optimize:'优化',develop:'开发',ready:'待推进',active:'进行中',blocked:'受阻',paused:'已暂停',review:'待验收',closed:'已结项',planned:'待开始',done:'已完成',cancelled:'已取消',achieved:'目标达成',not_achieved:'未达成',inconclusive:'证据不足',decision:'决定',finding:'发现',hypothesis:'假设',blocker:'阻塞',evidence:'证据',valid:'有效',obsolete:'已失效',pending:'未验收',met:'满足',not_met:'不满足'};
  function ProjectOverview({registration,sessionId,onSelection,openRun}) {
    const [context,setContext]=React.useState(null),[selected,setSelected]=React.useState(''),[workId,setWorkId]=React.useState('');
    const [editor,setEditorState]=React.useState(null),[error,setError]=React.useState(''),[saving,setSaving]=React.useState(false),[snapshot,setSnapshot]=React.useState(null);
    const message=e=>({'title must be text (1–200 characters)':'请填写目标名称（最多 200 字）','At least one acceptance condition is required':'请至少填写一条验收条件','Finish or explicitly cancel remaining work before acceptance':'还有未完成的工作，请完成或注明取消原因后再验收','All acceptance conditions need reviewed evidence':'请先逐条评审验收条件，并关联支持判断的证据','Attach evidence before reviewing this condition':'请先登记并选择支持判断的证据','Explain verification or why the work was cancelled':'请填写验证结果或取消原因','Complete dependencies before advancing this work':'请先完成此工作的依赖项','Work dependencies contain a cycle':'工作依赖形成了循环，请调整依赖关系','Evidence file does not exist inside the project':'未找到来源文件，请填写项目内的文件路径','Reviewed evidence is immutable; create a correction and review the criterion again':'这条证据已有验收引用，请新建更正记录，再重新评审'}[e.message]||e.message);
    const draftKey=sessionId+':'+registration;
    const setEditor=value=>{if(value)goalDrafts.set(draftKey,value);else goalDrafts.delete(draftKey);setEditorState(value);};
    const refresh=async(signal)=>{const value=await api(`/projects/${registration}/context`,undefined,signal);if(!signal?.aborted){setContext(value);return value;}};
    React.useEffect(()=>{
      const controller=new AbortController();let timer;setContext(null);setSelected('');setWorkId('');setEditorState(goalDrafts.get(draftKey)||null);
      const update=async()=>{try{await refresh(controller.signal);}catch(e){if(!controller.signal.aborted)setError(message(e));}if(!controller.signal.aborted)timer=setTimeout(update,5000);};
      update();return()=>{controller.abort();clearTimeout(timer);};
    },[registration,sessionId]);
    const project=context?.project, goals=project?.objectives||[], goal=goals.find(g=>g.id===selected);
    const work=(project?.work||[]).filter(w=>w.objective_id===selected), records=(project?.records||[]).filter(r=>!r.objective_id||r.objective_id===selected);
    React.useEffect(()=>{if(project&&!selected&&goals.length)setSelected(goals.find(g=>g.state!=='closed')?.id||goals.at(-1).id);},[project,selected]);
    React.useEffect(()=>{onSelection(goal?{objective_id:goal.id,objective_title:goal.title,editing:!!editor,project_revision:project.revision,work_id:work.some(w=>w.id===workId&&!['done','cancelled'].includes(w.state))?workId:'',locked:['closed','paused'].includes(goal.state)}:{loading:!context,editing:!!editor});},[project,selected,workId,editor]);
    const open=(operation,data)=>{setEditor({operation,data:structuredClone(data),revision:project.revision});setError('');};
    const mutate=async(operation,data,revision=project.revision)=>{
      setSaving(true);setError('');
      try{const next=await api(`/projects/${registration}/change`,{session_id:sessionId,revision,operation,data});setContext(next);setEditor(null);
        if(operation==='create_objective'){setSelected(next.project.objectives.at(-1).id);setWorkId('');}
      }catch(e){setError(message(e));await refresh().catch(()=>{});}finally{setSaving(false);}
    };
    const field={display:'flex',flexDirection:'column',gap:8,minWidth:0}, actions={display:'flex',flexWrap:'wrap',gap:8};
    const btn=(label,onClick,disabled=false)=>h(Button,{size:'sm',variant:'outline',onClick,disabled:saving||disabled},label);
    const input=(label,value,onChange,multiline=false)=>h('label',{style:field},label,h(multiline?'textarea':'input',{'aria-label':label,style:{...selectStyle,width:'100%',boxSizing:'border-box',...(multiline?{minHeight:80,resize:'vertical'}:{})},value:value||'',onChange:e=>onChange(e.target.value)}));
    const select=(label,value,options,onChange)=>h('label',{style:field},label,h('select',{'aria-label':label,style:selectStyle,value,disabled:saving||(!!editor&&label==='当前项目目标'),onChange:e=>onChange(e.target.value)},...options.map(([v,l])=>h('option',{value:v,key:v},l))));
    const patch=(key,value)=>setEditor({...editor,data:{...editor.data,[key]:value}});
    const patchChange=(key,value)=>patch('changes',{...editor.data.changes,[key]:value});
    const evidenceOptions=project?.records.filter(r=>r.kind==='evidence'&&r.status==='valid')||[];
    const renderEditor=()=>{
      if(!editor)return null;
      const {operation,data}=editor;
      let fields=[];
      if(operation==='create_objective')fields=[
        select('项目目标类型',data.kind,Object.keys(context.templates).map(k=>[k,bookNames[k]]),v=>patch('kind',v)),
        h('p',{style:muted},context.templates[data.kind].description),
        input('目标名称',data.title,v=>patch('title',v)),input('希望交付什么',data.intent,v=>patch('intent',v),true),
        input('验收条件（每行一条）',(data.criteria||[]).join('\n'),v=>patch('criteria',v.split('\n')),true),
        input('约束与预算说明',data.constraints,v=>patch('constraints',v),true),select('关联来源目标',data.parent_id,[['','独立目标'],...goals.map(g=>[g.id,g.title])],v=>patch('parent_id',v))];
      if(operation==='update_objective')fields=[select('目标状态',data.changes.state,['ready','active','blocked','paused','review'].map(k=>[k,bookNames[k]]),v=>patchChange('state',v)),input('目标名称',data.changes.title,v=>patchChange('title',v)),input('希望交付什么',data.changes.intent,v=>patchChange('intent',v),true),input('约束与预算说明',data.changes.constraints,v=>patchChange('constraints',v),true),input('下一步',data.changes.next_action,v=>patchChange('next_action',v),true),input('验收条件（每行一条）',data.changes.criteria.join('\n'),v=>patchChange('criteria',v.split('\n')),true),h('p',{style:muted},'交付、约束或验收条件变更后，需要重新评审；原来的判断保留在修订记录中')];
      if(operation==='save_work')fields=[input('工作名称',data.changes.title,v=>patchChange('title',v)),select('工作状态',data.changes.state,['planned','active','blocked','done','cancelled'].map(k=>[k,bookNames[k]]),v=>patchChange('state',v)),input('验证结果或取消原因',data.changes.verification,v=>patchChange('verification',v),true),
        h('details',null,h('summary',null,'依赖其他工作'),...work.filter(w=>w.id!==data.id).map(w=>h('label',{key:w.id,style:{display:'flex',gap:8,padding:'6px 0'}},h('input',{type:'checkbox',checked:(data.changes.depends_on||[]).includes(w.id),onChange:e=>patchChange('depends_on',e.target.checked?[...(data.changes.depends_on||[]),w.id]:(data.changes.depends_on||[]).filter(id=>id!==w.id))}),w.title)))];
      if(operation==='save_record')fields=[select('记录类型',data.kind,['decision','finding','hypothesis','blocker','evidence'].map(k=>[k,bookNames[k]]),v=>patch('kind',v)),input('记录内容',data.text,v=>patch('text',v),true),input('来源（项目内文件、网址或 run:编号）',data.reference,v=>patch('reference',v)),select('记录状态',data.status||'valid',['valid','obsolete'].map(k=>[k,bookNames[k]]),v=>patch('status',v))];
      if(operation==='review_criterion')fields=[select('验收判断',data.verdict,['pending','met','not_met'].map(k=>[k,bookNames[k]]),v=>patch('verdict',v)),h('p',{style:muted},'选择支持判断的证据；程序退出和助手陈述不自动代表目标达成'),...evidenceOptions.map(r=>h('label',{key:r.id,style:{display:'flex',gap:8,overflowWrap:'anywhere'}},h('input',{type:'checkbox',checked:data.evidence_ids.includes(r.id),onChange:e=>patch('evidence_ids',e.target.checked?[...data.evidence_ids,r.id]:data.evidence_ids.filter(id=>id!==r.id))}),r.text)),!evidenceOptions.length&&h('p',{style:muted},'请先登记文件或运行证据')];
      if(operation==='close_objective')fields=[select('项目结论',data.outcome,['achieved','not_achieved','inconclusive','cancelled'].map(k=>[k,bookNames[k]]),v=>patch('outcome',v)),input('结项说明',data.conclusion,v=>patch('conclusion',v),true)];
      return h('section',{'aria-label':'项目编辑',style:{...field,padding:12,border:'1px solid color-mix(in srgb, currentColor 18%, transparent)',borderRadius:8}},
        ...fields,error&&h('p',{role:'alert',style:muted},error),h('div',{style:actions},btn(saving?'正在保存…':'保存项目内容',()=>mutate(operation,data,editor.revision)),btn('放弃草稿',()=>{setEditor(null);setError('');})),
        editor.revision!==project.revision&&h('div',{style:field},h('p',{style:muted},'项目在编辑期间已更新。下方显示当前内容；请核对后再应用草稿。'),btn('已核对，使用当前版本',()=>setEditor({...editor,revision:project.revision}))));
    };
    if(!context)return h('section',null,h('p',{role:error?'alert':'status',style:muted},error||'正在读取项目目标…'),error&&btn('重试',()=>refresh().then(()=>setError('')).catch(e=>setError(message(e)))));
    return h('section',{'aria-label':'项目概览',style:field},
      h('div',{style:actions},h('span',{style:{fontWeight:500,flex:1}},'项目概览'),btn('新建目标',()=>open('create_objective',{kind:'reproduce',title:'',intent:'',criteria:[''],constraints:'',parent_id:''}),!!editor),btn('刷新项目',()=>refresh().then(()=>setError('')).catch(e=>setError(message(e))))),
      h('p',{style:{...muted,margin:0}},'目标、进展与证据跨会话保存。关闭应用会停止执行；预算说明暂不自动执行。'),
      error&&!editor&&h('p',{role:'alert',style:{...muted,margin:0}},error),
      goals.length?select('当前项目目标',selected,goals.map(g=>[g.id,`${bookNames[g.kind]} · ${g.title} · ${bookNames[g.state]}`]),v=>{setSelected(v);setWorkId('');}):h('p',{style:muted},'这个工作区还没有项目目标。选择复现、优化或开发，并约定交付和验收条件。'),
      renderEditor(),
      goal&&h(React.Fragment,null,
        h('div',{style:{fontWeight:500,overflowWrap:'anywhere'}},goal.title),
        goal.parent_id&&h('p',{style:muted},'来源目标：'+(goals.find(g=>g.id===goal.parent_id)?.title||goal.parent_id)),
        h('p',{style:{margin:'4px 0',whiteSpace:'pre-wrap',overflowWrap:'anywhere'}},goal.intent),
        goal.constraints&&h('p',{style:muted},'约束：'+goal.constraints),
        goal.state!=='closed'&&h('p',{style:{margin:'4px 0',whiteSpace:'pre-wrap'}},'下一步：'+(goal.next_action||'尚未记录')),
        goal.conclusion&&h('p',null,bookNames[goal.outcome]+' · '+goal.conclusion),
        h('div',{style:actions},goal.state!=='closed'&&btn('编辑目标',()=>open('update_objective',{id:goal.id,changes:{state:goal.state,title:goal.title,intent:goal.intent,constraints:goal.constraints,next_action:goal.next_action,criteria:goal.criteria.map(c=>c.text)}}),!!editor),
          goal.state!=='closed'&&btn(goal.state==='paused'?'继续目标':'暂停目标',()=>mutate('update_objective',{id:goal.id,changes:{state:goal.state==='paused'?'ready':'paused'}}),!!editor),
          goal.state!=='closed'?btn('验收结项',()=>open('close_objective',{id:goal.id,outcome:'achieved',conclusion:''}),!!editor):btn('重新评审',()=>mutate('update_objective',{id:goal.id,changes:{state:'review'}}),!!editor)),
        h('details',null,h('summary',null,`工作进展 · ${work.filter(w=>w.state==='done').length}/${work.length}`),h('div',{style:{...field,marginTop:8}},...work.map(w=>h('div',{key:w.id,style:{...field,padding:'8px 0',borderBottom:'1px solid color-mix(in srgb, currentColor 12%, transparent)'}},h('div',null,bookNames[w.state]+' · '+w.title),w.verification&&h('div',{style:muted},w.verification),h('div',null,btn('更新工作',()=>open('save_work',{id:w.id,changes:{title:w.title,state:w.state,verification:w.verification,depends_on:w.depends_on,evidence_ids:w.evidence_ids}}),!!editor||goal.state==='closed')))),btn('添加工作',()=>open('save_work',{objective_id:goal.id,changes:{title:'',state:'planned',verification:'',depends_on:[],evidence_ids:[]}}),!!editor||goal.state==='closed'))),
        h('details',null,h('summary',null,'验收条件'),h('div',{style:{...field,marginTop:8}},...goal.criteria.map(c=>h('div',{key:c.id,style:field},h('span',null,bookNames[c.verdict]+' · '+c.text),h('div',null,btn('评审此条件',()=>open('review_criterion',{objective_id:goal.id,id:c.id,verdict:c.verdict,evidence_ids:c.evidence_ids}),!!editor||goal.state==='closed')))))),
        goal.state!=='closed'&&select('本次运行关联的工作',workId,[['','仅关联当前目标'],...work.filter(w=>!['done','cancelled'].includes(w.state)).map(w=>[w.id,w.title])],setWorkId)),
      h('details',null,h('summary',null,`决定与证据 · ${records.length}`),h('div',{style:{...field,marginTop:8}},...records.map(r=>h('div',{key:r.id,style:field},h('div',{style:{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}},`${bookNames[r.kind]}${r.status==='obsolete'?' · 已失效':''} — ${r.text}`),r.reference&&h('div',{style:muted},r.reference),h('div',null,btn('修订记录',()=>open('save_record',{id:r.id,kind:r.kind,text:r.text,reference:r.reference,objective_id:r.objective_id,status:r.status}),!!editor)))),btn('添加记录或证据',()=>open('save_record',{kind:'decision',text:'',reference:'',objective_id:goal?.id||'',status:'valid'}),!!editor))),
      context.runs.length>0&&h('details',null,h('summary',null,`项目运行记录 · ${context.runs.length}`),h('div',{style:{...field,marginTop:8}},...context.runs.slice(0,30).map(r=>h('div',{key:r.id,style:field},h('div',null,`${r.recipe_id} · ${statusText[r.status]||r.status}`),h('div',{style:muted},r.project_context?.objective_title||'历史运行 / 未关联目标'),h('div',{style:actions},btn('查看运行',()=>openRun(r.id)),btn('登记为证据',()=>open('save_record',{kind:'evidence',text:`运行 ${r.recipe_id} 的原始记录（请补充结论和适用范围）`,reference:'run:'+r.id,objective_id:goal?.id||'',status:'valid'}),!!editor)))))),
      h('details',null,h('summary',null,'项目修订记录'),...context.history.slice(0,15).map(e=>h('div',{key:e.revision,style:{...field,marginTop:8}},h('span',{style:muted},`v${e.revision} · ${e.actor} · ${e.operation} · ${new Date(e.at).toLocaleString()}`),btn('查看 v'+e.revision,()=>api(`/projects/${registration}/revision`,{revision:e.revision}).then(setSnapshot).catch(e=>setError(message(e)))))),snapshot&&h('div',null,btn('关闭历史快照',()=>setSnapshot(null)),h('pre',{style:preStyle},JSON.stringify(snapshot,null,2)))));
  }
  function ProjectButton({sessionId,useSessions,open,t}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    return preset==='linkmind-embodied'?h(Button,{size:'sm',variant:'toolbar',onClick:open},t('title')):null;
  }
  function ProjectPanel({sessionId,useSessions,openFiles,openRun,chooseDirectory,openWorkspace,t,copyInstruction}) {
    const cwd=useSessions(s=>s.byId[sessionId]?.cwd||s.byId[sessionId]?.projectionValues?.workingDirectory);
    const draftKey=JSON.stringify([sessionId,cwd]);
    const [info,setInfo]=React.useState(null),[selected,setSelectedState]=React.useState(''),[draft,setDraftState]=React.useState(null);
    const [error,setError]=React.useState(''),[notice,setNotice]=React.useState(''),[busy,setBusy]=React.useState('');
    const [directory,setDirectory]=React.useState(cwd||'');
    const [goalContext,setGoalContext]=React.useState({});
    const generation=React.useRef(0);
    const setSelected=value=>{projectSelections.set(draftKey,value);setSelectedState(value);};
    const setDraft=value=>{if(value)projectDrafts.set(draftKey,value);else projectDrafts.delete(draftKey);setDraftState(value);};
    const load=async()=>{
      if(!cwd)return;
      const version=++generation.current;
      try{
        const value=await api('/workspace/open',{path:cwd,session_id:sessionId});
        if(version!==generation.current)return;
        setInfo(value);setError('');const current=projectSelections.get(draftKey);
        setSelected(Object.hasOwn(value.recipes||{},current)?current:Object.keys(value.recipes||{})[0]||'');
      }catch(e){if(version===generation.current)setError(e.message);}
    };
    React.useEffect(()=>{setInfo(null);setGoalContext({loading:true});setError('');setNotice('');setDirectory(cwd||'');setDraftState(projectDrafts.get(draftKey)||null);load();return()=>{generation.current++;};},[sessionId,cwd]);
    React.useEffect(()=>{
      if(!info?.id)return;
      const controller=new AbortController();let timer;
      const update=async()=>{
        try {const state=await api('/state',undefined,controller.signal);
          if(!controller.signal.aborted)setInfo(current=>current&&({...current,active_runs:state.runs.filter(run=>run.kind==='project'&&run.project_path===current.path&&active(run))}));
        }catch{/* Explicit refresh reports service failures; keep the last known lock meanwhile. */}
        if(!controller.signal.aborted)timer=setTimeout(update,3000);
      };
      timer=setTimeout(update,3000);return()=>{controller.abort();clearTimeout(timer);};
    },[info?.id]);
    const perform=async(name,fn)=>{setBusy(name);setError('');setNotice('');try{await fn();}catch(e){setError(e.message);}finally{setBusy('');}};
    const edit=()=>setDraft({content:info.configuration.content,revision:info.configuration.revision});
    const add=duplicate=>{
      try{
        const data=JSON.parse(draft?.content||info.configuration.content);
        data.recipes??={};let name=duplicate?selected+'_copy':'new_run',n=2;
        while(Object.hasOwn(data.recipes,name))name=(duplicate?selected+'_copy':'new_run')+'_'+n++;
        data.recipes[name]=duplicate?structuredClone(data.recipes[selected]):{
          argv:['python3','{project}/run.py','--output','{output}'],
          checks:[{kind:'path',value:'run.py',label:t('missingScript')}],
          timeout_seconds:5400,metadata:{description:t('template')}
        };
        setDraft({content:JSON.stringify(data,null,2)+'\n',revision:draft?.revision||info.configuration.revision});
      }catch(e){setError(e.message);}
    };
    const save=()=>perform('save',async()=>{
      await api(`/projects/${info.id}/configuration`,{session_id:sessionId,...draft});setDraft(null);await load();setNotice(t('saved'));
    });
    const start=()=>perform('start',async()=>{
      const identity=JSON.stringify([info.id,selected,info.configuration.revision,goalContext.objective_id,goalContext.work_id]);
      let request=startRequests.get(identity);if(!request){request=crypto.randomUUID();startRequests.set(identity,request);}
      const run=await api(`/projects/${info.id}/start`,{recipe:selected,request_id:request,config_revision:info.configuration.revision,...goalContext});
      startRequests.delete(identity);await load();openRun(run.id);
    });
    const recipe=info?.recipes?.[selected], check=info?.checks?.[selected];
    const running=info?.active_runs?.length>0, locked=!!busy||running;
    const field={display:'flex',flexDirection:'column',gap:8,minWidth:0};
    const actions={display:'flex',flexWrap:'wrap',gap:8};
    return h('div',{style:{height:'100%',overflowY:'auto',padding:16,fontSize:13,display:'flex',flexDirection:'column',gap:20}},
      h('section',{style:field},h('span',{style:muted},t('current')),h('div',{style:{overflowWrap:'anywhere'}},cwd||t('directory')),
        h('div',{style:actions},h(Button,{size:'sm',variant:'outline',onClick:openFiles},t('files')),h(Button,{size:'sm',variant:'ghost',disabled:!!busy,onClick:()=>perform('refresh',load)},t('refresh')))),
      h('details',null,h('summary',{style:{cursor:'pointer'}},t('openWorkspace')),
        h('div',{style:{...field,marginTop:12}},h('p',{style:{...muted,margin:0}},t('newHint')),
          h(Button,{size:'sm',variant:'outline',disabled:!!busy,onClick:()=>perform('workspace',async()=>{const value=await api('/workspace/default',{});await openWorkspace(value.path);})},t('defaultWorkspace')),
          h('label',{style:field},t('directory'),h('input',{'aria-label':t('directory'),style:selectStyle,value:directory,onChange:e=>setDirectory(e.target.value)})),
          h('div',{style:actions},h(Button,{size:'sm',variant:'outline',disabled:!!busy,onClick:()=>perform('pick',async()=>{const value=await chooseDirectory();if(value)setDirectory(value);})},t('browse')),
            h(Button,{size:'sm',variant:'outline',disabled:!!busy||!directory.trim(),onClick:()=>perform('workspace',()=>openWorkspace(directory.trim()))},t('openWorkspace'))),
          h('p',{style:{...muted,margin:0}},t('workspaceHint')))),
      error&&h('p',{role:'alert',style:{...muted,margin:0,overflowWrap:'anywhere'}},error),
      notice&&h('p',{role:'status',style:{...muted,margin:0}},notice),
      !info&&!error&&h('p',{role:'status'},t('loading')),
      info&&h(React.Fragment,null,
        h(ProjectOverview,{key:info.id,registration:info.id,sessionId,onSelection:setGoalContext,openRun}),
        h('section',{style:field},h('span',null,t('configurations')),
          info.configuration.error&&h('p',{role:'alert',style:{...muted,margin:0}},t('invalid')+' — '+info.configuration.error),
          Object.keys(info.recipes||{}).length?h('div',{role:'radiogroup','aria-label':t('configurations'),style:field},
            ...Object.entries(info.recipes).map(([name,r])=>h('label',{key:name,style:{display:'flex',alignItems:'flex-start',gap:8,padding:'8px 0',cursor:'pointer',borderBottom:'1px solid color-mix(in srgb, currentColor 12%, transparent)'}},
              h('input',{type:'radio',name:'linkmind-recipe-'+sessionId,value:name,checked:selected===name,onChange:()=>setSelected(name),style:{marginTop:3}}),
              h('span',{style:{minWidth:0,overflowWrap:'anywhere'}},h('span',{style:{fontWeight:500}},name),h('span',{style:{...muted,display:'block'}},[r.metadata?.model,r.metadata?.task,r.metadata?.description].filter(Boolean).join(' · ')))))):
            h('div',null,h('p',{style:{margin:'0 0 8px'}},t('empty')),h('p',{style:{...muted,margin:0}},t('emptyHint'))),
          h('div',{style:actions},h(Button,{size:'sm',variant:'outline',disabled:locked,onClick:()=>add(false)},t('new')),
            h(Button,{size:'sm',variant:'ghost',disabled:locked||!recipe||!!draft,onClick:()=>add(true)},t('duplicate')),
            h(Button,{size:'sm',variant:'ghost',disabled:locked||!!draft,onClick:edit},t('edit')))),
        running&&h('p',{role:'status',style:{...muted,margin:0}},t('active')),
        draft&&h('section',{style:field},h('label',{style:field},t('draft'),h('textarea',{'aria-label':'linkmind.studio.json',spellCheck:false,value:draft.content,onChange:e=>setDraft({...draft,content:e.target.value}),style:{...selectStyle,fontFamily:'monospace',fontSize:12,lineHeight:1.6,minHeight:280,resize:'vertical',width:'100%',boxSizing:'border-box'}})),
          h('p',{style:{...muted,margin:0}},t('editorHint')),
          h('div',{style:actions},h(Button,{size:'sm',disabled:locked,onClick:save},t('save')),h(Button,{size:'sm',variant:'ghost',disabled:!!busy,onClick:()=>{setDraft(null);load();}},t('cancel')))),
        recipe&&h('section',{style:field},h('span',null,t('selected')+' · '+selected),
          h('div',null,h('span',{style:muted},t('command')),h('pre',{style:preStyle},JSON.stringify(recipe.argv,null,2))),
          Object.keys(recipe.metadata||{}).length>0&&h('details',null,h('summary',null,t('metadata')),h('pre',{style:preStyle},JSON.stringify(recipe.metadata,null,2))),
          h('div',null,h('span',null,t('checks')),h('p',{style:{...muted,margin:'8px 0'}},!check?.checks?.length?t('unchecked'):check.ready?t('ready'):t('missing')),
            ...((check?.checks)||[]).map((c,i)=>h('div',{key:i,style:{...muted,overflowWrap:'anywhere'}},(c.ready?'✓ ':'— ')+c.label))),
          goalContext.editing&&h('p',{style:muted},'先保存或放弃项目草稿，再运行或复制启动指令'),
          goalContext.locked&&h('p',{style:muted},'当前项目目标已暂停或结项，继续目标或新建目标后再运行'),
          h('div',{style:actions},h(Button,{size:'sm',disabled:locked||!!draft||!!info.configuration.error||!check?.ready||goalContext.locked||goalContext.loading||goalContext.editing,onClick:start},busy==='start'?t('starting'):t('run')),
            h(Button,{size:'sm',variant:'outline',disabled:!!draft||goalContext.editing||goalContext.locked||goalContext.loading,onClick:()=>perform('copy',async()=>{await copyInstruction(cwd,selected,goalContext);setNotice(t('copied'));})},t('copy')))),
        h('p',{style:{...muted,margin:0}},t('hint'))));
  }

  function CameraPanel({sessionId,useSessions}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    const cwd=useSessions(s=>s.byId[sessionId]?.cwd||s.byId[sessionId]?.projectionValues?.workingDirectory);
    const [run,setRun]=React.useState(null),[runs,setRuns]=React.useState([]),[selected,setSelected]=React.useState('');
    const [error,setError]=React.useState(''),[camera,setCamera]=React.useState('head'),[busy,setBusy]=React.useState(false);
    const [disconnected,setDisconnected]=React.useState(false),[imageError,setImageError]=React.useState(false);
    const [log,setLog]=React.useState(''),[logError,setLogError]=React.useState(''),[result,setResult]=React.useState(null);
    const [retry,setRetry]=React.useState(0),[now,setNow]=React.useState(Date.now());
    React.useEffect(()=>{const choose=()=>setSelected(cameraSelections.get(sessionId)||'');choose();setRun(null);setRuns([]);window.addEventListener('linkmind:choose-run',choose);return()=>window.removeEventListener('linkmind:choose-run',choose);},[sessionId,cwd]);
    React.useEffect(()=> {
      setError('');setDisconnected(false);
      if(preset!=='linkmind-embodied')return;
      const controller=new AbortController();let timer;
      const update=async()=> {
        try {
          const state=await api('/state',undefined,controller.signal);
          const mine=state.runs.filter(r=>r.task_snapshot?.session_id===sessionId||(r.kind==='project'&&r.project_path===cwd));
          const chosen=selected?mine.find(r=>r.id===selected):mine[0];
          if(!controller.signal.aborted){setRuns(mine);setRun(current=>current?.id===chosen?.id?current:chosen||null);setError('');}
        } catch(e){if(!controller.signal.aborted)setError('无法连接运行服务，请检查 LinkMind 插件是否已启用');}
        if(!controller.signal.aborted)timer=setTimeout(update,1500);
      };
      update();return()=>{controller.abort();clearTimeout(timer);};
    },[sessionId,preset,selected,cwd]);
    React.useEffect(()=> {
      if(!run?.id)return;
      const controller=new AbortController();let timer;
      const connect=async()=> {
        try {
          const ended=await follow(run.id,controller.signal,next=>{if(!controller.signal.aborted){setRun(next);setDisconnected(false);}});
          if(ended)return;
        } catch(e){if(!controller.signal.aborted)setDisconnected(true);}
        if(!controller.signal.aborted)timer=setTimeout(connect,1500);
      };
      connect();return()=>{controller.abort();clearTimeout(timer);};
    },[run?.id]);
    React.useEffect(()=> {
      setLog('');setResult(null);setLogError('');
      if(run?.kind!=='project')return;
      const controller=new AbortController();let timer,offset=0;
      const update=async()=> {
        try {
          const reply=await api(`/project-runs/${run.id}/follow`,{offset},controller.signal);
          if(controller.signal.aborted)return;
          offset=reply.next_offset;
          setLog(text=>(text+reply.log).slice(-32768));setResult(reply.result);setLogError('');
          if(!active(reply.run)&&offset>=reply.run.log_bytes)return;
        } catch(e){if(controller.signal.aborted)return;setLogError('日志暂时未能更新，正在重连');}
        timer=setTimeout(update,1000);
      };
      update();return()=>{controller.abort();clearTimeout(timer);};
    },[run?.id,run?.kind]);
    React.useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
    const project=run?.kind==='project';
    const views=project?Object.fromEntries(Object.keys(run.recipe.cameras||{}).map(id=>[id,cameraNames[id]||id])):cameraNames;
    const view=Object.hasOwn(views,camera)?camera:Object.keys(views)[0];
    const frame=project?run.cameras?.find(c=>c.id===view):run?.camera;
    const image=run&&view&&(frame||(!project&&(run.observation||run.observation_available)))?`/linkmind/api/runs/${run.id}/artifacts/${encodeURIComponent(view)}${project?'':'.png'}?frame=${frame?.frame??run.step??run.observation?.step??0}&retry=${retry}`:null;
    React.useEffect(()=>setImageError(false),[image]);
    const stop=async()=> {
      setBusy(true);
      try{await api(`/runs/${run.id}/stop`,{});setRun(await api(`/runs/${run.id}/live`));setError('');}
      catch(e){setError(e.message);}finally{setBusy(false);}
    };
    const age=frame?Math.max(0,Math.floor((now-frame.captured_at*1000)/1000)):null;
    return h('div',{style:{height:'100%',overflowY:'auto',padding:16,fontSize:13,display:'flex',flexDirection:'column',gap:16}},
      runs.length>0&&h('label',{style:{display:'flex',flexDirection:'column',gap:8}},'当前工作区与会话的运行',
        h('select',{'aria-label':'选择运行记录',value:selected,onChange:e=>setSelected(e.target.value),style:selectStyle},
          h('option',{value:''},'跟随最新运行'),
          ...runs.map(r=>h('option',{key:r.id,value:r.id},`${r.recipe_id||r.task} · ${new Date(r.created_at).toLocaleTimeString()} · ${statusText[r.status]||r.status}`)))),
      run&&h('div',null,
        project&&h('div',{style:{overflowWrap:'anywhere',marginBottom:8}},`${run.project_name} / ${run.recipe_id}`),
        h('div',{role:'status'},`${statusText[run.status]||run.status}${project?(run.elapsed_seconds?` · ${Math.round(run.elapsed_seconds)} 秒`:''):` · 控制步 ${run.step??run.observation?.step??'—'}`}`),
        project&&h('div',{style:muted},`版本 ${run.source?.commit?.slice(0,8)||'未记录'}${run.source?.dirty?' · 有本地修改':''}`),
        run.error&&h('p',{role:'alert',style:muted},run.error),
        run.camera_error&&h('p',{role:'status',style:muted},'摄像头暂时未能更新，当前保留最近画面'),
        disconnected&&h('p',{role:'status',style:muted},'连接中断，正在重连；当前显示最后收到的状态')),
      error&&h('p',{role:'alert',style:{margin:0}},error),
      h('div',{style:{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}},
        Object.keys(views).length>0&&h('label',{style:{display:'flex',alignItems:'center',gap:8,minWidth:0}},'视角',
          h('select',{'aria-label':'摄像头视角',value:view,onChange:e=>setCamera(e.target.value),style:selectStyle},
            ...Object.entries(views).map(([key,name])=>h('option',{key,value:key},name)))),
        active(run)&&h(Button,{size:'sm',variant:'outline',disabled:busy,onClick:stop,style:{marginLeft:'auto'}},busy?'正在停止…':project?'停止运行':'停止仿真')),
      image?h('figure',{style:{margin:0}},
        h('img',{src:image,alt:views[view],onError:()=>setImageError(true),style:{display:'block',width:'100%',aspectRatio:'4 / 3',maxHeight:'42vh',objectFit:'contain',background:'#151515',borderRadius:8}}),
        h('figcaption',{style:{...muted,marginTop:8}},imageError?'画面暂时不可用':age===null?'最近一次观察':`最近画面 · ${age} 秒前`),
        imageError&&h(Button,{size:'sm',variant:'ghost',onClick:()=>setRetry(value=>value+1)},'重试画面')):
        h('p',{style:{...muted,margin:0}},project?(Object.keys(views).length?'等待程序输出摄像头画面':'该方案未配置摄像头输出'):run?.status==='starting'?'正在连接仿真摄像头…':'在会话里打开项目或描述仿真任务。运行后，这里会显示过程与画面。'),
      project&&h('section',{'aria-label':'运行日志'},h('div',null,'程序输出'),
        h('pre',{style:preStyle},log||'等待程序输出…'),
        logError&&h('p',{role:'status',style:muted},logError),
        h('p',{style:muted},'显示最近 32 KB，完整日志保存在运行目录')),
      project&&h('details',null,h('summary',null,'配置与结果'),
        h('pre',{style:preStyle},JSON.stringify({metadata:run.recipe.metadata||{},argv:run.argv,output:run.output,result:result??'尚无可显示的 JSON 结果'},null,2)),
        h('p',{style:muted},'程序退出不等于任务成功，请以原始结果为准')),
      run?.artifact_errors?.length>0&&h('p',{role:'alert',style:muted},run.artifact_errors.join('\n')),
      h('p',{style:{...muted,margin:0}},project?'会话用于协助开发；运行按项目配置执行。对话不会自动改变正在执行的策略。':'运行中用“插话发送”引导下一动作段；排队消息按 DSH 的发送设置处理。“停止仿真”结束当前执行。'));
  }
  function CameraButton({open,sessionId,useSessions}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    if(preset!=='linkmind-embodied')return null;
    return h(Button,{size:'sm',variant:'toolbar',onClick:open},'运行与摄像头');
  }
  return {inject:['slots','sidebarRight','sidebarRightTabs','sessions','workspaces','uiWorkspace','locale'],apply(ctx){
    ctx.effect(()=>ctx.locale.register('linkmindProject',projectCopy),'LinkMind project copy');
    const t=ctx.locale.bind('linkmindProject');
    const openProject=sessionId=>ctx.sidebarRight.openTab('linkmind-project',{params:{sessionId}});
    const projectActions=sessionId=>({
      openFiles:()=>ctx.sidebarRight.openTab('files',{params:{sessionId}}),
      openRun:runId=>{cameraSelections.set(sessionId,runId||'');window.dispatchEvent(new Event('linkmind:choose-run'));return ctx.sidebarRight.openTab('linkmind-camera',{params:{sessionId}});},
      chooseDirectory:()=>ctx.uiWorkspace.pickDirectory(),
      openWorkspace:async path=>{
        const workspace=await ctx.workspaces.create({path});let target;
        await ctx.uiWorkspace.openWorkspace(workspace.workspaceId,id=>{target=id;},{agentPreset:'linkmind-embodied'});
        if(target)openProject(target);
      },
      copyInstruction:async(path,name,goal)=>{const association=goal?.objective_id?`\n关联已有项目目标“${goal.objective_title}”（objective_id: ${goal.objective_id}）${goal.work_id?`，工作 work_id: ${goal.work_id}`:''}。先读取最新 project_context，再使用其 project_revision 启动；保留已有目标。`:'';if(!await writeClipboard(t('prompt',{path,name})+association))throw new Error(t('copyFailed'));},
    });
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-project',kind:'linkmind-project',title:()=>t('title'),
      guide:[{id:'linkmind-project',order:-30,title:()=>t('title'),description:()=>t('description')}]}),'LinkMind project tab');
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-project',locale:'linkmindProject',inject:projectActions},ProjectPanel));
    for(const name of ['conversation.hero.options','conversation.session.header.utilities','sidebar.right.tab.files.actions']){
      ctx.slots.inject(name,()=>ctx.slots.register({name,id:'linkmind-project',order:-30,locale:'linkmindProject',inject:sessionId=>({open:()=>openProject(sessionId)})},ProjectButton));
    }

    ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-camera',kind:'linkmind-camera',title:()=> '运行与摄像头',
      guide:[{id:'linkmind-camera',order:-20,title:()=> '运行与摄像头',description:()=> '查看项目输出、运行记录与实时画面'}]}),'LinkMind run tab');
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-camera'},CameraPanel));
    ctx.slots.inject('conversation.session.header.utilities',()=>ctx.slots.register({name:'conversation.session.header.utilities',id:'linkmind-camera',order:-20,
      inject:sessionId=>({open:()=>ctx.sidebarRight.openTab('linkmind-camera',{params:{sessionId}})})},CameraButton));
  }};
}});
