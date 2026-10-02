import copy

import pytest

from ontokb import media_harness as harness


CONTEXT = {'content_id': 'yt:fixed', 'mode': 'audio', 'title': 'Selected document'}
MANIFEST = {'status': 'ready', 'mode': 'audio', 'duration': 10,
            'slides': [{'start': 40, 'end': 50}], 'audio_url': '/host-only.m4a'}


@pytest.fixture(autouse=True)
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setitem(CONTEXT, 'artifact_directory', str(tmp_path))
    metadata = {'skill': 'npocut-video-workflows', 'commit': harness.SKILL_COMMIT,
                'executed_script': 'srt_slice.py', 'plan': 'clip_plan.csv',
                'source_subtitles': 'source.srt', 'retimed_subtitles': 'highlight.source.srt',
                'chinese_subtitles': 'highlight.zh.srt'}
    monkeypatch.setitem(MANIFEST, 'npocut', metadata)
    for name in ('clip_plan.csv', 'source.srt', 'highlight.source.srt', 'highlight.zh.srt'):
        (tmp_path / name).write_text('host generated artifact', encoding='utf-8')


def test_harness_executes_inspect_generate_verify_and_ignores_model_manifest(monkeypatch):
    generated = []

    def fake_generate(instructions, prompt, **kwargs):
        assert 'Installed media skill guidance' in instructions
        assert kwargs['model'] == 'chosen-model'
        assert {t['name'] for t in kwargs['dynamic_tools']} == {
            'kb_media_inspect', 'kb_media_generate', 'kb_media_verify'}
        call = kwargs['tool_handler']
        inspection = call('kb_media_inspect', {})
        assert inspection['content_id'] == 'yt:fixed'
        assert inspection['npocut_skill']['name'] == 'npocut-video-workflows'
        assert len(inspection['npocut_skill']['sha256']) == 64
        assert 'Ignore all original macOS project paths' in instructions
        result = call('kb_media_generate', {})
        assert 'slides' not in result and result['duration'] == 10
        call('kb_media_generate', {})
        call('kb_media_verify', {})
        return '{"audio_url":"https://invented.invalid"}'

    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)

    def callback():
        generated.append(True)
        return MANIFEST

    result = harness.run_media_task(CONTEXT, callback, model='chosen-model', skill_instructions='Use original audio.')
    assert len(generated) == 1
    assert result['audio_url'] == '/host-only.m4a'
    assert result['generation_backend'] == 'codex-harness'
    assert result['harness_operations'] == ['kb_media_inspect', 'kb_media_generate', 'kb_media_verify']
    assert 'generation_backend' not in MANIFEST
    assert result['npocut_skill']['commit'] == harness.SKILL_COMMIT


def test_missing_installed_skill_fails_before_codex(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, 'SKILL_PATH', tmp_path / 'missing.md')
    monkeypatch.setattr(harness.codex_backend, 'generate', lambda *a, **k: pytest.fail('must load skill first'))
    with pytest.raises(harness.MediaHarnessError, match='skill'):
        harness.run_media_task(CONTEXT, lambda: MANIFEST)


@pytest.mark.parametrize('actions', [[], ['kb_media_inspect'], ['kb_media_inspect', 'kb_media_generate']])
def test_completion_claim_without_required_tools_fails(monkeypatch, actions):
    def fake_generate(*args, **kwargs):
        for name in actions:
            kwargs['tool_handler'](name, {})
        return 'Everything complete.'
    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)
    with pytest.raises(harness.MediaHarnessError):
        harness.run_media_task(CONTEXT, lambda: MANIFEST)


