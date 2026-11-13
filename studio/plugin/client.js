// DSH owns the conversation, streaming and steering. This is its native side pane.
window.__ModuleLoader__.load({id:'@linkmind/dsh-studio', factory:require => {
  const React=require('react'), h=React.createElement;
  const {Button}=require('@deepseek-ai/dsh-client-ui-primitives');
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
        h('img',{src:image,alt:views[view],onError:()=>setImageError(true),style:{display:'block',width:'100%',aspectRatio:'4 / 3',objectFit:'contain',background:'#151515',borderRadius:8}}),
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
  return {inject:['slots','sidebarRight','sidebarRightTabs','sessions'],apply(ctx){
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-camera',kind:'linkmind-camera',title:()=> '运行与摄像头',
      guide:[{id:'linkmind-camera',order:-20,title:()=> '运行与摄像头',description:()=> '查看项目输出、运行记录与实时画面'}]}),'LinkMind run tab');
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-camera'},CameraPanel));
    ctx.slots.inject('conversation.session.header.utilities',()=>ctx.slots.register({name:'conversation.session.header.utilities',id:'linkmind-camera',order:-20,
      inject:sessionId=>({open:()=>ctx.sidebarRight.openTab('linkmind-camera',{params:{sessionId}})})},CameraButton));
  }};
}});
