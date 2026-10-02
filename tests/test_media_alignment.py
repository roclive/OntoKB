import copy
import json
from types import SimpleNamespace

import pytest

from ontokb import media, media_alignment as alignment
from ontokb.graph import GraphStore
from ontokb.reading import reading_library


def manifest():
    return {'status': 'ready', 'mode': 'audio', 'duration': 10,
            'slides': [{'start': 10, 'end': 20, 'text': 'English original',
                        'audio_url': '/audio', 'image_url': '/image'}]}


def response(batch, steps, options, context):
    return {'captions': [{'id': c['id'], 'text': '这是来源中对应的中文内容。',
                          'summary_index': 0 if steps else None} for c in batch]}


def test_cue_times_come_only_from_source_and_overlap_is_preserved():
    segments = [{'start': 9, 'end': 11, 'text': 'crosses start'},
                {'start': 10, 'end': 14, 'text': 'First statement'},
                {'start': 13, 'end': 18, 'text': 'Overlapping next statement'},
                {'start': 19, 'end': 21, 'text': 'crosses end'}]
    original = manifest()
    result = alignment.enrich(original, segments, {'summary': '摘要一。摘要二。'}, {}, requester=response)
    assert result['summary_steps'] == ['摘要一。', '摘要二。']
    assert [(c['start'], c['end']) for c in result['slides'][0]['captions']] == [(0, 4), (3, 8)]
    assert result['slides'][0]['summary_indices'] == [0]
    assert result['slides'][0]['summary_index'] == 0
    assert result['subtitle_source'] == 'translated'
    assert alignment.aligned(result)
    assert original == manifest()


def test_chinese_original_preserved_and_null_never_invents_mapping():
    def untranslated(batch, *args):
        return {'captions': [{'id': c['id'], 'text': '模型擅自改写的内容', 'summary_index': None} for c in batch]}
    result = alignment.enrich(manifest(), [{'start': 10, 'end': 20, 'text': '这是原文，不应被改写。'}],
                              {'summary': '另一个摘要观点。'}, {}, requester=untranslated)
    slide = result['slides'][0]
    assert slide['text'] == '这是原文，不应被改写。'
    assert slide['summary_indices'] == []
    assert slide['summary_index'] is None
    assert slide['captions'][0]['summary_index'] is None
    assert result['subtitle_source'] == 'source'


@pytest.mark.parametrize('mutation', ['unknown', 'duplicate', 'missing', 'timestamp', 'boolean_index', 'outside_index', 'english'])
def test_invalid_model_output_rejected(mutation):
    batch = [{'id': 's0c1', 'text': 'The evidence supports a conclusion.', 'already_chinese': False}]
    item = {'id': 's0c1', 'text': '证据支持这一结论。', 'summary_index': 0}
    data = {'captions': [item]}
    if mutation == 'unknown':
        item['id'] = 'invented'
    elif mutation == 'duplicate':
        data['captions'].append(copy.copy(item))
    elif mutation == 'missing':
        data['captions'] = []
    elif mutation == 'timestamp':
        item['start'] = 999
    elif mutation == 'boolean_index':
        item['summary_index'] = True
    elif mutation == 'outside_index':
        item['summary_index'] = 10
    else:
        item['text'] = batch[0]['text']
    with pytest.raises(alignment.AlignmentError):
        alignment.validate_batch(data, batch, ['摘要'])


@pytest.mark.parametrize('text', ['OpenAI', 'AI', '2026', 'https://openai.com'])
def test_names_urls_numbers_are_not_forced_into_invented_translation(text):
    batch = [{'id': 'x', 'text': text, 'already_chinese': True}]
    result = alignment.validate_batch({'captions': [{'id': 'x', 'text': '', 'summary_index': None}]}, batch, [])
    assert result['x']['text'] == text


