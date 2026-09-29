"""Editing invariants exercised only against disposable databases and vaults."""

import copy
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ontokb.editing import EditingConflict, EditingError, EditingService
from ontokb.graph import GraphStore
from ontokb.models import ContentItem, ExtractedEntity, ExtractedTriple
from ontokb.pipeline import Pipeline
from ontokb.vault import ObsidianVault


@pytest.fixture()
def editor(tmp_path):
    graph = GraphStore(tmp_path / "editing.db")
    for name, kind, aliases in [
        ("OpenAI", "Organization", ["Open AI"]),
        ("Anthropic", "Organization", ["Claude company"]),
        ("Tool", "SoftwareApplication", []),
        ("Other tool", "SoftwareApplication", []),
        ("Sam", "Person", []),
        ("A source claim", "Claim", []),
    ]:
        graph.upsert_entity(ExtractedEntity(name=name, type=kind, aliases=aliases), source="article:one")
    graph.add_triple(ExtractedTriple(subject="OpenAI", predicate="develops", object="Tool",
                                    confidence=0.8, evidence="Original quoted evidence."),
                     graph.ontology, source="article:one", created_at="2026-09-01T00:00:00Z")
    vault = ObsidianVault(tmp_path / "vault")
    for row in graph.conn.execute("SELECT name FROM entities"):
        vault.write_entity_note(graph, row["name"])
    yield EditingService(graph, vault), graph, vault
    graph.close()


def _entity(graph, name):
    return graph.get_entity(name)["id"]


def _edge(graph):
    return dict(graph.conn.execute("SELECT * FROM triples ORDER BY id LIMIT 1").fetchone())


def _state(graph):
    return "\n".join(graph.conn.iterdump())


def _notes(vault):
    return {str(p.relative_to(vault.root)): p.read_bytes() for p in vault.root.rglob("*.md")}


def test_rename_keeps_identity_alias_resolution_and_updates_neighbor_notes(editor):
    service, graph, vault = editor
    entity_id = _entity(graph, "OpenAI")
    service.update_entity(entity_id, {"name": "OpenAI Research", "aliases": ["Open AI", "研究公司"]})
    assert _entity(graph, "OpenAI Research") == entity_id
    assert _entity(graph, "OpenAI") == entity_id
    assert _entity(graph, "研究公司") == entity_id
    assert _edge(graph)["subject_id"] == entity_id
    assert not (vault.root / "Entities/OpenAI.md").exists()
    assert (vault.root / "Entities/OpenAI Research.md").exists()
    assert "[[OpenAI Research]]" in (vault.root / "Entities/Tool.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", [
    {"name": "Anthropic"}, {"aliases": ["Claude company"]}, {"name": "  "},
    {"type": "UnknownType"}, {"type": "Person"},
])
def test_invalid_entity_edit_is_atomic(editor, payload):
    service, graph, vault = editor
    before, notes = _state(graph), _notes(vault)
    with pytest.raises(EditingError):
        service.update_entity(_entity(graph, "OpenAI"), payload)
    assert _state(graph) == before
    assert _notes(vault) == notes


@pytest.mark.parametrize("payload", [
    {"subject_id": 999999}, {"predicate": "notARelation"},
    {"predicate": "worksFor"}, {"confidence": -0.1}, {"confidence": 1.1},
])
def test_invalid_relation_edit_is_atomic(editor, payload):
    service, graph, vault = editor
    before, notes = _state(graph), _notes(vault)
    with pytest.raises(EditingError):
        service.update_triple(_edge(graph)["id"], payload)
    assert _state(graph) == before
    assert _notes(vault) == notes


def test_endpoint_and_predicate_edit_keeps_original_evidence_and_provenance(editor):
    service, graph, vault = editor
    original = _edge(graph)
    service.update_triple(original["id"], {"subject_id": _entity(graph, "Anthropic"),
        "object_id": _entity(graph, "Other tool"), "predicate": "adopts", "confidence": 0.95})
    updated = _edge(graph)
    assert updated["subject_id"] == _entity(graph, "Anthropic")
    assert updated["object_id"] == _entity(graph, "Other tool")
    assert updated["predicate"] == "adopts"
    assert updated["confidence"] == 0.95
    for key in ("id", "source", "evidence", "created_at"):
        assert updated[key] == original[key]
    assert "**develops**" not in (vault.root / "Entities/OpenAI.md").read_text(encoding="utf-8")
    assert "**adopts**" in (vault.root / "Entities/Anthropic.md").read_text(encoding="utf-8")


