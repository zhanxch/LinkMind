// Both views use the native workspace/session supplied by the DSH tab.
export function roundLineage(rows) {
  const unique = new Map(), counts = new Map();
  for (const row of rows) {
    counts.set(row.id, (counts.get(row.id) || 0) + 1);
    unique.set(row.id, row);
  }
  const depth = new Map();
  function locate(row) {
    let current = row;
    const seen = new Set(), chain = [];
    while (current && !depth.has(current.id)) {
      if (counts.get(current.id) !== 1 || seen.has(current.id)) return null;
      chain.push(current.id);
      seen.add(current.id);
      if (!current.parent) break;
      current = unique.get(current.parent);
    }
    if (!current) return null;
    let level = depth.get(current.id) ?? -1;
    while (chain.length) depth.set(chain.pop(), ++level);
    return depth.get(row.id);
  }
  return rows.map(row => ({...row, depth:locate(row)}))
    .sort((a,b) => (a.depth ?? Infinity) - (b.depth ?? Infinity));
}

const styles = `
.rsi-view{height:100%;box-sizing:border-box;overflow:auto;padding:18px 20px;color:var(--dsw-alias-label-primary);font-size:13px}.rsi-view h2{margin:0;font-size:19px;font-weight:500}.rsi-view h3{font-size:14px;margin:12px 0 6px;font-weight:500}.rsi-view p{line-height:1.55;margin:6px 0 12px;color:var(--dsw-alias-label-secondary)}.rsi-head,.rsi-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.rsi-head{justify-content:space-between;margin-bottom:14px}.rsi-controls{margin:10px 0}.rsi-view label{display:grid;gap:4px;min-width:0}.rsi-view input,.rsi-view select{font:inherit;color:inherit;background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l3);border-radius:6px;padding:6px;max-width:100%;box-sizing:border-box}.rsi-view table{border-collapse:collapse;width:100%;text-align:left}.rsi-view td,.rsi-view th{padding:7px 9px;border-bottom:1px solid var(--dsw-alias-border-l3);overflow-wrap:anywhere}.rsi-view th{font-weight:500}.rsi-chart{width:100%;min-height:128px;max-height:180px;color:var(--dsw-alias-label-secondary)}.rsi-chart text{font:11px system-ui;fill:currentColor}.rsi-chart circle{fill:var(--lm-accent,currentColor)}.rsi-view details{margin:10px 0}.rsi-scroll{overflow:auto}.rsi-view [role=alert]{color:var(--dsw-alias-label-primary)}.rsi-view code{overflow-wrap:anywhere}.rsi-empty{padding:16px 0}.rsi-catalog{display:grid;gap:8px}.rsi-catalog li{overflow-wrap:anywhere}
`;

