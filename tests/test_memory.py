import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ontokb.editing import EditingConflict, EditingService
from ontokb.graph import GraphStore
from ontokb.memory import MemoryService
from ontokb.models import ExtractedEntity, ExtractedTriple


@pytest.fixture
def memory(tmp_path):
    graph = GraphStore(tmp_path / 'memory.db')
    for cid in ('old', 'new'):
        graph.upsert_content(cid, 'article', 'other', f'https://example.com/{cid}', cid,
                             status='processed', meta={'summary': f'{cid} summary'})
    graph.upsert_entity(ExtractedEntity(name='A company', type='Organization'), source='old')
    graph.upsert_entity(ExtractedEntity(name='A prediction', type='Claim'), source='old')
    graph.add_triple(ExtractedTriple(subject='A company', predicate='makesClaim', object='A prediction',
                                    evidence='Old quoted text'), graph.ontology, source='old')
    yield MemoryService(graph)
    graph.close()


def record(service, kind='claim'):
    return next(r for r in service.records() if r['snapshot']['kind'] == kind)


def save(service, row=None, **kwargs):
    row = row or record(service)
    return service.update(dict(key=row['key'], revision=row['revision'], reviewed=True,
                               included=True, stance='agree', note='My initial judgment') | kwargs)


def test_existing_verification_does_not_imply_personal_endorsement(memory):
    graph = memory.graph
    EditingService(graph).update_entity(graph.get_entity('A prediction')['id'], {'verificationStatus': 'verified'})
    row = record(memory)
    assert not row['reviewed'] and not row['included'] and row['stance'] == 'unset'
    save(memory, stance='disagree')
    assert json.loads(graph.get_entity('A prediction')['properties'])['verificationStatus'] == 'verified'
    assert record(memory)['stance'] == 'disagree'


def test_scope_review_and_stance_are_independent_and_no_cascade(memory):
    save(memory, reviewed=False, stance='unset')
    assert record(memory)['included'] and not record(memory)['reviewed']
    assert not record(memory, 'entity')['included']
    assert not record(memory, 'triple')['included']
    save(memory, reviewed=False, stance='uncertain')
    assert record(memory)['stance'] == 'uncertain'
    assert memory.compare('new', answer=lambda *a, **k: pytest.fail('unreviewed baseline'))['status'] == 'no_baseline'
    save(memory, record(memory, 'entity'), stance='unset')
    with pytest.raises(ValueError):
        save(memory, record(memory, 'entity'), stance='agree')


def test_version_conflict_and_history_preserve_both_states(memory):
    original = record(memory)
    save(memory, original)
    with pytest.raises(EditingConflict):
        save(memory, original, stance='disagree')
    save(memory, stance='uncertain', source_id='new', note='New evidence changes the conditions')
    history = memory.bootstrap()['history']
    assert len(history) == 2
    assert history[0]['before_state']['stance'] == 'agree'
    assert history[0]['after_state']['stance'] == 'uncertain'
    assert history[0]['source_id'] == 'new'
    save(memory, stance='uncertain', note='New evidence changes the conditions')
    assert len(memory.bootstrap()['history']) == 2


def test_renaming_or_removing_graph_never_transfers_endorsement(memory):
    save(memory)
    old = record(memory)
    graph = memory.graph
    EditingService(graph).update_entity(graph.get_entity('A prediction')['id'], {'name': 'A different prediction'})
    rows = memory.records()
    snapshot = next(r for r in rows if r['key'] == old['key'])
    assert snapshot['included'] and not snapshot['current']
    assert snapshot['snapshot']['title'] == 'A prediction'
    fresh = next(r for r in rows if r['snapshot']['title'] == 'A different prediction')
    assert not fresh['reviewed'] and fresh['stance'] == 'unset'


def test_changed_relation_evidence_requires_new_review(memory):
    save(memory, record(memory, 'triple'))
    memory.conn.execute("UPDATE triples SET evidence='Changed evidence'")
    memory.conn.commit()
    rows = [r for r in memory.records() if r['snapshot']['kind'] == 'triple']
    assert len(rows) == 2
    assert next(r for r in rows if r['current'])['reviewed'] is False
    assert next(r for r in rows if not r['current'])['included'] is True


