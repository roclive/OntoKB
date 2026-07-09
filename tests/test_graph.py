from pathlib import Path

import pytest

from ontokb.graph import GraphStore
from ontokb.models import ExtractedEntity, ExtractedTriple
from ontokb.ontology import Ontology

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def onto():
    return Ontology.load(ROOT / "ontology" / "core.yaml")


@pytest.fixture()
def graph():
    g = GraphStore(":memory:")
    yield g
    g.close()


def _seed(graph):
    graph.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization", aliases=["open ai"]))
    graph.upsert_entity(ExtractedEntity(name="GPT-5.5", type="Technology"))
    graph.upsert_entity(ExtractedEntity(name="Anthropic", type="Organization"))


def test_alias_merging(graph):
    _seed(graph)
    graph.upsert_entity(ExtractedEntity(name="Open AI", type="Organization"))  # norm merge
    assert graph.get_entity("open ai")["name"] == "OpenAI"
    # merging did not create a new row
    n = graph.conn.execute("SELECT COUNT(*) n FROM entities").fetchone()["n"]
    assert n == 3


def test_triple_validation_and_dedup(graph, onto):
    _seed(graph)
    t = ExtractedTriple(subject="OpenAI", predicate="develops", object="GPT-5.5")
    assert graph.add_triple(t, onto, source="test") is True
    assert graph.add_triple(t, onto, source="test") is False  # duplicate
    eid = graph.get_entity("OpenAI")["id"]
    assert graph.degree(eid) == 1


def test_triple_rejects_domain_violation(graph, onto):
    _seed(graph)
    graph.upsert_entity(ExtractedEntity(name="Sam", type="Person"))
    bad = ExtractedTriple(subject="Sam", predicate="develops", object="GPT-5.5")
    with pytest.raises(Exception):
        graph.add_triple(bad, onto)


def test_facts_projection(graph, onto):
    _seed(graph)
    graph.add_triple(
        ExtractedTriple(subject="OpenAI", predicate="competesWith", object="Anthropic"),
        onto, source="test",
    )
    graph.upsert_content("yt:abc", "video", "youtube", "https://x", "t",
                         status="processed", meta={"relevance": {"AI agents": 0.9}})
    facts = list(graph.facts())
    kinds = {f["kind"] for f in facts}
    assert kinds == {"entity", "triple", "content"}
    content = next(f for f in facts if f["kind"] == "content")
    assert content["relevance"] == 0.9
    assert content["top_topic"] == "AI agents"
