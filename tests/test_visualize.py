from ontokb.graph import GraphStore
from ontokb.models import ExtractedEntity
from ontokb.visualize import export_html, graph_data, render_html


def _store() -> GraphStore:
    g = GraphStore(":memory:")
    a = g.upsert_entity(ExtractedEntity(name="Anthropic", type="Organization"))
    b = g.upsert_entity(ExtractedEntity(name="Claude</script>", type="Product"))
    g.conn.execute(
        "INSERT INTO triples (subject_id, predicate, object_id, source) VALUES (?,?,?,?)",
        (a, "makes", b, "test"),
    )
    g.conn.commit()
    return g


def test_graph_data_projects_nodes_and_edges():
    data = graph_data(_store())
    assert {n["id"] for n in data["nodes"]} == {"Anthropic", "Claude</script>"}
    assert data["edges"] == [{"s": "Anthropic", "p": "makes", "t": "Claude</script>"}]


def test_graph_data_dedupes_multi_source_triples():
    g = _store()
    a = g.get_entity("Anthropic")["id"]
    b = g.get_entity("Claude</script>")["id"]
    g.conn.execute(
        "INSERT INTO triples (subject_id, predicate, object_id, source) VALUES (?,?,?,?)",
        (a, "makes", b, "another-source"),
    )
    g.conn.commit()
    assert len(graph_data(g)["edges"]) == 1


def test_render_html_embeds_data_and_escapes_script_close():
    html = render_html(graph_data(_store()))
    assert "Anthropic" in html
    assert "Claude</script>" not in html  # must be <-escaped
    assert "Claude\\u003c/script>" in html


def test_export_html_writes_file(tmp_path):
    out = export_html(_store(), tmp_path / "sub" / "graph.html")
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
