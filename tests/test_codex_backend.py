import io
import json

import pytest

from ontokb import codex_backend
from ontokb.llm import answer_graph_question


def test_codex_qa_uses_graph_and_inherits_model(monkeypatch):
    seen = {}
    def generate(instructions, prompt, **kwargs):
        seen.update(kwargs, prompt=prompt)
        return "SQLite"
    monkeypatch.delenv("ONTOKB_MODEL", raising=False)
    monkeypatch.setenv("ONTOKB_LLM_PROVIDER", "codex")
    monkeypatch.setattr(codex_backend, "generate", generate)
    assert answer_graph_question("storage?", {"source": "SQLite"}) == "SQLite"
    assert seen["model"] is None
    assert "SQLite" in seen["prompt"]


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_protocol_events_and_cleanup(monkeypatch, status):
    events = [
        {"id": 1, "result": {}},
        {"id": 2, "result": {"thread": {"id": "t"}}},
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "answer"}}},
        {"id": 3, "result": {}},
        {"method": "turn/completed", "params": {"turn": {"status": status}}},
    ]
    class Process:
        stdin = io.StringIO()
        stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in events))
        stopped = False
        def poll(self): return None
        def terminate(self): self.stopped = True
        def wait(self, **kwargs): return 0
    proc = Process()
    monkeypatch.setattr(codex_backend, "executable", lambda: "codex")
    monkeypatch.setattr(codex_backend.subprocess, "Popen", lambda *a, **k: proc)
    if status == "failed":
        with pytest.raises(RuntimeError, match="turn failed"):
            codex_backend.generate("instructions", "prompt")
    else:
        assert codex_backend.generate("instructions", "prompt") == "answer"
    assert proc.stopped
    assert proc.stdin.closed and proc.stdout.closed


def test_missing_binary(monkeypatch):
    monkeypatch.setattr(codex_backend, "executable", lambda: None)
    with pytest.raises(RuntimeError, match="Codex CLI"):
        codex_backend.generate("instructions", "prompt")