def test_claim_correction_and_verdict_survive_new_extraction(editor):
    service, graph, _ = editor
    claim_id = _entity(graph, "A source claim")
    service.update_entity(claim_id, {"name": "Corrected source claim", "verificationStatus": "disputed"})
    graph.upsert_entity(ExtractedEntity(name="A source claim", type="Claim",
                                       properties={"verificationStatus": "unverified"}), source="article:two")
    claim = graph.get_entity("Corrected source claim")
    props = json.loads(claim["properties"])
    assert props["text"] == "Corrected source claim"
    assert props["verificationStatus"] == "disputed"
    assert json.loads(claim["sources"]) == ["article:one", "article:two"]


def test_undo_rejects_nonlatest_change_and_keeps_new_sources(editor):
    service, graph, _ = editor
    first = service.update_entity(_entity(graph, "OpenAI"), {"name": "OpenAI Research"})
    second = service.update_triple(_edge(graph)["id"], {"confidence": 0.95})
    before = _state(graph)
    with pytest.raises(EditingConflict):
        service.undo(first["change_id"])
    assert _state(graph) == before
    service.undo(second["change_id"])
    assert _edge(graph)["confidence"] == 0.8
    graph.upsert_entity(ExtractedEntity(name="OpenAI", type="Organization"), source="article:two")
    service.undo(first["change_id"])
    assert graph.get_entity("OpenAI")["name"] == "OpenAI"
    assert "article:two" in json.loads(graph.get_entity("OpenAI")["sources"])


def test_relation_deletion_can_be_undone_without_losing_evidence(editor):
    service, graph, _ = editor
    original = _edge(graph)
    result = service.delete_triple(original["id"])
    assert graph.conn.execute("SELECT count(*) FROM triples").fetchone()[0] == 0
    service.undo(result["change_id"])
    assert _edge(graph) == original


def test_edit_cannot_duplicate_existing_relation(editor):
    service, graph, vault = editor
    graph.add_triple(ExtractedTriple(subject="OpenAI", predicate="adopts", object="Tool"),
                     graph.ontology, source="article:one")
    before, notes = _state(graph), _notes(vault)
    with pytest.raises(EditingConflict):
        service.update_triple(_edge(graph)["id"], {"predicate": "adopts"})
    assert _state(graph) == before
    assert _notes(vault) == notes


def test_deleted_relation_id_is_not_reused_and_undo_keeps_new_relation(editor):
    service, graph, _ = editor
    original = _edge(graph)
    change = service.delete_triple(original["id"])
    graph.add_triple(ExtractedTriple(subject="Anthropic", predicate="adopts", object="Other tool"),
                     graph.ontology, source="article:two")
    new_relation = _edge(graph)
    assert new_relation["id"] != original["id"]
    service.undo(change["change_id"])
    rows = {r["id"]: dict(r) for r in graph.conn.execute("SELECT * FROM triples")}
    assert rows == {original["id"]: original, new_relation["id"]: new_relation}


def test_sync_keeps_source_summary_annotations_and_extraction_snapshot(editor):
    service, graph, vault = editor
    snapshot = {"entities": [{"name": "OpenAI"}], "triples": [{"evidence": "Raw evidence"}]}
    graph.upsert_content("article:one", "article", "other", "", "Source", status="processed",
                         meta={"processed_snapshot": snapshot})
    note = vault.root / "Sources/Source.md"
    note.write_text("# Source\n\n## Summary\nOriginal summary\n\n## Extracted knowledge\n"
                    "- [[OpenAI]] **develops** [[Tool]]\n\n## My notes\nKeep my annotation.\n", encoding="utf-8")
    service.update_entity(_entity(graph, "OpenAI"), {"name": "Corrected company"})
    text = note.read_text(encoding="utf-8")
    assert "Original summary" in text and "Keep my annotation." in text
    assert "[[Corrected company]] **develops** [[Tool]]" in text
    meta = json.loads(graph.conn.execute("SELECT meta FROM contents WHERE id='article:one'").fetchone()[0])
    assert meta["processed_snapshot"] == snapshot


def test_reading_summary_resolves_renamed_entity_through_hidden_original_name(editor):
    from ontokb.reading import reading_library

    service, graph, _ = editor
    summary = "OpenAI announced its latest research."
    graph.upsert_content("article:one", "article", "other", "", "Source", status="processed",
                         meta={"summary": summary})
    entity_id = _entity(graph, "OpenAI")
    service.update_entity(entity_id, {"name": "Corrected company", "aliases": []})
    current = graph.get_entity("Corrected company")
    assert json.loads(current["aliases"]) == []
    assert graph.conn.execute("SELECT entity_id FROM aliases WHERE norm_alias='openai'").fetchone()[0] == entity_id
    library = reading_library(graph)
    assert library[0]["summary"] == summary
    step = library[0]["steps"][0]
    assert step["entities"] == ["Corrected company"]
    assert step["edges"][0]["s"] == "Corrected company"
    assert step["edges"][0]["evidence"] == "Original quoted evidence."


