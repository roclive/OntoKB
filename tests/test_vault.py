from pathlib import Path

import pytest

from ontokb.graph import GraphStore
from ontokb.models import ContentItem, ExtractedEntity, ExtractedTriple, ProcessedContent
from ontokb.ontology import Ontology
from ontokb.rules import Action
from ontokb.vault import ObsidianVault, slugify

ROOT = Path(__file__).resolve().parents[1]


def test_slugify_strips_illegal_chars():
    assert slugify('a/b:c*d?"e<f>g|h#i[j]') == "abcdefghij"
    assert slugify("  ") == "untitled"


def test_content_and_entity_notes(tmp_path):
    vault = ObsidianVault(tmp_path)
    graph = GraphStore(":memory:")
    onto = Ontology.load(ROOT / "ontology" / "core.yaml")

    graph.upsert_entity(ExtractedEntity(name="DeepSeek", type="Organization"))
    graph.upsert_entity(ExtractedEntity(name="MoE", type="Technology"))
    graph.add_triple(ExtractedTriple(subject="DeepSeek", predicate="develops", object="MoE"),
                     onto, source="yt:1")

    item = ContentItem(id="yt:1", kind="video", source="youtube",
                       url="https://youtu.be/x", title="DeepSeek 解析")
    processed = ProcessedContent(
        content_id="yt:1", summary="总结", key_points=["要点一"],
        topics=["端侧 AI"], relevance={"芯片": 0.4},
        triples=[ExtractedTriple(subject="DeepSeek", predicate="develops", object="MoE")],
    )
    note = vault.write_content_note(item, processed)
    text = note.read_text(encoding="utf-8")
    assert "[[端侧 AI]]" in text and "**develops**" in text

    entity_note = vault.write_entity_note(graph, "DeepSeek")
    assert "[[MoE]]" in entity_note.read_text(encoding="utf-8")


def test_apply_actions(tmp_path):
    vault = ObsidianVault(tmp_path)
    graph = GraphStore(":memory:")
    wiki = vault.apply_action(graph, Action("create_wiki_page", {"entity": "AI agents"}, "r1"))
    assert wiki.exists() and "AI agents" in wiki.read_text(encoding="utf-8")

    q1 = vault.apply_action(graph, Action("queue_report", {"topic": "AI agents"}, "r2"))
    q2 = vault.apply_action(graph, Action("queue_report", {"topic": "AI agents"}, "r2"))
    # idempotent append
    assert q1 == q2
    assert q1.read_text(encoding="utf-8").count("AI agents") == 1
