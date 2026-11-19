const stages = ['evidence','proposal','review','validation','evaluation','decision','activation','loaded'];
const labels = {
  coding:['诊断','提案','审查','验证','评估','决策','采用','下一轮'],
  embodied:['采集证据','提炼经验','冻结','验证','留出复测','决策','采用','下一轮'],
  generic:['证据','提案','审查','验证','评估','决策','采用','下一轮']
};
const statusText = {running:'进行中',done:'完成',passed:'通过',rejected:'拒绝',admissible:'可采用',
  adopted:'已采用',retained:'保留原版',blocked:'暂停',failed:'失败',skipped:'跳过',
  pending:'待运行',error:'错误',loaded:'已加载',warning:'有提示'};
const styles = `
.rsi-flow{height:100%;box-sizing:border-box;overflow:auto;padding:14px 18px;color:var(--dsw-alias-label-primary);font-size:12px;--flow-on:#6069da;--flow-ok:#2e9c88;--flow-stop:#bf6d5e;--flow-dim:var(--dsw-alias-label-secondary)}
.rsi-flow select{font:inherit;color:inherit;background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l3);border-radius:5px;padding:5px;min-width:0;max-width:100%}
.flow-controls,.flow-focus,.flow-badges,.flow-details-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.flow-controls{justify-content:space-between;margin-bottom:12px}
.flow-controls>div{display:flex;gap:7px;flex-wrap:wrap}
.flow-focus{gap:5px 10px;padding:8px 9px;border:1px solid var(--dsw-alias-border-l3);border-left:3px solid var(--flow-on);border-radius:5px;margin-bottom:9px}
.flow-focus[data-status=blocked],.flow-focus[data-status=failed]{border-left-color:var(--flow-stop)}
.flow-focus strong{font-size:14px}.flow-focus span,.flow-note,.flow-node small{color:var(--flow-dim)}
.flow-badges{margin-left:auto;font-variant-numeric:tabular-nums}.flow-tag{border:1px solid var(--dsw-alias-border-l3);border-radius:4px;padding:2px 5px;white-space:nowrap}
.flow-grid{display:grid;grid-template-columns:minmax(78px,1fr) repeat(8,minmax(67px,1.3fr));gap:5px;align-items:stretch}
.flow-scroll{overflow:auto;padding-bottom:4px}
.flow-column{font-weight:500;color:var(--flow-dim);padding:1px 3px 4px;position:relative;white-space:nowrap}
.flow-column:not(:first-child):not(:last-child)::after{content:'→';position:absolute;right:-2px;color:var(--flow-dim)}
.flow-row{display:contents}.flow-lane{display:flex;align-items:center;min-width:0;padding-right:5px;font-weight:650;overflow-wrap:anywhere}
.flow-node{position:relative;display:flex;align-items:start;justify-content:center;gap:2px;flex-direction:column;text-align:left;min-width:0;min-height:38px;padding:4px 6px;background:transparent;color:inherit;border:1px solid var(--dsw-alias-border-l3);border-radius:5px;font:inherit;overflow:hidden}
.flow-node:not(:disabled){cursor:pointer;overflow:visible}.flow-node[data-edge=true]::after{content:'';position:absolute;left:100%;top:50%;width:6px;border-top:1px solid var(--flow-ok);opacity:.6}.flow-node[aria-pressed=true],.flow-node:not(:disabled):hover{outline:1px solid var(--flow-on);outline-offset:-1px}
.flow-node b{font-size:11px}.flow-node small{display:block;white-space:nowrap;text-overflow:ellipsis;max-width:100%;overflow:hidden;font-size:10px}
.flow-node:disabled{opacity:.45;border-style:dashed}
.flow-node[data-status=running]{border-color:var(--flow-on);background:color-mix(in srgb,var(--flow-on) 16%,transparent)}
.flow-node[data-status=running] b::before,.flow-connection[data-link=live]::before{content:'';display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--flow-on);margin-right:5px;animation:studio-pulse 1.8s ease-in-out infinite}
@keyframes studio-pulse{50%{opacity:.32}}
@media(prefers-reduced-motion:reduce){.flow-node[data-status=running] b::before,.flow-connection[data-link=live]::before{animation:none}}
.flow-node[data-status=passed]{background:color-mix(in srgb,var(--flow-ok) 17%,transparent)}
.flow-node[data-status=adopted]{border-color:var(--flow-ok);background:color-mix(in srgb,var(--flow-ok) 26%,transparent)}
.flow-node[data-status=loaded]{border-color:var(--flow-on);background:color-mix(in srgb,var(--flow-on) 23%,transparent)}
.flow-node[data-status=warning]{border-color:#bd9051}.flow-validation{display:grid;gap:5px;margin-top:5px}
.flow-validator{display:flex;gap:9px;align-items:center;flex-wrap:wrap;padding:4px 0;border-top:1px solid var(--dsw-alias-border-l3)}
.flow-validator-state{border:1px solid var(--dsw-alias-border-l3);border-radius:4px;padding:1px 5px}
.flow-validator-state[data-status=passed]{color:var(--flow-ok)}.flow-validator-state[data-status=failed],.flow-validator-state[data-status=error]{color:var(--flow-stop)}
.flow-node[data-status=blocked],.flow-node[data-status=rejected],.flow-node[data-status=failed]{background:color-mix(in srgb,var(--flow-stop) 17%,transparent)}
.flow-meter{position:absolute;bottom:0;left:0;height:2px;background:var(--flow-on)}
.flow-details{margin-top:7px;padding:7px 9px;border-radius:5px;border:1px solid var(--dsw-alias-border-l3)}
.flow-details strong{display:block;margin-bottom:4px}.flow-details dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 10px;margin:6px 0}
.flow-details dt{color:var(--flow-dim)}.flow-details dd{margin:0;min-width:0;overflow-wrap:anywhere;white-space:pre-wrap}
.flow-details-actions{margin-top:6px}
`;