def test_note_write_failure_rolls_back_edit_and_audit(editor, monkeypatch):
    service, graph, vault = editor
    before, notes = _state(graph), _notes(vault)

    def fail(*args, **kwargs):
        raise OSError("Simulated disk failure")

    monkeypatch.setattr(vault, "write_entity_note", fail)
    with pytest.raises(OSError, match="disk failure"):
        service.update_entity(_entity(graph, "OpenAI"), {"name": "Renamed"})
    assert _state(graph) == before
    assert _notes(vault) == notes


def _client(payload):
    return SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:
        SimpleNamespace(output_text=json.dumps(payload), status="completed")))


@pytest.mark.parametrize("remove_relation", [False, True])
def test_reanalysis_preserves_manual_corrections_and_relation_decisions(tmp_path, monkeypatch, remove_relation):
    monkeypatch.delenv("ONTOKB_LLM_PROVIDER", raising=False)
    pipeline = Pipeline(config={"interests": [], "llm": {"provider": "openai"}, "paths": {
        "db": str(tmp_path / "kb.db"), "vault": str(tmp_path / "vault"),
        "transcripts": str(tmp_path / "transcripts")}})
    payload = {"summary": "Source summary", "key_points": [], "topics": [], "relevance": [],
        "entities": [{"name": "OpenAI", "type": "Organization", "aliases": [], "properties": []},
                     {"name": "Tool", "type": "SoftwareApplication", "aliases": [], "properties": []}],
        "triples": [{"subject": "OpenAI", "predicate": "develops", "object": "Tool",
                     "confidence": 0.8, "evidence": "Original evidence"}]}
    item = ContentItem(id="article:one", kind="article", source="other", url="", title="Source", raw_text="Body")
    try:
        pipeline.ingest(item, client=_client(payload))
        service = EditingService(pipeline.graph, pipeline.vault)
        entity_id = _entity(pipeline.graph, "OpenAI")
        service.update_entity(entity_id, {"name": "Corrected company"})
        relation = dict(pipeline.graph.conn.execute("SELECT * FROM triples WHERE predicate='develops'").fetchone())
        if remove_relation:
            service.delete_triple(relation["id"])
        else:
            service.update_triple(relation["id"], {"predicate": "adopts", "confidence": 0.5})
        revised = copy.deepcopy(payload)
        revised["summary"] = "Updated summary"
        pipeline.ingest(item, client=_client(revised), replace_source=True)
        assert _entity(pipeline.graph, "Corrected company") == entity_id
        assert pipeline.graph.get_entity("OpenAI")["name"] == "Corrected company"
        assert pipeline.graph.conn.execute("SELECT count(*) FROM triples WHERE predicate='develops'").fetchone()[0] == 0
        corrected = pipeline.graph.conn.execute("SELECT * FROM triples WHERE predicate='adopts'").fetchall()
        assert len(corrected) == (0 if remove_relation else 1)
        if corrected:
            assert corrected[0]["evidence"] == "Original evidence"
            assert corrected[0]["confidence"] == 0.5
        source_note = (pipeline.vault.root / "Sources/Source.md").read_text(encoding="utf-8")
        assert "**develops**" not in source_note
        if not remove_relation:
            assert "[[Corrected company]] **adopts** [[Tool]]" in source_note
    finally:
        pipeline.graph.close()


@pytest.mark.parametrize("undo_count,expected", [
    (0, set()), (1, {"makes"}), (2, {"adopts", "makes"}), (3, {"develops", "adopts", "makes"}),
])
def test_repeated_relation_edits_suppress_every_prior_signature_and_undo_restores_scope(
        tmp_path, monkeypatch, undo_count, expected):
    monkeypatch.delenv("ONTOKB_LLM_PROVIDER", raising=False)
    pipeline = Pipeline(config={"interests": [], "llm": {"provider": "openai"}, "paths": {
        "db": str(tmp_path / "kb.db"), "vault": str(tmp_path / "vault"),
        "transcripts": str(tmp_path / "transcripts")}})
    original = {"subject": "OpenAI", "predicate": "develops", "object": "Tool",
                "confidence": 0.8, "evidence": "Original evidence"}
    payload = {"summary": "Source summary", "key_points": [], "topics": [], "relevance": [],
        "entities": [{"name": "OpenAI", "type": "Organization", "aliases": [], "properties": []},
                     {"name": "Tool", "type": "SoftwareApplication", "aliases": [], "properties": []}],
        "triples": [original]}
    item = ContentItem(id="article:chain", kind="article", source="other", url="", title="Source", raw_text="Body")
    try:
        pipeline.ingest(item, client=_client(payload))
        service = EditingService(pipeline.graph, pipeline.vault)
        relation_id = pipeline.graph.conn.execute("SELECT id FROM triples WHERE predicate='develops'").fetchone()[0]
        changes = [service.update_triple(relation_id, {"predicate": "adopts"}),
                   service.update_triple(relation_id, {"predicate": "makes"}),
                   service.delete_triple(relation_id)]
        for change in list(reversed(changes))[:undo_count]:
            service.undo(change["change_id"])
        revised = copy.deepcopy(payload)
        revised["triples"] = [original | {"predicate": p, "evidence": "New extraction evidence"}
                              for p in ("develops", "adopts", "makes")]
        pipeline.ingest(item, client=_client(revised), replace_source=True)
        rows = list(pipeline.graph.conn.execute(
            "SELECT * FROM triples WHERE predicate IN ('develops','adopts','makes')"))
        assert {r["predicate"] for r in rows} == expected
        assert len(rows) == len(expected)
        if undo_count in (1, 2):
            protected = next(r for r in rows if r["id"] == relation_id)
            assert protected["evidence"] == "Original evidence"
        source_note = (pipeline.vault.root / "Sources/Source.md").read_text(encoding="utf-8")
        for predicate in ("develops", "adopts", "makes"):
            assert (f"**{predicate}**" in source_note) == (predicate in expected)
    finally:
        pipeline.graph.close()


