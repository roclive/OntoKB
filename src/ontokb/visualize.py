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


_TEMPLATE = r"""<!DOCTYPE html>
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
#workspace {
  --panel-width: 380px; flex: 1; min-height: 0; display: grid;
  grid-template-columns: minmax(0, 1fr) 7px minmax(300px, var(--panel-width));
}
#graph { min-height: 0; }
#graph svg { width: 100%%; height: 100%%; display: block; }
#workspace-resizer {
  position: relative; z-index: 2; cursor: col-resize; touch-action: none; outline: none;
  background: transparent;
}
#workspace-resizer::after {
  content: ""; position: absolute; top: 0; bottom: 0; left: 3px; width: 1px;
  background: var(--border); transition: width 120ms ease, left 120ms ease, background 120ms ease;
}
#workspace-resizer:hover::after, #workspace-resizer:focus-visible::after, #workspace-resizer.dragging::after {
  left: 2px; width: 3px; background: color-mix(in srgb, var(--text) 42%%, var(--border));
}
body.resizing { cursor: col-resize; user-select: none; }
#query-panel {
  min-width: 0; background: var(--panel);
  display: flex; flex-direction: column; min-height: 0;
}
.panel-tabs {
  display: grid; grid-template-columns: 1fr 1fr; padding: 8px 14px 0;
  border-bottom: 1px solid var(--border);
}
.panel-tab {
  padding: 8px 4px 9px; border: 0; border-bottom: 2px solid transparent;
  background: transparent; color: var(--muted); font: inherit; cursor: pointer;
  transition: color 140ms ease, border-color 140ms ease;
}
.panel-tab:hover { color: var(--text); }
.panel-tab.active { color: var(--text); border-bottom-color: var(--text); font-weight: 600; }
.panel-view { display: none; min-height: 0; flex: 1; }
.panel-view.active { display: flex; flex-direction: column; animation: panel-in 160ms ease-out; }
@keyframes panel-in { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
#query-form { padding: 14px; display: grid; gap: 10px; border-bottom: 1px solid var(--border); }
#query-form label { font-size: 12px; color: var(--muted); }
#query-row { display: grid; grid-template-columns: minmax(0, 1fr) 76px; gap: 8px; }
#query-input, #api-base, #query-mode, #chat-mode {
  width: 100%%; padding: 7px 9px; font-size: 13px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text); outline: none;
}
#query-input:focus, #api-base:focus, #query-mode:focus, #chat-mode:focus, #search:focus {
  border-color: color-mix(in srgb, var(--text) 35%%, var(--border));
}
#query-button {
  border: 1px solid var(--border); border-radius: 6px; background: var(--text);
  color: var(--bg); font-size: 13px; cursor: pointer;
}
#query-button:disabled { opacity: 0.5; cursor: default; }
#query-options { display: grid; grid-template-columns: minmax(0, 1fr) 86px; gap: 8px; align-items: stretch; }
#api-base { grid-column: 1 / -1; }
.top-field {
  min-width: 0; padding: 0 7px; display: flex; align-items: center; gap: 3px;
  border: 1px solid var(--border); border-radius: 6px; background: var(--bg);
  color: var(--muted); font-size: 11px;
}
.top-field:focus-within { border-color: color-mix(in srgb, var(--text) 35%%, var(--border)); }
.top-field input {
  min-width: 0; width: 100%%; padding: 7px 0; border: 0; outline: 0;
  background: transparent; color: var(--text); font: inherit;
}
#query-expand-label {
  display: inline-flex; align-items: center; gap: 7px; font-size: 12px; color: var(--muted);
}
#query-expand { margin: 0; accent-color: var(--text); }
#query-status {
  padding: 8px 14px; font-size: 12px; color: var(--muted);
  border-bottom: 1px solid var(--border);
}
#query-results { flex: 1; min-height: 0; overflow: auto; }
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
#chat-messages {
  flex: 1; min-height: 0; overflow-y: auto; padding: 16px 14px 10px;
  display: flex; flex-direction: column; gap: 16px;
}
.chat-intro { color: var(--muted); font-size: 13px; max-width: 29em; }
.chat-message { animation: message-in 180ms ease-out; }
@keyframes message-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }
.chat-role { margin-bottom: 4px; color: var(--muted); font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.chat-body { line-height: 1.65; overflow-wrap: anywhere; }
.chat-body > :first-child { margin-top: 0; }
.chat-body > :last-child { margin-bottom: 0; }
.chat-body p { margin: 0 0 9px; }
.chat-body h1, .chat-body h2, .chat-body h3, .chat-body h4 {
  margin: 16px 0 7px; line-height: 1.3; color: var(--text); font-weight: 650;
}
.chat-body h1 { font-size: 18px; }
.chat-body h2 { font-size: 16px; }
.chat-body h3, .chat-body h4 { font-size: 14px; }
.chat-body ul, .chat-body ol { margin: 5px 0 10px; padding-left: 21px; }
.chat-body li { margin: 3px 0; padding-left: 2px; }
.chat-body blockquote {
  margin: 10px 0; padding: 2px 0 2px 11px; border-left: 2px solid var(--border); color: var(--muted);
}
.chat-body code {
  padding: 1px 4px; border-radius: 4px; background: color-mix(in srgb, var(--text) 8%%, transparent);
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.chat-body pre {
  margin: 10px 0; padding: 10px 11px; overflow-x: auto; border: 1px solid var(--border);
  border-radius: 7px; background: var(--bg); white-space: pre;
}
.chat-body pre code { padding: 0; border-radius: 0; background: transparent; }
.chat-body a { color: var(--text); text-decoration-color: var(--muted); text-underline-offset: 2px; }
.chat-body hr { margin: 13px 0; border: 0; border-top: 1px solid var(--border); }
.chat-table-wrap { margin: 10px 0; overflow-x: auto; border: 1px solid var(--border); border-radius: 7px; }
.chat-body table { width: 100%%; border-collapse: collapse; font-size: 12px; }
.chat-body th, .chat-body td { padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
.chat-body th { background: color-mix(in srgb, var(--text) 5%%, transparent); font-weight: 650; }
.chat-body tr:last-child td { border-bottom: 0; }
.chat-message.user { margin-left: 28px; }
.chat-message.user .chat-body {
  padding: 9px 11px; border-radius: 10px; background: var(--bg); border: 1px solid var(--border);
  white-space: pre-wrap;
}
.chat-sources { margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--border); color: var(--muted); font-size: 11px; }
#chat-form { padding: 10px 14px 14px; border-top: 1px solid var(--border); }
#chat-options { display: grid; grid-template-columns: minmax(0, 1fr) 86px; gap: 8px; margin-bottom: 8px; }
#chat-options select { width: 100%%; padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text); outline: none; }
#chat-expand-label { display: inline-flex; align-items: center; gap: 7px; margin-bottom: 9px; color: var(--muted); font-size: 12px; }
#chat-expand { margin: 0; accent-color: var(--text); }
#chat-composer { display: grid; grid-template-columns: minmax(0, 1fr) 66px; gap: 8px; align-items: end; }
#chat-input {
  width: 100%%; min-height: 42px; max-height: 120px; resize: vertical; padding: 9px 10px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--text);
  font: inherit; outline: none;
}
#chat-input:focus { border-color: color-mix(in srgb, var(--text) 35%%, var(--border)); }
#chat-button {
  height: 42px; border: 0; border-radius: 8px; background: var(--text); color: var(--bg);
  font: inherit; cursor: pointer; transition: opacity 140ms ease, transform 140ms ease;
}
#chat-button:hover { transform: translateY(-1px); }
#chat-button:disabled { opacity: .48; transform: none; cursor: default; }
.chat-hint { margin-top: 7px; color: var(--muted); font-size: 11px; }
#info {
  padding: 8px 16px; min-height: 56px; max-height: 120px; overflow-y: auto;
  font-size: 13px; color: var(--muted); border-top: 1px solid var(--border);
}
#info b { color: var(--text); font-weight: 600; }
.badge { font-size: 11px; padding: 1px 8px; border-radius: 8px; }
@media (max-width: 860px) {
  body { height: auto; min-height: 100vh; }
  #workspace { grid-template-columns: 1fr; grid-template-rows: 60vh auto; }
  #workspace-resizer { display: none; }
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
  <div id="workspace-resizer" role="separator" aria-label="调整图谱与右侧面板宽度" aria-orientation="vertical" tabindex="0"></div>
  <aside id="query-panel">
    <nav class="panel-tabs" aria-label="右侧工具">
      <button class="panel-tab active" type="button" data-panel="query-view">查询</button>
      <button class="panel-tab" type="button" data-panel="chat-view">Chat</button>
    </nav>
    <section id="query-view" class="panel-view active">
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
            <option value="phrase">全文匹配</option>
          </select>
          <label class="top-field">Top=<input id="query-top" type="number" value="20" min="1" max="200" step="1" aria-label="查询 Top K"></label>
        </div>
        <label id="query-expand-label"><input id="query-expand" type="checkbox" checked> 扩展相关词</label>
      </form>
      <div id="query-status">启动 `ontokb api` 后可查询 SQLite graph。</div>
      <div id="query-results"><div id="query-empty">输入关键词后查询相关节点和一跳关系。</div></div>
    </section>
    <section id="chat-view" class="panel-view">
      <div id="chat-messages" aria-live="polite">
        <div class="chat-intro">向知识库提问。系统会先检索 knowledge graph，再让 LLM 基于命中的实体与关系回答。</div>
      </div>
      <form id="chat-form">
        <div id="chat-options">
          <select id="chat-mode" aria-label="Chat 匹配模式">
            <option value="terms">按词匹配</option>
            <option value="phrase">全文匹配</option>
          </select>
          <label class="top-field">Top=<input id="chat-top" type="number" value="20" min="1" max="200" step="1" aria-label="Chat Top K"></label>
        </div>
        <label id="chat-expand-label"><input id="chat-expand" type="checkbox" checked> 扩展相关词</label>
        <div id="chat-composer">
          <textarea id="chat-input" rows="2" placeholder="例如：Codex 使用了什么技术？" aria-label="问题"></textarea>
          <button id="chat-button" type="submit">发送</button>
        </div>
        <div class="chat-hint">Enter 发送 · Shift + Enter 换行</div>
      </form>
    </section>
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
const workspace = document.getElementById('workspace');
const workspaceResizer = document.getElementById('workspace-resizer');
const savedPanelWidth = Number(localStorage.getItem('graphPanelWidth'));
if(Number.isFinite(savedPanelWidth) && savedPanelWidth >= 300){
  workspace.style.setProperty('--panel-width', savedPanelWidth + 'px');
}
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

let graphResizeFrame = 0;
new ResizeObserver(() => {
  cancelAnimationFrame(graphResizeFrame);
  graphResizeFrame = requestAnimationFrame(() => {
    const width = box.clientWidth || W;
    const height = box.clientHeight || H;
    svg.attr('viewBox', [0, 0, width, height]);
    sim.force('center', d3.forceCenter(width / 2, height / 2));
    sim.force('x', d3.forceX(width / 2).strength(0.05));
    sim.force('y', d3.forceY(height / 2).strength(0.06));
    sim.alpha(0.16).restart();
  });
}).observe(box);

function setPanelWidth(width, persist = true){
  const available = workspace.getBoundingClientRect().width;
  const max = Math.max(300, available - 320);
  const next = Math.round(Math.min(max, Math.max(300, width)));
  workspace.style.setProperty('--panel-width', next + 'px');
  workspaceResizer.setAttribute('aria-valuenow', String(next));
  workspaceResizer.setAttribute('aria-valuemin', '300');
  workspaceResizer.setAttribute('aria-valuemax', String(Math.round(max)));
  if(persist) localStorage.setItem('graphPanelWidth', String(next));
}

workspaceResizer.addEventListener('pointerdown', ev => {
  if(matchMedia('(max-width: 860px)').matches) return;
  workspaceResizer.setPointerCapture(ev.pointerId);
  workspaceResizer.classList.add('dragging');
  document.body.classList.add('resizing');
});
workspaceResizer.addEventListener('pointermove', ev => {
  if(!workspaceResizer.hasPointerCapture(ev.pointerId)) return;
  const rect = workspace.getBoundingClientRect();
  setPanelWidth(rect.right - ev.clientX, false);
});
function finishPanelResize(ev){
  if(workspaceResizer.hasPointerCapture(ev.pointerId)) workspaceResizer.releasePointerCapture(ev.pointerId);
  workspaceResizer.classList.remove('dragging');
  document.body.classList.remove('resizing');
  const width = parseFloat(getComputedStyle(workspace).getPropertyValue('--panel-width'));
  if(Number.isFinite(width)) localStorage.setItem('graphPanelWidth', String(Math.round(width)));
}
workspaceResizer.addEventListener('pointerup', finishPanelResize);
workspaceResizer.addEventListener('pointercancel', finishPanelResize);
workspaceResizer.addEventListener('dblclick', () => {
  localStorage.removeItem('graphPanelWidth');
  setPanelWidth(380, false);
});
workspaceResizer.addEventListener('keydown', ev => {
  if(!['ArrowLeft', 'ArrowRight'].includes(ev.key)) return;
  ev.preventDefault();
  const current = parseFloat(getComputedStyle(workspace).getPropertyValue('--panel-width')) || 380;
  setPanelWidth(current + (ev.key === 'ArrowLeft' ? 20 : -20));
});
setPanelWidth(savedPanelWidth || 380, false);

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
const queryTop = document.getElementById('query-top');
const queryButton = document.getElementById('query-button');
const queryStatus = document.getElementById('query-status');
const queryResults = document.getElementById('query-results');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatButton = document.getElementById('chat-button');
const chatMessages = document.getElementById('chat-messages');
const chatMode = document.getElementById('chat-mode');
const chatExpand = document.getElementById('chat-expand');
const chatTop = document.getElementById('chat-top');
const chatIntro = chatMessages.querySelector('.chat-intro');
let chatHealthChecked = false;

async function checkChatHealth(){
  if(chatHealthChecked) return;
  chatHealthChecked = true;
  try {
    const res = await fetch(apiUrl('/health', {}));
    if(!res.ok) throw new Error('HTTP ' + res.status);
    const health = await res.json();
    if(health.chat !== true){
      chatIntro.textContent = '当前运行的是旧版 API，不支持 Chat。请停止后重新运行 ontokb api。';
      chatIntro.dataset.state = 'error';
    } else if(!health.llm_configured){
      const keyName = health.llm_provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : 'OPENAI_API_KEY';
      chatIntro.textContent = '后端已连接，但未检测到 ' + keyName + '。请设置 Key 后重启 ontokb api。';
      chatIntro.dataset.state = 'error';
    }
  } catch (err) {
    chatIntro.textContent = '无法连接 Chat API。请确认 ontokb api 已在 127.0.0.1:8765 运行。';
    chatIntro.dataset.state = 'error';
  }
}

document.querySelectorAll('.panel-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.panel-tab').forEach(el => el.classList.toggle('active', el === tab));
    document.querySelectorAll('.panel-view').forEach(el => el.classList.toggle('active', el.id === tab.dataset.panel));
    if(tab.dataset.panel === 'chat-view'){
      checkChatHealth();
      chatInput.focus();
    }
  });
});

const params = new URLSearchParams(location.search);
if(params.get('api')) apiBase.value = params.get('api');
else if(localStorage.getItem('graphApiBase')) apiBase.value = localStorage.getItem('graphApiBase');
apiBase.addEventListener('change', () => localStorage.setItem('graphApiBase', apiBase.value.trim()));

function validTop(input){
  const value = Number(input.value);
  const valid = Number.isInteger(value) && value >= 1 && value <= 200;
  input.setCustomValidity(valid ? '' : 'Top K 必须是 1 到 200 之间的整数');
  if(!valid) input.reportValidity();
  return valid ? value : null;
}

function apiUrl(path, query){
  const base = apiBase.value.trim().replace(/\/$/, '');
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
  const top = validTop(queryTop);
  if(top === null) return;
  queryButton.disabled = true;
  queryStatus.textContent = '查询中…';
  try {
    const res = await fetch(apiUrl('/api/graph/query', {
      q,
      mode: queryMode.value,
      expand: queryExpand.checked ? '1' : '0',
      limit: String(top),
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

function renderInlineMarkdown(parent, source){
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\n]+\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  for(const match of source.matchAll(pattern)){
    if(match.index > cursor) parent.appendChild(document.createTextNode(source.slice(cursor, match.index)));
    const token = match[0];
    let element;
    if(token.startsWith('`')){
      element = document.createElement('code');
      element.textContent = token.slice(1, -1);
    } else if(token.startsWith('**')){
      element = document.createElement('strong');
      element.textContent = token.slice(2, -2);
    } else if(token.startsWith('*')){
      element = document.createElement('em');
      element.textContent = token.slice(1, -1);
    } else {
      const parts = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = parts[2].trim();
      let safe = false;
      try {
        const url = new URL(href, location.href);
        safe = ['http:', 'https:', 'mailto:'].includes(url.protocol);
      } catch (err) {}
      if(safe){
        element = document.createElement('a');
        element.href = href;
        element.target = '_blank';
        element.rel = 'noopener noreferrer';
        element.textContent = parts[1];
      } else {
        element = document.createTextNode(parts[1] + ' (' + href + ')');
      }
    }
    parent.appendChild(element);
    cursor = match.index + token.length;
  }
  if(cursor < source.length) parent.appendChild(document.createTextNode(source.slice(cursor)));
}

function markdownTableCells(line){
  return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
}

function renderMarkdown(container, markdown){
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');
  const fragment = document.createDocumentFragment();
  const tableDivider = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;
  const isBlockStart = (line, index) => /^\s*```/.test(line) || /^\s*#{1,4}\s+/.test(line)
    || /^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line) || /^\s*>\s?/.test(line)
    || /^\s*[-+*]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)
    || (line.includes('|') && index + 1 < lines.length && tableDivider.test(lines[index + 1]));

  for(let i = 0; i < lines.length;){
    const line = lines[i];
    if(!line.trim()){ i += 1; continue; }

    const fence = line.match(/^\s*```([\w+-]*)\s*$/);
    if(fence){
      const codeLines = [];
      i += 1;
      while(i < lines.length && !/^\s*```\s*$/.test(lines[i])) codeLines.push(lines[i++]);
      if(i < lines.length) i += 1;
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      if(fence[1]) code.dataset.language = fence[1];
      code.textContent = codeLines.join('\n');
      pre.appendChild(code);
      fragment.appendChild(pre);
      continue;
    }

    const heading = line.match(/^\s*(#{1,4})\s+(.+)$/);
    if(heading){
      const h = document.createElement('h' + heading[1].length);
      renderInlineMarkdown(h, heading[2].replace(/\s+#+\s*$/, ''));
      fragment.appendChild(h);
      i += 1;
      continue;
    }

    if(/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)){
      fragment.appendChild(document.createElement('hr'));
      i += 1;
      continue;
    }

    if(line.includes('|') && i + 1 < lines.length && tableDivider.test(lines[i + 1])){
      const headers = markdownTableCells(line);
      i += 2;
      const wrap = document.createElement('div');
      wrap.className = 'chat-table-wrap';
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      headers.forEach(value => {
        const th = document.createElement('th');
        renderInlineMarkdown(th, value);
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      while(i < lines.length && lines[i].includes('|') && lines[i].trim()){
        const tr = document.createElement('tr');
        markdownTableCells(lines[i]).forEach(value => {
          const td = document.createElement('td');
          renderInlineMarkdown(td, value);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
        i += 1;
      }
      table.appendChild(tbody);
      wrap.appendChild(table);
      fragment.appendChild(wrap);
      continue;
    }

    if(/^\s*>\s?/.test(line)){
      const quote = document.createElement('blockquote');
      const quoteLines = [];
      while(i < lines.length && /^\s*>\s?/.test(lines[i])) quoteLines.push(lines[i++].replace(/^\s*>\s?/, ''));
      renderInlineMarkdown(quote, quoteLines.join(' '));
      fragment.appendChild(quote);
      continue;
    }

    const listMatch = line.match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
    if(listMatch){
      const ordered = /^\d/.test(listMatch[1]);
      const list = document.createElement(ordered ? 'ol' : 'ul');
      const listPattern = ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-+*]\s+(.+)$/;
      while(i < lines.length){
        const itemMatch = lines[i].match(listPattern);
        if(!itemMatch) break;
        const li = document.createElement('li');
        renderInlineMarkdown(li, itemMatch[1]);
        list.appendChild(li);
        i += 1;
      }
      fragment.appendChild(list);
      continue;
    }

    const paragraphLines = [line.trim()];
    i += 1;
    while(i < lines.length && lines[i].trim() && !isBlockStart(lines[i], i)) paragraphLines.push(lines[i++].trim());
    const paragraph = document.createElement('p');
    renderInlineMarkdown(paragraph, paragraphLines.join(' '));
    fragment.appendChild(paragraph);
  }
  container.replaceChildren(fragment);
}

function appendMessage(role, body, context){
  const message = document.createElement('div');
  message.className = 'chat-message ' + role;
  const roleLabel = document.createElement('div');
  roleLabel.className = 'chat-role';
  roleLabel.textContent = role === 'user' ? 'You' : 'Knowledge graph';
  const content = document.createElement('div');
  content.className = 'chat-body';
  if(role === 'assistant') renderMarkdown(content, body);
  else content.textContent = body;
  message.append(roleLabel, content);
  const relations = context && context.relations ? context.relations : [];
  if(role === 'assistant' && context){
    const sources = document.createElement('div');
    sources.className = 'chat-sources';
    const modeLabel = context && context.mode === 'phrase' ? '全文匹配' : '按词匹配';
    const expandLabel = context && context.expand ? '扩展' : '不扩展';
    const topLabel = context && context.top ? 'Top ' + context.top : '';
    const strategy = [modeLabel, expandLabel, topLabel].filter(Boolean).join(' · ');
    sources.textContent = relations.length
      ? 'KG 上下文 · ' + strategy + ' · ' + relations.length + ' 条关系：' + relations.slice(0, 3).map(row => row.relation).join('；')
      : 'KG 上下文 · ' + strategy + ' · 未命中关系';
    message.appendChild(sources);
  }
  chatMessages.appendChild(message);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

chatInput.addEventListener('keydown', ev => {
  if(ev.key === 'Enter' && !ev.shiftKey){
    ev.preventDefault();
    chatForm.requestSubmit();
  }
});

chatForm.addEventListener('submit', async ev => {
  ev.preventDefault();
  const question = chatInput.value.trim();
  if(!question) return chatInput.focus();
  const top = validTop(chatTop);
  if(top === null) return;
  appendMessage('user', question);
  chatInput.value = '';
  chatButton.disabled = true;
  chatButton.textContent = '思考中';
  try {
    const res = await fetch(apiUrl('/api/chat', {}), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        question,
        mode: chatMode.value,
        expand: chatExpand.checked,
        top,
      }),
    });
    const result = await res.json();
    if(!res.ok) throw new Error(result.error || '请求失败');
    appendMessage('assistant', result.answer, result.context);
    if(result.context && result.context.edges && result.context.edges.length){
      highlightRelation(result.context.edges[0]);
    }
  } catch (err) {
    const detail = String(err.message || err);
    const hint = detail === 'Load failed' || detail === 'Failed to fetch'
      ? '无法连接 Chat API。可能仍在运行旧版后端，请停止后重新启动 `ontokb api`。'
      : '暂时无法回答：' + detail;
    appendMessage('assistant', hint);
  } finally {
    chatButton.disabled = false;
    chatButton.textContent = '发送';
    chatInput.focus();
  }
});
</script>
</body>
</html>
"""
