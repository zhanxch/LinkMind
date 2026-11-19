// Optional development preview of the same plugin installed in Desktop.
import {spawn} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url)), root=path.dirname(here);
const state=path.resolve(process.env.LINKMIND_STUDIO_STATE||path.join(here,'.state'));
const home=path.join(state,'dsh'), profile=path.join(home,'profiles/linkmind-basic');
await mkdir(profile,{recursive:true,mode:0o700});
const manifest=path.join(profile,'package.json');
try {await readFile(manifest);} catch(error) {
  if(error.code!=='ENOENT')throw error;
  await writeFile(manifest,JSON.stringify({private:true,name:'linkmind-local-profile',dsh:{profile:{bundles:['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}));
}
// A launch overlay, not a rewrite of saved settings or account credentials.
const overlay=path.join(state,'development.patch.json');
await writeFile(overlay,JSON.stringify([
  {id:'agent-default-model',config:{provider:'linkmind-codex',model:process.env.LINKMIND_MODEL||'codex-default'}},
  {insert:[{id:'linkmind-studio',name:path.join(here,'plugin/desktop-host.mjs'),config:{root,state,
    workspace:process.env.LINKMIND_WORKSPACE||'',
    python:process.env.LINKMIND_PYTHON?path.resolve(process.env.LINKMIND_PYTHON):'',codex:true}}]},
]),{mode:0o600});
const child=spawn(process.execPath,[path.join(here,'node_modules/@deepseek-ai/dsh/lib/bin.js'),
  '--profile','linkmind-basic','--patch',overlay,'--host','127.0.0.1','--port',process.env.LINKMIND_PORT||'3080','--no-open'],
  {cwd:root,env:{...process.env,DSH_HOME:home,DSH_TELEMETRY_DISABLED:'1'},stdio:'inherit'});
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>child.kill(signal));
child.on('error',error=>{console.error(error.message);process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code||0;});
