import csv

from ontokb.media_npocut import write_edit_artifacts


def test_real_npocut_retimes_gapped_clips_and_keeps_chinese(tmp_path):
    manifest = {'slides': [
        {'start': 10, 'end': 14, 'captions': [
            {'start': 1, 'end': 3, 'text': '第一段中文。'}]},
        {'start': 30, 'end': 35, 'timeline_start': 4, 'captions': [
            {'start': 0, 'end': 2, 'text': '第二段中文。'}]},
    ]}
    segments = [{'start': 11, 'end': 13, 'text': 'First source cue'},
                {'start': 20, 'end': 22, 'text': 'Excluded'},
                {'start': 30, 'end': 32, 'text': 'Second source cue'}]
    evidence = write_edit_artifacts(tmp_path, manifest, segments)
    rows = list(csv.DictReader((tmp_path / 'clip_plan.csv').open(encoding='utf-8')))
    assert [(r['start'], r['end']) for r in rows] == [('10.000', '14.000'), ('30.000', '35.000')]
    retimed = (tmp_path / evidence['retimed_subtitles']).read_text(encoding='utf-8')
    assert '00:00:01,000 --> 00:00:03,000' in retimed
    assert '00:00:04,000 --> 00:00:06,000' in retimed
    assert 'Excluded' not in retimed
    chinese = (tmp_path / evidence['chinese_subtitles']).read_text(encoding='utf-8')
    assert '第一段中文。' in chinese and '00:00:04,000 --> 00:00:06,000' in chinese
    assert evidence['executed_script'] == 'srt_slice.py'
