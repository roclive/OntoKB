import { basename, join } from 'node:path';

const scripts = new Set(['cut_plan.py', 'remove_ranges.py', 'make_shorts.py',
  'generate_srt.py', 'burn_existing_srt.py', 'burn_vertical_srt.py']);

// Parse our generated command format without ever invoking a shell.
export function parseCommand(command, scriptsDir, media, workspace) {
  if (typeof command !== 'string' || /[\r\n\0]/.test(command)) throw new Error('Invalid command');
  const args = [];
  let current = '', quoted = false, started = false;
  for (const char of command.trim()) {
    if (char === '"') { quoted = !quoted; started = true; }
    else if (/\s/.test(char) && !quoted) {
      if (started) args.push(current);
      current = ''; started = false;
    } else { current += char; started = true; }
  }
  if (quoted) throw new Error('Unclosed quote');
  if (started) args.push(current);
  if (args.shift() !== 'python3' || !scripts.has(args[0])) throw new Error('Unsupported command');
  const script = args.shift();
  const inputPositions = new Set([0]);
  if (script.startsWith('burn_')) inputPositions.add(1);
  const resolved = args.map((arg, i) => {
    if (inputPositions.has(i) || args[i - 1] === '--srt') {
      return media.get(arg) || join(workspace, basename(arg));
    }
    return arg;
  });
  return [join(scriptsDir, script), ...resolved];
}
