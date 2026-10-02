import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createAppServer } from '../server.js';
import { parseCommand } from '../electron/commands.js';

test('desktop commands preserve paths and never interpret shell metacharacters', () => {
  const media = new Map([['视频 & test.mp4', 'C:\\Video Folder\\视频 & test.mp4']]);
  const args = parseCommand('python3 cut_plan.py "视频 & test.mp4" clip_plan.csv -o "x & y.mp4"', 'scripts', media, 'output');
  assert.equal(args[1], media.get('视频 & test.mp4'));
  assert.equal(args.at(-1), 'x & y.mp4');
  assert.throws(() => parseCommand('python3 evil.py', 'scripts', media, 'output'));
  assert.throws(() => parseCommand('python3 cut_plan.py "oops', 'scripts', media, 'output'));
  assert.throws(() => parseCommand('python3 cut_plan.py\nwhoami', 'scripts', media, 'output'));
});

test('server exports to writable workspace and protects desktop POST requests', async () => {
  const workspace = await mkdtemp(join(tmpdir(), 'npocut-test-'));
  let ran = '';
  const server = createAppServer({ workspace, token: 'test-secret', runCommand: command => { ran = command; } });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const post = (path, body, token = 'test-secret') => fetch(origin + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Npocut-Token': token }, body: JSON.stringify(body) });
  try {
    assert.equal((await fetch(origin)).status, 200);
    assert.equal((await fetch(origin + '/%zz')).status, 400);
    assert.equal((await post('/api/export-plan', { filename: 'clip_plan.csv', content: 'start,end\n0,1' }, '')).status, 403);
    assert.equal((await post('/api/export-plan', { filename: 'clip_plan.csv', content: 'start,end\n0,1' })).status, 200);
    assert.equal(await readFile(join(workspace, 'clip_plan.csv'), 'utf8'), 'start,end\n0,1');
    assert.equal((await post('/api/export-plan', { filename: 'evil.py', content: '' })).status, 400);
    assert.equal((await post('/api/save-srt', { filename: 'test.srt', content: '字幕' })).status, 200);
    assert.equal(await readFile(join(workspace, 'test.srt'), 'utf8'), '字幕');
    await post('/api/run-command', { command: 'python3 cut_plan.py test.mp4 clip_plan.csv' });
    assert.ok(ran.startsWith('python3 cut_plan.py'));
  } finally { await new Promise(resolve => server.close(resolve)); await rm(workspace, { recursive: true, force: true }); }
});
