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
const modules=['__init__.py','service.py','projects.py','project_worker.py','external_agent.py','codex_agent.py','mcp.py'];
for(const name of modules)await copy('src/roborag/studio/'+name,'backend/src/roborag/studio/'+name);
await copy('src/roborag/episode_files.py','backend/src/roborag/episode_files.py');
await writeFile(path.join(target,'backend/src/roborag/__init__.py'),'"""Standalone Studio runtime; simulator integrations are supplied separately."""\n');
await mkdir(path.join(target,'backend/resources'),{recursive:true});
await writeFile(path.join(target,'backend/resources/task-bundles.json'),'{"tasks":{}}\n');
for(const file of await readdir(path.join(root,'examples/studio-project')))await copy('examples/studio-project/'+file,'examples/studio-project/'+file);
await copy('docs/studio-projects.md','docs/projects.md');
for(const name of ['test_studio_projects.py','test_studio_workspace.py']){
  await copy('tests/'+name,'tests/'+name);
  const file=path.join(target,'tests',name);
  await writeFile(file,(await readFile(file,'utf8')).replace("PYTHONPATH=str(ROOT/'src')","PYTHONPATH=str(ROOT/'backend/src')"));
  sources['tests/'+name].note='Test Python path adjusted to standalone backend/src';
}
await writeFile(path.join(target,'SOURCE.json'),JSON.stringify({repository:'https://github.com/zhanxch/LinkMind',
  commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),files:sources},null,2)+'\n');
console.log(target);
