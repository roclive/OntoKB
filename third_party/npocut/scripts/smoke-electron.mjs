import { _electron as electron } from 'playwright';
import { mkdir, writeFile, stat } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';

const root = resolve('.');
const fixture = join(root, '.build-cache', 'smoke 中文 & paths');
const output = join(fixture, 'output');
await mkdir(output, { recursive: true });
await mkdir(join(root, 'output/playwright'), { recursive: true });
const video = join(fixture, '测试 & sample.mp4');
const srt = join(fixture, '测试 & sample.srt');
execFileSync(join(root, 'runtime/ffmpeg.exe'), ['-y', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:r=25:d=2', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', video], { stdio: 'ignore' });
await writeFile(srt, '1\n00:00:00,000 --> 00:00:01,500\n测试字幕 Hello Windows\n', 'utf8');
const env = { ...process.env, NPOCUT_WORKSPACE: output };
delete env.ELECTRON_RUN_AS_NODE;
const executablePath = process.argv[2];
const app = await electron.launch({ ...(executablePath ? { executablePath: resolve(executablePath) } : {}), args: executablePath ? [] : ['.'], env });
try {
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.waitForFunction(() => document.querySelector('#runCommand')?.textContent === 'Run');
  console.log(await page.locator('body').ariaSnapshot());
  await page.locator('#videoInput').setInputFiles(video);
  await page.waitForFunction(() => document.querySelector('#video').readyState >= 1);
  await page.locator('#srtInput').setInputFiles(srt);
  await page.locator('#cueList').getByText('测试字幕 Hello Windows').waitFor();
  await page.locator('button[data-mode="clip"]').click();
  await page.locator('#clearPlan').click();
  await page.locator('#startInput').fill('0');
  await page.locator('#endInput').fill('1');
  await page.locator('#addSegment').click();
  async function run() {
    await page.locator('#runCommand').click();
    await page.waitForFunction(() => /Task completed|Task stopped or failed/.test(document.querySelector('#jobLog').textContent), null, { timeout: 120000 });
    const log = await page.locator('#jobLog').textContent();
    assert.ok(log.includes('Task completed.'), log);
  }
  await run();
  assert.ok((await stat(join(output, '测试 & sample.cut.mp4'))).size > 0);
  await page.locator('button[data-mode="burnSrt"]').click();
  await run();
  assert.ok((await stat(join(output, '测试 & sample.subbed.mp4'))).size > 0);
  await page.locator('button[data-mode="burnVerticalSrt"]').click();
  await run();
  assert.ok((await stat(join(output, '测试 & sample.vertical.subbed.mp4'))).size > 0);
  await page.screenshot({ path: join(root, 'output/playwright/windows-electron.png'), fullPage: true });
  assert.deepEqual(errors, []);
  console.log('PASS: Electron startup, media preview, Unicode/space/metacharacter paths, cut + SRT retiming, subtitle burn, vertical burn.');
} finally { await app.close(); }