def test_reinserted_identical_relation_keeps_snapshot_but_exposes_current_id(memory):
    original = record(memory, 'triple')
    save(memory, original)
    memory.conn.execute('UPDATE triples SET id=id+100')
    memory.conn.commit()
    current = record(memory, 'triple')
    assert current['key'] == original['key'] and current['included']
    assert current['snapshot']['target_id'] == original['snapshot']['target_id']
    assert current['current_target_id'] == original['snapshot']['target_id'] + 100


def test_compare_is_read_only_honors_dissent_and_excludes_same_source(memory):
    save(memory, stance='disagree')
    before = '\n'.join(memory.conn.iterdump())
    calls = []
    def answer(question, context, **options):
        calls.append(context)
        assert context['personal_judgments'][0]['stance'] == 'disagree'
        assert '禁止自动更新记忆' in question
        return '待确认建议'
    result = memory.compare('new', answer=answer)
    assert result['status'] == 'suggestion' and len(calls) == 1
    assert '\n'.join(memory.conn.iterdump()) == before
    assert memory.compare('old', answer=answer)['status'] == 'no_baseline'
    assert len(calls) == 1


def test_no_baseline_does_not_call_model_and_invalid_source_fails(memory):
    assert memory.compare('new', answer=lambda *a, **k: pytest.fail('must not call'))['status'] == 'no_baseline'
    with pytest.raises(ValueError):
        memory.compare('missing')
    with pytest.raises(ValueError):
        save(memory, source_id='missing')
    assert memory.bootstrap()['history'] == []


def test_new_source_context_does_not_misattribute_old_quotes(memory):
    save(memory)
    graph = memory.graph
    graph.upsert_entity(ExtractedEntity(name='A prediction', type='Claim'), source='new')
    graph.add_triple(ExtractedTriple(subject='A company', predicate='makesClaim', object='A prediction',
                                    evidence='New quoted text'), graph.ontology, source='new')
    def answer(question, context, **options):
        new = context['new_source']['assertions']
        assert new
        assert all(e['source'] == 'new' for a in new for e in a['evidence'])
        assert all('Old quoted text' not in json.dumps(a) for a in new)
        return '建议'
    memory.compare('new', answer=answer)


def test_persistence_and_existing_database_reopen(memory):
    save(memory)
    path = memory.conn.execute('PRAGMA database_list').fetchone()[2]
    with_graph = GraphStore(path)
    try:
        assert record(MemoryService(with_graph))['stance'] == 'agree'
        assert len(MemoryService(with_graph).bootstrap()['history']) == 1
    finally:
        with_graph.close()


def test_memory_http_roundtrip_conflicts_and_read_only_comparison(memory, monkeypatch):
    from ontokb.api import GraphApiHandler
    path = memory.conn.execute('PRAGMA database_list').fetchone()[2]
    class Handler(GraphApiHandler):
        def setup(self):
            super().setup()
            self.store = GraphStore(path)
        def finish(self):
            try:
                super().finish()
            finally:
                self.store.close()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(route, body=None):
        req = Request(f'http://127.0.0.1:{server.server_port}{route}',
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)
    try:
        status, data = request('/api/memory')
        assert status == 200 and len(data['records']) == 3
        row = next(r for r in data['records'] if r['snapshot']['kind'] == 'claim')
        body = dict(key=row['key'], revision=0, reviewed=True, included=True, stance='uncertain', note='Conditional')
        assert request('/api/memory/review', body)[0] == 200
        assert request('/api/memory/review', body)[0] == 409
        assert request('/api/memory/review', body | {'reviewed': 'true'})[0] == 400
        monkeypatch.setattr('ontokb.llm.answer_graph_question', lambda *a, **kw: '待确认建议')
        before = memory.bootstrap()
        status, result = request('/api/memory/compare', {'source_id': 'new'})
        assert status == 200 and result['status'] == 'suggestion'
        assert memory.bootstrap() == before
        assert request('/api/memory/compare', {'source_id': 'missing'})[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
