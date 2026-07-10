"""Export the knowledge graph as a standalone interactive HTML page.

Reads nodes/edges straight from the SQLite graph store (the source of
truth; entity notes are just a projection of it) and embeds them into a
self-contained D3 force-directed graph. Only external dependency is the
D3 script tag (CDN), so the file opens in any browser.
"""

from __future__ import annotations

import json
from pathlib import Path

from .graph import GraphStore

# type -> (base color, darker accent for light backgrounds)
_TYPE_COLORS = {
    "Organization": ("#7F77DD", "#534AB7"),
    "Person": ("#1D9E75", "#0F6E56"),
    "Product": ("#D85A30", "#993C1D"),
    "Technology": ("#378ADD", "#185FA5"),
    "Claim": ("#EF9F27", "#854F0B"),
    "Content": ("#D4537E", "#993556"),
    "Topic": ("#97C459", "#3B6D11"),
    "Event": ("#E24B4A", "#A32D2D"),
}
_FALLBACK_COLOR = ("#888780", "#5F5E5A")

_TYPE_LABELS_CN = {
    "Organization": "组织", "Person": "人物", "Product": "产品",
    "Technology": "技术", "Claim": "观点", "Content": "内容",
    "Topic": "话题", "Event": "事件", "Thing": "其他",
}


def graph_data(graph: GraphStore) -> dict:
    """Project entities + triples into the node/edge lists the page embeds."""
    nodes = [
        {"id": row["name"], "type": row["type"]}
        for row in graph.conn.execute("SELECT name, type FROM entities ORDER BY name")
    ]
    edges = [
        {"s": row["subject"], "p": row["predicate"], "t": row["object"]}
        for row in graph.conn.execute(
            """SELECT DISTINCT s.name AS subject, t.predicate, o.name AS object
               FROM triples t
               JOIN entities s ON s.id = t.subject_id
               JOIN entities o ON o.id = t.object_id
               ORDER BY s.name, t.predicate, o.name"""
        )
    ]
    return {"nodes": nodes, "edges": edges}


def render_html(data: dict, title: str = "Knowledge graph") -> str:
    # <-escape so entity names can never close the script tag
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    colors = {t: c for t, c in _TYPE_COLORS.items()}
    return _TEMPLATE % {
        "title": title,
        "data": payload,
        "colors": json.dumps(colors, ensure_ascii=False),
        "fallback": json.dumps(_FALLBACK_COLOR),
        "labels": json.dumps(_TYPE_LABELS_CN, ensure_ascii=False),
    }


