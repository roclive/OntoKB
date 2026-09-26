import pytest

from ontokb.assistant import video_url, respond
from ontokb.graph import GraphStore


@pytest.mark.parametrize('text', [
    '分析 https://www.youtube.com/watch?v=XAujxrtd4uI 并入库',
    '[video](https://youtu.be/XAujxrtd4uI)',
    'https://m.youtube.com/shorts/XAujxrtd4uI',
])
def test_video_detection(text):
    assert video_url(text) == ('https://www.youtube.com/watch?v=XAujxrtd4uI', 'XAujxrtd4uI')


@pytest.mark.parametrize('text', ['https://youtube.com.evil.test/watch?v=XAujxrtd4uI',
                                 'https://youtube.com/watch?v=invalid', 'Codex uses what?'])
def test_non_video(text):
    assert video_url(text) is None


def test_video_reuses_processed_content(tmp_path, monkeypatch):
    graph = GraphStore(tmp_path / 'kb.db')
    graph.upsert_content('yt:XAujxrtd4uI', 'video', 'youtube',
                         'https://www.youtube.com/watch?v=XAujxrtd4uI', 'Video',
                         status='processed', meta={'summary': 'Grounded summary'})
    monkeypatch.setattr('ontokb.pipeline.Pipeline.fetch', lambda *a: pytest.fail('must not fetch twice'))
    seen = {}
    def answer(question, context, **kwargs):
        seen.update(context)
        return 'analysis'
    monkeypatch.setattr('ontokb.llm.answer_graph_question', answer)
    result = respond(graph, 'https://youtu.be/XAujxrtd4uI')
    assert result['ingested']['reused']
    assert seen['video_analysis']['summary'] == 'Grounded summary'
    graph.close()


def test_video_fetch_extract_store_and_answer(tmp_path, monkeypatch):
    from ontokb.models import ProcessedContent
    from ontokb.pipeline import load_config
    config = load_config()
    config['paths']['vault'] = str(tmp_path / 'vault')
    monkeypatch.setattr('ontokb.assistant.load_config', lambda: config)
    def fetch(self, item, **kwargs):
        item.title = 'Test video'
        item.raw_text = 'Actual source content'
    monkeypatch.setattr('ontokb.pipeline.Pipeline.fetch', fetch)
    monkeypatch.setattr('ontokb.pipeline.process_content', lambda item, *a, **k:
                        ProcessedContent(content_id=item.id, summary='Summary from source',
                                         key_points=['Important point'], topics=[]))
    monkeypatch.setattr('ontokb.llm.answer_graph_question', lambda *a, **k: 'Analysis')
    graph = GraphStore(tmp_path / 'test.db')
    progress = []
    result = respond(graph, 'Analyze https://youtu.be/XAujxrtd4uI', progress=progress.append)
    assert result['ingested']['content_id'] == 'yt:XAujxrtd4uI'
    assert graph.conn.execute('SELECT status FROM contents').fetchone()[0] == 'processed'
    assert result['context']['video_analysis']['key_points'] == ['Important point']
    assert len(progress) == 3
    assert list((tmp_path / 'vault' / 'Sources').glob('*.md'))
    graph.close()


def test_fetch_failure_does_not_claim_ingested(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('No transcript available')
    monkeypatch.setattr('ontokb.pipeline.Pipeline.fetch', fail)
    graph = GraphStore(tmp_path / 'test.db')
    with pytest.raises(RuntimeError, match='No transcript'):
        respond(graph, 'https://youtu.be/XAujxrtd4uI')
    assert graph.conn.execute('SELECT count(*) FROM contents').fetchone()[0] == 0
    graph.close()