def test_batch_request_uses_utf8_and_bounds_output_size(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"captions":[{"id":"x","text":"中文字幕","summary_index":null}]}')
    monkeypatch.setattr(alignment.subprocess, 'run', run)
    data = alignment.request_batch([{'id': 'x', 'text': 'Original source', 'already_chinese': False}], ['中文摘要'], {})
    assert data['captions'][0]['text'] == '中文字幕'
    assert calls[0][0][1:3] == ['-X', 'utf8']
    assert calls[0][1]['encoding'] == 'utf-8'
    assert calls[0][1]['timeout'] == 200
    cues = [{'text': 'x' * 200} for _ in range(40)]
    batches = list(alignment._batches(cues))
    assert sum(map(len, batches)) == 40
    assert all(len(b) <= 12 and sum(len(c['text']) for c in b) <= 1600 for b in batches)


def test_summary_steps_identical_to_reading_library(tmp_path):
    graph = GraphStore(tmp_path / 'steps.db')
    try:
        for index, meta in enumerate([{'summary': '第一句。第二句？\n第三句!'}, {'summary': '', 'key_points': ['要点甲', '要点乙']} ]):
            graph.conn.execute('INSERT INTO contents(id,kind,source,url,title,status,meta) VALUES (?,?,?,?,?,?,?)',
                (str(index), 'video', 'youtube', '', '', 'processed', json.dumps(meta)))
        graph.conn.commit()
        for doc in reading_library(graph):
            meta = json.loads(graph.conn.execute('SELECT meta FROM contents WHERE id=?', (doc['id'],)).fetchone()[0])
            assert alignment.summary_steps(meta) == [step['text'] for step in doc['steps']]
    finally:
        graph.close()


def test_audio_cache_enriched_without_encoding_or_changing_assets(tmp_path, monkeypatch):
    from ontokb import media_harness
    monkeypatch.setattr(media_harness, 'run_media_task', lambda context, callback, **kw:
                        {**callback(), 'generation_backend': 'codex-harness'})
    graph = GraphStore(tmp_path / 'cache.db')
    graph.conn.execute('INSERT INTO contents(id,kind,source,url,title,status,meta) VALUES (?,?,?,?,?,?,?)',
        ('yt:test', 'video', 'youtube', 'https://www.youtube.com/watch?v=abcdefghijk', '', 'processed', json.dumps({'summary': '现有摘要。'})))
    graph.conn.commit()
    row = media._record(graph, 'yt:test')
    directory, db = media._directory(graph, row, 'audio')
    directory.mkdir(parents=True)
    original = manifest()
    (directory / 'manifest.json').write_text(json.dumps(original), encoding='utf-8')
    for name in ('highlight.m4a', '0.m4a', '0.jpg'):
        (directory / name).write_bytes(b'unchanged media')
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir() if p.suffix != '.json'}
    assert media.status(graph, 'yt:test', 'audio')['status'] == 'unavailable'
    def forbidden(*args, **kwargs):
        pytest.fail('Cached audio upgrade must not download or encode media')
    monkeypatch.setattr(media, '_generate', forbidden)
    monkeypatch.setattr(media, '_download_source', forbidden)
    def enrich(row, directory, data, options):
        return alignment.enrich(data, [{'start': 10, 'end': 20, 'text': 'Original statement'}],
                                json.loads(row['meta']), {}, requester=response)
    monkeypatch.setattr(media, '_enrich_audio', enrich)
    media._worker(db, 'yt:test', directory, {}, 'audio')
    result = media.status(graph, 'yt:test', 'audio')
    assert result['status'] == 'ready' and alignment.aligned(result)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir() if p.suffix != '.json'}
    graph.close()


def test_broken_or_english_alignment_never_ready():
    data = manifest()
    assert not alignment.aligned(data)
    data.update({'alignment_version': 1, 'subtitle_language': 'zh', 'summary_steps': []})
    data['slides'] = [None]
    assert not alignment.aligned(data)


