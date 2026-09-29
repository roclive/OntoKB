import json

import pytest

from ontokb.graph import GraphStore
from ontokb.models import ExtractedEntity, ExtractedTriple
from ontokb.reading import _mentioned, article_categories, reading_library, ingest_article, set_article_category


@pytest.mark.parametrize(('title', 'meta', 'expected'), [
    ('他断送了中国最后的政改机会', {}, ['历史类']),
    ('中国具身智能泡沫 | 935亿融资', {}, ['AI类', '经济类']),
    ('我认为的泡沫是2029年', {}, ['经济类']),
    ('Shopify如何用AI重构', {}, ['AI类']),
    ('实验研究', {'topics': ['人工智能']}, ['实证类', 'AI类']),
    ('日常随笔', {}, ['未分类']),
    ('邮件 Mail', {}, ['未分类']),
    ('AI', {'categories': [' 历史类 ', '历史类', None]}, ['历史类']),
])
def test_article_categories(title, meta, expected):
    assert article_categories(title, meta) == expected


def test_manual_category_persists_and_preserves_other_content(tmp_path):
    path = tmp_path / 'categories.db'
    g = GraphStore(path)
    meta = {'summary': '人工智能的发展。', 'raw_text': '正文', 'topics': ['AI']}
    for cid in ['a', 'b']:
        g.upsert_content(cid, 'article', 'other', '', 'AI', status='processed', meta=meta)
    for category in ['历史', '科技', '时政']:
        assert set_article_category(g, {'content_id': 'a', 'category': category})['categories'] == [category]
    g.close()
    g = GraphStore(path)
    docs = {d['id']: d for d in reading_library(g)}
    assert docs['a']['categories'] == ['时政']
    assert docs['b']['categories'] == ['AI类']
    saved = json.loads(g.conn.execute("SELECT meta FROM contents WHERE id='a'").fetchone()[0])
    assert saved == {**meta, 'categories': ['时政']}
    for body in [{'content_id': 'a', 'category': []}, {'content_id': 'missing', 'category': '历史'},
                 {'content_id': 'a', 'category': 'invalid'}]:
        with pytest.raises(ValueError):
            set_article_category(g, body)
    g.close()


def test_summary_walk_is_source_scoped_and_never_invents_edges():
    g = GraphStore()
    for name, typ, aliases in [('OpenAI', 'Organization', ['Open AI']), ('Model', 'SoftwareApplication', []),
                               ('Other', 'Organization', [])]:
        g.upsert_entity(ExtractedEntity(name=name, type=typ, aliases=aliases), source='a')
    g.add_triple(ExtractedTriple(subject='OpenAI', predicate='develops', object='Model', evidence='quote'), g.ontology, source='a')
    g.add_triple(ExtractedTriple(subject='Other', predicate='develops', object='Model'), g.ontology, source='b')
    g.upsert_content('a', 'article', 'other', '', 'Article', status='processed',
                     meta={'summary': 'Open AI开发软件。Other也出现了。没有实体的句子。', 'key_points': ['要点']})
    doc = reading_library(g)[0]
    assert len(doc['steps']) == 3
    first = doc['steps'][0]
    assert first['entities'] == ['OpenAI']
    assert first['neighbors'] == ['Model']
    assert len(first['edges']) == 1 and first['edges'][0]['evidence'] == 'quote'
    assert not doc['steps'][1]['edges']  # Other's edge exists only in source b.
    assert not doc['steps'][2]['entities'] and not doc['steps'][2]['edges']
    g.close()


def test_reading_http_endpoints_and_large_unicode_article(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from ontokb.api import GraphApiHandler
    from ontokb import reading

    db = tmp_path / 'api.db'
    g = GraphStore(db)
    g.upsert_content('a', 'article', 'other', '', 'Article', status='processed', meta={'summary': '摘要。'})
    g.close()
    received = []
    monkeypatch.setattr(reading, 'ingest_article', lambda store, body, **kwargs:
                        received.append(body) or {'content_id': 'new'})

    class Handler(GraphApiHandler):
        def setup(self):
            super().setup()
            self.store = GraphStore(db)

        def finish(self):
            try:
                super().finish()
            finally:
                self.store.close()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(origin+'/api/reading') as response:
            assert json.load(response)['library'][0]['steps'][0]['text'] == '摘要。'
        request = Request(origin+'/api/reading/category',
                          data=json.dumps({'content_id': 'a', 'category': '历史'}).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': origin})
        with urlopen(request) as response:
            assert json.load(response)['categories'] == ['历史']
        with urlopen(origin+'/api/reading') as response:
            assert json.load(response)['library'][0]['categories'] == ['历史']
        body = {'title': 'Long article', 'text': '正文内容。'*5000}
        request = Request(origin+'/api/articles', data=json.dumps(body, ensure_ascii=False).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': origin})
        with urlopen(request) as response:
            assert json.load(response)['content_id'] == 'new'
        assert received == [body]
        with urlopen(origin) as response:
            assert response.headers['Cache-Control'] == 'no-store'
            assert '新建摘要' in response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_ascii_alias_boundaries_and_mixed_chinese():
    assert _mentioned('采用OpenAI的技术', 'OpenAI')
    assert not _mentioned('OpenAI develops models', 'AI')
    assert not _mentioned('Driver software', 'River')


def test_empty_library_and_fallback_to_key_points():
    g = GraphStore()
    assert reading_library(g) == []
    g.upsert_content('a', 'article', 'other', '', 'Article', status='processed', meta={'key_points': ['一个要点']})
    assert reading_library(g)[0]['steps'][0]['text'] == '一个要点'
    g.close()


@pytest.mark.parametrize('body', [{'title': '', 'text': 'x'*30}, {'title': 'A', 'text': 'short'},
                                  {'title': 'A', 'text': 'x'*30, 'url': 'javascript:alert(1)'},
                                  {'title': 'A', 'text': []}])
def test_article_validation_before_model_call(body):
    g = GraphStore()
    with pytest.raises(ValueError):
        ingest_article(g, body)
    assert not reading_library(g)
    g.close()


def test_article_ingest_end_to_end_and_dedup(tmp_path, monkeypatch):
    from ontokb import pipeline
    from ontokb.models import ProcessedContent
    db = tmp_path / 'test.db'
    monkeypatch.setattr(pipeline, 'load_config', lambda: {'paths': {'vault': str(tmp_path/'vault')}})
    calls = []
    def process(item, *args, **kwargs):
        calls.append(item.raw_text)
        return ProcessedContent(content_id=item.id, summary='OpenAI发布软件。', key_points=['要点'], topics=['OpenAI'],
                                entities=[ExtractedEntity(name='OpenAI',type='Organization')])
    monkeypatch.setattr(pipeline, 'process_content', process)
    g = GraphStore(db)
    body = {'title': 'New article', 'text': 'OpenAI发布软件。这里是用于验证摘要功能的文章正文。', 'url': 'https://example.com/a'}
    result = ingest_article(g, body)
    doc = reading_library(g)[0]
    assert doc['id'] == result['content_id'] and doc['kind'] == 'article'
    assert doc['steps'][0]['entities'] == ['OpenAI']
    meta = json.loads(g.conn.execute('SELECT meta FROM contents').fetchone()[0])
    assert meta['raw_text'] == body['text']
    assert g.get_entity('New article')['type'] == 'Article'
    assert ingest_article(g, body)['reused']
    assert len(calls) == 1
    with pytest.raises(ValueError, match='标题'):
        ingest_article(g, {**body,'text':body['text']+'修改版本'})
    g.close()