export async function followSnapshots(url,signal,onValue) {
  const response=await fetch(url,{cache:'no-store',signal});
  if(!response.ok || !response.body) throw Error('流程流暂时不可用');
  const reader=response.body.getReader(), decoder=new TextDecoder();
  let buffer='';
  try {
    while(true) {
      const {value,done}=await reader.read();
      if(done)return;
      buffer+=decoder.decode(value,{stream:true});
      let end;
      while((end=buffer.indexOf('\n\n'))>=0) {
        const frame=buffer.slice(0,end);
        buffer=buffer.slice(end+2);
        const line=frame.split('\n').find(line=>line.startsWith('data: '));
        if(line) onValue(JSON.parse(line.slice(6)));
      }
    }
  } finally {
    await reader.cancel().catch(()=>{});
    reader.releaseLock();
  }
}

function focusNode(round) {
  const candidates=[...Object.values(round.shared),...Object.values(round.candidates).flatMap(Object.values)];
  const rank={running:5,loaded:4,blocked:3,failed:3,adopted:2,retained:2};
  return candidates.sort((a,b)=>(rank[b.status]||0)-(rank[a.status]||0) ||
    b.time-a.time || stages.indexOf(b.stage)-stages.indexOf(a.stage))[0];
}

export function createFlow(React,ui,api) {
  const h=React.createElement;
  const button=(name,onClick)=>h(ui.Button,{size:'sm',variant:'outline',onClick},name);
  const renderValue=v=>typeof v==='number'?v.toLocaleString(undefined,{maximumFractionDigits:4}):typeof v==='boolean'?(v?'是':'否'):String(v);
  function Flow({cwd,sessionId,openRun,openFile,onMatrix}) {
    const [received,save]=React.useState(null),[connection,setConnection]=React.useState('connecting');
    const [source,selectSource]=React.useState(''),[roundNumber,selectRound]=React.useState(''),[selection,inspect]=React.useState('');
    React.useEffect(()=>{
      if(!cwd)return;
      const controller=new AbortController(),signal=controller.signal;
      let registration,timer;
      async function connect() {
        try {
          registration??=await api('/workspace/open',{path:cwd,session_id:sessionId},signal);
          await followSnapshots('/linkmind/api/projects/'+registration.id+'/flow',signal,value=>{
            if(!signal.aborted){save(value);setConnection('live');}
          });
        } catch {
          if(!signal.aborted)setConnection('retrying');
        } finally {
          if(!signal.aborted)timer=setTimeout(connect,1300);
        }
      }
      connect();return()=>{clearTimeout(timer);controller.abort();};
    },[cwd,sessionId]);
    const rounds=received?.rounds||[];
    const names=[...new Set(rounds.map(r=>r.run))];
    const newest=rounds.reduce((best,r)=>!best || r.last_event>best.last_event?r:best,null);
    const activeSource=names.includes(source)?source:newest?.run;
    const series=rounds.filter(r=>r.run===activeSource);
    const round=series.find(r=>String(r.round)===roundNumber)||series.at(-1);
    const chooser=(name,value,items,change)=>h('select',{'aria-label':name,value,onChange:e=>change(e.target.value)},
      items.map(([key,label])=>h('option',{key,value:key},label)));
    const controls=h('div',{className:'flow-controls'},h('div',null,
      round&&chooser('演化运行',activeSource,names.map(n=>[n,n]),v=>{selectSource(v);selectRound('');inspect('');}),
      round&&chooser('轮次',series.some(r=>String(r.round)===roundNumber)?roundNumber:'',
        [['','最新一轮'],...series.map(r=>[String(r.round),'轮次 '+r.round])],v=>{selectRound(v);inspect('');})),
      h('div',null,h('span',{className:'flow-connection','data-link':connection},
        connection==='live'?'实时连接':connection==='retrying'?'正在重连':'正在连接'),
        button('批量评测',onMatrix)));
    if(!round)return h('section',{className:'rsi-flow'},h('style',null,styles),controls,
      h('p',{className:'flow-note'},!cwd?'先打开工作区':received?'等待流程事件':'正在读取演化进程'));
    const laneLabels=labels[round.meta.workflow]||labels.generic;
    const lanes=Object.entries(round.candidates);
    const focus=focusNode(round);
    const stateFor=(entry)=>entry?.status==='running' && ['blocked','failed'].includes(round.meta.status)
      ?'blocked':entry?.status;
    const status=round.meta.status||focus?.status;
    const active=selection?JSON.parse(selection):null;
    const current=active?(active[0]?round.candidates[active[0]]:round.shared)?.[active[1]]:null;
    const pill=(name,value)=>h('span',{key:name,className:'flow-tag'},name+' '+renderValue(value));
    function node(candidate,stage,index,map) {
      const entry=map[stage];
      const identity=JSON.stringify([candidate,stage]);
      const progress=entry?.progress;
      const awaiting=stage==='loaded'&&!entry&&['adopted','retained'].includes(map.activation?.status);
      const nodeStatus=stateFor(entry);
      const title=entry?.title||entry?.focus||entry?.change||entry?.reason;
      const brief=entry?.loaded_in!==undefined?'第 '+entry.loaded_in+' 轮':entry?.metrics?.['分数']!==undefined?'分数 '+renderValue(entry.metrics['分数']):
        entry?.metrics?.['通过']!==undefined && progress?'通过 '+entry.metrics['通过']+' / '+progress.total:
        progress?'已测 '+progress.done+' / '+progress.total:title;
      const connector=!!entry && !!map[stages[index+1]] && !['failed','rejected','blocked','skipped'].includes(nodeStatus);
      return h('button',{key:stage,type:'button',className:'flow-node',disabled:!entry,
        'data-status':nodeStatus,'data-edge':connector,'aria-pressed':selection===identity,
        'aria-label':(candidate||'全轮')+' '+laneLabels[index]+' '+(statusText[nodeStatus]||(awaiting?'待加载凭据':'暂无记录')),
        title,onClick:()=>inspect(selection===identity?'':identity)},
        h('b',null,entry?(statusText[nodeStatus]||nodeStatus):awaiting?'待加载凭据':'—'),
        brief&&h('small',null,brief),
        progress&&h('i',{className:'flow-meter',style:{width:100*progress.done/progress.total+'%'},'aria-hidden':true}));
    }
    function row(name,id,map) {
      return h('div',{className:'flow-row',key:id},h('div',{className:'flow-lane'},name),
        stages.map((stage,index)=>node(id,stage,index,map)));
    }
    const info=current?[
      ['关注',current.focus],['实际改动',current.change],['假设',current.hypothesis],
      ['依据',current.reason],['版本',current.version],['实际加载轮次',current.loaded_in],...Object.entries(current.metrics||{}),
      ...Object.entries(current.checks||{})
    ].filter(([,v])=>v!==undefined&&v!==''):[];
    return h('section',{className:'rsi-flow'},h('style',null,styles),controls,
      h('div',{className:'flow-focus','data-status':status,role:'status'},
        h('strong',null,(round.meta.title||round.run)+' · '+(statusText[status]||'已记录')),
        round.meta.target&&h('span',null,round.meta.target),
        round.meta.version&&h('span',{title:round.meta.version},'本轮基线 '+round.meta.version.slice(0,12)),
        focus&&h('span',null,(focus.candidate?focus.candidate+' · ':'')+
          laneLabels[stages.indexOf(focus.stage)]+(focus.focus?' · '+focus.focus:'')),
        h('div',{className:'flow-badges'},
          focus?.progress&&pill('进度',focus.progress.done+' / '+focus.progress.total),
          ...Object.entries(focus?.metrics||{}).slice(0,3).map(([k,v])=>pill(k,v))),
        round.meta.reason&&h('small',{className:'flow-note'},round.meta.reason)),
      h('div',{className:'flow-scroll'},h('div',{className:'flow-grid','aria-label':'演化流程'},
        h('div',{className:'flow-column'},'轮次 '+round.round),
        laneLabels.map(name=>h('div',{key:name,className:'flow-column'},name)),
        row('整轮','',round.shared),...lanes.map(([id,map])=>row(id,id,map)))),
      current&&h('section',{className:'flow-details'},
        h('strong',null,(active[0]||'整轮')+' · '+laneLabels[stages.indexOf(active[1])]),
        info.length>0&&h('dl',null,info.map(([k,v],i)=>h(React.Fragment,{key:i},h('dt',null,k),h('dd',null,renderValue(v))))),
        current.validators&&h('div',{className:'flow-validation'},Object.values(current.validators).map(v=>
          h('div',{className:'flow-validator',key:v.check},h('b',null,v.title||v.check),
            h('span',{className:'flow-note'},v.required?'必需':'建议'),
            h('span',{className:'flow-validator-state','data-status':v.status},statusText[v.status]||v.status),
            v.reason&&h('span',{className:'flow-note'},v.reason),
            (v.links||[]).map(link=>h('span',{key:link.path},button(link.label,()=>openFile(cwd+'/'+link.path))))))),
        h('div',{className:'flow-details-actions'},
          current.loaded_in!==undefined&&series.some(r=>r.round===current.loaded_in)&&
            button('查看加载轮次',()=>{selectRound(String(current.loaded_in));inspect('');}),
          ...(current.links||[]).map(link=>
          h('span',{key:link.path},button(link.label,()=>openFile(cwd+'/'+link.path)))),
          current.studio_run&&button('打开控制会话与摄像头',()=>openRun(current.studio_run)))),
      received?.warnings?.length>0&&h('details',null,h('summary',null,'来源提示 · '+received.warnings.length),
        received.warnings.map(t=>h('p',{key:t,className:'flow-note'},t))));
  }
  return Flow;
}
