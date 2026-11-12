// The conversation, streaming and steering are owned entirely by DSH.
window.__ModuleLoader__.load({id:'@linkmind/dsh-studio', factory:require => {
  const React=require('react'), h=React.createElement;
  const {Button}=require('@deepseek-ai/dsh-client-ui-primitives');
  const active=run=>['starting','ready','finishing','stopping'].includes(run?.status);
  const statusText={starting:'正在准备仿真',ready:'仿真运行中',finishing:'正在结束',completed:'已结束',stopping:'正在停止',stopped:'已停止',failed:'运行失败',interrupted:'已中断'};
  const cameraNames={head:'主摄像头',wrist_l:'左腕摄像头',wrist_r:'右腕摄像头'};
  const muted={fontSize:12,color:'var(--dsw-alias-label-secondary, currentColor)',lineHeight:1.6};
  async function api(path,data) {
    const response=await fetch('/linkmind/api'+path,data===undefined?{cache:'no-store'}:
      {method:'POST',headers:{'Content-Type':'application/json','X-LinkMind-Request':'1'},body:JSON.stringify(data)});
    const value=await response.json();
    if(!response.ok)throw new Error(value.error||'请求失败');
    return value;
  }
  // Fetch streams work with both HTTP and Desktop's authenticated dsh-app protocol.
  async function follow(runId,signal,onValue) {
    const response=await fetch(`/linkmind/api/runs/${encodeURIComponent(runId)}/stream`,{signal,cache:'no-store'});
    if(!response.ok)throw new Error('暂时无法连接仿真');
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
    const [run,setRun]=React.useState(null),[error,setError]=React.useState('');
    const [camera,setCamera]=React.useState('head'),[busy,setBusy]=React.useState(false);
    const [disconnected,setDisconnected]=React.useState(false),[imageError,setImageError]=React.useState(false);
    const [retry,setRetry]=React.useState(0);
    const [now,setNow]=React.useState(Date.now());
    React.useEffect(()=> {
      setRun(null);setError('');setDisconnected(false);
      if(preset!=='linkmind-embodied')return;
      let closed=false,timer;
      const update=async()=> {
        try {
          const state=await api('/state');
          const latest=state.runs.find(r=>r.task_snapshot.session_id===sessionId);
          if(!closed){setRun(current=>current?.id===latest?.id?current:latest||null);setError('');}
        } catch(e){if(!closed)setError('无法连接仿真服务，请检查 LinkMind 插件是否已启用');}
        if(!closed)timer=setTimeout(update,1000);
      };
      update();return()=>{closed=true;clearTimeout(timer);};
    },[sessionId,preset]);
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
    React.useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
    const frame=run?.camera;
    const image=run&&(frame||run.observation||run.observation_available)?`/linkmind/api/runs/${run.id}/artifacts/${camera}.png?frame=${frame?.frame??run.step??run.observation?.step??0}&retry=${retry}`:null;
    React.useEffect(()=>setImageError(false),[image]);
    const stop=async()=> {
      setBusy(true);
      try{await api(`/runs/${run.id}/stop`,{});setRun(await api(`/runs/${run.id}/live`));setError('');}
      catch(e){setError(e.message);}finally{setBusy(false);}
    };
    const age=frame?Math.max(0,Math.floor((now-frame.captured_at*1000)/1000)):null;
    return h('div',{style:{height:'100%',overflowY:'auto',padding:16,fontSize:13,display:'flex',flexDirection:'column',gap:16}},
      h('div',{style:{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}},
        h('label',{style:{display:'flex',alignItems:'center',gap:8}},'视角',
          h('select',{'aria-label':'摄像头视角',value:camera,onChange:e=>setCamera(e.target.value),style:{font:'inherit',color:'inherit',background:'var(--dsw-alias-background-primary, transparent)',padding:6,borderRadius:6,border:'1px solid color-mix(in srgb, currentColor 18%, transparent)'}},
            ...Object.entries(cameraNames).map(([key,name])=>h('option',{key,value:key},name)))),
        active(run)&&h(Button,{size:'sm',variant:'outline',disabled:busy,onClick:stop,style:{marginLeft:'auto'}},busy?'正在停止…':'停止仿真')),
      error&&h('p',{role:'alert',style:{margin:0}},error),
      image?h('figure',{style:{margin:0}},
        h('img',{src:image,alt:cameraNames[camera],onError:()=>setImageError(true),style:{display:'block',width:'100%',aspectRatio:'4 / 3',objectFit:'contain',background:'#151515',borderRadius:8}}),
        h('figcaption',{style:{...muted,marginTop:8}},imageError?'画面暂时不可用':age===null?'最近一次观察':`最近画面 · ${age} 秒前`),
        imageError&&h(Button,{size:'sm',variant:'ghost',onClick:()=>setRetry(value=>value+1)},'重试画面')):
        h('p',{style:{...muted,margin:0}},run?.status==='starting'?'正在连接仿真摄像头…':'在会话里描述任务。启动仿真后，这里会显示摄像头画面。'),
      run&&h('div',null,h('div',null,`${statusText[run.status]||run.status} · 控制步 ${run.step??run.observation?.step??'—'}`),
        run.error&&h('p',{role:'alert',style:muted},run.error),
        run.camera_error&&h('p',{role:'status',style:muted},'摄像头暂时未能更新，当前保留最近画面'),
        disconnected&&h('p',{role:'status',style:muted},'连接中断，正在重连；当前显示的是最后收到的画面')),
      h('p',{style:{...muted,margin:0}},'运行中用“插话发送”引导下一动作段；排队消息按 DSH 的发送设置处理。“停止仿真”结束当前执行。'));
  }
  function CameraButton({open,sessionId,useSessions}) {
    const preset=useSessions(s=>s.byId[sessionId]?.projectionValues?.agentPreset);
    if(preset!=='linkmind-embodied')return null;
    return h(Button,{size:'sm',variant:'toolbar',onClick:open},'摄像头');
  }
  return {inject:['slots','sidebarRight','sidebarRightTabs','sessions'],apply(ctx){
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:'linkmind-camera',kind:'linkmind-camera',title:()=> '摄像头',
      guide:[{id:'linkmind-camera',order:-20,title:()=> '摄像头',description:()=> '查看当前仿真的实时画面'}]}),'LinkMind camera tab');
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'linkmind-camera'},CameraPanel));
    ctx.slots.inject('conversation.session.header.utilities',()=>ctx.slots.register({name:'conversation.session.header.utilities',id:'linkmind-camera',order:-20,
      inject:sessionId=>({open:()=>ctx.sidebarRight.openTab('linkmind-camera',{params:{sessionId}})})},CameraButton));
  }};
}});
