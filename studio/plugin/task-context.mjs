// Carry the authoritative brief intact. Historical evidence is an index, not
// another copy of every log/recipe in every model request.
const pick=(value,keys)=>Object.fromEntries(keys.filter(k=>value[k]!==undefined).map(k=>[k,value[k]]));
export function taskContext(value,task) {
  const work=value.project.work.filter(w=>w.objective_id===task.id);
  const records=value.project.records.filter(r=>r.objective_id===task.id);
  const runs=value.runs.filter(r=>r.project_context?.objective_id===task.id);
  const active=work.filter(w=>!['completed','done','closed','cancelled'].includes(w.state));
  const ordered=[...active,...work.filter(w=>!active.includes(w))];
  return {project_id:value.registration_id,revision:value.project.revision,
    task:pick(task,['id','kind','title','request','original_request','intent','constraints','criteria','state','outcome','conclusion','next_action','native_goal_id','native_revision','owner_session_id']),
    work:ordered.slice(0,20).map(w=>pick(w,['id','title','state','depends_on','next_action','objective_id'])),
    records:records.slice(-6).map(r=>({...pick(r,['id','kind','reference','created_at']),
      text:(r.text||'').slice(0,1200),...(r.text?.length>1200?{excerpt:true}:{})})),
    runs:runs.slice(0,5).map(r=>pick(r,['id','status','started_at','finished_at','exit_code','result_path'])),
    available:{work:work.length,records:records.length,runs:runs.length},
    history_note:'History below is a bounded index; omitted or excerpted evidence is not absent. Retrieve project_context or inspect_project only when full records are needed. Original request, constraints and acceptance criteria are retained in full.'};
}
