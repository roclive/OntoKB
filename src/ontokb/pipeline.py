"""End-to-end pipeline glue: fetch -> LLM -> ontology-validated graph ->
rules -> Obsidian vault."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .graph import GraphStore
from .llm import process_content
from .models import ContentItem, ExtractedEntity, ExtractedTriple
from .ontology import Ontology, OntologyError
from .rules import RuleEngine
from .sources.youtube import DEFAULT_WHISPER_LANGUAGE
from .vault import ObsidianVault

log = logging.getLogger("ontokb")

DEFAULT_OUTPUT_LANGUAGE = "Simplified Chinese"

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    candidates = [path] if path else [ROOT / "config" / "config.yaml",
                                      ROOT / "config" / "config.example.yaml"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return yaml.safe_load(Path(candidate).read_text(encoding="utf-8"))
    raise FileNotFoundError("no config found; copy config/config.example.yaml to config/config.yaml")


class Pipeline:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        paths = self.config.get("paths", {})
        self.ontology = Ontology.load(ROOT / "ontology" / "core.yaml")
        self.graph = GraphStore(ROOT / paths.get("db", "data/kb.db"), ontology=self.ontology)
        self.vault = ObsidianVault(ROOT / paths.get("vault", "vault"))
        self.engine = RuleEngine.load(ROOT / "rules" / "default.yaml")

    # -- M2: content acquisition ------------------------------------------

    def fetch(self, item: ContentItem, progress=None) -> ContentItem:
        if item.source == "youtube":
            from .sources.youtube import fetch_transcript

            yt = self.config.get("sources", {}).get("youtube", {}) or {}
            paths = self.config.get("paths", {})
            item.raw_text = fetch_transcript(
                item,
                cookies_file=yt.get("cookies_file"),
                whisper_model=yt.get("whisper_model", "small"),
                whisper_language=yt.get("whisper_language") or DEFAULT_WHISPER_LANGUAGE,
                whisper_device=yt.get("whisper_device", "cpu"),
                whisper_compute_type=yt.get("whisper_compute_type", "int8"),
                cache_dir=ROOT / paths.get("transcripts", "data/transcripts") / "youtube",
                **({"progress": progress} if progress is not None else {}),
            )
        elif item.source == "netease":
            from .sources.netease import fetch_article

            item.raw_text = fetch_article(item)
        else:
            raise ValueError(f"unknown source: {item.source}")
        return item

    # -- M3/M4: LLM processing + graph build -------------------------------

    def ingest(self, item: ContentItem, client=None) -> dict:
        """Process one content item end to end. Returns a small stats dict.

        Builds a two-tier graph: the LLM extracts the knowledge tier (entity-to-
        entity relations), then the pipeline deterministically adds the document
        tier — one Content node per ingested item, linked to every extracted
        entity via mentions/about — so grounding never depends on LLM output.
        """
        if not item.raw_text:
            self.fetch(item)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        llm = self.config.get("llm", {}) or {}
        defaults = self.config.get("defaults", {}) or {}
        processed = process_content(
            item,
            self.ontology,
            self.config.get("interests", []),
            client=client,
            provider=llm.get("provider"),
            model=llm.get("model"),
            fallback_model=llm.get("fallback_model"),
            output_language=llm.get("output_language")
            or defaults.get("output_language")
            or DEFAULT_OUTPUT_LANGUAGE,
        )

        entity_types = {e.name: e.type for e in processed.entities}
        accepted, rejected = 0, 0
        accepted_entities: list[str] = []
        rejected_names: set[str] = set()
        rejection_details: list[dict] = []
        validated_triples: list[ExtractedTriple] = []
        for entity in processed.entities:
            try:
                self.ontology.validate_entity(entity.type)
                self.graph.upsert_entity(entity, source=item.id, added_time=now)
            except OntologyError as exc:
                log.warning("entity rejected: %s", exc)
                rejected += 1
                rejected_names.add(entity.name)
                rejection_details.append({"kind": "entity", "name": entity.name, "error": str(exc)})
                continue
            accepted_entities.append(entity.name)
        for triple in processed.triples:
            try:
                if triple.subject in rejected_names or triple.object in rejected_names:
                    raise OntologyError("triple references a rejected entity")
                if self.graph.add_triple(triple, self.ontology, source=item.id,
                                         entity_types=entity_types, created_at=now):
                    accepted += 1
                validated_triples.append(triple.model_copy(update={
                    "predicate": self.ontology.canonical_relation(triple.predicate)}))
            except (OntologyError, ValueError) as exc:
                log.warning("triple rejected: %s", exc)
                rejected += 1
                rejection_details.append({"kind": "triple", "subject": triple.subject,
                                          "predicate": triple.predicate, "object": triple.object,
                                          "error": str(exc)})

        doc_links = self._link_document(item, [t for t in processed.topics if t not in rejected_names], accepted_entities, now)

        self.graph.upsert_content(
            item.id, item.kind, item.source, item.url, item.title,
            status="processed",
            meta={"relevance": processed.relevance, "summary": processed.summary,
                  "added_time": now, "key_points": processed.key_points,
                  "extraction_rejections": rejection_details,
                  **({"raw_text": item.raw_text} if item.kind == "article" else {})},
        )
        # Source notes project accepted knowledge, not rejected raw model output.
        self.vault.write_content_note(item, processed.model_copy(update={
            "triples": validated_triples,
            "topics": [t for t in processed.topics if t not in rejected_names],
        }))
        for name in accepted_entities:
            self.vault.write_entity_note(self.graph, name)
        return {"content_id": item.id, "triples_accepted": accepted,
                "rejected": rejected, "document_links": doc_links}

    def _link_document(
        self,
        item: ContentItem,
        topics: list[str],
        entity_names: list[str],
        now: str,
    ) -> int:
        """Create the document-tier node for `item` and wire it to the knowledge
        tier: Content --about--> Topic and Content --mentions--> entity."""
        properties = {
            "url": item.url,
            "source": item.source,
            "kind": item.kind,
            "added_time": now,
        }
        if item.published_at:
            properties["published_at"] = item.published_at
        doc = ExtractedEntity(
            name=item.title or item.id,
            type="VideoObject" if item.kind == "video" else "Article",
            aliases=[item.id],  # stable handle even if the title changes
            properties=properties,
        )
        doc_id = self.graph.upsert_entity(doc, source=item.id, added_time=now)

        linked = 0
        seen_ids = {doc_id}
        for topic in dict.fromkeys(topics):
            # Topic is a role (about target), not a competing entity type.
            # A document can be about OpenAI without retyping it as a concept.
            existing = self.graph.get_entity(topic)
            self.graph.upsert_entity(ExtractedEntity(
                name=topic, type=existing["type"] if existing else "DefinedTerm"),
                source=item.id, added_time=now)
            linked += self._link_doc_edge(doc.name, "about", topic, item.id, now, seen_ids)
        for name in dict.fromkeys(entity_names):
            linked += self._link_doc_edge(doc.name, "mentions", name, item.id, now, seen_ids)
        return linked

    def _link_doc_edge(
        self,
        doc_name: str,
        predicate: str,
        target: str,
        source: str,
        now: str,
        seen_ids: set[int],
    ) -> int:
        """Add one document-tier edge, skipping self-loops and already-linked
        targets (an entity that is also a topic only gets the `about` edge)."""
        row = self.graph.get_entity(target)
        if row is None or row["id"] in seen_ids:
            return 0
        triple = ExtractedTriple(subject=doc_name, predicate=predicate,
                                 object=target, confidence=1.0, evidence="")
        try:
            added = self.graph.add_triple(triple, self.ontology, source=source, created_at=now)
        except (OntologyError, ValueError) as exc:
            log.info("document link skipped: %s", exc)
            return 0
        seen_ids.add(row["id"])  # inserted now, or already linked by a past ingest
        return 1 if added else 0

    def backfill_documents(self) -> dict:
        """Rebuild the document tier for contents ingested before the two-tier
        refactor: one Content node per processed row, mentions edges to every
        entity that appears in a triple sourced from it, and source tags on
        those entities. Offline — no LLM calls; safe to re-run."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        docs, links = 0, 0
        rows = self.graph.conn.execute(
            "SELECT id, kind, source, url, title FROM contents WHERE status='processed'"
        ).fetchall()
        for row in rows:
            involved = self.graph.conn.execute(
                """SELECT DISTINCT e.name AS name, e.type AS type
                   FROM triples t
                   JOIN entities e ON e.id = t.subject_id OR e.id = t.object_id
                   WHERE t.source = ?""",
                (row["id"],),
            ).fetchall()
            for ent in involved:
                self.graph.upsert_entity(
                    ExtractedEntity(name=ent["name"], type=ent["type"]),
                    source=row["id"], added_time=now,
                )
            item = ContentItem(id=row["id"], kind=row["kind"], source=row["source"],
                               url=row["url"], title=row["title"])
            links += self._link_document(item, [], [ent["name"] for ent in involved], now)
            docs += 1
        return {"documents": docs, "links_added": links}

    # -- M5: rules ----------------------------------------------------------

    def run_rules(self) -> list:
        actions = self.engine.run(list(self.graph.facts()))
        for action in actions:
            self.vault.apply_action(self.graph, action)
        return actions

    # -- visualization -------------------------------------------------------

    def export_graph_html(self, out: str | Path | None = None) -> Path:
        from .visualize import export_html

        paths = self.config.get("paths", {})
        target = Path(out or paths.get("graph_html")
                      or Path(paths.get("vault", "vault")) / "Knowledge Graph.html")
        if not target.is_absolute():
            target = ROOT / target
        return export_html(self.graph, target)

    def status(self) -> dict:
        c = self.graph.conn
        return {
            "entities": c.execute("SELECT COUNT(*) n FROM entities").fetchone()["n"],
            "triples": c.execute("SELECT COUNT(*) n FROM triples").fetchone()["n"],
            "contents": c.execute("SELECT COUNT(*) n FROM contents").fetchone()["n"],
        }


def report_stub() -> str:
    """M5 placeholder: real report generation aggregates the queue by topic."""
    return json.dumps({"todo": "aggregate Reports/_queue.md by topic, call LLM once per topic"},
                      ensure_ascii=False)
