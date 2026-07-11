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
    properties TEXT NOT NULL DEFAULT '{}',
    sources TEXT NOT NULL DEFAULT '[]',
    added_time TEXT NOT NULL DEFAULT ''
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
    created_at TEXT NOT NULL DEFAULT '',
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

_CHINESE_VARIANTS = {
    "达": ("达", "達"),
    "達": ("達", "达"),
    "里": ("里", "裡", "裏"),
    "裡": ("裡", "里", "裏"),
    "裏": ("裏", "里", "裡"),
    "奥": ("奥", "奧"),
    "奧": ("奧", "奥"),
    "对": ("对", "對"),
    "對": ("對", "对"),
    "国": ("国", "國"),
    "國": ("國", "国"),
    "敌": ("敌", "敵"),
    "敵": ("敵", "敌"),
    "于": ("于", "於"),
    "於": ("於", "于"),
    "经": ("经", "經"),
    "經": ("經", "经"),
    "验": ("验", "驗"),
    "驗": ("驗", "验"),
    "与": ("与", "與"),
    "與": ("與", "与"),
    "虑": ("虑", "慮"),
    "慮": ("慮", "虑"),
    "逻": ("逻", "邏"),
    "邏": ("邏", "逻"),
    "辑": ("辑", "輯"),
    "輯": ("輯", "辑"),
    "权": ("权", "權"),
    "權": ("權", "权"),
    "术": ("术", "術"),
    "術": ("術", "术"),
    "问": ("问", "問"),
    "問": ("問", "问"),
    "题": ("题", "題"),
    "題": ("題", "题"),
    "锁": ("锁", "鎖"),
    "鎖": ("鎖", "锁"),
    "户": ("户", "戶"),
    "戶": ("戶", "户"),
    "体": ("体", "體"),
    "體": ("體", "体"),
    "频": ("频", "頻"),
    "頻": ("頻", "频"),
    "视": ("视", "視"),
    "視": ("視", "视"),
}


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
        self._migrate()

    def _migrate(self) -> None:
        """Add provenance columns to databases created before source tagging."""
        entity_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(entities)")}
        if "sources" not in entity_cols:
            self.conn.execute("ALTER TABLE entities ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'")
        if "added_time" not in entity_cols:
            self.conn.execute("ALTER TABLE entities ADD COLUMN added_time TEXT NOT NULL DEFAULT ''")
        triple_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(triples)")}
        if "created_at" not in triple_cols:
            self.conn.execute("ALTER TABLE triples ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- entities ---------------------------------------------------------

    def upsert_entity(
        self,
        entity: ExtractedEntity,
        source: str = "",
        added_time: str = "",
    ) -> int:
        """Insert or merge an entity; aliases resolve to the same row.

        `source` (a content id) is accumulated into the entity's sources list so
        merged entities keep provenance from every document that mentioned them.
        `added_time` is kept from the first sighting.
        """
        norm = normalize(entity.name)
        row = self._resolve(norm)
        if row is None:
            cur = self.conn.execute(
                "INSERT INTO entities (name, norm_name, type, aliases, properties, sources, added_time) "
                "VALUES (?,?,?,?,?,?,?)",
                (entity.name, norm, entity.type,
                 json.dumps(entity.aliases, ensure_ascii=False),
                 json.dumps(entity.properties, ensure_ascii=False),
                 json.dumps([source] if source else [], ensure_ascii=False),
                 added_time),
            )
            eid = cur.lastrowid
        else:
            eid = row["id"]
            aliases = set(json.loads(row["aliases"]))
            aliases.update(entity.aliases)
            props = json.loads(row["properties"])
            props.update(entity.properties)
            sources = list(json.loads(row["sources"]))
            if source and source not in sources:
                sources.append(source)
            self.conn.execute(
                "UPDATE entities SET aliases=?, properties=?, sources=?, added_time=? WHERE id=?",
                (json.dumps(sorted(aliases), ensure_ascii=False),
                 json.dumps(props, ensure_ascii=False),
                 json.dumps(sources, ensure_ascii=False),
                 row["added_time"] or added_time, eid),
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

    def search_entities(
        self,
        query: str,
        *,
        mode: str = "terms",
        limit: int = 50,
        expand: bool = False,
    ) -> list[dict]:
        """Find entities by name or alias.

        mode="phrase" searches the whole query as one phrase; mode="terms" searches
        each whitespace-separated term and returns entities matching any term. When
        expand=True, phrase mode also searches the phrase's component terms.
        """
        terms = _query_terms(query, mode)
        if expand:
            terms = _expanded_query_terms(query, terms)
        terms = _variant_query_terms(terms)
        if not terms:
            return []

        matches: dict[int, dict] = {}
        for term in terms:
            like = f"%{normalize(term)}%"
            rows = self.conn.execute(
                """SELECT id, name, type, aliases, properties, sources, added_time,
                          'name' AS matched_by, name AS matched_value
                   FROM entities
                   WHERE norm_name LIKE ? OR lower(name) LIKE ?
                   ORDER BY name
                   LIMIT ?""",
                (like, like, limit),
            ).fetchall()
            for row in rows:
                _add_entity_match(matches, row, term)

            alias_rows = self.conn.execute(
                """SELECT e.id, e.name, e.type, e.aliases, e.properties, e.sources, e.added_time,
                          'alias' AS matched_by, a.norm_alias AS matched_value
                   FROM aliases a
                   JOIN entities e ON e.id = a.entity_id
                   WHERE a.norm_alias LIKE ?
                   ORDER BY e.name
                   LIMIT ?""",
                (like, limit),
            ).fetchall()
            for row in alias_rows:
                _add_entity_match(matches, row, term)

            json_alias_rows = self.conn.execute(
                """SELECT id, name, type, aliases, properties, sources, added_time,
                          'alias_json' AS matched_by, aliases AS matched_value
                   FROM entities
                   WHERE lower(aliases) LIKE ?
                   ORDER BY name
                   LIMIT ?""",
                (like, limit),
            ).fetchall()
            for row in json_alias_rows:
                _add_entity_match(matches, row, term)

        return sorted(matches.values(), key=lambda item: (item["name"].casefold(), item["id"]))[:limit]

    def related_graph(
        self,
        query: str,
        *,
        mode: str = "terms",
        limit: int = 50,
        expand: bool = True,
    ) -> dict:
        """Return matched entities and their one-hop triples.

        This is the programmatic form of the ad-hoc SQLite query used for finding
        "harness agent" nodes plus incoming/outgoing relationships.
        """
        matched_entities = self.search_entities(query, mode=mode, limit=limit, expand=expand)
        matched_ids = {entity["id"] for entity in matched_entities}
        edge_rows: list[sqlite3.Row] = []
        if matched_ids:
            placeholders = ",".join("?" for _ in matched_ids)
            edge_rows = self.conn.execute(
                f"""SELECT t.id AS id,
                          s.id AS subject_id, s.name AS subject, s.type AS subject_type,
                          t.predicate,
                          o.id AS object_id, o.name AS object, o.type AS object_type,
                          t.confidence, t.source, t.evidence, t.created_at
                   FROM triples t
                   JOIN entities s ON s.id = t.subject_id
                   JOIN entities o ON o.id = t.object_id
                   WHERE t.subject_id IN ({placeholders}) OR t.object_id IN ({placeholders})
                   ORDER BY t.id
                   LIMIT ?""",
                (*matched_ids, *matched_ids, limit),
            ).fetchall()

        related_ids = set(matched_ids)
        edges = []
        relations = []
        source_ids = set()
        for row in edge_rows:
            related_ids.add(row["subject_id"])
            related_ids.add(row["object_id"])
            if row["source"]:
                source_ids.add(row["source"])
            edges.append(_edge_dict(row))
            relations.append(
                {
                    "triple_id": row["id"],
                    "relation": f'{row["subject"]} -- {row["predicate"]} -> {row["object"]}',
                }
            )

        related_entities = self._entities_by_id(related_ids)
        return {
            "query": query,
            "mode": mode,
            "expand": expand,
            "matched_entities": matched_entities,
            "related_entities": related_entities,
            "relations": relations,
            "edges": edges,
            "sources": self._contents_by_id(source_ids),
        }

    # -- triples ----------------------------------------------------------

    def add_triple(
        self,
        triple: ExtractedTriple,
        ontology: Ontology,
        source: str = "",
        entity_types: dict[str, str] | None = None,
        created_at: str = "",
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
                "INSERT INTO triples (subject_id, predicate, object_id, confidence, source, evidence, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (subj["id"], triple.predicate, obj["id"], triple.confidence, source,
                 triple.evidence, created_at),
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

    def _entities_by_id(self, ids: set[int]) -> list[dict]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""SELECT id, name, type, aliases, properties, sources, added_time
                FROM entities
                WHERE id IN ({placeholders})
                ORDER BY name""",
            tuple(ids),
        ).fetchall()
        return [_entity_dict(row) for row in rows]

    def _contents_by_id(self, ids: set[str]) -> list[dict]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""SELECT id, kind, source, url, title, status, meta
                FROM contents
                WHERE id IN ({placeholders})
                ORDER BY id""",
            tuple(ids),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "source": row["source"],
                "url": row["url"],
                "title": row["title"],
                "status": row["status"],
                "meta": json.loads(row["meta"]),
            }
            for row in rows
        ]

    # -- contents ---------------------------------------------------------

    def contents_by_id(self, ids) -> list[dict]:
        """Public lookup of content rows (documents) by id, for provenance display."""
        return self._contents_by_id(set(ids))

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


