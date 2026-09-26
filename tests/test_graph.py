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


def test_related_graph_returns_harness_agent_relations(graph):
    content_id = "yt:VwL82lejnrw"
    ids = {}
    for entity in [
            ExtractedEntity(
                name="Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？",
                type="Content",
            ),
            ExtractedEntity(name="Codex", type="Product"),
            ExtractedEntity(name="Claude Code", type="Product"),
            ExtractedEntity(name="harness agent", type="Technology", aliases=["代理脚手架", "agent工具链"]),
            ExtractedEntity(name="AI agent 工具链", type="Topic", aliases=["harness agent 研究主题"]),
            ExtractedEntity(name="模型公司用agent工具链抢Palantir核心价值", type="Claim"),
            ExtractedEntity(name="Palantir的结果生意被token模式打破", type="Claim"),
        ]:
        ids[entity.name] = graph.upsert_entity(entity)
    graph.upsert_content(
        content_id,
        "video",
        "youtube",
        "https://www.youtube.com/watch?v=VwL82lejnrw",
        "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？",
        status="processed",
    )
    triples = [
        ("Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？", "about", "AI agent 工具链"),
        ("Codex", "uses", "harness agent"),
        ("Claude Code", "uses", "harness agent"),
        (
            "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？",
            "makesClaim",
            "模型公司用agent工具链抢Palantir核心价值",
        ),
        (
            "模型公司用agent工具链抢Palantir核心价值",
            "supports",
            "Palantir的结果生意被token模式打破",
        ),
    ]
    for subject, predicate, obj in triples:
        graph.conn.execute(
            "INSERT INTO triples (subject_id, predicate, object_id, source) VALUES (?,?,?,?)",
            (ids[subject], predicate, ids[obj], content_id),
        )
    graph.conn.commit()

    result = graph.related_graph("harness agent")

    assert [row["relation"] for row in result["relations"]] == [
        "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？ -- about -> AI agent 工具链",
        "Codex -- uses -> harness agent",
        "Claude Code -- uses -> harness agent",
        "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？ -- makesClaim -> 模型公司用agent工具链抢Palantir核心价值",
        "模型公司用agent工具链抢Palantir核心价值 -- supports -> Palantir的结果生意被token模式打破",
    ]
    assert {entity["name"] for entity in result["matched_entities"]} == {
        "AI agent 工具链",
        "harness agent",
        "模型公司用agent工具链抢Palantir核心价值",
    }
    assert result["sources"][0]["id"] == content_id

    expanded_phrase = graph.related_graph("harness agent", mode="phrase")
    assert [row["relation"] for row in expanded_phrase["relations"]] == [
        "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？ -- about -> AI agent 工具链",
        "Codex -- uses -> harness agent",
        "Claude Code -- uses -> harness agent",
        "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？ -- makesClaim -> 模型公司用agent工具链抢Palantir核心价值",
        "模型公司用agent工具链抢Palantir核心价值 -- supports -> Palantir的结果生意被token模式打破",
    ]

    strict_phrase = graph.related_graph("harness agent", mode="phrase", expand=False)
    assert [row["relation"] for row in strict_phrase["relations"]] == [
        "Palantir CEO破防怒骂OpenAI和Anthropic，他真正怕的是什么？ -- about -> AI agent 工具链",
        "Codex -- uses -> harness agent",
        "Claude Code -- uses -> harness agent",
    ]


def test_search_expands_simplified_traditional_variants(graph):
    person_id = graph.upsert_entity(
        ExtractedEntity(name="達里奧・阿莫迪", type="Person", aliases=["Dario Amodei", "達里奧"])
    )
    org_id = graph.upsert_entity(ExtractedEntity(name="Anthropic", type="Organization"))
    graph.conn.execute(
        "INSERT INTO triples (subject_id, predicate, object_id, source) VALUES (?,?,?,?)",
        (person_id, "worksAt", org_id, "test"),
    )
    graph.conn.commit()

    result = graph.related_graph("达里奥", mode="phrase")

    assert [entity["name"] for entity in result["matched_entities"]] == ["達里奧・阿莫迪"]
    assert result["relations"] == [
        {
            "triple_id": 1,
            "relation": "達里奧・阿莫迪 -- worksAt -> Anthropic",
        }
    ]


def test_source_tagging_accumulates_across_documents(graph):
    graph.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization"),
                        source="yt:one", added_time="2026-07-11T00:00:00+00:00")
    graph.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization", aliases=["GPT母公司"]),
                        source="wx:two", added_time="2026-07-12T00:00:00+00:00")
    graph.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization"),
                        source="wx:two")  # duplicate source is not repeated

    row = graph.get_entity("OpenAI")
    import json as _json
    assert _json.loads(row["sources"]) == ["yt:one", "wx:two"]
    assert row["added_time"] == "2026-07-11T00:00:00+00:00"  # first sighting wins
    # alias from the second document resolves to the same node (entity resolution)
    assert graph.get_entity("GPT母公司")["id"] == row["id"]


def test_triple_created_at_persisted(graph, onto):
    _seed(graph)
    t = ExtractedTriple(subject="OpenAI", predicate="develops", object="GPT-5.5")
    assert graph.add_triple(t, onto, source="yt:one", created_at="2026-07-11T00:00:00+00:00")
    edge = graph.related_graph("OpenAI")["edges"][0]
    assert edge["created_at"] == "2026-07-11T00:00:00+00:00"
    assert edge["source"] == "yt:one"


def test_migration_adds_provenance_columns(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, norm_name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL, aliases TEXT NOT NULL DEFAULT '[]',
            properties TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE aliases (norm_alias TEXT PRIMARY KEY, entity_id INTEGER NOT NULL);
        CREATE TABLE triples (
            id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, predicate TEXT NOT NULL,
            object_id INTEGER NOT NULL, confidence REAL NOT NULL DEFAULT 0.8,
            source TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '',
            UNIQUE(subject_id, predicate, object_id, source));
        CREATE TABLE contents (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'queued',
            meta TEXT NOT NULL DEFAULT '{}');
        INSERT INTO entities (name, norm_name, type) VALUES ('OpenAI', 'openai', 'Organization');
    """)
    conn.commit()
    conn.close()

    g = GraphStore(db)
    row = g.get_entity("OpenAI")
    assert row["sources"] == "[]" and row["added_time"] == ""
    g.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization"),
                    source="yt:one", added_time="2026-07-11T00:00:00+00:00")
    assert g.related_graph("OpenAI")["matched_entities"][0]["sources"] == ["yt:one"]
    g.close()
