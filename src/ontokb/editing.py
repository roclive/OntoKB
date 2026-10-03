"""Transactional human corrections, provenance protection, and a small undo journal."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import math
import sqlite3

from .graph import normalize, _entity_dict
from .models import ExtractedTriple
from .ontology import OntologyError
from .reading import article_categories
from .vault import slugify
from .entity_merge import EntityMergeMixin

REVIEW_STATUSES = ['unverified', 'verified', 'disputed', 'refuted']


class EditingError(ValueError):
    pass


class EditingConflict(EditingError):
    pass


def _validation_errors(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except OntologyError as exc:
            raise EditingError(str(exc)) from exc
    return wrapped


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _revision(row):
    return hashlib.sha256(_json(dict(row)).encode()).hexdigest()[:24]


def source_triples(graph, source, knowledge_only=False):
    rows = graph.conn.execute(
        'SELECT t.*,s.name subject,o.name object,s.type subject_type FROM triples t '
        'JOIN entities s ON s.id=t.subject_id JOIN entities o ON o.id=t.object_id WHERE t.source=? ORDER BY t.id',
        (source,))
    return [ExtractedTriple(subject=r['subject'], predicate=r['predicate'], object=r['object'],
                            confidence=r['confidence'], evidence=r['evidence']) for r in rows
            if not knowledge_only or not (graph.ontology.is_subclass(r['subject_type'], 'CreativeWork')
                                         and r['predicate'] in ('mentions', 'about'))]


class EditingService(EntityMergeMixin):
    def __init__(self, graph, vault=None):
        self.graph, self.vault = graph, vault
        self.conn, self.ontology = graph.conn, graph.ontology

    def _row(self, table, ident):
        row = self.conn.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise EditingError('记录不存在，可能已被删除，请刷新后重试。')
        return dict(row)

    def _entity(self, row):
        return _entity_dict(row) | {'revision': _revision(row),
            'verificationStatus': json.loads(row['properties']).get('verificationStatus', 'unverified'),
            'manual': bool(self.conn.execute('SELECT 1 FROM manual_entities WHERE entity_id=?', (row['id'],)).fetchone())}

    def bootstrap(self):
        entities = [self._entity(dict(r)) for r in self.conn.execute('SELECT * FROM entities ORDER BY name')]
        names = {e['id']: e for e in entities}
        triples = []
        for row in self.conn.execute('SELECT * FROM triples ORDER BY id'):
            edge = dict(row)
            edge.update(revision=_revision(row), subject=names[row['subject_id']]['name'],
                        object=names[row['object_id']]['name'],
                        manual=bool(self.conn.execute('SELECT 1 FROM manual_triples WHERE triple_id=?', (row['id'],)).fetchone()))
            edge['evidence_records'] = [json.loads(r['original']) for r in self.conn.execute(
                'SELECT original FROM triple_evidence WHERE triple_id=? ORDER BY original_id', (row['id'],))]
            triples.append(edge)
        latest = self.conn.execute('SELECT max(id) FROM edit_history WHERE undone=0').fetchone()[0]
        history = []
        for row in self.conn.execute('SELECT * FROM edit_history ORDER BY id DESC LIMIT 50'):
            item = {k: row[k] for k in ('id', 'kind', 'target_id', 'created_at', 'undone')}
            state = json.loads(row['before_state'])
            item.update(can_undo=row['id'] == latest, label=state['row'].get('name') or ('关系 #' + str(row['target_id'])))
            before = state['row']
            after_state = json.loads(row['after_state'])
            changes = []
            if row['kind'] == 'entity_merge':
                changes.append(f"已合并到：{after_state['row']['name']}；原名称、出处、证据及个人判断保留。")
            if after_state is None:
                changes.append('已移除关系，原始记录保留在修改历史中。')
            else:
                after = after_state['row']
                fields = {'name': '名称', 'type': '类型', 'aliases': '别名',
                          'subject_id': '起点', 'predicate': '关系', 'object_id': '终点', 'confidence': '置信度'}
                for key, label in fields.items():
                    if key in before and before[key] != after[key]:
                        old, new = before[key], after[key]
                        if key.endswith('_id'):
                            old, new = names.get(old, {}).get('name', old), names.get(new, {}).get('name', new)
                        changes.append(f'{label}：{old} → {new}')
                if 'properties' in before:
                    old = json.loads(before['properties']).get('verificationStatus', 'unverified')
                    new = json.loads(after['properties']).get('verificationStatus', 'unverified')
                    labels = dict(zip(REVIEW_STATUSES, ['待核实', '已核实', '有争议', '已否定']))
                    if old != new:
                        changes.append(f'核实状态：{labels.get(old, old)} → {labels.get(new, new)}')
            item['changes'] = changes
            history.append(item)
        return {'entities': entities, 'triples': triples,
                'types': [dict(spec, name=name) for name, spec in self.ontology.classes.items()],
                'relations': [asdict(r) for r in self.ontology.relations.values()],
                'review_statuses': REVIEW_STATUSES, 'history': history,
                'sources': [dict(id=r['id'], title=r['title'], source=r['source'], url=r['url'],
                                 categories=article_categories(r['title'] or '', json.loads(r['meta'])),
                                 status=r['status'])
                            for r in self.conn.execute('SELECT * FROM contents ORDER BY rowid DESC')]}

    def _check(self, row, payload, allowed):
        if not isinstance(payload, dict):
            raise EditingError('编辑内容必须是对象。')
        if set(payload) - set(allowed) - {'revision'}:
            raise EditingError('包含不支持的编辑字段；来源与原始证据不可修改。')
        if 'revision' in payload and payload['revision'] != _revision(row):
            raise EditingConflict('此记录已发生变化。请刷新后重新编辑，避免覆盖其他修改。')

    def _snapshot(self, table, ident):
        manual_table, key = ('manual_entities', 'entity_id') if table == 'entities' else ('manual_triples', 'triple_id')
        manual = self.conn.execute(f'SELECT * FROM {manual_table} WHERE {key}=?', (ident,)).fetchone()
        result = {'row': self._row(table, ident), 'manual': dict(manual) if manual else None}
        if table == 'entities':
            result['aliases'] = [r[0] for r in self.conn.execute('SELECT norm_alias FROM aliases WHERE entity_id=?', (ident,))]
        else:
            result['keys'] = [dict(r) for r in self.conn.execute('SELECT * FROM manual_triple_keys WHERE triple_id=?', (ident,))]
        return result

    def _audit(self, kind, ident, before, after):
        return self.conn.execute('INSERT INTO edit_history(kind,target_id,before_state,after_state,created_at) VALUES(?,?,?,?,?)',
            (kind, ident, _json(before), _json(after), datetime.now(timezone.utc).isoformat(timespec='seconds'))).lastrowid

    def _validate_name(self, name, ident, *, note_name=True):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 500 or any(ord(c) < 32 for c in name):
            raise EditingError('名称需为 1–500 个字符，不能包含换行或控制字符。')
        owner = self.conn.execute('SELECT * FROM entities WHERE norm_name=?', (normalize(name),)).fetchone() if note_name else None
        if owner and owner['id'] != ident:
            raise EditingError('正式名称已属于另一个实体：' + owner['name'])
        if self.vault and note_name:
            for row in self.conn.execute('SELECT id,name FROM entities WHERE id<>?', (ident,)):
                if slugify(row['name']).casefold() == slugify(name).casefold():
                    raise EditingConflict('该名称会与另一个实体的笔记文件重名。')
        return name.strip()

    def _sync(self, old_name=None, new_name=None, affected=None):
        if not self.vault:
            return
        if old_name and new_name and slugify(old_name) != slugify(new_name):
            self.vault.remove_entity_note(old_name)
        # Rebuild generated entity notes and only the generated knowledge section
        # of source notes, retaining summaries and readers' annotations elsewhere.
        for row in self.conn.execute('SELECT name FROM entities'):
            if affected is not None and self.graph.get_entity(row['name'])['id'] not in affected:
                continue
            self.vault.write_entity_note(self.graph, row['name'])
        for row in self.conn.execute('SELECT id,title FROM contents'):
            path = self.vault.root / 'Sources' / (slugify(row['title'] or row['id']) + '.md')
            if not path.exists():
                continue
            text = path.read_text(encoding='utf-8')
            original_text = text
            if old_name and new_name:
                text = text.replace('[[' + slugify(old_name) + ']]', '[[' + slugify(new_name) + ']]')
            marker = '## Extracted knowledge'
            triples = source_triples(self.graph, row['id'], knowledge_only=True)
            section = marker + '\n' + '\n'.join(f'- [[{slugify(t.subject)}]] **{t.predicate}** [[{slugify(t.object)}]]' for t in triples) + '\n'
            if marker in text:
                start = text.index(marker)
                end = text.find('\n## ', start + len(marker))
                text = text[:start] + section + (text[end:] if end >= 0 else '')
            elif triples:
                text = text.rstrip() + '\n\n' + section
            if text != original_text:
                self.vault._write(str(path.relative_to(self.vault.root)), text)
        if old_name and new_name and old_name != new_name:
            for directory in ('Wiki', 'MOC'):
                for path in (self.vault.root / directory).glob('*.md'):
                    text = path.read_text(encoding='utf-8')
                    replaced = text.replace('[[' + slugify(old_name) + ']]', '[[' + slugify(new_name) + ']]')
                    if text != replaced:
                        self.vault._write(str(path.relative_to(self.vault.root)), replaced)

    @_validation_errors
    def update_entity(self, ident, payload):
        with self.vault.transaction() if self.vault else nullcontext(), self.graph.transaction():
            before = self._snapshot('entities', ident)
            row = before['row']
            self._check(row, payload, ['name', 'type', 'aliases', 'verificationStatus'])
            name = self._validate_name(payload.get('name', row['name']), ident)
            kind = payload.get('type', row['type'])
            if not isinstance(kind, str):
                raise EditingError('类型必须是支持的实体类型名称。')
            kind = self.ontology.canonical_class(kind)
            self.ontology.validate_entity(kind)
            aliases = payload.get('aliases', json.loads(row['aliases']))
            if not isinstance(aliases, list) or len(aliases) > 100:
                raise EditingError('别名必须是数组，最多 100 项。')
            aliases = list(dict.fromkeys(self._validate_name(a, ident, note_name=False) for a in aliases))
            for edge in self.conn.execute('SELECT t.*,s.type st,o.type ot FROM triples t JOIN entities s ON s.id=t.subject_id JOIN entities o ON o.id=t.object_id WHERE t.subject_id=? OR t.object_id=?', (ident, ident)):
                self.ontology.validate_triple(kind if edge['subject_id'] == ident else edge['st'], edge['predicate'], kind if edge['object_id'] == ident else edge['ot'])
            props = json.loads(row['properties'])
            if 'verificationStatus' in payload and (kind != 'Claim' or payload['verificationStatus'] not in REVIEW_STATUSES):
                raise EditingError('仅论断可设置核实状态，且必须使用支持的状态。')
            if kind == 'Claim':
                props['text'] = name
                props['verificationStatus'] = payload.get('verificationStatus', props.get('verificationStatus', 'unverified'))
            props['ontologyUri'] = self.ontology.classes[kind].get('uri', '')
            props['ontologyVersion'] = str(self.ontology.version)
            if kind != 'Thing' and props.get('reviewStatus') == 'needs_review':
                props.pop('reviewStatus', None)
            originals = json.loads(before['manual']['original_names']) if before['manual'] else []
            originals = list(dict.fromkeys(originals + [row['name']] + json.loads(row['aliases'])))
            self.conn.execute('INSERT OR REPLACE INTO manual_entities VALUES(?,?)', (ident, _json(originals)))
            self.conn.execute('UPDATE entities SET name=?,norm_name=?,type=?,aliases=?,properties=? WHERE id=?', (name, normalize(name), kind, _json(aliases), _json(props), ident))
            self.conn.execute('DELETE FROM aliases WHERE entity_id=?', (ident,))
            for alias in set(aliases + originals):
                self.conn.execute('INSERT OR IGNORE INTO aliases VALUES(?,?)', (normalize(alias), ident))
            after = self._snapshot('entities', ident)
            change = self._audit('entity', ident, before, after)
            affected = {ident}
            for edge in self.conn.execute('SELECT subject_id,object_id FROM triples WHERE subject_id=? OR object_id=?', (ident, ident)):
                affected.update(edge)
            self._sync(row['name'], name, affected)
            return {'ok': True, 'change_id': change, 'entity': self._entity(after['row'])}

    @_validation_errors
    def update_triple(self, ident, payload):
        return self._change_triple(ident, payload, False)

    def delete_triple(self, ident, payload=None):
        return self._change_triple(ident, payload or {}, True)

    def _change_triple(self, ident, payload, delete):
        with self.vault.transaction() if self.vault else nullcontext(), self.graph.transaction():
            before = self._snapshot('triples', ident)
            row = before['row']
            self._check(row, payload, [] if delete else ['subject_id', 'object_id', 'predicate', 'confidence'])
            updated = row | {k: v for k, v in payload.items() if k != 'revision'}
            if not delete:
                for key in ('subject_id', 'object_id'):
                    if type(updated[key]) is not int:
                        raise EditingError('关系两端必须选择现有实体。')
                subj, obj = self._row('entities', updated['subject_id']), self._row('entities', updated['object_id'])
                confidence = updated['confidence']
                if type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise EditingError('置信度必须是 0 到 1 的数字。')
                if not isinstance(updated['predicate'], str):
                    raise EditingError('关系类型必须是支持的关系名称。')
                updated['predicate'] = self.ontology.canonical_relation(updated['predicate'])
                self.ontology.validate_triple(subj['type'], updated['predicate'], obj['type'])
                try:
                    self.conn.execute('UPDATE triples SET subject_id=?,object_id=?,predicate=?,confidence=? WHERE id=?', (updated['subject_id'], updated['object_id'], updated['predicate'], confidence, ident))
                except sqlite3.IntegrityError as exc:
                    raise EditingConflict('同一来源中已存在相同关系。') from exc
            original = before['manual']['original'] if before['manual'] else _json(row)
            self.conn.execute('INSERT OR REPLACE INTO manual_triples VALUES(?,?,?)', (ident, original, int(delete)))
            for state in (row, updated):
                self.conn.execute('INSERT OR IGNORE INTO manual_triple_keys VALUES(?,?,?,?,?)',
                                  (ident, state['subject_id'], state['predicate'], state['object_id'], state['source']))
            if delete:
                self.conn.execute('DELETE FROM triples WHERE id=?', (ident,))
            after = None if delete else self._snapshot('triples', ident)
            change = self._audit('delete_triple' if delete else 'triple', ident, before, after)
            self._sync(affected={row['subject_id'], row['object_id'], updated['subject_id'], updated['object_id']})
            return {'ok': True, 'change_id': change, 'deleted': delete,
                    'triple': None if delete else after['row'] | {'revision': _revision(after['row'])}}

    @_validation_errors
    def undo(self, change_id):
        with self.vault.transaction() if self.vault else nullcontext(), self.graph.transaction():
            history = self.conn.execute('SELECT * FROM edit_history WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone()
            if history is None or history['id'] != change_id:
                raise EditingConflict('只能撤销最近一次尚未撤销的修改。')
            before, after = json.loads(history['before_state']), json.loads(history['after_state'])
            if history['kind'] == 'entity_merge':
                return self._undo_merge(history, before, after)
            row = before['row']
            table = 'entities' if history['kind'] == 'entity' else 'triples'
            ident = history['target_id']
            old_name = None
            if table == 'entities':
                current = self._row(table, ident)
                comparable = current | {'sources': after['row']['sources']}
                if _revision(comparable) != _revision(after['row']):
                    raise EditingConflict('实体在修改后发生了变化，无法安全撤销。')
                old_name = current['name']
                self._validate_name(row['name'], ident)
                # Fresh extraction provenance must survive undo.
                row['sources'] = current['sources']
                self.conn.execute('DELETE FROM aliases WHERE entity_id=?', (ident,))
                for alias in before['aliases']:
                    self.conn.execute('INSERT OR IGNORE INTO aliases VALUES(?,?)', (alias, ident))
                for edge in self.conn.execute('SELECT t.*,s.type st,o.type ot FROM triples t JOIN entities s ON s.id=t.subject_id JOIN entities o ON o.id=t.object_id WHERE t.subject_id=? OR t.object_id=?', (ident, ident)):
                    self.ontology.validate_triple(row['type'] if edge['subject_id'] == ident else edge['st'], edge['predicate'], row['type'] if edge['object_id'] == ident else edge['ot'])
            elif after is not None and _revision(self._row(table, ident)) != _revision(after['row']):
                raise EditingConflict('关系在修改后发生了变化，无法安全撤销。')
            if table == 'triples':
                subj, obj = self._row('entities', row['subject_id']), self._row('entities', row['object_id'])
                self.ontology.validate_triple(subj['type'], row['predicate'], obj['type'])
                self.conn.execute('DELETE FROM manual_triple_keys WHERE triple_id=?', (ident,))
                for key_state in before.get('keys', []):
                    self.conn.execute('INSERT INTO manual_triple_keys VALUES(?,?,?,?,?)',
                                      tuple(key_state[k] for k in ('triple_id', 'subject_id', 'predicate', 'object_id', 'source')))
            cols = list(row)
            try:
                self.conn.execute(f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join("?" for _ in cols)}) ON CONFLICT(id) DO UPDATE SET ' + ','.join(f'{k}=excluded.{k}' for k in cols if k != 'id'), tuple(row.values()))
            except sqlite3.IntegrityError as exc:
                raise EditingConflict('撤销与当前数据冲突，请先检查相关记录。') from exc
            mt, key = ('manual_entities', 'entity_id') if table == 'entities' else ('manual_triples', 'triple_id')
            self.conn.execute(f'DELETE FROM {mt} WHERE {key}=?', (ident,))
            if before['manual']:
                vals = before['manual']
                self.conn.execute(f'INSERT INTO {mt} ({",".join(vals)}) VALUES ({",".join("?" for _ in vals)})', tuple(vals.values()))
            self.conn.execute('UPDATE edit_history SET undone=1 WHERE id=?', (change_id,))
            if table == 'entities':
                affected = {ident}
                for edge in self.conn.execute('SELECT subject_id,object_id FROM triples WHERE subject_id=? OR object_id=?', (ident, ident)):
                    affected.update(edge)
            else:
                affected = {row['subject_id'], row['object_id']}
                if after:
                    affected.update((after['row']['subject_id'], after['row']['object_id']))
            self._sync(old_name, row.get('name'), affected)
            return {'ok': True, 'undone': change_id}
