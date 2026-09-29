"""End-to-end ingest tests for the two-tier (document + knowledge) graph."""

from __future__ import annotations

import json
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from ontokb.models import ContentItem
from ontokb.pipeline import Pipeline


def _fake_openai_client(payload: dict):
    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(
                output_text=json.dumps(payload, ensure_ascii=False),
                status="completed",
            )

    return SimpleNamespace(responses=FakeResponses())


def test_source_replacement_preserves_other_sources_and_prunes_old_nodes(pipe):
    from ontokb.models import ExtractedEntity
    item=ContentItem(id='yt:replace0001',kind='video',source='youtube',url='https://youtu.be/replace0001',title='Replace test',raw_text='old body')
    pipe.ingest(item,client=_fake_openai_client(EXTRACTION))
    other=item.model_copy(update={'id':'yt:other000001','title':'Other video'})
    pipe.ingest(other,client=_fake_openai_client(EXTRACTION))
    pipe.graph.upsert_entity(ExtractedEntity(name='Old isolated claim',type='Claim'),source=item.id)
    pipe.vault.write_entity_note(pipe.graph,'Old isolated claim')
    payload=copy.deepcopy(EXTRACTION)
    payload.update(summary='New complete body analysis',key_points=['New evidence'],topics=[],triples=[])
    payload['entities']=[{'name':'New software','type':'SoftwareApplication','aliases':[],'properties':[]}]
    before_other=[dict(r) for r in pipe.graph.conn.execute('SELECT * FROM triples WHERE source=?',(other.id,))]
    item.raw_text='New complete source body'
    result=pipe.ingest(item,client=_fake_openai_client(payload),replace_source=True)
    assert result['verified'] and result['removed_relations']>0
    assert [dict(r) for r in pipe.graph.conn.execute('SELECT * FROM triples WHERE source=?',(other.id,))]==before_other
    assert pipe.graph.get_entity('Old isolated claim') is None
    assert not (pipe.vault.root/'Entities'/'Old isolated claim.md').exists()
    assert item.id not in json.loads(pipe.graph.get_entity('OpenAI')['sources'])
    assert (Path(result['backup'])/'knowledge.db').exists()
    assert 'New complete body analysis' in Path(result['note_path']).read_text(encoding='utf-8')


def test_failed_note_write_rolls_back_database_and_notes(pipe,monkeypatch):
    item=ContentItem(id='yt:rollback001',kind='video',source='youtube',url='https://youtu.be/rollback001',title='Rollback test',raw_text='old body')
    pipe.ingest(item,client=_fake_openai_client(EXTRACTION))
    before='\n'.join(pipe.graph.conn.iterdump())
    files={str(p.relative_to(pipe.vault.root)):p.read_bytes() for p in pipe.vault.root.rglob('*.md')}
    def fail(*a,**kw): raise OSError('Simulated disk error')
    monkeypatch.setattr(pipe.vault,'write_entity_note',fail)
    payload=copy.deepcopy(EXTRACTION);payload['summary']='Replacement that must roll back'
    with pytest.raises(OSError,match='disk error'):
        pipe.ingest(item.model_copy(update={'raw_text':'new body'}),client=_fake_openai_client(payload),replace_source=True)
    assert '\n'.join(pipe.graph.conn.iterdump())==before
    assert {str(p.relative_to(pipe.vault.root)):p.read_bytes() for p in pipe.vault.root.rglob('*.md')}==files


def test_agent_sync_restores_note_from_saved_snapshot(pipe,monkeypatch):
    from ontokb.knowledge_agent import KnowledgeTools
    item=ContentItem(id='article:sync',kind='article',source='other',url='',title='Sync test',raw_text='Article source body')
    stats=pipe.ingest(item,client=_fake_openai_client(EXTRACTION))
    note=Path(stats['note_path']);note.write_text('Outdated note',encoding='utf-8')
    monkeypatch.setattr('ontokb.knowledge_agent.load_config',lambda:pipe.config)
    host=KnowledgeTools(pipe.graph,item.id,{},lambda m:None)
    assert host.read('')['analysis_current']
    assert not host.read('')['note_matches_summary']
    result=host.call('kb_sync_note',{'target':''})
    assert result['verified'] and result['changed']
    assert EXTRACTION['summary'] in note.read_text(encoding='utf-8')
    assert host.call('kb_sync_note',{'target':''})==result
    assert len(host.operations)==1
    with pytest.raises(ValueError): host.call('shell',{'command':'ignored'})


