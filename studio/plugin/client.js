// Native dsh conversation slots and session side panel. Experience remains source data.
window.__ModuleLoader__.load({id:'@linkmind/dsh-studio', factory:require => {
  const React=require('react'), h=React.createElement;
  const button={border:'1px solid color-mix(in srgb, currentColor 18%, transparent)',borderRadius:8,
    padding:'7px 11px',background:'transparent',color:'inherit',cursor:'pointer',font:'inherit'};
  const muted={fontSize:12,opacity:.66,lineHeight:1.6};
  const section={padding:'18px 0',borderBottom:'1px solid color-mix(in srgb, currentColor 12%, transparent)'};
  const select={width:'100%',padding:9,borderRadius:7,border:button.border,background:'transparent',color:'inherit',font:'inherit'};
  const statusText={starting:'正在准备仿真',ready:'执行中',finishing:'正在收束',completed:'已结束',stopping:'正在停止',stopped:'已停止',failed:'运行失败',interrupted:'已中断'};
  async function api(path,data) {
    const response=await fetch('/linkmind/api'+path,data===undefined?{cache:'no-store'}:
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const value=await response.json();
    if(!response.ok) throw new Error(value.error||'请求失败');
    return value;
  }
  function Panel({sessionId,draft,useSessions}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    const [state,setState]=React.useState(null), [error,setError]=React.useState('');
    const [task,setTask]=React.useState('push_T'), [experience,setExperience]=React.useState(null);
    const [chosenRun,setChosenRun]=React.useState(''), [notice,setNotice]=React.useState('');
    const [tick,setTick]=React.useState(0), [busy,setBusy]=React.useState(false);
    React.useEffect(()=> {
      if(preset!=='linkmind-embodied') return;
      let closed=false,timer;
      const update=async()=> {
        try {const value=await api('/state'); if(!closed){setState(value);setTick(Date.now());}}
        catch(e){if(!closed)setError(e.message);}
        if(!closed)timer=setTimeout(update,2000);
      };
      update();return()=>{closed=true;clearTimeout(timer);};
    },[preset]);
    React.useEffect(()=>{setChosenRun('');setNotice('');},[sessionId]);
    React.useEffect(()=> {
      if(preset!=='linkmind-embodied') return;
      let closed=false;
      setExperience(null);
      api(`/experience/${encodeURIComponent(task)}`).then(value=>{if(!closed)setExperience(value);})
        .catch(e=>{if(!closed)setError(e.message);});
      return()=>{closed=true;};
    },[task,preset]);
    const runs=(state?.runs||[]).filter(r=>r.task_snapshot.session_id===sessionId);
    const run=runs.find(r=>r.id===chosenRun)||runs[0];
    const selectedTask=state?.catalog.find(t=>t.id===task);
    const insert=prompt=>{
      try{draft(sessionId,prompt);setNotice('已放入当前会话输入框，确认后发送。');setError('');}
      catch(e){setError(e.message);}
    };
    const stop=async()=>{
      setBusy(true);
      try{await api(`/runs/${run.id}/stop`,{});setState(await api('/state'));setError('');}
      catch(e){setError(e.message);}finally{setBusy(false);}
    };
    if(preset!=='linkmind-embodied')return h('p',{style:{padding:20}},'在新会话的模式菜单中选择「具身模式 · LinkMind」，即可使用现场与参考经验。');
    return h('div',{style:{height:'100%',overflowY:'auto',padding:'6px 20px 24px',fontSize:13}},
      h('div',{style:section},h('strong',{style:{fontSize:16}},'会话旁的现场'),
        h('p',{style:muted},'在会话里说明目标、查看执行过程、随时引导。这里跟随本会话的仿真，查看观察和结果。')),
      error&&h('p',{role:'alert',style:{color:'#b94848'}},error),
      notice&&h('p',{role:'status',style:muted},notice),
      h('section',{style:section},h('strong',null,'当前执行'),
        runs.length>1&&h('select',{'aria-label':'本会话的执行记录',style:{...select,marginTop:10},value:run?.id||'',onChange:e=>setChosenRun(e.target.value)},
          ...runs.map(r=>h('option',{key:r.id,value:r.id},`${r.task_snapshot.title} · ${statusText[r.status]||r.status} · ${r.id.slice(0,6)}`))),
        !run&&h('p',{style:muted},'本会话还没有启动仿真。先在会话里说清楚要完成什么，以及需要遵守的约束。'),
        run&&h('div',null,
          h('div',{style:{display:'flex',justifyContent:'space-between',alignItems:'center',gap:8,marginTop:12}},
            h('strong',null,statusText[run.status]||run.status),
            ['starting','ready','finishing','stopping'].includes(run.status)&&h('button',{style:{...button,color:'#b94848'},disabled:busy,onClick:stop},busy?'正在停止…':'停止仿真')),
          h('p',null,run.task_snapshot.goal),
          run.task_snapshot.constraints&&h('p',{style:muted},`约束：${run.task_snapshot.constraints}`),
          h('p',{style:muted},`执行 ${run.id} · 步数 ${run.observation?.step??run.progress?.step??'—'}`),
          run.observation&&h('img',{alt:'当前头部相机观察',src:`/linkmind/api/runs/${run.id}/artifacts/head.png?t=${tick}`,
            style:{width:'100%',borderRadius:9,display:'block',background:'#111'}}),
          run.control_fault&&h('p',{role:'alert',style:{color:'#b94848'}},run.control_fault),
          run.error&&h('p',{role:'alert'},run.error),
          h('button',{style:{...button,marginTop:12},onClick:()=>insert(`请查看执行 ${run.id} 的 task_context 和当前观察，解释目前进展。`)},'在会话中查看进展'),
          run.result&&h('details',{style:{marginTop:14}},h('summary',null,'原生运行结果'),h('pre',{style:{whiteSpace:'pre-wrap',fontSize:11}},JSON.stringify(run.result,null,2))),
          h('p',{style:muted},'中途引导在下一步生效。停止会话生成与停止仿真是两个操作。'))),
      h('section',{style:section},h('strong',null,'参考经验'),
        h('p',{style:muted},'查看过去的示范，选择一份交给 Agent 判断是否适用。选择参考不会启动任务，也不会要求照着执行。'),
        h('select',{'aria-label':'参考经验的任务',style:select,value:task,onChange:e=>setTask(e.target.value)},
          ...(state?.catalog||[]).map(t=>h('option',{key:t.id,value:t.id},t.title))),
        experience===null?h('p',{style:muted},'正在读取示范…'):experience.map(item=>h('article',{key:item.id,style:{marginTop:16,padding:12,border:button.border,borderRadius:9}},
          h('strong',null,item.title||item.id),h('p',{style:{...muted,opacity:.85}},item.summary),
          h('p',{style:muted},`TRAIN 示范 · ${item.phase_count??item.phases.length} 个描述片段 · ${item.id}`),
          h('button',{style:button,onClick:()=>insert(`参考经验：${item.title||item.id}（任务 ${task}，经验 ID ${item.id}）。请用 view_experience 查看这份历史材料的来源与局限，再结合当前目标和现场判断是否采用。`)},'引用到会话'),
          h('details',{style:{marginTop:12}},h('summary',null,'查看来源与过程'),
            h('p',{style:{...muted,overflowWrap:'anywhere'}},`来源：${typeof item.source==='string'?item.source:item.source.path||JSON.stringify(item.source)}`),
            h('p',{style:muted},'以下是历史过程的描述，不是当前任务的执行步骤。'),
            ...item.phases.map(phase=>h('div',{key:phase.id,style:{marginTop:10}},h('strong',null,phase.title),h('p',{style:muted},phase.summary))),
            h('p',{style:{...muted,overflowWrap:'anywhere'}},`元数据 SHA-256：${item.metadata_sha256}`)))),
        h('button',{style:{...button,marginTop:14},onClick:()=>insert(`我想在仿真中完成${selectedTask?.title||task}，请先确认目标、约束和准备情况，暂时不要启动或运动。`)},'用这个任务开始讨论')),
      state&&h('p',{style:muted},state.preflight.ready?'本机运行文件已就绪 · 仅仿真':'仿真资源尚未齐备；仍可对话和查看经验。'));
  }
  function SceneButton({open,sessionId,useSessions}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    if(preset!=='linkmind-embodied')return null;
    return h('button',{type:'button',style:button,onClick:open,title:'打开现场与参考经验'},'◈ 现场');
  }
  return {inject:['slots','sidebarRight','sidebarRightTabs','conversation','sessions'],apply(ctx){
    const draft=(sessionId,prompt)=>{
      const binding=ctx.sessions.binding(sessionId);
      if(!binding)throw new Error('会话尚未就绪');
      const result=ctx.conversation.input.requestDraftInitialization(binding,{prompt,whenDraftExists:'append'});
      if(result==='blocked')throw new Error('输入框正在提交，请稍后重试');
    };
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-scene',kind:'linkmind-scene',title:()=> '具身现场',
      guide:[{id:'linkmind-scene',order:-20,title:()=> '具身现场',description:()=> '查看机器人观察与参考经验'}]}),'LinkMind scene tab');
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-scene',inject:()=>({draft})},Panel));
    ctx.slots.inject('conversation.session.header.utilities',()=>ctx.slots.register({name:'conversation.session.header.utilities',id:'linkmind-scene',order:-20,
      inject:sessionId=>({open:()=>ctx.sidebarRight.openTab('linkmind-scene',{params:{sessionId}})})},SceneButton));
  }};
}});
