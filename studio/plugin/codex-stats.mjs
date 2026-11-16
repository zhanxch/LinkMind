import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import path from 'node:path';
import {emptyCodexStats,foldCodexStats} from './codex-telemetry.mjs';
export const statsPath=(directory,id)=>path.join(directory,'stats-'+createHash('sha256').update(id).digest('hex')+'.json');
export async function readCodexStats(directory,id) {
  try{const {threads,...value}=JSON.parse(await readFile(statsPath(directory,id),'utf8'));return value;}
  catch(error){if(error.code==='ENOENT')return null;throw error;}
}
export class CodexStatsStore {
  constructor(directory){this.directory=directory;this.pending=Promise.resolve();}
  record(sample){
    const operation=this.pending.then(async()=>{
      const file=statsPath(this.directory,sample.sessionId);
      let state;try{state=JSON.parse(await readFile(file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;state=emptyCodexStats();}
      const next=foldCodexStats(state,sample);if(next===state)return;
      await mkdir(this.directory,{recursive:true,mode:0o700});
      await writeFile(file+'.tmp',JSON.stringify(next),{mode:0o600});await rename(file+'.tmp',file);
    });
    this.pending=operation.catch(()=>{});return operation;
  }
}
