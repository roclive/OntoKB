import json
import sqlite3
from pathlib import Path

import pytest

from ontokb.graph import GraphStore
from ontokb.migration import export_jsonld, migrate_graph, migration_plan
from ontokb.models import ExtractedEntity, ExtractedTriple
from ontokb.ontology import Ontology, OntologyError


ROOT = Path(__file__).resolve().parents[1]


def test_profile_hierarchy_and_union_domains():
    onto = Ontology.load(ROOT / 'ontology/core.yaml')
    assert onto.is_subclass('VideoObject', 'CreativeWork')
    assert onto.is_subclass('SoftwareApplication', 'CreativeWork')
    assert not onto.is_subclass('SoftwareApplication', 'Product')
    onto.validate_triple('Claim', 'about', 'Organization')
    onto.validate_triple('Book', 'author', 'Organization')
    onto.validate_triple('Organization', 'develops', 'SoftwareApplication')
    with pytest.raises(OntologyError):
        onto.validate_triple('DefinedTerm', 'author', 'Person')
    with pytest.raises(OntologyError):
        onto.validate_triple('Organization', 'worksFor', 'Person')


def test_reject_cycles(tmp_path):
    p = tmp_path / 'bad.yaml'
    p.write_text('classes:\n  A: {parent: B}\n  B: {parent: A}\n')
    with pytest.raises(OntologyError, match='cycle'):
        Ontology.load(p)


def test_conflict_does_not_pollute_existing_entity_or_aliases():
    g = GraphStore()
    g.upsert_entity(ExtractedEntity(name='Example', type='Organization'))
    with pytest.raises(OntologyError, match='type conflict'):
        g.upsert_entity(ExtractedEntity(name='Example', type='Person', aliases=['bad alias']))
    assert g.get_entity('Example')['type'] == 'Organization'
    assert g.get_entity('bad alias') is None
    with pytest.raises(OntologyError, match='alias conflict'):
        g.upsert_entity(ExtractedEntity(name='Different', type='Organization', aliases=['Example']))
    assert g.get_entity('Different') is None
    g.close()


def test_batch_type_override_cannot_bypass_persisted_type():
    g = GraphStore()
    g.upsert_entity(ExtractedEntity(name='Alice', type='Person'))
    g.upsert_entity(ExtractedEntity(name='Concept', type='DefinedTerm'))
    with pytest.raises(OntologyError):
        g.add_triple(ExtractedTriple(subject='Alice', predicate='develops', object='Concept'),
                     g.ontology, entity_types={'Alice': 'Organization'})
    assert g.conn.execute('SELECT COUNT(*) FROM triples').fetchone()[0] == 0
    g.close()


def test_refinement_cannot_invalidate_existing_edges():
    g = GraphStore()
    g.upsert_entity(ExtractedEntity(name='Work', type='CreativeWork'))
    g.upsert_entity(ExtractedEntity(name='Alice', type='Person'))
    g.add_triple(ExtractedTriple(subject='Work', predicate='author', object='Alice'), g.ontology)
    g.upsert_entity(ExtractedEntity(name='Work', type='Book'))
    assert g.get_entity('Work')['type'] == 'Book'
    g.upsert_entity(ExtractedEntity(name='Work', type='CreativeWork'))
    assert g.get_entity('Work')['type'] == 'Book'
    g.upsert_entity(ExtractedEntity(name='Work', type='Thing'))
    assert g.get_entity('Work')['type'] == 'Book'
    assert 'reviewStatus' not in json.loads(g.get_entity('Work')['properties'])
    g.close()


def legacy_store(path):
    g = GraphStore(path)
    for eid, name, typ, props in [(1, 'Video', 'Content', {'kind': 'video'}),
                                  (2, 'Concept', 'Topic', {}), (3, 'Alice', 'Person', {}),
                                  (4, 'Org', 'Organization', {})]:
        g.conn.execute('INSERT INTO entities(id,name,norm_name,type,properties,sources,added_time) VALUES(?,?,?,?,?,?,?)',
                       (eid, name, name.lower(), typ, json.dumps(props), '["yt:one"]', 'original-date'))
    g.conn.execute("INSERT INTO triples(id,subject_id,predicate,object_id,source,evidence,confidence,created_at) "
                   "VALUES(1,3,'worksAt',4,'yt:one','source quote',0.7,'original-date')")
    g.conn.execute("INSERT INTO triples(id,subject_id,predicate,object_id,source) VALUES(2,1,'about',2,'yt:one')")
    g.conn.commit()
    return g


def test_migration_backup_preservation_and_idempotence(tmp_path):
    g = legacy_store(tmp_path / 'kb.db')
    preview = migrate_graph(g, g.ontology, tmp_path / 'backup')
    assert not preview['applied']
    assert g.get_entity('Video')['type'] == 'Content'
    before = dict(g.conn.execute('SELECT * FROM triples WHERE id=1').fetchone())
    result = migrate_graph(g, g.ontology, tmp_path / 'backup', apply=True)
    assert result['applied']
    with sqlite3.connect(result['backup']) as backup:
        assert backup.execute('SELECT type FROM entities WHERE id=1').fetchone()[0] == 'Content'
        assert backup.execute('SELECT predicate FROM triples WHERE id=1').fetchone()[0] == 'worksAt'
    after = dict(g.conn.execute('SELECT * FROM triples WHERE id=1').fetchone())
    assert after == {**before, 'predicate': 'worksFor'}
    assert g.get_entity('Video')['type'] == 'VideoObject'
    assert json.loads(g.get_entity('Concept')['sources']) == ['yt:one']
    assert g.get_entity('Concept')['added_time'] == 'original-date'
    assert not migration_plan(g, g.ontology)['errors']
    again = migrate_graph(g, g.ontology, tmp_path / 'backup', apply=True)
    assert again['already_current']
    assert len(list((tmp_path / 'backup').glob('*.db'))) == 1
    out = export_jsonld(g, g.ontology, tmp_path / 'kg.jsonld')
    data = json.loads(out.read_text(encoding='utf-8'))
    statement = next(n for n in data['@graph'] if n['@id'] == 'urn:ontokb:statement:1')
    assert statement['rdf:predicate']['@id'] == 'https://schema.org/worksFor'
    assert statement['kb:evidence'] == 'source quote'
    assert statement['kb:confidence'] == 0.7
    g.close()


def test_invalid_migration_rolls_back_without_backup(tmp_path):
    g = legacy_store(tmp_path / 'kb.db')
    g.conn.execute("UPDATE entities SET type='UnknownType' WHERE id=2")
    g.conn.commit()
    with pytest.raises(OntologyError, match='migration blocked'):
        migrate_graph(g, g.ontology, tmp_path / 'backup', apply=True)
    assert g.get_entity('Video')['type'] == 'Content'
    assert not (tmp_path / 'backup').exists()
    g.close()


def test_invalid_override_rolls_back(tmp_path):
    g = legacy_store(tmp_path / 'kb.db')
    override = {'entities': {'Video': {'from': 'Content', 'to': 'Organization', 'reason': 'bad'}}}
    with pytest.raises(OntologyError):
        migrate_graph(g, g.ontology, tmp_path / 'backup', override, apply=True)
    assert g.get_entity('Video')['type'] == 'Content'
    g.close()
