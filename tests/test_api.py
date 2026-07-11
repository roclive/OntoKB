from ontokb.api import _chat_response, _relations_table
from ontokb.graph import GraphStore
from ontokb.models import ExtractedEntity


def test_relations_table_matches_expected_shape():
    text = _relations_table(
        [
            {
                "triple_id": 72,
                "relation": "Codex -- uses -> harness agent",
            }
        ]
    )

    assert text == "相关关系如下：\ntriple_id\t关系\n72\tCodex -- uses -> harness agent\n"


def test_chat_retrieves_graph_before_calling_answerer():
    graph = GraphStore(":memory:")
    codex = graph.upsert_entity(ExtractedEntity(name="Codex", type="Product"))
    harness = graph.upsert_entity(ExtractedEntity(name="harness agent", type="Technology"))
    graph.conn.execute(
        "INSERT INTO triples (subject_id, predicate, object_id) VALUES (?,?,?)",
        (codex, "uses", harness),
    )
    graph.conn.commit()
    seen = {}

    def answerer(question, context, **kwargs):
        seen["question"] = question
        seen["context"] = context
        return "Codex 使用 harness agent。"

    result = _chat_response(
        graph,
        "Codex使用什么？",
        answerer=answerer,
        mode="phrase",
        expand=True,
        top=1,
    )

    assert result["answer"] == "Codex 使用 harness agent。"
    assert seen["context"]["relations"][0]["relation"] == "Codex -- uses -> harness agent"
    assert seen["context"]["mode"] == "phrase"
    assert seen["context"]["expand"] is True
    assert seen["context"]["top"] == 1
    assert result["context"] is seen["context"]


def test_chat_strict_phrase_does_not_fall_back_to_embedded_entity():
    graph = GraphStore(":memory:")
    graph.upsert_entity(ExtractedEntity(name="Codex", type="Product"))
    seen = {}

    def answerer(question, context, **kwargs):
        seen.update(context)
        return "没有命中。"

    _chat_response(
        graph,
        "Codex使用什么？",
        answerer=answerer,
        mode="phrase",
        expand=False,
        top=5,
    )

    assert seen["matched_entities"] == []
    assert seen["top"] == 5
