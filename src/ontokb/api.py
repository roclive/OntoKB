"""Small JSON API for querying the SQLite knowledge graph."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .graph import GraphStore, normalize


def run_api(
    db_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    provider: str | None = None,
    model: str | None = None,
    fallback_model: str | None = None,
) -> None:
    """Serve the graph query API until interrupted."""

    graph = GraphStore(db_path)

    class Handler(GraphApiHandler):
        store = graph
        llm_provider = provider
        llm_model = model
        llm_fallback_model = fallback_model

    server = HTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        graph.close()


class GraphApiHandler(BaseHTTPRequestHandler):
    store: GraphStore
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_fallback_model: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                provider = (os.environ.get("ONTOKB_LLM_PROVIDER") or self.llm_provider or "openai").lower()
                key_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
                self._send_json({
                    "ok": True,
                    "chat": True,
                    "llm_provider": provider,
                    "llm_configured": bool(os.environ.get(key_name)),
                })
            elif parsed.path == "/api/entities/search":
                self._handle_entity_search(params)
            elif parsed.path == "/api/graph/query":
                self._handle_graph_query(params)
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/chat":
                self._handle_chat()
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": f"LLM request failed: {exc}"}, HTTPStatus.BAD_GATEWAY)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT.value)
        self._send_cors_headers()
        self.end_headers()

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

    def _handle_chat(self) -> None:
        body = self._read_json()
        question = str(body.get("question", "")).strip()
        if not question:
            raise ValueError("missing required field: question")
        if len(question) > 4000:
            raise ValueError("question must be at most 4000 characters")
        mode = str(body.get("mode", "terms")).strip().lower()
        if mode not in {"terms", "phrase"}:
            raise ValueError("mode must be 'terms' or 'phrase'")
        expand = body.get("expand", True)
        if not isinstance(expand, bool):
            raise ValueError("expand must be a boolean")
        top = body.get("top", 20)
        if isinstance(top, bool):
            raise ValueError("top must be an integer")
        try:
            top = int(top)
        except (TypeError, ValueError) as exc:
            raise ValueError("top must be an integer") from exc
        if top < 1 or top > 200:
            raise ValueError("top must be between 1 and 200")

        self._send_json(_chat_response(
            self.store,
            question,
            mode=mode,
            expand=expand,
            top=top,
            provider=self.llm_provider,
            model=self.llm_model,
            fallback_model=self.llm_fallback_model,
        ))

    def _read_json(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 1 or length > 64_000:
            raise ValueError("request body must be between 1 and 64000 bytes")
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        return body

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, body: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = body.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self._send_cors_headers()
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


def _chat_response(
    store: GraphStore,
    question: str,
    *,
    answerer=None,
    mode: str = "terms",
    expand: bool = True,
    top: int = 20,
    provider: str | None = None,
    model: str | None = None,
    fallback_model: str | None = None,
) -> dict:
    """Retrieve graph context first, then pass that exact payload to the LLM."""
    context = store.related_graph(question, mode=mode, limit=top, expand=expand)
    if expand and not context["matched_entities"]:
        mentioned = _entities_mentioned_in_question(store, question)
        if mentioned:
            context = store.related_graph(" ".join(mentioned), mode="terms", limit=top, expand=True)
            context["query"] = question
            context["mode"] = mode
            context["expand"] = expand
    context["top"] = top
    if answerer is None:
        from .llm import answer_graph_question

        answerer = answer_graph_question
    answer = answerer(
        question,
        context,
        provider=provider,
        model=model,
        fallback_model=fallback_model,
    )
    return {"answer": answer, "context": context}


def _entities_mentioned_in_question(store: GraphStore, question: str) -> list[str]:
    """Find known names embedded in unsegmented questions such as Chinese text."""
    normalized_question = normalize(question)
    mentioned = []
    for row in store.conn.execute("SELECT name, aliases FROM entities ORDER BY length(name) DESC"):
        names = [row["name"], *json.loads(row["aliases"])]
        if any(len(normalize(name)) >= 2 and normalize(name) in normalized_question for name in names):
            mentioned.append(row["name"])
    return mentioned[:20]
