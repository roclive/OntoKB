"""Offline, transactional migration to the Schema.org research profile.

No LLM calls, entity deletion, or guessed sameAs links. IDs and evidence survive.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

from .graph import GraphStore
from .ontology import Ontology, OntologyError


def migration_plan(graph: GraphStore, ontology: Ontology, overrides: dict | None = None) -> dict:
    decisions = (overrides or {}).get("entities", {})
    entities, relations, errors, reviews = [], [], [], []
    rows = graph.conn.execute("SELECT * FROM entities ORDER BY id").fetchall()
    types = {}
    for row in rows:
        old = row["type"]
        new = ontology.canonical_class(old)
        props = json.loads(row["properties"])
        reason = "标准类型保留" if old == new else "旧类型映射到 Schema.org"
        if old == "Content":
            new = {"video": "VideoObject", "article": "Article"}.get(props.get("kind"), "CreativeWork")
            reason = "按已保存的内容媒介细分"
        decision = decisions.get(row["name"], {})
        if decision and old == decision.get("from"):
            new = decision["to"]
            props.update(decision.get("properties", {}))
            reason = decision["reason"]
        try:
            ontology.validate_entity(new)
        except OntologyError as exc:
            errors.append({"entity_id": row["id"], "error": str(exc)})
        if new in ontology.classes:
            props["ontologyUri"] = ontology.classes[new]["uri"]
        props["ontologyVersion"] = str(ontology.version)
        if old != new:
            props.setdefault("legacyType", old)
            props["classificationReason"] = reason
        if old in {"Technology", "Topic"} and new == "DefinedTerm":
            props.setdefault("termCategory", "technology" if old == "Technology" else "research_topic")
        if new == "Claim":
            props.setdefault("text", row["name"])
            props.setdefault("verificationStatus", "unverified")
        if new == "Thing":
            props["reviewStatus"] = "needs_review"
            props.setdefault("reviewReason", "没有足够证据判断具体类型")
        if props.get("reviewStatus") == "needs_review":
            reviews.append({"id": row["id"], "name": row["name"], "reason": props["reviewReason"]})
        types[row["id"]] = new
        entities.append({"id": row["id"], "name": row["name"], "before": old, "after": new,
                         "properties": props, "reason": reason,
                         "changed": old != new or props != json.loads(row["properties"])})
    seen = set()
    for row in graph.conn.execute("SELECT * FROM triples ORDER BY id"):
        pred = ontology.canonical_relation(row["predicate"])
        try:
            ontology.validate_triple(types.get(row["subject_id"], ""), pred,
                                     types.get(row["object_id"], ""))
        except OntologyError as exc:
            errors.append({"triple_id": row["id"], "error": str(exc)})
        key = (row["subject_id"], pred, row["object_id"], row["source"])
        if key in seen:
            errors.append({"triple_id": row["id"], "error": "predicate mapping would create a duplicate"})
        seen.add(key)
        relations.append({"id": row["id"], "before": row["predicate"], "after": pred})
    # Audit alias ownership as well as the aliases table, without merging by guess.
    for row in rows:
        for alias in json.loads(row["aliases"]):
            owner = graph.get_entity(alias)
            if owner is None or owner["id"] != row["id"]:
                errors.append({"entity_id": row["id"], "error": f"ambiguous alias: {alias}"})
    return {"profile_version": ontology.version, "entities": entities, "relations": relations,
            "before_counts": dict(Counter(r["type"] for r in rows)),
            "after_counts": dict(Counter(types.values())), "errors": errors, "needs_review": reviews,
            "entity_type_changes": sum(e["before"] != e["after"] for e in entities),
            "relation_changes": sum(r["before"] != r["after"] for r in relations)}


def migrate_graph(graph: GraphStore, ontology: Ontology, backup_dir: Path,
                  overrides: dict | None = None, *, apply: bool = False) -> dict:
    # Hold the write lock across planning, backup, and updates, so an ingest
    # cannot slip in between validation and commit.
    graph.conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
    try:
        plan = migration_plan(graph, ontology, overrides)
        plan["applied"] = False
        if not apply:
            graph.conn.rollback()
            return plan
        if plan["errors"]:
            raise OntologyError(f"migration blocked by {len(plan['errors'])} validation errors: {plan['errors']}")
        changed = any(e["changed"] for e in plan["entities"]) or plan["relation_changes"]
        if not changed:
            graph.conn.rollback()
            plan["already_current"] = True
            return plan
        db_path = graph.conn.execute("PRAGMA database_list").fetchone()["file"]
        if not db_path:
            raise ValueError("applied migration requires an on-disk database for backup")
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = backup_dir / f"kb-before-schema-v2-{stamp}.db"
        # A separate read connection can snapshot the committed state while the
        # writer holds RESERVED. Backing up the writing connection can deadlock.
        with sqlite3.connect(db_path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        plan["backup"] = str(backup.resolve())
        for entity in plan["entities"]:
            if entity["changed"]:
                graph.conn.execute("UPDATE entities SET type=?, properties=? WHERE id=?",
                                   (entity["after"], json.dumps(entity["properties"], ensure_ascii=False), entity["id"]))
        for relation in plan["relations"]:
            if relation["before"] != relation["after"]:
                graph.conn.execute("UPDATE triples SET predicate=? WHERE id=?",
                                   (relation["after"], relation["id"]))
        graph.conn.commit()
        plan["applied"] = True
        return plan
    except BaseException:
        graph.conn.rollback()
        raise


def load_overrides(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def export_jsonld(graph: GraphStore, ontology: Ontology, path: Path) -> Path:
    """Export vocabulary URIs and reified, source-qualified assertions.

    Edges are statements, not unconditional RDF facts; all source confidence,
    evidence, and dates are retained. Unknown property names stay local.
    """
    nodes = []
    for row in graph.conn.execute("SELECT * FROM entities ORDER BY id"):
        cls = ontology.canonical_class(row["type"])
        props = json.loads(row["properties"])
        node = {"@id": f"urn:ontokb:entity:{row['id']}", "@type": ontology.classes[cls]["uri"],
                "schema:name": row["name"], "schema:alternateName": json.loads(row["aliases"]),
                "kb:sourceIds": json.loads(row["sources"]), "kb:addedTime": row["added_time"],
                "kb:properties": {"@value": props, "@type": "@json"}}
        if cls == "Claim":
            node["schema:text"] = props.get("text", row["name"])
        nodes.append(node)
    for row in graph.conn.execute("SELECT * FROM triples ORDER BY id"):
        pred = ontology.canonical_relation(row["predicate"])
        nodes.append({"@id": f"urn:ontokb:statement:{row['id']}", "@type": "rdf:Statement",
                      "rdf:subject": {"@id": f"urn:ontokb:entity:{row['subject_id']}"},
                      "rdf:predicate": {"@id": ontology.relations[pred].uri},
                      "rdf:object": {"@id": f"urn:ontokb:entity:{row['object_id']}"},
                      "kb:sourceId": row["source"], "kb:evidence": row["evidence"],
                      "kb:confidence": row["confidence"], "kb:createdAt": row["created_at"]})
    for row in graph.conn.execute("SELECT * FROM contents ORDER BY id"):
        nodes.append({"@id": "urn:ontokb:content:" + quote(row["id"], safe=""),
                      "@type": "kb:SourceRecord", "schema:identifier": row["id"],
                      "schema:url": row["url"], "schema:name": row["title"],
                      "kb:source": row["source"], "kb:kind": row["kind"],
                      "kb:status": row["status"], "kb:meta": {"@value": json.loads(row["meta"]), "@type": "@json"}})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"@context": {"@version": 1.1, "schema": "https://schema.org/",
                      "kb": "urn:ontokb:ontology:", "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"},
                      "@graph": nodes}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