def export_html(graph: GraphStore, out_path: str | Path,
                title: str = "Knowledge graph") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(graph_data(graph), title), encoding="utf-8")
    return out


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>%(title)s</title>
<style>
:root {
  --bg: #ffffff; --panel: #f7f6f3; --text: #2c2c2a; --muted: #6f6e68;
  --border: rgba(0,0,0,0.12); --link: rgba(0,0,0,0.18); --halo: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1a18; --panel: #242422; --text: #e8e6e0; --muted: #b4b2a9;
    --border: rgba(255,255,255,0.15); --link: rgba(255,255,255,0.22); --halo: #1a1a18;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  display: flex; flex-direction: column; height: 100vh;
}
header {
  padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 8px 16px;
  align-items: center; border-bottom: 1px solid var(--border);
}
header h1 { font-size: 15px; font-weight: 600; margin: 0 8px 0 0; }
#legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--muted); }
#legend span { display: inline-flex; align-items: center; gap: 4px; }
#legend i { width: 10px; height: 10px; border-radius: 50%%; display: inline-block; }
#search {
  margin-left: auto; padding: 5px 10px; font-size: 13px; width: 180px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel); color: var(--text); outline: none;
}
#stat { font-size: 12px; color: var(--muted); }
#workspace { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 380px; }
#graph { min-height: 0; }
#graph svg { width: 100%%; height: 100%%; display: block; }
#query-panel {
  min-width: 0; border-left: 1px solid var(--border); background: var(--panel);
  display: flex; flex-direction: column; min-height: 0;
}
#query-form { padding: 14px; display: grid; gap: 10px; border-bottom: 1px solid var(--border); }
#query-form label { font-size: 12px; color: var(--muted); }
#query-row { display: grid; grid-template-columns: minmax(0, 1fr) 76px; gap: 8px; }
#query-input, #api-base, #query-mode {
  width: 100%%; padding: 7px 9px; font-size: 13px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text); outline: none;
}
#query-input:focus, #api-base:focus, #query-mode:focus, #search:focus {
  border-color: color-mix(in srgb, var(--text) 35%%, var(--border));
}
#query-button {
  border: 1px solid var(--border); border-radius: 6px; background: var(--text);
  color: var(--bg); font-size: 13px; cursor: pointer;
}
#query-button:disabled { opacity: 0.5; cursor: default; }
#query-options { display: grid; grid-template-columns: minmax(0, 1fr) 108px; gap: 8px; align-items: end; }
#query-expand-label {
  display: inline-flex; align-items: center; gap: 7px; font-size: 12px; color: var(--muted);
}
#query-expand { margin: 0; accent-color: var(--text); }
#query-status {
  padding: 8px 14px; font-size: 12px; color: var(--muted);
  border-bottom: 1px solid var(--border);
}
#query-results { min-height: 0; overflow: auto; }
#query-results table { width: 100%%; border-collapse: collapse; table-layout: fixed; }
#query-results th, #query-results td {
  padding: 8px 10px; border-bottom: 1px solid var(--border);
  text-align: left; vertical-align: top; font-size: 12px;
}
#query-results th { color: var(--muted); font-weight: 600; background: var(--panel); position: sticky; top: 0; }
#query-results th:first-child, #query-results td:first-child { width: 74px; }
#query-results tbody tr { cursor: pointer; }
#query-results tbody tr:hover { background: color-mix(in srgb, var(--text) 7%%, transparent); }
#query-results tbody tr.active { background: color-mix(in srgb, var(--text) 12%%, transparent); }
#query-empty { padding: 14px; color: var(--muted); font-size: 13px; }
#info {
  padding: 8px 16px; min-height: 56px; max-height: 120px; overflow-y: auto;
  font-size: 13px; color: var(--muted); border-top: 1px solid var(--border);
}
#info b { color: var(--text); font-weight: 600; }
.badge { font-size: 11px; padding: 1px 8px; border-radius: 8px; }
@media (max-width: 860px) {
  body { height: auto; min-height: 100vh; }
  #workspace { grid-template-columns: 1fr; grid-template-rows: 60vh auto; }
  #query-panel { border-left: 0; border-top: 1px solid var(--border); max-height: 46vh; }
  #search { margin-left: 0; flex: 1 1 160px; }
}
</style>
</head>
<body>
<header>
  <h1>%(title)s</h1>
  <div id="legend"></div>
  <input type="text" id="search" placeholder="搜索实体…">
  <span id="stat"></span>
</header>
<main id="workspace">
  <div id="graph"></div>
  <aside id="query-panel">
    <form id="query-form">
      <label for="query-input">查询 knowledge graph</label>
      <div id="query-row">
        <input id="query-input" type="search" placeholder="harness agent" autocomplete="off">
        <button id="query-button" type="submit">查询</button>
      </div>
      <div id="query-options">
        <input id="api-base" type="url" value="http://127.0.0.1:8765" aria-label="API 地址">
        <select id="query-mode" aria-label="查询模式">
          <option value="terms">按词匹配</option>
          <option value="phrase">整句匹配</option>
        </select>
      </div>
      <label id="query-expand-label"><input id="query-expand" type="checkbox" checked> 扩展相关词</label>
    </form>
    <div id="query-status">启动 `ontokb api` 后可查询 SQLite graph。</div>
    <div id="query-results"><div id="query-empty">输入关键词后查询相关节点和一跳关系。</div></div>
  </aside>
</main>
<div id="info">悬停查看关系,点击固定选中,双击空白处重置,拖拽节点调整布局,滚轮缩放。</div>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const DATA = %(data)s;
const TYPE_COLORS = %(colors)s;
const FALLBACK = %(fallback)s;
const TYPE_CN = %(labels)s;
const isDark = matchMedia('(prefers-color-scheme: dark)').matches;
const ramp = t => TYPE_COLORS[t] || FALLBACK;
const color = t => ramp(t)[0];

const nodes = DATA.nodes.map(d => ({...d}));
const links = DATA.edges.map(e => ({source: e.s, target: e.t, p: e.p}));
const deg = {};
links.forEach(l => { deg[l.source]=(deg[l.source]||0)+1; deg[l.target]=(deg[l.target]||0)+1; });
nodes.forEach(n => n.deg = deg[n.id]||0);

document.getElementById('stat').textContent = nodes.length + ' 实体 · ' + links.length + ' 关系';

const counts = {};
nodes.forEach(n => counts[n.type]=(counts[n.type]||0)+1);
const legend = document.getElementById('legend');
Object.keys(counts).sort((a,b)=>counts[b]-counts[a]).forEach(t => {
  const span = document.createElement('span');
  span.innerHTML = '<i style="background:'+color(t)+'"></i>'+(TYPE_CN[t]||t)+' '+counts[t];
  legend.appendChild(span);
});