def _query_terms(query: str, mode: str) -> list[str]:
    query = query.strip()
    if not query:
        return []
    if mode == "phrase":
        return [query]
    if mode == "terms":
        return [term for term in re.split(r"\s+", query) if term]
    raise ValueError("mode must be 'terms' or 'phrase'")


def _expanded_query_terms(query: str, base_terms: list[str]) -> list[str]:
    expanded = list(base_terms)
    expanded.extend(term for term in re.split(r"\s+", query.strip()) if term)
    return _dedupe_terms(expanded)


def _variant_query_terms(terms: list[str]) -> list[str]:
    variants = []
    for term in terms:
        variants.extend(_term_variants(term))
    return _dedupe_terms(variants)


def _term_variants(term: str, limit: int = 64) -> list[str]:
    terms = [""]
    for char in term:
        options = _CHINESE_VARIANTS.get(char, (char,))
        next_terms = []
        for prefix in terms:
            for option in options:
                next_terms.append(prefix + option)
                if len(next_terms) >= limit:
                    break
            if len(next_terms) >= limit:
                break
        terms = next_terms
    return terms


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for term in terms:
        norm = normalize(term)
        if norm not in seen:
            seen.add(norm)
            deduped.append(term)
    return deduped


def _entity_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "aliases": json.loads(row["aliases"]),
        "properties": json.loads(row["properties"]),
        "sources": json.loads(row["sources"]),
        "added_time": row["added_time"],
    }


def _add_entity_match(matches: dict[int, dict], row: sqlite3.Row, term: str) -> None:
    entity = matches.setdefault(row["id"], _entity_dict(row) | {"matches": []})
    match = {
        "term": term,
        "matched_by": row["matched_by"],
        "matched_value": row["matched_value"],
    }
    if match not in entity["matches"]:
        entity["matches"].append(match)


def _edge_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "subject": row["subject"],
        "subject_type": row["subject_type"],
        "predicate": row["predicate"],
        "object_id": row["object_id"],
        "object": row["object"],
        "object_type": row["object_type"],
        "confidence": row["confidence"],
        "source": row["source"],
        "evidence": row["evidence"],
        "created_at": row["created_at"],
    }
