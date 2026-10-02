"""Run the vendored npocut plan/SRT workflow for OntoKB media jobs."""
from __future__ import annotations

import csv
import math
from pathlib import Path
import subprocess
import sys


NPOCUT_COMMIT = '178e84e597db99a5377650c3164794ddb1205584'
NPOCUT_ROOT = Path(__file__).resolve().parents[2] / 'third_party' / 'npocut'


def _timestamp(seconds):
    milliseconds = round(float(seconds) * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'


def _write_srt(path, cues):
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        for index, cue in enumerate(cues, 1):
            stream.write(f'{index}\n{_timestamp(cue["start"])} --> {_timestamp(cue["end"])}\n')
            stream.write(str(cue['text']).strip().replace('\r', '') + '\n\n')


def write_edit_artifacts(directory, manifest, segments):
    """Persist the edit decision list, then invoke upstream subtitle retiming.

    All paths are host-selected. The source video and transcript cache are never
    overwritten; these artifacts live beside the generated media manifest.
    """
    directory = Path(directory)
    script = NPOCUT_ROOT / 'srt_slice.py'
    if not script.is_file():
        raise RuntimeError('缺少 third_party/npocut/srt_slice.py，请恢复项目内的 npocut 源码。')
    slides = manifest.get('slides') or []
    if not slides or any(not all(math.isfinite(float(s[k])) for k in ('start', 'end'))
                         or float(s['start']) < 0 or float(s['end']) <= float(s['start']) for s in slides):
        raise ValueError('npocut 剪辑计划需要有效的原视频时间戳。')
    directory.mkdir(parents=True, exist_ok=True)
    plan = directory / 'clip_plan.csv'
    with plan.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['start', 'end', 'title'])
        for index, slide in enumerate(slides):
            writer.writerow([f'{float(slide["start"]):.3f}', f'{float(slide["end"]):.3f}',
                             slide.get('title') or f'片段 {index + 1}'])
    source = directory / 'source.srt'
    _write_srt(source, segments)
    output = directory / 'highlight.source.srt'
    try:
        process = subprocess.run([sys.executable, '-X', 'utf8', str(script), str(source.resolve()),
                                  str(plan.resolve()), '-o', str(output.resolve())],
                                 cwd=NPOCUT_ROOT, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('npocut 字幕时间轴处理失败，请重试。') from exc
    if process.returncode or not output.is_file():
        raise RuntimeError('npocut 无法根据剪辑计划生成字幕时间轴。')
    chinese_cues = []
    elapsed = 0.0
    for slide in slides:
        offset = float(slide.get('timeline_start', elapsed))
        for cue in slide.get('captions', []):
            chinese_cues.append({'start': offset + float(cue['start']),
                                 'end': offset + float(cue['end']), 'text': cue['text']})
        elapsed = offset + float(slide['end']) - float(slide['start'])
    if chinese_cues:
        _write_srt(directory / 'highlight.zh.srt', chinese_cues)
    return {'skill': 'npocut-video-workflows', 'commit': NPOCUT_COMMIT,
            'plan': plan.name, 'source_subtitles': source.name,
            'retimed_subtitles': output.name,
            'chinese_subtitles': 'highlight.zh.srt' if chinese_cues else None,
            'executed_script': 'srt_slice.py'}
