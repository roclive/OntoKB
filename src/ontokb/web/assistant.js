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
if(location.protocol === 'http:' || location.protocol === 'https:') document.getElementById('api-base').value = location.origin;
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
    } else if(health.llm_provider === 'codex' && health.llm_configured){
      chatIntro.textContent = 'Codex 已接入。粘贴 YouTube 链接即可获取内容、分析并入库，也可以查询已有知识。';
    } else if(!health.llm_configured){
      const keyName = health.llm_provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : 'OPENAI_API_KEY';
      chatIntro.textContent = health.llm_provider === 'codex' ? '未找到 Codex CLI，请安装并运行 codex login。' : '后端已连接，但未检测到 ' + keyName + '。请设置 Key 后重启 ontokb api。';
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
  roleLabel.textContent = role === 'user' ? 'You' : 'Codex · 知识助手';
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
    if(context.video_analysis){
      sources.textContent = '视频已入库 · ' + relations.length + ' 条相关关系 · ';
      const link = document.createElement('a');
      link.textContent = context.video_analysis.title || '查看原视频';
      link.href = context.video_analysis.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      sources.appendChild(link);
    }
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
  chatButton.textContent = '处理中';
  const progress = document.createElement('div');
  progress.className = 'chat-hint';
  progress.textContent = '正在开始…';
  chatMessages.appendChild(progress);
  try {
    const res = await fetch(apiUrl('/api/chat', {}), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        question,
        stream: true,
        mode: chatMode.value,
        expand: chatExpand.checked,
        top,
      }),
    });
    if(!res.ok) { const error = await res.json(); throw new Error(error.error || '请求失败'); }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', result = null;
    while(true){
      const {value, done} = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for(const line of lines){
        if(!line.trim()) continue;
        const event = JSON.parse(line);
        if(event.error) throw new Error(event.error);
        if(event.status) progress.textContent = event.status;
        if(event.result) result = event.result;
      }
      if(done) break;
    }
    if(!result) throw new Error('连接中断，未收到完整结果。请重试；已入库视频会复用。');
    if(result.ingested){
      progress.textContent = '已入库 · 正在更新摘要与图谱…';
      try { await refreshReading(result.ingested.content_id); progress.textContent = '摘要与图谱已更新，可在阅读工作台漫游。'; }
      catch (err) { progress.textContent = '已入库，请刷新页面查看新摘要。'; }
    }
    else progress.remove();
    appendMessage('assistant', result.answer, result.context);
    if(result.context && result.context.edges && result.context.edges.length){
      highlightRelation(result.context.edges[0]);
    }
  } catch (err) {
    progress.remove();
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
