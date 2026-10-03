"""Lossless entity consolidation against disposable databases and vaults only."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from ontokb.editing import EditingConflict, EditingError, EditingService
from ontokb.graph import GraphStore
from ontokb.memory import MemoryService
from ontokb.models import ExtractedEntity, ExtractedTriple
from ontokb.models import ContentItem
from ontokb.pipeline import Pipeline
from ontokb.vault import ObsidianVault
from test_editing import editor, editor_http  # Reuse disposable HTTP-server fixtures.


@pytest.fixture
def merge_editor(tmp_path):
    graph = GraphStore(tmp_path / 'merge.db')
    for name, kind, aliases, source in [
        ('NVIDIA', 'Organization', ['NVDA'], 'article:en'),
        ('英伟达', 'Organization', ['辉达'], 'article:zh'),
        ('GPU', 'Product', [], 'article:en'),
        ('Someone', 'Person', [], 'article:en'),
        ('Document A', 'Article', [], 'article:en'),
        ('Document B', 'Article', [], 'article:zh'),
    ]:
        graph.upsert_entity(ExtractedEntity(name=name, type=kind, aliases=aliases), source=source)
    for subject, predicate, obj, source, evidence in [
        ('NVIDIA', 'makes', 'GPU', 'article:en', 'First original quote'),
        ('英伟达', 'makes', 'GPU', 'article:en', 'Second independent quote'),
        ('英伟达', 'makes', 'GPU', 'article:zh', '中文出处'),
        ('Someone', 'worksFor', 'NVIDIA', 'article:en', 'Employment evidence'),
        ('NVIDIA', 'relatedTo', '英伟达', 'article:en', 'Related names'),
    ]:
        graph.add_triple(ExtractedTriple(subject=subject, predicate=predicate, object=obj,
                         evidence=evidence), graph.ontology, source=source)
    vault = ObsidianVault(tmp_path / 'vault')
    for row in graph.conn.execute('SELECT name FROM entities'):
        vault.write_entity_note(graph, row['name'])
    yield EditingService(graph, vault), graph, vault
    graph.close()


def ident(graph, name):
    return graph.get_entity(name)['id']


def state(graph):
    return '\n'.join(graph.conn.iterdump())


def notes(vault):
    return {str(p.relative_to(vault.root)): p.read_bytes() for p in vault.root.rglob('*.md')}


def records(graph, table):
    return [dict(r) for r in graph.conn.execute(f'SELECT * FROM {table} ORDER BY rowid')]


def merge(service, graph):
    source, target = ident(graph, 'NVIDIA'), ident(graph, '英伟达')
    preview = service.preview_merge(source, {'target_id': target})
    result = service.merge_entities(source, {'target_id': target, 'preview_token': preview['preview_token']})
    return preview, result


def test_preview_is_read_only_and_exposes_duplicates_sources_and_self_relations(merge_editor):
    service, graph, vault = merge_editor
    before, files = state(graph), notes(vault)
    preview = service.preview_merge(ident(graph, 'NVIDIA'), {'target_id': ident(graph, '英伟达')})
    assert preview['can_merge'] and not preview['blocked_reasons']
    assert preview['preview_token']
    assert {'NVIDIA', 'NVDA', '辉达'} <= set(preview['aliases'])
    assert set(preview['sources']) == {'article:en', 'article:zh'}
    assert preview['impact']['duplicate_relations'] == 1
    assert preview['impact']['self_relations'] == 1
    assert preview['warnings']
    assert state(graph) == before and notes(vault) == files


@pytest.mark.parametrize('target_name', ['NVIDIA', 'Someone', 'Document A'])
def test_invalid_merge_rejects_atomically(merge_editor, target_name):
    service, graph, vault = merge_editor
    before, files = state(graph), notes(vault)
    source, target = ident(graph, 'NVIDIA'), ident(graph, target_name)
    with pytest.raises(EditingError):
        service.merge_entities(source, {'target_id': target, 'preview_token': 'invalid'})
    assert state(graph) == before and notes(vault) == files


def test_document_identity_merging_is_explicitly_blocked(merge_editor):
    service, graph, _ = merge_editor
    preview = service.preview_merge(ident(graph, 'Document A'), {'target_id': ident(graph, 'Document B')})
    assert not preview['can_merge'] and preview['blocked_reasons']


def test_merge_transfers_aliases_sources_and_keeps_target_identity(merge_editor):
    service, graph, vault = merge_editor
    source_id, target_id = ident(graph, 'NVIDIA'), ident(graph, '英伟达')
    _, result = merge(service, graph)
    assert result['ok'] and result['entity']['id'] == target_id
    assert not graph.conn.execute('SELECT 1 FROM entities WHERE id=?', (source_id,)).fetchone()
    for name in ['NVIDIA', 'NVDA', '英伟达', '辉达']:
        assert ident(graph, name) == target_id
    assert set(json.loads(graph.get_entity('英伟达')['sources'])) == {'article:en', 'article:zh'}
    assert not graph.conn.execute('SELECT 1 FROM triples WHERE subject_id=? OR object_id=?', (source_id, source_id)).fetchone()
    assert '[[英伟达]]' in (vault.root / 'Entities/Someone.md').read_text(encoding='utf-8')
    assert not (vault.root / 'Entities/NVIDIA.md').exists()


def test_duplicate_relation_original_quotes_are_preserved_and_self_loop_is_retained(merge_editor):
    service, graph, _ = merge_editor
    originals = records(graph, 'triples')
    _, result = merge(service, graph)
    target = result['entity']['id']
    assert len(records(graph, 'triples')) == len(originals) - 1
    assert graph.conn.execute('SELECT 1 FROM triples WHERE subject_id=? AND object_id=?', (target, target)).fetchone()
    evidence_rows = records(graph, 'triple_evidence')
    retained = json.dumps(evidence_rows, ensure_ascii=False)
    for quote in ('First original quote', 'Second independent quote'):
        assert quote in retained
    assert len([r for r in records(graph, 'triples') if r['predicate'] == 'makes']) == 2


def test_merge_undo_restores_exact_identities_relations_aliases_and_vault(merge_editor):
    service, graph, vault = merge_editor
    tables = ['entities', 'aliases', 'triples', 'manual_entities', 'manual_triples', 'manual_triple_keys']
    before = {t: records(graph, t) for t in tables}
    files = notes(vault)
    _, result = merge(service, graph)
    service.undo(result['change_id'])
    assert {t: records(graph, t) for t in tables} == before
    assert notes(vault) == files
    assert service.bootstrap()['history'][0]['undone'] == 1


@pytest.mark.parametrize('mutation', ['alias', 'relation', 'memory'])
def test_changed_preview_cannot_commit(merge_editor, mutation):
    service, graph, vault = merge_editor
    source, target = ident(graph, 'NVIDIA'), ident(graph, '英伟达')
    preview = service.preview_merge(source, {'target_id': target})
    if mutation == 'alias':
        service.update_entity(target, {'aliases': ['辉达', 'New alias']})
    elif mutation == 'relation':
        triple = graph.conn.execute('SELECT id FROM triples LIMIT 1').fetchone()[0]
        service.update_triple(triple, {'confidence': 0.33})
    else:
        remember(MemoryService(graph), source, note='New review')
    before, files = state(graph), notes(vault)
    with pytest.raises(EditingConflict):
        service.merge_entities(source, {'target_id': target, 'preview_token': preview['preview_token']})
    assert state(graph) == before and notes(vault) == files


def remember(memory, target_id, *, note):
    record = next(r for r in memory.records() if r['snapshot']['kind'] == 'entity' and r['snapshot']['target_id'] == target_id)
    memory.update(dict(key=record['key'], revision=record['revision'], reviewed=True,
                       included=True, stance='unset', note=note))
    return record['key']


def test_both_personal_reviews_survive_merge_with_original_snapshots_and_undo(merge_editor):
    service, graph, _ = merge_editor
    memory = MemoryService(graph)
    source, target = ident(graph, 'NVIDIA'), ident(graph, '英伟达')
    keys = [remember(memory, source, note='English review'), remember(memory, target, note='中文审核')]
    before = records(graph, 'personal_memory')
    _, result = merge(service, graph)
    assert records(graph, 'personal_memory') == before
    saved = {r['key']: r for r in memory.records()}
    for key in keys:
        assert saved[key]['reviewed'] and saved[key]['included']
    # Source judgment stays archived: its approval must never transfer silently.
    assert saved[keys[0]]['current_target_id'] is None
    assert saved[keys[0]]['associated_target_id'] == target
    assert saved[keys[1]]['current_target_id'] == target
    service.undo(result['change_id'])
    assert records(graph, 'personal_memory') == before
    saved = {r['key']: r for r in memory.records()}
    assert saved[keys[0]]['current_target_id'] == source


def test_new_personal_judgment_blocks_unsafe_merge_undo(merge_editor):
    service, graph, vault = merge_editor
    _, result = merge(service, graph)
    remember(MemoryService(graph), result['entity']['id'], note='Reviewed after merge')
    before, files = state(graph), notes(vault)
    with pytest.raises(EditingConflict):
        service.undo(result['change_id'])
    assert state(graph) == before and notes(vault) == files


def test_vault_write_failure_rolls_back_merge_and_audit(merge_editor, monkeypatch):
    service, graph, vault = merge_editor
    before, files = state(graph), notes(vault)

    def fail(*args, **kwargs):
        raise OSError('Simulated merge disk failure')

    monkeypatch.setattr(vault, 'write_entity_note', fail)
    with pytest.raises(OSError, match='merge disk failure'):
        merge(service, graph)
    assert state(graph) == before and notes(vault) == files


def test_shared_alias_edit_is_searchable_without_choosing_an_arbitrary_identity(merge_editor):
    service, graph, _ = merge_editor
    first, second = ident(graph, 'NVIDIA'), ident(graph, '英伟达')
    service.update_entity(first, {'aliases': ['NVDA', 'Chip company']})
    change = service.update_entity(second, {'aliases': ['辉达', 'Chip company']})
    assert {e['id'] for e in graph.search_entities('Chip company', mode='phrase')} == {first, second}
    with pytest.raises(ValueError):
        graph.get_entity('Chip company')
    service.undo(change['change_id'])
    assert ident(graph, 'Chip company') == first


def test_extraction_keeps_distinct_canonical_entities_with_shared_alias(merge_editor):
    _, graph, _ = merge_editor
    first = graph.upsert_entity(ExtractedEntity(name='Firm A', type='Organization', aliases=['Shared']), source='one')
    second = graph.upsert_entity(ExtractedEntity(name='Firm B', type='Organization', aliases=['Shared']), source='two')
    assert first != second
    assert {e['id'] for e in graph.search_entities('Shared', mode='phrase')} == {first, second}
    with pytest.raises(ValueError):
        graph.get_entity('Shared')
    # An exact canonical name still identifies its owner even when another node uses it as an alias.
    graph.upsert_entity(ExtractedEntity(name='Firm C', type='Organization', aliases=['Firm A']), source='three')
    assert ident(graph, 'Firm A') == first


def test_canonical_names_remain_unique_with_shared_alias_support(merge_editor):
    service, graph, vault = merge_editor
    before, files = state(graph), notes(vault)
    with pytest.raises(EditingError):
        service.update_entity(ident(graph, 'NVIDIA'), {'name': '英伟达'})
    assert state(graph) == before and notes(vault) == files


def test_merge_preserves_alias_shared_by_third_entity(merge_editor):
    service, graph, _ = merge_editor
    third = graph.upsert_entity(ExtractedEntity(name='Another firm', type='Organization'), source='three')
    service.update_entity(third, {'aliases': ['Shared company']})
    service.update_entity(ident(graph, 'NVIDIA'), {'aliases': ['NVDA', 'Shared company']})
    _, result = merge(service, graph)
    assert {e['id'] for e in graph.search_entities('Shared company', mode='phrase')} == {third, result['entity']['id']}
    assert ident(graph, 'NVIDIA') == result['entity']['id']
    assert ident(graph, 'Another firm') == third


def test_old_single_owner_alias_schema_migrates_without_losing_mapping(tmp_path):
    path = tmp_path / 'old.db'
    graph = GraphStore(path)
    entity = graph.upsert_entity(ExtractedEntity(name='Existing', type='Organization', aliases=['Previous alias']))
    graph.close()
    conn = sqlite3.connect(path)
    conn.execute('ALTER TABLE aliases RENAME TO previous_aliases')
    conn.execute('CREATE TABLE aliases(norm_alias TEXT PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id))')
    conn.execute('INSERT INTO aliases SELECT norm_alias,entity_id FROM previous_aliases')
    conn.execute('DROP TABLE previous_aliases')
    conn.commit()
    conn.close()
    graph = GraphStore(path)
    try:
        assert ident(graph, 'Previous alias') == entity
        second = graph.upsert_entity(ExtractedEntity(name='New entity', type='Organization', aliases=['Previous alias']))
        assert second != entity
        assert {e['id'] for e in graph.search_entities('Previous alias', mode='phrase')} == {entity, second}
    finally:
        graph.close()


@pytest.mark.parametrize('remove_relation', [False, True])
def test_reanalysis_retains_merge_aliases_and_prior_relation_decisions(tmp_path, monkeypatch, remove_relation):
    monkeypatch.delenv('ONTOKB_LLM_PROVIDER', raising=False)
    pipeline = Pipeline(config={'interests': [], 'llm': {'provider': 'openai'}, 'paths': {
        'db': str(tmp_path / 'pipeline.db'), 'vault': str(tmp_path / 'vault'),
        'transcripts': str(tmp_path / 'transcripts')}})
    payload = {'summary': 'Original summary', 'key_points': [], 'topics': [], 'relevance': [],
        'entities': [dict(name=name, type=kind, aliases=[], properties=[])
                     for name, kind in [('NVIDIA', 'Organization'), ('英伟达', 'Organization'), ('Tool', 'SoftwareApplication')]],
        'triples': [dict(subject='NVIDIA', predicate='develops', object='Tool', confidence=0.8, evidence='Reviewed original quote')]}
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:
        SimpleNamespace(output_text=json.dumps(payload), status='completed')))
    item = ContentItem(id='article:merge', kind='article', source='other', url='', title='Merge source', raw_text='Source body')
    try:
        pipeline.ingest(item, client=client)
        graph, service = pipeline.graph, EditingService(pipeline.graph, pipeline.vault)
        triple_id = graph.conn.execute("SELECT id FROM triples WHERE predicate='develops'").fetchone()[0]
        if remove_relation:
            service.delete_triple(triple_id)
        else:
            service.update_triple(triple_id, {'predicate': 'adopts', 'confidence': 0.42})
        _, result = merge(service, graph)
        target = result['entity']['id']
        pipeline.ingest(item, client=client, replace_source=True)
        assert ident(graph, 'NVIDIA') == ident(graph, '英伟达') == target
        assert not graph.conn.execute("SELECT 1 FROM triples WHERE predicate='develops'").fetchone()
        corrected = graph.conn.execute("SELECT * FROM triples WHERE predicate='adopts'").fetchall()
        assert len(corrected) == (0 if remove_relation else 1)
        if corrected:
            assert corrected[0]['subject_id'] == target
            assert corrected[0]['evidence'] == 'Reviewed original quote'
            assert corrected[0]['confidence'] == 0.42
    finally:
        pipeline.graph.close()


def test_http_preview_commit_stale_token_and_undo(editor_http):
    request, graph, _ = editor_http
    source, target = ident(graph, 'OpenAI'), ident(graph, 'Anthropic')
    path = f'/api/editor/entities/{source}'
    before = state(graph)
    status, preview = request(path + '/merge-preview', {'target_id': target})
    assert status == 200 and preview['can_merge'] and state(graph) == before
    status, result = request(path + '/merge', {'target_id': target, 'preview_token': preview['preview_token']})
    assert status == 200 and result['ok']
    assert ident(graph, 'OpenAI') == target
    status, _ = request(path + '/merge', {'target_id': target, 'preview_token': preview['preview_token']})
    assert status in (400, 409)
    status, result = request(f"/api/editor/changes/{result['change_id']}/undo", {})
    assert status == 200 and result['ok']
    assert ident(graph, 'OpenAI') == source


def test_http_merge_guards_and_stale_preview(editor_http):
    from ontokb.assistant import _ingest_lock

    request, graph, port = editor_http
    source, target = ident(graph, 'OpenAI'), ident(graph, 'Anthropic')
    path = f'/api/editor/entities/{source}'
    status, preview = request(path + '/merge-preview', {'target_id': target})
    assert status == 200
    payload = {'target_id': target, 'preview_token': preview['preview_token']}
    for origin in ('https://example.org', 'http://localhost:1'):
        status, _ = request(path + '/merge', payload, origin=origin)
        assert status == 403
    status, _ = request(path + '/merge', payload, content_type='text/plain')
    assert status == 415
    with _ingest_lock:
        status, _ = request(path + '/merge', payload)
        assert status == 409
    status, _ = request(path, {'aliases': ['A new alias']}, origin=f'http://127.0.0.1:{port}')
    assert status == 200
    before = state(graph)
    status, _ = request(path + '/merge', payload)
    assert status == 409 and state(graph) == before


def test_chained_merges_preserve_all_names_and_can_be_undone_in_order(merge_editor):
    service, graph, vault = merge_editor
    third = graph.upsert_entity(ExtractedEntity(name='Canonical firm', type='Organization', aliases=['Final name']))
    vault.write_entity_note(graph, 'Canonical firm')
    before, files = records(graph, 'entities'), notes(vault)
    original = ident(graph, 'NVIDIA')
    key = remember(MemoryService(graph), original, note='Original judgment')
    _, first = merge(service, graph)
    survivor = first['entity']['id']
    preview = service.preview_merge(survivor, {'target_id': third})
    second = service.merge_entities(survivor, {'target_id': third, 'preview_token': preview['preview_token']})
    for name in ('NVIDIA', 'NVDA', '英伟达', '辉达', 'Final name'):
        assert ident(graph, name) == third
    archived = next(r for r in MemoryService(graph).records() if r['key'] == key)
    assert archived['snapshot']['target_id'] == original
    assert archived['associated_target_id'] == third
    service.undo(second['change_id'])
    assert ident(graph, 'NVIDIA') == survivor
    service.undo(first['change_id'])
    assert records(graph, 'entities') == before
    assert notes(vault) == files


def test_relation_personal_judgments_keep_distinct_quotes_after_duplicate_merge(merge_editor):
    service, graph, _ = merge_editor
    memory = MemoryService(graph)
    keys = []
    for record in memory.records():
        if record['snapshot']['kind'] == 'triple' and record['snapshot']['predicate'] == 'makes':
            memory.update(dict(key=record['key'], revision=record['revision'], reviewed=True,
                               included=True, stance='agree', note=record['snapshot']['title']))
            keys.append(record['key'])
    before = records(graph, 'personal_memory')
    merge(service, graph)
    assert records(graph, 'personal_memory') == before
    saved = {r['key']: r for r in memory.records()}
    assert len(keys) == 3
    assert {saved[k]['snapshot']['evidence'][0]['quote'] for k in keys} == {
        'First original quote', 'Second independent quote', '中文出处'}
    assert all(saved[k]['reviewed'] and saved[k]['stance'] == 'agree' for k in keys)
    assert all(saved[k].get('associated_target_id') for k in keys)


def test_merged_evidence_is_available_to_graph_queries_and_archived_ids_are_reserved(merge_editor):
    service, graph, _ = merge_editor
    for name in ('英伟达', 'NVIDIA'):
        graph.add_triple(ExtractedTriple(subject=name, predicate='makes', object='GPU', evidence=name),
                         graph.ontology, source='article:extra')
    original_max = graph.conn.execute('SELECT max(id) FROM triples').fetchone()[0]
    merge(service, graph)
    edges = graph.related_graph('英伟达', mode='phrase')['edges']
    duplicate = next(e for e in edges if e['predicate'] == 'makes' and e['source'] == 'article:en')
    assert {r['evidence'] for r in duplicate['evidence_records']} == {'First original quote', 'Second independent quote'}
    graph.add_triple(ExtractedTriple(subject='Someone', predicate='worksFor', object='英伟达'),
                     graph.ontology, source='article:new')
    assert graph.conn.execute('SELECT max(id) FROM triples').fetchone()[0] > original_max


def test_merge_leaves_unrelated_entity_note_annotations_intact(merge_editor):
    service, graph, vault = merge_editor
    unrelated = vault.root / 'Entities' / 'Document A.md'
    unrelated.write_text(unrelated.read_text(encoding='utf-8') + '\nPersonal annotation to preserve.\n', encoding='utf-8')
    original = unrelated.read_bytes()
    merge(service, graph)
    assert unrelated.read_bytes() == original


def test_confirmed_merge_preserves_former_name_when_third_entity_shares_it_as_alias(merge_editor):
    service, graph, _ = merge_editor
    third = graph.upsert_entity(ExtractedEntity(name='Different organization', type='Organization', aliases=['NVIDIA']))
    _, result = merge(service, graph)
    assert ident(graph, 'NVIDIA') == result['entity']['id']
    assert {e['id'] for e in graph.search_entities('NVIDIA', mode='phrase')} == {third, result['entity']['id']}
    graph.upsert_entity(ExtractedEntity(name='NVIDIA', type='Organization'), source='article:later')
    assert 'article:later' in json.loads(graph.get_entity('英伟达')['sources'])
