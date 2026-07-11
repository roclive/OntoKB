"""Obsidian vault writer: content notes, entity notes with typed links,
and rule-engine outputs (wiki pages / MOCs / report queue)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .graph import GraphStore
from .models import ContentItem, ProcessedContent

DIRS = ("Sources", "Entities", "Wiki", "MOC", "Reports")


def slugify(name: str) -> str:
    # Obsidian filenames: strip characters invalid on Windows/macOS
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", name).strip() or "untitled"


class ObsidianVault:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        for d in DIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def _write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_content_note(self, item: ContentItem, processed: ProcessedContent) -> Path:
        topics_links = ", ".join(f'"[[{slugify(t)}]]"' for t in processed.topics)
        fm = [
            "---",
            f'title: "{item.title}"',
            f"source: {item.source}",
            f"kind: {item.kind}",
            f"url: {item.url}",
            f"content_id: {item.id}",
            f"topics: [{topics_links}]",
            "tags: [inbox]",
            "---",
        ]
        body = [f"# {item.title or item.id}", "", "## Summary", processed.summary, "", "## Key points"]
        body += [f"- {p}" for p in processed.key_points]
        if processed.relevance:
            body += ["", "## Relevance"]
            body += [f"- {k}: {v:.2f}" for k, v in
                     sorted(processed.relevance.items(), key=lambda kv: -kv[1])]
        if processed.triples:
            body += ["", "## Extracted knowledge"]
            body += [f"- [[{slugify(t.subject)}]] **{t.predicate}** [[{slugify(t.object)}]]"
                     for t in processed.triples]
        return self._write(f"Sources/{slugify(item.title or item.id)}.md",
                           "\n".join(fm + [""] + body) + "\n")

    def write_entity_note(self, graph: GraphStore, name: str) -> Path | None:
        row = graph.get_entity(name)
        if row is None:
            return None
        lines = [
            "---",
            f'entity: "{row["name"]}"',
            f"type: {row['type']}",
            "---",
            f"# {row['name']}",
            "",
            "## Relations",
        ]
        for rel in graph.neighbors(row["id"]):
            if rel["subject"] == row["name"]:
                lines.append(f"- **{rel['predicate']}** → [[{slugify(rel['object'])}]]")
            else:
                lines.append(f"- [[{slugify(rel['subject'])}]] **{rel['predicate']}** → this")
        source_ids = json.loads(row["sources"]) if "sources" in row.keys() else []
        docs = graph.contents_by_id(source_ids)
        if docs:
            lines += ["", "## Sources"]
            for doc in docs:
                label = doc["title"] or doc["id"]
                lines.append(f"- [[{slugify(label)}]] ({doc['source']}) {doc['url']}")
        return self._write(f"Entities/{slugify(row['name'])}.md", "\n".join(lines) + "\n")

    def apply_action(self, graph: GraphStore, action) -> Path | None:
        """Materialize a rule-engine action into the vault."""
        p = action.params
        if action.action == "create_wiki_page":
            name = p.get("entity")
            return self._write(
                f"Wiki/{slugify(name)}.md",
                f"---\ntype: wiki\nentity: \"{name}\"\n---\n# {name}\n\n"
                f"> Auto-created by rule `{action.rule}`. See [[{slugify(name)}]] entity note.\n",
            ) if name else None
        if action.action == "create_moc":
            name = p.get("entity")
            return self._write(
                f"MOC/{slugify(name)} MOC.md",
                f"---\ntype: moc\n---\n# {name} — Map of Content\n\n- [[{slugify(name)}]]\n",
            ) if name else None
        if action.action in ("queue_report", "flag_controversy"):
            queue = self.root / "Reports" / "_queue.md"
            entry = f"- `{action.action}` {p} (rule: {action.rule})\n"
            existing = queue.read_text(encoding="utf-8") if queue.exists() else "# Report queue\n\n"
            if entry not in existing:
                queue.write_text(existing + entry, encoding="utf-8")
            return queue
        return None