const box = document.getElementById('graph');
const W = box.clientWidth || 900, H = box.clientHeight || 600;
const svg = d3.select('#graph').append('svg').attr('viewBox', [0,0,W,H]);
const g = svg.append('g');
svg.call(d3.zoom().scaleExtent([0.2,5]).on('zoom', ev => g.attr('transform', ev.transform)));

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const link = g.append('g').selectAll('line').data(links).join('line')
  .attr('stroke', css('--link')).attr('stroke-width', 1);

const edgeLabel = g.append('g').selectAll('text').data(links).join('text')
  .text(d => d.p).attr('font-size', 9).attr('fill', css('--muted'))
  .attr('text-anchor','middle').style('opacity',0).style('pointer-events','none');

const radius = d => 5 + Math.min(Math.sqrt(d.deg)*2.4, 14);
const truncate = s => s.length > 16 ? s.slice(0,15)+'…' : s;

const node = g.append('g').selectAll('g').data(nodes).join('g')
  .style('cursor','pointer')
  .call(d3.drag()
    .on('start', (ev,d)=>{ if(!ev.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
    .on('drag', (ev,d)=>{ d.fx=ev.x; d.fy=ev.y; })
    .on('end', (ev,d)=>{ if(!ev.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }));

node.append('circle')
  .attr('r', radius)
  .attr('fill', d => color(d.type))
  .attr('stroke', css('--halo')).attr('stroke-width', 1.2);

node.append('text')
  .text(d => truncate(d.id))
  .attr('font-size', d => d.deg >= 6 ? 12 : 10)
  .attr('fill', css('--text'))
  .attr('text-anchor','middle')
  .attr('dy', d => radius(d) + 12)
  .style('pointer-events','none');

const sim = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d=>d.id).distance(80).strength(0.5))
  .force('charge', d3.forceManyBody().strength(-260))
  .force('center', d3.forceCenter(W/2, H/2))
  .force('collide', d3.forceCollide().radius(d => radius(d) + 12))
  .force('x', d3.forceX(W/2).strength(0.05))
  .force('y', d3.forceY(H/2).strength(0.06));

sim.on('tick', () => {
  link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
      .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
  edgeLabel.attr('x',d=>(d.source.x+d.target.x)/2).attr('y',d=>(d.source.y+d.target.y)/2 - 3);
  node.attr('transform', d=>'translate('+d.x+','+d.y+')');
});

function neighbors(id){
  const s = new Set([id]);
  links.forEach(l => {
    if(l.source.id===id) s.add(l.target.id);
    if(l.target.id===id) s.add(l.source.id);
  });
  return s;
}

const info = document.getElementById('info');
const DEFAULT_INFO = info.textContent;
let pinned = null;

function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }

function highlight(id){
  const nb = neighbors(id);
  node.style('opacity', d => nb.has(d.id) ? 1 : 0.12);
  link.style('opacity', l => (l.source.id===id||l.target.id===id) ? 1 : 0.06)
      .attr('stroke-width', l => (l.source.id===id||l.target.id===id) ? 1.8 : 1);
  edgeLabel.style('opacity', l => (l.source.id===id||l.target.id===id) ? 1 : 0);
  const rels = links.filter(l => l.source.id===id||l.target.id===id)
    .map(l => l.source.id===id
      ? '→ '+esc(l.p)+' → '+esc(l.target.id)
      : '← '+esc(l.p)+' ← '+esc(l.source.id));
  const n = nodes.find(n=>n.id===id);
  const accent = ramp(n.type)[isDark?0:1];
  info.innerHTML = '<b>'+esc(id)+'</b> <span class="badge" style="background:'+color(n.type)+'22;color:'+accent+'">'
    + (TYPE_CN[n.type]||esc(n.type)) + '</span><br>'
    + (rels.length ? rels.join(' · ') : '(无关系)');
}
function highlightRelation(edge){
  pinned = null;
  const subject = edge.subject || edge.s;
  const predicate = edge.predicate || edge.p;
  const object = edge.object || edge.t;
  node.style('opacity', d => (d.id===subject || d.id===object) ? 1 : 0.12);
  link.style('opacity', l => (l.source.id===subject && l.target.id===object && l.p===predicate) ? 1 : 0.05)
      .attr('stroke-width', l => (l.source.id===subject && l.target.id===object && l.p===predicate) ? 2.4 : 1);
  edgeLabel.style('opacity', l => (l.source.id===subject && l.target.id===object && l.p===predicate) ? 1 : 0);
  info.innerHTML = '<b>'+esc(subject)+'</b> → '+esc(predicate)+' → <b>'+esc(object)+'</b>';
}
function reset(){
  node.style('opacity',1);
  link.style('opacity',1).attr('stroke-width',1);
  edgeLabel.style('opacity',0);
  info.textContent = DEFAULT_INFO;
}
node.on('mouseover', (ev,d) => { if(!pinned) highlight(d.id); })
    .on('mouseout', () => { if(!pinned) reset(); else highlight(pinned); })
    .on('click', (ev,d) => { ev.stopPropagation(); pinned = d.id; highlight(d.id); });
svg.on('dblclick.zoom', null);
svg.on('dblclick', () => { pinned = null; reset(); });

document.getElementById('search').addEventListener('input', ev => {
  const q = ev.target.value.trim().toLowerCase();
  if(!q){ pinned=null; reset(); return; }
  const hit = nodes.filter(n => n.id.toLowerCase().includes(q));
  if(hit.length===1){ pinned=hit[0].id; highlight(pinned); return; }
  pinned = null;
  const ids = new Set(hit.map(n=>n.id));
  node.style('opacity', d => ids.has(d.id) ? 1 : 0.12);
  link.style('opacity', l => (ids.has(l.source.id)&&ids.has(l.target.id)) ? 1 : 0.06);
  edgeLabel.style('opacity', 0);
  info.textContent = '匹配 ' + hit.length + ' 个实体';
});

const queryForm = document.getElementById('query-form');
const queryInput = document.getElementById('query-input');
const apiBase = document.getElementById('api-base');
const queryMode = document.getElementById('query-mode');
const queryExpand = document.getElementById('query-expand');
const queryButton = document.getElementById('query-button');
const queryStatus = document.getElementById('query-status');
const queryResults = document.getElementById('query-results');

const params = new URLSearchParams(location.search);
if(params.get('api')) apiBase.value = params.get('api');
else if(localStorage.getItem('graphApiBase')) apiBase.value = localStorage.getItem('graphApiBase');
apiBase.addEventListener('change', () => localStorage.setItem('graphApiBase', apiBase.value.trim()));

function apiUrl(path, query){
  const base = apiBase.value.trim().replace(/\\/$/, '');
  const url = new URL(base + path);
  Object.entries(query).forEach(([k,v]) => url.searchParams.set(k, v));
  return url.toString();
}

function renderQueryResult(result){
  const rows = result.relations || [];
  const matched = (result.matched_entities || []).map(e => e.name).join('、');
  queryStatus.textContent = rows.length + ' 条关系' + (result.expand ? ' · 已扩展' : ' · 严格匹配') + (matched ? ' · 命中：' + matched : '');
  if(!rows.length){
    queryResults.innerHTML = '<div id="query-empty">没有找到相关关系。</div>';
    reset();
    return;
  }
  queryResults.innerHTML = '<table><thead><tr><th>triple_id</th><th>关系</th></tr></thead><tbody></tbody></table>';
  const tbody = queryResults.querySelector('tbody');
  rows.forEach((row, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>'+row.triple_id+'</td><td>'+esc(row.relation)+'</td>';
    tr.addEventListener('click', () => {
      queryResults.querySelectorAll('tr.active').forEach(el => el.classList.remove('active'));
      tr.classList.add('active');
      highlightRelation((result.edges || [])[i] || {});
    });
    tbody.appendChild(tr);
  });
  if(result.edges && result.edges.length) highlightRelation(result.edges[0]);
}

queryForm.addEventListener('submit', async ev => {
  ev.preventDefault();
  const q = queryInput.value.trim();
  if(!q){
    queryStatus.textContent = '请输入查询关键词。';
    queryInput.focus();
    return;
  }
  queryButton.disabled = true;
  queryStatus.textContent = '查询中…';
  try {
    const res = await fetch(apiUrl('/api/graph/query', {
      q,
      mode: queryMode.value,
      expand: queryExpand.checked ? '1' : '0',
      limit: '200',
    }));
    if(!res.ok) throw new Error(await res.text());
    renderQueryResult(await res.json());
  } catch (err) {
    queryResults.innerHTML = '<div id="query-empty">无法连接查询 API。请确认已运行 `ontokb api --host 127.0.0.1 --port 8765`。</div>';
    queryStatus.textContent = String(err.message || err);
  } finally {
    queryButton.disabled = false;
  }
});
</script>
</body>
</html>
"""
