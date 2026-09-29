"""Chat actions: collect a video before answering, otherwise search the graph."""
import json
import re
import threading
from urllib.parse import urlparse, parse_qs

from .models import ContentItem
from .pipeline import Pipeline, load_config

_ingest_lock = threading.Lock()


def video_url(text):
    for candidate in re.findall(r'https?://[^\s<>"\]\)]+', text):
        parsed = urlparse(candidate.rstrip('。，；'))
        host = (parsed.hostname or '').lower()
        vid = None
        if host in {'youtu.be', 'www.youtu.be'}:
            vid = parsed.path.strip('/')
        elif host in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
            if parsed.path == '/watch':
                vid = parse_qs(parsed.query).get('v', [''])[0]
            elif parsed.path.startswith(('/shorts/', '/live/', '/embed/')):
                vid = parsed.path.split('/')[2]
        if vid and re.fullmatch(r'[\w-]{11}', vid):
            return f'https://www.youtube.com/watch?v={vid}', vid
    return None


def respond(store, question, *, progress=lambda message: None, **options):
    from .api import _chat_response
    from .chat_history import validate_history
    history = validate_history(options.get('history', []))
    options['history'] = history
    if options.pop('agent', False):
        from .knowledge_agent import run_agent
        return run_agent(store, question, progress=progress, **options)
    options.pop('content_id', None)
    target = video_url(question)
    if not target:
        for message in reversed(history):
            if message['role'] != 'user':
                continue
            candidate = video_url(message['content'])
            if candidate:
                # A historical link may supply context, but must not ingest an
                # unprocessed URL just because it appeared in client history.
                if store.conn.execute("SELECT 1 FROM contents WHERE id=? AND status='processed'",
                                      (f'yt:{candidate[1]}',)).fetchone():
                    target = candidate
                break
    if not target:
        progress('正在检索知识库并生成回答…')
        return _chat_response(store, question, **options)
    if not _ingest_lock.acquire(blocking=False):
        raise ValueError('已有视频正在处理，请等待当前任务完成后重试。')
    try:
        return _respond_video(store, question, target, progress, options)
    finally:
        _ingest_lock.release()


def _respond_video(store, question, target, progress, options):
    from .sources.youtube import _read_cached_transcript, valid_transcript
    from .pipeline import ROOT, analysis_stamp
    from .llm import MAX_INPUT_CHARS
    url, vid = target
    config = load_config()
    db = store.conn.execute('PRAGMA database_list').fetchone()[2]
    config.setdefault('paths', {})['db'] = db
    for key in ('provider', 'model', 'fallback_model'):
        if options.get(key) is not None:
            config.setdefault('llm', {})[key] = options[key]
    pipe = Pipeline(config)
    item = ContentItem(id=f'yt:{vid}', kind='video', source='youtube', url=url)
    transcript_dir = ROOT / config.get('paths', {}).get('transcripts', 'data/transcripts') / 'youtube'
    try:
        existing = pipe.graph.conn.execute(
            "SELECT title, meta FROM contents WHERE id=? AND status='processed'", (item.id,)
        ).fetchone()
        if existing:
            item.raw_text = _read_cached_transcript(item, transcript_dir)
            item.title = existing['title']
        if not item.raw_text:
            progress('正在获取视频正文（字幕或本地音频转写）…')
            pipe.fetch(item, progress=progress)
        if not valid_transcript(item.raw_text):
            raise ValueError('未获取到有效视频文字，未入库。')
        old_meta = json.loads(existing['meta']) if existing else {}
        fresh = all(old_meta.get(key) == value for key, value in analysis_stamp(item.raw_text).items())
        if existing and fresh and not options.get('force_reanalyze'):
            progress('视频已在知识库，正在读取已有分析…')
            item.title = existing['title']
            meta = json.loads(existing['meta'])
            stats = {'content_id': item.id, 'reused': True, 'changed': False, 'operation': 'read'}
        else:
            if existing:
                progress('正文版本与旧分析不一致或已请求重做，正在重新分析并替换该来源的旧关系…')
            progress(f'已获取《{item.title}》的 {len(item.raw_text)} 字文字，Codex 正在分析并入库…')
            stats = pipe.ingest(item, replace_source=bool(existing))
            meta = json.loads(pipe.graph.conn.execute(
                'SELECT meta FROM contents WHERE id=?', (item.id,)
            ).fetchone()['meta'])
        progress('已入库，正在结合原文摘要回答你的问题…')
        context = pipe.graph.related_graph(item.title or item.id, limit=options.get('top', 20), expand=True)
        context['video_analysis'] = {'url': url, 'title': item.title, **meta}
        context['conversation_history'] = options.get('history', [])
        context['workflow_status'] = {
            'ingested': True, 'reused': bool(stats.get('reused')),
            'changed': bool(stats.get('changed')), 'operation': stats.get('operation'),
            'verified': bool(stats.get('verified')),
            'description': ('This turn regenerated the analysis and verified database and vault note writes.'
                            if stats.get('changed') else 'Read existing analysis only. No note or graph was updated this turn.'),
        }
        transcript = item.raw_text
        if transcript:
            context['source_transcript'] = transcript[:MAX_INPUT_CHARS]
            context['transcript_status'] = {
                'characters': len(transcript),
                'sent_characters': min(len(transcript), MAX_INPUT_CHARS),
                'truncated': len(transcript) > MAX_INPUT_CHARS,
            }
            progress(f'本次回答读取正文 {min(len(transcript), MAX_INPUT_CHARS)} / {len(transcript)} 字符。')
            context['transcript_note'] = '自动获取的字幕或语音转写，可能存在人名、术语和数字识别错误；不代表已人工核实。'
        from .llm import answer_graph_question
        if options.get('skip_answer'):
            return {'answer': '已重新分析并验证回写。' if stats.get('changed') else '已读取已有分析，本次未回写。',
                    'context': context, 'ingested': stats}
        try:
            answer = answer_graph_question(question, context, **{
                k: options.get(k) for k in ('provider', 'model', 'fallback_model')
            })
        except Exception as exc:
            answer = f"视频已成功入库，但本次问答失败：{exc}。可以重发链接重试。\n\n已有摘要：\n{meta.get('summary', '')}"
        prefix = '已更新并验证' if stats.get('changed') else '正在使用已有分析'
        return {'answer': f'{prefix}《{item.title}》。\n\n{answer}', 'context': context, 'ingested': stats}
    finally:
        pipe.graph.close()
