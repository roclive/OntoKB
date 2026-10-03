"""Source-scoped summaries and deterministic, evidence-preserving graph walks."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

from .models import ContentItem

ARTICLE_CATEGORY_CHOICES = ['历史类', 'AI类', '经济类', '科技', '时政', '实证类', '未分类']


def normalize_article_category(category: str) -> str:
    return '历史类' if category.strip() == '历史' else category.strip()


def _mentioned(text: str, name: str) -> bool:
    if not name.strip():
        return False
    if name.isascii():
        return re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text, re.I) is not None
    return name.casefold() in text.casefold()


def article_categories(title: str, meta: dict) -> list[str]:
    """Prefer curated categories; otherwise derive browsing tags from metadata."""
    explicit = meta.get('categories')
    if isinstance(explicit, list):
        labels = list(dict.fromkeys(normalize_article_category(s) for s in explicit if isinstance(s, str) and s.strip()))
        if labels:
            return labels
    text = ' '.join([title, str(meta.get('summary') or ''),
                     *[str(t) for t in meta.get('topics', [])]])
    rules = {
        '实证类': r'实证|随机对照|实验研究|数据分析|案例研究|调查研究',
        'AI类': r'(?<![a-zA-Z])AI(?![a-zA-Z])|人工智能|具身智能|机器人|大模型|机器学习|OpenAI',
        '历史类': r'历史|政改|改革开放|文革|辛亥|近代|朝代',
        '经济类': r'经济|金融|融资|投资|估值|泡沫|资本|通胀',
    }
    return [label for label, pattern in rules.items() if re.search(pattern, text, re.I)] or ['未分类']


def set_article_category(graph, body: dict) -> dict:
    """Persist the user's category without replacing other article metadata."""
    from .assistant import _ingest_lock

    content_id, category = body.get('content_id'), body.get('category')
    if not isinstance(content_id, str) or not content_id.strip():
        raise ValueError('请选择一篇文章。')
    if not isinstance(category, str):
        raise ValueError('请选择有效的文章分类。')
    category = normalize_article_category(category)
    if category not in ARTICLE_CATEGORY_CHOICES:
        raise ValueError('请选择有效的文章分类。')
    if not _ingest_lock.acquire(blocking=False):
        raise ValueError('知识库正在更新，请稍后重试。')
    try:
        with graph.conn:
            row = graph.conn.execute("SELECT title,meta FROM contents WHERE id=? AND status='processed'", (content_id,)).fetchone()
            if row is None:
                raise ValueError('文章不存在或尚未处理完成。')
            meta = json.loads(row['meta'])
            current = article_categories(row['title'] or '', meta)
            removed = category in current
            if category == '未分类':
                categories = ['未分类']
            elif removed:
                categories = [label for label in current if label not in {category, '未分类'}] or ['未分类']
            else:
                categories = [label for label in current if label != '未分类'] + [category]
            meta['categories'] = categories
            graph.conn.execute('UPDATE contents SET meta=? WHERE id=?',
                               (json.dumps(meta, ensure_ascii=False), content_id))
        return {'content_id': content_id, 'categories': categories, 'removed': removed}
    finally:
        _ingest_lock.release()


