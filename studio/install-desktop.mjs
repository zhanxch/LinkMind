// Install through DSH's own bundle manager; preserve the user's account and profile.
import {spawn} from 'node:child_process';
import {access, copyFile, mkdir, readFile, readdir, realpath, rename, writeFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url)), root=path.dirname(here);
const args=process.argv.slice(2);
const options={};
for(let i=0;i<args.length;i++) {
  if(!['--home','--dsh','--profile'].includes(args[i])||!args[i+1])throw new Error('Usage: node install-desktop.mjs [--home DSH_HOME] [--dsh executable] [--profile desktop]');
  options[args[i].slice(2)]=args[++i];
}
const home=path.resolve(options.home||process.env.DSH_HOME||path.join(homedir(),'.local/share/dsh-linux/home'));
const profile=options.profile||'desktop';
if(!/^[a-zA-Z0-9_-]+$/.test(profile))throw new Error('Invalid profile name');
const directory=path.join(home,'profiles',profile);
await access(path.join(directory,'package.json'));
// Package operations require an idle profile. Do not interrupt an active conversation.
for(const pid of await readdir('/proc')) {
  if(!/^\d+$/.test(pid)||Number(pid)===process.pid)continue;
  try {
    const command=await readFile(`/proc/${pid}/comm`,'utf8');
    if(!/deepseek|node/.test(command))continue;
    const env=(await readFile(`/proc/${pid}/environ`,'utf8')).split('\0');
    const other=env.find(item=>item.startsWith('DSH_HOME='))?.slice(9);
    if(other && await realpath(other)===await realpath(home))throw new Error(`DSH_RUNNING:${pid}`);
  } catch(error) {
    if(error.message.startsWith('DSH_RUNNING:'))throw new Error('Fully quit DeepSeek Harness before installing this bundle, then run this command again. Your account and conversations will be preserved.');
    if(!['ENOENT','ESRCH','EACCES','EPERM'].includes(error.code))throw error;
  }
}
let dsh=options.dsh;
if(!dsh) {
  const bases=['/opt/DeepSeek Harness',path.join(homedir(),'.local/opt/dsh-linux')];
  const candidates=[path.join(bases[0],'resources/runtime/cli/bin/dsh')];
  try {for(const version of (await readdir(bases[1])).sort().reverse())candidates.push(path.join(bases[1],version,'resources/runtime/cli/bin/dsh'));}catch(error){if(error.code!=='ENOENT')throw error;}
  for(const candidate of candidates){try{await access(candidate);dsh=candidate;break;}catch{}}
}
if(!dsh)throw new Error('Desktop CLI not found; pass --dsh /path/to/installed/dsh');
function run(executable,argv,cwd=here,capture=false) {
  return new Promise((resolve,reject)=>{
    const child=spawn(executable,argv,{cwd,env:{...process.env,DSH_HOME:home},stdio:capture?['ignore','pipe','inherit']:'inherit'});
    let output='';child.stdout?.on('data',data=>output+=data);
    child.once('error',reject);child.once('exit',code=>code===0?resolve(output):reject(new Error(`${executable} exited ${code}`)));
  });
}
const backup=path.join(home,'linkmind-install-backups',new Date().toISOString().replaceAll(':','-'));
await mkdir(backup,{recursive:true,mode:0o700});
for(const name of ['package.json','cordis.patch.yml','pnpm-lock.yaml','pnpm-workspace.yaml']) {
  try{await copyFile(path.join(directory,name),path.join(backup,name));}catch(error){if(error.code!=='ENOENT')throw error;}
}
const bundles=path.join(home,'local-bundles');await mkdir(bundles,{recursive:true,mode:0o700});
const packed=JSON.parse(await run('npm',['pack','--json','--ignore-scripts','--pack-destination',bundles],path.join(here,'plugin'),true));
await run(dsh,['plugin','--profile',profile,'add',path.join(bundles,packed[0].filename),'--ignore-scripts']);
const target=path.join(directory,'cordis.patch.yml');
let patch='';try{patch=await readFile(target,'utf8');}catch(error){if(error.code!=='ENOENT')throw error;}
patch=patch.replace(/\n?# BEGIN LinkMind desktop configuration\n[\s\S]*?# END LinkMind desktop configuration\n?/g,'');
patch+='\n# BEGIN LinkMind desktop configuration\n- id: linkmind-studio\n  config:\n    root: '+JSON.stringify(root)+'\n# END LinkMind desktop configuration\n';
await writeFile(target+'.linkmind-tmp',patch,{mode:0o600});await rename(target+'.linkmind-tmp',target);
console.log('LinkMind installed. Reopen DeepSeek Harness and select 具身模式 · LinkMind.');
console.log('Profile backup: '+backup);
