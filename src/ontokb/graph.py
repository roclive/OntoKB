"""SQLite-backed triple store with alias-aware entity merging.

Deliberately lightweight: one file, no server, portable next to the vault.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Iterator, Optional

from .models import ExtractedEntity, ExtractedTriple
from .ontology import Ontology

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    properties TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS aliases (
    norm_alias TEXT PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id)
);
CREATE TABLE IF NOT EXISTS triples (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES entities(id),
    predicate TEXT NOT NULL,
    object_id INTEGER NOT NULL REFERENCES entities(id),
    confidence REAL NOT NULL DEFAULT 0.8,
    source TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    UNIQUE(subject_id, predicate, object_id, source)
);
CREATE TABLE IF NOT EXISTS contents (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject_id);
CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object_id);
"""


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).casefold().strip()
    return re.sub(r"\s+", " ", name)


class GraphStore:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- entities ---------------------------------------------------------

    def upsert_entity(self, entity: ExtractedEntity) -> int:
        """Insert or merge an entity; aliases resolve to the same row."""
        norm = normalize(entity.name)
        row = self._resolve(norm)
        if row is None:
            cur = self.conn.execute(
                "INSERT INTO entities (name, norm_name, type, aliases, properties) VALUES (?,?,?,?,?)",
                (entity.name, norm, entity.type,
                 json.dumps(entity.aliases, ensure_ascii=False),
                 json.dumps(entity.properties, ensure_ascii=False)),
            )
            eid = cur.lastrowid
        else:
            eid = row["id"]
            aliases = set(json.loads(row["aliases"]))
            aliases.update(entity.aliases)
            props = json.loads(row["properties"])
            props.update(entity.properties)
            self.conn.execute(
                "UPDATE entities SET aliases=?, properties=? WHERE id=?",
                (json.dumps(sorted(aliases), ensure_ascii=False),
                 json.dumps(props, ensure_ascii=False), eid),
            )
        for alias in entity.aliases:
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases (norm_alias, entity_id) VALUES (?,?)",
                (normalize(alias), eid),
            )
        self.conn.commit()
        return eid

    def _resolve(self, norm: str) -> Optional[sqlite3.Row]:
        row = self.conn.execute(
            "SELECT * FROM entities WHERE norm_name=?", (norm,)
        ).fetchone()
        if row:
            return row
        hit = self.conn.execute(
            "SELECT entity_id FROM aliases WHERE norm_alias=?", (norm,)
        ).fetchone()
        if hit:
            return self.conn.execute(
                "SELECT * FROM entities WHERE id=?", (hit["entity_id"],)
            ).fetchone()
        return None

    def get_entity(self, name: str) -> Optional[sqlite3.Row]:
        return self._resolve(normalize(name))

    def degree(self, entity_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM triples WHERE subject_id=? OR object_id=?",
            (entity_id, entity_id),
        ).fetchone()
        return row["n"]

    # -- triples ----------------------------------------------------------

    def add_triple(
        self,
        triple: ExtractedTriple,
        ontology: Ontology,
        source: str = "",
        entity_types: dict[str, str] | None = None,
    ) -> bool:
        """Validate against the ontology and insert. Returns False on duplicate.

        entity_types maps entity name -> class for entities in the same batch;
        falls back to the stored type for already-known entities.
        """
        subj = self.get_entity(triple.subject)
        obj = self.get_entity(triple.object)
        types = entity_types or {}
        subj_type = types.get(triple.subject) or (subj["type"] if subj else None)
        obj_type = types.get(triple.object) or (obj["type"] if obj else None)
        if subj is None or obj is None or subj_type is None or obj_type is None:
            raise ValueError(f"triple references unknown entity: {triple.subject!r} / {triple.object!r}")
        ontology.validate_triple(subj_type, triple.predicate, obj_type)
        try:
            self.conn.execute(
                "INSERT INTO triples (subject_id, predicate, object_id, confidence, source, evidence) "
                "VALUES (?,?,?,?,?,?)",
                (subj["id"], triple.predicate, obj["id"], triple.confidence, source, triple.evidence),
            )
        except sqlite3.IntegrityError:
            return False
        self.conn.commit()
        return True

    def neighbors(self, entity_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT t.predicate, t.confidence, t.source,
                      s.name AS subject, o.name AS object
               FROM triples t
               JOIN entities s ON s.id = t.subject_id
               JOIN entities o ON o.id = t.object_id
               WHERE t.subject_id=? OR t.object_id=?""",
            (entity_id, entity_id),
        ).fetchall()

    # -- contents ---------------------------------------------------------

    def upsert_content(self, content_id: str, kind: str, source: str, url: str,
                       title: str = "", status: str = "queued", meta: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO contents (id, kind, source, url, title, status, meta) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, status=excluded.status, meta=excluded.meta",
            (content_id, kind, source, url, title, status,
             json.dumps(meta or {}, ensure_ascii=False)),
        )
        self.conn.commit()

    # -- facts for the rule engine ----------------------------------------

    def facts(self) -> Iterator[dict]:
        """Project the graph into flat facts the rule engine can match on."""
        for row in self.conn.execute("SELECT * FROM entities"):
            yield {
                "kind": "entity",
                "name": row["name"],
                "type": row["type"],
                "degree": self.degree(row["id"]),
            }
        for row in self.conn.execute(
            """SELECT t.predicate, s.name AS subject, o.name AS object, t.confidence
               FROM triples t
               JOIN entities s ON s.id = t.subject_id
               JOIN entities o ON o.id = t.object_id"""
        ):
            yield {
                "kind": "triple",
                "subject": row["subject"],
                "predicate": row["predicate"],
                "object": row["object"],
                "confidence": row["confidence"],
            }
        for row in self.conn.execute("SELECT * FROM contents"):
            meta = json.loads(row["meta"])
            relevance = meta.get("relevance") or {}
            top = max(relevance.items(), key=lambda kv: kv[1]) if relevance else (None, 0.0)
            yield {
                "kind": "content",
                "id": row["id"],
                "content_kind": row["kind"],
                "source": row["source"],
                "title": row["title"],
                "status": row["status"],
                "relevance": top[1],
                "top_topic": top[0],
            }