def reading_library(graph) -> list[dict]:
    entities = [dict(r) for r in graph.conn.execute("SELECT * FROM entities ORDER BY id")]
    lookup_names: dict[int, list[str]] = {}
    for alias in graph.conn.execute("SELECT entity_id,norm_alias FROM aliases"):
        lookup_names.setdefault(alias['entity_id'], []).append(alias['norm_alias'])
    triples = [dict(r) for r in graph.conn.execute(
        "SELECT t.*,s.name s,o.name t FROM triples t "
        "JOIN entities s ON s.id=t.subject_id JOIN entities o ON o.id=t.object_id ORDER BY t.id")]
    library = []
    for row in graph.conn.execute("SELECT * FROM contents WHERE status='processed' ORDER BY rowid DESC"):
        meta = json.loads(row['meta'])
        summary = str(meta.get('summary') or '')
        source_edges = [e for e in triples if e['source'] == row['id']]
        edge_ids = {e[k] for e in source_edges for k in ('subject_id', 'object_id')}
        scoped = [e for e in entities if row['id'] in json.loads(e['sources']) or e['id'] in edge_ids]
        docs = {e['name'] for e in scoped if row['id'] in json.loads(e['aliases'])
                or json.loads(e['properties']).get('url') == row['url'] and row['url']}
        candidates = [e for e in scoped if e['name'] not in docs and e['type'] != 'Claim']
        facts = [e for e in source_edges if e['s'] not in docs and e['t'] not in docs]
        text_steps = [s.strip() for s in re.split(r'(?<=[。！？!?])\s*|\n+', summary) if s.strip()]
        if not text_steps:
            text_steps = [str(p) for p in meta.get('key_points', []) if str(p).strip()]
        steps = []
        for sentence in text_steps:
            direct = [e['name'] for e in candidates
                      if any(_mentioned(sentence, n) for n in [e['name'], *json.loads(e['aliases']),
                                                               *lookup_names.get(e['id'], [])])]
            direct = list(dict.fromkeys(direct))
            # Walk only existing edges from THIS source. Never infer a new edge
            # from two names co-occurring in a summary.
            eligible = [e for e in facts if e['s'] in direct or e['t'] in direct]
            eligible = [e for e in eligible if e['predicate'] != 'makesClaim'
                        or e['s'] in direct and e['t'] in direct]
            eligible.sort(key=lambda e: (not(e['s'] in direct and e['t'] in direct), e['id']))
            edges = [{k: e[k] for k in ('id', 's', 't', 'predicate', 'source', 'evidence', 'confidence')}
                     for e in eligible[:8]]
            neighbors = list(dict.fromkeys(n for e in edges for n in (e['s'], e['t']) if n not in direct))
            steps.append({'text': sentence, 'entities': direct, 'neighbors': neighbors, 'edges': edges})
        library.append({'id': row['id'], 'title': row['title'] or row['id'], 'url': row['url'],
                        'kind': row['kind'], 'source': row['source'], 'summary': summary,
                        'categories': article_categories(row['title'] or '', meta),
                        'key_points': meta.get('key_points', []), 'steps': steps,
                        'entity_count': len(candidates), 'relation_count': len(facts),
                        'rejections': len(meta.get('extraction_rejections', []))})
    return library


def ingest_article(store, body: dict, *, provider=None, model=None, fallback_model=None) -> dict:
    """Summarize pasted text via the existing validated extraction pipeline."""
    from .pipeline import Pipeline, load_config
    from .assistant import _ingest_lock

    for field in ('title', 'text', 'url'):
        if field in body and not isinstance(body[field], str):
            raise ValueError(f'{field} must be a string')
    title = body.get('title', '').strip()
    raw = body.get('text', '').strip()
    url = body.get('url', '').strip()
    if not title or len(title) > 200:
        raise ValueError('请输入 1–200 字的文章标题。')
    if not 20 <= len(raw) <= 100_000:
        raise ValueError('正文长度需为 20–100000 字。')
    if url and (urlparse(url).scheme not in {'http', 'https'} or not urlparse(url).netloc):
        raise ValueError('来源链接必须是 http 或 https 地址。')
    if not _ingest_lock.acquire(blocking=False):
        raise ValueError('已有资料正在处理，请稍后再试。')
    pipe = None
    try:
        cid = 'article:' + hashlib.sha256((title + '\0' + url + '\0' + raw).encode()).hexdigest()[:24]
        if store.conn.execute("SELECT 1 FROM contents WHERE id=? AND status='processed'", (cid,)).fetchone():
            return {'content_id': cid, 'reused': True}
        # A global name key cannot represent two documents with one title.
        if store.get_entity(title):
            raise ValueError('标题已被现有对象使用，请添加日期或副标题以区分资料。')
        config = load_config()
        config.setdefault('paths', {})['db'] = store.conn.execute('PRAGMA database_list').fetchone()[2]
        for key, value in [('provider', provider), ('model', model), ('fallback_model', fallback_model)]:
            if value is not None:
                config.setdefault('llm', {})[key] = value
        pipe = Pipeline(config)
        return pipe.ingest(ContentItem(id=cid, title=title, raw_text=raw, kind='article', source='other', url=url))
    finally:
        if pipe is not None:
            pipe.graph.close()
        _ingest_lock.release()