def test_invalid_batch_retried_once_then_checkpointed(tmp_path):
    calls = []
    def invalid_once(batch, steps, options, context):
        calls.append([c['id'] for c in batch])
        if len(calls) == 1:
            return {'captions': []}
        return response(batch, steps, options, context)
    segments = [{'start': 10, 'end': 20, 'text': 'Original statement'}]
    result = alignment.enrich(manifest(), segments, {'summary': '现有摘要。'}, {},
                              requester=invalid_once, cache_dir=tmp_path)
    assert alignment.aligned(result)
    assert len(calls) == 2
    alignment.enrich(manifest(), segments, {'summary': '现有摘要。'}, {},
                     requester=lambda *a: pytest.fail('Completed batch must be reused'), cache_dir=tmp_path)
    assert len(list((tmp_path / 'caption-checkpoints').glob('*.json'))) == 1
    assert not list((tmp_path / 'caption-checkpoints').glob('*.tmp'))


def test_retry_resumes_only_failed_batches_and_summary_invalidates_cache(tmp_path):
    data = manifest()
    data['slides'][0].update({'start': 0, 'end': 13})
    segments = [{'start': i, 'end': i+1, 'text': f'Original statement number {i}'} for i in range(13)]
    calls = []
    def fail_second(batch, steps, options, context):
        calls.append(batch[0]['id'])
        if batch[0]['id'] == 's0c12':
            raise alignment.AlignmentError('Temporary batch failure')
        return response(batch, steps, options, context)
    with pytest.raises(alignment.AlignmentError, match='第 2/2 批'):
        alignment.enrich(data, segments, {'summary': '现有摘要。'}, {},
                         requester=fail_second, cache_dir=tmp_path)
    assert calls == ['s0c0', 's0c12', 's0c12']
    assert len(list((tmp_path / 'caption-checkpoints').glob('*.json'))) == 1
    calls.clear()
    def succeed(batch, steps, options, context):
        calls.append(batch[0]['id'])
        return response(batch, steps, options, context)
    alignment.enrich(data, segments, {'summary': '现有摘要。'}, {}, requester=succeed, cache_dir=tmp_path)
    assert calls == ['s0c12']
    calls.clear()
    alignment.enrich(data, segments, {'summary': '修改后的摘要。'}, {}, requester=succeed, cache_dir=tmp_path)
    assert calls == ['s0c0', 's0c12']


def test_changed_source_or_corrupt_checkpoint_is_not_reused(tmp_path):
    segments = [{'start': 10, 'end': 20, 'text': 'Original statement'}]
    alignment.enrich(manifest(), segments, {}, {}, requester=response, cache_dir=tmp_path)
    path = next((tmp_path / 'caption-checkpoints').glob('*.json'))
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['captions'][0]['summary_index'] = 999
    path.write_text(json.dumps(payload), encoding='utf-8')
    calls = []
    def recorder(batch, *args):
        calls.append(batch[0]['text'])
        return response(batch, *args)
    alignment.enrich(manifest(), segments, {}, {}, requester=recorder, cache_dir=tmp_path)
    assert calls == ['Original statement']
    segments[0]['text'] = 'Changed source speech'
    alignment.enrich(manifest(), segments, {}, {}, requester=recorder, cache_dir=tmp_path)
    assert calls == ['Original statement', 'Changed source speech']


def test_real_proper_name_dense_chinese_caption_is_accepted():
    batch = [{'id': 's4c180', 'text': 'Gockbot, MAAI, and the Que from MANUS', 'already_chinese': False}]
    caption = 'Gockbot、MAAI，以及 MANUS 的 Que'
    result = alignment.validate_batch({'captions': [
        {'id': 's4c180', 'text': caption, 'summary_index': None}]}, batch, [])
    assert result['s4c180']['text'] == caption
    for unchanged in ('Gockbot, MAAI, and the Que from MANUS',
                      'Gockbot and MAAI are the models from MANUS 中文'):
        with pytest.raises(alignment.AlignmentError):
            alignment.validate_batch({'captions': [
                {'id': 's4c180', 'text': unchanged, 'summary_index': None}]}, batch, [])
