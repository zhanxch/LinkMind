import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {mkdir, readFile, writeFile, access} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import readline from 'node:readline';
import {embodiedPreset} from './preset.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
const state = path.resolve(process.env.LINKMIND_STUDIO_STATE || path.join(here, '.state'));
let runtime = {};
try { runtime = JSON.parse(await readFile(path.join(root, 'local.runtime.json'), 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
const selectedPython = process.env.LINKMIND_PYTHON || runtime.policy_python || 'python3';
const python = selectedPython.includes('/') ? path.resolve(selectedPython) : selectedPython;
const env = {...process.env, PYTHONPATH: [path.join(root, 'src'), path.join(root, '.runtime/mcp')].join(path.delimiter),
  LINKMIND_STUDIO_TOKEN: randomBytes(32).toString('hex'), DSH_HOME: path.join(state, 'dsh'),
  DSH_TELEMETRY_DISABLED: '1'};
const profile = path.join(env.DSH_HOME, 'profiles/linkmind');
await mkdir(profile, {recursive:true});
const bin = path.join(here, 'node_modules/@deepseek-ai/dsh/lib/bin.js');
await access(bin);
const probe = spawn(python, ['-c', 'from mcp.server import MCPServer'], {env, stdio: ['ignore','ignore','pipe']});
let probeError = '';
probe.stderr.on('data', data => { probeError += data; });
if (await new Promise((resolve, reject) => { probe.on('error', reject); probe.on('close', resolve); }) !== 0) {
  throw new Error(`MCP dependencies are missing for ${python}. Install experiments/rag-mcp-requirements.txt into .runtime/mcp.\n${probeError}`);
}
// This is an application-owned profile in its own home; existing ~/.dsh is untouched.
await writeFile(path.join(profile, 'package.json'), JSON.stringify({private:true, name:'linkmind-local-profile',
  dsh:{profile:{bundles:['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app']}}}, null, 2));
const backend = spawn(python, ['-m', 'roborag.studio.service', '--state', state], {cwd:root, env, stdio:['ignore','pipe','inherit']});
let dsh;
let closing = false;
function close() {
  if (closing) return;
  closing = true;
  dsh?.kill('SIGTERM'); backend.kill('SIGTERM');
}
process.on('SIGINT', close); process.on('SIGTERM', close);
backend.on('error', error => { console.error(error.message); close(); process.exitCode = 1; });
const lines = readline.createInterface({input:backend.stdout});
try {
  env.LINKMIND_STUDIO_URL = await new Promise((resolve, reject) => {
    lines.once('line', line => { try { resolve(JSON.parse(line).url); } catch (error) { reject(error); } });
    backend.once('exit', code => reject(new Error(`Studio service exited (${code})`)));
  });
  const patch = [
    {id:'ui-brand-official', disabled:false},
    {id:'ui-settings-models', config:{credentialOnboarding:false}},
    {id:'agent-default-model', config:{provider:'linkmind-codex', model:process.env.LINKMIND_MODEL || 'codex-default'}},
    {insert:[{id:'linkmind-studio', name:path.join(here, 'plugin/index.mjs')},
      {id:'linkmind-agent', name:path.join(here, 'plugin/agent.mjs')},
      embodiedPreset(here, {
        serverName:'linkmind', transport:'stdio', command:python, args:['-m','roborag.studio.mcp'], cwd:root,
        env:{PYTHONPATH:env.PYTHONPATH, LINKMIND_STUDIO_URL:env.LINKMIND_STUDIO_URL, LINKMIND_STUDIO_TOKEN:env.LINKMIND_STUDIO_TOKEN},
        toolCallTimeoutMs:600000, failOnStartupError:true})]},
  ];
  // JSON is a YAML subset; literal paths never become YAML/JS expressions.
  await writeFile(path.join(profile, 'cordis.patch.yml'), JSON.stringify(patch, null, 2), {mode:0o600});
  dsh = spawn(process.execPath, [bin, '--profile', 'linkmind', '--host', '127.0.0.1', '--port', process.env.LINKMIND_PORT || '3080', '--no-open'],
    {cwd:root, env, stdio:'inherit'});
  dsh.on('error', error => {console.error(error.message); process.exitCode = 1; close();});
  dsh.on('exit', code => {process.exitCode = code || 0; close();});
  backend.on('exit', code => {if (!closing) {console.error(`Studio backend exited (${code})`); process.exitCode = 1; close();}});
} catch (error) {
  close(); throw error;
}
