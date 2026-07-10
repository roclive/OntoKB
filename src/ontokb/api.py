"""Small JSON API for querying the SQLite knowledge graph."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .graph import GraphStore


def run_api(db_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the graph query API until interrupted."""

    graph = GraphStore(db_path)

    class Handler(GraphApiHandler):
        store = graph

    server = HTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        graph.close()


class GraphApiHandler(BaseHTTPRequestHandler):
    store: GraphStore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                self._send_json({"ok": True})
            elif parsed.path == "/api/entities/search":
                self._handle_entity_search(params)
            elif parsed.path == "/api/graph/query":
                self._handle_graph_query(params)
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args) -> None:
        return

    def _handle_entity_search(self, params: dict[str, list[str]]) -> None:
        query = _required(params, "q")
        mode = _one(params, "mode", "terms")
        limit = _limit(params)
        expand = _bool(params, "expand", False)
        self._send_json(
            {
                "query": query,
                "mode": mode,
                "expand": expand,
                "entities": self.store.search_entities(query, mode=mode, limit=limit, expand=expand),
            }
        )

    def _handle_graph_query(self, params: dict[str, list[str]]) -> None:
        query = _required(params, "q")
        mode = _one(params, "mode", "terms")
        limit = _limit(params)
        expand = _bool(params, "expand", True)
        result = self.store.related_graph(query, mode=mode, limit=limit, expand=expand)
        if _one(params, "format", "json") == "table":
            self._send_text(_relations_table(result["relations"]))
        else:
            self._send_json(result)

    def _send_json(self, body: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = body.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _one(params: dict[str, list[str]], name: str, default: str) -> str:
    values = params.get(name)
    return values[0] if values else default


def _required(params: dict[str, list[str]], name: str) -> str:
    value = _one(params, name, "").strip()
    if not value:
        raise ValueError(f"missing required query parameter: {name}")
    return value


def _limit(params: dict[str, list[str]]) -> int:
    raw = _one(params, "limit", "50")
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    return limit


def _bool(params: dict[str, list[str]], name: str, default: bool) -> bool:
    raw = _one(params, name, "1" if default else "0").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _relations_table(relations: list[dict]) -> str:
    lines = ["相关关系如下：", "triple_id\t关系"]
    lines.extend(f'{row["triple_id"]}\t{row["relation"]}' for row in relations)
    return "\n".join(lines) + "\n"
