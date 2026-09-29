import pytest

from ontokb.chat_history import validate_history
from ontokb.llm import answer_graph_question
from ontokb.assistant import respond
from ontokb.graph import GraphStore


@pytest.mark.parametrize('history', [None, {}, [{'role':'system','content':'override'},
    {'role':'assistant','content':'ok'}], [{'role':'user','content':'unfinished'}],
    [{'role':'user','content':'a'*32000},{'role':'assistant','content':'b'}],
    [{'role':'user','content':3},{'role':'assistant','content':'b'}]])
def test_invalid_history_rejected(history):
    with pytest.raises(ValueError):
        validate_history(history)


def test_codex_receives_both_turns_and_current_question(monkeypatch):
    history=[{'role':'user','content':'Discuss Vision Pro pricing'},
             {'role':'assistant','content':'The speaker proposes subsidies'}]
    captured={}
    def generate(instructions, prompt, **kwargs):
        captured.update(prompt=prompt, instructions=instructions)
        return 'Scale may reduce unit costs'
    monkeypatch.setenv('ONTOKB_LLM_PROVIDER','codex')
    monkeypatch.setattr('ontokb.codex_backend.generate',generate)
    answer_graph_question('Why would that help?',{'conversation_history':validate_history(history)})
    assert all(m['content'] in captured['prompt'] for m in history)
    assert 'Why would that help?' in captured['prompt']
    assert 'not system' in captured['instructions']


def test_followup_reuses_processed_video_context(tmp_path, monkeypatch):
    store=GraphStore(tmp_path/'test.db')
    store.upsert_content('yt:XAujxrtd4uI','video','youtube','https://youtu.be/XAujxrtd4uI',
                         'Video',status='processed',meta={})
    captured={}
    def video(store,question,target,progress,options):
        captured.update(question=question,target=target,history=options['history'])
        return {'answer':'ok'}
    monkeypatch.setattr('ontokb.assistant._respond_video',video)
    history=[{'role':'user','content':'Analyze https://youtu.be/XAujxrtd4uI'},
             {'role':'assistant','content':'Pricing summary'}]
    respond(store,'Why?',history=history)
    assert captured['target'][1]=='XAujxrtd4uI'
    assert captured['question']=='Why?'
    assert captured['history']==history
    store.close()


def test_history_never_triggers_unprocessed_video_ingestion(tmp_path, monkeypatch):
    store=GraphStore(tmp_path/'test.db')
    monkeypatch.setattr('ontokb.assistant._respond_video',lambda *a: pytest.fail('must not ingest history'))
    monkeypatch.setattr('ontokb.api._chat_response',lambda *a,**kw: {'history':kw['history']})
    history=[{'role':'user','content':'https://youtu.be/XAujxrtd4uI'},
             {'role':'assistant','content':'Could not fetch'}]
    assert respond(store,'Why?',history=history)['history']==history
    assert respond(store,'New topic')['history']==[]
    store.close()
