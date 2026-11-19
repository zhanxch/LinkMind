import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, stat, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {startStudio} from '../plugin/runtime.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
test('desktop service owns its lifetime, private connection and exclusive state', async()=>{
  const state=await mkdtemp(path.join(tmpdir(),'linkmind-runtime-'));
  let backend;
  try {
    backend=await startStudio({root,state});
    assert.equal((await stat(backend.connectionFile)).mode & 0o777,0o600);
    const connection=await readFile(backend.connectionFile,'utf8');
    const response=await fetch(backend.url+'/api/state',{headers:{Authorization:`Bearer ${backend.token}`}});
    assert.equal(response.status,200);
    assert.ok((await response.json()).catalog.some(t=>t.id==='push_T'));
    await assert.rejects(startStudio({root,state}),/could not start/);
    assert.equal(await readFile(backend.connectionFile,'utf8'),connection);
    await backend.close();
    assert.equal(backend.alive,false);
    await assert.rejects(readFile(backend.connectionFile),{code:'ENOENT'});
    await backend.close();
  } finally {await backend?.close();await rm(state,{recursive:true,force:true});}
});
test('missing Python fails without a stale connection',async()=>{
  const state=await mkdtemp(path.join(tmpdir(),'linkmind-missing-python-'));
  try {
    await assert.rejects(startStudio({root,state,python:'/nonexistent/linkmind-python'}),{code:'ENOENT'});
    await assert.rejects(readFile(path.join(state,'desktop-connection.json')),{code:'ENOENT'});
  } finally {await rm(state,{recursive:true,force:true});}
});