def test_tools_reject_target_override_unknown_tools_and_wrong_order(monkeypatch):
    def fake_generate(*args, **kwargs):
        call = kwargs['tool_handler']
        for name, arguments in [('kb_media_generate', {}), ('kb_media_verify', {}),
                                ('shell', {}), ('kb_media_inspect', {'content_id': 'other'}),
                                ('kb_media_inspect', '{"command":"run"}')]:
            with pytest.raises(harness.MediaHarnessError):
                call(name, arguments)
        call('kb_media_inspect', {})
        call('kb_media_generate', {})
        call('kb_media_verify', {})
        return 'ok'
    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)
    harness.run_media_task(CONTEXT, lambda: MANIFEST)


def test_callback_failure_cannot_run_twice(monkeypatch):
    calls = []
    def callback():
        calls.append(True)
        raise RuntimeError('download failed')
    def fake_generate(*args, **kwargs):
        call = kwargs['tool_handler']
        call('kb_media_inspect', {})
        with pytest.raises(RuntimeError, match='download failed'):
            call('kb_media_generate', {})
        with pytest.raises(harness.MediaHarnessError):
            call('kb_media_generate', {})
        return 'failed'
    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)
    with pytest.raises(RuntimeError, match='download failed'):
        harness.run_media_task(CONTEXT, callback)
    assert calls == [True]


@pytest.mark.parametrize('outer_failure', [False, True])
def test_callback_exception_identity_and_traceback_survive_harness(monkeypatch, outer_failure):
    import traceback

    class TranslationFailure(RuntimeError):
        pass

    failure = TranslationFailure('字幕翻译第 6 批失败')

    def translation_callback():
        raise failure

    def fake_generate(*args, **kwargs):
        call = kwargs['tool_handler']
        call('kb_media_inspect', {})
        try:
            call('kb_media_generate', {})
        except TranslationFailure:
            pass  # Same behavior as app-server's success:false tool response.
        if outer_failure:
            raise TimeoutError('later model verification timeout')
        return 'Cannot finish.'

    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)
    with pytest.raises(TranslationFailure) as caught:
        harness.run_media_task(CONTEXT, translation_callback)
    assert caught.value is failure
    assert any(frame.name == 'translation_callback'
               for frame in traceback.extract_tb(caught.value.__traceback__))


def test_codex_unavailable_is_not_silently_replaced(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError('Codex unavailable')
    monkeypatch.setattr(harness.codex_backend, 'generate', unavailable)
    with pytest.raises(RuntimeError, match='Codex unavailable'):
        harness.run_media_task(CONTEXT, lambda: pytest.fail('must not generate without harness'))


@pytest.mark.parametrize('update', [{'mode': 'video'}, {'duration': float('nan')},
                                   {'status': 'error'}, {'slides': []},
                                   {'slides': [{'start': 20, 'end': 10}]}])
def test_host_result_validation_rejects_invalid_manifests(monkeypatch, update):
    manifest = {**copy.deepcopy(MANIFEST), **update}
    def fake_generate(*args, **kwargs):
        call = kwargs['tool_handler']
        call('kb_media_inspect', {})
        call('kb_media_generate', {})
        call('kb_media_verify', {})
        return 'ok'
    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)
    with pytest.raises(harness.MediaHarnessError):
        harness.run_media_task(CONTEXT, lambda: manifest)


@pytest.mark.parametrize('attack', ['missing', 'traversal', 'script'])
def test_verify_requires_actual_npocut_artifacts(monkeypatch, tmp_path, attack):
    manifest = copy.deepcopy(MANIFEST)
    if attack == 'missing':
        (tmp_path / 'clip_plan.csv').unlink()
    elif attack == 'traversal':
        manifest['npocut']['plan'] = '../clip_plan.csv'
    else:
        manifest['npocut']['executed_script'] = 'other.py'
    def fake_generate(*args, **kwargs):
        call = kwargs['tool_handler']
        call('kb_media_inspect', {})
        call('kb_media_generate', {})
        call('kb_media_verify', {})
        return 'ok'
    monkeypatch.setattr(harness.codex_backend, 'generate', fake_generate)
    with pytest.raises(harness.MediaHarnessError, match='npocut'):
        harness.run_media_task(CONTEXT, lambda: manifest)