def test_agent_read_does_not_write_or_accept_paths(pipe,monkeypatch):
    from ontokb.knowledge_agent import KnowledgeTools
    monkeypatch.setattr('ontokb.knowledge_agent.load_config',lambda:pipe.config)
    host=KnowledgeTools(pipe.graph,'',{},lambda m:None)
    before='\n'.join(pipe.graph.conn.iterdump())
    with pytest.raises(ValueError): host.call('kb_read_document',{'target':'../../private.txt'})
    assert host.operations[-1]['status']=='failed'
    assert '\n'.join(pipe.graph.conn.iterdump())==before


@pytest.fixture()
def pipe(tmp_path, monkeypatch):
    monkeypatch.delenv("ONTOKB_LLM_PROVIDER", raising=False)
    config = {
        "interests": ["AI agents"],
        "llm": {"provider": "openai"},
        "paths": {
            "db": str(tmp_path / "kb.db"),
            "vault": str(tmp_path / "vault"),
            "transcripts": str(tmp_path / "transcripts"),
        },
    }
    p = Pipeline(config=config)
    yield p
    p.graph.close()


EXTRACTION = {
    "summary": "总结",
    "key_points": ["要点"],
    "topics": ["AI agents"],
    "relevance": [{"interest": "AI agents", "score": 0.8}],
    "entities": [
        {"name": "OpenAI", "type": "Organization", "aliases": ["GPT母公司"], "properties": []},
        {"name": "harness agent", "type": "Technology", "aliases": [], "properties": []},
        {"name": "AI agents", "type": "Topic", "aliases": [], "properties": []},
    ],
    "triples": [
        {"subject": "OpenAI", "predicate": "develops", "object": "harness agent",
         "confidence": 0.9, "evidence": "OpenAI 开发了 harness agent"},
    ],
}


def test_ingest_builds_document_tier(pipe):
    item = ContentItem(
        id="yt:abc12345678", kind="video", source="youtube",
        url="https://www.youtube.com/watch?v=abc12345678",
        title="Agent 架构解析", raw_text="全文",
    )
    stats = pipe.ingest(item, client=_fake_openai_client(EXTRACTION))

    # knowledge tier
    assert stats["triples_accepted"] == 1
    # document tier: about(topic) + mentions(OpenAI, harness agent);
    # the Topic entity is only linked once, via about
    assert stats["document_links"] == 3

    doc = pipe.graph.get_entity("Agent 架构解析")
    assert doc["type"] == "VideoObject"
    props = json.loads(doc["properties"])
    assert props["url"] == item.url
    assert props["source"] == "youtube"
    assert props["kind"] == "video"
    assert props["added_time"]
    # the content id is an alias, so the doc node resolves from the item id too
    assert pipe.graph.get_entity("yt:abc12345678")["id"] == doc["id"]

    edges = {(e["subject"], e["predicate"], e["object"])
             for e in pipe.graph.related_graph("Agent 架构解析", mode="phrase")["edges"]}
    assert ("Agent 架构解析", "about", "AI agents") in edges
    assert ("Agent 架构解析", "mentions", "OpenAI") in edges
    assert ("Agent 架构解析", "mentions", "harness agent") in edges
    assert ("Agent 架构解析", "mentions", "AI agents") not in edges


def test_ingest_tags_entities_with_source(pipe):
    item = ContentItem(
        id="yt:abc12345678", kind="video", source="youtube",
        url="https://www.youtube.com/watch?v=abc12345678",
        title="Agent 架构解析", raw_text="全文",
    )
    pipe.ingest(item, client=_fake_openai_client(EXTRACTION))

    row = pipe.graph.get_entity("OpenAI")
    assert json.loads(row["sources"]) == ["yt:abc12345678"]
    assert row["added_time"]
    # entity resolution: the alias from this document resolves to the same node
    assert pipe.graph.get_entity("GPT母公司")["id"] == row["id"]


