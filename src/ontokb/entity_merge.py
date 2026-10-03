"""Explicit, previewed identity merges with lossless evidence and conservative undo."""
from contextlib import nullcontext
import base64
import hashlib
import json

from .graph import normalize

TABLES = ('entities', 'aliases', 'triples', 'manual_entities', 'manual_triples',
          'manual_triple_keys', 'triple_evidence', 'merged_entities', 'memory_redirects')


class EntityMergeMixin:
    def _merge_state(self):
        # A conservative fingerprint also detects new extraction and judgments.
        tables = {t: [dict(r) for r in self.conn.execute(f'SELECT * FROM {t} ORDER BY rowid')]
                  for t in TABLES}
        observed = {t: [dict(r) for r in self.conn.execute(f'SELECT * FROM {t} ORDER BY rowid')]
                    for t in ('personal_memory', 'memory_history')}
        return dict(tables=tables, memory=observed)

    def _merge_token(self, source_id, target_id, state):
        from .editing import _json
        return hashlib.sha256(_json([source_id, target_id, state]).encode()).hexdigest()

    def _merge_pair(self, source_id, payload, *, execution=False):
        from .editing import EditingError
        allowed = {'target_id', 'preview_token'} if execution else {'target_id'}
        if not isinstance(payload, dict) or set(payload) - allowed or type(payload.get('target_id')) is not int:
            raise EditingError('请选择要保留的实体。')
        if type(source_id) is not int or source_id == payload['target_id']:
            raise EditingError('请选择两个不同的实体。')
        return self._row('entities', source_id), self._row('entities', payload['target_id'])

    def preview_merge(self, source_id, payload):
        source, target = self._merge_pair(source_id, payload)
        reasons, warnings = [], []
        document_types = ('CreativeWork', 'MediaObject', 'VideoObject', 'Article', 'Book')
        if source['type'] in document_types or target['type'] in document_types:
            reasons.append('资料文档节点不能合并，请保留独立来源。')
        if source['type'] != target['type']:
            reasons.append('两个实体类型不同，请先确认身份并统一类型。')
        source_props, target_props = json.loads(source['properties']), json.loads(target['properties'])
        conflicts = [dict(field=k, source=v, target=target_props[k]) for k, v in source_props.items()
                     if k in target_props and v != target_props[k] and k not in ('text',)]
        if conflicts:
            warnings.append('不同属性保留在合并记录中；当前实体采用保留实体的属性。')
        if source['type'] == 'Claim':
            warnings.append('请核对论断的时间、条件与证据，确认表达的是同一论断。核实状态保留双方原始记录；不同状态会标记为有争议。')
        aliases = list(dict.fromkeys(json.loads(target['aliases']) + [source['name']] + json.loads(source['aliases'])))
        aliases = [a for a in aliases if normalize(a) != target['norm_name']]
        edges = [dict(r) for r in self.conn.execute('SELECT * FROM triples WHERE subject_id IN (?,?) OR object_id IN (?,?) ORDER BY id',
                                                  (source_id, target['id'], source_id, target['id']))]
        keys, self_relations = set(), 0
        for edge in edges:
            sid = target['id'] if edge['subject_id'] == source_id else edge['subject_id']
            oid = target['id'] if edge['object_id'] == source_id else edge['object_id']
            keys.add((sid, edge['predicate'], oid, edge['source']))
            self_relations += sid == oid
            try:
                self.ontology.validate_triple(self._row('entities', sid)['type'], edge['predicate'], self._row('entities', oid)['type'])
            except ValueError as exc:
                reasons.append('合并后的关系类型不合法：' + str(exc))
        if self_relations:
            warnings.append('合并后存在指向自身的关系，将保留供人工检查。')
        memory_count = 0
        edge_ids = {e['id'] for e in edges}
        for row in self.conn.execute('SELECT p.snapshot,r.target_id associated_id FROM personal_memory p LEFT JOIN memory_redirects r ON r.key=p.key'):
            snap = json.loads(row['snapshot'])
            relevant = edge_ids if snap.get('kind') == 'triple' else {source_id, target['id']}
            if snap.get('target_id') in relevant or row['associated_id'] in relevant:
                memory_count += 1
        if memory_count:
            warnings.append('原有个人判断和笔记完整保留为历史快照；合并改变的记录需要重新审核，不会自动继承认可。')
        return dict(source=self._entity(source), target=self._entity(target), can_merge=not reasons,
                    blocked_reasons=list(dict.fromkeys(reasons)), warnings=warnings, aliases=aliases,
                    sources=list(dict.fromkeys(json.loads(target['sources']) + json.loads(source['sources']))),
                    property_conflicts=conflicts,
                    impact=dict(relations_before=len(edges), relations_after=len(keys), duplicate_relations=len(edges)-len(keys),
                                self_relations=self_relations, memory_records=memory_count),
                    preview_token=self._merge_token(source_id, target['id'], self._merge_state()))

    def _vault_snapshot(self):
        return {str(p.relative_to(self.vault.root)): base64.b64encode(p.read_bytes()).decode()
                for p in self.vault.root.rglob('*.md')} if self.vault else {}

    def merge_entities(self, source_id, payload):
        from .editing import EditingError, EditingConflict, _json
        with self.vault.transaction() if self.vault else nullcontext(), self.graph.transaction():
            source, target = self._merge_pair(source_id, payload, execution=True)
            state = self._merge_state()
            if payload.get('preview_token') != self._merge_token(source_id, target['id'], state):
                raise EditingConflict('预览后数据或个人判断已变化，请重新预览再合并。')
            preview = self.preview_merge(source_id, {'target_id': target['id']})
            if not preview['can_merge']:
                raise EditingError('；'.join(preview['blocked_reasons']))
            before = dict(row=source, merge_state=state, vault_notes=self._vault_snapshot())
            tid = target['id']
            all_edges = [dict(r) for r in self.conn.execute('SELECT * FROM triples ORDER BY id')]
            affected = [r for r in all_edges if source_id in (r['subject_id'], r['object_id']) or tid in (r['subject_id'], r['object_id'])]
            edge_map = {}
            groups = {}
            for row in affected:
                changed = row | dict(subject_id=tid if row['subject_id'] == source_id else row['subject_id'],
                                     object_id=tid if row['object_id'] == source_id else row['object_id'])
                key = tuple(changed[k] for k in ('subject_id', 'predicate', 'object_id', 'source'))
                groups.setdefault(key, []).append((row, changed))
            for row in affected:
                self.conn.execute('DELETE FROM triples WHERE id=?', (row['id'],))
            for group in groups.values():
                # Prefer a pre-existing canonical relation, preserving its id.
                group.sort(key=lambda pair: (source_id in (pair[0]['subject_id'], pair[0]['object_id']), pair[0]['id']))
                primary, changed = group[0]
                cols = list(changed)
                self.conn.execute(f'INSERT INTO triples ({",".join(cols)}) VALUES ({",".join("?" for _ in cols)})', tuple(changed.values()))
                for original, mapped in group:
                    edge_map[original['id']] = primary['id']
                    self.conn.execute('INSERT OR IGNORE INTO triple_evidence VALUES(?,?,?)', (primary['id'], original['id'], _json(original)))
                    for archived in self.conn.execute('SELECT * FROM triple_evidence WHERE triple_id=?', (original['id'],)).fetchall():
                        self.conn.execute('INSERT OR IGNORE INTO triple_evidence VALUES(?,?,?)', (primary['id'], archived['original_id'], archived['original']))
                    if original['id'] != primary['id']:
                        self.conn.execute('DELETE FROM triple_evidence WHERE triple_id=?', (original['id'],))
                    for item in (original, mapped):
                        self.conn.execute('INSERT OR IGNORE INTO manual_triple_keys VALUES(?,?,?,?,?)',
                                          (primary['id'], item['subject_id'], item['predicate'], item['object_id'], item['source']))
                self.conn.execute('INSERT OR IGNORE INTO manual_triples VALUES(?,?,0)', (primary['id'], _json(primary)))
            # Deleted human corrections remain tombstones after endpoint remapping.
            for row in self.conn.execute('SELECT * FROM manual_triple_keys WHERE subject_id=? OR object_id=?', (source_id, source_id)).fetchall():
                self.conn.execute('INSERT OR IGNORE INTO manual_triple_keys VALUES(?,?,?,?,?)',
                                  (row['triple_id'], tid if row['subject_id']==source_id else row['subject_id'], row['predicate'],
                                   tid if row['object_id']==source_id else row['object_id'], row['source']))
            originals = [source['name'], target['name'], *json.loads(source['aliases']), *json.loads(target['aliases'])]
            for row in self.conn.execute('SELECT original_names FROM manual_entities WHERE entity_id IN (?,?)', (source_id, tid)):
                originals.extend(json.loads(row['original_names']))
            self.conn.execute('DELETE FROM aliases WHERE entity_id IN (?,?)', (source_id, tid))
            alias_norms = [r['norm_alias'] for r in state['tables']['aliases'] if r['entity_id'] in (source_id, tid)]
            for alias in set(alias_norms + [normalize(a) for a in originals + preview['aliases']]):
                self.conn.execute('INSERT INTO aliases VALUES(?,?)', (alias, tid))
            props = json.loads(source['properties']) | json.loads(target['properties'])
            if target['type'] == 'Claim':
                props['text'] = target['name']
                if json.loads(source['properties']).get('verificationStatus','unverified') != json.loads(target['properties']).get('verificationStatus','unverified'):
                    props['verificationStatus'] = 'disputed'
            self.conn.execute('UPDATE entities SET aliases=?,sources=?,properties=? WHERE id=?',
                              (_json(preview['aliases']), _json(preview['sources']), _json(props), tid))
            self.conn.execute('INSERT OR REPLACE INTO manual_entities VALUES(?,?)', (tid, _json(list(dict.fromkeys(originals)))))
            self.conn.execute('INSERT INTO merged_entities VALUES(?,?,?)', (source_id, tid, _json(source)))
            self.conn.execute('UPDATE merged_entities SET target_id=? WHERE target_id=?', (tid, source_id))
            self.conn.execute('DELETE FROM manual_entities WHERE entity_id=?', (source_id,))
            self.conn.execute('DELETE FROM entities WHERE id=?', (source_id,))
            for row in self.conn.execute('SELECT key,snapshot FROM personal_memory'):
                snap = json.loads(row['snapshot'])
                kind, ident = snap.get('kind'), snap.get('target_id')
                mapped = edge_map.get(ident) if kind == 'triple' else tid if ident in (source_id, tid) else None
                if mapped is not None:
                    self.conn.execute('INSERT OR REPLACE INTO memory_redirects VALUES(?,?,?)', (row['key'], kind, mapped))
            self.conn.execute("UPDATE memory_redirects SET target_id=? WHERE target_id=? AND target_kind IN ('entity','claim')", (tid,source_id))
            # Keep earlier archived judgments associated through repeated merges.
            for old_id, mapped_id in edge_map.items():
                self.conn.execute("UPDATE memory_redirects SET target_id=? WHERE target_id=? AND target_kind='triple'", (mapped_id, old_id))
            affected_entities = {tid}
            for edge in affected:
                affected_entities.update(tid if ident == source_id else ident
                                         for ident in (edge['subject_id'], edge['object_id']))
            self._sync(source['name'], target['name'], affected=affected_entities)
            after = dict(row=self._row('entities', tid), merge_state=self._merge_state(), vault_notes=self._vault_snapshot())
            change = self._audit('entity_merge', tid, before, after)
            return dict(ok=True, change_id=change, entity=self._entity(after['row']))

    def _undo_merge(self, history, before, after):
        from .editing import EditingConflict, _json
        if _json(self._merge_state()) != _json(after['merge_state']) or self._vault_snapshot() != after['vault_notes']:
            raise EditingConflict('合并后知识、个人判断或笔记发生了变化，无法安全撤销。')
        for table in reversed(TABLES):
            self.conn.execute(f'DELETE FROM {table}')
        for table in TABLES:
            for row in before['merge_state']['tables'][table]:
                self.conn.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))
        if self.vault:
            for rel in set(after['vault_notes']) - set(before['vault_notes']):
                path = self.vault.root / rel
                self.vault._remember(path)
                path.unlink(missing_ok=True)
            for rel, encoded in before['vault_notes'].items():
                path = self.vault.root / rel
                self.vault._remember(path)
                path.write_bytes(base64.b64decode(encoded))
        self.conn.execute('UPDATE edit_history SET undone=1 WHERE id=?', (history['id'],))
        return dict(ok=True, undone=history['id'])
