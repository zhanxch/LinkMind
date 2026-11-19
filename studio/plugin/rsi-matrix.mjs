const outcomes = [
  ['success','成功'], ['failure','失败'], ['unscored','未评分'],
  ['interrupted','中断'], ['pending','待运行']
];
const styles = `
.rsi-matrix{--mx-ok:#2c9d8e;--mx-bad:#cb6679;--mx-unscored:#c39454;--mx-interrupted:#8c81bb;--mx-pending:#778399}
.rsi-matrix-controls,.rsi-matrix-legend,.rsi-matrix-stats{display:flex;gap:8px 15px;align-items:center;flex-wrap:wrap}
.rsi-matrix-controls label{display:flex;align-items:center;gap:6px}.rsi-matrix-controls label:first-child{max-width:min(100%,35em)}.rsi-matrix-controls select{min-width:0}
.rsi-matrix-summary{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 15px;margin:10px 0 8px}.rsi-matrix-stats{margin:0}.rsi-matrix-stats span{font-variant-numeric:tabular-nums}.rsi-matrix-stats strong{font-size:16px}
.rsi-matrix-legend{color:var(--dsw-alias-label-secondary);font-size:11px;margin:0}
.rsi-legend-swatch{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}.rsi-matrix-frame{max-height:65vh;overflow:auto;border:1px solid var(--dsw-alias-border-l3);border-radius:7px}
.rsi-matrix table{border-collapse:separate;border-spacing:0;text-align:center}.rsi-matrix td,.rsi-matrix th{padding:2px 4px;white-space:nowrap}
.rsi-matrix th[scope=col]{position:sticky;top:0;background:var(--dsw-alias-bg-base);z-index:1;text-align:center}
.rsi-matrix th[scope=row],.rsi-matrix th.rsi-matrix-corner{position:sticky;left:0;z-index:2;background:var(--dsw-alias-bg-base);text-align:left;padding:3px 9px;max-width:15rem;overflow:hidden;text-overflow:ellipsis}
.rsi-matrix th.rsi-matrix-corner{top:0;z-index:3}
.rsi-matrix-col,.rsi-matrix-cell{font:inherit;color:inherit;cursor:pointer;border:1px solid transparent;border-radius:4px;background:transparent;width:100%;font-variant-numeric:tabular-nums}
.rsi-matrix-col{max-width:15rem;overflow:hidden;text-overflow:ellipsis;padding:4px 5px}.rsi-matrix-col[aria-pressed=true]{border-color:var(--dsw-alias-border-l3);background:var(--dsw-alias-bg-weak,transparent)}
.rsi-matrix-cell{position:relative;display:flex;align-items:center;justify-content:space-between;gap:9px;padding:3px 6px;min-width:86px;line-height:14px}
.rsi-matrix-cell:hover,.rsi-matrix-cell:focus-visible{outline:1px solid var(--dsw-alias-label-secondary);outline-offset:-1px}.rsi-matrix-cell[disabled]{cursor:default;opacity:.65;outline:none}
.rsi-matrix-cell:has(.rsi-cell-bars){padding-bottom:7px}.rsi-cell-bars{display:flex;position:absolute;bottom:2px;left:6px;right:6px;height:3px;overflow:hidden;border-radius:2px}
.rsi-cell-bars i{height:100%;flex-shrink:0}.rsi-mx-gain,.rsi-mx-regression,.rsi-mx-restored{font-weight:650}.rsi-mx-gain{color:var(--mx-ok)}.rsi-mx-regression{color:var(--mx-bad)}.rsi-mx-restored{color:var(--mx-unscored)}
.rsi-matrix-caption{color:var(--dsw-alias-label-secondary);font-size:11px}.rsi-matrix-controls .rsi-window{display:flex;align-items:center;gap:4px;margin-left:auto}
`;

function sumCells(cells) {
  const sum = {};
  for (const cell of cells) {
    for (const [key,value] of Object.entries(cell)) {
      if (typeof value === 'number') sum[key] = (sum[key] || 0) + value;
    }
  }
  return sum;
}
const reported = cell => outcomes.reduce((sum,[key])=>sum+(cell[key]||0),0);
const scored = cell => (cell.success||0) + (cell.failure||0);