export function createRSIViews(React, ui, api) {
  const h = React.createElement;
  const button = (title, action, disabled = false) => h(ui.Button,{size:'sm',variant:'outline',onClick:action,disabled},title);
  const field = (title, child) => h('label',null,title,child);
  const textInput = (value, set, placeholder) => h('input',{value,placeholder,onChange:e=>set(e.target.value)});
  const options = values => values.map(([value,title]) => h('option',{key:value,value},title));
  const choose = (value,set,items) => h('select',{value,onChange:e=>set(e.target.value)},...options(items));
  const useWorkspace = (sessionId,useSessions) => useSessions(s=>s.byId[sessionId]?.cwd || s.byId[sessionId]?.projectionValues?.workingDirectory);
  const view = (...children) => h('section',{className:'rsi-view'},h('style',null,styles),...children);
  const errorText = error => error && h('p',{role:'alert'},error);

  function Chart({rows,metric}) {
    const points = rows.filter(r=>r.depth!==null && Number.isFinite(r.metrics[metric]));
    if (!points.length) return h('p',null,'当前指标没有可绘制的轮次。');
    const maxX = Math.max(...points.map(r=>r.depth));
    const vals = points.map(r=>r.metrics[metric]), hi = Math.max(...vals), lo = Math.min(...vals);
    const x = r=>74 + 525*r.depth/(maxX||1), y = r=>hi===lo?70:113-84*(r.metrics[metric]-lo)/(hi-lo);
    const parents = new Map(points.map(r=>[r.id,r]));
    return h('svg',{className:'rsi-chart',viewBox:'0 0 640 148',role:'img','aria-label':metric+' 按迭代代数，每条线连接显式父轮次'},
      h('text',{x:4,y:15},metric),h('text',{x:65,y:hi===lo?74:32,textAnchor:'end'},hi.toLocaleString()),
      hi!==lo&&h('text',{x:65,y:115,textAnchor:'end'},lo.toLocaleString()),
      h('path',{d:'M70 22 V119 H608',stroke:'currentColor',fill:'none',opacity:.35}),
      ...points.filter(r=>parents.has(r.parent)).map(r=>h('line',{key:r.id,x1:x(parents.get(r.parent)),y1:y(parents.get(r.parent)),x2:x(r),y2:y(r),stroke:'currentColor'})),
      ...points.map(r=>h('circle',{key:r.id,cx:x(r),cy:y(r),r:4},h('title',null,r.id+' · '+r.metrics[metric]))),
      h('text',{x:74,y:140},'基线'),maxX>0&&h('text',{x:599,y:140,textAnchor:'end'},'迭代代数 '+maxX));
  }

  function Board({sessionId,useSessions,openRun}) {
    const cwd = useWorkspace(sessionId,useSessions);
    const [data,save] = React.useState(null),[error,fail] = React.useState(''),[group,pickGroup] = React.useState(''),[metric,pickMetric] = React.useState(''),[tick,retry]=React.useState(0);
    React.useEffect(()=>{
      const controller=new AbortController(), signal=controller.signal;
      let timer,registration;
      save(null);fail('');
      async function update() {
        try {
          if (!cwd) return;
          registration ??= await api('/workspace/open',{path:cwd,session_id:sessionId},signal);
          const value=await api('/projects/'+registration.id+'/board',undefined,signal);
          if (!signal.aborted) {save(value);fail('');}
        } catch(e) {if(!signal.aborted) fail(e.message);}
        finally {if(cwd&&!signal.aborted) timer=setTimeout(update,4000);}
      }
      update();return ()=>{controller.abort();clearTimeout(timer);};
    },[sessionId,cwd,tick]);
    const groups=new Map();
    for (const r of data?.rounds||[]) {
      if (!groups.has(r.group)) groups.set(r.group,[]);
      groups.get(r.group).push(r);
    }
    const active=groups.has(group)?group:groups.keys().next().value;
    const rows=roundLineage(groups.get(active)||[]);
    const metrics=[...new Set(rows.flatMap(r=>Object.keys(r.metrics)))];
    const chosen=metrics.includes(metric)?metric:metrics.includes('native.score')?'native.score':metrics[0];
    const selectGroup=[...groups].map(([key,[r]])=>[key,[r.series,r.protocol,r.environment,...Object.values(r.condition),key.slice(0,5)].filter(v=>v!=null).join(' / ')]);
    const parents = new Map(rows.filter(r=>r.depth!==null).map(r=>[r.id,r]));
    return view(h('div',{className:'rsi-head'},h('h2',null,'Agent RSI Board'),button('刷新',()=>retry(x=>x+1))),
      errorText(error),data?.warnings.length>0&&errorText(data.warnings.slice(0,3).join(' · ')),
      !rows.length?h('div',{className:'rsi-empty'},h('h3',null,!cwd?'先打开工作区':data?'还没有 RSI 轮次':'正在读取轮次'),
        data&&h('p',null,'在会话中说「把这次实验记为基线，下一轮记录改动并与它比较」。外部实验也可以写入工作区的 studio.rsi.jsonl。')):
      h(React.Fragment,null,h('div',{className:'rsi-controls'},field('实验 / 对照条件',choose(active,pickGroup,selectGroup)),
        metrics.length>0&&field('指标',choose(chosen,pickMetric,metrics.map(m=>[m,m])))),
        chosen&&h(Chart,{rows,metric:chosen}),h('div',{className:'rsi-scroll'},h('table',null,
        h('thead',null,h('tr',null,...['轮次 / 父轮次','版本与改动','状态',chosen||'指标','较父轮','运行'].map(v=>h('th',{key:v},v)))),
        h('tbody',null,...rows.map((r,i)=>{
          const v=r.metrics[chosen],p=parents.get(r.parent)?.metrics[chosen];
          const delta=r.depth!==null && Number.isFinite(v)&&Number.isFinite(p)?Number((v-p).toPrecision(6)):null;
          return h('tr',{key:[r.group,r.run_id,r.id,i].join('/')},h('td',null,r.id,h('small',null,' ← '+(r.parent||'基线')),r.depth===null&&h('small',null,'（关系待核对）')),
            h('td',null,r.agent_version||r.commit?.slice(0,8)||'—',h('div',null,r.change),r.hypothesis&&h('small',null,'假设 · '+r.hypothesis),r.decision&&h('div',null,'决定 · '+r.decision)),
            h('td',null,r.status),h('td',null,v??'—'),h('td',null,delta===null?'—':(delta>0?'+':'')+delta),
            h('td',null,r.run_id?button('查看运行',()=>openRun(r.run_id)):'外部记录'));
        }))))));
  }

  function Environments({sessionId,useSessions,openPage,pickDirectory}) {
    const cwd=useWorkspace(sessionId,useSessions);
    return h(EnvironmentForm,{key:JSON.stringify([sessionId,cwd]),cwd,sessionId,openPage,pickDirectory});
  }
  function EnvironmentForm({cwd,sessionId,openPage,pickDirectory}) {
    const [catalog,save]=React.useState(null),[root,setRoot]=React.useState(''),[python,setPython]=React.useState(''),[name,setName]=React.useState(''),[selected,setSelected]=React.useState('');
    const [editing,setEditing]=React.useState(null);
    const [error,fail]=React.useState(''),[report,show]=React.useState(null),[busy,lock]=React.useState(false),[notice,say]=React.useState('');
    React.useEffect(()=>{const c=new AbortController();api('/environments',undefined,c.signal).then(v=>{if(!c.signal.aborted) save(v);}).catch(e=>{if(!c.signal.aborted)fail(e.message);});return ()=>c.abort();},[]);
    async function act(f){lock(true);fail('');say('');try{await f();}catch(e){fail(e.message);}finally{lock(false);}}
    const id=selected||catalog?.instances[0]?.id;
    const current=catalog?.instances.find(item=>item.id===id);
    const resetForm=()=>{setEditing(null);setRoot('');setPython('');setName('');};
    const edit=()=>{setEditing(current);setRoot(current.root);setPython(current.python);setName(current.id);say('');fail('');};
    async function register() {
      const result=await api('/environments/register',{root,python,id:editing?.id||name,replace_revision:editing?.binding});
      save(await api('/environments'));setSelected(result.id);resetForm();show(null);await verify(result.id);
    }
    const verify=async id=>show(await api('/environments/check',{id}));
    return view(h('h2',null,'环境注册'),h('p',null,'选择已安装的环境目录。内置识别 LIBERO、LIBERO-Pro、RoboCasa 和 RoboTwin。'),
      h('div',{className:'rsi-controls'},field('环境目录',textInput(root,setRoot,'本机 checkout 目录')),
        button('选择目录',()=>act(async()=>{const path=await pickDirectory();if(path)setRoot(path);}),busy)),
      h('div',{className:'rsi-controls'},field('Python（可选）',textInput(python,setPython,'环境的 Python 可执行文件')),
        editing?field('注册名',h('code',null,editing.id)):field('注册名（可选）',textInput(name,setName,'默认使用适配器名称')),
        button(editing?'保存绑定':'注册环境',()=>act(register),busy||!root.trim()),editing&&button('取消编辑',resetForm,busy)),
      errorText(error), id&&h(React.Fragment,null,h('h3',null,'已注册环境'),h('div',{className:'rsi-controls'},
        field('当前环境',choose(id,v=>{setSelected(v);show(null);say('');if(editing)resetForm();},catalog.instances.map(r=>[r.id,r.id+' · '+r.adapter]))),
        button('编辑绑定',edit,busy||!current),button('检查环境',()=>act(()=>verify(id)),busy),
        button('添加观察配置',()=>act(async()=>{const reg=await api('/workspace/open',{path:cwd,session_id:sessionId});const r=await api('/projects/'+reg.id+'/observe-config',{session_id:sessionId,id});say('已添加 '+r.recipe+'，可在运行配置中启动。');}),busy||!cwd)),
        h('code',null,catalog.instances.find(r=>r.id===id)?.root)),
      notice&&h('p',{role:'status'},notice,' ',button('打开运行配置',()=>openPage('linkmind-project'))),
      report?.id===id&&report&&h(React.Fragment,null,h('h3',null,report.ready?'路径与依赖检查通过':'待补齐的运行条件'),
        h('ul',{className:'rsi-catalog'},...report.checks.map((c,i)=>h('li',{key:i},(c.ready?'✓ ':'缺少 ')+c.label))),
        h('details',null,h('summary',null,'已发现的任务与套件'),...Object.entries(report.tasks).map(([k,items])=>h('p',{key:k},k+' · '+items.join('、'))))));
  }
  return {Board,Environments};
}
