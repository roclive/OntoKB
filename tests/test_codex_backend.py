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


@pytest.mark.parametrize('allowed',[True,False])
def test_dynamic_tool_dispatch_and_failure_receipt(monkeypatch,allowed):
    events=[{'id':1,'result':{}},{'id':2,'result':{'thread':{'id':'t'}}},
            {'id':99,'method':'item/tool/call','params':{'tool':'kb_read' if allowed else 'shell','arguments':{'target':'doc'}}},
            {'id':3,'result':{}},
            {'method':'item/completed','params':{'item':{'type':'agentMessage','text':'done'}}},
            {'method':'turn/completed','params':{'turn':{'status':'completed'}}}]
    class Recording(io.StringIO):
        def close(self): self.recorded=self.getvalue();super().close()
    class Process:
        stdin=Recording()
        stdout=io.StringIO(''.join(json.dumps(e)+'\n' for e in events))
        def poll(self): return None
        def terminate(self): pass
        def wait(self,**kw): return 0
    proc=Process();calls=[]
    monkeypatch.setattr(codex_backend,'executable',lambda:'codex')
    monkeypatch.setattr(codex_backend.subprocess,'Popen',lambda *a,**kw:proc)
    def handler(name,args): calls.append((name,args));return {'verified':True}
    codex_backend.generate('instructions','prompt',dynamic_tools=[{'name':'kb_read'}],tool_handler=handler)
    messages=[json.loads(s) for s in proc.stdin.recorded.splitlines()]
    result=next(m['result'] for m in messages if m.get('id')==99)
    assert result['success'] is allowed
    assert bool(calls) is allowed