export function createMatrix(React, ui) {
  const h = React.createElement;
  const button = (label, action, disabled=false, accessibleName) =>
    h(ui.Button,{size:'sm',variant:'outline',onClick:action,disabled,'aria-label':accessibleName},label);
  const colors = {
    success:'var(--mx-ok)',failure:'var(--mx-bad)',unscored:'var(--mx-unscored)',
    interrupted:'var(--mx-interrupted)',pending:'var(--mx-pending)'
  };
  const selector = (label,value,change,entries) =>
    h('label',null,label,h('select',{value,onChange:e=>change(e.target.value)},
      entries.map(([id,title])=>h('option',{key:id,value:id},title))));
  const stat = (value,label) => h('span',null,h('strong',null,value),' ',label);

  function Matrix({batches,batch,pickBatch,split,pickSplit,openDetail}) {
    const [mode,setMode]=React.useState('outcomes');
    const [selected,setSelected]=React.useState(null);
    const [endOffset,setEndOffset]=React.useState(0);
    const splits=[...new Set(batch.rounds.flatMap(r=>r.cells.map(cell=>cell.split)))].sort();
    const activeSplit=splits.includes(split)?split:null;
    const columns=batch.rounds.map(round=>{
      const tasks=new Map();
      for (const cell of round.cells) {
        if (activeSplit!==null && cell.split!==activeSplit) continue;
        if (!tasks.has(cell.task)) tasks.set(cell.task,[]);
        tasks.get(cell.task).push(cell);
      }
      return {...round,tasks:new Map([...tasks].map(([name,cells])=>[name,sumCells(cells)]))};
    });
    const tasks=[...new Set(columns.flatMap(col=>[...col.tasks.keys()]))].sort((a,b)=>a.localeCompare(b));
    const total=columns.length;
    const size=14;
    const offset=Math.min(endOffset,Math.floor((total-1)/size));
    const last=total-offset*size;
    const visible=columns.slice(Math.max(0,last-size),last);
    const active=visible.find(col=>col.record===selected)||visible[visible.length-1];
    const totals=sumCells([...active.tasks.values()]);
    const legend=mode==='outcomes'?outcomes.map(([key,name])=>h('span',{key},h('i',{className:'rsi-legend-swatch',style:{background:colors[key]}}),name)):
      [h('span',{key:'fix',className:'rsi-mx-gain'},'↑ 修复'),h('span',{key:'regression',className:'rsi-mx-regression'},'↓ 回归'),
       h('span',{key:'restored',className:'rsi-mx-restored'},'+ 补齐评分'),h('span',{key:'paired'},'◌ 未配对')];

    function matrixCell(column,task) {
      const cell=column.tasks.get(task);
      const count=cell?reported(cell):0;
      if (!cell) return h('span',{className:'rsi-matrix-caption',title:'无记录'},'—');
      const info=outcomes.filter(([key])=>cell[key]).map(([key,title])=>title+' '+cell[key]).join(' · ');
      const compared=column.parent && (cell.paired || cell.unpaired);
      const diff=compared?'修复 '+(cell.gain||0)+' · 回归 '+(cell.regression||0)+' · 补齐评分 '+(cell.restored||0)+
        ' · 已评分配对 '+(cell.paired||0)+' · 未配对 '+(cell.unpaired||0):'无父版配对';
      return h('button',{type:'button',className:'rsi-matrix-cell',
        style:mode==='outcomes'&&count?{background:'color-mix(in srgb, var(--mx-ok) '+Math.round(4+18*(cell.success||0)/count)+'%, transparent)'}:undefined,
        title:[task,column.id,info,diff].filter(Boolean).join(' / '),
        'aria-label':task+' '+column.id+' · '+(mode==='outcomes'?info:diff),
        onClick:()=>openDetail({record:column.record,version:column.id,task,split:activeSplit})},
        mode==='outcomes'?
          h(React.Fragment,null,h('strong',null,count?String(cell.success||0)+'/'+count:'—'),
            h('span',{className:'rsi-matrix-caption'},count && scored(cell)<count?'◌'+(count-scored(cell)):''),
            !!count&&h('span',{className:'rsi-cell-bars','aria-hidden':true},
              outcomes.map(([key])=>cell[key]?h('i',{key,style:{width:100*cell[key]/count+'%',background:colors[key]}}):null))) :
          compared?h(React.Fragment,null,
            h('span',{className:'rsi-mx-gain'},'↑'+(cell.gain||0)),
            h('span',{className:'rsi-mx-regression'},'↓'+(cell.regression||0)),
            cell.restored?h('span',{className:'rsi-mx-restored'},'+'+cell.restored):null,
            (cell.unpaired||0)>(cell.restored||0)?h('span',{className:'rsi-matrix-caption'},'◌'+(cell.unpaired-(cell.restored||0))):null):'—');
    }
    return h('section',{className:'rsi-matrix'},h('style',null,styles),
      h('div',{className:'rsi-matrix-controls'},
        selector('实验',batch.id,pickBatch,batches.map(b=>[b.id,b.series+' · '+b.protocol])),
        selector('数据集',JSON.stringify(activeSplit),v=>pickSplit(JSON.parse(v)),
          [['null','全部'],...splits.map(s=>[JSON.stringify(s),s||'未标注'])]),
        selector('图层',mode,setMode,[['outcomes','结果'],['changes','较父版']]),
        total>size&&h('div',{className:'rsi-window'},
          button('‹',()=>setEndOffset(offset+1),last<=size,'更早版本'),h('small',null,(Math.max(0,last-size)+1)+'–'+last+' / '+total),
          button('›',()=>setEndOffset(offset-1),offset===0,'更新版本'))),
      h('div',{className:'rsi-matrix-summary'},h('div',{className:'rsi-matrix-stats'},h('strong',null,active.id),
        stat(active.tasks.size+'/'+tasks.length,'任务'),stat(scored(totals)+'/'+reported(totals),'已评分'),
        active.parent&&stat('↑'+(totals.gain||0)+' / ↓'+(totals.regression||0),'修复 / 回归'),
        totals.restored?stat('+'+totals.restored,'补齐评分'):null),
      h('div',{className:'rsi-matrix-legend'},...legend)),
      h('div',{className:'rsi-matrix-frame',tabIndex:0,'aria-label':'任务 × 版本'},
        h('table',{'aria-label':'任务 × 版本'},h('thead',null,h('tr',null,h('th',{scope:'col',className:'rsi-matrix-corner'},'任务'),
          ...visible.map(col=>h('th',{scope:'col',key:col.record},
            h('button',{type:'button',className:'rsi-matrix-col','aria-pressed':col.record===active.record,
              title:[col.id,col.parent&&'← '+col.parent,col.change].filter(Boolean).join(' '),
              onClick:()=>setSelected(col.record)},col.id))))),
          h('tbody',null,...tasks.map(task=>h('tr',{key:task},h('th',{scope:'row',title:task},task),
            ...visible.map(column=>h('td',{key:column.record},matrixCell(column,task)))))))));
  }
  return Matrix;
}
