/* Curation belongs to the reader. Model comparisons never write a personal stance. */
(() => {
  const node = (tag, text, cls) => { const n=document.createElement(tag); if(text!=null)n.textContent=text;if(cls)n.className=cls;return n; };
  const byId=id=>document.getElementById(id);
  const labels={unset:'未表态',agree:'认同',uncertain:'存疑',disagree:'不认同'};
  const entry=node('button','个人记忆');entry.id='memory-open';byId('editor-open')?.before(entry);
  const dialog=node('dialog');dialog.id='memory-dialog';dialog.setAttribute('aria-labelledby','memory-title');
  dialog.innerHTML=`<div class="ke-shell"><header class="ke-header"><div><div class="eyebrow">PERSONAL RESEARCH MEMORY</div><h2 id="memory-title">个人记忆与判断变化</h2><p>收录是记住；审核是检查；个人立场由你决定。</p></div><button id="memory-close" aria-label="关闭个人记忆">×</button></header>
    <div class="memory-toolbar"><input id="memory-search" type="search" placeholder="搜索实体、论断或关系…" aria-label="搜索个人记忆"><select id="memory-scope" aria-label="记忆范围"><option value="all">全部知识</option><option value="included">个人记忆</option><option value="unreviewed">未审核</option><option value="reviewed">已审核</option><option value="history">判断变化记录</option></select><select id="memory-kind" aria-label="知识类别"><option value="all">全部类别</option><option value="claim">论断</option><option value="triple">关系</option><option value="entity">实体与概念</option></select></div>
    <div class="memory-toolbar"><select id="memory-source" aria-label="选择用于对照的新资料"></select><button id="memory-compare">新资料对旧判断的影响</button></div>
    <div class="ke-layout"><aside class="ke-sidebar"><div id="memory-count" class="ke-count"></div><div id="memory-list" class="ke-list"></div></aside><section class="ke-main"><div id="memory-detail" class="ke-content"></div></section></div><div id="memory-feedback" class="ke-feedback" role="status"></div></div>`;
  document.body.append(dialog);
  let data=null,selected=null,busy=false,dirty=false,lastFocus=null,lastScope='all',lastKind='all';
  const feedback=(text,error=false)=>{byId('memory-feedback').textContent=text;byId('memory-feedback').classList.toggle('error',error);};
  async function request(path,body){const response=await fetch(apiUrl(path,{}),body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error||'操作失败');return result;}
  function setBusy(value){busy=value;dialog.querySelectorAll('button,input,select,textarea').forEach(n=>n.disabled=value);dialog.setAttribute('aria-busy',String(value));}
  function guard(action){if(busy)return false;if(dirty&&!confirm('有未保存的个人判断，确定放弃修改？'))return false;dirty=false;action();return true;}
  const stateText=s=>`${s.reviewed?'已审核':'未审核'} · ${s.included?'个人记忆':'资料库'} · ${labels[s.stance]||s.stance}`;
  function renderList(){
    if(!data)return;const list=byId('memory-list');list.replaceChildren();
    const scope=byId('memory-scope').value,q=byId('memory-search').value.trim().toLocaleLowerCase(),kind=byId('memory-kind').value;
    const rows=data.records.filter(r=>(!q||(r.snapshot.title+' '+r.note).toLocaleLowerCase().includes(q))&&(kind==='all'||r.snapshot.kind===kind)&&(scope==='included'?r.included:scope==='reviewed'?r.reviewed:scope==='unreviewed'?!r.reviewed:true));
    byId('memory-count').textContent=rows.length+' 条知识记录';
    if(scope==='history'){showHistory();return;}
    for(const row of rows.slice(0,250)){const b=node('button',null,'ke-item');b.setAttribute('aria-current',String(selected?.key===row.key));b.append(node('strong',row.snapshot.title),node('small',stateText(row)+(row.current?'':' · 历史快照')));b.onclick=()=>guard(()=>select(row));list.append(b);}
    if(!rows.length)list.append(node('p','没有符合条件的记录。','ke-empty'));
    if(rows.length>250)list.append(node('p','显示前 250 条，请搜索缩小范围。','ke-source'));
  }
  function showHistory(){
    selected=null;const content=byId('memory-detail');content.replaceChildren(node('h3','判断变化记录'),node('p','这里只记录你实际保存的审核、范围和立场变化。AI 对照建议不会写入这里。','ke-subtitle'));
    const q=byId('memory-search').value.trim().toLocaleLowerCase();
    const rows=data.history.filter(h=>{const r=data.records.find(r=>r.key===h.memory_key);return (!q||r?.snapshot.title.toLocaleLowerCase().includes(q))&&(byId('memory-kind').value==='all'||r?.snapshot.kind===byId('memory-kind').value);});
    if(!rows.length)content.append(node('p','尚无判断变化记录。'));
    for(const h of rows){const r=data.records.find(r=>r.key===h.memory_key),section=node('section',null,'ke-history-row');section.append(node('strong',r?.snapshot.title||h.memory_key),node('small',h.created_at),node('p',stateText(h.before_state)+' → '+stateText(h.after_state)),node('p','原说明：'+(h.before_state.note||'无')),node('p','新说明：'+(h.after_state.note||'无')));if(h.source_id)section.append(node('p','影响资料：'+(data.sources.find(s=>s.id===h.source_id)?.title||h.source_id)));content.append(section);}
  }
  function field(form,title,id,tag='select'){const label=node('label',title),input=node(tag);input.id=id;label.append(input);form.append(label);return input;}
  function select(row){
    if(byId('memory-scope').value==='history'){byId('memory-scope').value='all';lastScope='all';}
    selected=row;dirty=false;const content=byId('memory-detail');content.replaceChildren(node('h3',row.snapshot.title),node('p',row.current?'设置仅属于这条记录，不会连带认可邻接实体或其他关系。':'原记录已变化或移除；这里保留当时的个人判断快照。','ke-subtitle'));
    const form=node('form');content.append(form);
    const reviewed=field(form,'审核状态','memory-reviewed');reviewed.add(new Option('未审核','false'));reviewed.add(new Option('已审核','true'));reviewed.value=String(row.reviewed);
    const included=field(form,'记忆范围','memory-included');included.add(new Option('仅保留在资料库','false'));included.add(new Option('纳入个人记忆','true'));included.value=String(row.included);
    let stance=null;if(row.snapshot.kind!=='entity'){stance=field(form,'我的立场（与事实核实状态独立）','memory-stance');for(const [value,label]of Object.entries(labels))stance.add(new Option(label,value));stance.value=row.stance;}
    const note=field(form,'我的判断或适用条件','memory-note','textarea');note.maxLength=4000;note.value=row.note;
    const influence=field(form,'这次修改受哪篇资料影响（可选）','memory-influence');influence.add(new Option('没有指定资料',''));for(const s of data.sources)influence.add(new Option(s.title||s.id,s.id));
    const save=node('button','保存个人判断','primary');save.type='submit';form.append(save);
    form.addEventListener('input',()=>dirty=true);form.addEventListener('change',()=>dirty=true);
    form.onsubmit=async event=>{event.preventDefault();if(busy)return;setBusy(true);feedback('正在保存…');let saved=false;try{const result=await request('/api/memory/review',{key:row.key,revision:row.revision,reviewed:reviewed.value==='true',included:included.value==='true',stance:stance?.value||'unset',note:note.value,source_id:influence.value});saved=true;dirty=false;await reload();select(data.records.find(r=>r.key===row.key));feedback(result.changed?'个人判断已保存，变化记录已保留。':'判断没有变化，未新增变化记录。');}catch(error){feedback((saved?'个人判断已保存，但页面刷新失败，请重新打开。':'')+error.message,true);}finally{setBusy(false);}};
    const section=node('section',null,'ke-section');section.append(node('h4','当时记录的来源与证据'));
    for(const id of row.snapshot.sources){const source=data.sources.find(s=>s.id===id);const p=node('p',source?.title||id,'ke-source');if(source?.url&&/^https?:\/\//i.test(source.url)){const a=node('a',' 打开来源 ↗');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';p.append(a);}section.append(p);}
    for(const evidence of row.snapshot.evidence.slice(0,20))if(evidence.quote)section.append(node('blockquote',evidence.quote,'ke-evidence'));
    if(!row.snapshot.evidence.some(e=>e.quote))section.append(node('p','没有保存逐字证据；收录或审核都不等于事实已证实。','ke-source'));
    content.append(section);renderList();
  }
  async function reload(){data=await request('/api/memory');const select=byId('memory-source'),previous=select.value||currentDoc?.id;select.replaceChildren(new Option('选择用于对照的新资料',''));for(const source of data.sources)select.add(new Option(source.title||source.id,source.id));select.value=previous||'';renderList();}
  entry.onclick=async()=>{lastFocus=document.activeElement;stopTour();dialog.showModal();setBusy(true);feedback('正在读取个人记忆…');try{await reload();byId('memory-detail').replaceChildren(node('h3','先标记，再比较'),node('p','现有知识默认留在资料库。可以把不认同或尚未审核的内容也纳入个人记忆；系统不会将它们当成你认可的事实。'),node('p','要比较新资料，请先为其他资料中的论断或关系保存个人立场，再点击上方“新资料对旧判断的影响”。'));feedback('');}catch(error){feedback(error.message,true);}finally{setBusy(false);}};
  byId('memory-compare').onclick=()=>guard(async()=>{const id=byId('memory-source').value;if(!id){feedback('请先选择用于对照的新资料。',true);return;}selected=null;setBusy(true);feedback('正在对照个人判断，可能需要几分钟…');try{const result=await request('/api/memory/compare',{source_id:id});const content=byId('memory-detail');content.replaceChildren(node('h3','新资料对旧判断的影响'),node('p','待确认建议 · 不会自动修改个人记忆','ke-subtitle'),node('div',result.answer,'memory-report'));if(result.scope)content.append(node('p',result.scope,'ke-source'));if(result.baseline?.length){content.append(node('h4','对照的个人判断 · 点击修改立场'));for(const r of result.baseline){const b=node('button',r.snapshot.title,'ke-related');b.onclick=()=>{select(r);byId('memory-influence').value=id;};content.append(b);}}feedback('对照完成。只有保存个人判断后，才会记录为你的实际变化。');}catch(error){feedback(error.message,true);}finally{setBusy(false);}});
  byId('memory-search').oninput=renderList;
  byId('memory-scope').onchange=()=>{if(guard(renderList))lastScope=byId('memory-scope').value;else byId('memory-scope').value=lastScope;};
  byId('memory-kind').onchange=()=>{if(guard(renderList))lastKind=byId('memory-kind').value;else byId('memory-kind').value=lastKind;};
  const close=()=>{dialog.close();lastFocus?.focus();};byId('memory-close').onclick=()=>guard(close);dialog.addEventListener('cancel',event=>{event.preventDefault();guard(close);});
  window.addEventListener('beforeunload',event=>{if(dirty||busy){event.preventDefault();event.returnValue='';}});
})();
