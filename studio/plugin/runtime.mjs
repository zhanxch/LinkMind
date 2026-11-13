import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {mkdir, readFile, writeFile, unlink, open} from 'node:fs/promises';
import {homedir} from 'node:os';
import path from 'node:path';
import readline from 'node:readline';

export async function startStudio(config) {
  const root = path.resolve(config.root);
  await readFile(path.join(root, 'resources/task-bundles.json'));
  let local = {};
  try {local = JSON.parse(await readFile(path.join(root, 'local.runtime.json'), 'utf8'));}
  catch (error) {if (error.code !== 'ENOENT') throw error;}
  const python = config.python || local.policy_python || 'python3';
  const state = path.resolve(config.state || path.join(process.env.DSH_HOME || path.join(homedir(), '.dsh'), 'linkmind'));
  await mkdir(state, {recursive: true, mode: 0o700});
  const token = randomBytes(32).toString('hex');
  const connectionFile = path.join(state, 'desktop-connection.json');
  const pythonPath = [path.join(root, 'src'), path.join(root, '.runtime/mcp')].join(path.delimiter);
  const env = {...process.env, PYTHONPATH: pythonPath, LINKMIND_INHERITED_PYTHONPATH: process.env.PYTHONPATH || '', LINKMIND_STUDIO_TOKEN: token};
  const identity = (await readFile(`/proc/${process.pid}/stat`, 'utf8')).split(') ').at(-1).split(' ')[19];
  const log = await open(path.join(state, 'service.log'), 'a', 0o600);
  const child = spawn(python, ['-m', 'roborag.studio.service', '--state', state,
    '--owner-pid', String(process.pid), '--owner-identity', identity],
  {cwd: root, env, stdio: ['ignore', 'pipe', log.fd]});
  let exited = false, spawnError;
  const done = new Promise(resolve => {
    child.once('error', error => {spawnError = error;});
    child.once('close', () => {exited = true; resolve();});
  });
  await log.close();
  let closing;
  const close = () => closing ??= (async () => {
    if (!exited) child.kill('SIGTERM');
    let timer;
    try {
      await Promise.race([done, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('LinkMind service is still stopping; check service.log before restarting.')), 45000);
      })]);
    } finally {clearTimeout(timer);}
    // A failed duplicate launch must not remove the active owner's connection.
    try {
      const saved = JSON.parse(await readFile(connectionFile, 'utf8'));
      if (saved.token === token) await unlink(connectionFile);
    } catch (error) {if (error.code !== 'ENOENT') throw error;}
  })();
  const lines = readline.createInterface({input: child.stdout});
  let timer;
  try {
    const url = await Promise.race([
      new Promise((resolve, reject) => lines.once('line', line => {
        try {
          const parsed = new URL(JSON.parse(line).url);
          if (parsed.protocol !== 'http:' || parsed.hostname !== '127.0.0.1') throw new Error('Unexpected Studio service address');
          resolve(parsed.origin);
        } catch (error) {reject(error);}
      })),
      done.then(() => {throw spawnError || new Error(`LinkMind service could not start. See ${path.join(state, 'service.log')}`);}),
      new Promise((_, reject) => {timer = setTimeout(() => reject(new Error('LinkMind service startup timed out')), 20000);}),
    ]);
    if (exited) throw new Error('LinkMind service exited during startup');
    await writeFile(connectionFile, JSON.stringify({url, token, pid: child.pid}), {mode: 0o600});
    return {url, token, root, state, python, pythonPath, connectionFile, pid: child.pid, close,
      get alive() {return !exited;}};
  } catch (error) {
    await close();
    throw error;
  } finally {clearTimeout(timer); lines.close();}
}
