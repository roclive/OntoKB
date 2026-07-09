"""LLM processing: summary, key points, topic relevance, and entity/relation
extraction in one structured call.

Uses the Anthropic API with claude-fable-5 and structured outputs. Per Fable 5
guidance, server-side refusal fallbacks to claude-opus-4-8 are enabled by
default, and stop_reason is checked before reading content.
"""

from __future__ import annotations

import json
import os

from .models import ContentItem, ExtractionResult, ProcessedContent
from .ontology import Ontology

MODEL = os.environ.get("ONTOKB_MODEL", "claude-fable-5")
FALLBACK_MODEL = os.environ.get("ONTOKB_FALLBACK_MODEL", "claude-opus-4-8")
MAX_INPUT_CHARS = 150_000  # ~1h video transcript fits comfortably

SYSTEM_PROMPT = """\
You are a knowledge extraction engine for a personal research knowledge base.
Given the full text of a tech video transcript or article, produce:
1. summary: a faithful summary in the same language as the source (5-10 sentences).
2. key_points: the concrete takeaways, one sentence each.
3. topics: the Topic entities this content is about (short noun phrases).
4. relevance: a 0-1 score for each of the user's interests provided below.
5. entities and triples that STRICTLY follow the ontology provided below.
   Only use listed classes and relations; respect domain/range. Include a short
   evidence quote for each triple. Do not invent facts not present in the text.
"""


class RefusalError(RuntimeError):
    pass


def process_content(
    item: ContentItem,
    ontology: Ontology,
    interests: list[str],
    client=None,
) -> ProcessedContent:
    """Run the extraction call. `client` is injectable for testing."""
    if client is None:
        import anthropic  # optional dependency: pip install ontokb[llm]

        client = anthropic.Anthropic()

    text = item.raw_text[:MAX_INPUT_CHARS]
    user_prompt = (
        f"User interests: {json.dumps(interests, ensure_ascii=False)}\n\n"
        f"Ontology:\n{ontology.prompt_summary()}\n\n"
        f"Content [{item.kind} from {item.source}] title: {item.title}\n"
        f"URL: {item.url}\n\n---\n{text}"
    )

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-06-01"],
        fallbacks=[{"model": FALLBACK_MODEL}],
        system=SYSTEM_PROMPT,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": _strict_schema(),
            }
        },
        messages=[{"role": "user", "content": user_prompt}],
    )

    if response.stop_reason == "refusal":
        raise RefusalError(f"model declined to process content {item.id}")

    payload = next(b.text for b in response.content if b.type == "text")
    result = ExtractionResult.model_validate_json(payload)
    return result.to_processed(item.id)


def _strict_schema() -> dict:
    """Pydantic JSON schema tightened for the structured-outputs validator:
    additionalProperties: false on every object. ExtractionResult contains no
    open dict fields, so this is safe."""
    schema = ExtractionResult.model_json_schema()

    def tighten(node: dict) -> None:
        if node.get("type") == "object":
            node["additionalProperties"] = False
        # numeric/string constraints are not supported by structured outputs;
        # pydantic still enforces them client-side at validation time
        for bad in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                    "minLength", "maxLength"):
            node.pop(bad, None)
        for child in node.get("properties", {}).values():
            if isinstance(child, dict):
                tighten(child)
        items = node.get("items")
        if isinstance(items, dict):
            tighten(items)
        for sub in node.get("$defs", {}).values():
            tighten(sub)

    tighten(schema)
    return schema