@pytest.fixture()
def editor_http(editor):
    from ontokb.api import GraphApiHandler

    _, graph, vault = editor
    database = graph.conn.execute("PRAGMA database_list").fetchone()[2]

    class Handler(GraphApiHandler):
        editor_vault_path = vault.root

        def setup(self):
            super().setup()
            self.store = GraphStore(database)

        def finish(self):
            try:
                super().finish()
            finally:
                self.store.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(path, payload=None, origin=None, content_type="application/json"):
        headers = {"Content-Type": content_type}
        if origin is not None:
            headers["Origin"] = origin
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(f"http://127.0.0.1:{server.server_port}{path}", data=data, headers=headers)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    yield request, graph, server.server_port
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


def test_http_bootstrap_edit_stale_revision_and_immutable_evidence(editor_http):
    request, graph, port = editor_http
    status, snapshot = request("/api/editor")
    assert status == 200
    entity_id = _entity(graph, "OpenAI")
    entity = next(e for e in snapshot["entities"] if e["id"] == entity_id)
    path = f"/api/editor/entities/{entity_id}"
    status, result = request(path, {"name": "Renamed company", "revision": entity["revision"]},
                             origin=f"http://127.0.0.1:{port}")
    assert status == 200 and result["ok"]
    status, _ = request(path, {"name": "Stale overwrite", "revision": entity["revision"]})
    assert status == 409
    assert graph.get_entity("OpenAI")["name"] == "Renamed company"
    triple = _edge(graph)
    for field in ("evidence", "source"):
        status, _ = request(f"/api/editor/triples/{triple['id']}", {field: "Edited raw source"})
        assert status == 400
        assert _edge(graph) == triple
    status, _ = request(path, {"aliases": ["Claude company"]})
    assert status == 400


def test_http_delete_undo_and_mutation_guards(editor_http):
    from ontokb.assistant import _ingest_lock

    request, graph, _ = editor_http
    triple = _edge(graph)
    path = f"/api/editor/triples/{triple['id']}/delete"
    for origin in ("https://example.org", "http://localhost:1"):
        status, _ = request(path, {}, origin=origin)
        assert status == 403
    status, _ = request(path, {}, content_type="text/plain")
    assert status == 415
    with _ingest_lock:
        status, _ = request(path, {})
        assert status == 409
    assert _edge(graph) == triple
    status, result = request(path, {})
    assert status == 200 and result["ok"]
    assert graph.conn.execute("SELECT count(*) FROM triples").fetchone()[0] == 0
    status, result = request(f"/api/editor/changes/{result['change_id']}/undo", {})
    assert status == 200 and result["ok"]
    assert _edge(graph) == triple


def test_editor_source_categories_match_reading_library(editor):
    from ontokb.reading import reading_library

    service, graph, _ = editor
    for ident, title, meta in [
        ('article:one', 'AI investment', {}),
        ('article:two', 'History', {'categories': ['专题', ' 历史类 ', '专题']}),
        ('article:three', 'Notes', {}),
    ]:
        graph.upsert_content(ident, 'article', 'other', '', title, 'processed', meta)
    sources = service.bootstrap()['sources']
    library = reading_library(graph)
    assert {s['id']: s['categories'] for s in sources} == {
        d['id']: d['categories'] for d in library
    }
    assert sources[0]['categories'] == ['未分类']
    assert sources[1]['categories'] == ['专题', '历史类']
    assert sources[2]['categories'] == ['AI类']
