from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ontokb.llm import process_content
from ontokb.models import ContentItem
from ontokb.ontology import Ontology

ROOT = Path(__file__).resolve().parents[1]


def test_process_content_defaults_to_openai_responses():
    payload = json.dumps(
        {
            "summary": "总结",
            "key_points": ["要点"],
            "topics": ["AI agents"],
            "relevance": [{"interest": "AI agents", "score": 0.8}],
            "entities": [],
            "triples": [],
        },
        ensure_ascii=False,
    )
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=payload, status="completed")

    client = SimpleNamespace(responses=FakeResponses())
    item = ContentItem(
        id="yt:abc",
        kind="video",
        source="youtube",
        url="https://youtu.be/abc",
        raw_text="hello",
    )

    processed = process_content(
        item,
        Ontology.load(ROOT / "ontology" / "core.yaml"),
        ["AI agents"],
        client=client,
    )

    assert processed.summary == "总结"
    assert processed.relevance == {"AI agents": 0.8}
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[0]["text"]["format"]["strict"] is True
    schema = calls[0]["text"]["format"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert "default" not in json.dumps(schema)
