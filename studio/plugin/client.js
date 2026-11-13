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
  const projectDrafts=new Map(), projectSelections=new Map(), startRequests=new Map();
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
    React.useEffect(()=>{setInfo(null);setError('');setNotice('');setDirectory(cwd||'');setDraftState(projectDrafts.get(draftKey)||null);load();return()=>{generation.current++;};},[sessionId,cwd]);
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
      const identity=JSON.stringify([info.id,selected,info.configuration.revision]);
      let request=startRequests.get(identity);if(!request){request=crypto.randomUUID();startRequests.set(identity,request);}
      await api(`/projects/${info.id}/start`,{recipe:selected,request_id:request,config_revision:info.configuration.revision});
      startRequests.delete(identity);await load();openRun();
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
          h('div',{style:actions},h(Button,{size:'sm',disabled:locked||!!draft||!!info.configuration.error||!check?.ready,onClick:start},busy==='start'?t('starting'):t('run')),
            h(Button,{size:'sm',variant:'outline',disabled:!!draft,onClick:()=>perform('copy',async()=>{await copyInstruction(cwd,selected);setNotice(t('copied'));})},t('copy')))),
        h('p',{style:{...muted,margin:0}},t('hint'))));
  }

  function CameraPanel({sessionId,useSessions}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    const [run,setRun]=React.useState(null),[runs,setRuns]=React.useState([]),[selected,setSelected]=React.useState('');
    const [error,setError]=React.useState(''),[camera,setCamera]=React.useState('head'),[busy,setBusy]=React.useState(false);
    const [disconnected,setDisconnected]=React.useState(false),[imageError,setImageError]=React.useState(false);
    const [log,setLog]=React.useState(''),[logError,setLogError]=React.useState(''),[result,setResult]=React.useState(null);
    const [retry,setRetry]=React.useState(0),[now,setNow]=React.useState(Date.now());
    React.useEffect(()=>{setSelected('');setRun(null);setRuns([]);},[sessionId]);
    React.useEffect(()=> {
      setError('');setDisconnected(false);
      if(preset!=='linkmind-embodied')return;
      const controller=new AbortController();let timer;
      const update=async()=> {
        try {
          const state=await api('/state',undefined,controller.signal);
          const mine=state.runs.filter(r=>r.task_snapshot?.session_id===sessionId);
          const chosen=selected?mine.find(r=>r.id===selected):mine[0];
          if(!controller.signal.aborted){setRuns(mine);setRun(current=>current?.id===chosen?.id?current:chosen||null);setError('');}
        } catch(e){if(!controller.signal.aborted)setError('无法连接运行服务，请检查 LinkMind 插件是否已启用');}
        if(!controller.signal.aborted)timer=setTimeout(update,1500);
      };
      update();return()=>{controller.abort();clearTimeout(timer);};
    },[sessionId,preset,selected]);
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
      runs.length>0&&h('label',{style:{display:'flex',flexDirection:'column',gap:8}},'本会话的运行',
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
      openRun:()=>ctx.sidebarRight.openTab('linkmind-camera',{params:{sessionId}}),
      chooseDirectory:()=>ctx.uiWorkspace.pickDirectory(),
      openWorkspace:async path=>{
        const workspace=await ctx.workspaces.create({path});let target;
        await ctx.uiWorkspace.openWorkspace(workspace.workspaceId,id=>{target=id;},{agentPreset:'linkmind-embodied'});
        if(target)openProject(target);
      },
      copyInstruction:async(path,name)=>{if(!await writeClipboard(t('prompt',{path,name})))throw new Error(t('copyFailed'));},
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
