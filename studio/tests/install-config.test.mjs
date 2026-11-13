import test from 'node:test';
import assert from 'node:assert/strict';
import {configureDesktop} from '../install-config.mjs';
test('reinstall preserves Codex and custom runtime settings without duplicating the block',()=>{
  const before='- id: agent-default-model\n  config:\n    model: deepseek-flash\n';
  const configured=configureDesktop(before,'/old').replace('    root: "/old"','    root: "/old"\n    codex: true\n    state: "/my-state"');
  const after=configureDesktop(configured,'/new');
  assert.equal(after,configured.replace('"/old"','"/new"'));
  assert.equal(configureDesktop(after,'/new'),after);
  assert.ok(configureDesktop(after,'/path/$&/project').includes('root: "/path/$&/project"'));
});