def test_reingest_and_second_source_merge(pipe):
    item1 = ContentItem(
        id="yt:abc12345678", kind="video", source="youtube",
        url="https://www.youtube.com/watch?v=abc12345678",
        title="Agent 架构解析", raw_text="全文",
    )
    pipe.ingest(item1, client=_fake_openai_client(EXTRACTION))

    # same entities arrive from a different medium -> merged, provenance kept
    item2 = ContentItem(
        id="ne:xyz", kind="article", source="netease",
        url="https://www.163.com/dy/article/xyz.html",
        title="深度解析 Agent 架构", raw_text="全文",
    )
    pipe.ingest(item2, client=_fake_openai_client(EXTRACTION))

    row = pipe.graph.get_entity("OpenAI")
    assert json.loads(row["sources"]) == ["yt:abc12345678", "ne:xyz"]

    # one entity node, two document nodes each with their own mentions edge
    docs = {pipe.graph.get_entity("yt:abc12345678")["id"],
            pipe.graph.get_entity("ne:xyz")["id"]}
    assert len(docs) == 2
    mentions = pipe.graph.conn.execute(
        "SELECT COUNT(*) n FROM triples t JOIN entities o ON o.id=t.object_id "
        "WHERE t.predicate='mentions' AND o.name='OpenAI'"
    ).fetchone()["n"]
    assert mentions == 2

    # re-ingesting the same item does not duplicate document links
    stats = pipe.ingest(item1, client=_fake_openai_client(EXTRACTION))
    assert stats["document_links"] == 0


def test_entity_note_lists_source_documents(pipe):
    item = ContentItem(
        id="yt:abc12345678", kind="video", source="youtube",
        url="https://www.youtube.com/watch?v=abc12345678",
        title="Agent 架构解析", raw_text="全文",
    )
    pipe.ingest(item, client=_fake_openai_client(EXTRACTION))

    note = (pipe.vault.root / "Entities" / "OpenAI.md").read_text(encoding="utf-8")
    assert "## Sources" in note
    assert "[[Agent 架构解析]]" in note
    assert "youtube" in note


def test_backfill_rebuilds_document_tier_for_old_data(pipe):
    from ontokb.models import ExtractedEntity, ExtractedTriple

    # simulate a pre-refactor database: entities + triples + content row,
    # but no document node, no mentions edges, no source tags
    g = pipe.graph
    g.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization"))
    g.upsert_entity(ExtractedEntity(name="harness agent", type="Technology"))
    g.add_triple(
        ExtractedTriple(subject="OpenAI", predicate="develops", object="harness agent"),
        pipe.ontology, source="yt:old00000001",
    )
    g.upsert_content("yt:old00000001", "video", "youtube",
                     "https://www.youtube.com/watch?v=old00000001",
                     "旧视频", status="processed")

    stats = pipe.backfill_documents()
    assert stats == {"documents": 1, "links_added": 2}

    doc = g.get_entity("yt:old00000001")
    assert doc["type"] == "VideoObject"
    assert json.loads(g.get_entity("OpenAI")["sources"]) == ["yt:old00000001"]
    edges = {(e["subject"], e["predicate"], e["object"])
             for e in g.related_graph("旧视频", mode="phrase")["edges"]}
    assert ("旧视频", "mentions", "OpenAI") in edges
    assert ("旧视频", "mentions", "harness agent") in edges

    # idempotent: second run adds nothing
    assert pipe.backfill_documents() == {"documents": 1, "links_added": 0}


def test_about_reuses_real_entity_instead_of_retyping_as_topic(pipe):
    payload = {**EXTRACTION, "topics": ["OpenAI"]}
    item = ContentItem(id="yt:about", kind="video", source="youtube", url="https://example.org/video",
                       title="Company analysis", raw_text="text")
    pipe.ingest(item, client=_fake_openai_client(payload))
    assert pipe.graph.get_entity("OpenAI")["type"] == "Organization"
    edges = pipe.graph.related_graph("Company analysis", mode="phrase")["edges"]
    assert any(e["predicate"] == "about" and e["object"] == "OpenAI" for e in edges)


def test_conflicting_extraction_cannot_add_edges_to_rejected_identity(pipe):
    from ontokb.models import ExtractedEntity
    pipe.graph.upsert_entity(ExtractedEntity(name="OpenAI", type="Person"))
    item = ContentItem(id="yt:conflict", kind="video", source="youtube", url="https://example.org/video",
                       title="Conflict case", raw_text="text")
    result = pipe.ingest(item, client=_fake_openai_client(EXTRACTION))
    assert result["rejected"] == 2  # identity and its triple
    assert pipe.graph.get_entity("OpenAI")["type"] == "Person"
    assert not pipe.graph.related_graph("OpenAI", mode="phrase")["edges"]
    meta = json.loads(pipe.graph.conn.execute("SELECT meta FROM contents WHERE id=?", (item.id,)).fetchone()[0])
    assert len(meta["extraction_rejections"]) == 2
    note = (pipe.vault.root / "Sources/Conflict case.md").read_text(encoding="utf-8")
    assert "**develops**" not in note
