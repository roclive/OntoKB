"""End-to-end pipeline glue: fetch -> LLM -> ontology-validated graph ->
rules -> Obsidian vault."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from .graph import GraphStore
from .llm import process_content
from .models import ContentItem
from .ontology import Ontology, OntologyError
from .rules import RuleEngine
from .vault import ObsidianVault

log = logging.getLogger("ontokb")

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
        self.graph = GraphStore(ROOT / paths.get("db", "data/kb.db"))
        self.vault = ObsidianVault(ROOT / paths.get("vault", "vault"))
        self.engine = RuleEngine.load(ROOT / "rules" / "default.yaml")

    # -- M2: content acquisition ------------------------------------------

    def fetch(self, item: ContentItem) -> ContentItem:
        if item.source == "youtube":
            from .sources.youtube import fetch_transcript

            yt = self.config.get("sources", {}).get("youtube", {}) or {}
            paths = self.config.get("paths", {})
            item.raw_text = fetch_transcript(
                item,
                cookies_file=yt.get("cookies_file"),
                whisper_model=yt.get("whisper_model", "small"),
                whisper_language=yt.get("whisper_language"),
                whisper_device=yt.get("whisper_device", "cpu"),
                whisper_compute_type=yt.get("whisper_compute_type", "int8"),
                cache_dir=ROOT / paths.get("transcripts", "data/transcripts") / "youtube",
            )
        elif item.source == "netease":
            from .sources.netease import fetch_article

            item.raw_text = fetch_article(item)
        else:
            raise ValueError(f"unknown source: {item.source}")
        return item

    # -- M3/M4: LLM processing + graph build -------------------------------

    def ingest(self, item: ContentItem, client=None) -> dict:
        """Process one content item end to end. Returns a small stats dict."""
        if not item.raw_text:
            self.fetch(item)
        llm = self.config.get("llm", {}) or {}
        processed = process_content(
            item,
            self.ontology,
            self.config.get("interests", []),
            client=client,
            provider=llm.get("provider"),
            model=llm.get("model"),
            fallback_model=llm.get("fallback_model"),
        )

        entity_types = {e.name: e.type for e in processed.entities}
        accepted, rejected = 0, 0
        for entity in processed.entities:
            try:
                self.ontology.validate_entity(entity.type)
            except OntologyError as exc:
                log.warning("entity rejected: %s", exc)
                rejected += 1
                continue
            self.graph.upsert_entity(entity)
        for triple in processed.triples:
            try:
                if self.graph.add_triple(triple, self.ontology,
                                         source=item.id, entity_types=entity_types):
                    accepted += 1
            except (OntologyError, ValueError) as exc:
                log.warning("triple rejected: %s", exc)
                rejected += 1

        self.graph.upsert_content(
            item.id, item.kind, item.source, item.url, item.title,
            status="processed",
            meta={"relevance": processed.relevance, "summary": processed.summary},
        )
        self.vault.write_content_note(item, processed)
        for entity in processed.entities:
            self.vault.write_entity_note(self.graph, entity.name)
        return {"content_id": item.id, "triples_accepted": accepted, "rejected": rejected}

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
