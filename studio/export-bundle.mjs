// Export only the public workbench runtime. No assets, credentials or experiments.
import {mkdir, readdir, readFile, copyFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url)), root=path.dirname(here);
if(process.argv.length!==3)throw new Error('Usage: node studio/export-bundle.mjs /new/output/directory');
const target=path.resolve(process.argv[2]);
await mkdir(target,{recursive:true});
if((await readdir(target)).length)throw new Error('Export destination must be empty');
const sources={};
async function copy(from,to=from) {
  const content=await readFile(path.join(root,from));
  await mkdir(path.dirname(path.join(target,to)),{recursive:true});
  await copyFile(path.join(root,from),path.join(target,to));
  sources[to]={path:from,sha256:createHash('sha256').update(content).digest('hex')};
}
for(const file of await readdir(path.join(here,'plugin'))){
  if(/\.(mjs|js)$/.test(file)||['package.json','cordis.patch.yml','LICENSE'].includes(file))await copy('studio/plugin/'+file,file);
}
const modules=['__init__.py','service.py','project_book.py','conversation_library.py','control_conversation.py','projects.py','environments.py','observe_environment.py','rsi_board.py','rsi_flow.py','rrsi_probe.py','project_worker.py','external_agent.py','codex_agent.py','mcp.py'];
for(const name of modules)await copy('src/roborag/studio/'+name,'backend/src/roborag/studio/'+name);
await copy('src/roborag/episode_files.py','backend/src/roborag/episode_files.py');
await writeFile(path.join(target,'backend/src/roborag/__init__.py'),'"""Standalone Studio runtime; simulator integrations are supplied separately."""\n');
await mkdir(path.join(target,'backend/resources'),{recursive:true});
await writeFile(path.join(target,'backend/resources/task-bundles.json'),'{"tasks":{}}\n');
const example='examples/studio-project/';
for(const name of ['README.md','run.py','linkmind.studio.json','rsi_calibration.py','rsi_workflow_demo.py','studio.rsi.jsonl'])await copy(example+name);
for(const version of ['baseline','summaries','no_plan','fixed','none']){
  for(const scene of ['standard','random'])await copy(example+'evidence/'+version+'-'+scene+'.json');
}
await copy(example+'studio.rsi.d/robodojo-history.jsonl');
for(const task of ['fold_clothes','hang_mugs','make_toast','pack_objects_into_box','push_T','stack_blocks','stack_bowls','sweep_blocks']){
  await copy(example+'batch-evidence/'+task+'.json');
}
await copy('docs/studio-projects.md','docs/projects.md');
await copy('docs/studio-rsi-board.md','docs/rsi-board.md');
await copy('docs/studio-rsi-flow.md','docs/rsi-flow.md');
await copy('docs/studio-ide-workbench.md','docs/workbench.md');
await copy('docs/studio-control-conversation.md','docs/control-conversation.md');
const projectGuide=path.join(target,'docs/projects.md');
await writeFile(projectGuide,(await readFile(projectGuide,'utf8')).replaceAll('(studio-control-conversation.md)','(control-conversation.md)'));
for(const name of ['test_studio_projects.py','test_studio_workspace.py','test_project_book.py','test_goal_tasks.py','test_control_conversation.py','test_rsi_studio.py','test_rsi_flow.py']){
  await copy('tests/'+name,'tests/'+name);
  const file=path.join(target,'tests',name);
  await writeFile(file,(await readFile(file,'utf8')).replace("PYTHONPATH=str(ROOT/'src')","PYTHONPATH=str(ROOT/'backend/src')"));
  sources['tests/'+name].note='Test Python path adjusted to standalone backend/src';
}
await copy('studio/studio-overview.test.mjs','tests/studio-overview.test.mjs');
const overviewTest=path.join(target,'tests/studio-overview.test.mjs');
await writeFile(overviewTest,(await readFile(overviewTest,'utf8')).replace("'./plugin/studio-overview.mjs'","'../studio-overview.mjs'"));
await copy('studio/tests/codex-session.test.mjs','tests/codex-session.test.mjs');
const codexTest=path.join(target,'tests/codex-session.test.mjs');
await writeFile(codexTest,(await readFile(codexTest,'utf8')).replaceAll("'../plugin/codex-","'../codex-"));
for(const name of ['codex-telemetry.test.mjs','task-context.test.mjs','proxy.test.mjs','studio-dock.test.mjs','rsi-board.test.mjs']) {
  await copy('studio/tests/'+name,'tests/'+name);
  const file=path.join(target,'tests',name);
  await writeFile(file,(await readFile(file,'utf8')).replaceAll("'../plugin/","'../"));
}
await copy('docs/studio-codex-continuity.md','docs/codex-continuity.md');
await copy('studio/benchmarks/codex-continuity.mjs','benchmarks/codex-continuity.mjs');
const benchmark=path.join(target,'benchmarks/codex-continuity.mjs');
await writeFile(benchmark,(await readFile(benchmark,'utf8')).replaceAll("'../plugin/codex-","'../codex-"));
await writeFile(path.join(target,'SOURCE.json'),JSON.stringify({repository:'https://github.com/zhanxch/LinkMind',
  commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),files:sources},null,2)+'\n');
console.log(target);
