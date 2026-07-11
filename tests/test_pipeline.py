"""End-to-end ingest tests for the two-tier (document + knowledge) graph."""

from __future__ import annotations

import json
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
    assert doc["type"] == "Content"
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
    assert doc["type"] == "Content"
    assert json.loads(g.get_entity("OpenAI")["sources"]) == ["yt:old00000001"]
    edges = {(e["subject"], e["predicate"], e["object"])
             for e in g.related_graph("旧视频", mode="phrase")["edges"]}
    assert ("旧视频", "mentions", "OpenAI") in edges
    assert ("旧视频", "mentions", "harness agent") in edges

    # idempotent: second run adds nothing
    assert pipe.backfill_documents() == {"documents": 1, "links_added": 0}
