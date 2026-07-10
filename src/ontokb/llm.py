"""LLM processing: summary, key points, topic relevance, and entity/relation
extraction in one structured call."""

from __future__ import annotations

import json
import os

from .models import ContentItem, ExtractionResult, ProcessedContent
from .ontology import Ontology

DEFAULT_PROVIDER = "openai"
MODEL = os.environ.get("ONTOKB_MODEL", "gpt-5.5")
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
    provider: str | None = None,
    model: str | None = None,
    fallback_model: str | None = None,
) -> ProcessedContent:
    """Run the extraction call. `client` is injectable for testing."""
    text = item.raw_text[:MAX_INPUT_CHARS]
    user_prompt = (
        f"User interests: {json.dumps(interests, ensure_ascii=False)}\n\n"
        f"Ontology:\n{ontology.prompt_summary()}\n\n"
        f"Content [{item.kind} from {item.source}] title: {item.title}\n"
        f"URL: {item.url}\n\n---\n{text}"
    )
    provider = os.environ.get("ONTOKB_LLM_PROVIDER", provider or DEFAULT_PROVIDER).lower()
    model = os.environ.get("ONTOKB_MODEL", model or MODEL)
    fallback_model = os.environ.get("ONTOKB_FALLBACK_MODEL", fallback_model or FALLBACK_MODEL)

    if provider in {"openai", "chatgpt"}:
        return _process_with_openai(client, model, user_prompt).to_processed(item.id)
    if provider == "anthropic":
        return _process_with_anthropic(client, model, fallback_model, user_prompt).to_processed(item.id)
    raise ValueError(f"unsupported llm provider: {provider}")


def _process_with_openai(client, model: str, user_prompt: str) -> ExtractionResult:
    if client is None:
        from openai import OpenAI  # optional dependency: pip install ontokb[llm]

        client = OpenAI()

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=user_prompt,
        max_output_tokens=16000,
        text={
            "format": {
                "type": "json_schema",
                "name": "ontokb_extraction",
                "schema": _strict_schema(),
                "strict": True,
            },
            "verbosity": "medium",
        },
    )
    if getattr(response, "status", None) == "refused":
        raise RefusalError("model declined to process content")
    payload = _response_text(response)
    return ExtractionResult.model_validate_json(payload)


def _process_with_anthropic(
    client,
    model: str,
    fallback_model: str,
    user_prompt: str,
) -> ExtractionResult:
    if client is None:
        import anthropic  # optional dependency: pip install ontokb[llm]

        client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-06-01"],
        fallbacks=[{"model": fallback_model}],
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
        raise RefusalError("model declined to process content")

    payload = next(b.text for b in response.content if b.type == "text")
    return ExtractionResult.model_validate_json(payload)


def _response_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                return text
    raise RuntimeError("OpenAI response did not contain text output")


def _strict_schema() -> dict:
    """Pydantic JSON schema tightened for the structured-outputs validator:
    additionalProperties: false on every object. ExtractionResult contains no
    open dict fields, so this is safe."""
    schema = ExtractionResult.model_json_schema()

    def tighten(node: dict) -> None:
        if node.get("type") == "object":
            node["additionalProperties"] = False
            node["required"] = list(node.get("properties", {}).keys())
        # numeric/string constraints are not supported by structured outputs;
        # pydantic still enforces them client-side at validation time
        for bad in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                    "minLength", "maxLength", "default"):
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
