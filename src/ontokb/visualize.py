"""Export the knowledge graph as a standalone interactive HTML page.

Reads nodes/edges straight from the SQLite graph store (the source of
truth; entity notes are just a projection of it) and embeds them into a
self-contained D3 force-directed graph. Only external dependency is the
D3 script tag (CDN), so the file opens in any browser.
"""

from __future__ import annotations

import json
from pathlib import Path

from .graph import GraphStore

# type -> (base color, darker accent for light backgrounds)
_TYPE_COLORS = {
    "Organization": ("#7F77DD", "#534AB7"),
    "Person": ("#1D9E75", "#0F6E56"),
    "Product": ("#D85A30", "#993C1D"),
    "Technology": ("#378ADD", "#185FA5"),
    "Claim": ("#EF9F27", "#854F0B"),
    "Content": ("#D4537E", "#993556"),
    "Topic": ("#97C459", "#3B6D11"),
    "Event": ("#E24B4A", "#A32D2D"),
    "DefinedTerm": ("#378ADD", "#185FA5"),
    "SoftwareApplication": ("#D85A30", "#993C1D"),
    "CreativeWork": ("#D4537E", "#993556"),
    "MediaObject": ("#D4537E", "#993556"),
    "VideoObject": ("#D4537E", "#993556"),
    "Article": ("#D4537E", "#993556"),
    "Book": ("#A07850", "#77512B"),
}
_FALLBACK_COLOR = ("#888780", "#5F5E5A")

_TYPE_LABELS_CN = {
    "Organization": "组织", "Person": "人物", "Product": "产品",
    "Technology": "技术", "Claim": "观点", "Content": "内容",
    "Topic": "话题", "Event": "事件", "Thing": "其他",
    "DefinedTerm": "概念与术语", "SoftwareApplication": "软件应用",
    "CreativeWork": "作品", "MediaObject": "媒体", "VideoObject": "视频",
    "Article": "文章", "Book": "书籍",
}
_TYPE_LABELS_CN.update({"Thing": "待复核", "Claim": "论断"})


def graph_data(graph: GraphStore) -> dict:
    """Project entities + triples into the node/edge lists the page embeds."""
    nodes = [
        {"id": row["name"], "entity_id": row["id"], "type": row["type"],
         "ontologyUri": graph.ontology.classes.get(graph.ontology.canonical_class(row["type"]), {}).get("uri", ""),
         "reviewStatus": json.loads(row["properties"]).get("reviewStatus", ""),
         "verificationStatus": json.loads(row["properties"]).get("verificationStatus", "")}
        for row in graph.conn.execute("SELECT id, name, type, properties FROM entities ORDER BY name")
    ]
    edges = [
        {"s": row["subject"], "p": row["predicate"], "t": row["object"]}
        for row in graph.conn.execute(
            """SELECT DISTINCT s.name AS subject, t.predicate, o.name AS object
               FROM triples t
               JOIN entities s ON s.id = t.subject_id
               JOIN entities o ON o.id = t.object_id
               ORDER BY s.name, t.predicate, o.name"""
        )
    ]
    from .reading import reading_library
    return {"nodes": nodes, "edges": edges, "library": reading_library(graph)}


def render_html(data: dict, title: str = "Knowledge graph") -> str:
    # <-escape so entity names can never close the script tag
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    colors = {t: c for t, c in _TYPE_COLORS.items()}
    from html import escape
    web = Path(__file__).parent / "web"
    html = (web / "reading.html").read_text(encoding="utf-8")
    html = html.replace("__STYLE__", (web / "reading.css").read_text(encoding="utf-8")
                        + "\n" + (web / "editor.css").read_text(encoding="utf-8")
                        + "\n" + (web / "memory.css").read_text(encoding="utf-8")
                        + "\n" + (web / "media.css").read_text(encoding="utf-8"))
    html = html.replace("__SCRIPT__", (web / "reading.js").read_text(encoding="utf-8"))
    html = html.replace("__ASSISTANT__", (web / "assistant.js").read_text(encoding="utf-8")
                        + "\n" + (web / "editor.js").read_text(encoding="utf-8")
                        + "\n" + (web / "memory.js").read_text(encoding="utf-8")
                        + "\n" + (web / "media.js").read_text(encoding="utf-8"))
    html = html.replace("__COLORS__", json.dumps(colors, ensure_ascii=False))
    html = html.replace("__FALLBACK__", json.dumps(_FALLBACK_COLOR))
    html = html.replace("__LABELS__", json.dumps(_TYPE_LABELS_CN, ensure_ascii=False))
    html = html.replace("__TITLE__", escape(title))
    return html.replace("__DATA__", payload)



def export_html(graph: GraphStore, out_path: str | Path,
                title: str = "Knowledge graph") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(graph_data(graph), title), encoding="utf-8")
    return out
